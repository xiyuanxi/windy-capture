import pytest
import tempfile
import os
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


def test_missing_s3_section_raises_error():
    yaml_content = """
global:
  wait_after_load_seconds: 5
  animation_detection_threshold: 0.5
categories:
  - name: wind
    url: "https://www.windy.com/wind"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        with pytest.raises(ValueError, match="s3"):
            load_config(path)
    finally:
        os.unlink(path)


def test_category_missing_url_raises_error():
    yaml_content = """
global:
  wait_after_load_seconds: 5
  animation_detection_threshold: 0.5
s3:
  bucket: "b"
  prefix: "p"
categories:
  - name: radar
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        with pytest.raises(ValueError, match="url"):
            load_config(path)
    finally:
        os.unlink(path)
