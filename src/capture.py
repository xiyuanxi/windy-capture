import asyncio
from datetime import datetime, timezone

from playwright.async_api import Browser

from src.animation import capture_burst_frames, is_animated
from src.config import CategoryConfig, GlobalConfig
from src.uploader import S3Uploader


async def capture_category(
    browser: Browser,
    category: CategoryConfig,
    global_cfg: GlobalConfig,
    uploader: S3Uploader,
) -> None:
    context = await browser.new_context()
    try:
        page = await context.new_page()
        await page.goto(category.url, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("canvas#map", timeout=30000)
        await asyncio.sleep(global_cfg.wait_after_load_seconds)

        timestamp = datetime.now(timezone.utc).strftime("%H-%M-%S")

        # Always capture one static frame
        static_bytes = await page.locator("canvas#map").screenshot()
        uploader.upload_static(static_bytes, category=category.name, timestamp=timestamp)

        # Detect animation and capture burst if needed
        animated = await is_animated(page, global_cfg.animation_detection_threshold)
        if animated:
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
                )
    finally:
        await context.close()
