import asyncio
import logging
from datetime import datetime, timezone

from playwright.async_api import BrowserContext

from src.animation import capture_burst_frames, is_animated, wait_until_stable
from src.config import CategoryConfig, GlobalConfig
from src.uploader import S3Uploader

logger = logging.getLogger("windy-capture.capture")


async def capture_category(
    context: BrowserContext,
    category: CategoryConfig,
    global_cfg: GlobalConfig,
    uploader: S3Uploader,
) -> None:
    logger.info("Starting capture for category: %s", category.name)
    page = await context.new_page()
    try:
        await page.goto(category.url, wait_until="load", timeout=60000)
        await page.wait_for_selector("canvas.maplibregl-canvas", timeout=30000)
        await asyncio.sleep(global_cfg.wait_after_load_seconds)
        await wait_until_stable(page)

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%H-%M-%S")

        # --- Capture phase: detect animation & burst first, static last ---
        # is_animated + burst frames give the page extra rendering time
        # before the static screenshot, avoiding partial-render captures.
        animated = await is_animated(page, global_cfg.animation_detection_threshold)
        burst_frames: list[bytes] = []
        if animated:
            logger.info("Animation detected for %s, capturing %d frames", category.name, category.animation_frames)
            burst_frames = await capture_burst_frames(
                page,
                num_frames=category.animation_frames,
                interval_ms=category.animation_frame_interval_ms,
            )
        else:
            logger.info("No animation detected for %s", category.name)

        # Static captured last — page has had the most time to render
        static_bytes = await page.locator("canvas.maplibregl-canvas").screenshot(timeout=60000)

        # --- Upload phase: all screenshots done, safe to block ---
        key = uploader.upload_static(static_bytes, category=category.name, timestamp=timestamp, date_str=date_str)
        logger.info("Uploaded static frame: %s", key)

        for i, frame_bytes in enumerate(burst_frames, start=1):
            uploader.upload_frame(
                frame_bytes,
                category=category.name,
                timestamp=timestamp,
                frame_num=i,
                date_str=date_str,
            )
        if burst_frames:
            logger.info("Uploaded %d frames for %s", len(burst_frames), category.name)
    except Exception:
        logger.exception("Capture failed for category: %s", category.name)
        raise
    finally:
        await page.close()
