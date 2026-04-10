import asyncio
import logging

from playwright.async_api import async_playwright

from src.config import load_config
from src.scheduler import build_scheduler
from src.uploader import S3Uploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("windy-capture")


async def main() -> None:
    config = load_config("config.yaml")
    uploader = S3Uploader(bucket=config.s3.bucket, prefix=config.s3.prefix)

    logger.info("Starting Windy capture service")
    logger.info(
        "Categories: %s",
        [c.name for c in config.categories if c.enabled],
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        logger.info("Browser launched")
        scheduler = build_scheduler(config, browser, uploader)
        try:
            scheduler.start()
            logger.info("Scheduler started. Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(60)
        finally:
            logger.info("Shutting down scheduler...")
            scheduler.shutdown()
            await browser.close()
            logger.info("Browser closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
