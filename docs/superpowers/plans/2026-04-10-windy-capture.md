# Windy Capture Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scheduled Python service that captures Windy.com map screenshots (static + animated frames) per configurable category and uploads to AWS S3, packaged as a Docker container.

**Architecture:** Single shared Chromium process via Playwright; each scheduled job creates an isolated BrowserContext, captures the `canvas#map` element, detects animation via pixel diff, then uploads static frame + optional burst frames to S3. APScheduler registers one async job per enabled category.

**Tech Stack:** Python 3.11, Playwright (async), APScheduler 3.x, boto3, Pillow, PyYAML, pytest, Docker (mcr.microsoft.com/playwright/python)

---

## File Map

| File | Responsibility |
|---|---|
| `src/config.py` | Load `config.yaml`, expose typed dataclasses |
| `src/uploader.py` | Upload bytes to S3, build S3 key from category/timestamp |
| `src/animation.py` | Pixel-diff animation detection; burst frame capture |
| `src/capture.py` | Full capture flow for one category (browser context lifecycle) |
| `src/scheduler.py` | Build APScheduler instance with one job per enabled category |
| `src/main.py` | Entry point: launch browser, start scheduler, block forever |
| `tests/test_config.py` | Unit tests for config loading |
| `tests/test_uploader.py` | Unit tests for S3 key generation and upload (mocked boto3) |
| `tests/test_animation.py` | Unit tests for pixel diff and burst capture (mocked page) |
| `tests/test_capture.py` | Integration-style tests for capture flow (mocked browser) |
| `tests/test_scheduler.py` | Unit tests for scheduler job registration |
| `config.yaml` | Sample multi-category configuration |
| `.env.example` | Template for AWS credentials |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Local/remote orchestration |

---

## Task 1: Project Scaffold & Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
playwright==1.44.0
APScheduler==3.10.4
boto3==1.34.0
Pillow==10.3.0
PyYAML==6.0.1
numpy==1.26.4
pytest==8.2.0
pytest-asyncio==0.23.6
```

- [ ] **Step 2: Create `.env.example`**

```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=us-east-1
```

- [ ] **Step 3: Create empty `src/__init__.py` and `tests/__init__.py`**

Both files are empty. Just create them so Python treats these directories as packages.

- [ ] **Step 4: Install dependencies locally for testing**

```bash
pip install -r requirements.txt
playwright install chromium
```

Expected: all packages install without errors.

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt .env.example src/__init__.py tests/__init__.py
git commit -m "chore: project scaffold and dependencies"
```

---

## Task 2: Config Loader

**Files:**
- Create: `config.yaml`
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create `config.yaml`**

