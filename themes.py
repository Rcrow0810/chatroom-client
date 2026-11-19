# themes.py
# ---------------------------------------------------------
# Look-and-feel for the chat window.
#
#   * THEMES        - ready-made color sets you can pick from.
#   * FONT_CHOICES  - fonts offered in Settings > Theme.
#   * load_prefs / save_prefs
#                   - your choices, saved per username in
#                     theme_prefs.json next to the program.
#                     Themes are LOCAL: they change how the chat
#                     looks on YOUR screen only, nobody else's.
#   * build_theme   - preset + your tweaks (accent color, chat
#                     background, font, size, spacing) -> the one
#                     dict of colors the GUI actually uses.
#   * readable_on   - nudges a color lighter/darker until it can
#                     be read on a given background (so a name
#                     color someone picked for a light theme
#                     doesn't vanish on a dark one).
# ---------------------------------------------------------

import json
import os

PREFS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme_prefs.json")

# Every theme defines the same keys:
#   window    - background behind everything / input strip
#   header    - top bar
#   header_btn- buttons in the top bar
#   sidebar   - the ONLINE list panel
#   sidebar_fg- text in the sidebar
#   chat_bg   - message log background
#   text      - normal message text
#   muted     - timestamps, typing indicator, system lines
#   accent    - Send button, links to files, selection highlight
#   input_bg / input_fg - the message box
#   mention   - highlight behind an @name
#   mention_me- highlight behind an @you / @everyone
#   link      - clickable URLs
THEMES = {
    "Pop": dict(                      # the default: lavender, violet + hot-pink
        window="#f3f1ff", header="#4a3df0", header2="#ff4f9a", header_btn="#7a62ff", sidebar="#ffffff",
        sidebar_fg="#1e1b3a", chat_bg="#f7f6ff", text="#1e1b3a", muted="#7a7897",
        accent="#6c4dff", input_bg="#ffffff", input_fg="#1e1b3a",
        mention="#ffe9a8", mention_me="#ffd166", link="#4f46e5",
    ),
    "Pop Dark": dict(                 # the same, after dark
        window="#16132b", header="#3b2bd9", header2="#c2338a", header_btn="#5a48ff", sidebar="#1d1938",
        sidebar_fg="#edebff", chat_bg="#1a1733", text="#edebff", muted="#9a96c4",
        accent="#8b6cff", input_bg="#2a2550", input_fg="#edebff",
        mention="#4a3f1e", mention_me="#6b5a14", link="#a99cff",
    ),
    "Light": dict(
        window="#f0f0f0", header="#2c2f33", header_btn="#40444b", sidebar="#23272a",
        sidebar_fg="#dcddde", chat_bg="#f5f6f8", text="#1f2328", muted="#888888",
        accent="#5865f2", input_bg="#ffffff", input_fg="#1f2328",
        mention="#fff3b0", mention_me="#ffd24d", link="#0b5ed7",
    ),
    "Dark": dict(
        window="#2b2d31", header="#1e1f22", header_btn="#383a40", sidebar="#232428",
        sidebar_fg="#dbdee1", chat_bg="#313338", text="#e3e5e8", muted="#949ba4",
        accent="#5865f2", input_bg="#383a40", input_fg="#e3e5e8",
        mention="#4a4524", mention_me="#6b5a14", link="#7aa7ff",
    ),
    "Midnight": dict(
        window="#0b1020", header="#060913", header_btn="#1a2240", sidebar="#080c18",
        sidebar_fg="#c5cdf0", chat_bg="#0f1530", text="#dfe5ff", muted="#7e89b8",
        accent="#6c8cff", input_bg="#18204a", input_fg="#dfe5ff",
        mention="#2b3566", mention_me="#4a3f8f", link="#8fb0ff",
    ),
    "Forest": dict(
        window="#e6efe6", header="#1f3a2b", header_btn="#2f5842", sidebar="#17301f",
        sidebar_fg="#d8ecd8", chat_bg="#f1f7f0", text="#1d2b21", muted="#6f8a76",
        accent="#2e8b57", input_bg="#ffffff", input_fg="#1d2b21",
        mention="#e3f2b5", mention_me="#c8e66a", link="#1b6b3f",
    ),
    "Sunset": dict(
        window="#fbeee6", header="#5a2a3c", header_btn="#7a3b52", sidebar="#44202e",
        sidebar_fg="#ffe3d3", chat_bg="#fff6f0", text="#3b2328", muted="#a2786f",
        accent="#e8643c", input_bg="#ffffff", input_fg="#3b2328",
        mention="#ffe2a8", mention_me="#ffc266", link="#c2410c",
    ),
    "Bubblegum": dict(
        window="#fde7f3", header="#a23b72", header_btn="#c2528d", sidebar="#7d2a58",
        sidebar_fg="#ffe3f1", chat_bg="#fff4fa", text="#4a1f3a", muted="#b07a9a",
        accent="#e0489b", input_bg="#ffffff", input_fg="#4a1f3a",
        mention="#ffe0f0", mention_me="#ffb3d9", link="#b0287a",
    ),
    "Ocean": dict(
        window="#e3f1f7", header="#0d3b52", header_btn="#175a7a", sidebar="#0a2c3f",
        sidebar_fg="#d4ecf7", chat_bg="#effaff", text="#10303f", muted="#6a93a6",
        accent="#0891b2", input_bg="#ffffff", input_fg="#10303f",
        mention="#d3f1fb", mention_me="#8bdcf2", link="#0369a1",
    ),
    "High contrast": dict(
        window="#000000", header="#000000", header_btn="#2a2a2a", sidebar="#000000",
        sidebar_fg="#ffffff", chat_bg="#000000", text="#ffffff", muted="#c0c0c0",
        accent="#ffd400", input_bg="#111111", input_fg="#ffffff",
        mention="#3a3a00", mention_me="#7a7a00", link="#66ccff",
    ),
}
DEFAULT_THEME = "Pop"

