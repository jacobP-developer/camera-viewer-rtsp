#!/usr/bin/env python3
"""
RTSP camera viewer with automatic player backend selection.

Desktop Linux: uses GStreamer for playback.
Android / Termux: uses mpv inside Termux:X11 (no root required).

The mode is chosen at runtime. No flags needed.
"""

import os
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Termux environment setup
# ---------------------------------------------------------------------------
# XDG_RUNTIME_DIR must point at $PREFIX/tmp so X11 clients can find the
# abstract socket that termux-x11 creates. Set it before anything else.
if "com.termux" in os.environ.get("PREFIX", ""):
    _PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    os.environ.setdefault("XDG_RUNTIME_DIR", os.path.join(_PREFIX, "tmp"))

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
PROBE_WORKERS = 12
PROBE_TIMEOUT = 2
STABILITY_GRACE = 6.0
HARD_FAIL_THRESHOLD = 2.0
PLAYER_STARTUP_TIMEOUT = 15.0
RTSP_USER_AGENT = "LIVE555 Streaming Media v2016.11.28"
RTSP_LATENCY = 500
X11_DISPLAY = ":0"
X11_STARTUP_WAIT = 8.0

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
IS_LINUX = not IS_TERMUX and sys.platform.startswith("linux")

PLAYER_BACKEND = None


def detect_backend():
    global PLAYER_BACKEND
    if IS_TERMUX:
        if shutil.which("mpv") and shutil.which("termux-x11"):
            PLAYER_BACKEND = "x11-mpv"
            return PLAYER_BACKEND
        PLAYER_BACKEND = None
        return None
    PLAYER_BACKEND = "gstreamer"
    return "gstreamer"


# ---------------------------------------------------------------------------
# Priority paths
# ---------------------------------------------------------------------------
PRIORITY_PATHS = [
    "/?chID=1&streamType=main&linkType=tcp",
    "/chID=1&streamType=main&linkType=tcp",
    "/chID=1&streamType=main",
    "/profile1",
    "/Streaming/Channels/101",
    "/Streaming/channels/101",
    "/cam/realmonitor?channel=1&subtype=0",
    "/user=admin_password={password}_channel=1_stream=0.sdp?real_stream",
    "/user=admin_password=admin_channel=1_stream=0.sdp?real_stream",
    "/user=admin_password={password}_channel=1_stream=0.sdp",
    "/user=admin_password=admin_channel=1_stream=0.sdp",
    "/11",
    "/axis-media/media.amp",
    "/mpeg/media.amp",
    "/h264Preview_01_main",
    "/live/ch0",
    "/videoMain",
]

PRIORITY_WORKERS = 4
PRIORITY_GRACE = 2.0

# ---------------------------------------------------------------------------
# Vendor -> primary path
# ---------------------------------------------------------------------------
VENDOR_PATHS = {
    "hipcam":       "/11",
    "xiongmai":     "/user=admin_password={password}_channel=1_stream=0.sdp?real_stream",
    "dahua":        "/cam/realmonitor?channel=1&subtype=0",
    "amcrest":      "/cam/realmonitor?channel=1&subtype=0",
    "intelbras":    "/cam/realmonitor?channel=1&subtype=0",
    "hikvision":    "/Streaming/Channels/101",
    "reolink":      "/h264Preview_01_main",
    "axis":         "/axis-media/media.amp",
    "doorbird":     "/mpeg/media.amp",
    "foscam":       "/videoMain",
    "dlink":        "/live1.sdp",
    "tp-link":      "/stream1",
    "tapo":         "/stream1",
    "samsung":      "/profile2/media.smp",
    "hanwha":       "/profile2/media.smp",
    "bosch":        "/video?inst=1",
    "vivotek":      "/live.sdp",
    "panasonic":    "/MediaInput/h264",
    "sony":         "/media/video1",
    "lorex":        "/cam/realmonitor?channel=1&subtype=0",
    "honeywell":    "/h264",
    "pelco":        "/stream1",
    "grandstream":  "/live/ch00_0",
    "geovision":    "/CH001.sdp",
    "acti":         "/stream1",
    "milesight":    "/main",
    "instar":       "/11",
    "arecont":      "/h264.sdp",
    "toshiba":      "/live.sdp",
    "lg":           "/video1+audio1",
    "tvt_dvr":      "/?chID=1&streamType=main&linkType=tcp",
    "tvt_cam":      "/profile1",
    "tvt_dvr_main": "/?chID=1&streamType=main&linkType=tcp",
    "tvt_dvr_sub":  "/?chID=1&streamType=sub&linkType=tcp",
    "tvt_plain":    "/chID=1&streamType=main&linkType=tcp",
    "h264dvr":      "/user=admin_password={password}_channel=1_stream=0.sdp?real_stream",
    "generic":      "/11",
}

