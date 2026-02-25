"""
Time Awareness Module (TAM): scheduling and reminders.

TAM can be used in two ways:

1) Tools (no LLM in TAM; preferred): The main model calls tools with structured args; TAM only
   consumes them. Tools: remind_me(minutes or at_time, message) for one-shot reminders;
   record_date(event_name, when, note) for recording dates/events (e.g. "Spring Festival is in
   two weeks"); cron_schedule(cron_expr, message) for recurring. TAM provides schedule_one_shot,
   record_event, schedule_cron_task and holds the scheduler. No second LLM parse.

2) route_to_tam (legacy): User message is passed to TAM; TAM runs its own LLM to parse intent
   into JSON (type reminder/cron, sub_type, interval, etc.) and then schedules. Use only when
   the request is too complex for the structured tools.
"""
import asyncio
from datetime import datetime, timedelta
import json
import random
import signal
import sys
import threading
import time
from typing import List, Dict, Optional, Any
from loguru import logger
from pathlib import Path
from schedule import Scheduler

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from base.base import IntentType, Intent, PromptRequest
from base.prompt_manager import get_prompt_manager
from base.util import Util
from core.coreInterface import CoreInterface
from memory import tam_storage


def _safe_user_id_for_recorded_events(system_user_id: Optional[str]) -> str:
    """Safe filename for per-user recorded events. None/empty -> '_default'. Never raises."""
    try:
        if not system_user_id or not isinstance(system_user_id, str):
            return "_default"
        import re
        s = re.sub(r"[^\w\-.]", "_", (system_user_id or "").strip())
        s = (s[:200] if len(s) > 200 else s) or "_default"
        return s or "_default"
    except Exception:
        return "_default"


