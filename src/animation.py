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


async def is_animated(page, threshold: float) -> bool:
    """Return True if the canvas is animating (pixel diff ratio exceeds threshold)."""
    frame1 = await page.locator("canvas#map").screenshot()
    await asyncio.sleep(0.3)
    frame2 = await page.locator("canvas#map").screenshot()
    ratio = compute_pixel_diff_ratio(frame1, frame2)
    return bool(ratio > threshold)


async def capture_burst_frames(page, num_frames: int, interval_ms: int) -> List[bytes]:
    """Capture num_frames screenshots with interval_ms between each."""
    frames = []
    for _ in range(num_frames):
        frame = await page.locator("canvas#map").screenshot()
        frames.append(frame)
        await asyncio.sleep(interval_ms / 1000.0)
    return frames
