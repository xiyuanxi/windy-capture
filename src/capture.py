import asyncio
import logging
from datetime import datetime, timezone

from playwright.async_api import BrowserContext

from src.animation import (
    canvas_screenshot,
    capture_burst_frames,
    get_canvas_bbox,
    wait_until_stable,
)
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

        # Resolve canvas bbox once and reuse for all subsequent screenshots.
        # Using page.screenshot(clip=bbox) avoids Locator.screenshot()'s
        # element-stability check, which can hang on animated canvases.
        bbox = await get_canvas_bbox(page)

        # Skip stability check for animated categories — their canvas never
        # stabilises, so we'd just waste the full timeout budget.
        if category.animation_frames > 1:
            logger.info("Skipping stability check for animated category %s", category.name)
        else:
            await wait_until_stable(page, bbox)

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%H-%M-%S")

        # Capture static immediately after stability — guaranteed even if
        # burst capture fails later.
        static_bytes = await canvas_screenshot(page, bbox)

        # Burst frames driven by config (animation_frames > 1). Best-effort —
        # failures here should not prevent the static upload.
        burst_frames: list[bytes] = []
        if category.animation_frames > 1:
            try:
                logger.info("Capturing %d burst frames for %s", category.animation_frames, category.name)
                burst_frames = await capture_burst_frames(
                    page,
                    bbox,
                    num_frames=category.animation_frames,
                    interval_ms=category.animation_frame_interval_ms,
                )
            except Exception:
                logger.exception("Burst capture failed for %s, continuing with static only", category.name)

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
