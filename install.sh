#!/usr/bin/env bash
# Install dependencies for WebRTC screen streamer on Fedora
set -euo pipefail

cd "$(dirname "$0")"

# ── Detect GPU vendor ────────────────────────────────────────────────────
has_nvidia=false
has_amd=false
has_intel=false

if lspci 2>/dev/null | grep -qi 'vga.*nvidia\|3d.*nvidia'; then
  has_nvidia=true
fi
if lspci 2>/dev/null | grep -qi 'vga.*amd\|vga.*ati\|3d.*amd'; then
  has_amd=true
fi
if lspci 2>/dev/null | grep -qi 'vga.*intel\|display.*intel'; then
  has_intel=true
fi

echo "=== Detected GPUs ==="
$has_nvidia && echo "  • NVIDIA"
$has_amd    && echo "  • AMD"
$has_intel  && echo "  • Intel"
! $has_nvidia && ! $has_amd && ! $has_intel && echo "  (none detected — will install software fallback only)"

# ── Base packages (always needed) ────────────────────────────────────────
echo ""
echo "=== Base system packages (DNF) ==="
sudo dnf install -y \
  gstreamer1 \
  gstreamer1-plugins-base \
  gstreamer1-plugins-good \
  gstreamer1-plugins-bad-free \
  gstreamer1-plugin-libav \
  python3-gobject \
  python3-dbus \
  pipewire-devel

# ── GPU-specific packages ────────────────────────────────────────────────
if $has_nvidia; then
  echo ""
  echo "=== NVIDIA encoder packages ==="
  sudo dnf install -y \
    gstreamer1-plugins-bad-freeworld
fi

if $has_amd || $has_intel; then
  echo ""
  echo "=== VA-API encoder packages (AMD/Intel) ==="
  sudo dnf install -y \
    gstreamer1-vaapi \
    libva-utils
  if $has_amd; then
    sudo dnf install -y libva-mesa-driver mesa-va-drivers
  fi
  if $has_intel; then
    sudo dnf install -y intel-media-driver
  fi
fi

# Software fallback (x264) — in plugins-ugly, always available
sudo dnf install -y gstreamer1-plugins-ugly 2>/dev/null || true

echo ""
echo "=== uv sync ==="
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv sync

# ── Verify GStreamer elements ────────────────────────────────────────────
echo ""
echo "=== Checking GStreamer elements ==="
ok=true

# Always check core elements
for el in pipewiresrc webrtcbin rtph264pay h264parse videoconvert; do
  if gst-inspect-1.0 "$el" >/dev/null 2>&1; then
    echo "  ✓ $el"
  else
    echo "  ✗ $el  NOT FOUND"
    ok=false
  fi
done

# Check GPU-specific encoders
encoder_found=false
if $has_nvidia; then
  if gst-inspect-1.0 nvh264enc >/dev/null 2>&1; then
    echo "  ✓ nvh264enc (NVIDIA NVENC)"
    encoder_found=true
  else
    echo "  ✗ nvh264enc  NOT FOUND — need RPM Fusion + NVIDIA drivers"
  fi
fi
if $has_amd || $has_intel; then
  if gst-inspect-1.0 vaapih264enc >/dev/null 2>&1; then
    echo "  ✓ vaapih264enc (VA-API)"
    encoder_found=true
  else
    echo "  ✗ vaapih264enc  NOT FOUND — check VA-API driver installation"
  fi
fi
if gst-inspect-1.0 x264enc >/dev/null 2>&1; then
  echo "  ✓ x264enc (software fallback)"
  encoder_found=true
fi

echo ""
if $ok && $encoder_found; then
  echo "✅ Ready to stream."
else
  echo "⚠  Some elements missing:"
  echo "  • webrtcbin  → gstreamer1-plugins-bad-free"
  echo "  • pipewiresrc → gstreamer1-plugins-good"
  $has_nvidia && echo "  • nvh264enc  → gstreamer1-plugins-bad-freeworld (RPM Fusion)"
  ($has_amd || $has_intel) && echo "  • vaapih264enc → gstreamer1-vaapi + VA-API driver"
fi

echo ""
echo "Usage:"
echo "  uv run stream --portal              # pick monitor interactively"
echo "  uv run stream --window              # pick window interactively"
echo "  uv run stream --pw-node <ID>        # known PipeWire node"
echo "  uv run stream --test                # SMPTE test pattern"
echo "  uv run stream --portal --bitrate 8000"
$has_nvidia && echo "  uv run stream --portal --encoder nvenc   # force NVENC"
($has_amd || $has_intel) && echo "  uv run stream --portal --encoder vaapi  # force VA-API"
echo "  uv run stream-tui                   # TUI launcher"
