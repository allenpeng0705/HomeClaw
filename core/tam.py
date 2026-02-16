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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from base.base import IntentType, Intent, PromptRequest
from base.prompt_manager import get_prompt_manager
from base.util import Util
from core.coreInterface import CoreInterface
from memory import tam_storage

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
        # Recorded events (no LLM): from record_date tool; e.g. "Spring Festival is in two weeks"
        self.recorded_events: List[Dict] = []
        self._recorded_events_path: Optional[Path] = None
        self._load_recorded_events()

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

    async def process_intent(self, intent: Intent, request: PromptRequest):
        if intent is None:
            return
        try:
            logger.debug(f"TAM process_intent: {intent}")
            # Analyze the intent using LLM and create a data object
            data_object = await self.analyze_intent_with_llm(intent)
            logger.debug(f"TAM got data_object: {data_object}")
            if data_object is None or not isinstance(data_object, dict):
                logger.warning("TAM: No valid scheduling data from LLM; cannot schedule.")
                await self.coreInst.send_response_to_request_channel(
                    response="I couldn't parse that as a reminder. Try something like: \"Remind me in 5 minutes\" or \"Remind me at 3pm\" with a clear time and what to remind you about.",
                    request=request,
                )
                return
            # Use the data object to schedule a job
            self.schedule_job_from_intent(data_object, request)
        except Exception as e:
            logger.exception(f"TAM: Error processing intent: {e}")
            try:
                await self.coreInst.send_response_to_request_channel(
                    response="Something went wrong setting the reminder. Please try again with a clear time (e.g. \"remind me in 5 minutes\").",
                    request=request,
                )
            except Exception:
                pass


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
            logger.error('TAM: Failed to decode LLM response JSON: %s', e)
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
                lang = getattr(meta, "main_llm_language", "en") or "en"
                content = pm.get_content(
                    "tam", "scheduling", lang=lang,
                    current_datetime=current_datetime, chat_history=chat_history or "", text=text,
                )
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.debug("TAM prompt manager fallback: %s", e)
        return self._create_prompt_fallback(text, chat_history)    

    def schedule_job_from_intent(self, data_object: Dict, request: PromptRequest):
        if data_object is None or not isinstance(data_object, dict):
            logger.warning("TAM: schedule_job_from_intent called with invalid data_object; skipping.")
            return
        logger.debug(f"Scheduling job with data: {data_object}")
        job_type = data_object.get('type')
        params: Dict = data_object.get('params', {})

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

    def schedule_one_shot(self, message: str, run_time_str: str) -> bool:
        """Schedule a one-shot reminder at the given time (YYYY-MM-DD HH:MM:SS). Persisted to DB so it survives Core restart."""
        try:
            run_time = datetime.strptime(run_time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning("TAM: invalid run_time_str %s; scheduling in memory only", run_time_str)
            async def task():
                await self.send_reminder_to_latest_channel(message)
            self.schedule_fixed_task(task, run_time_str)
            return True
        if run_time <= datetime.now():
            logger.debug("TAM: run_time is in the past; not scheduling")
            return False
        reminder_id = tam_storage.add_one_shot_reminder(run_time, message)
        if reminder_id:
            task = (lambda rid, msg: lambda: asyncio.run(self._run_one_shot_and_remove(rid, msg)))(reminder_id, message)
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

    def schedule_cron_task(
        self,
        task,
        cron_expr: str,
        job_id: Optional[str] = None,
        params: Optional[Dict] = None,
        skip_persist: bool = False,
    ) -> Optional[str]:
        """Schedule a task to run on cron expression (e.g. '0 9 * * *' = daily at 9:00).
        Persisted to DB unless skip_persist=True (e.g. when loading from DB).
        Returns job_id if scheduled, None if croniter unavailable or invalid expression."""
        if not CRONITER_AVAILABLE:
            logger.warning("TAM: croniter not installed; cron scheduling disabled")
            return None
        try:
            it = croniter(cron_expr, datetime.now())
            next_run = it.get_next(datetime)
        except Exception as e:
            logger.error(f"TAM: Invalid cron expression '{cron_expr}': {e}")
            return None
        jid = job_id or f"cron_{id(task)}_{datetime.now().timestamp()}"
        with self._cron_lock:
            self.cron_jobs.append({
                "job_id": jid,
                "cron_expr": cron_expr,
                "task": task,
                "next_run": next_run,
                "params": params or {},
            })
        if not skip_persist:
            try:
                tam_storage.save_cron_job(jid, cron_expr, params or {})
            except Exception as e:
                logger.debug("TAM: Could not persist cron job to DB: %s", e)
        logger.debug(f"TAM: Scheduled cron job {jid} '{cron_expr}' next at {next_run}")
        return jid

    def remove_cron_job(self, job_id: str) -> bool:
        """Remove a cron job by job_id (memory and DB). Returns True if removed, False if not found."""
        with self._cron_lock:
            before = len(self.cron_jobs)
            self.cron_jobs = [j for j in self.cron_jobs if j.get("job_id") != job_id]
            removed = len(self.cron_jobs) < before
        if removed:
            try:
                tam_storage.remove_cron_job(job_id)
            except Exception as e:
                logger.debug("TAM: Could not remove cron job from DB: %s", e)
            logger.debug(f"TAM: Removed cron job {job_id}")
        return removed

    def _load_recorded_events(self) -> None:
        """Load recorded events from file (no LLM; from record_date tool). Removes past events on load so the list does not grow indefinitely."""
        try:
            root = Path(__file__).resolve().parent.parent
            self._recorded_events_path = root / "database" / "tam_recorded_events.json"
            if self._recorded_events_path.exists():
                raw = self._recorded_events_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self.recorded_events = data if isinstance(data, list) else []
            else:
                self.recorded_events = []
            removed = self._cleanup_past_recorded_events()
            if removed > 0:
                self._save_recorded_events()
                logger.debug("TAM: Removed %d past recorded event(s) on load", removed)
        except Exception as e:
            logger.debug("TAM: Could not load recorded_events: %s", e)
            self.recorded_events = []

    def _cleanup_past_recorded_events(self, max_age_days_no_date: int = 90) -> int:
        """Remove events that are finished: (1) event_date in the past, (2) no event_date but recorded_at older than max_age_days_no_date. Returns number removed."""
        today = datetime.now().date()
        before = len(self.recorded_events)
        kept: List[Dict] = []
        for entry in self.recorded_events:
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
                    # "YYYY-MM-DD HH:MM:SS"
                    rec_date = datetime.strptime(recorded_at[:10], "%Y-%m-%d").date()
                    if (today - rec_date).days > max_age_days_no_date:
                        continue  # drop old undated event
                except ValueError:
                    pass
            kept.append(entry)
        self.recorded_events = kept
        return before - len(kept)

    def _save_recorded_events(self) -> None:
        try:
            if self._recorded_events_path is None:
                root = Path(__file__).resolve().parent.parent
                self._recorded_events_path = root / "database" / "tam_recorded_events.json"
            self._recorded_events_path.parent.mkdir(parents=True, exist_ok=True)
            self._recorded_events_path.write_text(
                json.dumps(self.recorded_events, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("TAM: Could not save recorded_events: %s", e)

    _RECURRING_CANCEL_HINT = "\n(To cancel this recurring reminder, say 'list my recurring reminders' and ask to remove it.)"

    def _load_cron_jobs_from_db(self) -> None:
        """Load persisted cron jobs and re-schedule them (survives Core restart)."""
        try:
            rows = tam_storage.load_cron_jobs()
            for row in rows:
                msg = (row.get("params") or {}).get("message", "")
                # Append cancel hint so user knows they can list and remove (same as newly scheduled cron)
                task = (lambda m: lambda: asyncio.run(self.send_reminder_to_latest_channel(m + self._RECURRING_CANCEL_HINT)))(msg)
                self.schedule_cron_task(
                    task,
                    row["cron_expr"],
                    job_id=row["job_id"],
                    params=row.get("params") or {},
                    skip_persist=True,
                )
            if rows:
                logger.debug("TAM: Loaded %d cron job(s) from DB", len(rows))
        except Exception as e:
            logger.debug("TAM: Could not load cron jobs from DB: %s", e)

    def _load_one_shot_reminders_from_db(self) -> None:
        """Load persisted one-shot reminders with run_at > now and re-schedule them (survives Core restart). Expired ones are deleted from DB."""
        try:
            deleted = tam_storage.cleanup_expired_one_shot_reminders()
            if deleted:
                logger.debug("TAM: Cleaned %d expired one-shot reminder(s) from DB", deleted)
            rows = tam_storage.load_one_shot_reminders(after=datetime.now())
            for row in rows:
                run_at = row.get("run_at")
                if run_at is None:
                    continue
                run_time_str = run_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(run_at, "strftime") else str(run_at)
                rid = row.get("id", "")
                msg = row.get("message", "")
                task = (lambda reminder_id, message: lambda: asyncio.run(self._run_one_shot_and_remove(reminder_id, message)))(rid, msg)
                self.schedule_fixed_task(task, run_time_str)
            if rows:
                logger.debug("TAM: Loaded %d one-shot reminder(s) from DB", len(rows))
        except Exception as e:
            logger.debug("TAM: Could not load one-shot reminders from DB: %s", e)

    async def _run_one_shot_and_remove(self, reminder_id: str, message: str) -> None:
        """Send reminder to latest channel and remove from DB (called when one-shot fires)."""
        await self.send_reminder_to_latest_channel(message)
        tam_storage.delete_one_shot_reminder(reminder_id)

    def record_event(
        self,
        event_name: str,
        when: str,
        note: str = "",
        event_date: Optional[str] = None,
        remind_on: Optional[str] = None,
        remind_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a date/event for future reference (no LLM; from record_date tool).
        Optional inference: if event_date (YYYY-MM-DD) and remind_on ('day_before' or 'on_day') are set,
        schedule a one-shot reminder. remind_message overrides the default reminder text.
        Returns dict with recorded entry and any scheduled reminder info."""
        entry = {
            "event_name": event_name.strip() or "event",
            "when": when.strip() or "",
            "note": note.strip() or "",
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_date": event_date.strip() if event_date else "",
            "remind_on": (remind_on or "").strip().lower() or "",
            "remind_message": (remind_message or "").strip() or "",
        }
        self.recorded_events.append(entry)
        self._save_recorded_events()
        logger.debug("TAM: Recorded event %s when=%s", entry["event_name"], entry["when"])

        result: Dict[str, Any] = {"recorded": True, "event_name": entry["event_name"], "when": entry["when"]}
        reminders_scheduled: List[str] = []

        if entry["event_date"] and entry["remind_on"]:
            try:
                ev_date = datetime.strptime(entry["event_date"], "%Y-%m-%d")
            except ValueError:
                logger.warning("TAM: Invalid event_date %s; skipping reminder", entry["event_date"])
            else:
                msg = entry["remind_message"] or f"Reminder: {entry['event_name']} is today!"
                if entry["remind_on"] == "day_before":
                    run_date = ev_date - timedelta(days=1)
                    run_time_str = run_date.strftime("%Y-%m-%d 09:00:00")
                    day_before_msg = entry["remind_message"] or f"Reminder: {entry['event_name']} is tomorrow!"
                    self.schedule_one_shot(day_before_msg, run_time_str)
                    reminders_scheduled.append(f"day before ({run_time_str})")
                elif entry["remind_on"] == "on_day":
                    run_time_str = ev_date.strftime("%Y-%m-%d 09:00:00")
                    self.schedule_one_shot(msg, run_time_str)
                    reminders_scheduled.append(f"on day ({run_time_str})")
                if reminders_scheduled:
                    result["reminders_scheduled"] = reminders_scheduled
        return result

    def list_recorded_events(self) -> List[Dict]:
        """Return recorded events (for 'what is coming up?' etc.). Past events are removed before returning so the list does not grow indefinitely."""
        removed = self._cleanup_past_recorded_events()
        if removed > 0:
            self._save_recorded_events()
            logger.debug("TAM: Removed %d past recorded event(s) on list", removed)
        return list(self.recorded_events)

    def get_recorded_events_summary(self, limit: int = 10) -> str:
        """Short text summary of recorded events for injection into system context (e.g. 'what is coming up')."""
        events = self.list_recorded_events()
        if not events:
            return ""
        lines = []
        for e in events[-limit:]:
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

    def _run_cron_pending(self) -> None:
        """Run any cron jobs that are due and advance their next_run."""
        if not CRONITER_AVAILABLE or not self.cron_jobs:
            return
        now = datetime.now()
        with self._cron_lock:
            to_run = []
            for job in self.cron_jobs:
                if job["next_run"] <= now:
                    to_run.append(job)
            for job in to_run:
                try:
                    it = croniter(job["cron_expr"], now)
                    job["next_run"] = it.get_next(datetime)
                except Exception:
                    job["next_run"] = now + timedelta(minutes=1)
        for job in to_run:
            try:
                asyncio.run(job["task"]())
            except Exception as e:
                logger.exception(f"TAM: Cron job {job.get('job_id')} failed: {e}")

    def run_scheduler(self):
        while True:
            self.scheduler.run_pending()
            self._run_cron_pending()
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
        logger.debug("SchedulerPlugin cleanup done!")  


    
    