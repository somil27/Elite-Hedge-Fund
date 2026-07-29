"""
Scheduler — runs trading cycles on a configurable schedule.
Can be run standalone:  python scheduler.py
Or imported and started alongside the FastAPI app.

Schedule examples:
  - Market open (9:30 AM ET) short-term cycle daily
  - Weekly long-term cycle on Monday morning
  - Every N minutes in dev/testing mode
"""
import asyncio
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

logger = structlog.get_logger()

API_BASE = "http://localhost:8000"


async def trigger_cycle(mode: str = "short_term", auto_mode: bool = False):
    """Hit the API to start a new cycle."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{API_BASE}/api/cycles/start",
                json={"mode": mode, "auto_mode": auto_mode},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("scheduled_cycle_started",
                        cycle_id=data["cycle_id"], mode=mode)
        except Exception as e:
            logger.error("scheduled_cycle_failed", error=str(e))


def build_scheduler(
    short_term_cron: str = "30 9 * * 1-5",   # 9:30 AM ET Mon–Fri
    long_term_cron: str  = "0 8 * * 1",       # 8:00 AM ET every Monday
    auto_mode: bool = False,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="America/New_York")

    # Short-term daily cycle at market open
    scheduler.add_job(
        trigger_cycle,
        CronTrigger.from_crontab(short_term_cron, timezone="America/New_York"),
        kwargs={"mode": "short_term", "auto_mode": auto_mode},
        id="short_term_daily",
        name="Short-term daily cycle",
        replace_existing=True,
    )

    # Long-term weekly cycle
    scheduler.add_job(
        trigger_cycle,
        CronTrigger.from_crontab(long_term_cron, timezone="America/New_York"),
        kwargs={"mode": "long_term", "auto_mode": auto_mode},
        id="long_term_weekly",
        name="Long-term weekly cycle",
        replace_existing=True,
    )

    return scheduler


async def main():
    logger.info("scheduler_starting")
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler_running", jobs=len(scheduler.get_jobs()))

    # Keep alive
    try:
        while True:
            await asyncio.sleep(60)
            jobs = scheduler.get_jobs()
            for j in jobs:
                logger.debug("next_run", job=j.name,
                             next=j.next_run_time.isoformat() if j.next_run_time else None)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    asyncio.run(main())