FONT_CHOICES = ["Segoe UI", "Arial", "Verdana", "Georgia", "Comic Sans MS", "Courier New", "Trebuchet MS"]
DEFAULT_FONT = "Segoe UI"
FONT_SIZES = [9, 10, 11, 12, 14]
DEFAULT_FONT_SIZE = 10

# message spacing: name -> blank lines extra / pixels between messages
DENSITIES = {"Cozy": 10, "Compact": 2}
DEFAULT_DENSITY = "Cozy"

DEFAULT_PREFS = {
    "theme": DEFAULT_THEME,
    "accent": None,        # "#rrggbb" or None = use the theme's own accent
    "chat_bg": None,       # "#rrggbb" or None = use the theme's own
    "font": DEFAULT_FONT,
    "font_size": DEFAULT_FONT_SIZE,
    "density": DEFAULT_DENSITY,
}


# -------------------------------------------------------------
# color math
# -------------------------------------------------------------
def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(v)))) for v in (r, g, b)))


def _lin(c: int) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = _rgb(hex_color)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def text_color_on(bg_hex: str) -> str:
    """Black or white, whichever reads better on this background."""
    return "#000000" if contrast_ratio(bg_hex, "#000000") >= contrast_ratio(bg_hex, "#ffffff") else "#ffffff"


