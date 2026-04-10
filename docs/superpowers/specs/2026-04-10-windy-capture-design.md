# Windy Capture Service — Design Spec

**Date:** 2026-04-10
**Status:** Approved

---

## Overview

A Python-based scheduled service that periodically captures map screenshots from Windy.com using a headless browser, detects animation, captures multiple frames when animation is present, and uploads results to AWS S3. Packaged as a Docker container for consistent local and remote deployment.

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Docker Container              │
│                                         │
│  ┌──────────┐    ┌───────────────────┐  │
│  │ Scheduler│───▶│  Capture Worker   │  │
│  │(APScheduler)  │                   │  │
│  └──────────┘    │ 1. Open Windy URL │  │
│                  │ 2. Wait for render │  │
│                  │ 3. Locate canvas  │  │
│                  │ 4. Capture static │  │
│                  │ 5. Detect anim.   │  │
│                  │ 6. Burst frames   │  │
│                  └────────┬──────────┘  │
│                           │             │
│                  ┌────────▼──────────┐  │
│                  │   S3 Uploader     │  │
│                  │ (boto3)           │  │
│                  └───────────────────┘  │
└─────────────────────────────────────────┘
```

### Directory Structure

```
windy-capture/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── config.yaml
├── requirements.txt
├── src/
│   ├── main.py          # Entry point, starts scheduler
│   ├── scheduler.py     # APScheduler: registers one job per category
│   ├── capture.py       # Playwright screenshot logic
│   ├── animation.py     # Animation detection + burst frame capture
│   └── uploader.py      # S3 upload via boto3
├── tests/
│   └── test_capture.py
└── docs/
    └── superpowers/specs/
        └── 2026-04-10-windy-capture-design.md
```

---

## Multi-Category Configuration

Each "category" represents a distinct Windy view (radar, satellite, wind, etc.) with its own URL, coordinates, schedule, and frame settings. Categories are defined in `config.yaml`.

```yaml
global:
  wait_after_load_seconds: 5
  animation_detection_threshold: 0.5  # pixel diff percentage

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

All URL parameters (including coordinates and zoom level) are fully configurable per category. Each category can override the global `schedule_interval_minutes`.

---

## Capture Logic

### Map Area Isolation

Windy renders its map on a `<canvas>` element. The capture worker uses Playwright's element screenshot (`locator("canvas#map").screenshot()`) to capture only the map region, excluding menus and UI chrome.

### Wait Strategy

1. `wait_until="networkidle"` — page and assets loaded
2. `wait_for_selector("canvas#map")` — canvas present in DOM
3. Configurable sleep (`wait_after_load_seconds`) — animation fully initialized

### Animation Detection

Two screenshots are taken 300ms apart. Pillow computes the pixel difference ratio. If the ratio exceeds `animation_detection_threshold`, the page is classified as animated.

### Frame Capture Behavior

| Condition   | Output                                              |
|-------------|-----------------------------------------------------|
| No animation | 1 static frame uploaded                            |
| Animation   | 1 static frame + N burst frames uploaded            |

Burst frame count (`animation_frames`) and interval (`animation_frame_interval_ms`) are configurable per category.

---

## Browser Resource Management

A **single shared Chromium process** is maintained for the lifetime of the service. Each capture job creates a new `BrowserContext` (isolated cookies and cache), opens a `Page`, performs capture, then closes the context. This keeps memory usage to ~300MB regardless of category count, versus 200–500MB per category with separate browser instances.

Scheduling is handled with `asyncio` — jobs run concurrently but share the one browser process.

---

## S3 Storage Layout

```
s3://{bucket}/{prefix}/
├── radar/
│   └── 2026-04-10/
│       ├── 14-00-00_static.jpg
│       ├── 14-00-00_frame_001.jpg
│       ├── 14-00-00_frame_002.jpg
│       └── ...
├── satellite/
│   └── 2026-04-10/
│       ├── 14-00-00_static.jpg
│       └── ...
└── wind/
    └── 2026-04-10/
        └── ...
```

File naming: `HH-MM-SS_static.jpg` and `HH-MM-SS_frame_NNN.jpg`. Timestamps are UTC.

---

## Docker & Deployment

### Dockerfile

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
COPY config.yaml .
CMD ["python", "src/main.py"]
```

### docker-compose.yml

```yaml
services:
  windy-capture:
    build: .
    env_file: .env
    volumes:
      - ./config.yaml:/app/config.yaml
    restart: unless-stopped
```

`config.yaml` is mounted as a volume so categories and intervals can be updated without rebuilding the image.

### Environment Variables (.env)

```env
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_DEFAULT_REGION=us-east-1
```

AWS credentials are injected via environment variables and never committed to version control.

### Running

```bash
# Local testing
docker compose up

# Remote server (background)
docker compose up -d
```

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Headless browser control |
| `APScheduler` | Per-category async scheduling |
| `boto3` | S3 upload |
| `Pillow` | Pixel diff for animation detection |
| `pyyaml` | Config file parsing |

---

## Out of Scope (this project)

- Playback / viewer UI — separate project, reads from same S3 bucket
- Alerting / anomaly detection — future extension
- Authentication / login to Windy — not required for public URLs
