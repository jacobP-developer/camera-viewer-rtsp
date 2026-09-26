# RTSP Camera Viewer for Linux

A Python-based RTSP camera viewer and diagnostic tool designed specifically for Linux environments. It leverages GStreamer for robust playback and `nmap` for advanced vendor identification.

> **⚠️ LEGAL WARNING**
> Intended **only** for use on your own network and on devices you own or have explicit, written permission to test. See the main [README](../README.md) for details.

---

## Requirements

- **Linux** (any modern distribution)
- **Python 3.7+**
- **GStreamer 1.0** (`gst-launch-1.0`, `gst-inspect-1.0`)
- **Optional:** `nmap` (for automatic vendor detection)

### Installing Dependencies

**Debian / Ubuntu / Linux Mint:**
```bash
sudo apt update
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav nmap
```

**Fedora**
```bash
sudo dnf install gstreamer1-plugins-good gstreamer1-plugins-bad-free \
  gstreamer1-plugins-ugly-free gstreamer1-libav gstreamer1-devel nmap
```

**Arch**
```bash
sudo pacman -S gstreamer gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav nmap
```

## Installation

**Clone the repo and cd**
```bash
git clone https://github.com/jacobP-cyberdev/rtsp-camera-viewer.git
cd rtsp-camera-viewer/linux
```

**python3 connect.py**
You will be prompted for an IP address. Once given, the tool will then automatically find a working RTSP path
