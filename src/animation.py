import asyncio
import io
import logging
import time
from typing import List

import numpy as np
from PIL import Image, ImageChops

logger = logging.getLogger("windy-capture.animation")


def compute_pixel_diff_ratio(img1_bytes: bytes, img2_bytes: bytes) -> float:
    """Return the percentage of pixels that differ between two JPEG images."""
    img1 = Image.open(io.BytesIO(img1_bytes)).convert("RGB")
    img2 = Image.open(io.BytesIO(img2_bytes)).convert("RGB")
    diff = ImageChops.difference(img1, img2)
    arr = np.array(diff)
    changed = np.any(arr > 10, axis=2).sum()
    total = arr.shape[0] * arr.shape[1]
    return (changed / total) * 100.0


async def get_canvas_bbox(page) -> dict:
    """Return the bounding box of the maplibre canvas for use with page.screenshot(clip=...)."""
    handle = await page.locator("canvas.maplibregl-canvas").element_handle()
    bbox = await handle.bounding_box()
    if bbox is None:
        raise RuntimeError("Canvas has no bounding box (not visible?)")
    return bbox


async def canvas_screenshot(page, bbox: dict, timeout: int = 60000) -> bytes:
    """Screenshot the canvas area using page.screenshot(clip=...).

    Unlike Locator.screenshot(), this skips Playwright's element-stability
    check, so it works reliably on continuously-animated canvases.
    JPEG format is used for faster encoding and smaller pipe transfer.
    """
    return await page.screenshot(clip=bbox, timeout=timeout, type="jpeg", quality=85)


async def wait_until_stable(
    page,
    bbox: dict,
    threshold: float = 0.1,
    interval: float = 1.0,
    stable_count: int = 1,
    timeout: float = 30.0,
) -> None:
    """Wait until the canvas stops changing (all layers fully rendered).

    Takes screenshots every *interval* seconds. Once *stable_count* consecutive
    comparisons show less than *threshold* % pixel change, the canvas is
    considered stable. Gives up after *timeout* wall-clock seconds.
    Screenshot failures are tolerated — the check is best-effort.
    """
    try:
        prev = await canvas_screenshot(page, bbox, timeout=30000)
    except Exception:
        logger.warning("wait_until_stable: initial screenshot failed, skipping stability check")
        return

    consecutive = 0
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        await asyncio.sleep(interval)
        elapsed = time.monotonic() - start
        try:
            curr = await canvas_screenshot(page, bbox, timeout=30000)
        except Exception:
            logger.warning("wait_until_stable: screenshot failed at %.1fs, skipping", elapsed)
            continue
        ratio = compute_pixel_diff_ratio(prev, curr)
        logger.debug("stability check: %.2f%% changed (need %d more stable)", ratio, stable_count - consecutive)
        if ratio < threshold:
            consecutive += 1
            if consecutive >= stable_count:
                logger.info("Canvas stable after %.1fs", elapsed)
                return
        else:
            consecutive = 0
        prev = curr

    logger.warning("Canvas did not stabilise within %.0fs, proceeding anyway", timeout)


async def is_animated(page, bbox: dict, threshold: float) -> bool:
    """Return True if the canvas is animating (pixel diff ratio exceeds threshold)."""
    frame1 = await canvas_screenshot(page, bbox)
    await asyncio.sleep(0.3)
    frame2 = await canvas_screenshot(page, bbox)
    ratio = compute_pixel_diff_ratio(frame1, frame2)
    return bool(ratio > threshold)


async def capture_burst_frames(page, bbox: dict, num_frames: int, interval_ms: int) -> List[bytes]:
    """Capture num_frames screenshots with interval_ms between each."""
    frames = []
    for _ in range(num_frames):
        frame = await canvas_screenshot(page, bbox)
        frames.append(frame)
        await asyncio.sleep(interval_ms / 1000.0)
    return frames
