import asyncio
import logging

from playwright.async_api import async_playwright

from src.config import load_config
from src.routing import install_request_blocker
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
    enabled = [c for c in config.categories if c.enabled]
    logger.info("Categories: %s", [c.name for c in enabled])

    # Resolve storage state path (if configured)
    storage_state = config.global_.storage_state or None
    if storage_state:
        import os
        if not os.path.isfile(storage_state):
            logger.warning("storage_state file not found: %s — starting without login", storage_state)
            storage_state = None
        else:
            logger.info("Using storage state: %s", storage_state)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        logger.info("Browser launched")

        # Create one persistent context per category (keeps HTTP cache between runs)
        contexts = {}
        for cat in enabled:
            ctx = await browser.new_context(
                viewport={
                    "width": config.global_.viewport_width,
                    "height": config.global_.viewport_height,
                },
                device_scale_factor=config.global_.device_scale_factor,
                storage_state=storage_state,
            )
            await install_request_blocker(ctx)
            contexts[cat.name] = ctx
            logger.info("Created persistent context for %s", cat.name)

        scheduler = build_scheduler(config, contexts, uploader)
        try:
            scheduler.start()
            logger.info("Scheduler started. Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(60)
        finally:
            logger.info("Shutting down scheduler...")
            scheduler.shutdown()
            for name, ctx in contexts.items():
                await ctx.close()
                logger.info("Closed context for %s", name)
            await browser.close()
            logger.info("Browser closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
