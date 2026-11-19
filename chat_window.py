# chat_window.py
# ---------------------------------------------------------
# The chat GUI. Structure:
#
#   ChatWindow           - owns the socket + background reader
#                           thread, the presence sidebar, and
#                           a Notebook of MessagePanes (one for
#                           the room, one per open DM).
#   MessagePane           - one scrollable conversation: the
#                           message log, typing indicator,
#                           entry box, and Send/Attach buttons.
#                           Used for both the room and DMs.
#
# Everything the server sends arrives as a dict (see protocol.py)
# on a background thread, gets pushed into a queue, and is only
# ever touched by the Tk main loop via _poll_incoming -- Tkinter
# is not thread-safe, so this is the one safe way to get data
# from the network thread onto the screen.
# ---------------------------------------------------------

import base64
import io
import math
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from tkinter import colorchooser, filedialog, scrolledtext, ttk
import tkinter as tk

from cryptography.fernet import InvalidToken

import zlib

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk   # pip install Pillow  (lets us show JPG/WEBP/etc.)
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

import crypto_utils
import account_api
import games
import protocol as proto
import popup_kit
import themes
import ui_kit as ui
from popup_kit import PillButton, RoundEntry, Themer, add_header, messagebox, simpledialog
from language_settings import LANGUAGE_NAMES, language_name, load_language, save_language
from onscreen_keyboard import LAYOUTS as KEYBOARD_LAYOUTS, DEFAULT_LANGUAGE as KEYBOARD_DEFAULT, KeyboardPanel
from money import format_cents, is_stripe_url, parse_amount_to_cents
from secure_connection import SecureConnectionError, connect_secure
from ai_friend_window import AIFriendWindow
from feed_window import FeedWindow
from roll_animation import RollAnimation
from wallet_window import PaymentPrompt, WalletWindow, note_suffix

try:                                         # offline translation (see translator.py / install_languages.py)
    import translator
except ImportError:                          # the file is missing: the Language menu then says so
    translator = None
from password_policy import check_password_strength, strength_label
from protocol import JSONStreamReader, send_json

TRANSLATING_NOTICE_MS = 500      # still translating after this long -> show a "Translating…" line

USER_COLORS = [
    "#e06c75", "#61afef", "#98c379", "#e5c07b",
    "#c678dd", "#56b6c2", "#d19a66",
]
REACTION_EMOJI = ["👍", "❤️", "😂", "😮", "😢", "🎉"]
DOWNLOADS_DIR = "downloads"
YOU_COLOR = "#43b581"   # your own name until you pick a color

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MAX_THUMB = (320, 240)                 # biggest an image is drawn in the chat (click for full size)
AUTO_IMAGE_MAX_BYTES = 3 * 1024 * 1024 # history images bigger than this wait for right-click > Download
AUTO_IMAGE_MAX_COUNT = 10              # only auto-load this many of the newest history images
AVATAR_STORE = 48                      # profile pictures are shrunk to this many pixels before sending
AVATAR_SHOW = 24                       # ...and drawn this big next to each message


def is_too_light(hex_color: str) -> bool:
    """True if a color would be hard to read on the light chat background."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 200


def _lanczos():
    return getattr(Image, "Resampling", Image).LANCZOS     # name differs between Pillow versions


def _round_edges(im, size: int):
    """Give a square RGBA image a smooth circular edge."""
    big = Image.new("L", (size * 4, size * 4), 0)           # drawn 4x bigger, then shrunk = anti-aliased
    ImageDraw.Draw(big).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    im = im.copy()
    im.putalpha(big.resize((size, size), _lanczos()))
    return im


def make_avatar_b64(path: str) -> str:
    """Any image file -> centered square crop, AVATAR_STORE px, as base64 PNG text."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGBA")
        im = ImageOps.fit(im, (AVATAR_STORE, AVATAR_STORE), _lanczos())
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


POP_AVATAR_COLORS = ["#6C4DFF", "#FF4F9A", "#FF8A3D", "#14B8A6", "#3B82F6", "#A855F7", "#EF4444", "#22A06B"]