# ---------------------------------------------------------------------------
# Multi-variant paths per vendor
# ---------------------------------------------------------------------------
VENDOR_PATH_VARIANTS = {
    "h264dvr": [
        "/user=admin_password={password}_channel=1_stream=0.sdp?real_stream",
        "/user=admin_password=admin_channel=1_stream=0.sdp?real_stream",
        "/user=admin&password=&channel=1&stream=0.sdp?real_stream",
        "/user=admin&password=admin&channel=1&stream=0.sdp?real_stream",
        "/11", "/12", "/0", "/1",
        "/live/ch0", "/stream1", "/h264", "/video1",
    ],
    "tvt_dvr": [
        "/?chID=1&streamType=main&linkType=tcp",
        "/?chID=1&streamType=sub&linkType=tcp",
        "/chID=1&streamType=main&linkType=tcp",
        "/chID=1&streamType=main",
        "/profile1",
        "/profile2",
    ],
    "tvt_cam": [
        "/profile1",
        "/profile2",
        "/?chID=1&streamType=main&linkType=tcp",
    ],
    "hipcam": ["/11", "/12", "/13", "/0", "/1"],
    "dahua": [
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
        "/cam/realmonitor?channel=1&subtype=0&proto=Onvif",
    ],
    "amcrest": [
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
    ],
    "intelbras": [
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
    ],
    "lorex": [
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
    ],
    "hikvision": [
        "/Streaming/Channels/101",
        "/Streaming/Channels/102",
        "/ISAPI/Streaming/channels/101",
        "/h264/ch1/main/av_stream",
    ],
    "axis": [
        "/axis-media/media.amp",
        "/axis-media/media.amp?videocodec=h264",
        "/mpeg/media.amp",
        "/mpeg4/media.amp",
    ],
    "doorbird": [
        "/mpeg/media.amp",
        "/mpeg/720p/media.amp",
        "/mpeg/1080p/media.amp",
        "/axis-media/media.amp",
    ],
    "xiongmai": [
        "/user=admin_password={password}_channel=1_stream=0.sdp?real_stream",
        "/11", "/12",
    ],
    "reolink": [
        "/h264Preview_01_main",
        "/h264Preview_01_sub",
        "/Preview_01_main",
    ],
    "foscam": ["/videoMain", "/videoSub"],
    "grandstream": ["/live/ch0", "/live/ch00_0", "/live/ch01_0"],
    "vivotek": ["/live.sdp", "/live1.sdp", "/live2.sdp"],
    "generic": [
        "/11", "/12", "/13", "/0", "/1", "/2",
        "/stream1", "/stream2", "/video1", "/video2",
        "/h264", "/h264.sdp", "/mpeg4", "/live/ch0",
        "/onvif1", "/onvif2",
    ],
}

FALLBACK_PATHS = [
    "/?chID=1&streamType=main&linkType=tcp",
    "/?chID=1&streamType=sub&linkType=tcp",
    "/?chID=2&streamType=main&linkType=tcp",
    "/chID=1&streamType=main&linkType=tcp",
    "/chID=1&streamType=main",
    "/chID=1&streamType=sub&linkType=tcp",
    "/profile1", "/profile2", "/profile3",
    "/Streaming/channels/101", "/Streaming/Channels/101",
    "/user=admin_password={password}_channel=1_stream=0.sdp?real_stream",
    "/user=admin_password=admin_channel=1_stream=0.sdp?real_stream",
    "/user=admin&password=&channel=1&stream=0.sdp?real_stream",
    "/user=admin&password=admin&channel=1&stream=0.sdp?real_stream",
    "/cam/realmonitor?channel=1&subtype=0",
    "/cam/realmonitor?channel=1&subtype=1",
    "/cam/realmonitor?channel=1&subtype=0&proto=Onvif",
    "/Streaming/Channels/102",
    "/Streaming/Unicast/channels/101",
    "/ISAPI/Streaming/channels/101",
    "/h264/ch1/main/av_stream",
    "/h264/ch1/sub/av_stream",
    "/axis-media/media.amp",
    "/axis-media/media.amp?videocodec=h264",
    "/mpeg/media.amp",
    "/mpeg/720p/media.amp",
    "/mpeg/1080p/media.amp",
    "/mpeg4/media.amp",
    "/mjpg/media.smp",
    "/axis-cgi/mjpg/video.cgi",
    "/rtsp_tunnel",
    "/videoMain", "/videoSub",
    "/h264Preview_01_main", "/h264Preview_01_sub", "/Preview_01_main",
    "/live/ch0", "/live/ch00_0", "/live/ch01_0",
    "/profile2/media.smp", "/profile1/media.smp", "/media.smp",
    "/live.sdp", "/live1.sdp",
    "/MediaInput/h264", "/MediaInput/h264/stream_1",
    "/media/video1", "/media/video2",
    "/video?inst=1",
    "/stream1", "/stream2",
    "/CH001.sdp",
    "/11", "/12", "/13", "/14", "/21", "/22", "/0", "/1", "/2",
    "/h264", "/h264.sdp",
    "/mpeg4", "/mpeg4.sdp", "/mpeg4cif", "/mpeg4unicast",
    "/live", "/live/", "/live/av0",
    "/live/h264", "/live/mpeg4",
    "/live_h264.sdp", "/live_mpeg4.sdp",
    "/live0.264", "/live1.264",
    "/av0_0", "/av0_1", "/av1_0", "/av1_1",
    "/ch0", "/ch1",
    "/ch0.h264", "/ch0_0.h264",
    "/ch0_unicast_firststream", "/ch0_unicast_secondstream",
    "/channel1", "/channel2",
    "/media", "/media.amp", "/media/media.amp",
    "/onvif1", "/onvif2",
    "/onvif-media/media.amp", "/onvif/channel1", "/onvif/live/2",
    "/ipcam.sdp", "/ipcam_h264.sdp",
    "/rtsph264", "/rtpvideo1.sdp",
    "/play1.sdp", "/play2.sdp",
    "/1/1:1/main", "/1/stream1", "/1/cif", "/1.AMP",
    "/0/video1", "/tcp/av0_0",
    "/unicast/c1/s1/live", "/ucast/11",
    "/videoinput_1:0/h264_1/onvif.stm",
    "/videostream.cgi", "/video.cgi", "/video.mjpg", "/video.h264",
    "/video1+audio1",
    "/now.mp4",
    "/GetData.cgi", "/MJPEG.cgi", "/mjpeg.cgi", "/image/jpeg.cgi",
    "/cgi-bin/viewer/video.jpg?resolution=640x480",
]

