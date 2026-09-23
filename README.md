# RTSP Camera Viewer

A Python-based RTSP camera viewer and diagnostic tool for Linux. It uses GStreamer for live playback, automatically deinterlaces video, and probes a wide range of common RTSP paths to help you find a working stream on your camera.

> **⚠️ LEGAL WARNING**
> This tool is intended **only** for use on your own network and on devices you own or have explicit, written permission to test.
> Unauthorized access to camera systems, network scanning, or credential testing is illegal in many jurisdictions.
> By using this tool you accept that it will be used only on your own network and for **educational / lab purposes**.
> The authors and contributors assume **no liability** for misuse or damage caused by this software.

## Features

- Live RTSP playback via GStreamer (TCP/UDP, H.264, H.265, MP4V, JPEG).
- Automatic deinterlacing for interlaced streams.
- Two-phase path probing: priority paths first, then a large fallback list.
- Vendor detection using `nmap -sV` or RTSP banner grabbing.
- Multi-variant path testing per vendor.
- Hard-fail detection to avoid infinite loops on bad URLs.
- Microphone and speaker (ONVIF backchannel) detection.
- Interactive menu for manual path entry and re-checks.

## Requirements

- Linux (any modern distribution)
- Python 3.7+
- GStreamer 1.0 (`gst-launch-1.0`, `gst-inspect-1.0`)
- Optional: `nmap` for vendor detection

### Install GStreamer

**Debian / Ubuntu / Linux Mint:**
```bash
sudo apt update
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav
```

**Fedora:**
```bash
sudo dnf install gstreamer1-plugins-good gstreamer1-plugins-bad-free \
  gstreamer1-plugins-ugly-free gstreamer1-libav gstreamer1-devel
```

**Arch Linux:**
```bash
sudo pacman -S gstreamer gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav
```

### Install nmap

**Debian / Ubuntu / Linux Mint:**
```bash
sudo apt install nmap
```

**Fedora:**
```bash
sudo dnf install nmap
```

**Arch Linux:**
```bash
sudo pacman -S nmap
```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/jacobP-cyberdev/rtsp-camera-viewer.git
   cd rtsp-camera-viewer
   ```

2. (Optional) Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. No Python dependencies are required beyond the standard library.
   Ensure GStreamer and `nmap` are installed and available in your `PATH`.

## Usage

```bash
python3 connect.py
```

You will be prompted for an IP address. The tool will then probe for a working RTSP path and present an interactive menu.

> **Note:** `connect.py` requires `APPROVED = True` before it will run. Read [SECURITY.md](SECURITY.md) first.

### Providing credentials

**Do not hardcode credentials in the source code.**
If your camera requires a username and password, include them in the path you enter, or modify the script to prompt at runtime.

Example of a custom path with credentials:
```
/user=admin_password=YOUR_PASSWORD_channel=1_stream=0.sdp?real_stream
```

Replace `YOUR_PASSWORD` with your actual password. Never commit credentials to version control.

### Menu options

- **Connect using detected path** – uses the best path found during the initial probe.
- **I know the vendor** – select a vendor from a list.
- **Auto-detect vendor** – runs `nmap -sV` and falls back to RTSP banner probing.
- **Try common paths blindly** – iterates through a large list of fallback paths.
- **Enter a custom RTSP path** – manually specify a path.
- **Change target IP** – switch to a different camera.
- **Check speaker (ONVIF backchannel)** – probes for two-way audio support.
- **Re-check mic on current IP** – re-runs the microphone detection.
- **Re-check with verbose path output** – same as above with detailed logs.

## Configuration

There are no configuration files. All tuning constants are at the top of `connect.py`. Edit them directly to change timeouts, worker counts, or path lists.

**Security note:** The path lists in `connect.py` may contain placeholders for default credentials. Replace all hardcoded passwords with `{password}` placeholders and prompt the user at runtime, or remove those paths entirely before publishing.

## Security and Legal

- Use only on networks and devices you own or have permission to test.
- Do not use this tool to access cameras you do not own.
- Never commit real credentials, API keys, or personal data to the repository.
- See [SECURITY.md](SECURITY.md) for the security policy and reporting instructions.

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please ensure that any contributions do not include real credentials or personal data, and that they adhere to the legal and ethical guidelines above.