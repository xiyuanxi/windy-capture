import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image
from src.animation import compute_pixel_diff_ratio, is_animated, capture_burst_frames


BBOX = {"x": 0, "y": 0, "width": 100, "height": 100}


def make_image_bytes(color: tuple, size: tuple = (100, 100)) -> bytes:
    """Create a solid-color JPEG image as bytes."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_identical_images_have_zero_diff():
    img = make_image_bytes((128, 128, 128))
    ratio = compute_pixel_diff_ratio(img, img)
    assert ratio == pytest.approx(0.0, abs=0.1)


def test_completely_different_images_have_high_diff():
    img1 = make_image_bytes((0, 0, 0))
    img2 = make_image_bytes((255, 255, 255))
    ratio = compute_pixel_diff_ratio(img1, img2)
    assert ratio > 90.0


def test_partially_different_images():
    img1 = Image.new("RGB", (100, 100), color=(0, 0, 0))
    img2 = Image.new("RGB", (100, 100), color=(0, 0, 0))
    # Make top half of img2 white
    for y in range(50):
        for x in range(100):
            img2.putpixel((x, y), (255, 255, 255))

    def to_bytes(img):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    ratio = compute_pixel_diff_ratio(to_bytes(img1), to_bytes(img2))
    # About 50% of pixels changed
    assert 40.0 < ratio < 60.0


@pytest.mark.asyncio
async def test_is_animated_returns_true_when_diff_exceeds_threshold():
    static_img = make_image_bytes((0, 0, 0))
    moving_img = make_image_bytes((255, 255, 255))

    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(side_effect=[static_img, moving_img])

    result = await is_animated(mock_page, BBOX, threshold=0.5)
    assert result is True


@pytest.mark.asyncio
async def test_is_animated_returns_false_when_diff_below_threshold():
    static_img = make_image_bytes((100, 100, 100))

    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(side_effect=[static_img, static_img])

    result = await is_animated(mock_page, BBOX, threshold=0.5)
    assert result is False


@pytest.mark.asyncio
async def test_capture_burst_frames_returns_correct_count():
    frame = make_image_bytes((50, 100, 150))

    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(return_value=frame)

    frames = await capture_burst_frames(mock_page, BBOX, num_frames=5, interval_ms=10)
    assert len(frames) == 5
    assert all(isinstance(f, bytes) for f in frames)


@pytest.mark.asyncio
async def test_capture_burst_frames_screenshots_with_clip():
    frame = make_image_bytes((0, 0, 0))

    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(return_value=frame)

    await capture_burst_frames(mock_page, BBOX, num_frames=3, interval_ms=10)
    assert mock_page.screenshot.call_count == 3
    for call in mock_page.screenshot.call_args_list:
        assert call.kwargs.get("clip") == BBOX
