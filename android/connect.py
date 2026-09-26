#!/usr/bin/env python3
"""
RTSP camera viewer for Android via Termux + Termux:X11 + mpv.

Playback flow:
  1. Start termux-x11 on :0 (kills old sessions first)
  2. Verify the server answers on the socket
  3. Launch mpv inside the X11 display
  4. Read mpv's log to confirm a video output was opened
  5. If mpv fails to render, try the fallback VO and report the log
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


# Environment setup

if "com.termux" in os.environ.get("PREFIX", ""):
    _PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    os.environ.setdefault("XDG_RUNTIME_DIR", os.path.join(_PREFIX, "tmp"))


# Tuning

PROBE_WORKERS = 12
PROBE_TIMEOUT = 2
STABILITY_GRACE = 6.0
HARD_FAIL_THRESHOLD = 2.0
RTSP_USER_AGENT = "LIVE555 Streaming Media v2016.11.28"
X11_DISPLAY = ":0"
X11_STARTUP_WAIT = 8.0
MPV_VO_WAIT = 8.0


# Platform detection

IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")

if not IS_TERMUX:
    print("[!] This script is built for Termux on Android.")
    print("[*] Use the Linux version for desktop systems.")
    sys.exit(1)

PLAYER_BACKEND = "x11-mpv"


# Priority paths

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
    "/11",
    "/axis-media/media.amp",
    "/mpeg/media.amp",
    "/h264Preview_01_main",
    "/live/ch0",
    "/videoMain",
]

PRIORITY_WORKERS = 4
PRIORITY_GRACE = 2.0


# Vendor -> primary path

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


# Multi-variant paths per vendor

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


# Validation

IP_REGEX = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"
)


def is_valid_ipv4(ip):
    return bool(IP_REGEX.match(ip.strip()))



# Path scoring

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



# Probing

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



# Termux:X11 helpers

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


def _mpv_log_path():
    prefix = os.environ.get("PREFIX", "/tmp")
    return os.path.join(prefix, "tmp", "mpv-camera.log")


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
    time.sleep(0.8)


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


def _x11_pid():
    """Return PID of the running termux-x11 process, or None."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "termux-x11"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().split()[0])
    except Exception:
        pass
    return None


