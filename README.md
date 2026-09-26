# RTSP Camera Viewer & Diagnostic Tool

A Python-based RTSP camera viewer and diagnostic tool supporting both
**Linux** and **Android**. It uses GStreamer on Linux (with automatic
deinterlacing) and mpv inside Termux:X11 on Android.

Linux is the primary platform and supports the full feature set. Android
is functional but slower. Vendor detection via `nmap` is limited on
mobile, and the tool falls back to RTSP banner parsing, which is less
precise for some camera models.

> **⚠️ LEGAL WARNING**
> This tool is intended **only** for use on your own network and on
> devices you own or have explicit, written permission to test.
> Unauthorized access to camera systems, network scanning, or credential
> testing is illegal in many jurisdictions.
> By using this tool you accept that it will be used only on your own
> network and for **educational and lab purposes**.
> The authors and contributors assume no liability for misuse or damage
> caused by this software.

---

## Platform Guides

| Platform | Guide | Player |
|---|---|---|
| Linux | [linux/LINUX.md](linux/LINUX.md) | GStreamer |
| Android | [android/ANDROID.md](android/ANDROID.md) | mpv in Termux:X11 |

Both platforms share the same `camera.py`. The script detects the
platform at runtime and selects the correct backend automatically. There
is no build step and no configuration file.

---

## What the Tool Does

The tool sends RTSP `OPTIONS` and `DESCRIBE` requests to port 554 on the
target IP, trying a library of known camera paths collected from vendor
documentation and public write-ups. It parses the returned SDP to
identify the video codec, check for an audio track, and score each path.
The best-scoring path is handed to the player. Paths that return RTSP
errors are rejected immediately, so the tool never loops on a dead URL.

A two-phase probe design tries a short priority list first, then a much
larger fallback list only if needed.

---

## Features

- **Live RTSP Playback:** GStreamer on Linux (TCP/UDP). mpv in Termux:X11 on Android (TCP).
- **Codec support:** H.264, H.265, MP4V, JPEG, MPV on Linux. H.264, H.265 on Android.
- **Automatic deinterlacing** on Linux for interlaced streams.
- **Two-phase path probing:** fast priority pass, then large fallback.
- **Vendor detection** via `nmap -sV` or RTSP banner parsing.
- **Multi-variant path testing** per vendor.
- **Hard-fail detection** so bad URLs do not loop.
- **Microphone and speaker detection**, including ONVIF backchannel probing.
- **Interactive menu** with manual path entry, vendor selection, and rechecks.
- **No third-party Python dependencies** beyond the standard library.

---

## Security and Legal

- Use only on networks and devices you own or have explicit permission to test.
- The path library uses `PRIORITY_PATHS` placeholders. This json has the majority of all **publicly available paths**
- See [SECURITY.md](SECURITY.md) for the security policy and vulnerability reporting process.

---

## License

This project is licensed under the Apache License 2.0.
See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for details.

---

## Prohibited Uses

You may not use this tool to access devices, networks, or camera systems
without explicit, written authorization from the owner. You may not use
it for unauthorized surveillance, harassment, or any illegal activity.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to
discuss what you would like to change.

Please ensure contributions do not include real credentials or personal
data, and that they follow the legal and ethical guidelines above.