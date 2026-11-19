# notifier.py
# ---------------------------------------------------------
# Alerts for when the app is open but you're not looking at it: a pop-up in the corner of the screen,
# a flashing taskbar button, and the on/off switches for them (saved per person on this computer).
# Nothing here can crash the chat: every function swallows its own errors.
# ---------------------------------------------------------

import json
import os
import shutil
import subprocess
import sys
import threading

import app_paths

DEFAULTS = {"toast": True, "preview": True, "flash": True, "sound": True}
PREFS_FILE = os.path.join(app_paths.user_data_dir(), "notify_prefs.json")


class Prefs:
    def __init__(self, path: str = PREFS_FILE):
        self.path = path
        self.values = dict(DEFAULTS)
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            for key in DEFAULTS:
                if isinstance(saved.get(key), bool):
                    self.values[key] = saved[key]
        except (OSError, ValueError, AttributeError):
            pass

    def get(self, key: str) -> bool:
        return bool(self.values.get(key, DEFAULTS.get(key, False)))

    def set(self, key: str, value: bool):
        if key not in DEFAULTS:
            return
        self.values[key] = bool(value)
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.values, f)
        except OSError:
            pass


def clean(text, limit: int) -> str:
    """One short line of plain text: no control characters, cut to `limit`."""
    text = "".join(ch if ch.isprintable() else " " for ch in str(text or ""))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def show_toast(title: str, body: str = "") -> None:
    """Pop-up notification. Runs in its own thread because some systems hold the call open for a few seconds."""
    title, body = clean(title, 60) or "Chat Room", clean(body, 200)

    def run():
        try:
            icon = app_paths.find_resource("icon.ico")
            if sys.platform.startswith("win"):
                from plyer import notification
                notification.notify(title=title, message=body or " ", app_name="Chat Client",
                                    app_icon=icon if os.path.exists(icon) else "", timeout=6)
            elif sys.platform == "darwin":
                script = f"display notification {json.dumps(body, ensure_ascii=False)} " \
                         f"with title {json.dumps(title, ensure_ascii=False)}"
                subprocess.run(["osascript", "-e", script], timeout=5)
            elif shutil.which("notify-send"):
                png = app_paths.find_resource("icon.png")
                cmd = ["notify-send", "-a", "Chat Client"]
                if os.path.exists(png):
                    cmd += ["-i", png]
                subprocess.run(cmd + [title, body], timeout=5)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def flash_taskbar(window) -> None:
    """Windows: make the app's taskbar button flash until the person clicks it. Other systems: nothing."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        user32.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        # 0x2 = flash the taskbar button, 0xC = keep flashing until the window comes to the front
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x2 | 0xC, 0, 0)
        user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass
