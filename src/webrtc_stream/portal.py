"""XDG ScreenCast Portal — Wayland screen/window capture via D-Bus."""

from __future__ import annotations

import logging
import random
import string
import sys
from typing import NamedTuple

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

LOG = logging.getLogger(__name__)

REQ_IFACE = "org.freedesktop.portal.Request"


class CaptureSource(NamedTuple):
    """Result of a portal screen-cast session."""

    fd: int
    node_id: int


def _token() -> str:
    return "t" + "".join(random.choices(string.ascii_lowercase, k=8))


def portal_screencast(capture_type: int = 1) -> CaptureSource:
    """Pick a source via the ScreenCast portal.

    Args:
        capture_type: 1 = monitor, 2 = window, 3 = both.

    Returns:
        CaptureSource(fd, node_id).

    Blocks until the user allows capture. Exits on failure.
    """
    DBusGMainLoop(set_as_default=True)

    bus = dbus.SessionBus()
    portal = dbus.Interface(
        bus.get_object(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
        ),
        "org.freedesktop.portal.ScreenCast",
    )

    result: dict = {}
    loop = GLib.MainLoop()

    def on_create(resp, res):
        if resp:
            LOG.error("Portal CreateSession failed (%d)", resp)
            loop.quit()
            return
        session = res["session_handle"]
        result["session"] = session

        def on_select(resp2, _):
            if resp2:
                LOG.error("Portal SelectSources failed (%d)", resp2)
                loop.quit()
                return

            def on_start(resp3, res3):
                if resp3:
                    LOG.error("Portal Start failed (%d)", resp3)
                    loop.quit()
                    return
                streams = res3.get("streams", [])
                if not streams:
                    LOG.error("Portal returned no streams")
                    loop.quit()
                    return
                result["node"] = int(streams[0][0])
                result["fd"] = portal.OpenPipeWireRemote(
                    session,
                    dbus.Dictionary({}, signature="sv"),
                ).take()
                LOG.info("Portal capture: node=%d fd=%d", result["node"], result["fd"])
                loop.quit()

            p3 = portal.Start(
                session,
                "",
                dbus.Dictionary({"handle_token": _token()}, signature="sv"),
            )
            bus.add_signal_receiver(on_start, "Response", REQ_IFACE, path=p3)

        p2 = portal.SelectSources(
            session,
            dbus.Dictionary(
                {
                    "handle_token": _token(),
                    "types": dbus.UInt32(capture_type),
                    "multiple": False,
                    "cursor_mode": dbus.UInt32(2),
                },
                signature="sv",
            ),
        )
        bus.add_signal_receiver(on_select, "Response", REQ_IFACE, path=p2)

    p1 = portal.CreateSession(
        dbus.Dictionary(
            {
                "handle_token": _token(),
                "session_handle_token": _token(),
            },
            signature="sv",
        ),
    )
    bus.add_signal_receiver(on_create, "Response", REQ_IFACE, path=p1)

    GLib.timeout_add_seconds(60, loop.quit)
    loop.run()

    if "fd" not in result:
        sys.exit("Portal: screen capture was not granted")

    return CaptureSource(fd=result["fd"], node_id=result["node"])