def mix(a: str, b: str, amount: float) -> str:
    """Blend a toward b by `amount` (0 = a, 1 = b)."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return _hex(ra + (rb - ra) * amount, ga + (gb - ga) * amount, ba + (bb - ba) * amount)


def readable_on(color: str, bg: str, minimum: float = 3.0) -> str:
    """Return `color`, pushed lighter or darker only as far as needed to be
    readable on `bg`. Colors that are already fine come back unchanged."""
    if contrast_ratio(color, bg) >= minimum:
        return color
    toward = "#ffffff" if luminance(bg) < 0.5 else "#000000"
    for step in range(1, 21):
        candidate = mix(color, toward, step * 0.05)
        if contrast_ratio(candidate, bg) >= minimum:
            return candidate
    return toward


# -------------------------------------------------------------
# saving / loading your choices
# -------------------------------------------------------------
def _read_all() -> dict:
    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _valid_hex(value) -> bool:
    return isinstance(value, str) and len(value) == 7 and value[0] == "#" and all(
        c in "0123456789abcdefABCDEF" for c in value[1:])


def clean_prefs(raw: dict | None) -> dict:
    """Throw away anything unexpected so a hand-edited or old file can't break the GUI."""
    prefs = dict(DEFAULT_PREFS)
    raw = raw if isinstance(raw, dict) else {}
    if raw.get("theme") in THEMES:
        prefs["theme"] = raw["theme"]
    for key in ("accent", "chat_bg"):
        if _valid_hex(raw.get(key)):
            prefs[key] = raw[key].lower()
    if raw.get("font") in FONT_CHOICES:
        prefs["font"] = raw["font"]
    if raw.get("font_size") in FONT_SIZES:
        prefs["font_size"] = raw["font_size"]
    if raw.get("density") in DENSITIES:
        prefs["density"] = raw["density"]
    return prefs


def load_prefs(username: str) -> dict:
    return clean_prefs(_read_all().get(username.lower()))


def save_prefs(username: str, prefs: dict) -> None:
    data = _read_all()
    data[username.lower()] = clean_prefs(prefs)
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass   # can't write the file -> the theme just won't be remembered next time


# -------------------------------------------------------------
# preset + tweaks -> the dict the GUI uses
# -------------------------------------------------------------
def build_theme(prefs: dict) -> dict:
    prefs = clean_prefs(prefs)
    t = dict(THEMES[prefs["theme"]])
    if prefs["accent"]:
        t["accent"] = prefs["accent"]
    if prefs["chat_bg"]:
        t["chat_bg"] = prefs["chat_bg"]
        # keep text readable if the person picked a background that clashes with the preset
        if contrast_ratio(t["text"], t["chat_bg"]) < 4.5:
            t["text"] = text_color_on(t["chat_bg"])
        t["muted"] = readable_on(t["muted"], t["chat_bg"], 3.0)
    t["accent_text"] = text_color_on(t["accent"])
    t["link_file"] = readable_on(t["accent"], t["chat_bg"], 3.0)
    t["link"] = readable_on(t["link"], t["chat_bg"], 3.5)
    t["is_dark"] = luminance(t["chat_bg"]) < 0.4
    t["font"] = prefs["font"]
    t["font_size"] = prefs["font_size"]
    t["gap"] = DENSITIES[prefs["density"]]
    t["name"] = prefs["theme"]
    # --- colors for the modern look; older presets don't define them, so they are worked out here ---
    t.setdefault("header2", mix(t["header"], t["accent"], 0.55))       # far end of the header gradient
    t["accent2"] = mix(t["accent"], "#ff4f9a", 0.55)                   # the pink-ish partner of the accent
    if t["is_dark"]:
        t["bubble_other"] = mix(t["chat_bg"], "#ffffff", 0.07)
        t["bubble_me"] = mix(t["chat_bg"], t["accent"], 0.32)
    else:
        t["bubble_other"] = "#ffffff" if luminance(t["chat_bg"]) > 0.8 else mix(t["chat_bg"], "#ffffff", 0.55)
        t["bubble_me"] = mix("#ffffff", t["accent"], 0.15)
    t["hover"] = mix(t["sidebar"], t["accent"], 0.14)                  # row under the mouse in the sidebar
    t["selected"] = mix(t["sidebar"], t["accent"], 0.24)
    t["tab_idle"] = mix(t["window"], t["accent"], 0.12 if not t["is_dark"] else 0.25)
    return t
