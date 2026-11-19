# app_paths.py
# ---------------------------------------------------------
# Where the program finds / saves its files, so it behaves the same
# whether you run `python3 login_app.py` or the packaged app.
#
#   user_data_dir()  - a per-user folder for settings (theme_prefs.json).
#                      A packaged app's own folder can be temporary or
#                      read-only, so settings must NOT live there.
#   find_resource()  - looks for a file like chat.key next to the app,
#                      then inside the bundle, then in the current folder.
# ---------------------------------------------------------

import os
import sys

APP_NAME = "ChatClient"


def app_dir() -> str:
    """Folder the app lives in (the exe's folder when packaged, this folder otherwise)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir() -> str:
    """Where PyInstaller unpacks files that were bundled inside the app."""
    return getattr(sys, "_MEIPASS", app_dir())


def user_data_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return app_dir()
    return path


def find_resource(name: str) -> str:
    """Full path of `name`, or just `name` if it can't be found (so the error message stays clear)."""
    for folder in (app_dir(), bundle_dir(), user_data_dir(), os.getcwd()):
        candidate = os.path.join(folder, name)
        if os.path.exists(candidate):
            return candidate
    return name


def set_app_icon(root) -> None:
    """Give every window the chat-bubble icon (title bar corner + taskbar). Never raises: no icon is fine."""
    try:
        if sys.platform.startswith("win"):
            try:                                   # so the taskbar shows OUR icon, not Python's
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChatClient.App")
            except Exception:
                pass
            ico = find_resource("icon.ico")
            if os.path.exists(ico):
                root.iconbitmap(default=ico)
                return
        png = find_resource("icon.png")
        if os.path.exists(png):
            import tkinter as tk
            root._app_icon = tk.PhotoImage(file=png)      # keep a reference or Tk drops it
            root.iconphoto(True, root._app_icon)           # True = also for every window opened later
    except Exception:
        pass
