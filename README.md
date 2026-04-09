# 📡 WebRTC Screen Streamer

Headless screen streaming from Fedora (Wayland / PipeWire) to any Chromium-based browser via WebRTC.
Hardware-accelerated H.264 encoding with hard CBR bitrate cap and sub-100 ms latency over local 5 GHz Wi-Fi.

## Features

- **Hardware encoding** — NVIDIA NVENC, AMD/Intel VA-API, software x264 fallback
- **Auto-detection** — picks the best available GPU encoder automatically
- **Ultra-low latency** — CBR, zero-latency tune, no B-frames, 1-frame VBV
- **Wayland native** — PipeWire capture via XDG ScreenCast portal (monitor or window)
- **Single-file viewer** — static HTML/JS page, works on Smart TVs (Samsung Tizen, etc.)
- **TUI** — Textual-based launcher with presets, encoder selector, real-time log
- **Simple signaling** — aiohttp WebSocket, no external TURN/STUN needed on LAN

## Requirements

| Component     | Details                                           |
|---------------|---------------------------------------------------|
| **OS**        | Fedora 40+ (Wayland session, PipeWire)            |
| **GPU**       | NVIDIA (NVENC), AMD (VA-API), Intel (VA-API), or CPU |
| **GStreamer**  | 1.22+ with `webrtcbin`, `pipewiresrc`, encoder plugins |
| **Python**    | 3.11+                                             |
| **Browser**   | Any Chromium-based (Chrome, Edge, Tizen TV, etc.) |

## Quick Start

```bash
# 1. Clone
git clone <repo-url> && cd stream

# 2. Install system deps + Python venv
./install.sh

# 3. Stream!
uv run stream --portal              # pick monitor
uv run stream --window              # pick window
uv run stream --test                # SMPTE test pattern
uv run stream-tui                   # TUI launcher
```

Then open `http://<your-ip>:8888` in the browser / TV.

## Usage

### CLI

```
uv run stream [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--portal` | — | Pick source via XDG ScreenCast portal |
| `--window` | — | Portal shows windows instead of monitors |
| `--pw-node ID` | — | PipeWire node ID (skips portal) |
| `--test` | — | SMPTE test pattern |
| `--bitrate KBPS` | 6000 | Target CBR bitrate (kbit/s) |
| `--fps N` | 30 | Capture frame rate |
| `--scale WxH` | 1280x720 | Output resolution (`none` to disable) |
| `--encoder ID` | auto | Force encoder: `nvenc`, `vaapi`, `x264` |
| `--host ADDR` | 0.0.0.0 | Bind address |
| `--port PORT` | 8888 | HTTP port |
| `--stun URI` | — | STUN server (not needed on LAN) |

### TUI

```
uv run stream-tui
```

Hotkeys: **S** Start · **X** Stop · **Q** Quit · **C** Clear log

### Browser Viewer

Open `http://<ip>:8888` in Chromium. The page auto-connects via WebSocket, shows the stream fullscreen, and overlays real-time stats (bitrate, FPS, jitter, RTT, packet loss).

## Presets

| Preset | Resolution | FPS | Bitrate |
|--------|-----------|-----|---------|
| Gaming 720p 30fps | 1280×720 | 30 | 6 Mbps |
| Gaming 720p 60fps | 1280×720 | 60 | 10 Mbps |
| Gaming 1080p 30fps | 1920×1080 | 30 | 10 Mbps |
| Gaming 1080p 60fps | 1920×1080 | 60 | 15 Mbps |
| Quality 1080p 30fps | 1920×1080 | 30 | 20 Mbps |
| Quality 1080p 60fps | 1920×1080 | 60 | 25 Mbps |
| Custom | — | — | — |

## Encoder Support

| Encoder | GPU | GStreamer Element | Plugin Package |
|---------|-----|-------------------|----------------|
| NVENC | NVIDIA | `nvh264enc` | `gstreamer1-plugins-bad-freeworld` (RPM Fusion) |
| VA-API | AMD / Intel | `vaapih264enc` | `gstreamer1-vaapi` |
| x264 | CPU (slow!) | `x264enc` | `gstreamer1-plugins-ugly` |

Auto-detection priority: NVENC → VA-API → x264.

## Architecture

```
src/webrtc_stream/
├── __init__.py      # empty
├── config.py        # StreamConfig dataclass, PRESETS, SourceType enum
├── encoders.py      # EncoderInfo, ENCODERS registry, detect/build
├── pipeline.py      # GStreamer Pipeline (build/start/stop, WebRTC callbacks)
├── portal.py        # XDG ScreenCast portal (Wayland capture)
├── server.py        # SignalingServer (aiohttp HTTP + WebSocket)
├── cli.py           # argparse CLI entry-point
└── tui.py           # Textual TUI app
```

Entry-points (defined in `pyproject.toml`):
- `stream` → `webrtc_stream.cli:main`
- `stream-tui` → `webrtc_stream.tui:main`

## License

MIT
