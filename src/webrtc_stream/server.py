"""HTTP + WebSocket signaling server for WebRTC pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web
from gi.repository import GLib

from webrtc_stream.pipeline import Pipeline

LOG = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class SignalingServer:
    """aiohttp server: serves static viewer + WebSocket signaling."""

    def __init__(self, pipeline: Pipeline, host: str, port: int) -> None:
        self._pipeline = pipeline
        self._host = host
        self._port = port

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        LOG.info("Client connected: %s", request.remote)

        loop = asyncio.get_event_loop()
        self._pipeline.bind(ws, loop)

        def _restart() -> bool:
            self._pipeline.stop()
            self._pipeline.build()
            self._pipeline.start()
            return False

        GLib.idle_add(_restart)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                kind = data.get("type")
                if kind == "answer":
                    GLib.idle_add(self._pipeline.handle_answer, data["sdp"])
                elif kind == "ice" and data.get("candidate"):
                    GLib.idle_add(
                        self._pipeline.handle_ice,
                        data["sdpMLineIndex"],
                        data["candidate"],
                    )

        LOG.info("Client disconnected")
        GLib.idle_add(self._pipeline.stop)
        self._pipeline.bind(None, None)
        return ws

    def run(self) -> None:
        app = web.Application()
        app.router.add_get("/ws", self.ws_handler)
        app.router.add_get("/", lambda _: web.FileResponse(STATIC_DIR / "index.html"))
        app.router.add_static("/static/", STATIC_DIR)
        LOG.info("Listening on http://%s:%d", self._host, self._port)
        web.run_app(app, host=self._host, port=self._port, print=None)
