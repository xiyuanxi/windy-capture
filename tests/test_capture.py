import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from src.config import CategoryConfig, GlobalConfig
from src.capture import capture_category


def make_category(**overrides):
    defaults = dict(
        name="radar",
        url="https://www.windy.com/-Radar/radar?42.158,-85.504,8",
        enabled=True,
        schedule_interval_minutes=5,
        animation_frames=3,
        animation_frame_interval_ms=100,
    )
    defaults.update(overrides)
    return CategoryConfig(**defaults)


def make_global_cfg(**overrides):
    defaults = dict(wait_after_load_seconds=0, animation_detection_threshold=0.5)
    defaults.update(overrides)
    return GlobalConfig(**defaults)


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.locator = MagicMock()
    return page


@pytest.fixture
def mock_context(mock_page):
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=mock_page)
    ctx.close = AsyncMock()
    return ctx


@pytest.fixture
def mock_browser(mock_context):
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=mock_context)
    return browser


@pytest.fixture
def mock_uploader():
    uploader = MagicMock()
    uploader.upload_static = MagicMock(return_value="s3://bucket/key/static.jpg")
    uploader.upload_frame = MagicMock(return_value="s3://bucket/key/frame.jpg")
    return uploader


@pytest.mark.asyncio
async def test_capture_opens_url(mock_browser, mock_page, mock_uploader):
    cat = make_category()
    global_cfg = make_global_cfg()

    with patch("src.capture.is_animated", new=AsyncMock(return_value=False)):
        with patch("src.capture.capture_burst_frames", new=AsyncMock(return_value=[])):
            frame_bytes = b"fake-jpeg"
            mock_locator = MagicMock()
            mock_locator.screenshot = AsyncMock(return_value=frame_bytes)
            mock_page.locator.return_value = mock_locator

            await capture_category(mock_browser, cat, global_cfg, mock_uploader)

    mock_page.goto.assert_called_once_with(
        cat.url, wait_until="networkidle", timeout=60000
    )


@pytest.mark.asyncio
async def test_capture_waits_for_canvas(mock_browser, mock_page, mock_uploader):
    cat = make_category()
    global_cfg = make_global_cfg()

    with patch("src.capture.is_animated", new=AsyncMock(return_value=False)):
        frame_bytes = b"fake-jpeg"
        mock_locator = MagicMock()
        mock_locator.screenshot = AsyncMock(return_value=frame_bytes)
        mock_page.locator.return_value = mock_locator

        await capture_category(mock_browser, cat, global_cfg, mock_uploader)

    mock_page.wait_for_selector.assert_called_once_with("canvas#map", timeout=30000)


@pytest.mark.asyncio
async def test_capture_uploads_static_frame(mock_browser, mock_page, mock_uploader):
    cat = make_category(name="radar")
    global_cfg = make_global_cfg()
    frame_bytes = b"static-frame"

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(return_value=frame_bytes)
    mock_page.locator.return_value = mock_locator

    with patch("src.capture.is_animated", new=AsyncMock(return_value=False)):
        await capture_category(mock_browser, cat, global_cfg, mock_uploader)

    mock_uploader.upload_static.assert_called_once()
    call_args = mock_uploader.upload_static.call_args
    assert call_args[1]["category"] == "radar" or call_args[0][1] == "radar"


@pytest.mark.asyncio
async def test_capture_uploads_burst_frames_when_animated(mock_browser, mock_page, mock_uploader):
    cat = make_category(name="satellite", animation_frames=3)
    global_cfg = make_global_cfg()
    frame_bytes = b"burst-frame"

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(return_value=frame_bytes)
    mock_page.locator.return_value = mock_locator

    burst_frames = [b"f1", b"f2", b"f3"]
    with patch("src.capture.is_animated", new=AsyncMock(return_value=True)):
        with patch("src.capture.capture_burst_frames", new=AsyncMock(return_value=burst_frames)):
            await capture_category(mock_browser, cat, global_cfg, mock_uploader)

    assert mock_uploader.upload_frame.call_count == 3


@pytest.mark.asyncio
async def test_capture_does_not_upload_frames_when_not_animated(mock_browser, mock_page, mock_uploader):
    cat = make_category()
    global_cfg = make_global_cfg()
    frame_bytes = b"static-only"

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(return_value=frame_bytes)
    mock_page.locator.return_value = mock_locator

    with patch("src.capture.is_animated", new=AsyncMock(return_value=False)):
        await capture_category(mock_browser, cat, global_cfg, mock_uploader)

    mock_uploader.upload_frame.assert_not_called()


@pytest.mark.asyncio
async def test_context_always_closed_even_on_error(mock_browser, mock_context, mock_page, mock_uploader):
    cat = make_category()
    global_cfg = make_global_cfg()
    mock_page.goto = AsyncMock(side_effect=RuntimeError("network error"))

    with pytest.raises(RuntimeError, match="network error"):
        await capture_category(mock_browser, cat, global_cfg, mock_uploader)

    mock_context.close.assert_called_once()
