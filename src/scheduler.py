import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import BrowserContext

from src.capture import capture_category
from src.config import CategoryConfig, Config, GlobalConfig
from src.uploader import S3Uploader

logger = logging.getLogger("windy-capture.scheduler")

# Shared lock — ensures only one category captures at a time across all jobs
_capture_lock = asyncio.Lock()


async def capture_category_serialized(
    context: BrowserContext,
    category: CategoryConfig,
    global_cfg: GlobalConfig,
    uploader: S3Uploader,
) -> None:
    """Wrap capture_category with a shared lock so captures run one at a time."""
    if _capture_lock.locked():
        logger.info("Capture queued for %s (another capture in progress)", category.name)
    async with _capture_lock:
        await capture_category(context, category, global_cfg, uploader)


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

    # Jobs are serialized via _capture_lock — only one capture runs at a time.
    # Stagger first-run times slightly so they queue in a predictable order.
    STAGGER_SECONDS = 5

    for idx, category in enumerate(c for c in config.categories if c.enabled):
        first_run = next_aligned_time(category.schedule_interval_minutes) + timedelta(seconds=idx * STAGGER_SECONDS)
        scheduler.add_job(
            capture_category_serialized,
            trigger="interval",
            minutes=category.schedule_interval_minutes,
            args=[contexts[category.name], category, config.global_, uploader],
            id=f"capture_{category.name}",
            max_instances=1,
            next_run_time=first_run,
        )

    return scheduler