```yaml
global:
  wait_after_load_seconds: 5
  animation_detection_threshold: 0.5

s3:
  bucket: "your-bucket"
  prefix: "windy-capture"

categories:
  - name: radar
    enabled: true
    url: "https://www.windy.com/-Radar/radar?42.158,-85.504,8"
    schedule_interval_minutes: 5
    animation_frames: 12
    animation_frame_interval_ms: 500

  - name: satellite
    enabled: true
    url: "https://www.windy.com/-Satellite/satellite?42.158,-85.504,8"
    schedule_interval_minutes: 10
    animation_frames: 8
    animation_frame_interval_ms: 600

  - name: wind
    enabled: true
    url: "https://www.windy.com/-Menu/menu?42.158,-85.504,8"
    schedule_interval_minutes: 5
    animation_frames: 10
    animation_frame_interval_ms: 500
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_config.py
import pytest
import tempfile
import os
import yaml
from src.config import load_config, Config, CategoryConfig, GlobalConfig, S3Config


SAMPLE_YAML = """
global:
  wait_after_load_seconds: 3
  animation_detection_threshold: 1.0

s3:
  bucket: "test-bucket"
  prefix: "test-prefix"

categories:
  - name: radar
    enabled: true
    url: "https://www.windy.com/-Radar/radar?42.158,-85.504,8"
    schedule_interval_minutes: 5
    animation_frames: 12
    animation_frame_interval_ms: 500

  - name: satellite
    enabled: false
    url: "https://www.windy.com/-Satellite/satellite?42.158,-85.504,8"
    schedule_interval_minutes: 10
    animation_frames: 8
    animation_frame_interval_ms: 600
"""


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(SAMPLE_YAML)
    return str(path)


def test_load_config_returns_config_object(config_file):
    config = load_config(config_file)
    assert isinstance(config, Config)


def test_global_settings_loaded(config_file):
    config = load_config(config_file)
    assert config.global_.wait_after_load_seconds == 3
    assert config.global_.animation_detection_threshold == 1.0


def test_s3_settings_loaded(config_file):
    config = load_config(config_file)
    assert config.s3.bucket == "test-bucket"
    assert config.s3.prefix == "test-prefix"


def test_categories_loaded(config_file):
    config = load_config(config_file)
    assert len(config.categories) == 2


def test_category_fields(config_file):
    config = load_config(config_file)
    radar = config.categories[0]
    assert radar.name == "radar"
    assert radar.enabled is True
    assert radar.url == "https://www.windy.com/-Radar/radar?42.158,-85.504,8"
    assert radar.schedule_interval_minutes == 5
    assert radar.animation_frames == 12
    assert radar.animation_frame_interval_ms == 500


def test_disabled_category_loaded(config_file):
    config = load_config(config_file)
    satellite = config.categories[1]
    assert satellite.enabled is False


def test_category_defaults_applied():
    minimal_yaml = """
global:
  wait_after_load_seconds: 5
  animation_detection_threshold: 0.5
s3:
  bucket: "b"
  prefix: "p"
categories:
  - name: wind
    url: "https://www.windy.com/wind"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(minimal_yaml)
        path = f.name
    try:
        config = load_config(path)
        cat = config.categories[0]
        assert cat.enabled is True
        assert cat.schedule_interval_minutes == 5
        assert cat.animation_frames == 10
        assert cat.animation_frame_interval_ms == 500
    finally:
        os.unlink(path)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `src.config` doesn't exist yet.

- [ ] **Step 4: Implement `src/config.py`**

```python
from dataclasses import dataclass, field
from typing import List
import yaml


@dataclass
class GlobalConfig:
    wait_after_load_seconds: int = 5
    animation_detection_threshold: float = 0.5


@dataclass
class S3Config:
    bucket: str
    prefix: str = "windy-capture"


@dataclass
class CategoryConfig:
    name: str
    url: str
    enabled: bool = True
    schedule_interval_minutes: int = 5
    animation_frames: int = 10
    animation_frame_interval_ms: int = 500


@dataclass
class Config:
    global_: GlobalConfig
    s3: S3Config
    categories: List[CategoryConfig]


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)

    g = data.get("global", {})
    global_cfg = GlobalConfig(
        wait_after_load_seconds=g.get("wait_after_load_seconds", 5),
        animation_detection_threshold=g.get("animation_detection_threshold", 0.5),
    )

    s = data["s3"]
    s3_cfg = S3Config(
        bucket=s["bucket"],
        prefix=s.get("prefix", "windy-capture"),
    )

    categories = []
    for c in data.get("categories", []):
        categories.append(CategoryConfig(
            name=c["name"],
            url=c["url"],
            enabled=c.get("enabled", True),
            schedule_interval_minutes=c.get("schedule_interval_minutes", 5),
            animation_frames=c.get("animation_frames", 10),
            animation_frame_interval_ms=c.get("animation_frame_interval_ms", 500),
        ))

    return Config(global_=global_cfg, s3=s3_cfg, categories=categories)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add config.yaml src/config.py tests/test_config.py
git commit -m "feat: config loader with multi-category yaml support"
```

---

## Task 3: S3 Uploader

**Files:**
- Create: `src/uploader.py`
- Create: `tests/test_uploader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_uploader.py
import pytest
from unittest.mock import MagicMock, patch
from src.uploader import S3Uploader


