from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import Browser

from src.capture import capture_category
from src.config import Config
from src.uploader import S3Uploader


def build_scheduler(
    config: Config,
    browser: Browser,
    uploader: S3Uploader,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    for category in config.categories:
        if not category.enabled:
            continue
        scheduler.add_job(
            capture_category,
            trigger="interval",
            minutes=category.schedule_interval_minutes,
            args=[browser, category, config.global_, uploader],
            id=f"capture_{category.name}",
            max_instances=1,
        )

    return scheduler
