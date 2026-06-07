# -*- coding: utf-8 -*-
"""
Scheduler Module - APScheduler Setup

Handles background tasks like token refresh and periodic data updates.
"""
import asyncio
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger


class Scheduler:
    """
    Background Task Scheduler
    
    Uses APScheduler for:
    - Token auto-refresh
    - Periodic data fetching
    - Scheduled strategy execution
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._is_running = False

    def start(self):
        """Start the scheduler"""
        if not self._is_running:
            if self._scheduler is None:
                self._scheduler = AsyncIOScheduler()
            self._scheduler.start()
            self._is_running = True
            print(f"[Scheduler] Started at {datetime.now()}")

    def stop(self):
        """Stop the scheduler"""
        if self._is_running:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception as e:
                print(f"[Scheduler] Error during shutdown: {e}")
            self._scheduler = None
            self._is_running = False
            print(f"[Scheduler] Stopped at {datetime.now()}")

    def pause(self):
        """Pause the scheduler"""
        if self._is_running:
            self._scheduler.pause()
            print(f"[Scheduler] Paused at {datetime.now()}")

    def resume(self):
        """Resume the scheduler"""
        if self._is_running:
            self._scheduler.resume()
            print(f"[Scheduler] Resumed at {datetime.now()}")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self._is_running and self._scheduler is not None

    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        seconds: int = 60,
        **kwargs
    ):
        """
        Add a job that runs at fixed intervals.
        
        Args:
            func: Async function to execute
            job_id: Unique identifier for the job
            seconds: Interval in seconds
            **kwargs: Additional arguments for add_job
        """
        self._scheduler.add_job(
            func,
            IntervalTrigger(seconds=seconds),
            id=job_id,
            replace_existing=True,
            **kwargs
        )
        print(f"[Scheduler] Added interval job '{job_id}' (every {seconds}s)")

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        hour: int = 9,
        minute: int = 0,
        replace_existing: bool = True,
        **kwargs
    ):
        """
        Add a job that runs at a specific time daily.
        """
        self._scheduler.add_job(
            func,
            CronTrigger(hour=hour, minute=minute),
            id=job_id,
            replace_existing=replace_existing,
            **kwargs
        )
        print(f"[Scheduler] Added cron job: {job_id} (at {hour:02d}:{minute:02d})")

    def add_date_job(
        self,
        func: Callable,
        job_id: str,
        run_date: datetime,
        **kwargs
    ):
        """
        Add a job that runs once at a specific date/time.
        """
        self._scheduler.add_job(
            func,
            trigger='date',
            run_date=run_date,
            id=job_id,
            replace_existing=True,
            **kwargs
        )
        print(f"[Scheduler] Added date job: {job_id} (at {run_date})")

    def remove_job(self, job_id: str):
        """Remove a scheduled job"""
        try:
            self._scheduler.remove_job(job_id)
            print(f"[Scheduler] Removed job: {job_id}")
        except Exception as e:
            print(f"[Scheduler] Failed to remove job {job_id}: {e}")

    def get_jobs(self):
        """Get list of all scheduled jobs"""
        return self._scheduler.get_jobs()

    def get_job(self, job_id: str):
        """Get a scheduled job by ID"""
        return self._scheduler.get_job(job_id)

    def pause_job(self, job_id: str):
        """Pause a job"""
        self._scheduler.pause_job(job_id)
        print(f"[Scheduler] Paused job: {job_id}")

    def resume_job(self, job_id: str):
        """Resume a paused job"""
        self._scheduler.resume_job(job_id)
        print(f"[Scheduler] Resumed job: {job_id}")


# Pre-defined job functions
async def token_refresh_job(client, password: str):
    """Refresh API token"""
    try:
        await client.get_token(password)
        print(f"[Scheduler] Token refreshed at {datetime.now()}")
    except Exception as e:
        print(f"[Scheduler] Token refresh failed: {e}")


async def heartbeat_job():
    """Simple heartbeat for monitoring"""
    print(f"[Scheduler] Heartbeat at {datetime.now()}")
