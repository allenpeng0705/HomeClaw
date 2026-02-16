# plugins/scheduler_plugin/scheduler_plugin.py
from datetime import datetime, timedelta
import threading
import yaml
import random
import asyncio
import schedule
import time
from threading import Event, Thread
from base.BasePlugin import BasePlugin
from loguru import logger
from core.coreInterface import CoreInterface

class SchedulerPlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        self.scheduler = schedule.Scheduler()
        self.scheduled_jobs = []
        self.thread = None
        self.stop_event = Event()

    def initialize(self):
        if self.initialized:
            return
        logger.debug("Initializing SchedulerPlugin plugin")
        super().initialize()
        self.schedule_tasks_from_config()
        self.thread = Thread(target=self.run_scheduler)
        self.thread.daemon = True
        self.thread.start()

        self.initialized = True

    def schedule_repeated_task(self, task, interval_unit, interval, start_time=None):
        def job_wrapper():
            asyncio.run(task())
            # Schedule the next run using the schedule library
            self._schedule_interval_task(task, interval_unit, interval)

        if start_time:
            now = datetime.now()
            start_time_obj = datetime.strptime(start_time, "%H:%M:%S").replace(year=now.year, month=now.month, day=now.day)
            if now > start_time_obj:
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

    def schedule_fixed_task(self, task, frequency, time_str, day_of_week=None, day_of_month=None, month=None):
        if frequency == 'daily':
            job = self.scheduler.every().day.at(time_str).do(lambda: asyncio.run(task()))
        elif frequency == 'weekly':
            if day_of_week is None:
                raise ValueError("day_of_week must be specified for weekly frequency")
            job = getattr(self.scheduler.every(), day_of_week).at(time_str).do(lambda: asyncio.run(task()))
        elif frequency == 'monthly':
            if day_of_month is None:
                raise ValueError("day_of_month must be specified for monthly frequency")
            def monthly_task():
                if datetime.now().day == day_of_month:
                    asyncio.run(task())
            job = self.scheduler.every().day.at(time_str).do(monthly_task)
        elif frequency == 'yearly':
            if month is None or day_of_month is None:
                raise ValueError("month and day_of_month must be specified for yearly frequency")
            def yearly_task():
                now = datetime.now()
                if now.month == month and now.day == day_of_month:
                    asyncio.run(task())
            job = self.scheduler.every().day.at(time_str).do(yearly_task)
        else:
            raise ValueError(f"Unsupported frequency: {frequency}")

        self.scheduled_jobs.append(job)
        logger.debug(f"Scheduled {frequency} task at {time_str}")

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

    def run_scheduler(self):
        while not self.stop_event.is_set():
            self.scheduler.run_pending()
            time.sleep(10)

    def schedule_tasks_from_config(self):
        job = None
        logger.debug(f'Scheduling tasks from config: {self.config}')
        for task_name, task_config in self.config['tasks'].items():
            if hasattr(self, task_name):
                task = getattr(self, task_name)
            if task_config['type'] == 'repeated':
                interval_unit = task_config['interval_unit']
                interval = task_config['interval']
                start_time = task_config['start_time']
                self.schedule_repeated_task(task, interval_unit, interval, start_time)
            elif task_config['type'] == 'random':
                interval_unit = task_config['interval_unit']
                min_interval = task_config['min_interval']
                max_interval = task_config['max_interval']
                self.schedule_random_task(task, interval_unit, min_interval, max_interval)
            elif task_config['type'] == 'fixed':
                frequency = task_config['frequency']
                time_str = task_config['time']
                day_of_week = None
                day_of_month = None
                month = None
                if frequency == 'weekly':
                    day_of_week = task_config.get('day_of_week')
                if frequency == 'monthly' or frequency == 'yearly':
                    day_of_month = task_config.get('day_of_month')
                    month = task_config.get('month')

                self.schedule_fixed_task(task, frequency, time_str, day_of_week, day_of_month, month)


    def cleanup(self):
        super().cleanup()
        self.stop_event.set()
        #for job in self.scheduled_jobs:
        #    job.cancel()
        if self.thread.is_alive():
            self.thread.join()
        logger.debug("SchedulerPlugin cleanup done!")