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
