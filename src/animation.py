import asyncio
import io
from typing import List

import numpy as np
from PIL import Image, ImageChops


def compute_pixel_diff_ratio(img1_bytes: bytes, img2_bytes: bytes) -> float:
    """Return the percentage of pixels that differ between two JPEG images."""
    img1 = Image.open(io.BytesIO(img1_bytes)).convert("RGB")
    img2 = Image.open(io.BytesIO(img2_bytes)).convert("RGB")
    diff = ImageChops.difference(img1, img2)
    arr = np.array(diff)
    changed = np.any(arr > 10, axis=2).sum()
    total = arr.shape[0] * arr.shape[1]
    return (changed / total) * 100.0


async def wait_until_stable(
    page,
    threshold: float = 0.1,
    interval: float = 1.0,
    stable_count: int = 2,
    timeout: float = 30.0,
) -> None:
    """Wait until the canvas stops changing (all layers fully rendered).

    Takes screenshots at *interval* seconds apart. Once *stable_count*
    consecutive comparisons show less than *threshold* % pixel change,
    the canvas is considered stable.  Gives up after *timeout* seconds.
    Screenshot failures are tolerated — the check is best-effort.
    """
    import logging
    logger = logging.getLogger("windy-capture.animation")

    try:
        prev = await page.locator("canvas.maplibregl-canvas").screenshot(timeout=60000)
    except Exception:
        logger.warning("wait_until_stable: initial screenshot failed, skipping stability check")
        return

    consecutive = 0
    elapsed = 0.0

    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            curr = await page.locator("canvas.maplibregl-canvas").screenshot(timeout=60000)
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


async def is_animated(page, threshold: float) -> bool:
    """Return True if the canvas is animating (pixel diff ratio exceeds threshold)."""
    frame1 = await page.locator("canvas.maplibregl-canvas").screenshot(timeout=60000)
    await asyncio.sleep(0.3)
    frame2 = await page.locator("canvas.maplibregl-canvas").screenshot(timeout=60000)
    ratio = compute_pixel_diff_ratio(frame1, frame2)
    return bool(ratio > threshold)


async def capture_burst_frames(page, num_frames: int, interval_ms: int) -> List[bytes]:
    """Capture num_frames screenshots with interval_ms between each."""
    frames = []
    for _ in range(num_frames):
        frame = await page.locator("canvas.maplibregl-canvas").screenshot(timeout=60000)
        frames.append(frame)
        await asyncio.sleep(interval_ms / 1000.0)
    return frames