def _default_avatar_image(letter: str, size: int):
    """Colored circle with the person's initial, for people without a picture."""
    big = size * 4
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.ellipse((0, 0, big - 1, big - 1), fill=POP_AVATAR_COLORS[ord(letter[:1] or "?") % len(POP_AVATAR_COLORS)])
    try:
        font = ImageFont.load_default(size=int(big * 0.55))
        box = draw.textbbox((0, 0), letter, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        draw.text(((big - w) / 2 - box[0], (big - h) / 2 - box[1]), letter, font=font, fill="white")
    except Exception:
        pass                                                # older Pillow: a plain grey circle is fine
    return im.resize((size, size), _lanczos())


def avatar_photo(b64: str | None, size: int, letter: str = "?"):
    """A round Tk image `size` px wide: their picture if they have one, else the
    grey initial circle. Returns None if nothing can be drawn (e.g. no Pillow)."""
    if b64:
        try:
            if HAVE_PIL:
                with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
                    im = im.convert("RGBA").resize((size, size), _lanczos())
                return ImageTk.PhotoImage(_round_edges(im, size))
            img = tk.PhotoImage(data=b64)                   # Tk reads PNG itself; no rounding without Pillow
            return img.subsample(max(1, img.width() // size))
        except Exception:
            pass                                            # damaged picture -> fall through to the default
    if HAVE_PIL:
        try:
            return ImageTk.PhotoImage(_default_avatar_image(letter, size))
        except Exception:
            return None
    return None


def is_image_name(name: str | None) -> bool:
    return os.path.splitext(name or "")[1].lower() in IMAGE_EXTS


def load_thumbnail(path: str):
    """A Tk-ready image no bigger than MAX_THUMB, or None if it can't be shown."""
    try:
        if HAVE_PIL:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)   # phone photos come in rotated
                im = im.convert("RGBA")
                im.thumbnail(MAX_THUMB)            # shrinks in place, keeps aspect ratio
                return ImageTk.PhotoImage(im)
        # No Pillow: Tk itself can only read PNG and GIF.
        img = tk.PhotoImage(file=path)
        factor = max(1, math.ceil(img.width() / MAX_THUMB[0]), math.ceil(img.height() / MAX_THUMB[1]))
        return img.subsample(factor) if factor > 1 else img
    except Exception:
        return None


FEED_KINDS = {proto.FEED, proto.POST_NEW, proto.POST_IMAGE, proto.POST_LIKES, proto.COMMENT_NEW,
              proto.COMMENT_GONE, proto.POST_GONE}


def color_for_username(username: str) -> str:
    # zlib.crc32 is stable across runs/machines (built-in hash() is randomized per process)
    return USER_COLORS[zlib.crc32(username.encode("utf-8")) % len(USER_COLORS)]


def open_file_externally(path: str):
    """Open a downloaded file with whatever the OS considers the default app."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as e:
        messagebox.showerror("Couldn't open file", str(e))


def human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB"):
        if num_bytes < 1024 or unit == "MB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes/1024:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} MB"


# ─────────────────────────────────────────────────────────────
# EMOJI, LINKS AND @MENTIONS (pure helpers, no GUI)
# ─────────────────────────────────────────────────────────────

EMOJI_FONT = ("Segoe UI Emoji", 14)
EMOJI_CATEGORIES = [
    ("😀", "Smileys", "😀 😃 😄 😁 😆 😅 😂 🤣 🙂 😉 😊 😇 🥰 😍 🤩 😘 😋 😛 😜 🤪 😎 🤓 🥳 😏 "
                      "😒 😞 😔 😟 😕 🙁 😣 😖 😫 😩 🥺 😢 😭 😤 😠 😡 🤯 😳 🥵 🥶 😱 😨 😰 😥 "
                      "😓 🤗 🤔 🤭 🤫 🙄 😬 😴 🤤 😷 🤒 🤕 🤢 🤮 🥴 😵 🤠 🤡 💩 👻 💀 👽 🤖"),
    ("👍", "Hands", "👍 👎 👌 ✌ 🤞 🤟 🤘 👋 🤚 ✋ 👏 🙌 👐 🤲 🙏 💪 👀 🤝 💅 🤷 🤦 🙋 🙇 🫶"),
    ("❤", "Hearts & stuff", "❤ 🧡 💛 💚 💙 💜 🖤 🤍 💔 💕 💞 💓 💗 💖 💘 💝 💯 ✨ ⭐ 🌟 🔥 💥 🎉 🎊 "
                            "🎁 🏆 👑 💎 ⚡ 🌈 ☀ 🌙 ❄ 🌸"),
    ("🐶", "Animals", "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🦄 🐝 🦋 🐢 🐙 🐬 🐳 🦈"),
    ("🍕", "Food", "🍎 🍌 🍉 🍓 🍒 🍕 🍔 🍟 🌭 🌮 🍿 🍩 🍪 🎂 🍰 🍫 🍦 ☕ 🍺 🍷 🥤 🍜 🍣"),
    ("🎮", "Fun", "⚽ 🏀 🏈 🎮 🎲 🎯 🎵 🎶 🎧 🎬 📚 💻 📱 💡 🚀 ✈ 🚗 🎨 📸 🧠 ✅ ❌ ⚠ ❓ ❗"),
]
EMOJI_CATEGORIES = [(tab, name, items.split()) for tab, name, items in EMOJI_CATEGORIES]

# Type :name: and it turns into the emoji when you send.
EMOJI_SHORTCODES = {
    "smile": "😄", "grin": "😁", "joy": "😂", "laugh": "😂", "rofl": "🤣", "wink": "😉", "blush": "😊",
    "heart": "❤️", "love": "😍", "kiss": "😘", "cool": "😎", "sunglasses": "😎", "nerd": "🤓",
    "thinking": "🤔", "hmm": "🤔", "shrug": "🤷", "facepalm": "🤦", "mindblown": "🤯", "scream": "😱",
    "cry": "😢", "sob": "😭", "angry": "😠", "sleepy": "😴", "zzz": "😴", "hug": "🤗", "eyes": "👀",
    "thumbsup": "👍", "+1": "👍", "thumbsdown": "👎", "-1": "👎", "ok": "👌", "clap": "👏",
    "pray": "🙏", "wave": "👋", "muscle": "💪", "fire": "🔥", "100": "💯", "sparkles": "✨",
    "star": "⭐", "tada": "🎉", "party": "🥳", "gift": "🎁", "trophy": "🏆", "crown": "👑",
    "rocket": "🚀", "skull": "💀", "ghost": "👻", "poop": "💩", "robot": "🤖", "alien": "👽",
    "pizza": "🍕", "coffee": "☕", "cake": "🎂", "beer": "🍺", "taco": "🌮", "burger": "🍔",
    "dog": "🐶", "cat": "🐱", "unicorn": "🦄", "sun": "☀️", "moon": "🌙", "rainbow": "🌈",
    "game": "🎮", "music": "🎵", "book": "📚", "computer": "💻", "bulb": "💡", "brain": "🧠",
    "check": "✅", "x": "❌", "warning": "⚠️",
}
# Classic text faces -> emoji (only when they stand alone, so URLs and code are left alone).
EMOTICONS = {
    ":)": "🙂", ":-)": "🙂", ":(": "🙁", ":-(": "🙁", ":D": "😄", ":-D": "😄", ";)": "😉", ";-)": "😉",
    ":P": "😛", ":p": "😛", ":-P": "😛", ":O": "😮", ":o": "😮", ":'(": "😢", "xD": "😆", "XD": "😆",
    ":*": "😘", "<3": "❤️", "</3": "💔",
}
_SHORTCODE_RE = re.compile(r"(?<![\w/:]):([a-z0-9_+\-]{1,20}):(?![\w/])")
_EMOTICON_RE = re.compile(r"(?<!\S)(" + "|".join(re.escape(k) for k in sorted(EMOTICONS, key=len, reverse=True)) + r")(?!\S)")


def convert_emoji_shortcuts(text: str) -> str:
    """':fire:' -> 🔥 and ':)' -> 🙂 . Unknown :names: are left exactly as typed."""
    text = _SHORTCODE_RE.sub(lambda m: EMOJI_SHORTCODES.get(m.group(1).lower(), m.group(0)), text)
    return _EMOTICON_RE.sub(lambda m: EMOTICONS[m.group(1)], text)


# A web address (http://, https:// or www.) OR an @name that isn't glued to the end of a word (so a@b.com is not a mention).
_TOKEN_RE = re.compile(r"(?P<url>(?:https?://|www\.)[^\s<>\"]+)|(?<!\w)(?P<mention>@\w+)", re.I)
_URL_TRAILING = ".,;:!?'\"]}"


def tokenize_body(text: str) -> list[tuple[str, str]]:
    """Split a message into ('text'|'url'|'mention', piece) parts, in order."""
    parts, pos = [], 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() > pos:
            parts.append(("text", text[pos:m.start()]))
        if m.group("url"):
            url = m.group("url")
            while url and (url[-1] in _URL_TRAILING or (url[-1] == ")" and url.count(")") > url.count("("))):
                url = url[:-1]                       # "see example.com." -> don't swallow the full stop
            if len(url) > len("https://") and "." in url:
                parts.append(("url", url))
            else:
                parts.append(("text", url))
            if m.end() - m.start() > len(url):
                parts.append(("text", m.group("url")[len(url):]))
        else:
            parts.append(("mention", m.group("mention")))
        pos = m.end()
    if pos < len(text):
        parts.append(("text", text[pos:]))
    return parts


def mentions_user(text: str, username: str) -> bool:
    """True if the message has @username (or @everyone)."""
    me = username.lower()
    return any(kind == "mention" and piece[1:].lower() in (me, "everyone")
               for kind, piece in tokenize_body(text))


DEFAULT_BANNER = "#5865f2"


def text_color_on(bg_hex: str) -> str:
    """Dark text on light colors, white text on dark ones."""
    r, g, b = (int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))
    return "#222222" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "white"


def status_parts(status: str | None) -> tuple[str, str, str]:
    """(emoji, fun name, meaning) for a status key; unknown keys count as Active."""
    return proto.STATUSES.get(status or "", proto.STATUSES[proto.DEFAULT_STATUS])


# ─────────────────────────────────────────────────────────────
# PROFILE CARD (what you get when you click someone's name)
# ─────────────────────────────────────────────────────────────

class ProfileCard(tk.Toplevel):
    WIDTH = 330

    def __init__(self, owner: "ChatWindow", username: str):
        super().__init__(owner)
        self.owner = owner
        self.username = username
        self.title(f"{username}'s profile")
        self.resizable(False, False)
        self.transient(owner)
        self.configure(bg=owner.theme["window"])

        self.banner = tk.Frame(self, bg=DEFAULT_BANNER, width=self.WIDTH, height=96)
        self.banner.pack(fill="x")
        self.banner.pack_propagate(False)
        photo = owner.avatar_for(username, size=64)
        self._avatar = photo                                   # keep a reference or Tk drops the image
        self.avatar_lbl = tk.Label(self.banner, bg=DEFAULT_BANNER, image=photo or "")
        self.avatar_lbl.pack(side="left", padx=(16, 8))
        info = tk.Frame(self.banner, bg=DEFAULT_BANNER)
        info.pack(side="left", fill="both", expand=True)
        self.info_frame = info
        self.name_lbl = tk.Label(info, text=username, font=("Segoe UI", 14, "bold"), bg=DEFAULT_BANNER,
                                 fg="white", anchor="w")
        self.name_lbl.pack(fill="x", pady=(24, 0))
        self.pronoun_lbl = tk.Label(info, text="", font=("Segoe UI", 9), bg=DEFAULT_BANNER, fg="white", anchor="w")
        self.pronoun_lbl.pack(fill="x")

        self.body = tk.Frame(self, bg=owner.theme["window"], padx=16, pady=12)
        self.body.pack(fill="both", expand=True)
        self.status_lbl = tk.Label(self.body, text="Loading…", bg=owner.theme["window"], fg="#555555", anchor="w",
                                   justify="left", font=("Segoe UI Emoji", 10, "bold"), wraplength=self.WIDTH - 40)
        self.status_lbl.pack(fill="x")

        for w in (self.banner, self.avatar_lbl, self.info_frame, self.name_lbl, self.pronoun_lbl):
            w._pk_skip = True                       # the banner keeps the color its owner picked
        self._themer = Themer(self, lambda: self.owner.theme)
        self._themer.apply()
        self.update_idletasks()
        x = owner.winfo_rootx() + max(20, (owner.winfo_width() - self.WIDTH) // 2)
        self.geometry(f"+{x}+{owner.winfo_rooty() + 90}")
        self.bind("<Escape>", lambda e: self.destroy())
        owner.request_profile(username, self.fill)

    def _section(self, title: str, value: str):
        tk.Label(self.body, text=title, bg="white", fg="#888888", anchor="w",
                 font=("Segoe UI", 8, "bold")).pack(fill="x", pady=(12, 0))
        tk.Label(self.body, text=value, bg="white", fg="#222222", anchor="w", justify="left",
                 font=("Segoe UI", 10), wraplength=self.WIDTH - 40).pack(fill="x")

    def fill(self, msg: dict):
        if msg.get("missing"):
            self.status_lbl.config(text="This account doesn't exist any more.")
            return
        banner = msg.get("banner") or DEFAULT_BANNER
        fg = text_color_on(banner)
        for w in (self.banner, self.avatar_lbl, self.info_frame, self.name_lbl, self.pronoun_lbl):
            w.config(bg=banner)
        self.name_lbl.config(fg=fg, text=f"{msg.get('badge') or ''} {self.username}".strip())
        self.pronoun_lbl.config(fg=fg, text=msg.get("pronouns") or "")

        if msg.get("online"):
            emoji, label, meaning = status_parts(msg.get("status"))
            line = f"{emoji} {label}"
            if msg.get("status_text"):
                line += f" — {msg['status_text']}"
            self.status_lbl.config(text=line, fg="#222222")
            if msg.get("status") == "dnd":
                tk.Label(self.body, text="Do Not Disturb: they may not see your message right away.",
                         bg="white", fg="#b26a00", font=("Segoe UI", 8), anchor="w").pack(fill="x")
        else:
            self.status_lbl.config(text="⚫ Offline", fg="#888888")

        self._section("ABOUT ME", msg.get("bio") or "Nothing here yet.")
        if msg.get("created_at"):
            try:
                d = datetime.fromisoformat(msg["created_at"])
                self._section("MEMBER SINCE", f"{d:%B} {d.day}, {d.year}")
            except ValueError:
                pass

        if self.username == self.owner.username:
            PillButton(self.body, text="✏  Edit my card", command=self._edit_mine, t=self.owner.theme,
                       height=34).pack(anchor="w", pady=(16, 0))
        else:
            PillButton(self.body, text="💬  Send message", command=self._message, t=self.owner.theme,
                       height=34).pack(anchor="w", pady=(16, 0))
        self._themer.apply()                        # recolor the labels that were just added

    def _message(self):
        self.owner.open_dm_tab(self.username)
        self.destroy()

    def _edit_mine(self):
        self.owner.open_settings("card")
        self.destroy()


# ─────────────────────────────────────────────────────────────
# EMOJI PICKER
# ─────────────────────────────────────────────────────────────

class EmojiPicker(tk.Toplevel):
    """A small window of emoji buttons. Calls on_pick(emoji) for each click."""

    COLUMNS = 9

    def __init__(self, owner, on_pick, close_on_pick=False):
        super().__init__(owner)
        self.title("Emojis")
        self.resizable(False, False)
        self.transient(owner)
        self.on_pick = on_pick
        self.close_on_pick = close_on_pick
        t = popup_kit.current()                    # the chat's theme
        self.configure(bg=t["window"])
        tabs = ttk.Notebook(self)                  # recolored by popup_kit.style_ttk (accent when selected)
        tabs.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        for tab_icon, _name, emojis in EMOJI_CATEGORIES:
            page = tk.Frame(tabs, bg=t["window"])
            tabs.add(page, text=tab_icon)
            for i, emoji in enumerate(emojis):
                tk.Button(page, text=emoji, font=EMOJI_FONT, width=2, bd=0, relief="flat", bg=t["window"],
                          activebackground=t["selected"], cursor="hand2", highlightthickness=0,
                          command=lambda e=emoji: self._pick(e)).grid(row=i // self.COLUMNS, column=i % self.COLUMNS)
        tk.Label(self, text="Tip: you can also type :fire: or :) ", font=(t["font"], 8), bg=t["window"],
                 fg=t["muted"]).pack(pady=(4, 6))
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = owner.winfo_rootx() + 190
        y = max(0, owner.winfo_rooty() + owner.winfo_height() - self.winfo_reqheight() - 70)
        self.geometry(f"+{x}+{y}")

    def _pick(self, emoji):
        self.on_pick(emoji)
        if self.close_on_pick:
            self.destroy()


# ─────────────────────────────────────────────────────────────
# ONE CONVERSATION (the room, or one DM)
# ─────────────────────────────────────────────────────────────

class MessagePane(tk.Frame):
    def __init__(self, parent, owner: "ChatWindow", target: str | None):
        super().__init__(parent, bg="#f0f0f0")
        self.owner = owner
        self.target = target  # None = room, else the other person's username

        self.records: dict[int, dict] = {}     # message_id -> record
        self.file_buffers: dict[str, dict] = {}  # file_id -> {index: b64data}, for in-progress downloads
        self.typing_others: dict[str, str] = {}  # username -> "after" job id
        self.editing_id: int | None = None
        self.loading: set[int] = set()            # image message ids we've asked the server for
        self.read_sent: set[int] = set()          # incoming DMs we've already told the server we read
        self._thumbs: dict[str, object] = {}      # local path -> thumbnail (must stay referenced or Tk drops it)
        self._typing_state = False
        self._typing_stop_job = None
        self._mention_open = False                # is the @name suggestion list showing?
        self.keyboard = None                      # the on-screen keyboard strip, built the first time it's opened
        self._keyboard_visible = False
        self._kb_window = None                    # floating keyboard window, used when the strip has no room

        self._build_ui()
        self.bind("<Destroy>", self._on_pane_destroy, add="+")

    # -------------------------------------------------
    def _build_ui(self):
        self.messages_area = scrolledtext.ScrolledText(
            self, wrap="word", state="disabled", bg="#f5f6f8",
            font=("Segoe UI", 10), borderwidth=0, padx=10, pady=10,
            height=1,       # asks for little, then expand=True stretches it: otherwise this 24-line request leaves
        )                   # no room for the widgets packed after it (e.g. the on-screen keyboard)
        self.messages_area.pack(fill="both", expand=True, side="top")
        self.messages_area.bind("<Button-3>", self._show_context_menu)   # Windows/Linux
        self.messages_area.bind("<Button-2>", self._show_context_menu)   # macOS

        # every message is a soft "card": its own tint behind all of its lines (see _write_block)
        self.messages_area.tag_configure("row_me", lmargin1=18, lmargin2=18, rmargin=18, spacing1=2, spacing3=2)
        self.messages_area.tag_configure("row_other", lmargin1=18, lmargin2=18, rmargin=18, spacing1=2, spacing3=2)
        self.messages_area.tag_configure("row_head", spacing1=10)
        self.messages_area.tag_configure("timestamp", foreground="#888888", font=("Segoe UI", 8))
        self.messages_area.tag_configure("system", foreground="#999999", font=("Segoe UI", 9, "italic"), justify="center")
        self.messages_area.tag_configure("message_text", font=("Segoe UI", 10))
        self.messages_area.tag_configure("deleted_text", font=("Segoe UI", 10, "italic"), foreground="#aaaaaa")
        self.messages_area.tag_configure("file_link", font=("Segoe UI", 10, "underline"), foreground="#5865f2")
        self.messages_area.tag_configure("mention", background="#fff3b0")
        self.messages_area.tag_configure("mention_me", background="#ffd24d", font=("Segoe UI", 10, "bold"))   # @you / @everyone
        self.messages_area.tag_configure("link", foreground="#0b5ed7", underline=True)
        # clicking a name or picture opens that person's profile card
        self.messages_area.tag_configure("profile_click")
        self.messages_area.tag_bind("profile_click", "<Button-1>", self._on_profile_click)
        self.messages_area.tag_bind("profile_click", "<Enter>", lambda e: self.messages_area.configure(cursor="hand2"))
        self.messages_area.tag_bind("profile_click", "<Leave>", lambda e: self.messages_area.configure(cursor="xterm"))
        self.messages_area.tag_bind("link", "<Button-1>", self._on_link_click)
        self.messages_area.tag_bind("link", "<Enter>", lambda e: self.messages_area.configure(cursor="hand2"))
        self.messages_area.tag_bind("link", "<Leave>", lambda e: self.messages_area.configure(cursor="xterm"))
        self.messages_area.tag_configure("reactions", font=("Segoe UI", 9), foreground="#555555")
        self.messages_area.tag_configure("translation", font=("Segoe UI", 10, "italic"), foreground="#555555")
        self.messages_area.tag_configure("align_right", justify="right")
        self.messages_area.tag_configure("align_left", justify="left")
        self.messages_area.tag_configure("you_name", foreground=self.owner.my_name_color(), font=("Segoe UI", 10, "bold"))
        # per-user name-color tags are created lazily in _name_tag_for
        # clicking an inline image opens it full size
        self.messages_area.tag_bind("image_thumb", "<Button-1>", self._on_image_click)
        self.messages_area.tag_bind("image_thumb", "<Enter>", lambda e: self.messages_area.configure(cursor="hand2"))
        self.messages_area.tag_bind("image_thumb", "<Leave>", lambda e: self.messages_area.configure(cursor="xterm"))

        self.typing_label = tk.Label(self, text="", bg="#f0f0f0", fg="#888888",
                                      font=("Segoe UI", 8, "italic"), anchor="w")
        self.typing_label.pack(fill="x", side="top", padx=10)

        self.edit_banner = tk.Label(self, text="", bg="#fff3b0", fg="#333333",
                                     font=("Segoe UI", 8), anchor="w")
        # packed only while editing (see start_edit / cancel_edit)

        # The message box: one rounded bar holding the icons, the text entry and a round send button
        # (ui.InputBar places them; it glows while you type).
        input_frame = tk.Frame(self, bg="#f0f0f0")
        input_frame.pack(fill="x", side="bottom", pady=(4, 10), padx=12)
        self.input_frame = input_frame
        self.input_bar = ui.InputBar(input_frame, self.owner.theme)
        self.input_bar.pack(fill="x")

        attach_button = ui.IconButton(self.input_bar, "📎", self.attach_file)
        emoji_button = ui.IconButton(self.input_bar, "😊", self.open_emoji_picker)

        # A plain button that pops the menu up on a single click. (tk.Menubutton only works
        # while the mouse is held down on Linux, which is why it isn't used here.)
        self.games_button = ui.IconButton(self.input_bar, "🎮", self._open_games_menu)
        self.games_menu = tk.Menu(self.games_button, tearoff=0)

        # on-screen keyboard for accented letters (see onscreen_keyboard.py)
        self.kb_button = ui.IconButton(self.input_bar, "⌨", self.toggle_keyboard)

        self.entry = tk.Entry(self.input_bar, font=("Segoe UI", 11), relief="flat", bd=0, highlightthickness=0)
        self.entry.bind("<Return>", self.send_message)
        self.entry.bind("<KeyPress>", self._on_keypress)
        self.entry.bind("<Escape>", self._on_escape)
        self.entry.bind("<KeyRelease>", self._update_mention_popup)
        self.entry.bind("<Up>", lambda e: self._mention_move(-1))
        self.entry.bind("<Down>", lambda e: self._mention_move(1))
        self.entry.bind("<Tab>", lambda e: "break" if self._accept_mention() else None)
        self.entry.bind("<FocusOut>", lambda e: self.after(150, self._hide_mention_popup_if_unfocused))

        # the @name suggestion list (hidden until you type "@")
        self.mention_box = tk.Listbox(self, height=1, font=("Segoe UI", 10), activestyle="none",
                                      exportselection=False, bd=1, relief="solid",
                                      selectbackground="#5865f2", selectforeground="white")
        self.mention_box.bind("<ButtonRelease-1>", lambda e: self._accept_mention())

        self.send_button = ui.SendButton(self.input_bar, self.send_message)
        self.input_bar.layout([attach_button, emoji_button, self.games_button, self.kb_button], self.entry,
                              self.send_button)
        self.attach_button, self.emoji_button = attach_button, emoji_button
        self.apply_theme()

    def apply_theme(self):
        """(Re)color and re-font everything in this pane from the owner's current theme."""
        t = self.owner.theme
        fam, size = t["font"], t["font_size"]
        small = max(7, size - 2)
        area = self.messages_area
        self.configure(bg=t["window"])
        area.configure(bg=t["chat_bg"], fg=t["text"], insertbackground=t["text"],
                       selectbackground=t["accent"], selectforeground=t["accent_text"],
                       font=(fam, size))
        area.tag_configure("timestamp", foreground=t["muted"], font=(fam, small))
        area.tag_configure("system", foreground=t["muted"], font=(fam, max(8, size - 1), "italic"))
        area.tag_configure("message_text", foreground=t["text"], font=(fam, size))
        area.tag_configure("deleted_text", foreground=t["muted"], font=(fam, size, "italic"))
        area.tag_configure("file_link", foreground=t["link_file"], font=(fam, size, "underline"))
        area.tag_configure("mention", background=t["mention"], foreground=t["text"])
        area.tag_configure("mention_me", background=t["mention_me"], foreground=t["text"], font=(fam, size, "bold"))
        area.tag_configure("link", foreground=t["link"], underline=True)
        area.tag_configure("reactions", foreground=t["muted"], font=(fam, max(8, size - 1)))
        area.tag_configure("translation", foreground=t["muted"], font=(fam, size, "italic"))
        area.tag_configure("gap", font=(fam, t["gap"]))
        self.refresh_name_colors()
        self.typing_label.configure(bg=t["window"], fg=t["muted"], font=(fam, small, "italic"))
        self.edit_banner.configure(bg=t["mention"], fg=t["text"], font=(fam, small))
        self.input_frame.configure(bg=t["window"])
        self.input_bar.restyle(t)
        for b in (self.attach_button, self.emoji_button, self.games_button, self.kb_button):
            b.restyle(t["input_bg"], t["text"], ui.mix_hex(t["input_bg"], t["accent"], 0.16))
        self.games_menu.configure(bg=t["input_bg"], fg=t["input_fg"], activebackground=t["accent"],
                                  activeforeground=t["accent_text"], font=(fam, size))
        self.entry.configure(bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["accent"],
                             disabledbackground=t["input_bg"], font=(fam, size + 1),
                             selectbackground=t["accent"], selectforeground=t["accent_text"])
        self.send_button.restyle(t["input_bg"], t["accent"], t["accent2"])
        area.tag_configure("row_me", background=t["bubble_me"])
        area.tag_configure("row_other", background=t["bubble_other"])
        area.tag_lower("row_me")
        for name in area.window_names():                         # rolls already in the log follow the new colors
            try:
                widget = area.nametowidget(name)
            except Exception:
                continue
            if isinstance(widget, RollAnimation):
                widget.recolor({"bg": area.cget("bg"), "fg": t["text"], "accent": t["accent"],
                                "accent_text": t["accent_text"], "shadow": themes.mix(area.cget("bg"), "#000000", 0.18),
                                "die_edge": "#9CA3AF"})
        area.tag_lower("row_other")
        self.mention_box.configure(bg=t["input_bg"], fg=t["input_fg"], font=(fam, size),
                                   selectbackground=t["accent"], selectforeground=t["accent_text"])
        if self.keyboard is not None:
            self.keyboard.apply_theme(t)
        if self._kb_window is not None:
            self._kb_window.configure(bg=t["window"])

    def _name_tag_for(self, username: str) -> str:
        tag = f"user_{username}"
        if tag not in self.messages_area.tag_names():
            self.messages_area.tag_configure(tag, foreground=self.owner.display_color(username),
                                             font=(self.owner.theme["font"], self.owner.theme["font_size"], "bold"))
        return tag

    def refresh_name_colors(self):
        """Re-apply everyone's current colors to names already on screen."""
        area = self.messages_area
        for tag in area.tag_names():
            if tag.startswith("user_"):
                area.tag_configure(tag, foreground=self.owner.display_color(tag[len("user_"):]),
                                   font=(self.owner.theme["font"], self.owner.theme["font_size"], "bold"))
        area.tag_configure("you_name", foreground=themes.readable_on(self.owner.my_name_color(), self.owner.theme["chat_bg"]),
                           font=(self.owner.theme["font"], self.owner.theme["font_size"], "bold"))

    # -------------------------------------------------
    # RENDERING
    # -------------------------------------------------
    def _reactions_line(self, reactions: list[dict] | None) -> str:
        if not reactions:
            return ""
        return "  ".join(f"{r['emoji']} {len(r['users'])}" for r in reactions)

    def _file_display_text(self, record: dict) -> str:
        size = human_size(record.get("file_size") or 0)
        name = record.get("file_name", "file")
        image = is_image_name(name)
        if record.get("local_path"):
            # for an image we only get here if it couldn't be drawn
            status = "  (preview unavailable -- right-click to open)" if image else ""
        elif record["id"] in self.loading:
            status = "  (loading...)"
        else:
            status = "  (click to download)"
        return f"{'🖼' if image else '📎'} {name}  ({size}){status}"

    def purge_user(self, username: str):
        """That account was deleted: take everything of theirs off the screen --
        their messages, their reactions on other messages, and (in a DM tab with
        them) the whole conversation."""
        area = self.messages_area
        whole_tab = (self.target == username)
        area.configure(state="normal")
        for mid, record in list(self.records.items()):
            if whole_tab or record["sender"] == username:
                ranges = area.tag_ranges(f"m{mid}")
                if ranges:
                    area.delete(ranges[0], ranges[1])
                del self.records[mid]
        area.configure(state="disabled")
        for record in list(self.records.values()):          # their reactions on what's left
            changed = False
            for entry in list(record.get("reactions") or []):
                if username in entry["users"]:
                    entry["users"].remove(username)
                    changed = True
                    if not entry["users"]:
                        record["reactions"].remove(entry)
            if changed:
                self.upsert_message(record)

    def redraw_messages(self, sender: str | None = None):
        """Redraw already-shown messages (all, or just one person's) in place --
        used when a profile picture changes. Keeps your scroll position."""
        area = self.messages_area
        at_bottom = area.yview()[1] >= 0.999
        top = area.yview()[0]
        for record in sorted(self.records.values(), key=lambda r: r["id"]):
            if sender is None or record["sender"] == sender:
                self.upsert_message(record)
        if at_bottom:
            area.see("end")
        else:
            area.yview_moveto(top)

    def _thumbnail_for(self, path: str):
        if path not in self._thumbs:
            self._thumbs[path] = load_thumbnail(path)   # None is cached too, so a bad file isn't retried on every redraw
        return self._thumbs[path]

    def _on_image_click(self, event):
        area = self.messages_area
        idx = area.index(f"@{event.x},{event.y}")
        for t in area.tag_names(idx):
            if t.startswith("m") and t[1:].isdigit():
                record = self.records.get(int(t[1:]))
                if record and record.get("local_path"):
                    open_file_externally(record["local_path"])
                return

    def auto_fetch_images(self):
        """After history loads: pull down the newest small images so they show inline."""
        wanted = [r for r in self.records.values()
                  if r.get("msg_type") == "file" and not r.get("deleted")
                  and is_image_name(r.get("file_name")) and not r.get("local_path")
                  and r["id"] not in self.loading
                  and (r.get("file_size") or 0) <= AUTO_IMAGE_MAX_BYTES]
        wanted.sort(key=lambda r: r["id"])
        for record in wanted[-AUTO_IMAGE_MAX_COUNT:]:
            self.loading.add(record["id"])
            self._request_file(record["id"])
            self.upsert_message(record)   # redraw with the "loading..." label

    def _write_block(self, record: dict, index: str):
        """Draw one message. Each piece of the message is inserted together
        with its own tags, so there is no character-offset math that could
        drift and color the wrong text."""
        tag_id = f"m{record['id']}"
        is_me = record["sender"] == self.owner.username
        display_name = "You" if is_me else record["sender"]
        ts = record.get("ts_display", "")

        receipt = ""
        if is_me and self.target is not None and record.get("msg_type") != "file":
            receipt = "  ✓✓ Read" if record.get("read") else "  ✓ Sent"

        is_file = record.get("msg_type") == "file"
        is_deleted = bool(record.get("deleted"))
        if is_deleted:
            body_text = "[message deleted]"
        elif is_file:
            body_text = self._file_display_text(record)
        else:
            body_text = record.get("text", "")
            if record.get("edited"):
                body_text += "  (edited)"

        body_tag = "deleted_text" if is_deleted else ("file_link" if is_file else "message_text")
        name_tag = "you_name" if is_me else self._name_tag_for(record["sender"])
        align_tag = "align_left"
        row_tag = "row_me" if is_me else "row_other"
        base_tags = (tag_id, align_tag, row_tag)   # tag_id lets upsert_message find/replace this block

        area = self.messages_area
        area.configure(state="normal")
        # Insert at a moving mark: "end-1c" is where insert("end") really writes.
        area.mark_set("blk_ins", "end-1c" if index == "end" else index)
        area.mark_gravity("blk_ins", "right")

        def put(text, *extra_tags):
            if text:
                area.insert("blk_ins", text, base_tags + extra_tags)

        # header line: small round picture, then ONLY the name gets the user's color
        avatar = self.owner.avatar_for(record["sender"])
        if avatar is not None:
            area.image_create("blk_ins", image=avatar, padx=4, align="center")
            for t in base_tags + ("profile_click", "row_head"):
                area.tag_add(t, "blk_ins-1c", "blk_ins")   # the picture is exactly one character
        put(f"{display_name}  ", name_tag, "profile_click", "row_head")
        put(f"{ts}{receipt}\n", "row_head")

        photo = None
        if is_file and not is_deleted and record.get("local_path") and is_image_name(record.get("file_name")):
            photo = self._thumbnail_for(record["local_path"])

        # body line: plain text (with @mentions highlighted), or the picture itself
        if photo is not None:
            area.image_create("blk_ins", image=photo, padx=2, pady=4)
            for t in base_tags + ("image_thumb",):
                area.tag_add(t, "blk_ins-1c", "blk_ins")   # the image is exactly one character
        elif is_file or is_deleted:
            put(body_text, body_tag)
        else:
            for kind, part in tokenize_body(body_text):
                if kind == "mention":
                    is_me_mentioned = part[1:].lower() in (self.owner.username.lower(), "everyone")
                    put(part, body_tag, "mention_me" if is_me_mentioned else "mention")
                elif kind == "url":
                    put(part, body_tag, "link")
                else:
                    put(part, body_tag)
        put("\n")

        if record.get("translation") and not is_file and not is_deleted:
            put(f"🌐 {record['translation']}\n", "translation")     # your-language version, under the original

        reactions_str = self._reactions_line(record.get("reactions"))
        if reactions_str:
            put(reactions_str, "reactions")
            put("\n")
        area.insert("blk_ins", "\n", (tag_id, "gap"))     # the space BETWEEN cards: no tint, so they read as separate cards

        area.mark_unset("blk_ins")
        area.configure(state="disabled")
        area.see("end")

    def upsert_message(self, record: dict):
        self.records[record["id"]] = record
        tag_id = f"m{record['id']}"
        ranges = self.messages_area.tag_ranges(tag_id)
        if ranges:
            start, end = str(ranges[0]), str(ranges[1])
            self.messages_area.configure(state="normal")
            self.messages_area.delete(start, end)
            self.messages_area.configure(state="disabled")
            self._write_block(record, start)
        else:
            self._write_block(record, "end")

    def display_system(self, text: str):
        self.messages_area.configure(state="normal")
        self.messages_area.insert("end", f"{text}\n\n", ("system",))
        self.messages_area.configure(state="disabled")
        self.messages_area.see("end")

    def display_roll(self, text: str, roll: dict | None):
        """A dice roll / coin flip: play the animation right in the chat. It lands on the result the SERVER picked,
        then stays there with the usual sentence under it. Falls back to the plain sentence if it can't be drawn."""
        if not roll:
            self.display_system(text)
            return
        area, t = self.messages_area, self.owner.theme
        bg = area.cget("bg")
        try:
            anim = RollAnimation(area, roll, text, {
                "bg": bg, "fg": t["text"], "accent": t["accent"], "accent_text": t["accent_text"],
                "shadow": themes.mix(bg, "#000000", 0.18), "die_edge": "#9CA3AF"})
        except Exception:
            self.display_system(text)
            return
        try:
            area.configure(state="normal")
            area.window_create("end", window=anim, pady=2)
            area.tag_add("system", "end-2c", "end-1c")           # centered, like the other notices
            area.insert("end", "\n\n", ("system",))
        except Exception:
            try:
                anim.destroy()
            except Exception:
                pass
            self.display_system(text)
            return
        finally:
            area.configure(state="disabled")                      # the log must never be left typeable
        area.see("end")

    # -------------------------------------------------
    # INCOMING EVENTS (called by ChatWindow's router)
    # -------------------------------------------------
    def on_text(self, msg: dict, is_new: bool):
        record = self._record_from_text_msg(msg)
        self.upsert_message(record)
        if is_new:
            self.send_pending_reads()

    def send_pending_reads(self):
        """Tell the server which incoming DMs we've now read -- but ONLY if the
        person can really see this conversation (tab selected, window focused).
        Anything else stays unread until they look: see _on_tab_changed / _on_focus_in."""
        if self.target is None or not self.owner.is_viewing(self.target):
            return
        for record in self.records.values():
            if (record["sender"] != self.owner.username and not record.get("read")
                    and record["id"] not in self.read_sent):
                self.read_sent.add(record["id"])
                self.owner.send_json({"type": proto.READ, "message_id": record["id"]})

    def _record_from_text_msg(self, msg: dict) -> dict:
        # Live TEXT/FILE_START messages use the key "text"; history rows
        # loaded straight from the database use the DB column name "body".
        # Accept either so the same rendering path works for both.
        text = msg["text"] if "text" in msg else msg.get("body", "")
        if not msg.get("deleted") and msg.get("msg_type", "text") == "text":
            text = self.owner.decrypt(text)
        ts = msg.get("ts") or msg.get("created_at")

        # History rows keep the server-side path ("server_uploads/<file_id>_<name>");
        # we save downloads under the same <file_id>_<name>, so if it's already on
        # disk we can use it instead of asking the server again.
        local_path = None
        if msg.get("msg_type") == "file" and msg.get("body"):
            cached = os.path.join(DOWNLOADS_DIR, os.path.basename(str(msg["body"]).replace("\\", "/")))
            if os.path.exists(cached):
                local_path = cached
        return {
            "id": msg["id"], "sender": msg["sender"], "text": text,
            "msg_type": msg.get("msg_type", "text"),
            "file_name": msg.get("file_name"), "file_size": msg.get("file_size"),
            "edited": bool(msg.get("edited")), "deleted": bool(msg.get("deleted")),
            "reactions": msg.get("reactions", []), "read": bool(msg.get("read", False)),
            "ts_display": self.owner.format_ts(ts), "local_path": local_path,
        }

    def on_edit(self, message_id, new_text):
        record = self.records.get(message_id)
        if not record:
            return
        record["text"] = self.owner.decrypt(new_text)
        record["edited"] = True
        record.pop("translation", None)             # the old translation no longer matches
        record.pop("tr_key", None)
        self.upsert_message(record)
        self.owner.request_translation(self, record)

    def set_translation(self, message_id: int, text: str | None):
        """Show (or clear) the translated line under one message without jumping the scroll position."""
        record = self.records.get(message_id)
        if not record:
            return
        if text:
            record["translation"] = text
        else:
            record.pop("translation", None)
        area = self.messages_area
        at_bottom = area.yview()[1] >= 0.999
        top = area.yview()[0]
        self.upsert_message(record)
        if at_bottom:
            area.see("end")
        else:
            area.yview_moveto(top)

    def on_delete(self, message_id):
        record = self.records.get(message_id)
        if not record:
            return
        record["deleted"] = True
        record["text"] = ""
        self.upsert_message(record)

    def on_reaction(self, message_id, emoji, action, username):
        record = self.records.get(message_id)
        if not record:
            return
        reactions = record.setdefault("reactions", [])
        entry = next((r for r in reactions if r["emoji"] == emoji), None)
        if action == "add":
            if entry is None:
                reactions.append({"emoji": emoji, "users": [username]})
            elif username not in entry["users"]:
                entry["users"].append(username)
        else:
            if entry and username in entry["users"]:
                entry["users"].remove(username)
                if not entry["users"]:
                    reactions.remove(entry)
        self.upsert_message(record)

    def on_read(self, message_id):
        record = self.records.get(message_id)
        if not record:
            return
        record["read"] = True
        self.upsert_message(record)

    def show_typing(self, username: str, state: str):
        if state == "start":
            if username in self.typing_others:
                self.after_cancel(self.typing_others[username])
            self.typing_others[username] = self.after(4000, lambda: self._expire_typing(username))
        else:
            self._expire_typing(username)
        self._refresh_typing_label()

    def _expire_typing(self, username):
        job = self.typing_others.pop(username, None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._refresh_typing_label()

    def _refresh_typing_label(self):
        names = list(self.typing_others.keys())
        if not names:
            self.typing_label.config(text="")
        elif len(names) == 1:
            self.typing_label.config(text=f"{names[0]} is typing…")
        else:
            self.typing_label.config(text=f"{', '.join(names)} are typing…")

    # -------------------------------------------------
    # PROFILE CARDS
    # -------------------------------------------------
    def _on_profile_click(self, event):
        area = self.messages_area
        idx = area.index(f"@{event.x},{event.y}")
        for t in area.tag_names(idx):
            if t.startswith("m") and t[1:].isdigit():
                record = self.records.get(int(t[1:]))
                if record:
                    self.owner.show_profile(record["sender"])
                return

    # -------------------------------------------------
    # LINKS
    # -------------------------------------------------
    def _on_link_click(self, event):
        area = self.messages_area
        idx = area.index(f"@{event.x},{event.y}")
        rng = area.tag_prevrange("link", f"{idx}+1c")      # the link range that starts at or before the click
        if not rng or not (area.compare(rng[0], "<=", idx) and area.compare(idx, "<", rng[1])):
            return
        self.owner.open_link(area.get(rng[0], rng[1]))

    # -------------------------------------------------
    # EMOJI
    # -------------------------------------------------
    def open_emoji_picker(self):
        self.owner.open_emoji_picker(self._insert_emoji)

    def _insert_emoji(self, emoji: str):
        self.entry.insert("insert", emoji)
        self.entry.focus_set()

    # -------------------------------------------------
    # ON-SCREEN KEYBOARD (accented letters)
    # Shown as a strip above the message box. If the window is too short to fit it there, it opens as a
    # small floating window instead (like the emoji picker), so it always appears somewhere.
    # -------------------------------------------------
    def toggle_keyboard(self):
        if self._keyboard_visible:
            self._close_keyboard()
        else:
            try:
                self._open_keyboard()
            except Exception as e:           # never fail silently: say what went wrong
                self._close_keyboard()
                messagebox.showerror("Keyboard", f"The on-screen keyboard couldn't be built:\n"
                                                 f"{type(e).__name__}: {e}", parent=self)
        self.kb_button.set_active(self._keyboard_visible)
        self.entry.focus_set()

    def _new_keyboard(self, parent):
        return KeyboardPanel(parent, self.entry, self.owner.theme, language=self.owner.kb_language,
                             on_typed=self._keyboard_typed, on_language=self._keyboard_language)

    def _open_keyboard(self):
        if self.keyboard is None:
            self.keyboard = self._new_keyboard(self)
        self.keyboard.pack(fill="x", side="bottom", padx=6, after=self.input_frame)
        self._keyboard_visible = True
        self.update_idletasks()              # let Tk lay it out now, then check it really got its space
        if self.keyboard.winfo_height() < self.keyboard.winfo_reqheight():
            self._float_keyboard()

    def _float_keyboard(self):
        """No room above the message box: show the keyboard in its own small window instead."""
        self.keyboard.destroy()
        win = self._kb_window = tk.Toplevel(self.owner)
        win.title("Keyboard")
        win.resizable(False, False)
        win.transient(self.owner)
        win.configure(bg=self.owner.theme["window"])
        win.protocol("WM_DELETE_WINDOW", self.toggle_keyboard)      # closing the window = switching it off
        self.keyboard = self._new_keyboard(win)
        self.keyboard.pack(padx=6, pady=2)
        win.update_idletasks()
        x = self.owner.winfo_rootx() + 190
        y = max(0, self.owner.winfo_rooty() + self.owner.winfo_height() - win.winfo_reqheight() - 70)
        win.geometry(f"+{x}+{y}")

    def _close_keyboard(self):
        try:
            if self._kb_window is not None:           # floating: remove it completely
                self._kb_window.destroy()
                self.keyboard = None
            elif self.keyboard is not None:           # docked: just hide it (keeps its language and Caps)
                self.keyboard.pack_forget()
        except tk.TclError:
            pass
        self._kb_window = None
        self._keyboard_visible = False

    def _on_pane_destroy(self, event):
        if event.widget is self:                      # this tab was closed: don't leave its keyboard behind
            self._close_keyboard()

    def _keyboard_typed(self):
        """A key on the on-screen keyboard counts as typing (typing indicator, @name list)."""
        class _Key:                     # _on_keypress only looks at .keysym
            keysym = "x"
        self._on_keypress(_Key())
        self._update_mention_popup()

    def _keyboard_language(self, code: str):
        self.owner.kb_language = code   # remembered for the other tabs and for next time it opens

    # -------------------------------------------------
    # @MENTION SUGGESTIONS
    # -------------------------------------------------
    def _mention_query(self) -> str | None:
        """The partial name after an '@' right before the cursor, or None."""
        before = self.entry.get()[:self.entry.index("insert")]
        m = re.search(r"(?:^|\s)@(\w*)$", before)
        return m.group(1) if m else None

    def _mention_candidates(self, prefix: str) -> list[str]:
        names = set(self.owner.online_users) | {r["sender"] for r in self.records.values()}
        if self.target:
            names.add(self.target)
        names.discard(self.owner.username)
        pool = sorted(names, key=str.lower)
        if self.target is None:
            pool.append("everyone")
        p = prefix.lower()
        return [n for n in pool if n.lower().startswith(p)][:6]

    def _update_mention_popup(self, event=None):
        if event is not None and event.keysym in ("Up", "Down", "Return", "Tab", "Escape", "Shift_L", "Shift_R"):
            return
        prefix = self._mention_query()
        candidates = self._mention_candidates(prefix) if prefix is not None else []
        if not candidates:
            self._hide_mention_popup()
            return
        self.mention_box.delete(0, "end")
        for name in candidates:
            self.mention_box.insert("end", name)
        self.mention_box.selection_set(0)
        self.mention_box.configure(height=len(candidates))
        self.mention_box.place(in_=self, x=12, rely=1.0, anchor="sw",
                               y=-(self.input_frame.winfo_height() + 12), width=190)
        self.mention_box.lift()
        self._mention_open = True

    def _hide_mention_popup(self):
        if self._mention_open:
            self.mention_box.place_forget()
            self._mention_open = False

    def _hide_mention_popup_if_unfocused(self):
        # clicking a suggestion briefly takes focus from the entry -- don't hide it out from under the click
        try:
            if self.focus_get() is not self.mention_box:
                self._hide_mention_popup()
        except KeyError:
            self._hide_mention_popup()

    def _mention_move(self, step: int):
        if not self._mention_open:
            return None
        sel = self.mention_box.curselection()
        cur = sel[0] if sel else 0
        new = max(0, min(self.mention_box.size() - 1, cur + step))
        self.mention_box.selection_clear(0, "end")
        self.mention_box.selection_set(new)
        return "break"

    def _accept_mention(self) -> bool:
        """Finish the @name being typed with the highlighted suggestion. True if it did."""
        if not self._mention_open:
            return False
        sel = self.mention_box.curselection()
        if not sel:
            self._hide_mention_popup()
            return False
        name = self.mention_box.get(sel[0])
        pos = self.entry.index("insert")
        m = re.search(r"@(\w*)$", self.entry.get()[:pos])
        if m:
            self.entry.delete(m.start(), pos)
            self.entry.insert(m.start(), f"@{name} ")
        self._hide_mention_popup()
        self.entry.focus_set()
        return True

    def _on_escape(self, event=None):
        if self._mention_open:
            self._hide_mention_popup()
        else:
            self.cancel_edit()

    # -------------------------------------------------
    # SENDING TEXT
    # -------------------------------------------------
    def _on_keypress(self, event):
        if event.keysym in ("Return", "Escape"):
            return
        if not self._typing_state:
            self._typing_state = True
            self.owner.send_json({"type": proto.TYPING, "target": self.target, "state": "start"})
        if self._typing_stop_job:
            self.after_cancel(self._typing_stop_job)
        self._typing_stop_job = self.after(3000, self._send_typing_stop)

    def _send_typing_stop(self):
        if self._typing_state:
            self._typing_state = False
            self.owner.send_json({"type": proto.TYPING, "target": self.target, "state": "stop"})
        self._typing_stop_job = None

    def send_message(self, event=None):
        if self._mention_open:                  # Enter picks the highlighted @name instead of sending
            self._accept_mention()
            return "break"
        text = convert_emoji_shortcuts(self.entry.get().strip())
        if not text:
            return

        if self.editing_id is not None:
            encrypted = self.owner.encrypt(text)
            self.owner.send_json({"type": proto.EDIT, "message_id": self.editing_id, "text": encrypted})
            self.cancel_edit()
            self.entry.delete(0, "end")
            return

        if text.startswith("/") and self._run_command(text):
            self.entry.delete(0, "end")
            return

        encrypted = self.owner.encrypt(text)
        self.owner.send_json({"type": proto.TEXT, "target": self.target, "text": encrypted})
        self.entry.delete(0, "end")
        self._hide_mention_popup()
        self._send_typing_stop()

    # ---- games --------------------------------------------------------------
    def _open_games_menu(self):
        self._fill_games_menu()
        x = self.games_button.winfo_rootx()
        y = self.games_button.winfo_rooty() + self.games_button.winfo_height()
        try:
            self.games_menu.tk_popup(x, y)
        finally:
            self.games_menu.grab_release()

    def _fill_games_menu(self):
        """Rebuilt every time it opens, so the list of who you can challenge is always current."""
        menu = self.games_menu
        menu.delete(0, "end")
        where = "the room" if self.target is None else self.target
        menu.add_command(label=f"🎲  Roll a die  (to {where})", command=lambda: self.roll("dice", 1, 6))
        dice = tk.Menu(menu, tearoff=0, bg=menu.cget("bg"), fg=menu.cget("fg"))
        for count, sides in ((1, 6), (2, 6), (1, 20), (1, 100)):
            label = f"{count}d{sides}" if count > 1 else f"d{sides}"
            dice.add_command(label=label, command=lambda c=count, sd=sides: self.roll("dice", c, sd))
        menu.add_cascade(label="🎲  More dice…", menu=dice)
        menu.add_command(label=f"🪙  Flip a coin  (to {where})", command=lambda: self.roll("coin"))
        menu.add_separator()
        for kind, name in games.GAME_NAMES.items():
            icon = "❌" if kind == "ttt" else "✊"
            if self.target is not None:
                menu.add_command(label=f"{icon}  {name} with {self.target}",
                                 command=lambda k=kind, p=self.target: self.invite(k, p))
            else:
                others = [u for u in self.owner.online_users if u != self.owner.username]
                sub = tk.Menu(menu, tearoff=0, bg=menu.cget("bg"), fg=menu.cget("fg"))
                for person in others:
                    sub.add_command(label=person, command=lambda k=kind, p=person: self.invite(k, p))
                if not others:
                    sub.add_command(label="(nobody else is online)", state="disabled")
                menu.add_cascade(label=f"{icon}  {name} with…", menu=sub)

    def invite(self, kind: str, person: str):
        self.owner.send_json({"type": proto.GAME_INVITE, "game": kind, "opponent": person})

    def roll(self, kind: str, count: int = 1, sides: int = 6):
        self.owner.send_json({"type": proto.GAME_ROLL, "target": self.target, "kind": kind,
                              "count": count, "sides": sides})

    def _run_command(self, text: str) -> bool:
        """/roll, /roll 2d20, /flip -- returns True if it was one of ours. Anything else that
        starts with a slash (like /shrug) is just sent as a normal message."""
        word, _, rest = text.partition(" ")
        word = word.lower()
        if word == "/roll":
            parsed = games.parse_roll(rest)
            if parsed is None:
                self.display_system("Try /roll, /roll 2d20 or /roll d100.")
            else:
                self.roll("dice", *parsed)
            return True
        if word in ("/flip", "/coin"):
            self.roll("coin")
            return True
        if word == "/request":
            self._request_command(rest)
            return True
        return False

    def _request_command(self, rest: str):
        """/request 12.50 pizza   (in a private chat: asks that person)
           /request bob 12.50 pizza   (anywhere)"""
        parts = rest.split(None, 2 if self.target is None else 1)
        person = self.target
        if self.target is None:
            if len(parts) < 2:
                self.display_system("Try /request bob 12.50 pizza money   (or open a private chat and type /request 12.50 pizza).")
                return
            person, parts = parts[0].lstrip("@"), parts[1:]
        cents = parse_amount_to_cents(parts[0]) if parts else None
        if cents is None:
            self.display_system("Type the amount like 12 or 12.50, for example: /request 12.50 pizza money")
            return
        note = parts[1] if len(parts) > 1 else ""
        self.owner.send_json({"type": proto.PAY_REQUEST, "payer": person, "amount_cents": cents, "note": note})

    def start_edit(self, message_id: int):
        record = self.records.get(message_id)
        if not record or record.get("msg_type") == "file":
            return
        self.editing_id = message_id
        self.entry.delete(0, "end")
        self.entry.insert(0, record["text"])
        self.entry.focus_set()
        self.edit_banner.config(text="Editing message — Enter to save, Esc to cancel")
        self.edit_banner.pack(fill="x", side="top", padx=10, before=self.typing_label)

    def cancel_edit(self):
        if self.editing_id is not None:
            self.editing_id = None
            self.entry.delete(0, "end")
        self.edit_banner.pack_forget()

    def request_delete(self, message_id: int):
        if messagebox.askyesno("Delete message", "Delete this message for everyone?"):
            self.owner.send_json({"type": proto.DELETE, "message_id": message_id})

    def toggle_reaction(self, message_id: int, emoji: str):
        record = self.records.get(message_id)
        if not record:
            return
        entry = next((r for r in record.get("reactions", []) if r["emoji"] == emoji), None)
        action = "remove" if (entry and self.owner.username in entry["users"]) else "add"
        self.owner.send_json({"type": proto.REACTION, "message_id": message_id,
                               "emoji": emoji, "action": action})

    # -------------------------------------------------
    # CONTEXT MENU (react / edit / delete)
    # -------------------------------------------------
    def _show_context_menu(self, event):
        try:
            idx = self.messages_area.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        message_id = None
        for t in self.messages_area.tag_names(idx):
            if t.startswith("m") and t[1:].isdigit():
                message_id = int(t[1:])
                break
        if message_id is None:
            return
        record = self.records.get(message_id)
        if not record or record.get("deleted"):
            return

        menu = tk.Menu(self, tearoff=0)
        react_menu = tk.Menu(menu, tearoff=0)
        for emoji in REACTION_EMOJI:
            react_menu.add_command(label=emoji, command=lambda e=emoji: self.toggle_reaction(message_id, e))
        react_menu.add_separator()
        react_menu.add_command(label="More…", command=lambda: self.owner.open_emoji_picker(
            lambda e: self.toggle_reaction(message_id, e), close_on_pick=True))
        menu.add_cascade(label="React", menu=react_menu)

        if record["sender"] == self.owner.username:
            menu.add_separator()
            if record.get("msg_type") != "file":
                menu.add_command(label="Edit", command=lambda: self.start_edit(message_id))
            menu.add_command(label="Delete", command=lambda: self.request_delete(message_id))
        elif record.get("msg_type") == "file" and record.get("local_path") is None:
            menu.add_separator()
            menu.add_command(label="Download", command=lambda: self._request_file(message_id))

        if record.get("msg_type") == "file" and record.get("local_path"):
            menu.add_separator()
            menu.add_command(label="Open file", command=lambda: open_file_externally(record["local_path"]))

        menu.tk_popup(event.x_root, event.y_root)

    def _request_file(self, message_id: int):
        self.owner.send_json({"type": proto.FILE_FETCH, "message_id": message_id})

    # -------------------------------------------------
    # FILE SENDING
    # -------------------------------------------------
    def attach_file(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        size = os.path.getsize(path)
        if size > proto.MAX_FILE_SIZE:
            messagebox.showerror("File too big",
                                  f"Max file size is {proto.MAX_FILE_SIZE // (1024*1024)} MB.")
            return
        threading.Thread(target=self._send_file_thread, args=(path, size), daemon=True).start()

    def _send_file_thread(self, path: str, size: int):
        file_id = str(uuid.uuid4())
        filename = os.path.basename(path)
        total_chunks = max(1, math.ceil(size / proto.FILE_CHUNK_SIZE))

        # Remember this is our own outgoing file so the FILE_START echo
        # doesn't try to re-download something we already have.
        self.owner.outgoing_files[file_id] = path

        self.owner.send_json({"type": proto.FILE_START, "file_id": file_id, "target": self.target,
                               "filename": filename, "size": size, "total_chunks": total_chunks})
        with open(path, "rb") as f:
            index = 0
            while True:
                chunk = f.read(proto.FILE_CHUNK_SIZE)
                if not chunk:
                    break
                b64 = base64.b64encode(chunk).decode("ascii")
                self.owner.send_json({"type": proto.FILE_CHUNK, "file_id": file_id, "index": index, "data": b64})
                index += 1
        self.owner.send_json({"type": proto.FILE_END, "file_id": file_id})

    # -------------------------------------------------
    # FILE RECEIVING
    # -------------------------------------------------
    def on_file_start(self, msg: dict):
        # A re-fetched history file arrives as a FILE_START too. Keep the record
        # we already have (it holds the reactions) rather than rebuilding it.
        record = self.records.get(msg["id"]) or self._record_from_text_msg(msg)

        own_path = self.owner.outgoing_files.get(msg["file_id"])
        if own_path:
            record["local_path"] = own_path
            self.upsert_message(record)
            return  # it's our own upload -- nothing to receive
        self.upsert_message(record)

        self.file_buffers[msg["file_id"]] = {
            "message_id": msg["id"], "filename": msg["filename"],
            "total_chunks": msg["total_chunks"], "parts": {},
        }

    def on_file_chunk(self, msg: dict):
        buf = self.file_buffers.get(msg["file_id"])
        if buf is None:
            return
        buf["parts"][msg["index"]] = msg["data"]

    def on_file_end(self, msg: dict):
        buf = self.file_buffers.pop(msg["file_id"], None)
        if buf is None:
            return
        try:
            os.makedirs(DOWNLOADS_DIR, exist_ok=True)
            pieces = [buf["parts"][i] for i in range(buf["total_chunks"])]
            raw = b"".join(base64.b64decode(p) for p in pieces)
            safe_path = os.path.join(DOWNLOADS_DIR, f"{msg['file_id']}_{buf['filename']}")
            with open(safe_path, "wb") as f:
                f.write(raw)
        except Exception as e:
            self.display_system(f"Failed to save {buf['filename']}: {e}")
            return

        self.loading.discard(buf["message_id"])
        record = self.records.get(buf["message_id"])
        if record:
            record["local_path"] = safe_path
            self.upsert_message(record)


# ─────────────────────────────────────────────────────────────
# SETTINGS DIALOG: change username / change password
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# GAMES (the server is the referee -- these windows only show what it says
# and ask for moves; see games.py)
# ─────────────────────────────────────────────────────────────
RPS_EMOJI = {"rock": "✊", "paper": "✋", "scissors": "✌"}


class GameInviteDialog(tk.Toplevel):
    """\"Sam wants to play Tic-Tac-Toe\" -- Accept / Decline. Not modal: you can keep chatting."""

    def __init__(self, owner: "ChatWindow", invite: dict):
        super().__init__(owner)
        self.owner = owner
        self.game_id = invite["game_id"]
        t = owner.theme
        self.title("Game invite")
        self.resizable(False, False)
        self.configure(bg=t["window"])
        add_header(self, t, "Game invite", "Someone wants to play", height=54)
        name = games.GAME_NAMES.get(invite.get("game"), "a game")
        body = tk.Frame(self, bg=t["window"])
        body.pack(padx=30, pady=(16, 18))
        tk.Label(body, text="🎮", bg=t["window"], font=("Segoe UI Emoji", 28)).pack()
        tk.Label(body, text=f"{invite['sender']} wants to play\n{name}!", bg=t["window"], fg=t["text"],
                 font=(t["font"], t["font_size"] + 2, "bold"), justify="center").pack(pady=(2, 14))
        row = tk.Frame(body, bg=t["window"])
        row.pack()
        PillButton(row, "Accept", lambda: self._answer(True), t=t, width=110).pack(side="left", padx=5)
        PillButton(row, "Decline", lambda: self._answer(False), t=t, style="soft", width=110).pack(side="left", padx=5)
        self.protocol("WM_DELETE_WINDOW", lambda: self._answer(False))
        self.after(int(invite.get("expires_in", 120)) * 1000, self.close)   # the server expires it too
        owner.game_invites[self.game_id] = self
        self.transient(owner)

    def _answer(self, accept: bool):
        self.owner.send_json({"type": proto.GAME_RESPOND, "game_id": self.game_id, "accept": accept})
        self.close()

    def close(self):
        self.owner.game_invites.pop(self.game_id, None)
        if self.winfo_exists():
            self.destroy()


class GameWindow(tk.Toplevel):
    """One live game (Tic-Tac-Toe or Rock-Paper-Scissors). update_state() redraws everything
    from the server's latest state -- the window never keeps its own copy of the rules."""

    def __init__(self, owner: "ChatWindow", state: dict):
        super().__init__(owner)
        self.owner = owner
        self.game_id = state["game_id"]
        self.kind = state["game"]
        self.me = owner.username
        self.opp = next(p for p in state["players"] if p != self.me)
        self.gstate = state
        self.title(f"{games.GAME_NAMES[self.kind]} — vs {self.opp}")
        self.resizable(False, False)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.request_close)
        self._build()
        self.apply_theme()
        self.update_state(state)

    # ---- layout ---------------------------------------------------------
    def _build(self):
        self.heading = tk.Label(self, text=f"{games.GAME_NAMES[self.kind]}", anchor="center")
        self.heading.pack(fill="x", padx=20, pady=(14, 2))
        self.sub = tk.Label(self, text="", anchor="center")
        self.sub.pack(fill="x", padx=20)
        self.board = tk.Frame(self)
        self.board.pack(padx=20, pady=12)
        if self.kind == "ttt":
            self.cells = []
            for i in range(9):
                b = tk.Button(self.board, text="", width=3, height=1, relief="flat", bd=0,
                              command=lambda i=i: self._ttt_click(i))
                b.grid(row=i // 3, column=i % 3, padx=3, pady=3, ipadx=10, ipady=6)
                self.cells.append(b)
        else:
            self.rps_buttons = {}
            for choice, emoji in RPS_EMOJI.items():
                b = tk.Button(self.board, text=f"{emoji}\n{choice.title()}", width=9, relief="flat", bd=0,
                              command=lambda c=choice: self._rps_pick(c))
                b.pack(side="left", padx=4, ipady=8)
                self.rps_buttons[choice] = b
        self.status = tk.Label(self, text="", wraplength=300, justify="center")
        self.status.pack(fill="x", padx=20, pady=(0, 6))
        self.quit_btn = tk.Button(self, text="Close", command=self.request_close, relief="flat", padx=14)
        self.quit_btn.pack(pady=(0, 14))

    def apply_theme(self):
        t = self.owner.theme
        fam, size = t["font"], t["font_size"]
        self.configure(bg=t["window"])
        for w in (self.sub, self.status):
            w.configure(bg=t["window"], fg=t["text"], font=(fam, size))
        self.heading.configure(bg=t["window"], fg=t["text"], font=(fam, size + 4, "bold"))
        self.board.configure(bg=t["window"])
        self.quit_btn.configure(bg=t["header_btn"], fg="white", activebackground=t["header_btn"],
                                activeforeground="white", font=(fam, size))
        if hasattr(self, "gstate"):
            self._render()

    # ---- talking to the server ---------------------------------------------
    def _ttt_click(self, cell: int):
        self.owner.send_json({"type": proto.GAME_MOVE, "game_id": self.game_id, "move": cell})

    def _rps_pick(self, choice: str):
        self.owner.send_json({"type": proto.GAME_MOVE, "game_id": self.game_id, "move": choice})

    def update_state(self, state: dict):
        self.gstate = state
        self._render()

    def request_close(self):
        status = self.gstate.get("status")
        if status == "active" and not messagebox.askyesno(
                "Leave game", f"Leave this game? {self.opp} will win.", parent=self):
            return
        if status in ("pending", "active"):
            self.owner.closed_games.add(self.game_id)   # ignore any in-flight updates for it
            self.owner.send_json({"type": proto.GAME_QUIT, "game_id": self.game_id})
        self.close()

    def close(self):
        self.owner.game_windows.pop(self.game_id, None)
        if self.winfo_exists():
            self.destroy()

    # ---- drawing ------------------------------------------------------------
    def _render(self):
        st, t = self.gstate, self.owner.theme
        status = st.get("status")
        mine = st.get("winner") == self.me
        self.quit_btn.configure(text={"pending": "Cancel invite", "active": "Forfeit"}.get(status, "Close"))
        if status == "pending":
            self.sub.configure(text=f"You vs {self.opp}")
            self.status.configure(text=f"Waiting for {self.opp} to accept…")
        elif status == "over":
            self.sub.configure(text=f"You vs {self.opp}")
            self.status.configure(text=st.get("result", "") + ("  🎉" if mine else ""))
        if self.kind == "ttt":
            self._render_ttt(st, t, status)
        else:
            self._render_rps(st, t, status)

    def _render_ttt(self, st, t, status):
        board = st.get("board") or [None] * 9
        turn = st.get("turn")
        marks = st.get("marks") or {}
        win_line = set(st.get("line") or [])
        x_col = themes.readable_on("#e06c75", t["chat_bg"])
        o_col = themes.readable_on("#61afef", t["chat_bg"])
        for i, b in enumerate(self.cells):
            mark = board[i]
            col = x_col if mark == "X" else o_col
            can_click = status == "active" and turn == self.me and mark is None
            b.configure(text=mark or "", font=(t["font"], 26, "bold"),
                        bg=t["accent"] if i in win_line else t["chat_bg"],
                        fg=t["accent_text"] if i in win_line else col,
                        disabledforeground=t["accent_text"] if i in win_line else col,
                        activebackground=t["mention"], state="normal" if can_click else "disabled",
                        cursor="hand2" if can_click else "arrow")
        if status == "active":
            self.sub.configure(text=f"You are {marks.get(self.me, '?')}  ·  {self.opp} is {marks.get(self.opp, '?')}")
            self.status.configure(text="Your turn!" if turn == self.me else f"{self.opp}'s turn…")

    def _render_rps(self, st, t, status):
        scores = st.get("scores") or {}
        chosen = st.get("chosen") or {}
        picked = chosen.get(self.me, False)
        for choice, b in self.rps_buttons.items():
            can_click = status == "active" and not picked
            b.configure(bg=t["chat_bg"], fg=t["text"], activebackground=t["mention"], activeforeground=t["text"],
                        disabledforeground=t["muted"], font=(t["font"], t["font_size"] + 1),
                        state="normal" if can_click else "disabled", cursor="hand2" if can_click else "arrow")
        if status == "pending":
            return
        line = (f"You {scores.get(self.me, 0)}  –  {scores.get(self.opp, 0)} {self.opp}   "
                f"(first to {st.get('wins_needed', 2)})")
        last = st.get("last")
        if last:
            picks = last["picks"]
            who = "a tie" if last["winner"] is None else ("you won it" if last["winner"] == self.me else f"{self.opp} won it")
            line += (f"\nLast round: {RPS_EMOJI[picks[self.me]]} vs {RPS_EMOJI[picks[self.opp]]} — {who}")
        self.sub.configure(text=line)
        if status == "active":
            if picked:
                self.status.configure(text=f"Locked in! Waiting for {self.opp}…")
            elif chosen.get(self.opp):
                self.status.configure(text=f"{self.opp} has picked — your move!")
            else:
                self.status.configure(text="Pick one!")


class SettingsDialog(tk.Toplevel):
    def __init__(self, owner: "ChatWindow"):
        super().__init__(owner)
        self.owner = owner
        self.title("Settings")
        self.resizable(False, False)
        self.transient(owner)
        self.configure(bg=owner.theme["window"])
        add_header(self, owner.theme, "Settings", "Make the chat yours", height=54)

        tabs = ui.PillTabs(self, owner.theme)           # same rounded pill tabs as the chat window
        tabs.pack(fill="both", expand=True)
        profile = ttk.Frame(tabs)
        account = ttk.Frame(tabs)
        card = ttk.Frame(tabs)
        tabs.add(profile, text="Picture")
        theme_tab = ttk.Frame(tabs)
        tabs.add(theme_tab, text="Theme")
        self.theme_frame = theme_tab
        tabs.add(card, text="Profile card")
        tabs.add(account, text="Account")
        security = ttk.Frame(tabs)
        tabs.add(security, text="Security")
        danger = ttk.Frame(tabs)
        tabs.add(danger, text="Delete")
        self.tabs = tabs
        self.card_frame = card
        self._build_card_tab(card)
        self._build_theme_tab(theme_tab)

        # ---- profile picture ---------------------------------------------
        ttk.Label(profile, text="Your profile picture").pack(pady=(16, 6))
        self.preview_lbl = tk.Label(profile, font=("Segoe UI", 9), fg="#888888")
        self.preview_lbl.pack(pady=6)
        PillButton(profile, text="Choose picture…", command=self._choose_avatar).pack(pady=(8, 2))
        PillButton(profile, text="Remove picture", command=self._remove_avatar, style="soft").pack(pady=2)
        tk.Label(profile, text="Any image works: it's cropped to a square and shrunk.\n"
                               "Everyone in the chat sees it next to your name.",
                 font=("Segoe UI", 8), fg="#888888", justify="center").pack(padx=20, pady=(8, 16))
        self.refresh_avatar_preview()

        # ---- delete account ------------------------------------------------
        tk.Label(danger, text="Delete your account", font=("Segoe UI", 12, "bold"),
                 fg="#c0392b").pack(padx=18, pady=(16, 4), anchor="w")
        tk.Label(danger, justify="left", font=("Segoe UI", 9), text=(
            "This is permanent and can't be undone.\n\n"
            "What gets deleted:\n"
            "   \u2022 your account, password and security questions\n"
            "   \u2022 every message and file you sent, for everyone\n"
            "   \u2022 private messages other people sent you\n"
            "   \u2022 your reactions and profile picture\n\n"
            "Your username becomes free for anyone to register.")).pack(padx=18, anchor="w")
        ttk.Label(danger, text="Your current password").pack(anchor="w", padx=18, pady=(12, 0))
        self.del_pw_entry = ttk.Entry(danger, show="*", width=42)
        self.del_pw_entry.pack(padx=18, anchor="w")
        ttk.Label(danger, text=f"Type your username ({owner.username}) to confirm").pack(anchor="w", padx=18, pady=(8, 0))
        self.del_confirm_entry = ttk.Entry(danger, width=42)
        self.del_confirm_entry.pack(padx=18, anchor="w")
        self.del_btn = PillButton(danger, text="Delete my account permanently", command=self._delete_account,
                                  style="danger", state="disabled")
        self.del_btn.pack(padx=18, pady=(14, 18), anchor="w")
        self.del_pw_entry.bind("<KeyRelease>", self._update_delete_button)
        self.del_confirm_entry.bind("<KeyRelease>", self._update_delete_button)

        # ---- security questions (for "forgot password") --------------------
        ttk.Label(security, text="If you forget your password, these let you reset it.").pack(padx=14, pady=(14, 0))
        self.sec_status = tk.Label(security, text="", font=("Segoe UI", 9, "bold"))
        self.sec_status.pack(padx=14, pady=(2, 0))
        self.sec_boxes, self.sec_answers = [], []
        for i in range(3):
            ttk.Label(security, text=f"Question {i + 1}").pack(anchor="w", padx=14, pady=(8, 0))
            box = ttk.Combobox(security, values=account_api.SECURITY_QUESTIONS, state="readonly", width=46)
            box.pack(padx=14)
            answer = ttk.Entry(security, width=49)
            answer.pack(padx=14, pady=(2, 0))
            self.sec_boxes.append(box)
            self.sec_answers.append(answer)
        ttk.Label(security, text="Your current password").pack(anchor="w", padx=14, pady=(12, 0))
        self.sec_pw_entry = ttk.Entry(security, show="*", width=49)
        self.sec_pw_entry.pack(padx=14)
        tk.Label(security, text="Answers aren't case-sensitive and are never shown again.\n"
                                "To change a question, type all three answers again.",
                 font=("Segoe UI", 8), fg="#888888", justify="center").pack(padx=14, pady=(6, 0))
        PillButton(security, text="Save security questions", command=self._save_security).pack(pady=(8, 14))
        self._load_security_status()

        # ---- ONE current-password box, used by both actions below --------
        top = ttk.LabelFrame(account, text="Confirm it's you")
        top.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(top, text=f"Your current password (for {owner.username})").pack(anchor="w", padx=10, pady=(8, 0))
        self.current_pw_entry = ttk.Entry(top, show="*", width=34)
        self.current_pw_entry.pack(padx=10)
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Show passwords", variable=self.show_var,
                        command=self._toggle_show).pack(anchor="w", padx=10, pady=(4, 8))

        # ---- change username -------------------------------------------
        user_box = ttk.LabelFrame(account, text="Change username")
        user_box.pack(fill="x", padx=12, pady=6)
        ttk.Label(user_box, text="New username").pack(anchor="w", padx=10, pady=(8, 0))
        self.new_user_entry = ttk.Entry(user_box, width=34)
        self.new_user_entry.pack(padx=10)
        tk.Label(user_box, text="3-30 characters: letters, numbers, underscores.\n"
                                "You'll be asked to log in again afterwards.",
                 font=("Segoe UI", 8), fg="#888888", justify="left").pack(anchor="w", padx=10, pady=(4, 0))
        PillButton(user_box, text="Change username", command=self._change_username).pack(pady=10)

        # ---- change password -------------------------------------------
        pw_box = ttk.LabelFrame(account, text="Change password")
        pw_box.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Label(pw_box, text="New password").pack(anchor="w", padx=10, pady=(8, 0))
        self.new_pw_entry = ttk.Entry(pw_box, show="*", width=34)
        self.new_pw_entry.pack(padx=10)
        self.new_pw_entry.bind("<KeyRelease>", self._update_strength)
        self.strength_lbl = tk.Label(pw_box, text="", font=("Segoe UI", 9, "bold"))
        self.strength_lbl.pack(anchor="w", padx=10, pady=(4, 0))
        self.requirements_lbl = tk.Label(pw_box, text="", font=("Segoe UI", 8), fg="#888888", justify="left")
        self.requirements_lbl.pack(anchor="w", padx=10)
        ttk.Label(pw_box, text="Confirm new password").pack(anchor="w", padx=10, pady=(8, 0))
        self.confirm_pw_entry = ttk.Entry(pw_box, show="*", width=34)
        self.confirm_pw_entry.pack(padx=10)
        PillButton(pw_box, text="Change password", command=self._change_password).pack(pady=10)

        # ---- match the chat's theme (colors, fonts, rounded look) -----------
        for w in (*self._theme_buttons.values(), self.accent_btn, self.bg_btn, self.theme_preview,
                  self.banner_swatch):
            w._pk_skip = True              # these show specific colors on purpose
        self._themer = Themer(self, lambda: self.owner.theme)
        self._themer.apply()
        self.update_idletasks()            # every tab gets the size of the biggest one, so the window never jumps
        pages = (profile, theme_tab, card, account, security, danger)
        tabs.content.configure(width=max([560] + [p.winfo_reqwidth() for p in pages]),
                               height=max(p.winfo_reqheight() for p in pages))
        tabs.content.pack_propagate(False)
        popup_kit.center_on(self, owner)

        try:                       # make it modal (needs the window to be on screen first)
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.current_pw_entry.focus_set()

    # ---- theme tab ----------------------------------------------------------
    def _build_theme_tab(self, f):
        o = self.owner
        ttk.Label(f, text="Make the chat yours").pack(pady=(14, 0))
        tk.Label(f, text="Themes only change how the chat looks on YOUR screen.",
                 font=("Segoe UI", 8), fg="#888888").pack()

        grid = tk.Frame(f)
        grid.pack(padx=14, pady=(10, 4))
        self._theme_buttons = {}
        for i, name in enumerate(themes.THEMES):
            tv = themes.THEMES[name]
            b = tk.Button(grid, text=name, width=12, relief="flat", bd=2, font=("Segoe UI", 9, "bold"),
                          bg=tv["chat_bg"], fg=tv["text"], activebackground=tv["accent"],
                          activeforeground=themes.text_color_on(tv["accent"]),
                          highlightthickness=0, command=lambda n=name: self._pick_theme(n))
            b.grid(row=i // 4, column=i % 4, padx=3, pady=3)
            self._theme_buttons[name] = b

        tweaks = tk.Frame(f)
        tweaks.pack(fill="x", padx=18, pady=(8, 0))
        ttk.Label(tweaks, text="Accent color").grid(row=0, column=0, sticky="w", pady=3)
        self.accent_btn = tk.Button(tweaks, width=10, relief="flat", command=self._pick_accent, text="Pick...")
        self.accent_btn.grid(row=0, column=1, padx=6)
        PillButton(tweaks, text="Use theme's", command=lambda: self._set_pref(accent=None), style="soft", height=32).grid(row=0, column=2)
        ttk.Label(tweaks, text="Chat background").grid(row=1, column=0, sticky="w", pady=3)
        self.bg_btn = tk.Button(tweaks, width=10, relief="flat", command=self._pick_chat_bg, text="Pick...")
        self.bg_btn.grid(row=1, column=1, padx=6)
        PillButton(tweaks, text="Use theme's", command=lambda: self._set_pref(chat_bg=None), style="soft", height=32).grid(row=1, column=2)

        ttk.Label(tweaks, text="Font").grid(row=2, column=0, sticky="w", pady=3)
        self.font_box = ttk.Combobox(tweaks, values=themes.FONT_CHOICES, state="readonly", width=16)
        self.font_box.grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        self.font_box.bind("<<ComboboxSelected>>", lambda e: self._set_pref(font=self.font_box.get()))
        ttk.Label(tweaks, text="Text size").grid(row=3, column=0, sticky="w", pady=3)
        self.size_box = ttk.Combobox(tweaks, values=themes.FONT_SIZES, state="readonly", width=6)
        self.size_box.grid(row=3, column=1, sticky="w", padx=6)
        self.size_box.bind("<<ComboboxSelected>>", lambda e: self._set_pref(font_size=int(self.size_box.get())))
        ttk.Label(tweaks, text="Spacing").grid(row=4, column=0, sticky="w", pady=3)
        self.density_box = ttk.Combobox(tweaks, values=list(themes.DENSITIES), state="readonly", width=10)
        self.density_box.grid(row=4, column=1, sticky="w", padx=6)
        self.density_box.bind("<<ComboboxSelected>>", lambda e: self._set_pref(density=self.density_box.get()))

        ttk.Label(f, text="Preview").pack(anchor="w", padx=18, pady=(10, 0))
        self.theme_preview = tk.Text(f, width=46, height=6, wrap="word", state="disabled", bd=0, padx=8, pady=6)
        self.theme_preview.pack(padx=18, pady=(2, 6))
        PillButton(f, text="Reset to default look", command=self._reset_theme, style="soft").pack(pady=(0, 14))
        self.refresh_theme_preview()

    def _set_pref(self, **changes):
        prefs = dict(self.owner.theme_prefs)
        prefs.update(changes)
        self.owner.set_theme_prefs(prefs)

    def _pick_theme(self, name: str):
        # choosing a preset also clears your accent/background overrides, so what you
        # click is what you get; font, size and spacing are kept
        self._set_pref(theme=name, accent=None, chat_bg=None)

    def _pick_accent(self):
        _rgb, hx = colorchooser.askcolor(color=self.owner.theme["accent"], title="Accent color", parent=self)
        if hx:
            self._set_pref(accent=hx.lower())

    def _pick_chat_bg(self):
        _rgb, hx = colorchooser.askcolor(color=self.owner.theme["chat_bg"], title="Chat background", parent=self)
        if hx:
            self._set_pref(chat_bg=hx.lower())

    def _reset_theme(self):
        self.owner.set_theme_prefs(dict(themes.DEFAULT_PREFS))

    def refresh_theme_preview(self):
        t, prefs = self.owner.theme, self.owner.theme_prefs
        themer = getattr(self, "_themer", None)
        if themer is not None:
            themer.apply()                 # the Settings window itself follows the theme you just picked
        for name, b in self._theme_buttons.items():
            b.configure(relief="solid" if name == prefs["theme"] else "flat",
                        text=("✓ " if name == prefs["theme"] else "") + name)
        self.accent_btn.configure(bg=t["accent"], fg=t["accent_text"], activebackground=t["accent"])
        self.bg_btn.configure(bg=t["chat_bg"], fg=t["text"], activebackground=t["chat_bg"])
        self.font_box.set(prefs["font"])
        self.size_box.set(prefs["font_size"])
        self.density_box.set(prefs["density"])

        fam, size = t["font"], t["font_size"]
        w = self.theme_preview
        w.configure(state="normal", bg=t["chat_bg"], fg=t["text"], font=(fam, size))
        w.delete("1.0", "end")
        for tag in w.tag_names():
            if tag != "sel":
                w.tag_delete(tag)
        w.tag_configure("name", font=(fam, size, "bold"), foreground=themes.readable_on("#61afef", t["chat_bg"]))
        w.tag_configure("me", font=(fam, size, "bold"), foreground=themes.readable_on(YOU_COLOR, t["chat_bg"]))
        w.tag_configure("ts", font=(fam, max(7, size - 2)), foreground=t["muted"])
        w.tag_configure("men", background=t["mention_me"], foreground=t["text"], font=(fam, size, "bold"))
        w.tag_configure("link", foreground=t["link"], underline=True)
        w.tag_configure("gap", font=(fam, t["gap"]))
        w.insert("end", "Sam ", "name"); w.insert("end", "10:42 AM\n", "ts")
        w.insert("end", "hey! are we still on for tonight?\n"); w.insert("end", "\n", "gap")
        w.insert("end", "You ", "me"); w.insert("end", "10:43 AM\n", "ts")
        w.insert("end", "yep! "); w.insert("end", "@Sam", "men"); w.insert("end", " see ")
        w.insert("end", "example.com", "link"); w.insert("end", "\n")
        w.configure(state="disabled")

    # ---- profile card tab -------------------------------------------------
    def _build_card_tab(self, f):
        self._banner = None
        ttk.Label(f, text="Your profile card").pack(pady=(14, 0))
        tk.Label(f, text="This is what people see when they click your name.",
                 font=("Segoe UI", 8), fg="#888888").pack()

        ttk.Label(f, text="About me").pack(anchor="w", padx=16, pady=(10, 0))
        self.bio_box = tk.Text(f, width=44, height=4, wrap="word", font=("Segoe UI", 9))
        self.bio_box.pack(padx=16)
        self.bio_box.bind("<KeyRelease>", self._bio_changed)
        self.bio_count = tk.Label(f, text=f"0/{proto.BIO_MAX}", font=("Segoe UI", 8), fg="#888888", anchor="e")
        self.bio_count.pack(fill="x", padx=16)

        row = ttk.Frame(f)
        row.pack(fill="x", padx=16, pady=(4, 0))
        ttk.Label(row, text="Pronouns").pack(side="left")
        self.pronoun_entry = ttk.Entry(row, width=18)
        self.pronoun_entry.pack(side="left", padx=(8, 18))
        ttk.Label(row, text="Badge").pack(side="left")
        self.badge_entry = ttk.Entry(row, width=5, font=("Segoe UI Emoji", 10))
        self.badge_entry.pack(side="left", padx=(8, 4))
        self.badge_entry.bind("<KeyRelease>", lambda e: self._limit(self.badge_entry, proto.BADGE_MAX))
        PillButton(row, text="Pick…", command=self._pick_badge, style="soft", height=32).pack(side="left")

        row2 = ttk.Frame(f)
        row2.pack(fill="x", padx=16, pady=(10, 0))
        ttk.Label(row2, text="Card color").pack(side="left")
        self.banner_swatch = tk.Label(row2, width=6, bg=DEFAULT_BANNER, relief="solid", bd=1)
        self.banner_swatch.pack(side="left", padx=8)
        PillButton(row2, text="Choose…", command=self._pick_banner, style="soft", height=32).pack(side="left")
        PillButton(row2, text="Default", command=self._reset_banner, style="soft", height=32).pack(side="left", padx=4)

        self.card_save_btn = PillButton(f, text="Save my card", command=self._save_card, state="disabled")
        self.card_save_btn.pack(pady=(14, 2))
        self.card_status = tk.Label(f, text="Loading your card…", font=("Segoe UI", 9), fg="#888888")
        self.card_status.pack(pady=(0, 12))
        self.owner.request_profile(self.owner.username, self._load_card)

    def show_tab(self, name: str | None):
        if name == "card":
            self.tabs.select(self.card_frame)
        elif name == "theme":
            self.tabs.select(self.theme_frame)

    def _load_card(self, msg: dict):
        # Save stays disabled until the real card has loaded, so a failed load can never blank it.
        if msg.get("missing"):
            self.card_status.config(text="Couldn't load your card.", fg="#c0392b")
            return
        self.bio_box.delete("1.0", "end")
        self.bio_box.insert("1.0", msg.get("bio") or "")
        self.pronoun_entry.delete(0, "end")
        self.pronoun_entry.insert(0, msg.get("pronouns") or "")
        self.badge_entry.delete(0, "end")
        self.badge_entry.insert(0, msg.get("badge") or "")
        self._set_banner(msg.get("banner"))
        self._bio_changed()
        self.card_save_btn.config(state="normal")
        self.card_status.config(text="", fg="#888888")

    def _limit(self, entry, max_len):
        text = entry.get()
        if len(text) > max_len:
            entry.delete(max_len, "end")

    def _bio_changed(self, event=None):
        text = self.bio_box.get("1.0", "end-1c")
        if len(text) > proto.BIO_MAX:
            self.bio_box.delete(f"1.0+{proto.BIO_MAX}c", "end")
            text = self.bio_box.get("1.0", "end-1c")
        self.bio_count.config(text=f"{len(text)}/{proto.BIO_MAX}")

    def _set_banner(self, color):
        self._banner = color
        self.banner_swatch.config(bg=color or DEFAULT_BANNER)

    def _pick_banner(self):
        _rgb, hex_color = colorchooser.askcolor(color=self._banner or DEFAULT_BANNER,
                                                title="Pick your card color", parent=self)
        if hex_color:
            self._set_banner(hex_color.lower())

    def _reset_banner(self):
        self._set_banner(None)

    def _pick_badge(self):
        def put(emoji):
            self.badge_entry.delete(0, "end")
            self.badge_entry.insert(0, emoji)
        self.owner.open_emoji_picker(put, close_on_pick=True, parent=self)

    def _save_card(self):
        self.owner.send_json({
            "type": proto.SET_PROFILE,
            "bio": self.bio_box.get("1.0", "end-1c"),
            "pronouns": self.pronoun_entry.get(),
            "badge": self.badge_entry.get(),
            "banner": self._banner,
        })
        self.card_status.config(text="✓ Saved", fg="#2e8b57")

    def _update_delete_button(self, event=None):
        """The red button stays off until BOTH boxes are filled in properly."""
        ready = (bool(self.del_pw_entry.get())
                 and self.del_confirm_entry.get().strip().lower() == self.owner.username.lower())
        self.del_btn.configure(state="normal" if ready else "disabled")

    def _delete_account(self):
        if not messagebox.askyesno(
                "Delete account?",
                "Last chance.\n\nYour account and all your messages will be deleted forever.\n"
                "This cannot be undone.\n\nDelete it?",
                icon="warning", default="no", parent=self):
            return
        ok, message = account_api.delete_account(self.owner.username, self.del_pw_entry.get())
        if not ok:
            messagebox.showerror("Couldn't delete account", message, parent=self)
            return
        messagebox.showinfo("Account deleted", "Your account and messages have been deleted.", parent=self)
        owner = self.owner
        self.destroy()
        owner.account_deleted()

    def _load_security_status(self):
        try:
            questions = account_api.get_security_questions(self.owner.username)
        except Exception:
            self.sec_status.config(text="Not available yet (restart the server once)", fg="#b26a00")
            return
        if len(questions) == 3:
            for box, question in zip(self.sec_boxes, questions):
                box.set(question)
            self.sec_status.config(text="\u2713 Set up", fg="#2e8b57")
        else:
            self.sec_status.config(text="Not set up yet. Recommended!", fg="#b26a00")

    def _save_security(self):
        password = self.sec_pw_entry.get()
        if not password:
            messagebox.showwarning("Current password needed",
                                   "Type your current password first.", parent=self)
            self.sec_pw_entry.focus_set()
            return
        qa = [(box.get(), answer.get()) for box, answer in zip(self.sec_boxes, self.sec_answers)]
        if any(not question for question, _ in qa):
            messagebox.showwarning("Pick 3 questions", "Choose a question in each of the three boxes.", parent=self)
            return
        ok, message = account_api.set_security_questions(self.owner.username, password, qa)
        if not ok:
            messagebox.showerror("Couldn't save", message, parent=self)
            return
        messagebox.showinfo("Saved", "Your security questions are saved.\n"
                                     "Remember your answers -- you'll need all three.", parent=self)
        for answer in self.sec_answers:
            answer.delete(0, "end")
        self.sec_pw_entry.delete(0, "end")
        self._load_security_status()

    def refresh_avatar_preview(self):
        photo = self.owner.avatar_for(self.owner.username, size=AVATAR_STORE)
        self._preview_photo = photo                     # keep a reference or Tk drops the image
        if photo is not None:
            self.preview_lbl.configure(image=photo, text="")
        else:
            self.preview_lbl.configure(image="", text="(no picture)")

    def _choose_avatar(self):
        if not HAVE_PIL:
            messagebox.showinfo("Pillow needed",
                                "Setting a picture needs the Pillow library.\n"
                                "Install it with:  pip install Pillow", parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self, title="Choose a profile picture",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")])
        if not path:
            return
        try:
            b64 = make_avatar_b64(path)
        except Exception as e:
            messagebox.showerror("Couldn't use that image", f"That file couldn't be read as a picture.\n({e})", parent=self)
            return
        self.owner.set_avatar(b64)          # the preview updates when the server confirms

    def _remove_avatar(self):
        self.owner.set_avatar(None)

    def _toggle_show(self):
        mark = "" if self.show_var.get() else "*"
        for entry in (self.current_pw_entry, self.new_pw_entry, self.confirm_pw_entry):
            entry.configure(show=mark)

    def _current_password(self):
        """The shared box's text, or None (after telling the user) if it's empty."""
        password = self.current_pw_entry.get()
        if not password:
            messagebox.showwarning("Current password needed",
                                   "Type your current password in the box at the top first.",
                                   parent=self)
            self.current_pw_entry.focus_set()
            return None
        return password

    def _update_strength(self, event=None):
        password = self.new_pw_entry.get()
        label, color = strength_label(password)
        self.strength_lbl.config(text=label, fg=color)
        _, issues = check_password_strength(password)
        if not password:
            self.requirements_lbl.config(text="")
        elif issues:
            self.requirements_lbl.config(text="\n".join(f"\u2717 {i}" for i in issues))
        else:
            self.requirements_lbl.config(text="\u2713 Meets all requirements")

    def _change_username(self):
        current = self._current_password()
        if current is None:
            return
        new_name = self.new_user_entry.get().strip()
        ok, message = account_api.change_username(self.owner.username, new_name, current)
        if not ok:
            messagebox.showerror("Couldn't change username", message, parent=self)
            return
        messagebox.showinfo("Username changed",
                            f"You're now {new_name}.\nPlease log in again with your new username.",
                            parent=self)
        owner = self.owner
        self.destroy()
        owner.return_to_login(new_name)

    def _change_password(self):
        current = self._current_password()
        if current is None:
            return
        new = self.new_pw_entry.get()
        if new != self.confirm_pw_entry.get():
            messagebox.showerror("Mismatch", "The new passwords don't match.", parent=self)
            return
        ok, message = account_api.change_password(self.owner.username, current, new)
        if not ok:
            messagebox.showerror("Couldn't change password", message, parent=self)
            return
        messagebox.showinfo("Password changed", "Your password was updated.\nUse it next time you log in.",
                            parent=self)
        for entry in (self.current_pw_entry, self.new_pw_entry, self.confirm_pw_entry):
            entry.delete(0, "end")
        self._update_strength()


# ─────────────────────────────────────────────────────────────
# THE WINDOW: connection, sidebar, tabs, routing
# ─────────────────────────────────────────────────────────────

class ChatWindow(tk.Toplevel):
    def __init__(self, master, username: str, server_ip: str = "127.0.0.1", port: int = 5555,
                 sock=None, reader=None):
        """`sock` + `reader` are the connection login_app already logged in (password AND Google
        Authenticator code, see mfa_client.py). The chat window never sees the password."""
        super().__init__(master)
        self.master = master
        self.username = username
        self.server_ip = server_ip
        self.port = port

        self.title(f"Chat Room — {username}")
        self.geometry("1000x700")
        self.minsize(720, 480)

        self.incoming_queue = queue.Queue()
        self.sock = None
        self.online_users: list[str] = []
        self.everyone: list[str] = []                     # EVERY account on the server, online or not
        self.last_seen: dict[str, str] = {}               # username -> ISO time of their last disconnect
        self.unread: dict[str, int] = {}                  # username -> DMs from them you haven't read yet
        self._offline_hint_shown: set[str] = set()        # offline people we've already explained "they'll get it later" for
        self.user_colors: dict[str, str] = {}             # username -> "#rrggbb" they picked
        self.user_avatars: dict[str, str] = {}            # username -> base64 PNG profile picture
        self._avatar_cache: dict[tuple, object] = {}      # (picture, initial, size) -> Tk image (must stay referenced)
        self.panes: dict[str | None, MessagePane] = {}   # target -> pane (room is key None)
        self.outgoing_files: dict[str, str] = {}          # file_id -> local path, for our own uploads
        self.requested_dm_history: set[str] = set()
        self._emoji_picker = None
        self._profile_card = None
        self._profile_waiters: dict[str, list] = {}       # username -> callbacks waiting for their card data
        self.statuses: dict[str, dict] = {}               # username -> {status, text}, for everyone online
        self.my_status = proto.DEFAULT_STATUS
        self.my_status_text = ""
        self._last_activity = time.time()
        self._auto_idle = False
        self.game_windows: dict[str, GameWindow] = {}     # game_id -> its open window
        self.game_invites: dict[str, GameInviteDialog] = {}
        self.closed_games: set[str] = set()               # games I walked away from (ignore stragglers)
        self.language = load_language(username)           # language code messages are shown in ("" = off)
        # which accent set the on-screen keyboard opens with: your reading language if it has one
        self.kb_language = self.language if self.language in KEYBOARD_LAYOUTS else KEYBOARD_DEFAULT
        self.installed_languages: list[str] = []          # offline packs found on this computer
        self._translator = None
        self._last_translate_notice = 0.0
        self.wallet_window = None                         # the open Wallet window, if any
        self.ai_window = None                             # the open AI Friend window, if any
        self.feed_window = None                           # the open Feed window, if any
        self.feed_unseen = 0                              # new posts / likes / comments since the Feed was last open
        self.pay_prompts: dict[str, PaymentPrompt] = {}   # request_id -> its "X is asking you for $" pop-up
        self.pay_requests: dict[str, dict] = {}           # request_id -> latest state the server told us
        self.wallet_demo = False                          # True when the server uses play money (no Stripe)
        self.theme_prefs = themes.load_prefs(username)
        self.theme = themes.build_theme(self.theme_prefs)

        try:
            self.cipher = crypto_utils.load_cipher()
        except FileNotFoundError as e:
            messagebox.showerror("Missing encryption key", str(e))
            self.destroy()
            return

        self._build_ui()
        self.bind("<Motion>", self._on_activity, add="+")      # any mouse/keyboard use = "I'm here"
        self.bind("<KeyPress>", self._on_activity, add="+")
        self.after(20000, self._check_idle)
        threading.Thread(target=self._scan_languages, daemon=True).start()
        if sock is None or reader is None:                  # there is no way in except through login_app
            messagebox.showerror("Not logged in", "The chat window needs a logged-in connection.")
            self.destroy()
            return
        self.sock = sock
        self._reader = reader
        threading.Thread(target=self._receive_loop, daemon=True).start()
        self.bind("<FocusIn>", self._on_focus_in)   # returning to the window counts as reading what's showing

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._poll_incoming)

    # -----------------------------------------------------
    def encrypt(self, text: str) -> str:
        return crypto_utils.encrypt_message(self.cipher, text)

    def decrypt(self, ciphertext: str) -> str:
        try:
            return crypto_utils.decrypt_message(self.cipher, ciphertext)
        except InvalidToken:
            return "[Could not decrypt -- sender may be using a different key]"
        except Exception:
            return ciphertext  # already-plaintext system content, etc.

    # -----------------------------------------------------
    # NAME COLORS
    # -----------------------------------------------------
    def color_for(self, username: str) -> str:
        return self.user_colors.get(username) or color_for_username(username)

    def my_name_color(self) -> str:
        return self.user_colors.get(self.username) or YOU_COLOR

    def display_color(self, username: str) -> str:
        """A person's name color, nudged only if needed so it's readable on YOUR theme."""
        return themes.readable_on(self.color_for(username), self.theme["chat_bg"])

    # -----------------------------------------------------
    # THEME
    # -----------------------------------------------------
    def set_theme_prefs(self, prefs: dict, save: bool = True):
        self.theme_prefs = themes.clean_prefs(prefs)
        self.theme = themes.build_theme(self.theme_prefs)
        if save:
            themes.save_prefs(self.username, self.theme_prefs)
        self.apply_theme()

    def apply_theme(self):
        t = self.theme
        fam, size = t["font"], t["font_size"]
        style = ttk.Style()
        if not hasattr(self, "_orig_ttk_theme"):
            self._orig_ttk_theme = style.theme_use()      # remembered so logging out can put it back
        popup_kit.set_theme(t)           # message boxes, Settings, Wallet... follow the chat's theme
        popup_kit.style_ttk(t)           # (also switches ttk to "clam", the only look that can be recolored)
        self.configure(bg=t["window"])
        self.header.set_theme(t)
        self.sidebar.configure(bg=t["sidebar"])
        self.sidebar_title.configure(bg=t["sidebar"], fg=t["muted"], font=(fam, max(8, size - 2), "bold"))
        self.presence_list.set_theme(t)
        self.notebook.set_theme(t)
        for menu in (self.status_menu, self.more_menu):
            menu.configure(bg=t["input_bg"], fg=t["input_fg"], activebackground=t["accent"],
                           activeforeground=t["accent_text"], font=(fam, size))
        for pane in self.panes.values():
            pane.apply_theme()
            pane.redraw_messages()    # re-draws what's on screen so spacing/fonts apply to old messages too
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.refresh_theme_preview()
        for gw in list(self.game_windows.values()):
            gw.apply_theme()
        wallet = getattr(self, "wallet_window", None)
        if wallet is not None and wallet.winfo_exists():
            wallet.retheme()
        ai = getattr(self, "ai_window", None)
        if ai is not None and ai.winfo_exists():
            ai.retheme()
        feed = getattr(self, "feed_window", None)
        if feed is not None and feed.winfo_exists():
            feed.retheme()

    # -----------------------------------------------------
    # PROFILE PICTURES
    # -----------------------------------------------------
    def avatar_for(self, username: str, size: int = AVATAR_SHOW):
        data = self.user_avatars.get(username)
        letter = (username[:1] or "?").upper()
        key = (data, letter, size)
        if key not in self._avatar_cache:
            self._avatar_cache[key] = avatar_photo(data, size, letter)   # None is cached too
        return self._avatar_cache[key]

    def set_avatar(self, b64: str | None):
        self.send_json({"type": proto.SET_AVATAR, "data": b64})

    def _avatars_changed(self, username: str | None):
        """Redraw whatever shows this person's picture (None = everyone)."""
        for pane in self.panes.values():
            pane.redraw_messages(username)
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is not None and dialog.winfo_exists() and username in (None, self.username):
            dialog.refresh_avatar_preview()

    def choose_color(self):
        _rgb, hex_color = colorchooser.askcolor(
            color=self.my_name_color(), title="Pick your name color", parent=self)
        if not hex_color:
            return   # cancelled
        hex_color = hex_color.lower()
        self.send_json({"type": proto.SET_COLOR, "color": hex_color})

    def reset_color(self):
        self.send_json({"type": proto.SET_COLOR, "color": None})

    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------
    def open_settings(self, tab: str | None = None):
        existing = getattr(self, "_settings_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.show_tab(tab)
            return
        self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.show_tab(tab)

    def account_deleted(self):
        """Our account was just deleted: tell the server, then go back to login."""
        self.send_json({"type": proto.ACCOUNT_DELETED})
        self.return_to_login("")

    def _close_socket(self):
        """Really hang up. shutdown() first: on Linux/macOS a plain close() does NOT
        end the connection while the background thread is still blocked reading it,
        and the server would think you were still here ("username already connected")."""
        sock, self.sock = self.sock, None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def logout(self):
        if messagebox.askyesno("Log out", "Log out and go back to the login screen?", parent=self):
            self.return_to_login(self.username)

    def open_link(self, url: str):
        """Open a clicked link in the browser -- after showing exactly where it goes."""
        if url.lower().startswith("www."):
            url = "https://" + url
        if not url.lower().startswith(("http://", "https://")):
            return
        shown = url if len(url) <= 150 else url[:147] + "..."
        if messagebox.askyesno("Open link?", f"This will open in your web browser:\n\n{shown}\n\n"
                                              "Only continue if you trust who sent it.", parent=self):
            webbrowser.open(url)

    def open_emoji_picker(self, on_pick, close_on_pick: bool = False, parent=None):
        """`parent` matters when the picker is opened from a modal dialog: a modal
        window only lets its own children receive clicks."""
        if self._emoji_picker is not None and self._emoji_picker.winfo_exists():
            self._emoji_picker.destroy()
        self._emoji_picker = EmojiPicker(parent or self, on_pick, close_on_pick)

    # -----------------------------------------------------
    # STATUS (Vibing, Napping, Locked in, ...)
    # -----------------------------------------------------
    def set_status(self, key: str):
        self.my_status, self.my_status_text = key, ""
        self._auto_idle = False
        self._last_activity = time.time()
        self.send_json({"type": proto.SET_STATUS, "status": key, "text": ""})
        self._refresh_status_button()

    def edit_status_text(self):
        text = simpledialog.askstring("Status note", f"What are you up to? (max {proto.STATUS_TEXT_MAX} characters)\n"
                                      "Leave empty to clear it.", initialvalue=self.my_status_text, parent=self)
        if text is None:
            return
        self.my_status_text = text.strip()[:proto.STATUS_TEXT_MAX]
        self.send_json({"type": proto.SET_STATUS, "status": self.my_status, "text": self.my_status_text})

    def _refresh_status_button(self):
        emoji, label, _ = status_parts(self.my_status)
        self.header.set_label("status", f"{emoji} {label} ▾")

    def _on_activity(self, event=None):
        self._last_activity = time.time()
        if self._auto_idle:                                   # welcome back: restore the real status
            self._auto_idle = False
            self.send_json({"type": proto.SET_STATUS, "status": self.my_status, "text": self.my_status_text})

    def _check_idle(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if (self.sock and self.my_status == "active" and not self._auto_idle
                and time.time() - self._last_activity > proto.IDLE_AFTER_SECONDS):
            self._auto_idle = True
            self.send_json({"type": proto.SET_STATUS, "status": "idle", "text": self.my_status_text})
        self.after(20000, self._check_idle)

    def _last_seen_text(self, name: str) -> str:
        """'Last seen 5 min ago' / 'Last seen yesterday' / 'Offline' for someone who isn't here."""
        iso = self.last_seen.get(name)
        if not iso:
            return "Offline"
        try:
            then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            secs = (datetime.now(timezone.utc) - then).total_seconds()
        except Exception:
            return "Offline"
        if secs < 90:
            return "Last seen just now"
        if secs < 3600:
            return f"Last seen {int(secs // 60)} min ago"
        if secs < 86400:
            return f"Last seen {int(secs // 3600)} h ago"
        days = int(secs // 86400)
        return "Last seen yesterday" if days == 1 else f"Last seen {days} days ago"

    def _refresh_presence_list(self):
        """Everyone who has ever joined: people who are here first (with their status), then everyone else
        greyed out. You can message the greyed-out ones too -- they get it the next time they log in."""
        online = list(self.online_users)
        rows = []
        if online:
            rows.append({"name": None, "header": True, "title": f"ONLINE — {len(online)}"})
        for name in online:
            st = self.statuses.get(name) or {}
            key = st.get("status")
            _, label, _ = status_parts(key)
            rows.append({"name": name, "title": name + (" (you)" if name == self.username else ""),
                         "sub": (st.get("text") or "").strip() or label, "status": key,
                         "badge": self.unread.get(name, 0)})
        online_set = set(online)
        # (an older server doesn't send `everyone`; then we just show who's online, like before)
        offline = sorted((n for n in self.everyone if n not in online_set and n != self.username), key=str.lower)
        for n in sorted(self.unread):
            if n not in online_set and n not in offline and n != self.username:
                offline.append(n)
        if offline:
            rows.append({"name": None, "header": True, "title": f"OFFLINE — {len(offline)}"})
        for name in offline:
            rows.append({"name": name, "title": name, "sub": self._last_seen_text(name), "status": "offline",
                         "dim": True, "badge": self.unread.get(name, 0)})
        self.presence_list.set_people(rows)

    def _clear_unread(self, peer):
        if peer and self.unread.pop(peer, None):
            self._refresh_presence_list()

    # -----------------------------------------------------
    # PROFILE CARDS
    # -----------------------------------------------------
    def request_profile(self, username: str, callback):
        self._profile_waiters.setdefault(username, []).append(callback)
        self.send_json({"type": proto.PROFILE_REQUEST, "username": username})

    def show_profile(self, username: str):
        if self._profile_card is not None and self._profile_card.winfo_exists():
            self._profile_card.destroy()
        self._profile_card = ProfileCard(self, username)

    def _sidebar_menu(self, name: str, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="View profile", command=lambda: self.show_profile(name))
        if name != self.username:
            menu.add_command(label="Send message", command=lambda: self.open_dm_tab(name))
            menu.add_command(label="💸 Request money…", command=lambda: self.open_wallet(name))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def return_to_login(self, username_hint: str | None = None):
        """Leave the chat and show the login window again (used after a rename,
        because the server still knows this connection by the old name)."""
        self._close_socket()
        login_window = self.master
        orig = getattr(self, "_orig_ttk_theme", None)
        for gw in list(self.game_windows.values()):
            gw.close()
        if self.wallet_window is not None:
            self.wallet_window.close()
        if self.ai_window is not None:
            self.ai_window.close()
        if self.feed_window is not None and self.feed_window.winfo_exists():
            self.feed_window.close()
        for prompt in list(self.pay_prompts.values()):
            prompt.close()
        self.destroy()
        if orig:
            try:
                ttk.Style().theme_use(orig)      # login window looks exactly like it did before the chat opened
            except tk.TclError:
                pass
        popup_kit.set_theme(None)
        login_window.deiconify()
        try:
            tab = login_window.login_tab
            tab.username_entry.delete(0, "end")
            tab.username_entry.insert(0, username_hint or "")
            tab.password_entry.delete(0, "end")
            tab.password_entry.focus_set()
        except Exception:
            pass   # the login window is only a convenience prefill

    def format_ts(self, ts) -> str:
        if not ts:
            return datetime.now().strftime("%H:%M")
        try:
            return datetime.fromisoformat(ts).strftime("%H:%M")
        except Exception:
            return ""

    # -----------------------------------------------------
    # UI SETUP
    # -----------------------------------------------------
    def _build_ui(self):
        t = self.theme
        self.header = ui.HeaderBar(self, "Chat Room", f"Logged in as {self.username}", t)
        self.header.pack(fill="x", side="top")

        # menus the header pills open
        self.status_menu = tk.Menu(self, tearoff=0)
        for key in proto.PICKABLE_STATUSES:
            emoji, label, meaning = proto.STATUSES[key]
            self.status_menu.add_command(label=f"{emoji}  {label}   —   {meaning}", command=lambda k=key: self.set_status(k))
        self.status_menu.add_separator()
        self.status_menu.add_command(label="✏  Add a note to my status…", command=self.edit_status_text)
        self.more_menu = tk.Menu(self, tearoff=0)
        self.more_menu.add_command(label="🎨  My name color…", command=self.choose_color)
        self.more_menu.add_command(label="↺  Reset my name color", command=self.reset_color)
        self.more_menu.add_command(label="🖌  Theme…", command=lambda: self.open_settings("theme"))
        self.more_menu.add_command(label="🌐  Language…", command=self.open_language_menu)
        self.header.set_buttons([
            ("status", "", self._open_status_menu),
            ("feed", "Feed", self.open_feed),
            ("ai", "AI Friend", self.open_ai_friend),
            ("wallet", "Wallet", self.open_wallet),
            ("settings", "Settings", self.open_settings),
            ("more", "More ▾", self._open_more_menu),
            ("logout", "Log out", self.logout),
        ])
        self._refresh_status_button()

        body = tk.Frame(self, bg=t["window"])
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(body, bg=t["sidebar"], width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.sidebar = sidebar
        self.sidebar_title = tk.Label(sidebar, text="PEOPLE", bg=t["sidebar"], fg=t["muted"],
                                      font=ui.font(8, True), anchor="w")
        self.sidebar_title.pack(fill="x", padx=18, pady=(16, 6))
        self.presence_list = ui.PeopleList(sidebar, t, self.avatar_for,
                                           on_open=self._open_dm_from_sidebar, on_menu=self._sidebar_menu)
        self.presence_list.pack(fill="both", expand=True, pady=(0, 8))

        main = tk.Frame(body, bg=t["window"])
        main.pack(side="left", fill="both", expand=True)

        self.notebook = self._make_notebook(main)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        room_pane = MessagePane(self.notebook, self, target=None)
        self.panes[None] = room_pane
        self.notebook.add(room_pane, text="Room")
        self.apply_theme()

    def _open_status_menu(self):
        x, y = self.header.anchor_of("status")
        try:
            self.status_menu.tk_popup(x, y)
        finally:
            self.status_menu.grab_release()

    def _open_more_menu(self):
        x, y = self.header.anchor_of("more")
        try:
            self.more_menu.tk_popup(x, y)
        finally:
            self.more_menu.grab_release()

    def _make_notebook(self, parent):
        return ui.PillTabs(parent, self.theme)

    def _open_dm_from_sidebar(self, name=None):
        if name and name != self.username:      # raw username, never the "(you)" display label
            self.open_dm_tab(name)

    def open_dm_tab(self, peer: str, focus: bool = True):
        if peer not in self.panes:
            pane = MessagePane(self.notebook, self, target=peer)
            self.panes[peer] = pane
            self.notebook.add(pane, text=peer)
            if peer not in self.requested_dm_history:
                self.requested_dm_history.add(peer)
                self.send_json({"type": proto.HISTORY_REQUEST, "peer": peer})
        if focus:
            self.notebook.select(self.panes[peer])

    def _tab_title_for(self, target: str | None) -> str:
        return "Room" if target is None else target

    def _on_tab_changed(self, event=None):
        # Selecting a tab clears its "new activity" marker.
        current = self.notebook.select()
        if not current:
            return
        idx = self.notebook.index(current)
        target = self._target_for_tab_index(idx)
        self.notebook.tab(idx, text=self._tab_title_for(target))
        pane = self.panes.get(target)
        if pane is not None:
            pane.send_pending_reads()
        if target is not None:
            self._clear_unread(target)

    def is_viewing(self, target) -> bool:
        """True only if the person can actually SEE this conversation right now:
        window not minimized, window has keyboard focus, and its tab is selected."""
        try:
            if self.state() == "iconic":
                return False
            if self.focus_displayof() is None:        # another app has the focus
                return False
            pane = self.panes.get(target)
            return pane is not None and self.notebook.select() == str(pane)
        except tk.TclError:
            return False

    def _on_focus_in(self, event=None):
        """Coming back to the window: whatever tab is showing is now being read."""
        current = self.notebook.select()
        for pane in self.panes.values():
            if str(pane) == current:
                pane.send_pending_reads()
                self._clear_unread(pane.target)
                break

    def _target_for_tab_index(self, idx) -> str | None:
        for target, pane in self.panes.items():
            if str(pane) == self.notebook.tabs()[idx]:
                return target
        return None

    def _flag_tab_activity(self, target: str | None, mention: bool = False):
        pane = self.panes.get(target)
        if pane is None:
            return
        tab_id = str(pane)
        if self.notebook.select() == tab_id:
            return  # already looking at it
        current_text = self.notebook.tab(tab_id, "text")
        base = current_text[2:] if current_text.startswith(("• ", "@ ")) else current_text
        if mention:
            self.notebook.tab(tab_id, text=f"@ {base}")          # "@" outranks the plain dot
        elif not current_text.startswith(("• ", "@ ")):
            self.notebook.tab(tab_id, text=f"• {base}")

    # -----------------------------------------------------
    # NETWORKING
    # -----------------------------------------------------
    def send_json(self, obj: dict):
        if self.sock is None:
            return
        try:
            send_json(self.sock, obj)
        except Exception:
            self.panes[None].display_system("Failed to send -- connection lost.")

    def _receive_loop(self):
        reader = self._reader          # the same reader the login used: it may already hold the first chat messages
        while True:
            try:
                msg = reader.read_message()
                if msg is None:
                    self.incoming_queue.put({"type": "__disconnected__"})
                    break
                self.incoming_queue.put(msg)
            except Exception:
                self.incoming_queue.put({"type": "__disconnected__"})
                break

    def _poll_incoming(self):
        try:
            while True:
                msg = self.incoming_queue.get_nowait()
                self._handle_incoming(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_incoming)

    # -----------------------------------------------------
    # ROUTING SERVER MESSAGES TO THE RIGHT PANE
    # -----------------------------------------------------
    def _pane_for(self, sender: str, target: str | None) -> MessagePane:
        """Room messages (target None) go to the room pane. A DM's pane is
        keyed by 'the other person', whichever side of the conversation we're on."""
        if target is None:
            return self.panes[None]
        other = target if sender == self.username else sender
        self.open_dm_tab(other, focus=False)
        return self.panes[other]

    def _handle_incoming(self, msg: dict):
        kind = msg.get("type")

        if kind == "__disconnected__":
            self.panes[None].display_system("Disconnected from server.")
            return

        if kind == proto.PRESENCE:
            self.online_users = msg.get("users", [])
            self.statuses = msg.get("statuses") or {}
            self.everyone = msg.get("everyone") or []
            self.last_seen = msg.get("last_seen") or {}
            mine = self.statuses.get(self.username)
            if mine and mine.get("status") != "idle":        # "idle" is temporary -- keep the real one
                self.my_status = mine.get("status") or proto.DEFAULT_STATUS
                self.my_status_text = mine.get("text") or ""
            self._refresh_status_button()
            self._refresh_presence_list()
            return

        if kind == proto.UNREAD:
            # Messages people sent while we were offline. They are saved on the server; open each chat (which
            # loads the history), mark its tab, and say who wrote.
            counts = {k: int(v) for k, v in (msg.get("counts") or {}).items() if v}
            self.unread = counts
            for sender in sorted(counts, key=str.lower):
                self.open_dm_tab(sender, focus=False)
                self._flag_tab_activity(sender)
            if counts:
                total = sum(counts.values())
                who = ", ".join(f"{n} ({c})" for n, c in sorted(counts.items(), key=lambda kv: kv[0].lower()))
                self.panes[None].display_system(
                    f"📬 You have {total} new message{'s' if total != 1 else ''} from {who}. "
                    f"Their chats are open in the tabs above.")
                if self.my_status != "dnd":
                    self.bell()
            self._refresh_presence_list()
            return

        if kind == proto.PROFILE:
            for callback in self._profile_waiters.pop(msg.get("username"), []):
                try:
                    callback(msg)
                except tk.TclError:
                    pass                                      # that card/dialog was closed meanwhile
            return

        if kind == proto.USER_DELETED:
            gone = msg.get("username")
            for pane in self.panes.values():
                pane.purge_user(gone)
            self.user_colors.pop(gone, None)
            self.user_avatars.pop(gone, None)
            if self.feed_window is not None and self.feed_window.winfo_exists():
                self.feed_window.on_user_deleted(gone)
            return

        if kind == proto.AVATARS:
            self.user_avatars = msg.get("avatars") or {}
            self._avatars_changed(None)
            return

        if kind == proto.AVATAR:
            who, data = msg.get("username"), msg.get("data")
            if data:
                self.user_avatars[who] = data
            else:
                self.user_avatars.pop(who, None)
            self._avatars_changed(who)
            return

        if kind == proto.COLORS:
            self.user_colors = msg.get("colors") or {}
            for pane in self.panes.values():
                pane.refresh_name_colors()
            return

        if kind == proto.SYSTEM:
            self.panes[None].display_system(msg.get("text", ""))
            return

        if kind == proto.ERROR:
            if msg.get("fatal"):                         # the server is hanging up (wrong password, already logged in...)
                messagebox.showerror("Can't log in", msg.get("text", "The server closed the connection."))
                self.return_to_login(self.username)
                return
            messagebox.showwarning("Server says", msg.get("text", "Something went wrong."),
                                   parent=self.wallet_window or self)
            return

        if kind == "__languages__":
            self.installed_languages = msg.get("codes", [])
            self._warm_up_translator()          # load the models now, so the first message isn't the slow one
            return

        if kind == "__translated__":
            self._on_translated(msg)
            return

        if kind in FEED_KINDS:
            self._on_feed_message(kind, msg)
            return

        if kind in (proto.AI_STATE, proto.AI_REPLY):
            win = self.ai_window
            if win is not None and win.winfo_exists():
                win.set_state(msg) if kind == proto.AI_STATE else win.on_reply(msg)
            return

        if kind == proto.PAY_WALLET_STATE:
            self.wallet_demo = bool(msg.get("demo", self.wallet_demo))
            if self.wallet_window is not None:
                self.wallet_window.set_state(msg)
            return

        if kind == proto.PAY_UPDATE:
            self._on_pay_update(msg)
            return

        if kind == proto.PAY_LINK:
            self._on_pay_link(msg)
            return

        if kind == proto.GAME_EVENT:                     # a dice roll / coin flip
            sender, target = msg.get("sender"), msg.get("target")
            pane = self.panes[None] if target is None else self._pane_for(sender, target)
            pane.display_roll(msg.get("text", ""), msg.get("roll"))     # animated (older servers send no `roll`: plain text)
            return

        if kind == proto.GAME_INVITE:
            sender = msg.get("sender", "?")
            self._pane_for(sender, sender).display_system(
                f"🎮 {sender} invited you to play {games.GAME_NAMES.get(msg.get('game'), 'a game')}.")
            self._flag_tab_activity(sender)
            GameInviteDialog(self, msg)
            if self.my_status != "dnd":
                self.bell()
            return

        if kind == proto.GAME_STATE:
            self._on_game_state(msg)
            return

        if kind == proto.HISTORY:
            target = msg.get("target")
            pane = self.panes[None] if target is None else self._get_or_make_pane(target)
            shown = []
            for row in msg.get("messages", []):
                record = pane._record_from_text_msg(row)
                pane.upsert_message(record)
                shown.append(record)
            for record in reversed(shown):      # translate the NEWEST first: those are the ones you're reading
                self.request_translation(pane, record)
            pane.auto_fetch_images()
            pane.send_pending_reads()
            return

        if kind == proto.TEXT:
            target = msg.get("target")
            pane = self._pane_for(msg["sender"], target)
            pane.on_text(msg, is_new=True)
            if target is not None:
                if msg["sender"] != self.username:
                    if self.is_viewing(msg["sender"]):
                        self._clear_unread(msg["sender"])
                    else:
                        self.unread[msg["sender"]] = self.unread.get(msg["sender"], 0) + 1
                        self._refresh_presence_list()
                elif target not in self.online_users and target not in self._offline_hint_shown:
                    self._offline_hint_shown.add(target)       # say it once per person, not on every message
                    pane.display_system(f"{target} is offline right now. They'll get your message the next "
                                        f"time they log in.")
            record = pane.records.get(msg.get("id"))
            if record:
                self.request_translation(pane, record)
            mentioned = bool(record and msg["sender"] != self.username and not record.get("deleted")
                             and mentions_user(record["text"], self.username))
            if mentioned and not self.is_viewing(pane.target) and self.my_status != "dnd":
                self.bell()                                       # someone @'d you while you weren't looking
            self._flag_tab_activity(None if target is None else
                                     (target if msg["sender"] == self.username else msg["sender"]),
                                    mention=mentioned)
            return

        if kind == proto.EDIT:
            for pane in self.panes.values():
                if msg["message_id"] in pane.records:
                    pane.on_edit(msg["message_id"], msg["text"])
            return

        if kind == proto.DELETE:
            for pane in self.panes.values():
                if msg["message_id"] in pane.records:
                    pane.on_delete(msg["message_id"])
            return

        if kind == proto.REACTION:
            for pane in self.panes.values():
                if msg["message_id"] in pane.records:
                    pane.on_reaction(msg["message_id"], msg["emoji"], msg["action"], msg["username"])
            return

        if kind == proto.READ:
            for pane in self.panes.values():
                if msg["message_id"] in pane.records:
                    pane.on_read(msg["message_id"])
            return

        if kind == proto.TYPING:
            target = msg.get("target")
            pane = self._pane_for(msg["sender"], target)
            pane.show_typing(msg["sender"], msg["state"])
            return

        if kind == proto.FILE_START:
            target = msg.get("target")
            pane = self._pane_for(msg["sender"], target)
            pane.on_file_start(msg)
            self._flag_tab_activity(None if target is None else
                                     (target if msg["sender"] == self.username else msg["sender"]))
            return

        if kind == proto.FILE_CHUNK:
            for pane in self.panes.values():
                if msg["file_id"] in pane.file_buffers:
                    pane.on_file_chunk(msg)
                    break
            return

        if kind == proto.FILE_END:
            for pane in self.panes.values():
                if msg["file_id"] in pane.file_buffers:
                    pane.on_file_end(msg)
                    break
            return

    # -----------------------------------------------------
    # LANGUAGE -- messages from other people are translated, on THIS computer and offline, into the
    # language you picked, and shown under the original. Nothing is sent anywhere to do it.
    # -----------------------------------------------------
    def _scan_languages(self):
        """Background: which language packs are installed? (Loading the library takes a moment.)"""
        codes = []
        if translator is not None:
            try:
                codes = translator.available_language_codes()
            except Exception:
                codes = []
        self.incoming_queue.put({"type": "__languages__", "codes": codes})

    def open_language_menu(self):
        menu = tk.Menu(self, tearoff=0)
        choice = self._lang_choice = tk.StringVar(master=self, value=self.language or "off")   # keep a reference
        menu.add_radiobutton(label="Off — show messages as they were sent", variable=choice, value="off",
                             command=lambda: self.set_language(""))
        menu.add_separator()
        if translator is None:
            menu.add_command(label="translator.py is missing from this folder", state="disabled")
        else:
            # every language Google can translate into, plus any offline pack that's installed
            codes = sorted(set(LANGUAGE_NAMES) | set(self.installed_languages), key=language_name)
            menu.add_command(label="Show other people's messages in:", state="disabled")
            for i, code in enumerate(codes):
                menu.add_radiobutton(label=f"{language_name(code)}  ({code})", variable=choice, value=code,
                                     command=lambda c=code: self.set_language(c),
                                     columnbreak=(i > 0 and i % 18 == 0))      # long list: wrap into columns
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def set_language(self, code: str):
        self.language = code
        save_language(self.username, code)
        if code in KEYBOARD_LAYOUTS:                         # the accent keys follow the language you picked
            self.kb_language = code
            for pane in self.panes.values():
                if pane.keyboard is not None:
                    try:
                        pane.keyboard.set_language(code)
                    except tk.TclError:
                        pass
        self._warm_up_translator()
        for pane in self.panes.values():                    # redo everything already on screen
            for record in pane.records.values():
                record.pop("tr_key", None)
                record.pop("tr_done", None)
                record.pop("tr_placeholder", None)
                had = record.pop("translation", None)
                if had:
                    pane.set_translation(record["id"], None)
            for record in sorted(pane.records.values(), key=lambda r: r["id"], reverse=True):   # newest first
                self.request_translation(pane, record)
        self.panes[None].display_system(
            f"🌐 Messages from others will be shown in {language_name(code)}." if code
            else "🌐 Translation is off.")

    def _warm_up_translator(self):
        """Load the translation models in the background. The FIRST translation is the slow one (it has to
        load the language packs), so do that before anyone has sent a message."""
        if not self.language or translator is None:
            return
        if self._translator is None:
            self._translator = translator.MessageTranslator()
        self._translator.warm_up(self.language)

    def request_translation(self, pane, record: dict):
        """Ask (in the background) for a translation of one message from someone else."""
        if (not self.language or translator is None or record.get("msg_type", "text") != "text"
                or record.get("deleted") or record["sender"] == self.username or not record.get("text")):
            return
        key = (record["text"], self.language)
        if record.get("tr_key") == key:
            return                                          # already asked (or done) for exactly this
        record["tr_key"] = key
        record.pop("tr_done", None)
        if self._translator is None:
            self._translator = translator.MessageTranslator()
        target, msg_id, pane_target = self.language, record["id"], pane.target

        def done(result, error):                            # runs on the worker thread: just hand it over
            self.incoming_queue.put({"type": "__translated__", "target": pane_target, "id": msg_id,
                                     "key": key, "result": result, "error": error})
        self._translator.translate_async(record["text"], target, done)
        # Quick answers need no fuss. If it's still working after a moment, say so, so it doesn't look stuck.
        self.after(TRANSLATING_NOTICE_MS, lambda: self._show_translating(pane, record, key))

    def _show_translating(self, pane, record: dict, key):
        try:
            if record.get("tr_key") == key and record.get("tr_done") != key and not record.get("translation"):
                record["tr_placeholder"] = True
                pane.set_translation(record["id"], "Translating…")      # shown as "🌐 Translating…"
        except tk.TclError:                                 # the tab was closed in the meantime
            pass

    def _on_translated(self, msg: dict):
        pane = self.panes.get(msg.get("target"))
        record = pane.records.get(msg["id"]) if pane else None
        if record is None or record.get("tr_key") != msg.get("key"):
            return                                          # the message changed or was removed meanwhile
        record["tr_done"] = msg.get("key")
        had_placeholder = record.pop("tr_placeholder", None)
        if msg.get("error") is not None:
            if had_placeholder:
                pane.set_translation(record["id"], None)    # take the "Translating…" line away again
            record.pop("tr_key", None)                      # allow a later retry
            now = time.time()
            if now - self._last_translate_notice > 60:      # say why ONCE a minute, not on every message
                self._last_translate_notice = now
                self.panes[None].display_system("🌐 " + translator.friendly_error(msg["error"]))
            return
        result = msg.get("result")
        if result:
            pane.set_translation(record["id"], result["text"])
        elif had_placeholder:                               # nothing to show (already in your language)
            pane.set_translation(record["id"], None)

    # -----------------------------------------------------
    # PAYMENTS (the server and Stripe decide everything; this only shows it)
    # -----------------------------------------------------
    # -----------------------------------------------------
    # THE FEED (posts, likes, comments -- see feed_window.py)
    # -----------------------------------------------------
    def open_feed(self):
        if self.feed_window is not None and self.feed_window.winfo_exists():
            self.feed_window.lift()
        else:
            self.feed_window = FeedWindow(self)
        self.feed_unseen = 0
        self.header.set_label("feed", "Feed")

    def _on_feed_message(self, kind: str, msg: dict):
        win = self.feed_window if (self.feed_window is not None and self.feed_window.winfo_exists()) else None
        if win is not None:
            {proto.FEED: win.on_feed, proto.POST_NEW: lambda m: win.on_new_post(m["post"]),
             proto.POST_IMAGE: win.on_image, proto.POST_LIKES: win.on_likes, proto.COMMENT_NEW: win.on_comment,
             proto.COMMENT_GONE: win.on_comment_gone, proto.POST_GONE: win.on_post_gone}[kind](msg)
            return
        # The Feed isn't open: just let the person know something happened (a count on the Feed button, and a note
        # in the Room for things that happen to THEIR posts).
        me, news = self.username, None
        if kind == proto.POST_NEW and (msg.get("post") or {}).get("author") != me:
            news = ""
        elif kind == proto.POST_LIKES and msg.get("author") == me and msg.get("actor") != me and msg.get("liked"):
            news = f"❤  {msg.get('actor')} liked your post."
        elif kind == proto.COMMENT_NEW and msg.get("post_author") == me and (msg.get("comment") or {}).get("author") != me:
            news = f"💬  {msg['comment']['author']} commented on your post."
        if news is None:
            return
        if news:
            self.panes[None].display_system(news + "  Open Feed to see it.")
        self.feed_unseen += 1
        self.header.set_label("feed", f"Feed ({self.feed_unseen})")

    def open_ai_friend(self):
        if self.ai_window is not None and self.ai_window.winfo_exists():
            self.ai_window.lift()
        else:
            self.ai_window = AIFriendWindow(self)

    def open_wallet(self, person: str | None = None):
        if self.wallet_window is not None and self.wallet_window.winfo_exists():
            self.wallet_window.lift()
        else:
            self.wallet_window = WalletWindow(self)
        if person:
            self.wallet_window.prefill(person)

    def _on_pay_update(self, msg: dict):
        req, event = msg.get("request") or {}, msg.get("event")
        if not req.get("id"):
            return
        self.wallet_demo = bool(msg.get("demo", self.wallet_demo))
        previous = self.pay_requests.get(req["id"], {}).get("status")
        self.pay_requests[req["id"]] = req
        if self.wallet_window is not None and self.wallet_window.winfo_exists():
            self.wallet_window.apply_update(req)

        me = self.username
        other = req["payer"] if req["requester"] == me else req["requester"]
        amount = format_cents(req["amount_cents"], req["currency"]) + note_suffix(req)
        status = req["status"]

        # a request addressed to me that's still waiting: pop up the Pay / Decline box (once)
        if status == "pending" and req["payer"] == me and event in ("new", "open"):
            if req["id"] not in self.pay_prompts:
                PaymentPrompt(self, req)
                if event == "new" and self.my_status != "dnd":
                    self.bell()
        elif status != "pending":
            prompt = self.pay_prompts.get(req["id"])
            if prompt is not None:
                prompt.close()

        if event == "open" or other == me:
            return
        line = None
        if event == "new":
            line = (f"💸 You asked {other} for {amount}." if req["requester"] == me
                    else f"💸 {other} asked you for {amount}. Open 💸 Wallet to answer.")
        elif status == previous:
            return
        elif status == "paid":
            line = f"✅ {req['payer']} paid {req['requester']} {format_cents(req['amount_cents'], req['currency'])}."
        elif status == "declined":
            line = f"{req['payer']} declined the {format_cents(req['amount_cents'], req['currency'])} request."
        elif status == "cancelled":
            line = f"{req['requester']} cancelled the {format_cents(req['amount_cents'], req['currency'])} request."
        elif status == "review":
            line = "⚠ A payment needs a manual check. The server owner has been told in the server log."
        if line:
            self._pane_for(me, other).display_system(line)
            self._flag_tab_activity(other)

    def _on_pay_link(self, msg: dict):
        url = msg.get("url")
        if not is_stripe_url(url):
            messagebox.showerror("Payment", "The server sent a link that isn't a Stripe address, so it was "
                                            "not opened.", parent=self.wallet_window or self)
            return
        what = {"onboard": "Stripe's sign-up page", "dashboard": "your Stripe dashboard",
                "checkout": "Stripe's secure payment page"}.get(msg.get("purpose"), "Stripe")
        webbrowser.open(url)
        if self.wallet_window is not None and self.wallet_window.winfo_exists():
            self.wallet_window.detail_label.config(text=f"Opened {what} in your browser. This window updates "
                                                        f"by itself when you're done.")

    def _on_game_state(self, state: dict):
        gid, status = state.get("game_id"), state.get("status")
        invite = self.game_invites.get(gid)
        if invite is not None and status != "pending":       # answered, cancelled or expired
            invite.close()
        window = self.game_windows.get(gid)
        if gid in self.closed_games and window is None:
            if status == "over":
                self.closed_games.discard(gid)
            return
        if window is not None:
            window.update_state(state)
        elif status in ("pending", "active") and self.username in state.get("players", []):
            self.game_windows[gid] = GameWindow(self, state)
        if status == "over":
            players = state.get("players", [])
            other = next((p for p in players if p != self.username), None)
            if other and state.get("result"):
                self._pane_for(self.username, other).display_system("🎮 " + state["result"])
            self.closed_games.discard(gid)

    def _get_or_make_pane(self, target: str) -> MessagePane:
        self.open_dm_tab(target, focus=False)
        return self.panes[target]

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------
    def on_close(self):
        self._close_socket()
        self.master.destroy()
