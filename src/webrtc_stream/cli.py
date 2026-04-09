"""CLI entry-point for the WebRTC screen streamer."""

from __future__ import annotations

import argparse
import logging
import threading

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from webrtc_stream.config import SourceType, StreamConfig, parse_scale  # noqa: E402
from webrtc_stream.encoders import detect_encoder  # noqa: E402
from webrtc_stream.pipeline import Pipeline  # noqa: E402
from webrtc_stream.portal import CaptureSource, portal_screencast  # noqa: E402
from webrtc_stream.server import SignalingServer  # noqa: E402

LOG = logging.getLogger("webrtc_stream")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="WebRTC screen streamer — HW H.264 CBR, <100 ms latency",
    )

    enc = ap.add_argument_group("encoding")
    enc.add_argument(
        "--bitrate",
        type=int,
        default=6000,
        help="Target CBR bitrate, kbit/s (default: 6000)",
    )
    enc.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Capture frame rate (default: 30)",
    )
    enc.add_argument(
        "--scale",
        type=str,
        default="1280x720",
        help="Output resolution WxH (default: 1280x720, 'none' to disable)",
    )
    enc.add_argument(
        "--encoder",
        type=str,
        default=None,
        choices=["nvenc", "vaapi", "x264"],
        help="Force encoder (default: auto-detect)",
    )

    src = ap.add_argument_group("source")
    src.add_argument(
        "--portal",
        action="store_true",
        help="Pick source via XDG ScreenCast portal",
    )
    src.add_argument(
        "--window",
        action="store_true",
        help="Portal shows windows instead of monitors",
    )
    src.add_argument(
        "--pw-node",
        type=int,
        default=None,
        help="PipeWire node ID (skips portal)",
    )
    src.add_argument(
        "--test",
        action="store_true",
        help="Use SMPTE test pattern instead of capture",
    )

    net = ap.add_argument_group("network")
    net.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    net.add_argument(
        "--port",
        type=int,
        default=8888,
        help="HTTP port (default: 8888)",
    )
    net.add_argument(
        "--stun",
        default=None,
        help="STUN URI, e.g. stun://stun.l.google.com:19302 (not needed on LAN)",
    )

    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    Gst.init(None)

    # ── detect encoder ───────────────────────────────────────────────
    encoder = detect_encoder(args.encoder)
    LOG.info("Encoder: %s (%s)", encoder.name, encoder.element)

    # ── verify critical elements ─────────────────────────────────────
    for el in ("webrtcbin", "pipewiresrc"):
        if not Gst.ElementFactory.find(el):
            LOG.warning(
                "GStreamer element '%s' not found — run install.sh or check RPM Fusion",
                el,
            )

    # ── resolve source type ──────────────────────────────────────────
    if args.test:
        source_type = SourceType.TEST
    elif args.window:
        source_type = SourceType.WINDOW
    elif args.portal:
        source_type = SourceType.PORTAL
    elif args.pw_node is not None:
        source_type = SourceType.PW_NODE
    else:
        source_type = SourceType.DEFAULT

    # ── capture via portal if needed ─────────────────────────────────
    capture: CaptureSource | None = None
    if source_type in (SourceType.PORTAL, SourceType.WINDOW):
        ctype = 2 if source_type == SourceType.WINDOW else 1
        capture = portal_screencast(capture_type=ctype)

    if source_type == SourceType.DEFAULT:
        LOG.info(
            "No --portal / --pw-node / --test specified; "
            "pipewiresrc will use the default PipeWire node",
        )

    # ── build config ─────────────────────────────────────────────────
    config = StreamConfig(
        bitrate=args.bitrate,
        fps=args.fps,
        scale=parse_scale(args.scale),
        encoder_id=encoder.id,
        source_type=source_type,
        pw_node=args.pw_node,
        host=args.host,
        port=args.port,
        stun=args.stun,
    )

    pipeline = Pipeline(config, encoder, capture)

    # GLib main-loop in a background thread (drives GStreamer signals)
    glib_loop = GLib.MainLoop()
    threading.Thread(target=glib_loop.run, daemon=True).start()

    server = SignalingServer(pipeline, config.host, config.port)
    try:
        server.run()
    finally:
        GLib.idle_add(pipeline.stop)
        glib_loop.quit()
