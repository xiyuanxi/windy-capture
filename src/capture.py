import asyncio
import logging
from datetime import datetime, timezone

from playwright.async_api import Browser

from src.animation import capture_burst_frames, is_animated
from src.config import CategoryConfig, GlobalConfig
from src.uploader import S3Uploader

logger = logging.getLogger("windy-capture.capture")


async def capture_category(
    browser: Browser,
    category: CategoryConfig,
    global_cfg: GlobalConfig,
    uploader: S3Uploader,
) -> None:
    logger.info("Starting capture for category: %s", category.name)
    context = await browser.new_context()
    try:
        page = await context.new_page()
        await page.goto(category.url, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("canvas#map", timeout=30000)
        await asyncio.sleep(global_cfg.wait_after_load_seconds)

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%H-%M-%S")

        # Always capture one static frame
        static_bytes = await page.locator("canvas#map").screenshot()
        key = uploader.upload_static(static_bytes, category=category.name, timestamp=timestamp, date_str=date_str)
        logger.info("Uploaded static frame: %s", key)

        # Detect animation and capture burst if needed
        animated = await is_animated(page, global_cfg.animation_detection_threshold)
        if animated:
            logger.info("Animation detected for %s, capturing %d frames", category.name, category.animation_frames)
            frames = await capture_burst_frames(
                page,
                num_frames=category.animation_frames,
                interval_ms=category.animation_frame_interval_ms,
            )
            for i, frame_bytes in enumerate(frames, start=1):
                uploader.upload_frame(
                    frame_bytes,
                    category=category.name,
                    timestamp=timestamp,
                    frame_num=i,
                    date_str=date_str,
                )
            logger.info("Uploaded %d frames for %s", len(frames), category.name)
        else:
            logger.info("No animation detected for %s", category.name)
    except Exception:
        logger.exception("Capture failed for category: %s", category.name)
        raise
    finally:
        await context.close()
