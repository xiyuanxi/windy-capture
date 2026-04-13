from datetime import datetime, timezone
from typing import Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import BrowserContext

from src.capture import capture_category
from src.config import Config
from src.uploader import S3Uploader


def next_aligned_time(interval_minutes: int) -> datetime:
    """Return the next UTC datetime aligned to a multiple of interval_minutes.

    Example: interval=5, current time=14:23 → returns 14:25:00
             interval=3, current time=14:23 → returns 14:24:00
    """
    now = datetime.now(timezone.utc)
    # Seconds since Unix epoch, rounded down to whole minutes
    current_minute = int(now.timestamp()) // 60
    # Next minute that is a multiple of interval_minutes
    next_minute = (current_minute // interval_minutes + 1) * interval_minutes
    return datetime.fromtimestamp(next_minute * 60, tz=timezone.utc)


def build_scheduler(
    config: Config,
    contexts: Dict[str, BrowserContext],
    uploader: S3Uploader,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    for category in config.categories:
        if not category.enabled:
            continue
        first_run = next_aligned_time(category.schedule_interval_minutes)
        scheduler.add_job(
            capture_category,
            trigger="interval",
            minutes=category.schedule_interval_minutes,
            args=[contexts[category.name], category, config.global_, uploader],
            id=f"capture_{category.name}",
            max_instances=1,
            next_run_time=first_run,
        )

    return scheduler