VENDOR_KEYWORDS = [
    ("doorbird", "doorbird"), ("hipcam", "hipcam"),
    ("hikvision", "hikvision"), ("dahua", "dahua"),
    ("amcrest", "amcrest"), ("intelbras", "intelbras"),
    ("reolink", "reolink"), ("foscam", "foscam"),
    ("vivotek", "vivotek"), ("grandstream", "grandstream"),
    ("geovision", "geovision"), ("instar", "instar"),
    ("xiongmai", "xiongmai"),
    ("tvt rtsp", "tvt_dvr"), ("tvt", "tvt_dvr"),
    ("axis", "axis"),
    ("h264dvr", "h264dvr"),
    ("rtprtspflyer", "generic"), ("live555", "generic"),
]

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
IP_REGEX = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"
)


def is_valid_ipv4(ip):
    return bool(IP_REGEX.match(ip.strip()))


# ---------------------------------------------------------------------------
# Path scoring
# ---------------------------------------------------------------------------
def _path_score(path):
    p = path.lower()
    score = 0
    if "streamtype=main" in p:
        score += 100
    elif "streamtype=sub" in p:
        score -= 50
    if "subtype=0" in p:
        score += 20
    elif "subtype=1" in p:
        score -= 10
    if "profile1" in p:
        score += 15
    if "profile2" in p:
        score += 5
    if "/streaming/channels/101" in p:
        score += 15
    if "stream=0" in p or "stream1" in p:
        score += 5
    if "real_stream" in p:
        score += 10
    if p.endswith("/11"):
        score += 3
    return score


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------
def _rtsp_exchange(ip, path, timeout=4, extra_headers="", describe=True,
                   teardown=True):
    try:
        with socket.create_connection((ip, 554), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(
                f"OPTIONS rtsp://{ip}:554{path} RTSP/1.0\r\n"
                f"CSeq: 1\r\n"
                f"User-Agent: {RTSP_USER_AGENT}\r\n\r\n".encode()
            )
            opt = b""
            while b"\r\n\r\n" not in opt:
                chunk = s.recv(4096)
                if not chunk:
                    break
                opt += chunk

            if not describe:
                return opt.decode(errors="ignore")

            s.sendall(
                f"DESCRIBE rtsp://{ip}:554{path} RTSP/1.0\r\n"
                f"CSeq: 2\r\n"
                f"Accept: application/sdp\r\n"
                f"User-Agent: {RTSP_USER_AGENT}\r\n"
                f"{extra_headers}\r\n".encode()
            )

            body = b""
            while len(body) < 32768:
                try:
                    chunk = s.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                body += chunk

                if b"\r\n\r\n" in body:
                    headers, _, payload = body.partition(b"\r\n\r\n")
                    if b"200 OK" not in headers[:32]:
                        break
                    m = re.search(rb"Content-Length:\s*(\d+)", headers, re.I)
                    if m:
                        if len(payload) >= int(m.group(1)):
                            break
                    elif b"a=control" in payload:
                        break

            if teardown:
                try:
                    s.sendall(
                        f"TEARDOWN rtsp://{ip}:554{path} RTSP/1.0\r\n"
                        f"CSeq: 3\r\n"
                        f"User-Agent: {RTSP_USER_AGENT}\r\n\r\n".encode()
                    )
                    s.settimeout(0.3)
                    try:
                        s.recv(512)
                    except socket.timeout:
                        pass
                except (socket.timeout, ConnectionError, OSError):
                    pass

            return body.decode(errors="ignore")
    except (socket.timeout, ConnectionError, OSError):
        return ""


_STATIC_PAYLOAD_TYPES = {
    "0": "PCMU", "8": "PCMA", "9": "G722",
    "3": "GSM", "4": "G723", "18": "G729",
}

_VIDEO_CODEC_MAP = {
    "H264": "H264",
    "H265": "H265",
    "HEVC": "H265",
    "MP4V-ES": "MP4V",
    "MP4V": "MP4V",
    "JPEG": "JPEG",
    "MPV": "MPV",
    "VP8": "VP8",
    "VP9": "VP9",
}

_STATIC_VIDEO_PT = {
    "26": "JPEG", "31": "H261", "32": "MPV",
    "33": "MP2T", "34": "H263",
}

_RTSP_ERROR_CODES = ("400", "401", "403", "404", "405", "415",
                     "451", "500", "501", "503")


def _response_is_error(sdp):
    head = sdp[:96]
    for code in _RTSP_ERROR_CODES:
        if f" {code} " in head or f"\r\n{code} " in head:
            return True
    return False


def _parse_audio_codec(sdp):
    for line in sdp.splitlines():
        if line.startswith("a=rtpmap:") and any(
            c in line for c in ("PCMA", "PCMU", "opus", "OPUS",
                                "MPEG4-GENERIC", "AAC", "L16",
                                "G722", "G726", "SPEEX", "AMR")
        ):
            try:
                return line.split()[1].split("/")[0]
            except IndexError:
                pass
    for line in sdp.splitlines():
        if line.startswith("m=audio "):
            parts = line.split()
            if len(parts) >= 4 and parts[3] in _STATIC_PAYLOAD_TYPES:
                return _STATIC_PAYLOAD_TYPES[parts[3]]
    return "unknown"


def _parse_video_codec(sdp):
    fmtp_lines = [l for l in sdp.splitlines() if l.startswith("a=fmtp:")]
    fmtp_blob = " ".join(fmtp_lines).lower()
    if "sprop-vps" in fmtp_blob:
        return "H265"
    if "sprop-parameter-sets" in fmtp_blob:
        if not any(marker in fmtp_blob for marker in
                   ("sprop-vps", "sprop-sps", "sprop-pps")):
            return "H264"
    for line in sdp.splitlines():
        if line.startswith("a=rtpmap:"):
            up = line.upper()
            for key, canonical in _VIDEO_CODEC_MAP.items():
                if key in up:
                    return canonical
    for line in sdp.splitlines():
        if line.startswith("m=video "):
            parts = line.split()
            if len(parts) >= 4 and parts[3] in _STATIC_VIDEO_PT:
                return _STATIC_VIDEO_PT[parts[3]]
    return "unknown"


def _probe_batch(ip, paths, workers, timeout, verbose, label,
                 collect_grace=0.0):
    if not paths:
        return None, False, None, None
    total = len(paths)
    stop_event = threading.Event()
    stats = {"done": 0, "responses": 0}
    hits = []
    first_hit_time = [None]

    def try_path(path):
        if stop_event.is_set():
            return None
        sdp = _rtsp_exchange(ip, path, timeout=timeout, teardown=True)
        return (path, sdp)

    executor = ThreadPoolExecutor(max_workers=workers)
    futures = []
    try:
        futures = [executor.submit(try_path, p) for p in paths]
        for future in as_completed(futures):
            if stop_event.is_set() and first_hit_time[0] is None:
                continue
            if (first_hit_time[0] is not None
                    and time.time() - first_hit_time[0] > collect_grace):
                break
            try:
                res = future.result()
            except Exception:
                continue
            if res is None:
                continue
            path, sdp = res
            stats["done"] += 1
            if sdp:
                stats["responses"] += 1
            if verbose:
                tag = "resp" if sdp else "----"
                print(f"    [{label} {stats['done']}/{total}] [{tag}] {path}")

            if not sdp:
                continue
            if _response_is_error(sdp):
                continue
            if "m=video" not in sdp:
                continue

            vcodec = _parse_video_codec(sdp)
            has_audio = "m=audio" in sdp
            acodec = _parse_audio_codec(sdp) if has_audio else None
            if acodec == "unknown":
                has_audio = False
                acodec = None
            hits.append((path, has_audio, acodec, vcodec))
            if first_hit_time[0] is None:
                first_hit_time[0] = time.time()
                print(f"\n[+] {label} hit: {path}")
                stop_event.set()
            if collect_grace <= 0:
                break
    except KeyboardInterrupt:
        stop_event.set()
        raise
    finally:
        stop_event.set()
        for f in futures:
            f.cancel()
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    if hits:
        best = max(hits, key=lambda h: _path_score(h[0]))
        if len(hits) > 1:
            print(f"[*] {label}: collected {len(hits)} hits, "
                  f"picked best: {best[0]}")
        return best
    return None, False, None, None


def probe_audio(ip, timeout=PROBE_TIMEOUT, verbose=False,
                workers=PROBE_WORKERS):
    print(f"[*] Probing {ip}:554 (two-phase: priority then full)...")

    print(f"[*] Phase 1: {len(PRIORITY_PATHS)} priority paths, "
          f"{PRIORITY_WORKERS} workers, {PRIORITY_GRACE}s hit grace")
    result = _probe_batch(ip, PRIORITY_PATHS, PRIORITY_WORKERS,
                          timeout, verbose, "P1",
                          collect_grace=PRIORITY_GRACE)
    if result[0] is not None:
        path, has_audio, acodec, vcodec = result
        print(f"[+] Phase 1 found working path: {path}")
        return path, has_audio, acodec, vcodec

    print(f"[*] Phase 2: {len(FALLBACK_PATHS)} paths, "
          f"{workers} workers")
    result = _probe_batch(ip, FALLBACK_PATHS, workers,
                          timeout, verbose, "P2",
                          collect_grace=0.0)
    if result[0] is not None:
        path, has_audio, acodec, vcodec = result
        print(f"[+] Phase 2 found working path: {path}")
        return path, has_audio, acodec, vcodec

    return None, False, None, None


def probe_speaker(ip, path, timeout=4):
    sdp = _rtsp_exchange(
        ip, path, timeout=timeout, teardown=True,
        extra_headers="Require: www.onvif.org/ver20/backchannel\r\n"
    )
    if not sdp or "551" in sdp:
        return False, None
    if "a=sendonly" not in sdp:
        return False, None
    return True, _parse_audio_codec(sdp)


def report_mic(ip, verbose=False):
    print(f"[*] Probing {ip}:554 for a working RTSP stream and microphone...")
    path, has_audio, acodec, vcodec = probe_audio(ip, verbose=verbose)
    if path is None:
        print("[!] No working RTSP path found.")
        return None, False, None
    print(f"[+] Working path: {path}")
    print(f"[+] Video codec: {vcodec}")
    if has_audio:
        print(f"[+] Microphone: PRESENT (audio codec: {acodec})")
    else:
        print("[-] Microphone: NOT PRESENT (video only)")
    print("[*] Speaker check is available from the menu.")
    return path, has_audio, vcodec


# ---------------------------------------------------------------------------
# Termux:X11 helpers
# ---------------------------------------------------------------------------
def _x11_dir():
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return os.path.join(runtime, ".X11-unix")
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    return os.path.join(prefix, "tmp", ".X11-unix")


def _x11_socket_path():
    return os.path.join(_x11_dir(), "X" + X11_DISPLAY.lstrip(":"))


def _x11_env():
    env = dict(os.environ)
    env["DISPLAY"] = X11_DISPLAY
    if "XDG_RUNTIME_DIR" not in env:
        prefix = env.get("PREFIX", "/data/data/com.termux/files/usr")
        env["XDG_RUNTIME_DIR"] = os.path.join(prefix, "tmp")
    return env


def _kill_x11():
    try:
        subprocess.run(
            ["pkill", "-f", "termux-x11"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass
    time.sleep(0.5)


def _clean_x11_sockets():
    xdir = _x11_dir()
    if not os.path.isdir(xdir):
        return
    for name in os.listdir(xdir):
        if name.startswith("X") and name[1:].isdigit():
            try:
                os.remove(os.path.join(xdir, name))
            except Exception:
                pass


def _x11_is_running():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "termux-x11"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass
    return os.path.exists(_x11_socket_path())


def _start_x11():
    if _x11_is_running() and os.path.exists(_x11_socket_path()):
        print(f"[*] Termux:X11 already running on {X11_DISPLAY}.")
        return True

    print("[*] Cleaning up old Termux:X11 sessions...")
    _kill_x11()
    _clean_x11_sockets()

    print(f"[*] Starting Termux:X11 on {X11_DISPLAY}...")
    try:
        subprocess.Popen(
            ["termux-x11", X11_DISPLAY],
            env=_x11_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        print("[!] termux-x11 not found.")
        print("[*] Install with:")
        print("    pkg install x11-repo")
        print("    pkg install termux-x11-nightly")
        return False

    socket_path = _x11_socket_path()
    deadline = time.time() + X11_STARTUP_WAIT
    while time.time() < deadline:
        if os.path.exists(socket_path):
            print(f"[+] Termux:X11 ready on {X11_DISPLAY}.")
            print("[*] Open the Termux:X11 app on your phone to see video.")
            return True
        time.sleep(0.3)

    print("[!] Termux:X11 did not come up in time.")
    print("[*] Open the Termux:X11 app manually, then retry.")
    return False


def _build_mpv_command(url, gpu=True):
    base = [
        "mpv",
        "--no-config",
        "--rtsp-transport=tcp",
        "--no-input-default-bindings",
        "--input-terminal=no",
        "--osc=no",
    ]
    if gpu:
        base += ["--vo=gpu", "--gpu-context=x11egl"]
    else:
        base += ["--vo=x11"]
    base.append(url)
    return base


# ---------------------------------------------------------------------------
# External player backends
# ---------------------------------------------------------------------------
def ensure_player_available():
    backend = detect_backend()
    if backend is None:
        print("[!] Termux detected, but the required player is not installed.")
        print("[*] Install everything with:")
        print("    pkg update")
        print("    pkg install x11-repo")
        print("    pkg install termux-x11-nightly")
        print("    pkg install mpv-x")
        print("[*] Also install the Termux:X11 app on your phone.")
        sys.exit(1)
    if backend == "gstreamer":
        if shutil.which("gst-launch-1.0") is None:
            print("[!] gst-launch-1.0 not found.")
            print("[*] Install GStreamer:")
            print("    sudo apt install gstreamer1.0-tools "
                  "gstreamer1.0-plugins-good gstreamer1.0-plugins-bad "
                  "gstreamer1.0-plugins-ugly gstreamer1.0-libav")
            sys.exit(1)
    return backend


def _run_termux_x11_mpv(url):
    if not _start_x11():
        return "hardfail", 0.0

    env = _x11_env()

    print(f"[*] Launching mpv in Termux:X11 on {X11_DISPLAY}...")
    print("[*] Switch to the Termux:X11 app to watch.")
    print("[*] Press Ctrl+C in this terminal to stop.\n")

    start = time.time()
    variants = [
        ("GPU (x11egl)", _build_mpv_command(url, gpu=True)),
        ("x11 fallback", _build_mpv_command(url, gpu=False)),
    ]

    for label, cmd in variants:
        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("[!] mpv not found. Install with:")
            print("    pkg install mpv-x")
            return "hardfail", 0.0

        # give mpv time to fail fast if the vo/context is bad
        time.sleep(2.5)
        if proc.poll() is not None:
            print(f"[*] {label} failed to start, trying fallback...")
            continue

        try:
            while proc.poll() is None:
                time.sleep(0.2)
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("\n[*] Stopped.")
            return "interrupt", time.time() - start

        duration = time.time() - start
        if proc.returncode == 0:
            return "ok", duration
        if duration < HARD_FAIL_THRESHOLD:
            return "hardfail", duration
        return "fail", duration

    return "hardfail", time.time() - start


def _run_external_player(url, player):
    if IS_TERMUX:
        return _run_termux_x11_mpv(url)

    if player == "mpv":
        cmd = [
            "mpv",
            "--no-config",
            "--rtsp-transport=tcp",
            "--cache=yes",
            "--demuxer-max-bytes=4M",
            url,
        ]
    elif player == "ffplay":
        cmd = [
            "ffplay",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-framedrop",
            "-loglevel", "warning",
            url,
        ]
    else:
        print(f"[!] Unknown external player: {player}")
        return "fail", 0.0

    print(f"[*] Launching {player}...")
    print("[*] Press Ctrl+C in this terminal to stop playback.\n")

    start = time.time()
    try:
        proc = subprocess.Popen(cmd)
        try:
            while proc.poll() is None:
                time.sleep(0.2)
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("\n[*] Stopped.")
            return "interrupt", time.time() - start

        duration = time.time() - start
        if proc.returncode == 0:
            if duration >= STABILITY_GRACE:
                return "ok", duration
            return "fail", duration
        if duration < HARD_FAIL_THRESHOLD:
            return "hardfail", duration
        return "fail", duration

    except FileNotFoundError:
        print(f"[!] {player} not found in PATH.")
        return "hardfail", 0.0


# ---------------------------------------------------------------------------
# GStreamer backend (desktop Linux only)
# ---------------------------------------------------------------------------
_GST_ELEMENT_CACHE = {}


def _has_gst_element(name):
    if name in _GST_ELEMENT_CACHE:
        return _GST_ELEMENT_CACHE[name]
    try:
        result = subprocess.run(
            ["gst-inspect-1.0", name],
            capture_output=True, timeout=5,
        )
        found = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        found = False
    _GST_ELEMENT_CACHE[name] = found
    return found


def _append_deinterlace(branch):
    if _has_gst_element("deinterlace"):
        return branch + ["!", "deinterlace"]
    return branch


def _video_branch_for_codec(vcodec):
    vc = (vcodec or "").upper()
    if vc in ("H265", "HEVC"):
        if _has_gst_element("rtph265depay") and _has_gst_element("avdec_h265"):
            return _append_deinterlace([
                "r.", "!", "application/x-rtp,media=video,encoding-name=H265",
                "!", "rtph265depay", "!", "h265parse", "!", "avdec_h265",
            ]) + ["!", "videoconvert", "!", "autovideosink", "sync=false"]
    if vc in ("MP4V", "MP4V-ES"):
        if _has_gst_element("rtpmp4vdepay") and _has_gst_element("avdec_mpeg4"):
            return _append_deinterlace([
                "r.", "!", "application/x-rtp,media=video,encoding-name=MP4V-ES",
                "!", "rtpmp4vdepay", "!", "avdec_mpeg4",
            ]) + ["!", "videoconvert", "!", "autovideosink", "sync=false"]
    if vc == "JPEG":
        if _has_gst_element("rtpjpegdepay") and _has_gst_element("jpegdec"):
            return [
                "r.", "!", "application/x-rtp,media=video,encoding-name=JPEG",
                "!", "rtpjpegdepay", "!", "jpegdec",
                "!", "videoconvert", "!", "autovideosink", "sync=false",
            ]
    if _has_gst_element("rtph264depay") and _has_gst_element("avdec_h264"):
        return _append_deinterlace([
            "r.", "!", "application/x-rtp,media=video,encoding-name=H264",
            "!", "rtph264depay", "!", "h264parse", "!", "avdec_h264",
        ]) + ["!", "videoconvert", "!", "autovideosink", "sync=false"]
    return _append_deinterlace([
        "r.", "!", "application/x-rtp,media=video",
        "!", "decodebin",
    ]) + ["!", "videoconvert", "!", "autovideosink", "sync=false"]


def _video_branch_decodebin():
    return _append_deinterlace([
        "r.", "!", "application/x-rtp,media=video",
        "!", "decodebin",
    ]) + ["!", "videoconvert", "!", "autovideosink", "sync=false"]


def _build_pipeline(url, with_audio=True, transport="tcp", vcodec=None,
                    force_decodebin=False):
    rtspsrc = [
        "rtspsrc", f"location={url}",
        f"latency={RTSP_LATENCY}",
        f"protocols={transport}",
        f"user-agent={RTSP_USER_AGENT}",
        "do-rtsp-keep-alive=true",
        "do-retransmission=false",
        "buffer-mode=auto",
        "timeout=10000000",
        "ntp-sync=false",
    ]

    if force_decodebin:
        video_branch = _video_branch_decodebin()
    else:
        video_branch = _video_branch_for_codec(vcodec)

    audio_branch = None
    if with_audio:
        if _has_gst_element("rtppcmadepay") and _has_gst_element("alawdec"):
            audio_branch = [
                "r.", "!", "application/x-rtp,media=audio,encoding-name=PCMA",
                "!", "rtppcmadepay", "!", "alawdec",
                "!", "audioconvert", "!", "audioresample",
                "!", "autoaudiosink",
            ]
        elif _has_gst_element("rtppcmudepay") and _has_gst_element("mulawdec"):
            audio_branch = [
                "r.", "!", "application/x-rtp,media=audio,encoding-name=PCMU",
                "!", "rtppcmudepay", "!", "mulawdec",
                "!", "audioconvert", "!", "audioresample",
                "!", "autoaudiosink",
            ]

    cmd = ["gst-launch-1.0", "-e", *rtspsrc, "name=r", *video_branch]
    if audio_branch:
        cmd.extend(audio_branch)
    return cmd


def _run_gstreamer(cmd, label, startup_timeout=PLAYER_STARTUP_TIMEOUT):
    print(f"[*] Starting: {label}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        print(f"[!] {label} not found: {exc}")
        return ("hardfail", 0.0)

    start = time.time()
    started_playing = False
    killed_for_stall = False

    try:
        while proc.poll() is None:
            try:
                ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            except (OSError, ValueError):
                ready = []

            if ready:
                line = proc.stdout.readline()
                if line:
                    line = line.rstrip()
                    print(f"    [{label}] {line}")
                    if not started_playing and (
                        "Setting pipeline to PLAYING" in line
                        or "Pipeline is PLAYING" in line
                    ):
                        started_playing = True
                        print(f"[+] {label} reached PLAYING.")

            if (not started_playing
                    and time.time() - start > startup_timeout):
                print(f"[!] {label} stuck for {startup_timeout:.0f}s "
                      f"before PLAYING, killing.")
                killed_for_stall = True
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                break
    except KeyboardInterrupt:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        return ("interrupt", time.time() - start)

    duration = time.time() - start
    returncode = proc.returncode

    if killed_for_stall:
        return ("hardfail", duration)
    if returncode != 0:
        print(f"[!] {label} exited with code {returncode} after "
              f"{duration:.1f}s")
        if duration < HARD_FAIL_THRESHOLD:
            return ("hardfail", duration)
        return ("fail", duration)
    if duration >= STABILITY_GRACE:
        return ("ok", duration)
    return ("fail", duration)


# ---------------------------------------------------------------------------
# play() dispatches to the correct backend
# ---------------------------------------------------------------------------
def play(ip, path, with_audio=True, has_audio=True, vcodec=None):
    url = f"rtsp://{ip}:554{path}"
    print(f"[*] Playing (LIVE): {url}")
    print(f"[*] Video codec: {vcodec or 'auto'}")
    print(f"[*] Backend: {PLAYER_BACKEND}")
    print("[*] Press Ctrl+C to stop.\n")

    if PLAYER_BACKEND == "x11-mpv":
        while True:
            status, dur = _run_termux_x11_mpv(url)
            if status == "interrupt":
                return
            if status == "ok":
                print(f"[*] Stream ended after {dur:.1f}s. Reconnecting...")
                time.sleep(2)
                continue
            print(f"[!] Player exited with status {status} after {dur:.1f}s.")
            print("[!] Returning to menu.")
            return

    if PLAYER_BACKEND in ("mpv", "ffplay"):
        while True:
            status, dur = _run_external_player(url, PLAYER_BACKEND)
            if status == "interrupt":
                return
            if status == "ok":
                print(f"[*] Stream dropped after {dur:.1f}s. Reconnecting...")
                time.sleep(2)
                continue
            print(f"[!] Player exited with status {status} after {dur:.1f}s.")
            print("[!] Returning to menu.")
            return

    audio_label = " + audio" if (with_audio and has_audio) else ""
    variants = [
        (f"GStreamer TCP{audio_label} (codec: {vcodec or 'auto'})",
         _build_pipeline(url, with_audio and has_audio, "tcp", vcodec)),
        ("GStreamer TCP video-only (codec: "
         f"{vcodec or 'auto'})",
         _build_pipeline(url, False, "tcp", vcodec)),
        (f"GStreamer TCP{audio_label} (decodebin)",
         _build_pipeline(url, with_audio and has_audio, "tcp", None, True)),
        ("GStreamer TCP video-only (decodebin)",
         _build_pipeline(url, False, "tcp", None, True)),
        (f"GStreamer UDP{audio_label} (codec: {vcodec or 'auto'})",
         _build_pipeline(url, with_audio and has_audio, "udp", vcodec)),
        ("GStreamer UDP video-only (codec: "
         f"{vcodec or 'auto'})",
         _build_pipeline(url, False, "udp", vcodec)),
    ]

    working_idx = None
    hard_failed = set()

    try:
        while True:
            if working_idx is not None:
                label, cmd = variants[working_idx]
                status, dur = _run_gstreamer(cmd, label)
                if status == "interrupt":
                    print("\n[*] Stopped.")
                    return
                if status == "ok":
                    print(f"[*] Stream dropped after {dur:.1f}s. "
                          f"Reconnecting with {label}...")
                    time.sleep(2)
                    continue
                if status == "hardfail":
                    print(f"[!] {label} hard-failed, URL/path is bad.")
                    hard_failed.add(working_idx)
                    working_idx = None
                    continue
                print(f"[!] {label} failed in {dur:.1f}s, "
                      f"re-testing all variants.")
                working_idx = None
                continue

            print("[*] Finding a working player variant...")
            for i, (label, cmd) in enumerate(variants):
                if i in hard_failed:
                    print(f"[*] Skipping {label} (hard-failed earlier)")
                    continue
                status, dur = _run_gstreamer(cmd, label)
                if status == "interrupt":
                    print("\n[*] Stopped.")
                    return
                if status == "ok":
                    working_idx = i
                    print(f"[+] {label} works. Streaming live.")
                    break
                if status == "hardfail":
                    hard_failed.add(i)
                    print(f"[*] {label} hard-failed, skipping in future.")
                    continue
                print(f"[*] {label} failed in {dur:.1f}s.")

            if working_idx is None:
                if len(hard_failed) == len(variants):
                    print("[!] Every variant hard-failed. The path "
                          f"'{path}' is not usable on this camera.")
                    print("[!] Returning to menu, try a different path.")
                    return
                print("[!] No variant survived "
                      f"{STABILITY_GRACE:.0f}s. Retrying in 3s...")
                time.sleep(3)

    except KeyboardInterrupt:
        print("\n[*] Stopped.")


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------
def try_paths(ip, paths):
    for path in paths:
        answer = input(f"[?] Try {path}? [Y/n/q] ").strip().lower()
        if answer == "q":
            return
        if answer == "n":
            continue
        play(ip, path, has_audio=True, vcodec=None)
        worked = input("[?] Did the stream play? [y/N] ").strip().lower()
        if worked == "y":
            return


def _try_vendor_variants(ip, vendor, detected_vcodec=None):
    variants = VENDOR_PATH_VARIANTS.get(vendor)
    if not variants:
        variants = [VENDOR_PATHS[vendor]]

    print(f"[*] Testing {len(variants)} {vendor} path variant(s)...")

    for vpath in variants:
        print(f"\n[*] Checking: {vpath}")
        sdp = _rtsp_exchange(ip, vpath, timeout=3, teardown=True)
        if not sdp:
            print("[-] No response.")
            continue
        if _response_is_error(sdp):
            head = sdp.splitlines()[0] if sdp else ""
            print(f"[-] Error response: {head}")
            continue
        if "m=video" not in sdp:
            print("[-] No video track in SDP.")
            continue

        vcodec = _parse_video_codec(sdp)
        has_audio = "m=audio" in sdp
        acodec = _parse_audio_codec(sdp) if has_audio else None
        if acodec == "unknown":
            has_audio = False

        print(f"[+] Variant returns SDP. codec={vcodec} "
              f"audio={'yes' if has_audio else 'no'}")
        play(ip, vpath, has_audio=has_audio, vcodec=vcodec)
        return True

    print(f"[!] No {vendor} variant returned valid SDP.")
    return False


# ---------------------------------------------------------------------------
# Vendor detection
# ---------------------------------------------------------------------------
def _match_vendor(text):
    lowered = text.lower()
    for keyword, vendor in VENDOR_KEYWORDS:
        if keyword in lowered:
            return vendor
    return None


def detect_vendor(ip, timeout=120):
    print(f"[*] Running nmap version scan (may take up to {timeout}s)...")
    try:
        result = subprocess.run(
            ["nmap", "-sV", "-p", "554", "--version-all", ip],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        print("[!] nmap not found.")
        return probe_rtsp_banner(ip)
    except subprocess.TimeoutExpired:
        print("[!] nmap timed out. Falling back to RTSP banner probe.")
        return probe_rtsp_banner(ip)

    print(result.stdout)
    vendor = _match_vendor(result.stdout)
    if vendor:
        print(f"[+] Detected vendor from nmap: {vendor}")
        return vendor
    return probe_rtsp_banner(ip)


def probe_rtsp_banner(ip):
    request = (f"OPTIONS rtsp://{ip}:554/ RTSP/1.0\r\n"
               f"CSeq: 1\r\n"
               f"User-Agent: {RTSP_USER_AGENT}\r\n\r\n")
    try:
        with socket.create_connection((ip, 554), timeout=5) as sock:
            sock.sendall(request.encode())
            data = sock.recv(4096).decode(errors="ignore")
    except Exception as exc:
        print(f"[!] RTSP probe failed: {exc}")
        return None
    print("[*] RTSP banner:")
    print(data)
    vendor = _match_vendor(data)
    if vendor:
        print(f"[+] Detected vendor from RTSP banner: {vendor}")
        return vendor
    return None


def list_vendors():
    vendors = sorted(VENDOR_PATHS.keys())
    for i, vendor in enumerate(vendors, start=1):
        print(f"  {i:>2}. {vendor}")
    return vendors


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
def menu(ip, detected_path=None, detected_has_audio=False, detected_vcodec=None):
    while True:
        print("\n=== RTSP Camera Viewer ===")
        print(f"Target: {ip}")
        print(f"Backend: {PLAYER_BACKEND}")

        options = []
        if detected_path:
            audio_tag = " + audio" if detected_has_audio else " (video only)"
            codec_tag = f" [{detected_vcodec}]" if detected_vcodec else ""
            options.append((
                f"Connect using detected path: {detected_path}"
                f"{codec_tag}{audio_tag}",
                "play_detected"
            ))
        options.extend([
            ("I know the vendor", "vendor"),
            ("Auto-detect vendor (nmap -sV)", "auto"),
            ("Try common paths blindly", "blind"),
            ("Enter a custom RTSP path", "custom"),
            ("Change target IP", "change_ip"),
            ("Check speaker (ONVIF backchannel)", "check_speaker"),
            ("Re-check mic on current IP", "recheck"),
            ("Re-check with verbose path output", "recheck_verbose"),
            ("Quit", "quit"),
        ])

        for i, (label, _) in enumerate(options, start=1):
            print(f"  {i}. {label}")

        choice = input("> ").strip()
        if not choice.isdigit():
            print("[!] Invalid choice.")
            continue
        idx = int(choice) - 1
        if idx < 0 or idx >= len(options):
            print("[!] Out of range.")
            continue

        action = options[idx][1]

        if action == "play_detected":
            play(ip, detected_path,
                 has_audio=detected_has_audio,
                 vcodec=detected_vcodec)

        elif action == "vendor":
            vendors = list_vendors()
            pick = input("Pick number: ").strip()
            if not pick.isdigit():
                print("[!] Invalid choice.")
                continue
            vidx = int(pick) - 1
            if vidx < 0 or vidx >= len(vendors):
                print("[!] Out of range.")
                continue
            vkey = vendors[vidx]
            if not _try_vendor_variants(ip, vkey, detected_vcodec):
                print("[*] Falling back to single path attempt.")
                play(ip, VENDOR_PATHS[vkey],
                     has_audio=True, vcodec=detected_vcodec)

        elif action == "auto":
            vendor = detect_vendor(ip)
            if vendor:
                if not _try_vendor_variants(ip, vendor, detected_vcodec):
                    print("[*] Falling back to blind path trial.")
                    try_paths(ip, FALLBACK_PATHS)
            else:
                print("[*] Falling back to blind path trial.")
                try_paths(ip, FALLBACK_PATHS)

        elif action == "blind":
            try_paths(ip, FALLBACK_PATHS)

        elif action == "custom":
            path = input("Path (e.g. /11): ").strip()
            if not path.startswith("/"):
                path = "/" + path
            play(ip, path, has_audio=True, vcodec=detected_vcodec)

        elif action == "change_ip":
            new_ip = input("New IP: ").strip()
            if not is_valid_ipv4(new_ip):
                print("[!] Invalid IPv4 address.")
                continue
            ip = new_ip
            detected_path, detected_has_audio, detected_vcodec = report_mic(ip)

        elif action == "check_speaker":
            if not detected_path:
                print("[!] No detected path, run re-check first.")
                continue
            print(f"[*] Checking speaker on {detected_path}...")
            has_speaker, spk_codec = probe_speaker(ip, detected_path)
            if has_speaker:
                print(f"[+] Speaker: PRESENT (backchannel codec: {spk_codec})")
            else:
                print("[-] Speaker: NOT PRESENT (no ONVIF backchannel)")

        elif action == "recheck":
            detected_path, detected_has_audio, detected_vcodec = report_mic(ip)

        elif action == "recheck_verbose":
            detected_path, detected_has_audio, detected_vcodec = report_mic(
                ip, verbose=True)

        elif action == "quit":
            print("Bye.")
            return


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ensure_player_available()

    if IS_TERMUX:
        print(f"[*] Termux detected. Backend: {PLAYER_BACKEND}")
        print(f"[*] X11 display: {X11_DISPLAY}")
        print(f"[*] XDG_RUNTIME_DIR: {os.environ.get('XDG_RUNTIME_DIR')}")
        print("[*] Make sure the Termux:X11 app is installed and ready.")
    else:
        print(f"[*] Desktop Linux. Backend: {PLAYER_BACKEND}")

    while True:
        ip = input("Enter IP: ").strip()
        if not ip:
            print("[!] No IP given.")
            continue
        if not is_valid_ipv4(ip):
            print(f"[!] '{ip}' is not a valid IPv4 address.")
            continue
        break

    detected_path, detected_has_audio, detected_vcodec = report_mic(ip)
    menu(ip, detected_path, detected_has_audio, detected_vcodec)


if __name__ == "__main__":
    main()