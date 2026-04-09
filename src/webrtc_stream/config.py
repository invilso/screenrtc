"""Streaming configuration: dataclass, presets, enums."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceType(Enum):
    """Capture source kind."""

    PORTAL = "portal"
    WINDOW = "window"
    TEST = "test"
    PW_NODE = "pw-node"
    DEFAULT = "default"


@dataclass
class StreamConfig:
    """Validated streaming parameters — single source of truth."""

    bitrate: int = 6000
    fps: int = 30
    scale: tuple[int, int] | None = (1280, 720)
    encoder_id: str | None = None
    source_type: SourceType = SourceType.PORTAL
    pw_node: int | None = None
    host: str = "0.0.0.0"
    port: int = 8888
    stun: str | None = None

    def __post_init__(self) -> None:
        if self.bitrate <= 0:
            raise ValueError(f"bitrate must be > 0, got {self.bitrate}")
        if not 1 <= self.fps <= 240:
            raise ValueError(f"fps must be in [1..240], got {self.fps}")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"port must be in [1..65535], got {self.port}")
        if self.scale is not None and (
            len(self.scale) != 2 or self.scale[0] <= 0 or self.scale[1] <= 0
        ):
            raise ValueError(f"scale must be (width, height) > 0, got {self.scale}")


def parse_scale(raw: str) -> tuple[int, int] | None:
    """Parse 'WxH' string into (width, height) or None if 'none'."""
    if not raw or raw.lower() == "none":
        return None
    parts = raw.split("x")
    if len(parts) != 2:
        raise ValueError(f"scale must be WxH or 'none', got '{raw}'")
    return (int(parts[0]), int(parts[1]))


PRESETS: dict[str, dict] = {
    "gaming_720p30": {
        "label": "🎮 Gaming 720p 30fps",
        "desc": "Low latency, 720p30, 6 Mbps",
        "bitrate": 6000,
        "fps": 30,
        "scale": "1280x720",
    },
    "gaming_720p60": {
        "label": "🎮 Gaming 720p 60fps",
        "desc": "Smooth gaming, 720p60, 10 Mbps",
        "bitrate": 10000,
        "fps": 60,
        "scale": "1280x720",
    },
    "gaming_1080p30": {
        "label": "🎮 Gaming 1080p 30fps",
        "desc": "Low latency, 1080p30, 10 Mbps",
        "bitrate": 10000,
        "fps": 30,
        "scale": "none",
    },
    "gaming_1080p60": {
        "label": "🎮 Gaming 1080p 60fps",
        "desc": "Smooth gaming, 1080p60, 15 Mbps",
        "bitrate": 15000,
        "fps": 60,
        "scale": "none",
    },
    "quality_1080p30": {
        "label": "🎬 Quality 1080p 30fps",
        "desc": "Higher quality, 1080p30, 20 Mbps",
        "bitrate": 20000,
        "fps": 30,
        "scale": "none",
    },
    "quality_1080p60": {
        "label": "🎬 Quality 1080p 60fps",
        "desc": "Best quality, 1080p60, 25 Mbps",
        "bitrate": 25000,
        "fps": 60,
        "scale": "none",
    },
    "custom": {
        "label": "⚙️  Custom",
        "desc": "Set your own parameters",
        "bitrate": 6000,
        "fps": 30,
        "scale": "1280x720",
    },
}
