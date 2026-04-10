import pytest
from unittest.mock import MagicMock
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
