"""Textual TUI launcher for the WebRTC screen streamer."""

from __future__ import annotations

import signal
import socket
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Log,
    RadioButton,
    RadioSet,
    Rule,
    Select,
    Static,
)

from webrtc_stream.config import PRESETS

# ─── Helpers ─────────────────────────────────────────────────────────────


def _get_local_ips() -> list[str]:
    """Return non-loopback IPv4 addresses."""
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return sorted(set(ips)) or ["0.0.0.0"]


CSS = """
Screen {
    layout: vertical;
}

#main {
    layout: horizontal;
    height: 1fr;
}

#sidebar {
    width: 42;
    padding: 1 2;
    border-right: thick $accent;
}

#log-panel {
    width: 1fr;
    height: 1fr;
    padding: 1 2;
}

.section-title {
    text-style: bold;
    color: $text;
    margin-bottom: 1;
    height: auto;
}

.param-row {
    layout: horizontal;
    height: 3;
    margin-bottom: 0;
}

.param-label {
    width: 12;
    padding-top: 1;
    color: $text-muted;
}

.param-input {
    width: 1fr;
}

#status-bar {
    dock: bottom;
    height: 3;
    padding: 0 2;
    layout: horizontal;
    background: $surface;
    border-top: tall $accent;
}

#status-text {
    width: 1fr;
    padding-top: 1;
}

#url-display {
    width: auto;
    padding-top: 1;
    color: $success;
    text-style: bold;
}

#btn-row {
    layout: horizontal;
    height: 3;
    margin-top: 1;
}

#btn-start {
    width: 1fr;
    margin-right: 1;
}

#btn-stop {
    width: 1fr;
}

Button.start {
    background: $success;
}

Button.stop {
    background: $error;
}

#preset-select {
    margin-bottom: 1;
}

Log {
    border: round $accent;
    margin-top: 1;
    height: 1fr;
}

#client-info {
    height: 3;
    padding: 1;
    margin-top: 1;
    border: round $accent;
    color: $text;
}
"""