@pytest.fixture
def uploader():
    with patch("src.uploader.boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        u = S3Uploader(bucket="test-bucket", prefix="windy-capture")
        u._mock_client = mock_client
        yield u


def test_upload_static_puts_object(uploader):
    uploader.upload_static(b"fake-image-data", category="radar", timestamp="14-00-00")
    uploader._mock_client.put_object.assert_called_once()
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Body"] == b"fake-image-data"
    assert call_kwargs["ContentType"] == "image/jpeg"


def test_upload_static_key_contains_category_and_timestamp(uploader):
    uploader.upload_static(b"data", category="radar", timestamp="14-00-00")
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "windy-capture" in key
    assert "radar" in key
    assert "14-00-00_static.jpg" in key


def test_upload_frame_key_format(uploader):
    uploader.upload_frame(b"data", category="satellite", timestamp="09-30-00", frame_num=3)
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "satellite" in key
    assert "09-30-00_frame_003.jpg" in key


def test_upload_frame_zero_padded(uploader):
    uploader.upload_frame(b"data", category="wind", timestamp="00-05-00", frame_num=1)
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "00-05-00_frame_001.jpg" in key


def test_s3_key_includes_date_folder(uploader):
    with patch("src.uploader.datetime") as mock_dt:
        from datetime import datetime, timezone
        mock_dt.now.return_value = datetime(2026, 4, 10, 14, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.side_effect = lambda tz=None: datetime(2026, 4, 10, 14, 0, 0, tzinfo=timezone.utc)
        uploader.upload_static(b"data", category="radar", timestamp="14-00-00")
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "2026-04-10" in key
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_uploader.py -v
```

Expected: `ImportError` — `src.uploader` doesn't exist yet.

- [ ] **Step 3: Implement `src/uploader.py`**

```python
import boto3
from datetime import datetime, timezone


class S3Uploader:
    def __init__(self, bucket: str, prefix: str):
        self.bucket = bucket
        self.prefix = prefix
        self.client = boto3.client("s3")

    def _make_key(self, category: str, filename: str) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"{self.prefix}/{category}/{date_str}/{filename}"

    def _put(self, data: bytes, key: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="image/jpeg",
        )
        return key

    def upload_static(self, data: bytes, category: str, timestamp: str) -> str:
        key = self._make_key(category, f"{timestamp}_static.jpg")
        return self._put(data, key)

    def upload_frame(self, data: bytes, category: str, timestamp: str, frame_num: int) -> str:
        key = self._make_key(category, f"{timestamp}_frame_{frame_num:03d}.jpg")
        return self._put(data, key)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_uploader.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uploader.py tests/test_uploader.py
git commit -m "feat: S3 uploader with category/date/timestamp key structure"
```

---

## Task 4: Animation Detection

**Files:**
- Create: `src/animation.py`
- Create: `tests/test_animation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_animation.py
import asyncio
import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image
import numpy as np
from src.animation import compute_pixel_diff_ratio, is_animated, capture_burst_frames


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

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(side_effect=[static_img, moving_img])

    mock_page = MagicMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    result = await is_animated(mock_page, threshold=0.5)
    assert result is True


@pytest.mark.asyncio
async def test_is_animated_returns_false_when_diff_below_threshold():
    static_img = make_image_bytes((100, 100, 100))

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(side_effect=[static_img, static_img])

    mock_page = MagicMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    result = await is_animated(mock_page, threshold=0.5)
    assert result is False


@pytest.mark.asyncio
async def test_capture_burst_frames_returns_correct_count():
    frame = make_image_bytes((50, 100, 150))

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(return_value=frame)

    mock_page = MagicMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    frames = await capture_burst_frames(mock_page, num_frames=5, interval_ms=10)
    assert len(frames) == 5
    assert all(isinstance(f, bytes) for f in frames)


@pytest.mark.asyncio
async def test_capture_burst_frames_calls_locator_correctly():
    frame = make_image_bytes((0, 0, 0))

    mock_locator = MagicMock()
    mock_locator.screenshot = AsyncMock(return_value=frame)

    mock_page = MagicMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    await capture_burst_frames(mock_page, num_frames=3, interval_ms=10)
    assert mock_page.locator.call_count == 3
    for call in mock_page.locator.call_args_list:
        assert call[0][0] == "canvas#map"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_animation.py -v
```

Expected: `ImportError` — `src.animation` doesn't exist yet.

- [ ] **Step 3: Implement `src/animation.py`**

```python
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
    return ratio > threshold


async def capture_burst_frames(page, num_frames: int, interval_ms: int) -> List[bytes]:
    """Capture num_frames screenshots with interval_ms between each."""
    frames = []
    for _ in range(num_frames):
        frame = await page.locator("canvas#map").screenshot()
        frames.append(frame)
        await asyncio.sleep(interval_ms / 1000.0)
    return frames
```

- [ ] **Step 4: Add `asyncio_mode` to `pytest.ini` (or `pyproject.toml`) so async tests work**

Create `pytest.ini` in the project root:

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_animation.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/animation.py tests/test_animation.py pytest.ini
git commit -m "feat: animation detection and burst frame capture"
```

---

## Task 5: Capture Worker

**Files:**
- Create: `src/capture.py`
- Create: `tests/test_capture.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_capture.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_capture.py -v
```

Expected: `ImportError` — `src.capture` doesn't exist yet.

- [ ] **Step 3: Implement `src/capture.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_capture.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capture.py tests/test_capture.py
git commit -m "feat: playwright capture worker with animation detection"
```

---

## Task 6: Scheduler

**Files:**
- Create: `src/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scheduler.py
import pytest
from unittest.mock import MagicMock, patch
from src.config import Config, GlobalConfig, S3Config, CategoryConfig
from src.scheduler import build_scheduler


def make_config(categories):
    return Config(
        global_=GlobalConfig(wait_after_load_seconds=5, animation_detection_threshold=0.5),
        s3=S3Config(bucket="b", prefix="p"),
        categories=categories,
    )


def test_enabled_categories_get_jobs():
    config = make_config([
        CategoryConfig(name="radar", url="https://windy.com/radar", enabled=True, schedule_interval_minutes=5, animation_frames=10, animation_frame_interval_ms=500),
        CategoryConfig(name="satellite", url="https://windy.com/sat", enabled=True, schedule_interval_minutes=10, animation_frames=8, animation_frame_interval_ms=600),
    ])
    mock_browser = MagicMock()
    mock_uploader = MagicMock()

    scheduler = build_scheduler(config, mock_browser, mock_uploader)
    job_ids = [job.id for job in scheduler.get_jobs()]
    assert "capture_radar" in job_ids
    assert "capture_satellite" in job_ids
    scheduler.shutdown(wait=False)


def test_disabled_categories_are_skipped():
    config = make_config([
        CategoryConfig(name="radar", url="https://windy.com/radar", enabled=True, schedule_interval_minutes=5, animation_frames=10, animation_frame_interval_ms=500),
        CategoryConfig(name="wind", url="https://windy.com/wind", enabled=False, schedule_interval_minutes=5, animation_frames=10, animation_frame_interval_ms=500),
    ])
    mock_browser = MagicMock()
    mock_uploader = MagicMock()

    scheduler = build_scheduler(config, mock_browser, mock_uploader)
    job_ids = [job.id for job in scheduler.get_jobs()]
    assert "capture_radar" in job_ids
    assert "capture_wind" not in job_ids
    scheduler.shutdown(wait=False)


def test_job_interval_matches_category_config():
    config = make_config([
        CategoryConfig(name="radar", url="https://windy.com/radar", enabled=True, schedule_interval_minutes=7, animation_frames=10, animation_frame_interval_ms=500),
    ])
    mock_browser = MagicMock()
    mock_uploader = MagicMock()

    scheduler = build_scheduler(config, mock_browser, mock_uploader)
    job = scheduler.get_job("capture_radar")
    # APScheduler stores interval in trigger fields
    trigger = job.trigger
    assert trigger.interval.total_seconds() == 7 * 60
    scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scheduler.py -v
```

Expected: `ImportError` — `src.scheduler` doesn't exist yet.

- [ ] **Step 3: Implement `src/scheduler.py`**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import Browser

from src.capture import capture_category
from src.config import Config
from src.uploader import S3Uploader


def build_scheduler(
    config: Config,
    browser: Browser,
    uploader: S3Uploader,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    for category in config.categories:
        if not category.enabled:
            continue
        scheduler.add_job(
            capture_category,
            trigger="interval",
            minutes=category.schedule_interval_minutes,
            args=[browser, category, config.global_, uploader],
            id=f"capture_{category.name}",
            max_instances=1,
        )

    return scheduler
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scheduler.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/scheduler.py tests/test_scheduler.py
git commit -m "feat: APScheduler with per-category async jobs"
```

---

## Task 7: Entry Point

**Files:**
- Create: `src/main.py`

No unit tests for `main.py` — it's pure orchestration. Verification is done by running the service.

- [ ] **Step 1: Implement `src/main.py`**

```python
import asyncio
import logging

from playwright.async_api import async_playwright

from src.config import load_config
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
    logger.info(
        "Categories: %s",
        [c.name for c in config.categories if c.enabled],
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        logger.info("Browser launched")
        try:
            scheduler = build_scheduler(config, browser, uploader)
            scheduler.start()
            logger.info("Scheduler started. Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down scheduler...")
            scheduler.shutdown()
        finally:
            await browser.close()
            logger.info("Browser closed")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke test — verify it starts without error (requires real Playwright + valid config)**

Edit `config.yaml` temporarily to set `schedule_interval_minutes: 60` for all categories (so jobs don't fire immediately), then:

```bash
python src/main.py
```

Expected: logs show "Browser launched" and "Scheduler started". No errors. Ctrl+C to exit.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: entry point with browser lifecycle and scheduler startup"
```

---

## Task 8: Docker Packaging

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
.env
.git
__pycache__
*.pyc
*.pyo
.pytest_cache
tests/
docs/
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config.yaml .

CMD ["python", "src/main.py"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  windy-capture:
    build: .
    env_file: .env
    volumes:
      - ./config.yaml:/app/config.yaml
    restart: unless-stopped
```

- [ ] **Step 4: Create `.env` from `.env.example` and fill in real credentials**

```bash
cp .env.example .env
# Edit .env with real AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
```

`.env` must NOT be committed (it's in `.dockerignore` — also add to `.gitignore`).

- [ ] **Step 5: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 6: Build and verify the image**

```bash
docker compose build
```

Expected: build completes without errors. Playwright and Chromium are installed inside the image.

- [ ] **Step 7: Run the container locally**

```bash
docker compose up
```

Expected: logs show "Browser launched" and "Scheduler started". No errors. Ctrl+C to stop.

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore .gitignore
git commit -m "feat: Docker packaging for local and remote deployment"
```

---

## Task 9: End-to-End Smoke Test

Verify the full pipeline works against real Windy.com and a real S3 bucket.

- [ ] **Step 1: Set a short interval for one category to trigger quickly**

Edit `config.yaml`, change one category's `schedule_interval_minutes` to `1` for testing. Disable all other categories (`enabled: false`).

- [ ] **Step 2: Run the service**

```bash
docker compose up
```

Wait ~1 minute for the first job to fire.

- [ ] **Step 3: Verify files appear in S3**

```bash
aws s3 ls s3://your-bucket/windy-capture/ --recursive
```

Expected: at least one `_static.jpg` file. If Windy's animation was detected, also `_frame_001.jpg`, `_frame_002.jpg`, etc.

- [ ] **Step 4: Download and inspect a captured frame**

```bash
aws s3 cp s3://your-bucket/windy-capture/radar/$(date +%Y-%m-%d)/$(ls ...) ./test_output.jpg
open test_output.jpg
```

Expected: the image shows only the Windy map canvas, no browser chrome.

- [ ] **Step 5: Restore `config.yaml` to production settings**

Re-enable all categories and set production intervals. Commit.

```bash
git add config.yaml
git commit -m "chore: restore production config after smoke test"
```

---

## Self-Review Notes

- **Spec coverage:** All sections covered — multi-category config (Task 2), S3 layout (Task 3), animation detection (Task 4), capture flow (Task 5), scheduler (Task 6), browser resource management (shared browser via `main.py`+`capture.py`), Docker (Task 8), E2E (Task 9).
- **No placeholders:** All steps include real code or exact commands.
- **Type consistency:** `CategoryConfig`, `GlobalConfig`, `S3Uploader`, `capture_category`, `build_scheduler` — names are consistent across all tasks.
- **canvas#map selector:** The real Windy DOM must be verified during Task 9 smoke test. If the selector doesn't match, inspect the page with `page.content()` and update `src/animation.py` and `src/capture.py` accordingly.
