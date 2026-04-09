"""Hardware encoder registry, auto-detection, and GStreamer pipeline segments."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncoderInfo:
    """Description of a single H.264 encoder."""

    id: str
    name: str
    element: str
    required_elements: tuple[str, ...]


# Priority: NVENC > VA-API > software x264
ENCODERS: list[EncoderInfo] = [
    EncoderInfo(
        id="nvenc",
        name="NVIDIA NVENC",
        element="nvh264enc",
        required_elements=("nvh264enc", "cudaupload"),
    ),
    EncoderInfo(
        id="vaapi",
        name="VA-API (AMD/Intel)",
        element="vaapih264enc",
        required_elements=("vaapih264enc",),
    ),
    EncoderInfo(
        id="x264",
        name="Software x264 (slow!)",
        element="x264enc",
        required_elements=("x264enc",),
    ),
]


def detect_encoder(preferred: str | None = None) -> EncoderInfo:
    """Return the best available encoder. Optionally try *preferred* first."""
    if preferred:
        for enc in ENCODERS:
            if enc.id == preferred:
                if all(Gst.ElementFactory.find(e) for e in enc.required_elements):
                    LOG.info("Using requested encoder: %s", enc.name)
                    return enc
                LOG.warning("Requested encoder '%s' not available", preferred)
                break

    for enc in ENCODERS:
        if all(Gst.ElementFactory.find(e) for e in enc.required_elements):
            LOG.info("Auto-detected encoder: %s", enc.name)
            return enc

    LOG.error("No H.264 hardware encoder found! Install NVENC or VA-API plugins.")
    sys.exit(1)


def build_encoder_pipeline(encoder: EncoderInfo, bitrate: int, fps: int) -> str:
    """Return the '!'-joined GStreamer segment for encoding (upload + encoder)."""
    vbv = max(bitrate // fps, 100)

    if encoder.id == "nvenc":
        return (
            "cudaupload"
            " ! nvh264enc"
            " preset=p1"
            " tune=ultra-low-latency"
            " rc-mode=cbr"
            f" bitrate={bitrate}"
            f" max-bitrate={bitrate}"
            f" vbv-buffer-size={vbv}"
            f" gop-size={fps}"
            " bframes=0"
            " zerolatency=true"
            " aud=false"
            " qos=true"
        )

    if encoder.id == "vaapi":
        return (
            "videoconvert n-threads=4"
            " ! vaapih264enc"
            " rate-control=cbr"
            f" bitrate={bitrate}"
            f" keyframe-period={fps}"
            " tune=low-power"
            " quality-level=7"
            " cabac=true"
            " max-bframes=0"
            " qos=true"
        )

    # x264 (software fallback)
    return (
        "videoconvert n-threads=4"
        " ! x264enc"
        " speed-preset=ultrafast"
        " tune=zerolatency"
        f" bitrate={bitrate}"
        f" key-int-max={fps}"
        " bframes=0"
        " qos=true"
    )