def _x11_socket_alive():
    """True if the X server actually answers on the socket."""
    try:
        result = subprocess.run(
            ["xdpyinfo"],
            env=_x11_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return os.path.exists(_x11_socket_path())
    except Exception:
        return False


def _x11_is_running():
    """True only if the process is alive AND the socket answers."""
    if _x11_pid() is None:
        return False
    return _x11_socket_alive()


def _start_x11():
    # Reuse an already-healthy server
    if _x11_is_running():
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

    # Wait for the socket file to appear
    socket_path = _x11_socket_path()
    deadline = time.time() + X11_STARTUP_WAIT
    while time.time() < deadline:
        if os.path.exists(socket_path):
            break
        time.sleep(0.3)
    else:
        print("[!] Termux:X11 did not come up in time.")
        print("[*] Open the Termux:X11 app on your phone, then retry.")
        return False

    # Verify the server answers, not just that the socket exists
    if not _x11_socket_alive():
        print("[!] Termux:X11 socket exists but the server is not responding.")
        print("[*] Open the Termux:X11 app on your phone and try again.")
        return False

    print(f"[+] Termux:X11 ready on {X11_DISPLAY}.")
    print("[*] Open the Termux:X11 app on your phone to see video.")
    return True


def _build_mpv_command(url, gpu=True):
    base = [
        "mpv",
        "--no-config",
        "--rtsp-transport=tcp",
        "--no-input-default-bindings",
        "--input-terminal=no",
        "--osc=no",
        "--msg-level=all=info",
    ]
    if gpu:
        base += ["--vo=gpu", "--gpu-context=x11egl"]
    else:
        base += ["--vo=x11"]
    base.append(url)
    return base


def _mpv_vo_ready(log_path):
    """True if the mpv log shows a video output was successfully opened."""
    try:
        with open(log_path, "r", errors="ignore") as f:
            content = f.read()
    except Exception:
        return False
    markers = (
        "VO: [gpu]",
        "VO: [x11]",
        "Using hardware decoding",
        "Using software decoding",
    )
    return any(m in content for m in markers)



# Player

def ensure_player_available():
    if shutil.which("mpv") is None:
        print("[!] mpv is not installed.")
        print("[*] Install with:")
        print("    pkg install x11-repo")
        print("    pkg install termux-x11-nightly")
        print("    pkg install mpv-x")
        sys.exit(1)
    if shutil.which("termux-x11") is None:
        print("[!] termux-x11 is not installed.")
        print("[*] Install with:")
        print("    pkg install x11-repo")
        print("    pkg install termux-x11-nightly")
        sys.exit(1)


def _run_termux_x11_mpv(url):
    if not _start_x11():
        return "hardfail", 0.0

    env = _x11_env()
    log_path = _mpv_log_path()

    print(f"[*] Launching mpv in Termux:X11 on {X11_DISPLAY}...")
    print(f"[*] mpv log: {log_path}")
    print("[*] Switch to the Termux:X11 app to watch.")
    print("[*] Press Ctrl+C in this terminal to stop.\n")

    start = time.time()
    variants = [
        ("GPU (x11egl)", _build_mpv_command(url, gpu=True)),
        ("x11 fallback", _build_mpv_command(url, gpu=False)),
    ]

    for label, cmd in variants:
        # Truncate the log for this attempt
        try:
            log_file = open(log_path, "w")
        except Exception:
            log_file = subprocess.DEVNULL

        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("[!] mpv not found. Install with:")
            print("    pkg install mpv-x")
            if hasattr(log_file, "close"):
                log_file.close()
            return "hardfail", 0.0

        # Wait up to MPV_VO_WAIT for mpv to die or open a VO
        vo_ready = False
        deadline = time.time() + MPV_VO_WAIT
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if _mpv_vo_ready(log_path):
                vo_ready = True
                break
            time.sleep(0.3)

        if proc.poll() is not None:
            print(f"[*] {label} exited before opening a video output.")
            print(f"    See {log_path} for details.")
            if hasattr(log_file, "close"):
                log_file.close()
            continue

        if not vo_ready:
            print(f"[*] {label} did not open a video output in "
                  f"{MPV_VO_WAIT:.0f}s.")
            print(f"    See {log_path} for details.")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            if hasattr(log_file, "close"):
                log_file.close()
            continue

        # mpv is rendering. Wait for it to finish.
        print(f"[+] {label} is rendering. Enjoy the stream.")
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
            if hasattr(log_file, "close"):
                log_file.close()
            return "interrupt", time.time() - start

        duration = time.time() - start
        if hasattr(log_file, "close"):
            log_file.close()

        if proc.returncode == 0:
            return "ok", duration
        if duration < HARD_FAIL_THRESHOLD:
            return "hardfail", duration
        return "fail", duration

    return "hardfail", time.time() - start



# play() dispatcher

def play(ip, path, with_audio=True, has_audio=True, vcodec=None):
    url = f"rtsp://{ip}:554{path}"
    print(f"[*] Playing (LIVE): {url}")
    print(f"[*] Video codec: {vcodec or 'auto'}")
    print(f"[*] Backend: {PLAYER_BACKEND}")
    print("[*] Press Ctrl+C to stop.\n")

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



# Menu helpers

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



# Vendor detection

def _match_vendor(text):
    lowered = text.lower()
    for keyword, vendor in VENDOR_KEYWORDS:
        if keyword in lowered:
            return vendor
    return None


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



# Menu

def menu(ip, detected_path=None, detected_has_audio=False, detected_vcodec=None):
    while True:
        print("\n=== RTSP Camera Viewer (Android) ===")
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
            ("Probe RTSP banner (vendor hint)", "banner"),
            ("Try common paths blindly", "blind"),
            ("Enter a custom RTSP path", "custom"),
            ("Change target IP", "change_ip"),
            ("Check speaker (ONVIF backchannel)", "check_speaker"),
            ("Re-check mic on current IP", "recheck"),
            ("Re-check with verbose path output", "recheck_verbose"),
            ("Restart X11 viewer", "restart_x11"),
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

        elif action == "banner":
            vendor = probe_rtsp_banner(ip)
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

        elif action == "restart_x11":
            print("[*] Restarting Termux:X11...")
            _kill_x11()
            _clean_x11_sockets()
            if _start_x11():
                print("[+] Viewer restarted. Try playing again.")
            else:
                print("[!] Restart failed. Open the Termux:X11 app and retry.")

        elif action == "quit":
            print("Bye.")
            return



# Main

def main():
    ensure_player_available()

    print(f"[*] Termux detected. Backend: {PLAYER_BACKEND}")
    print(f"[*] X11 display: {X11_DISPLAY}")
    print(f"[*] XDG_RUNTIME_DIR: {os.environ.get('XDG_RUNTIME_DIR')}")
    print(f"[*] mpv log: {_mpv_log_path()}")
    print()
    print("[!] The Termux:X11 app must be OPEN before starting playback.")
    print("[!] If it is not open, the screen will stay black.")
    print("[*] Open Termux:X11 now, leave it running, then continue.")
    print()

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