class TAM:
    def __init__(self, coreInst: CoreInterface):
        logger.debug("TAM initializing...")
        #self.intent_queue = asyncio.Queue(100)
        #self.intent_queue_task = None
        self.scheduler = Scheduler()
        self.scheduled_jobs = []
        self.coreInst = coreInst
        # Cron-style jobs: list of {cron_expr, task, job_id, next_run, params}; next_run is datetime
        self.cron_jobs: List[Dict] = []
        self._cron_lock = threading.Lock()
        # Recorded events (no LLM): from record_date tool; e.g. "son's birthday", "Spring Festival".
        # Stored per-user under database/tam_recorded_events/{safe_user_id}.json. Cleared on memory reset (all users).
        self._recorded_events_dir: Optional[Path] = None

        # Load persisted cron jobs and one-shot reminders (survives Core restart)
        self._load_cron_jobs_from_db()
        self._load_one_shot_reminders_from_db()

        # Start the thread to handle the intent queue
        # Register signal handlers
        #signal.signal(signal.SIGINT, self.signal_handler)
        logger.debug("TAM initialized!")

    #def signal_handler(self, signum, frame):
    #    logger.debug('Received SIGINT, shutting down gracefully...')
    #    self.stop_intent_queue_handler()
        # Exit the program
        # sys.exit(0)

    #def add_intent(self, intent: Intent):
    #    logger.debug(f"TAM add intent: {intent}")
    #    self.intent_queue.put_nowait(intent)
    #    logger.debug(f"TAM added intent: {intent}")

    '''
    async def start_intent_queue_handler(self):
        logger.debug("Starting intent queue handler task...")
        self.intent_queue_task = asyncio.create_task(self.process_intent_queue())
        logger.debug("Intent queue handler task started.")

    async def stop_intent_queue_handler(self):
        # Add None to the queue to signal the task to shut down
        logger.debug("Stopping intent queue handler task...")
        await self.intent_queue.put(None)
        if self.intent_queue_task:
            await self.intent_queue_task
        logger.debug("Intent queue handler task stopped.")


    async def process_intent_queue(self):
        while True:
            try:
                logger.debug(f"TAM intent queue size before get: {self.intent_queue.qsize()}")
                intent: Intent = await self.intent_queue.get()
                logger.debug(f"TAM intent queue size after get: {self.intent_queue.qsize()}")
                if intent is None:
                    break

                    # Analyze the intent using LLM and create a data object
                    data_object = await self.analyze_intent_with_llm(intent)
                    
                    # Use the data object to schedule a job
                    self.schedule_job_from_intent(data_object)
            except Exception as e:
                logger.exception(f"TAM: Error processing intent: {e}")
            finally:
                self.intent_queue.task_done()
            await asyncio.sleep(0.1)  # Small sleep to avoid tight loop
    '''

    async def process_intent(self, intent: Intent, request: PromptRequest) -> Optional[str]:
        """Process time/scheduling intent. Returns the message sent to the user (if any) so sync inbound can return it; otherwise None."""
        if intent is None:
            return None
        try:
            logger.debug(f"TAM process_intent: {intent}")
            # Analyze the intent using LLM and create a data object
            data_object = await self.analyze_intent_with_llm(intent)
            logger.debug(f"TAM got data_object: {data_object}")
            if data_object is None or not isinstance(data_object, dict):
                logger.warning("TAM: No valid scheduling data from LLM; cannot schedule.")
                # Return as tool result only (do not send to channel). Model will see it and can call route_to_plugin or other tools; user never sees this internal message.
                msg = (
                    "That request was not a scheduling intent. Use route_to_plugin for: list nodes (plugin homeclaw-browser, capability node_list), open URL (browser_navigate), canvas (canvas_update), or other plugins. Use remind_me/record_date/cron_schedule only for time-related requests. Do not repeat this message to the user; call the appropriate tool or reply naturally."
                )
                return msg
            # Use the data object to schedule a job
            self.schedule_job_from_intent(data_object, request)
            return None
        except Exception as e:
            logger.exception(f"TAM: Error processing intent: {e}")
            msg = "Something went wrong setting the reminder. Please try again with a clear time (e.g. \"remind me in 5 minutes\")."
            try:
                await self.coreInst.send_response_to_request_channel(response=msg, request=request)
            except Exception:
                pass
            return msg


    async def analyze_intent_with_llm(self, intent: Intent) -> Dict:
        # Combine the input text and chat history into a single context
        text = intent.text
        hist = intent.chatHistory
        
        # Create the prompt
        prompt = self.create_prompt(text, hist)
        logger.debug(f'TAM Prompt: {prompt}')
        
        # Prepare messages for the language model
        messages = [{"role": "system", "content": prompt}]
        
        # Get the response from the language model
        response_str = await Util().openai_chat_completion(messages)
        response_str = response_str.strip()
        if not response_str:
            logger.error('TAM: LLM response is empty')
            return None
        logger.debug(f'TAM got response: {response_str}')
        
        # Parse the response into a JSON object
        try:
            extracted = Util().extract_json_str(response_str)
            if extracted is None or (isinstance(extracted, str) and not extracted.strip()):
                logger.error('TAM: No JSON object found in LLM response')
                return None
            response_str = extracted if isinstance(extracted, str) else str(extracted)
            logger.debug(response_str)
            response_json = json.loads(response_str)
            if not isinstance(response_json, dict):
                logger.error('TAM: LLM response JSON is not an object')
                return None
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error('TAM: Failed to decode LLM response JSON: {}', e)
            return None

        return response_json

    '''
    def create_prompt(self, text: str, chat_history: str) -> str:

       # Get the current datetime
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
     # Create the prompt with the current datetime
        prompt = f"""
        You are an expert at understanding user intentions based on chat history and user input. Use the provided chat history, user input, and the current datetime to determine the user's intent and create a structured JSON object for scheduling a job.

        Current datetime: {current_datetime}

        Guidelines:
        1. Use the provided chat history and user input to determine the user's intent.
        2. Ensure the intent is accurate, concise, and directly addresses the user's query.
        3. If the intent is related to scheduling, extract relevant time-based information and create a JSON object.
        4. Use the current datetime as a reference to determine appropriate scheduling times.
        5. Prioritize the most recent time information in the chat history and user input.
        6. Calculate the exact start time for the reminder based on the user's input and the current datetime.
        7. Refine the message in the parameters to be in the voice of the AI assistant, not just extracted from the input.
        8. If a start time is not provided, use the current datetime as the start time.
        9. The JSON object should include the type of job, the interval, and any necessary parameters.

        Provide the JSON object in the following format:
        {{
            "type": "reminder",
            "sub_type": "repeated | fixed | random",
            "interval_unit": "seconds | minutes | hours | days | weeks | months | years",
            "interval": number,
            "start_time": "YYYY-MM-DD HH:MM:SS" (ISO 8601 format) (optional for repeated events),
            "params": {{
                "message": "The message to be reminded or the content of the conversation",
                "repeat": "true" (optional, for repeated events only)
            }}
        }}

        Examples:

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: I have a meeting with John tomorrow at 8 AM.
        AI: Got it. Do you need a reminder?

        User Input:
        Yes, please remind me 30 minutes before.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "fixed",
            "interval_unit": "minutes",
            "interval": 30,
            "start_time": "2023-07-06 07:30:00",
            "params": {{"message": "Reminder: You have a meeting with John tomorrow at 8 AM. This is your 30-minute reminder."}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: My son's birthday is on 19th August.
        AI: Happy Birthday!

        User Input:
        Please remind me a week before his birthday every year.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "repeated",
            "interval_unit": "years",
            "interval": 1,
            "start_time": "2023-08-12 08:00:00",
            "params": {{"message": "Reminder: Your son's birthday is on 19th August. This is your one-week reminder.", "repeat": "true"}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: I have a lunch appointment at 2 PM today.
        AI: Sure, do you need a reminder?

        User Input:
        Yes, please remind me an hour before.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "fixed",
            "interval_unit": "hours",
            "interval": 1,
            "start_time": "2023-07-05 13:00:00",
            "params": {{"message": "Reminder: You have a lunch appointment at 2 PM today. This is your one-hour reminder."}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: I have an event the day after tomorrow.
        AI: Got it. Do you need a reminder?

        User Input:
        Yes, please remind me the day before.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "fixed",
            "interval_unit": "days",
            "interval": 1,
            "start_time": "2023-07-06 00:00:00",
            "params": {{"message": "Reminder: You have an event the day after tomorrow. This is your one-day reminder."}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: I have a meeting in 10 minutes.
        AI: Got it. Do you need a reminder?

        User Input:
        Yes, please remind me 5 minutes ahead.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "fixed",
            "interval_unit": "minutes",
            "interval": 5,
            "start_time": "2023-07-05 10:05:00",
            "params": {{"message": "Reminder: You have a meeting in 10 minutes. This is your 5-minute reminder."}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: Please remind me every 10 minutes.

        User Input:
        Sure, I will remind you every 10 minutes.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "repeated",
            "interval_unit": "minutes",
            "interval": 10,
            "start_time": "2023-07-05 10:10:00",
            "params": {{"message": "Reminder: This is your 10-minute reminder.", "repeat": "true"}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: Please say hello to me every 1 minute.

        User Input:
        Sure, I will remind you every minute.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "repeated",
            "interval_unit": "minutes",
            "interval": 1,
            "start_time": "2023-07-05 10:01:00",
            "params": {{"message": "Reminder: Hello! This is your 1-minute reminder.", "repeat": "true"}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: Please start to remind me from 9 am every 30 minutes.

        User Input:
        Sure, I will remind you every 30 minutes starting from 9 AM.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "repeated",
            "interval_unit": "minutes",
            "interval": 30,
            "start_time": "2023-07-06 09:00:00",
            "params": {{"message": "Reminder: This is your 30-minute reminder.", "repeat": "true"}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: Please send me some quotes in the morning.

        User Input:
        Sure, I will send you quotes every morning.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "random",
            "interval_unit": "days",
            "interval": 1,
            "start_time": "{current_datetime}",
            "params": {{"message": "Reminder: Here is your morning quote.", "repeat": "true"}}
        }}

        Current datetime: 2023-07-05 10:00:00

        Chat History:
        User: Please send me some short stories in the evening.

        User Input:
        Sure, I will send you short stories every evening.

        Determine the user's intent and create a JSON object:
        {{
            "type": "reminder",
            "sub_type": "random",
            "interval_unit": "days",
            "interval": 1,
            "start_time": "{current_datetime}",
            "params": {{"message": "Reminder: Here is your evening short story.", "repeat": "true"}}
        }}

        Current datetime: {current_datetime}

        Chat History:
        {chat_history}

        User Input:
        {text}

        Determine the user's intent and create a JSON object:
        """
        return prompt
    '''
    def _create_prompt_fallback(self, text: str, chat_history: str) -> str:
        """Fallback when use_prompt_manager is false or config/prompts/tam/scheduling not found."""
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return (
            "You are an expert at understanding user intentions for scheduling. Use the chat history, user input, and current datetime to create a JSON object for a reminder or cron job.\n\n"
            f"Current datetime: {current_datetime}\n\n"
            "Guidelines: Use chat history and user input. For cron use type \"cron\" with cron_expr; for intervals use type \"reminder\" with sub_type repeated/fixed/random. Use current datetime if no start time.\n\n"
            f"Chat History:\n{chat_history}\n\nUser Input:\n{text}\n\nDetermine the user's intent and create a JSON object:"
        )

    def create_prompt(self, text: str, chat_history: str) -> str:
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        meta = Util().get_core_metadata()
        if getattr(meta, "use_prompt_manager", False):
            try:
                pm = get_prompt_manager(
                    prompts_dir=getattr(meta, "prompts_dir", None),
                    default_language=getattr(meta, "prompt_default_language", "en"),
                    cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                )
                lang = Util().main_llm_language()
                content = pm.get_content(
                    "tam", "scheduling", lang=lang,
                    current_datetime=current_datetime, chat_history=chat_history or "", text=text,
                )
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.debug("TAM prompt manager fallback: {}", e)
        return self._create_prompt_fallback(text, chat_history)    

    def schedule_job_from_intent(self, data_object: Dict, request: PromptRequest):
        if data_object is None or not isinstance(data_object, dict):
            logger.warning("TAM: schedule_job_from_intent called with invalid data_object; skipping.")
            return
        logger.debug(f"Scheduling job with data: {data_object}")
        job_type = data_object.get('type')
        params: Dict = data_object.get('params', {})

        if job_type is None or job_type == "null":
            logger.debug("TAM: intent is not scheduling (type is null); skip scheduling.")
            return
        if job_type == "cron":
            cron_expr = data_object.get("cron_expr")
            if not cron_expr:
                logger.error("TAM: cron type requires cron_expr (e.g. '0 9 * * *' for daily at 9:00)")
                return
            async def cron_task():
                await self.send_reminder_to_latest_channel(params.get("message", ""))

            self.schedule_cron_task(cron_task, cron_expr, params=params)
            return

        sub_type = data_object.get('sub_type')
        interval_unit = data_object.get('interval_unit')
        interval = data_object.get('interval')
        start_time = data_object.get('start_time')

        if job_type == "reminder":
            async def task():
                await self.send_reminder_to_latest_channel(params.get("message"))
        else:
            logger.error(f'TAM: Unsupported job type: {job_type}')
            return
        if sub_type == "repeated":
            self.schedule_repeated_task(task, interval_unit, interval, start_time)
        elif sub_type == "fixed":
            self.schedule_fixed_task(task, start_time)
        elif sub_type == "random":
            self.schedule_random_task(task, interval_unit, interval, start_time)
        else:
            logger.error(f'TAM: Unsupported sub-type: {sub_type}')

    async def send_reminder(self, message: str, request: PromptRequest):
        await self.coreInst.send_response_to_request_channel(response=message, request=request)

    async def send_reminder_to_latest_channel(self, message: str):
        await self.coreInst.send_response_to_latest_channel(response=message)

    async def send_reminder_to_channel(self, message: str, params: Optional[Dict[str, Any]] = None):
        """Send reminder: if core has deliver_to_user, push to user (Companion + channel); else to channel by channel_key or latest. Never raises (logs and continues)."""
        try:
            params = params or {}
            user_id = params.get("user_id")
            channel_key = params.get("channel_key")
            if hasattr(self.coreInst, "deliver_to_user"):
                await self.coreInst.deliver_to_user(
                    user_id or "companion",
                    message or "Reminder",
                    channel_key=channel_key,
                    source="cron" if params.get("_cron") else "reminder",
                )
            elif channel_key and hasattr(self.coreInst, "send_response_to_channel_by_key"):
                await self.coreInst.send_response_to_channel_by_key(channel_key, message or "Reminder")
            else:
                await self.send_reminder_to_latest_channel(message or "Reminder")
        except Exception as e:
            logger.exception("TAM: send_reminder_to_channel failed: {}", e)

    async def _send_reminder_to_channel_safe(self, message: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Like send_reminder_to_channel but never raises (logs and continues). Used by cron tasks so Core does not crash."""
        try:
            await self.send_reminder_to_channel(message, params or {})
        except Exception as e:
            logger.exception("TAM: send_reminder_to_channel failed: {}", e)


    def schedule_repeated_task(self, task, interval_unit, interval, start_time=None):
        logger.debug(f"Scheduled task to repeat every {interval} {interval_unit} at {start_time}")
        def job_wrapper():
            asyncio.run(task())
            # Schedule the next run using the schedule library
            self._schedule_interval_task(task, interval_unit, interval)

        if start_time:
            now = datetime.now()
            start_time_obj = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time_delta = start_time_obj + timedelta(minutes=1)
            if now > start_time_delta:
                start_time_obj += timedelta(days=1)

            delay = (start_time_obj - now).total_seconds()
            threading.Timer(delay, job_wrapper).start()
            logger.debug(f"Scheduled task to start at {start_time_obj} and repeat every {interval} {interval_unit}")
        else:
            self._schedule_interval_task(task, interval_unit, interval)

    def _schedule_interval_task(self, task, interval_unit, interval):

        if interval_unit == 'seconds':
            job = self.scheduler.every(interval).seconds.do(lambda: asyncio.run(task()))
        elif interval_unit == 'minutes':
            job = self.scheduler.every(interval).minutes.do(lambda: asyncio.run(task()))
        elif interval_unit == 'hours':
            job = self.scheduler.every(interval).hours.do(lambda: asyncio.run(task()))
        elif interval_unit == 'days':
            job = self.scheduler.every(interval).days.do(lambda: asyncio.run(task()))
        elif interval_unit == 'weeks':
            job = self.scheduler.every(interval).weeks.do(lambda: asyncio.run(task()))
        else:
            raise ValueError(f"Unsupported interval unit: {interval_unit}")

        self.scheduled_jobs.append(job)
        logger.debug(f"Scheduled task to repeat every {interval} {interval_unit}")

    def schedule_fixed_task(self, task, run_time_str):
        run_time = datetime.strptime(run_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        # Calculate the delay until the run_time
        delay = (run_time - now).total_seconds()
        
        if delay <= 0:
            logger.debug("The specified run time is in the past.")
            return
        
        # Schedule the task to run after the delay
        threading.Timer(delay, lambda: asyncio.run(task())).start()
        logger.debug(f"Task scheduled to run at {run_time}")

    def schedule_one_shot(
        self,
        message: str,
        run_time_str: str,
        user_id: Optional[str] = None,
        channel_key: Optional[str] = None,
    ) -> bool:
        """Schedule a one-shot reminder at the given time (YYYY-MM-DD HH:MM:SS). Persisted to DB so it survives Core restart. user_id/channel_key used by deliver_to_user when reminder fires."""
        try:
            run_time = datetime.strptime(run_time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning("TAM: invalid run_time_str {}; scheduling in memory only", run_time_str)
            async def task():
                if hasattr(self.coreInst, "deliver_to_user"):
                    await self.coreInst.deliver_to_user(user_id or "companion", message, channel_key=channel_key, source="reminder")
                else:
                    await self.send_reminder_to_latest_channel(message)
            self.schedule_fixed_task(task, run_time_str)
            return True
        if run_time <= datetime.now():
            logger.debug("TAM: run_time is in the past; not scheduling")
            return False
        reminder_id = tam_storage.add_one_shot_reminder(run_time, message, user_id=user_id, channel_key=channel_key)
        if reminder_id:
            task = (
                lambda rid, msg, uid, ck: lambda: asyncio.run(self._run_one_shot_and_remove(rid, msg, user_id=uid, channel_key=ck))
            )(reminder_id, message, user_id, channel_key)
            self.schedule_fixed_task(task, run_time_str)
        else:
            async def fallback():
                await self.send_reminder_to_latest_channel(message)
            self.schedule_fixed_task(fallback, run_time_str)
        return True

    def random_time_within_range(self, min_interval, max_interval):
        return random.uniform(min_interval, max_interval)


    def schedule_random_task(self, task, interval_unit, min_interval, max_interval):
        if interval_unit == 'seconds':
            pass
        elif interval_unit == 'minutes':
            min_interval = min_interval * 60
            max_interval = max_interval * 60
        elif interval_unit == 'hours':
            min_interval = min_interval * 60 * 60
            max_interval = max_interval * 60 * 60
        elif interval_unit == 'days':
            min_interval = min_interval * 60 * 60 * 24
            max_interval = max_interval * 60 * 60 * 24
        elif interval_unit == 'weeks':
            min_interval = min_interval * 60 * 60 * 24 * 7
            max_interval = max_interval * 60 * 60 * 24 * 7

        def wrapped_task():
            asyncio.run(task())
            next_run_in_seconds = self.random_time_within_range(min_interval, max_interval)
            next_run_time = datetime.now() + timedelta(seconds=next_run_in_seconds)
            job = self.scheduler.every().day.at(next_run_time.strftime("%H:%M:%S")).do(wrapped_task)
            self.scheduled_jobs.append(job)

        # Schedule the initial task
        next_run_in_seconds = self.random_time_within_range(min_interval, max_interval)
        next_run_time = datetime.now() + timedelta(seconds=next_run_in_seconds)
        job = self.scheduler.every().day.at(next_run_time.strftime("%H:%M:%S")).do(wrapped_task)
        self.scheduled_jobs.append(job)

    def _cron_now(self, tz: Optional[str] = None) -> datetime:
        """Current time for cron: timezone-aware if tz given (e.g. 'America/New_York'), else naive local. Never raises."""
        if tz and ZoneInfo:
            try:
                return datetime.now(ZoneInfo(tz))
            except Exception as e:
                logger.debug("TAM: Invalid cron tz {}, using local: {}", tz, e)
        return datetime.now()

    def _cron_prev_run(self, cron_expr: str, before_dt: datetime, tz: Optional[str] = None, max_iter: int = 1000) -> Optional[datetime]:
        """Last run time for cron_expr that is < before_dt (for restart catch-up). Returns None if none or error. Never raises."""
        if not CRONITER_AVAILABLE:
            return None
        try:
            start = before_dt - timedelta(days=8)
            it = croniter(cron_expr, start)
            prev = None
            for _ in range(max_iter):
                n = it.get_next(datetime)
                if n >= before_dt:
                    return prev
                prev = n
            return prev
        except Exception as e:
            logger.debug("TAM: _cron_prev_run failed for {}: {}", cron_expr, e)
            return None

    def _cron_next_run(self, cron_expr: str, from_dt: datetime, tz: Optional[str] = None) -> datetime:
        """Next run time for cron_expr after from_dt. Uses tz for timezone-aware scheduling if ZoneInfo available."""
        if not CRONITER_AVAILABLE:
            return from_dt + timedelta(minutes=1)
        try:
            it = croniter(cron_expr, from_dt)
            return it.get_next(datetime)
        except Exception:
            return from_dt + timedelta(minutes=1)

    def schedule_cron_task(
        self,
        task,
        cron_expr: str,
        job_id: Optional[str] = None,
        params: Optional[Dict] = None,
        skip_persist: bool = False,
    ) -> Optional[str]:
        """Schedule a task to run on cron expression (e.g. '0 9 * * *' = daily at 9:00).
        params may include: message, tz (e.g. 'America/New_York'), enabled (bool), channel_key (for per-session delivery).
        Persisted to DB unless skip_persist=True (e.g. when loading from DB).
        Returns job_id if scheduled, None if croniter unavailable or invalid expression. Never raises."""
        try:
            if not CRONITER_AVAILABLE:
                logger.warning("TAM: croniter not installed; cron scheduling disabled")
                return None
            params = params or {}
            now = self._cron_now(params.get("tz"))
            try:
                next_run = self._cron_next_run(cron_expr, now, params.get("tz"))
            except Exception as e:
                logger.error("TAM: Invalid cron expression '{}': {}", cron_expr, e)
                return None
            jid = job_id or f"cron_{id(task)}_{datetime.now().timestamp()}"
            with self._cron_lock:
                self.cron_jobs.append({
                    "job_id": jid,
                    "cron_expr": cron_expr,
                    "task": task,
                    "next_run": next_run,
                    "params": params,
                })
            if not skip_persist:
                try:
                    tam_storage.save_cron_job(jid, cron_expr, params)
                except Exception as e:
                    logger.debug("TAM: Could not persist cron job to DB: {}", e)
            logger.debug("TAM: Scheduled cron job {} '{}' next at {}", jid, cron_expr, next_run)
            return jid
        except Exception as e:
            logger.warning("TAM: schedule_cron_task failed: {}", e)
            return None

    def update_cron_job(
        self,
        job_id: str,
        enabled: Optional[bool] = None,
        cron_expr: Optional[str] = None,
        params_update: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a cron job: enabled, cron_expr, or merge params_update into params. Persists to DB. Returns True if job found and updated. Never raises."""
        try:
            with self._cron_lock:
                job = next((j for j in self.cron_jobs if j.get("job_id") == job_id), None)
                if not job:
                    return False
                params = dict(job.get("params") or {})
                if enabled is not None:
                    params["enabled"] = enabled
                if params_update:
                    params.update(params_update)
                if cron_expr is not None:
                    job["cron_expr"] = cron_expr
                    tz = params.get("tz")
                    now = self._cron_now(tz)
                    try:
                        job["next_run"] = self._cron_next_run(cron_expr, now, tz)
                    except Exception:
                        job["next_run"] = now + timedelta(minutes=1)
                job["params"] = params
            try:
                pupdate = dict(params_update) if params_update else {}
                if enabled is not None:
                    pupdate["enabled"] = enabled
                return tam_storage.update_cron_job(job_id, cron_expr=cron_expr, params_update=pupdate if pupdate else params)
            except Exception as e:
                logger.debug("TAM: update_cron_job persist failed: {}", e)
                return True  # in-memory updated
        except Exception as e:
            logger.warning("TAM: update_cron_job failed: {}", e)
            return False

    def run_cron_job_now(self, job_id: str) -> bool:
        """Run a cron job once immediately (like OpenClaw cron.run force). Advances next_run so it does not fire again in the same tick. Records run state. Returns True if job found and run. Never raises."""
        try:
            with self._cron_lock:
                job = next((j for j in self.cron_jobs if j.get("job_id") == job_id), None)
                if not job:
                    return False
                task = job.get("task")
                tz = (job.get("params") or {}).get("tz")
                now = self._cron_now(tz)
                try:
                    job["next_run"] = self._cron_next_run(job.get("cron_expr", "0 * * * *"), now, tz)
                except Exception:
                    job["next_run"] = now + timedelta(minutes=1)
            self._run_one_cron_job(job)
            return True
        except Exception as e:
            logger.warning("TAM: run_cron_job_now {} failed: {}", job_id, e)
            return False

    def get_cron_status(self) -> Dict[str, Any]:
        """Scheduler status for UI: scheduler_enabled, next_wake_at (min of next_run), jobs_count. Never raises."""
        try:
            if not self.cron_jobs:
                return {"scheduler_enabled": True, "next_wake_at": None, "jobs_count": 0}
            with self._cron_lock:
                next_wake = None
                for j in self.cron_jobs:
                    try:
                        if not (j.get("params") or {}).get("enabled", True):
                            continue
                        nr = j.get("next_run")
                        if nr is not None and (next_wake is None or nr < next_wake):
                            next_wake = nr
                    except Exception:
                        continue
            nw = None
            if next_wake is not None:
                try:
                    nw = next_wake.isoformat() if hasattr(next_wake, "isoformat") else str(next_wake)
                except Exception:
                    nw = str(next_wake)
            return {
                "scheduler_enabled": True,
                "next_wake_at": nw,
                "jobs_count": len(self.cron_jobs),
            }
        except Exception as e:
            logger.debug("TAM: get_cron_status failed: {}", e)
            return {"scheduler_enabled": True, "next_wake_at": None, "jobs_count": 0}

    def remove_cron_job(self, job_id: str) -> bool:
        """Remove a cron job by job_id (memory and DB). Returns True if removed, False if not found. Never raises."""
        try:
            with self._cron_lock:
                before = len(self.cron_jobs)
                self.cron_jobs = [j for j in self.cron_jobs if j.get("job_id") != job_id]
                removed = len(self.cron_jobs) < before
            if removed:
                try:
                    tam_storage.remove_cron_job(job_id)
                except Exception as e:
                    logger.debug("TAM: Could not remove cron job from DB: {}", e)
                logger.debug("TAM: Removed cron job {}", job_id)
            return removed
        except Exception as e:
            logger.warning("TAM: remove_cron_job failed: {}", e)
            return False

    def _get_recorded_events_dir(self) -> Path:
        """Directory for per-user recorded event files: database/tam_recorded_events/. Never raises."""
        if self._recorded_events_dir is not None:
            return self._recorded_events_dir
        try:
            root = Path(__file__).resolve().parent.parent
            self._recorded_events_dir = root / "database" / "tam_recorded_events"
            return self._recorded_events_dir
        except Exception as e:
            logger.warning("TAM: _get_recorded_events_dir fallback: {}", e)
            self._recorded_events_dir = Path.cwd() / "database" / "tam_recorded_events"
            return self._recorded_events_dir

    def _get_recorded_events_path(self, system_user_id: Optional[str]) -> Path:
        """Path to this user's recorded events JSON file."""
        safe = _safe_user_id_for_recorded_events(system_user_id)
        return self._get_recorded_events_dir() / f"{safe}.json"

    def _load_recorded_events_for_user(self, system_user_id: Optional[str]) -> List[Dict]:
        """Load recorded events for one user. Returns list (possibly empty). Never raises."""
        try:
            path = self._get_recorded_events_path(system_user_id)
            if not path.exists():
                return []
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.debug("TAM: Could not load recorded_events for user {}: {}", system_user_id, e)
            return []

    def _save_recorded_events_for_user(self, system_user_id: Optional[str], events: List[Dict]) -> None:
        """Save recorded events for one user. Never raises."""
        try:
            events = events if isinstance(events, list) else []
            path = self._get_recorded_events_path(system_user_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(events, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("TAM: Could not save recorded_events for user {}: {}", system_user_id, e)

    @staticmethod
    def _cleanup_past_recorded_events(events: List[Dict], max_age_days_no_date: int = 90) -> tuple:
        """Remove events that are finished. Returns (kept_list, number_removed). Never raises."""
        events = events if isinstance(events, list) else []
        today = datetime.now().date()
        before = len(events)
        kept: List[Dict] = []
        for entry in events:
            if not isinstance(entry, dict):
                kept.append(entry)
                continue
            event_date_str = (entry.get("event_date") or "").strip()
            if event_date_str:
                try:
                    event_date = datetime.strptime(event_date_str[:10], "%Y-%m-%d").date()
                    if event_date < today:
                        continue  # drop past event
                except ValueError:
                    pass  # keep if unparseable
                kept.append(entry)
                continue
            # No event_date: drop if recorded_at is very old
            recorded_at = (entry.get("recorded_at") or "").strip()
            if recorded_at:
                try:
                    rec_date = datetime.strptime(recorded_at[:10], "%Y-%m-%d").date()
                    if (today - rec_date).days > max_age_days_no_date:
                        continue
                except ValueError:
                    pass
            kept.append(entry)
        return (kept, before - len(kept))

    _RECURRING_CANCEL_HINT = "\n(To cancel this recurring reminder, say 'list my recurring reminders' and ask to remove it.)"

    def _run_missed_cron_jobs_after_load(self, loaded_jobs: List[Dict[str, Any]]) -> None:
        """After loading cron jobs from DB, run once any job that would have been due while Core was down (restart catch-up). At most one run per job. Never raises."""
        if not loaded_jobs:
            return
        now = datetime.now()
        for job in loaded_jobs:
            try:
                if not (job.get("params") or {}).get("enabled", True):
                    continue
                params = job.get("params") or {}
                tz = params.get("tz")
                last_run_at = None
                lra = params.get("last_run_at")
                if lra:
                    try:
                        if isinstance(lra, str):
                            last_run_at = datetime.fromisoformat(lra.replace("Z", "+00:00"))
                        elif hasattr(lra, "year"):
                            last_run_at = lra
                    except Exception:
                        pass
                cron_expr = job.get("cron_expr") or "0 * * * *"
                prev_run = self._cron_prev_run(cron_expr, now, tz)
                if prev_run is None:
                    continue
                if last_run_at is not None and prev_run <= last_run_at:
                    continue
                logger.info("TAM: Catch-up run for cron job {} (missed while Core was down)", job.get("job_id"))
                self._run_one_cron_job(job)
                # Advance next_run so it does not fire again in the next scheduler tick
                with self._cron_lock:
                    try:
                        now2 = self._cron_now(tz)
                        job["next_run"] = self._cron_next_run(cron_expr, now2, tz)
                    except Exception:
                        job["next_run"] = self._cron_now(tz) + timedelta(minutes=1)
            except Exception as e:
                logger.warning("TAM: Catch-up for job {} failed: {}", job.get("job_id"), e)

    def _load_cron_jobs_from_db(self) -> None:
        """Load persisted cron jobs and re-schedule them (survives Core restart). Runs missed jobs once on restart (catch-up). Uses params (message, tz, enabled, channel_key) for delivery."""
        try:
            rows = tam_storage.load_cron_jobs()
        except Exception as e:
            logger.warning("TAM: Could not load cron jobs from DB: {}", e)
            return
        loaded_jobs: List[Dict[str, Any]] = []
        for row in rows:
            try:
                job_id = row.get("job_id")
                cron_expr = row.get("cron_expr")
                if not job_id or not cron_expr:
                    continue
                params = dict(row.get("params") or {})
                if params.get("task_type") == "run_skill":
                    skill_name = params.get("skill_name") or ""
                    script = params.get("script") or ""
                    args_list = params.get("args") or []
                    if skill_name and script:
                        def make_run_skill_task(prms: Dict[str, Any]):
                            async def _run():
                                from base.tools import get_tool_registry, ToolContext
                                registry = get_tool_registry()
                                if not registry:
                                    await self._send_reminder_to_channel_safe("Error: tool registry not available", prms)
                                    return
                                ctx = ToolContext(core=self.coreInst)
                                try:
                                    result = await registry.execute_async(
                                        "run_skill",
                                        {"skill_name": prms["skill_name"], "script": prms["script"], "args": prms.get("args") or []},
                                        ctx,
                                    )
                                except Exception as e:
                                    result = f"Error: {e}"
                                text = (result or "(no output)").strip()
                                prompt = (prms.get("post_process_prompt") or "").strip()
                                if prompt and hasattr(self.coreInst, "openai_chat_completion"):
                                    try:
                                        refined = await self.coreInst.openai_chat_completion([
                                            {"role": "system", "content": prompt},
                                            {"role": "user", "content": text},
                                        ])
                                        if refined and isinstance(refined, str) and refined.strip():
                                            text = refined.strip()
                                    except Exception:
                                        pass
                                await self._send_reminder_to_channel_safe(text, prms)
                            return lambda: asyncio.run(_run())
                        task = make_run_skill_task(params)
                    else:
                        task = (
                            lambda m, p: lambda: asyncio.run(
                                self._send_reminder_to_channel_safe(m + self._RECURRING_CANCEL_HINT, p)
                            )
                        )(params.get("message", ""), params)
                elif params.get("task_type") == "run_plugin":
                    plugin_id = params.get("plugin_id") or ""
                    if plugin_id:
                        def make_run_plugin_task(prms: Dict[str, Any]):
                            async def _run():
                                from base.tools import get_tool_registry, ToolContext
                                from base.base import PromptRequest, ChannelType, ContentType
                                import uuid as _uuid
                                import time as _time
                                registry = get_tool_registry()
                                if not registry:
                                    await self._send_reminder_to_channel_safe("Error: tool registry not available", prms)
                                    return
                                channel_key = prms.get("channel_key") or ""
                                parts = channel_key.split(":") if channel_key else ["", ""]
                                app_id = parts[0] if len(parts) > 0 else ""
                                user_id = parts[1] if len(parts) > 1 else ""
                                if channel_key == "companion":
                                    app_id = app_id or "homeclaw"
                                    user_id = "companion"
                                req = PromptRequest(
                                    request_id=str(_uuid.uuid4()),
                                    channel_name="cron",
                                    request_metadata={"capability_id": prms.get("capability_id"), "capability_parameters": prms.get("parameters") or {}},
                                    channelType=ChannelType.IM,
                                    user_name="cron",
                                    app_id=app_id,
                                    user_id=user_id,
                                    contentType=ContentType.TEXT,
                                    text="",
                                    action="respond",
                                    host="cron",
                                    port=0,
                                    images=[],
                                    videos=[],
                                    audios=[],
                                    files=[],
                                    timestamp=_time.time(),
                                )
                                ctx = ToolContext(core=self.coreInst, request=req, cron_scheduled=True)
                                try:
                                    result = await registry.execute_async(
                                        "route_to_plugin",
                                        {
                                            "plugin_id": prms["plugin_id"],
                                            "capability_id": prms.get("capability_id"),
                                            "parameters": prms.get("parameters") or {},
                                        },
                                        ctx,
                                    )
                                except Exception as e:
                                    result = f"Error: {e}"
                                text = (result or "(no output)").strip()
                                if not isinstance(text, str):
                                    text = str(text)
                                prompt = (prms.get("post_process_prompt") or "").strip()
                                if prompt and hasattr(self.coreInst, "openai_chat_completion"):
                                    try:
                                        refined = await self.coreInst.openai_chat_completion([
                                            {"role": "system", "content": prompt},
                                            {"role": "user", "content": text},
                                        ])
                                        if refined and isinstance(refined, str) and refined.strip():
                                            text = refined.strip()
                                    except Exception:
                                        pass
                                await self._send_reminder_to_channel_safe(text, prms)
                            return lambda: asyncio.run(_run())
                        task = make_run_plugin_task(params)
                    else:
                        task = (
                            lambda m, p: lambda: asyncio.run(
                                self._send_reminder_to_channel_safe(m + self._RECURRING_CANCEL_HINT, p)
                            )
                        )(params.get("message", ""), params)
                elif params.get("task_type") == "run_tool":
                    tool_name = params.get("tool_name") or ""
                    if tool_name:
                        def make_run_tool_task(prms: Dict[str, Any]):
                            async def _run():
                                from base.tools import get_tool_registry, ToolContext
                                registry = get_tool_registry()
                                if not registry:
                                    await self._send_reminder_to_channel_safe("Error: tool registry not available", prms)
                                    return
                                ctx = ToolContext(core=self.coreInst, cron_scheduled=True)
                                try:
                                    result = await registry.execute_async(
                                        prms["tool_name"],
                                        prms.get("tool_arguments") or {},
                                        ctx,
                                    )
                                except Exception as e:
                                    result = f"Error: {e}"
                                text = (result or "(no output)").strip()
                                if not isinstance(text, str):
                                    text = str(text)
                                prompt = (prms.get("post_process_prompt") or "").strip()
                                if prompt and hasattr(self.coreInst, "openai_chat_completion"):
                                    try:
                                        refined = await self.coreInst.openai_chat_completion([
                                            {"role": "system", "content": prompt},
                                            {"role": "user", "content": text},
                                        ])
                                        if refined and isinstance(refined, str) and refined.strip():
                                            text = refined.strip()
                                    except Exception:
                                        pass
                                await self._send_reminder_to_channel_safe(text, prms)
                            return lambda: asyncio.run(_run())
                        task = make_run_tool_task(params)
                    else:
                        task = (
                            lambda m, p: lambda: asyncio.run(
                                self._send_reminder_to_channel_safe(m + self._RECURRING_CANCEL_HINT, p)
                            )
                        )(params.get("message", ""), params)
                else:
                    msg = params.get("message", "")
                    task = (
                        lambda m, p: lambda: asyncio.run(
                            self._send_reminder_to_channel_safe(m + self._RECURRING_CANCEL_HINT, p)
                        )
                    )(msg, params)
                jid = self.schedule_cron_task(
                    task,
                    cron_expr,
                    job_id=job_id,
                    params=params,
                    skip_persist=True,
                )
                if jid:
                    with self._cron_lock:
                        job = next((j for j in self.cron_jobs if j.get("job_id") == jid), None)
                        if job:
                            loaded_jobs.append(job)
            except Exception as e:
                logger.warning("TAM: Skip loading cron job {}: {}", row.get("job_id"), e)
        if rows:
            logger.debug("TAM: Loaded {} cron job(s) from DB", len(rows))
        # Restart catch-up: run any job that would have been due while Core was down (at most one run per job)
        try:
            self._run_missed_cron_jobs_after_load(loaded_jobs)
        except Exception as e:
            logger.warning("TAM: Catch-up after load failed: {}", e)

    def _load_one_shot_reminders_from_db(self) -> None:
        """Load persisted one-shot reminders with run_at > now and re-schedule them (survives Core restart). Expired ones are deleted from DB."""
        try:
            deleted = tam_storage.cleanup_expired_one_shot_reminders()
            if deleted:
                logger.debug("TAM: Cleaned {} expired one-shot reminder(s) from DB", deleted)
            rows = tam_storage.load_one_shot_reminders(after=datetime.now())
            for row in rows:
                run_at = row.get("run_at")
                if run_at is None:
                    continue
                run_time_str = run_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(run_at, "strftime") else str(run_at)
                rid = row.get("id", "")
                msg = row.get("message", "")
                uid = row.get("user_id")
                ck = row.get("channel_key")
                task = (
                    lambda reminder_id, message, u, c: lambda: asyncio.run(
                        self._run_one_shot_and_remove(reminder_id, message, user_id=u, channel_key=c)
                    )
                )(rid, msg, uid, ck)
                self.schedule_fixed_task(task, run_time_str)
            if rows:
                logger.debug("TAM: Loaded {} one-shot reminder(s) from DB", len(rows))
        except Exception as e:
            logger.debug("TAM: Could not load one-shot reminders from DB: {}", e)

    async def _run_one_shot_and_remove(
        self,
        reminder_id: str,
        message: str,
        user_id: Optional[str] = None,
        channel_key: Optional[str] = None,
    ) -> None:
        """Deliver reminder to user (Companion push + channel) and remove from DB (called when one-shot fires). Never raises (logs and continues)."""
        try:
            if hasattr(self.coreInst, "deliver_to_user"):
                await self.coreInst.deliver_to_user(
                    user_id or "companion",
                    message or "Reminder",
                    channel_key=channel_key,
                    source="reminder",
                )
            else:
                await self.send_reminder_to_channel(message or "Reminder", {"channel_key": channel_key} if channel_key else None)
        except Exception as e:
            logger.exception("TAM: _run_one_shot_and_remove deliver failed: {}", e)
        try:
            tam_storage.delete_one_shot_reminder(reminder_id or "")
        except Exception as e:
            logger.debug("TAM: delete_one_shot_reminder failed: {}", e)

    def record_event(
        self,
        event_name: str,
        when: str,
        note: str = "",
        event_date: Optional[str] = None,
        remind_on: Optional[str] = None,
        remind_message: Optional[str] = None,
        system_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a date/event for future reference (no LLM; from record_date tool). Per-user. Never raises."""
        try:
            entry = {
                "event_name": (event_name or "").strip() or "event",
                "when": (when or "").strip() or "",
                "note": (note or "").strip() or "",
                "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event_date": (event_date or "").strip() if event_date else "",
                "remind_on": (remind_on or "").strip().lower() or "",
                "remind_message": (remind_message or "").strip() or "",
            }
            events = self._load_recorded_events_for_user(system_user_id)
            if not isinstance(events, list):
                events = []
            events.append(entry)
            self._save_recorded_events_for_user(system_user_id, events)
            logger.debug("TAM: Recorded event {} when={} (user={})", entry["event_name"], entry["when"], system_user_id or "_default")

            result: Dict[str, Any] = {"recorded": True, "event_name": entry["event_name"], "when": entry["when"]}
            reminders_scheduled: List[str] = []

            if entry["event_date"] and entry["remind_on"]:
                try:
                    ev_date = datetime.strptime(entry["event_date"], "%Y-%m-%d")
                except ValueError:
                    logger.warning("TAM: Invalid event_date {}; skipping reminder", entry["event_date"])
                else:
                    msg = entry["remind_message"] or f"Reminder: {entry['event_name']} is today!"
                    uid = system_user_id or "companion"
                    if entry["remind_on"] == "day_before":
                        run_date = ev_date - timedelta(days=1)
                        run_time_str = run_date.strftime("%Y-%m-%d 09:00:00")
                        day_before_msg = entry["remind_message"] or f"Reminder: {entry['event_name']} is tomorrow!"
                        self.schedule_one_shot(day_before_msg, run_time_str, user_id=uid)
                        reminders_scheduled.append(f"day before ({run_time_str})")
                    elif entry["remind_on"] == "on_day":
                        run_time_str = ev_date.strftime("%Y-%m-%d 09:00:00")
                        self.schedule_one_shot(msg, run_time_str, user_id=uid)
                        reminders_scheduled.append(f"on day ({run_time_str})")
                    if reminders_scheduled:
                        result["reminders_scheduled"] = reminders_scheduled
            return result
        except Exception as e:
            logger.warning("TAM: record_event failed: {}", e)
            return {"recorded": False, "error": str(e), "event_name": (event_name or "").strip() or "event", "when": (when or "").strip() or ""}

    def list_recorded_events(self, system_user_id: Optional[str] = None) -> List[Dict]:
        """Return recorded events for this user (for 'what is coming up?' etc.). Past events are removed before returning. Never raises."""
        try:
            events = self._load_recorded_events_for_user(system_user_id)
            kept, removed = self._cleanup_past_recorded_events(events)
            if removed > 0:
                self._save_recorded_events_for_user(system_user_id, kept)
                logger.debug("TAM: Removed {} past recorded event(s) on list (user={})", removed, system_user_id or "_default")
            return kept
        except Exception as e:
            logger.warning("TAM: list_recorded_events failed: {}", e)
            return []

    def clear_recorded_events(self) -> bool:
        """Clear all users' recorded events (from record_date). Used when user does memory reset. Returns True if cleared."""
        try:
            dir_path = self._get_recorded_events_dir()
            if not dir_path.exists():
                return True
            cleared = 0
            for path in dir_path.glob("*.json"):
                if path.is_file():
                    try:
                        path.write_text("[]", encoding="utf-8")
                        cleared += 1
                    except Exception as e:
                        logger.warning("TAM: Could not clear recorded_events file {}: {}", path, e)
            if cleared > 0:
                logger.debug("TAM: recorded_events cleared ({} user file(s))", cleared)
            return True
        except Exception as e:
            logger.warning("TAM: clear_recorded_events failed: {}", e)
            return False

    def get_recorded_events_summary(self, limit: int = 10, system_user_id: Optional[str] = None) -> str:
        """Short text summary of this user's recorded events for injection into system context. Never raises."""
        try:
            events = self.list_recorded_events(system_user_id=system_user_id)
            if not events or not isinstance(events, list):
                return ""
            limit = max(0, int(limit) if isinstance(limit, (int, float)) else 10)
            lines = []
            for e in events[-limit:]:
                if not isinstance(e, dict):
                    continue
                name = e.get("event_name") or "event"
                when = e.get("when") or ""
                ed = e.get("event_date") or ""
                ro = e.get("remind_on") or ""
                part = f"- {name}: {when}"
                if ed:
                    part += f" (date: {ed}"
                    if ro:
                        part += f", remind: {ro}"
                    part += ")"
                lines.append(part)
            return "Recorded events: " + "; ".join(lines) if lines else ""
        except Exception as e:
            logger.debug("TAM: get_recorded_events_summary failed: {}", e)
            return ""

    def _run_cron_pending(self) -> None:
        """Run any cron jobs that are due; advance next_run; record run history. Never raises (logs and continues)."""
        try:
            if not CRONITER_AVAILABLE or not self.cron_jobs:
                return
            to_run = []
            with self._cron_lock:
                for job in self.cron_jobs:
                    try:
                        if not (job.get("params") or {}).get("enabled", True):
                            continue
                        tz = (job.get("params") or {}).get("tz")
                        now = self._cron_now(tz)
                        nr = job.get("next_run")
                        if nr is None:
                            to_run.append(job)
                        else:
                            try:
                                if nr <= now:
                                    to_run.append(job)
                            except (TypeError, ValueError):
                                to_run.append(job)
                    except Exception as e:
                        logger.debug("TAM: Skip job {} in pending check: {}", job.get("job_id"), e)
                for job in to_run:
                    try:
                        tz = (job.get("params") or {}).get("tz")
                        now = self._cron_now(tz)
                        job["next_run"] = self._cron_next_run(job.get("cron_expr", "0 * * * *"), now, tz)
                    except Exception:
                        job["next_run"] = self._cron_now(tz) + timedelta(minutes=1)
            for job in to_run:
                self._run_one_cron_job(job)
        except Exception as e:
            logger.exception("TAM: _run_cron_pending failed (scheduler continues): %s", e)

    def _run_one_cron_job(self, job: Dict[str, Any]) -> None:
        """Run a single cron job and persist run state. Never raises."""
        jid = job.get("job_id") or "unknown"
        task = job.get("task")
        started_at = time.perf_counter()
        try:
            if task:
                asyncio.run(task())
            status, err = "ok", None
        except Exception as e:
            logger.exception("TAM: Cron job {} failed: {}", jid, e)
            status, err = "error", str(e)[:500]
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            tam_storage.update_cron_job_state(
                jid,
                last_run_at=datetime.now(),
                last_status=status,
                last_error=err,
                last_duration_ms=duration_ms,
            )
        except Exception as ex:
            logger.debug("TAM: Could not persist cron run state: {}", ex)
        params = job.get("params") or {}
        params["last_run_at"] = datetime.now().isoformat()
        params["last_status"] = status
        params["last_error"] = err
        params["last_duration_ms"] = duration_ms
        job["params"] = params

    def run_scheduler(self) -> None:
        """Main scheduler loop. Never exits; all exceptions are caught so Core does not crash."""
        while True:
            try:
                self.scheduler.run_pending()
            except Exception as e:
                logger.exception("TAM: scheduler.run_pending failed: {}", e)
            try:
                self._run_cron_pending()
            except Exception as e:
                logger.exception("TAM: _run_cron_pending failed: {}", e)
            try:
                time.sleep(10)
            except Exception as e:
                logger.debug("TAM: sleep interrupted: {}", e)
                time.sleep(10)

    def run(self):
        self.thread = threading.Thread(target=self.run_scheduler)
        self.thread.daemon = True
        self.thread.start()

    def cleanup(self):
        for job in self.scheduled_jobs:
            self.scheduler.cancel_job(job=job)
        self.scheduler.clear()
        with self._cron_lock:
            self.cron_jobs.clear()
        # Short timeout so Ctrl+C doesn't block (scheduler loop sleeps 10s)
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logger.debug("TAM scheduler cleanup done.")  


    
    