class StreamApp(App):
    """WebRTC Screen Streamer — TUI."""

    TITLE = "📡 WebRTC Stream"
    SUB_TITLE = "HW Encode → TV"
    CSS = CSS

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("s", "start_stream", "Start", show=True),
        Binding("x", "stop_stream", "Stop", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("c", "clear_log", "Clear Log", show=True),
    ]

    streaming: reactive[bool] = reactive(False)
    client_addr: reactive[str] = reactive("")
    _proc: subprocess.Popen | None = None
    _reader_thread: threading.Thread | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            with VerticalScroll(id="sidebar"):
                yield Label("Preset", classes="section-title")
                yield Select(
                    [(p["label"], k) for k, p in PRESETS.items()],
                    value="gaming_720p30",
                    id="preset-select",
                    allow_blank=False,
                )

                yield Rule()
                yield Label("Source", classes="section-title")
                with RadioSet(id="source-radio"):
                    yield RadioButton("Monitor", value=True, id="src-monitor")
                    yield RadioButton("Window", id="src-window")
                    yield RadioButton("Test pattern", id="src-test")

                yield Rule()
                yield Label("Encoder", classes="section-title")
                yield Select(
                    [
                        ("🔍 Auto-detect", "auto"),
                        ("🟢 NVIDIA NVENC", "nvenc"),
                        ("🔴 AMD/Intel VA-API", "vaapi"),
                        ("⚪ Software x264", "x264"),
                    ],
                    value="auto",
                    id="encoder-select",
                    allow_blank=False,
                )

                yield Rule()
                yield Label("Parameters", classes="section-title")

                with Horizontal(classes="param-row"):
                    yield Label("Bitrate", classes="param-label")
                    yield Input(
                        value="6000",
                        type="integer",
                        id="inp-bitrate",
                        classes="param-input",
                    )

                with Horizontal(classes="param-row"):
                    yield Label("FPS", classes="param-label")
                    yield Input(value="30", type="integer", id="inp-fps", classes="param-input")

                with Horizontal(classes="param-row"):
                    yield Label("Scale", classes="param-label")
                    yield Input(value="1280x720", id="inp-scale", classes="param-input")

                with Horizontal(classes="param-row"):
                    yield Label("Port", classes="param-label")
                    yield Input(
                        value="8888",
                        type="integer",
                        id="inp-port",
                        classes="param-input",
                    )

                with Horizontal(id="btn-row"):
                    yield Button(
                        "▶  Start",
                        id="btn-start",
                        variant="success",
                        classes="start",
                    )
                    yield Button(
                        "■  Stop",
                        id="btn-stop",
                        variant="error",
                        classes="stop",
                        disabled=True,
                    )

            with Vertical(id="log-panel"):
                yield Label("Stream Log", classes="section-title")
                yield Log(id="log", auto_scroll=True, max_lines=500)
                yield Static("No client connected", id="client-info")

        with Horizontal(id="status-bar"):
            yield Static("⏹  Idle", id="status-text")
            yield Static("", id="url-display")

        yield Footer()

    # ── Preset handling ──────────────────────────────────────────────

    @on(Select.Changed, "#preset-select")
    def on_preset_changed(self, event: Select.Changed) -> None:
        key = event.value
        if key == "custom":
            return
        preset = PRESETS[key]
        self.query_one("#inp-bitrate", Input).value = str(preset["bitrate"])
        self.query_one("#inp-fps", Input).value = str(preset["fps"])
        self.query_one("#inp-scale", Input).value = preset["scale"]

    # ── Buttons ──────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-start")
    def on_start_pressed(self) -> None:
        self.action_start_stream()

    @on(Button.Pressed, "#btn-stop")
    def on_stop_pressed(self) -> None:
        self.action_stop_stream()

    # ── Actions ──────────────────────────────────────────────────────

    def action_start_stream(self) -> None:
        if self.streaming:
            return
        self._launch_stream()

    def action_stop_stream(self) -> None:
        if not self.streaming:
            return
        self._kill_stream()

    def action_clear_log(self) -> None:
        self.query_one("#log", Log).clear()

    # ── Stream lifecycle ─────────────────────────────────────────────

    def _build_cmd(self) -> list[str]:
        bitrate = self.query_one("#inp-bitrate", Input).value or "6000"
        fps = self.query_one("#inp-fps", Input).value or "30"
        scale = self.query_one("#inp-scale", Input).value or "1280x720"
        port = self.query_one("#inp-port", Input).value or "8888"
        encoder = self.query_one("#encoder-select", Select).value

        radio = self.query_one("#source-radio", RadioSet)
        source_idx = radio.pressed_index

        cmd = [
            "uv",
            "run",
            "stream",
            "--bitrate",
            bitrate,
            "--fps",
            fps,
            "--scale",
            scale,
            "--port",
            port,
        ]

        if encoder != "auto":
            cmd.extend(["--encoder", encoder])

        if source_idx == 0:
            cmd.append("--portal")
        elif source_idx == 1:
            cmd.append("--window")
        elif source_idx == 2:
            cmd.append("--test")

        return cmd

    def _launch_stream(self) -> None:
        cmd = self._build_cmd()
        log = self.query_one("#log", Log)
        log.write_line(f"[{self._ts()}] Starting: {' '.join(cmd)}")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            log.write_line(f"[{self._ts()}] ERROR: {exc}")
            return

        self.streaming = True
        self._update_ui()

        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()

    def _read_output(self) -> None:
        """Read subprocess output line by line (runs in thread)."""
        proc = self._proc
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                self.call_from_thread(self._append_log, line)
        except Exception:
            pass
        finally:
            ret = proc.wait()
            self.call_from_thread(self._on_proc_exit, ret)

    def _append_log(self, line: str) -> None:
        log = self.query_one("#log", Log)
        log.write_line(line)

        if "Client connected:" in line:
            addr = line.split("Client connected:")[-1].strip()
            self.client_addr = addr
            self.query_one("#client-info", Static).update(f"📺 Client: {addr}")
        elif "Client disconnected" in line:
            self.client_addr = ""
            self.query_one("#client-info", Static).update("No client connected")

    def _on_proc_exit(self, returncode: int) -> None:
        log = self.query_one("#log", Log)
        if returncode == -signal.SIGTERM or returncode == -signal.SIGINT:
            log.write_line(f"[{self._ts()}] Stream stopped")
        elif returncode != 0:
            log.write_line(f"[{self._ts()}] Process exited with code {returncode}")
        else:
            log.write_line(f"[{self._ts()}] Stream ended normally")

        self._proc = None
        self.streaming = False
        self.client_addr = ""
        self._update_ui()

    def _kill_stream(self) -> None:
        if self._proc:
            log = self.query_one("#log", Log)
            log.write_line(f"[{self._ts()}] Stopping stream...")
            self._proc.terminate()

    # ── UI updates ───────────────────────────────────────────────────

    def _update_ui(self) -> None:
        btn_start = self.query_one("#btn-start", Button)
        btn_stop = self.query_one("#btn-stop", Button)
        status = self.query_one("#status-text", Static)
        url_disp = self.query_one("#url-display", Static)

        if self.streaming:
            btn_start.disabled = True
            btn_stop.disabled = False
            status.update("🔴 Streaming")
            port = self.query_one("#inp-port", Input).value or "8888"
            ips = _get_local_ips()
            ip = ips[0] if ips else "0.0.0.0"
            url_disp.update(f"http://{ip}:{port}")
        else:
            btn_start.disabled = False
            btn_stop.disabled = True
            status.update("⏹  Idle")
            url_disp.update("")
            self.query_one("#client-info", Static).update("No client connected")

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ── Cleanup ──────────────────────────────────────────────────────

    def on_unmount(self) -> None:
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=5)


def main() -> None:
    StreamApp().run()
