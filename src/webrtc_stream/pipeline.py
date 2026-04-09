"""GStreamer WebRTC pipeline: build, start, stop, signaling callbacks."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")
from gi.repository import Gst, GstSdp, GstWebRTC  # noqa: E402

from webrtc_stream.config import SourceType, StreamConfig  # noqa: E402
from webrtc_stream.encoders import EncoderInfo, build_encoder_pipeline  # noqa: E402

if TYPE_CHECKING:
    from aiohttp.web import WebSocketResponse

    from webrtc_stream.portal import CaptureSource

LOG = logging.getLogger(__name__)


class Pipeline:
    """pipewiresrc → HW H.264 (CBR) → webrtcbin — single viewer."""

    def __init__(
        self,
        config: StreamConfig,
        encoder: EncoderInfo,
        capture: CaptureSource | None = None,
    ) -> None:
        self._config = config
        self._encoder = encoder
        self._capture = capture
        self.pipe: Gst.Pipeline | None = None
        self.webrtc: Gst.Element | None = None
        self._ws: WebSocketResponse | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, ws: WebSocketResponse | None, loop: asyncio.AbstractEventLoop | None) -> None:
        """Attach the active WebSocket + asyncio loop for signaling."""
        self._ws = ws
        self._loop = loop

    # ── build / start / stop ─────────────────────────────────────────

    def build(self) -> None:
        cfg = self._config
        src = self._source_element()
        enc_segment = build_encoder_pipeline(self._encoder, cfg.bitrate, cfg.fps)
        wb = self._webrtcbin_element()

        parts = [
            src,
            f"video/x-raw,format=BGRx,max-framerate={cfg.fps}/1",
            "videorate drop-only=true skip-to-first=true",
            f"video/x-raw,framerate={cfg.fps}/1",
        ]

        if cfg.scale:
            parts += [
                "videoscale method=bilinear",
                f"video/x-raw,width={cfg.scale[0]},height={cfg.scale[1]}",
            ]

        parts += [
            "queue max-size-buffers=1 max-size-time=0 max-size-bytes=0 leaky=downstream",
            enc_segment,
            "h264parse config-interval=-1",
            "rtph264pay config-interval=-1 aggregate-mode=zero-latency pt=96 mtu=1400",
            "application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000",
            wb,
        ]

        desc = " ! ".join(parts)
        LOG.info("Pipeline:\n  %s", desc.replace(" ! ", "\n  ! "))

        self.pipe = Gst.parse_launch(desc)
        self.webrtc = self.pipe.get_by_name("webrtc")

        self.webrtc.connect("on-negotiation-needed", self._on_negotiation_needed)
        self.webrtc.connect("on-ice-candidate", self._on_ice_candidate)

        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_error)
        bus.connect("message::eos", lambda *_: LOG.warning("EOS received"))

    def start(self) -> None:
        if self.pipe:
            ret = self.pipe.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                LOG.error("Pipeline failed to start — check encoder / pipewiresrc")

    def stop(self) -> None:
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe = None
            self.webrtc = None

    # ── source element ───────────────────────────────────────────────

    def _source_element(self) -> str:
        cfg = self._config
        if cfg.source_type == SourceType.TEST:
            return "videotestsrc is-live=true pattern=smpte"

        if self._capture:
            return (
                f"pipewiresrc fd={self._capture.fd} "
                f"path={self._capture.node_id} do-timestamp=true "
                "keepalive-time=1000 resend-last=true"
            )

        if cfg.pw_node is not None:
            return (
                f"pipewiresrc path={cfg.pw_node} do-timestamp=true "
                "keepalive-time=1000 resend-last=true"
            )

        return "pipewiresrc do-timestamp=true keepalive-time=1000 resend-last=true"

    def _webrtcbin_element(self) -> str:
        wb = "webrtcbin name=webrtc bundle-policy=max-bundle latency=0"
        if self._config.stun:
            wb += f" stun-server={self._config.stun}"
        return wb

    # ── WebRTC callbacks (run on GLib thread) ────────────────────────

    def _on_negotiation_needed(self, _element: Gst.Element) -> None:
        LOG.info("Negotiation needed — creating offer")
        promise = Gst.Promise.new_with_change_func(self._on_offer_created)
        self.webrtc.emit("create-offer", None, promise)

    def _on_offer_created(self, promise: Gst.Promise) -> None:
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")

        p = Gst.Promise.new()
        self.webrtc.emit("set-local-description", offer, p)
        p.interrupt()

        sdp_text = offer.sdp.as_text()
        LOG.info("Offer ready (%d bytes)", len(sdp_text))
        self._ws_send({"type": "offer", "sdp": sdp_text})

    def _on_ice_candidate(self, _element: Gst.Element, mline_index: int, candidate: str) -> None:
        self._ws_send(
            {
                "type": "ice",
                "sdpMLineIndex": mline_index,
                "candidate": candidate,
            }
        )

    # ── incoming signaling messages ──────────────────────────────────

    def handle_answer(self, sdp_text: str) -> None:
        _, sdp_msg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(bytes(sdp_text.encode()), sdp_msg)
        answer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.ANSWER,
            sdp_msg,
        )
        p = Gst.Promise.new()
        self.webrtc.emit("set-remote-description", answer, p)
        p.interrupt()
        LOG.info("Remote answer applied")

    def handle_ice(self, mline_index: int, candidate: str) -> None:
        if self.webrtc:
            self.webrtc.emit("add-ice-candidate", mline_index, candidate)

    # ── helpers ──────────────────────────────────────────────────────

    def _ws_send(self, obj: dict) -> None:
        if self._ws and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._ws.send_str(json.dumps(obj)),
                self._loop,
            )

    def _on_error(self, _bus: Gst.Bus, msg: Gst.Message) -> None:
        err, dbg = msg.parse_error()
        LOG.error("GStreamer: %s\n%s", err.message, dbg)
