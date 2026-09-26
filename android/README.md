# RTSP Camera Viewer for Android

A mobile adaptation of the RTSP camera viewer and diagnostic tool. Designed to run on Android via **Termux**, utilizing `mpv` inside **Termux:X11** for stream rendering (no root access required).

> **⚠️ LEGAL WARNING**
> Intended **only** for use on your own network and on devices you own or have explicit, written permission to test. See the main [README](../README.md) for details.

---

## Requirements

- **Android Device** (Android 8.0 or higher)
- **Termux** app (installed from F-Droid, *do not use the obsolete Google Play version*)
- **Termux:X11 Android App** (APK downloaded from the official GitHub releases)
- **Python 3.7+** and **mpv** packages inside Termux

---

## Setting Up Termux:X11 & Dependencies

To enable graphical stream rendering via `mpv`, you must set up the Termux X11 server environment.

### Step 1: Install Termux:X11 App
1. Download the latest `termux-x11-universal-debug.apk` (or architecture-specific APK) from the [Termux:X11 GitHub Releases page](https://github.com/termux/termux-x11/releases). 

2. Install the APK on your Android device (ensure "Install from unknown sources" is allowed for your browser/file manager).

### Step 2: Install Termux Packages
Open your Termux terminal app and run the following commands to install Python, the X11 repository, the X11 companion package, and `mpv`:

```bash
pkg update && pkg upgrade
pkg install x11-repo -y
pkg install termux-x11-nightly mpv-x python -y
pkg install xorg-xdpyinfo -y
```

## Installation

### 1. Clone the repo
```bash
git clone https://github.com/jacobP-cyberdev/rtsp-camera-viewer.git
cd rtsp-camera-viewer/android
```
Go to the directory 
```bash
cd rtsp-camera-viewer/android
```
>**If this throws an error**
>Make sure you navigate to the right directory from where it was downloaded

### 2. Open the X11 app before running the script

### 3. Run the script
```bash
python3 connect.py
```

### Help
If the X11 player is ever showing a black screen, you most likely need to refresh it.

```bash

```