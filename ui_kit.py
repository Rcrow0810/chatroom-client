# ui_kit.py  --  CLIENT SIDE
# ---------------------------------------------------------
# The "modern look" building blocks. Plain Tk draws square, flat, 1990s-looking widgets, so instead of
# fighting it, everything here is drawn as smooth (anti-aliased) pictures with Pillow and put on a Canvas:
#
#   * rounded cards with a soft shadow           * pill buttons with a gradient + hover/press
#   * rounded text boxes with a glowing focus    * a sliding pill switch (Log in / Sign up)
#   * gradient window backgrounds                 * a drawn logo
#
# The picture-makers (gradient_bg, card_image, ...) only need Pillow, so they can be tested without a
# window. The widgets (ModernEntry, ModernButton, ...) need Tk.
# ---------------------------------------------------------

import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageTk

# ── palette ─────────────────────────────────────────────────────────────────────────
VIOLET = "#6C4DFF"
PINK = "#FF4F9A"
INDIGO = "#4338FF"
PURPLE = "#A24BFF"
INK = "#1E1B3A"            # main text
MUTED = "#7A7897"          # labels, hints
FIELD = "#F3F1FF"          # text box fill
FIELD_EDGE = "#E2DDFB"
WHITE = "#FFFFFF"
DANGER = "#E5484D"
DANGER_BG = "#FFF0F1"
OK = "#14A44D"
TRACK = "#EEEBFF"          # the switch's groove

SS = 4                      # draw 4x bigger, shrink = smooth edges


# ── tiny colour helpers ─────────────────────────────────────────────────────────────
def rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def lerp(a: str, b: str, t: float) -> tuple[int, int, int]:
    ra, rb = rgb(a), rgb(b)
    return tuple(int(round(ra[i] + (rb[i] - ra[i]) * t)) for i in range(3))


def mix_hex(a: str, b: str, t: float) -> str:
    return "#%02x%02x%02x" % lerp(a, b, t)


# ── picture makers (Pillow only) ────────────────────────────────────────────────────
def _hgradient(w: int, h: int, stops: list[str]) -> Image.Image:
    """Left -> right gradient through any number of colours."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    n = len(stops) - 1
    for x in range(w):
        t = x / max(1, w - 1) * n
        i = min(int(t), n - 1)
        d.line([(x, 0), (x, h)], fill=lerp(stops[i], stops[i + 1], t - i))
    return img


def _vgradient(w: int, h: int, stops: list[str]) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    n = len(stops) - 1
    for y in range(h):
        t = y / max(1, h - 1) * n
        i = min(int(t), n - 1)
        d.line([(0, y), (w, y)], fill=lerp(stops[i], stops[i + 1], t - i))
    return img


def _rounded_mask(w: int, h: int, r: int) -> Image.Image:
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=r * SS, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def rounded_image(w: int, h: int, r: int, fill, border: str | None = None, border_w: int = 0) -> Image.Image:
    """A smooth rounded rectangle (RGBA). `fill` is a colour, or a list of colours for a left->right gradient."""
    r = min(r, h // 2, w // 2)
    if isinstance(fill, (list, tuple)):
        body = _hgradient(w, h, list(fill)).convert("RGBA")
    else:
        body = Image.new("RGBA", (w, h), rgb(fill) + (255,))
    if border and border_w:
        outer = Image.new("RGBA", (w, h), rgb(border) + (255,))
        inner_mask = Image.new("L", (w * SS, h * SS), 0)
        b = border_w * SS
        ImageDraw.Draw(inner_mask).rounded_rectangle(
            (b, b, w * SS - 1 - b, h * SS - 1 - b), radius=max(0, (r - border_w)) * SS, fill=255)
        inner_mask = inner_mask.resize((w, h), Image.LANCZOS)
        outer.paste(body, (0, 0), inner_mask)
        body = outer
    body.putalpha(_rounded_mask(w, h, r))
    return body


SHADOW_PAD = 34


def card_image(w: int, h: int, r: int = 30, fill: str = WHITE, shadow: str = "#2a1470", alpha: int = 90) -> Image.Image:
    """A white rounded card with a soft shadow. The picture is bigger than the card by SHADOW_PAD on every
    side, so place it at (card_x - SHADOW_PAD, card_y - SHADOW_PAD)."""
    pad = SHADOW_PAD
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((pad, pad + 12, pad + w, pad + h + 12), radius=r,
                                           fill=rgb(shadow) + (alpha,))
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(rounded_image(w, h, r, fill), (pad, pad))
    return canvas


def gradient_bg(w: int, h: int) -> Image.Image:
    """Indigo -> purple -> pink, with a few soft glowing blobs so it isn't flat."""
    img = _vgradient(w, h, [INDIGO, PURPLE, PINK]).convert("RGBA")
    for cx, cy, rad, color, a in ((w * 0.92, h * 0.06, w * 0.55, "#7DE3FF", 70),
                                  (w * 0.02, h * 0.55, w * 0.50, "#FFD36E", 55),
                                  (w * 0.85, h * 0.98, w * 0.60, "#FF7AC8", 80)):
        blob = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(blob).ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=rgb(color) + (a,))
        img.alpha_composite(blob.filter(ImageFilter.GaussianBlur(rad * 0.35)))
    return img.convert("RGB")


def logo_image(size: int = 76, pad: int = 18) -> Image.Image:
    """A white rounded tile with a gradient chat bubble (three dots) on it."""
    S = size * SS
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.30), fill=(255, 255, 255, 255))

    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    bx0, by0, bx1, by1 = S * 0.20, S * 0.24, S * 0.80, S * 0.64
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=S * 0.16, fill=255)
    d.polygon([(S * 0.30, by1 - S * 0.04), (S * 0.30, S * 0.80), (S * 0.47, by1 - S * 0.04)], fill=255)
    grad = _hgradient(S, S, [VIOLET, PINK]).convert("RGBA")
    grad.putalpha(mask)
    tile.alpha_composite(grad)

    dots = ImageDraw.Draw(tile)
    cy = (by0 + by1) / 2
    for i in range(3):
        cx = S * (0.35 + 0.15 * i)
        dots.ellipse((cx - S * 0.034, cy - S * 0.034, cx + S * 0.034, cy + S * 0.034), fill=(255, 255, 255, 255))
    tile = tile.resize((size, size), Image.LANCZOS)

    out = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    if pad >= 12:                                   # only draw the soft shadow if there is room for it
        glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((pad, pad + 6, pad + size, pad + size + 6), radius=int(size * 0.3),
                                               fill=(30, 10, 90, 110))
        out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8)))
    out.alpha_composite(tile, (pad, pad))
    return out


# ── fonts ───────────────────────────────────────────────────────────────────────────
_PREFERRED = ("Inter", "Poppins", "Nunito", "Segoe UI Variable", "Segoe UI", "SF Pro Display", "Ubuntu",
              "Cantarell", "Helvetica Neue", "DejaVu Sans")
_family = None


def family() -> str:
    """The nicest font this computer has (needs a Tk window to exist)."""
    global _family
    if _family is None:
        have = {f.lower(): f for f in tkfont.families()}
        for name in _PREFERRED:
            if name.lower() in have:
                _family = have[name.lower()]
                break
        else:
            _family = tkfont.nametofont("TkDefaultFont").actual("family")
    return _family


def font(size: int, bold: bool = False) -> tuple:
    return (family(), size, "bold") if bold else (family(), size)


def photo(img: Image.Image) -> ImageTk.PhotoImage:
    return ImageTk.PhotoImage(img)


# ── widgets ─────────────────────────────────────────────────────────────────────────
class ModernEntry(tk.Frame):
    """A rounded text box with a violet glow when you click in it. Behaves like an Entry: get / insert /
    delete / focus_set / bind. `secret=True` hides the text and adds a Show/Hide switch."""

    def __init__(self, parent, width: int = 320, height: int = 48, secret: bool = False, bg: str = WHITE,
                 justify: str = "left", size: int = 11, readonly: bool = False):
        super().__init__(parent, bg=bg, width=width, height=height)
        self.pack_propagate(False)
        self._wd, self._ht = width, height
        self._secret = secret
        self._shown = False
        self._focused = False

        self._calm = photo(rounded_image(width, height, height // 3, FIELD, FIELD_EDGE, 1))
        self._glow = photo(rounded_image(width, height, height // 3, WHITE, VIOLET, 2))
        self.canvas = tk.Canvas(self, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0)
        self._bg_item = self.canvas.create_image(0, 0, image=self._calm, anchor="nw")

        toggle_w = 52 if secret else 0
        self.entry = tk.Entry(self.canvas, relief="flat", bd=0, highlightthickness=0, bg=FIELD, fg=INK,
                              insertbackground=VIOLET, selectbackground="#D9D2FF", selectforeground=INK,
                              font=font(size), justify=justify,
                              show="\u2022" if secret else "")
        if readonly:
            self.entry.config(state="readonly", readonlybackground=FIELD)
        self.canvas.create_window(16, height // 2, window=self.entry, anchor="w",
                                  width=width - 32 - toggle_w, height=height - 16)

        self._toggle = None
        if secret:
            self._toggle = self.canvas.create_text(width - 18, height // 2, text="Show", anchor="e",
                                                   fill=VIOLET, font=font(9, True))
            self.canvas.tag_bind(self._toggle, "<Button-1>", lambda e: self._toggle_show())
            self.canvas.tag_bind(self._toggle, "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind(self._toggle, "<Leave>", lambda e: self.canvas.config(cursor=""))

        self.entry.bind("<FocusIn>", lambda e: self._set_focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False), add="+")
        self.canvas.bind("<Button-1>", lambda e: self.entry.focus_set())

    def _set_focus(self, on: bool):
        self._focused = on
        self.canvas.itemconfigure(self._bg_item, image=self._glow if on else self._calm)
        if str(self.entry.cget("state")) != "readonly":
            self.entry.config(bg=WHITE if on else FIELD)

    def _toggle_show(self):
        self._shown = not self._shown
        self.entry.config(show="" if self._shown else "\u2022")
        self.canvas.itemconfigure(self._toggle, text="Hide" if self._shown else "Show")

    # Entry-like API
    def get(self):
        return self.entry.get()

    def insert(self, index, text):
        self.entry.insert(index, text)

    def delete(self, first, last=None):
        self.entry.delete(first, last)

    def focus_set(self):
        self.entry.focus_set()

    def bind(self, sequence=None, func=None, add=None):
        return self.entry.bind(sequence, func, add)


class ModernButton(tk.Canvas):
    """A pill button. style='primary' = violet->pink gradient, 'soft' = pale violet, 'ghost' = text only."""

    def __init__(self, parent, text: str, command, width: int = 320, height: int = 52, style: str = "primary",
                 bg: str = WHITE, size: int = 11):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._text, self._command, self._style = text, command, style
        self._wd, self._ht = width, height
        self._enabled = True
        self._inside = False
        r = height // 2
        if style == "primary":
            self._imgs = {
                "calm": photo(rounded_image(width, height, r, [VIOLET, PINK])),
                "hover": photo(rounded_image(width, height, r, [mix_hex(VIOLET, "#FFFFFF", .12), mix_hex(PINK, "#FFFFFF", .12)])),
                "press": photo(rounded_image(width, height, r, [mix_hex(VIOLET, "#000000", .12), mix_hex(PINK, "#000000", .12)])),
                "off": photo(rounded_image(width, height, r, ["#C9C2F5", "#F6B5D2"])),
            }
            self._fg = WHITE
        elif style == "soft":
            self._imgs = {
                "calm": photo(rounded_image(width, height, r, FIELD)),
                "hover": photo(rounded_image(width, height, r, "#E8E3FF")),
                "press": photo(rounded_image(width, height, r, "#DDD6FF")),
                "off": photo(rounded_image(width, height, r, FIELD)),
            }
            self._fg = VIOLET
        else:
            self._imgs = {}
            self._fg = MUTED
        self._image_item = self.create_image(0, 0, image=self._imgs["calm"], anchor="nw") if self._imgs else None
        self._label = self.create_text(width // 2, height // 2, text=text, fill=self._fg, font=font(size, True))
        self.bind("<Enter>", lambda e: self._state("hover"))
        self.bind("<Leave>", lambda e: self._state("calm"))
        self.bind("<ButtonPress-1>", lambda e: self._state("press"))
        self.bind("<ButtonRelease-1>", self._released)

    def _state(self, name: str):
        self._inside = name in ("hover", "press")
        if not self._enabled:
            name = "off"
        if self._image_item is not None:
            self.itemconfigure(self._image_item, image=self._imgs[name])
        elif self._enabled:
            self.itemconfigure(self._label, fill=VIOLET if name in ("hover", "press") else self._fg)

    def _released(self, event):
        inside = 0 <= event.x <= self._wd and 0 <= event.y <= self._ht
        self._state("hover" if inside else "calm")
        if inside and self._enabled:
            self._command()

    def set_text(self, text: str):
        self.itemconfigure(self._label, text=text)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self._state("calm")


class SegmentedSwitch(tk.Canvas):
    """Two-option pill switch with a coloured thumb (replaces the old square tabs)."""

    def __init__(self, parent, options: tuple[str, str], on_change, width: int = 320, height: int = 46,
                 bg: str = WHITE):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._opts, self._on_change = options, on_change
        self._wd, self._ht = width, height
        self.selected = 0
        self._track = photo(rounded_image(width, height, height // 2, TRACK))
        half = width // 2
        self._thumb = photo(rounded_image(half - 6, height - 8, (height - 8) // 2, [VIOLET, PINK]))
        self.bind("<Button-1>", lambda e: self.select(0 if e.x < half else 1))
        self._draw()

    def select(self, index: int, notify: bool = True):
        if index == self.selected:
            return
        self.selected = index
        self._draw()
        if notify:
            self._on_change(index)

    def _draw(self):
        self.delete("all")
        half = self._wd // 2
        self.create_image(0, 0, image=self._track, anchor="nw")
        self.create_image(3 + self.selected * half, 4, image=self._thumb, anchor="nw")
        for i, label in enumerate(self._opts):
            self.create_text(half * i + half // 2, self._ht // 2, text=label, font=font(10, True),
                             fill=WHITE if i == self.selected else MUTED)


class StrengthBar(tk.Canvas):
    """Four rounded segments that fill up (and change colour) as the password gets stronger."""

    def __init__(self, parent, width: int = 320, bg: str = WHITE):
        super().__init__(parent, width=width, height=10, bg=bg, highlightthickness=0, bd=0)
        self._wd = width
        self.set(0, TRACK)

    def set(self, filled: int, color: str):
        self.delete("all")
        gap, seg = 8, (self._wd - 3 * 8 - 6) // 4
        for i in range(4):
            x0 = 3 + i * (seg + gap)
            self.create_line(x0 + 3, 5, x0 + seg - 3, 5, width=6, capstyle="round",
                             fill=color if i < filled else TRACK)


class LinkLabel(tk.Label):
    def __init__(self, parent, text: str, command, bg: str = WHITE, size: int = 10):
        super().__init__(parent, text=text, fg=VIOLET, bg=bg, cursor="hand2", font=font(size, True))
        self._size = size
        self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self.config(fg=PINK))
        self.bind("<Leave>", lambda e: self.config(fg=VIOLET))


def field_label(parent, text: str, bg: str = WHITE) -> tk.Label:
    return tk.Label(parent, text=text, bg=bg, fg=MUTED, font=font(9, True), anchor="w")



# ═══════════════════════════════════════════════════════════════════════════════════
#  THE CHAT WINDOW
#  (header bar, people list, tab pills, message bar -- all colored from the theme dict in themes.py)
# ═══════════════════════════════════════════════════════════════════════════════════

STATUS_DOT = {"active": "#22C55E", "studying": "#3B82F6", "gaming": "#A855F7", "snacking": "#F59E0B",
              "napping": "#94A3B8", "dnd": "#EF4444", "ghost": "#94A3B8", "idle": "#F59E0B", "offline": "#6B7280"}


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:max(1, limit - 1)] + "\u2026"


def glass_image(w: int, h: int, alpha: int) -> Image.Image:
    """A see-through white pill (for buttons sitting on the gradient header)."""
    img = rounded_image(w, h, h // 2, "#FFFFFF")
    img.putalpha(img.getchannel("A").point(lambda v: v * alpha // 255))
    return img


def send_image(size: int, c1: str, c2: str, lift: float = 0.0) -> Image.Image:
    """A gradient circle with a white paper plane."""
    if lift:
        c1, c2 = mix_hex(c1, "#FFFFFF", lift), mix_hex(c2, "#FFFFFF", lift)
    S = size * SS
    body = _hgradient(S, S, [c1, c2]).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S - 1, S - 1), fill=255)
    body.putalpha(mask)
    d = ImageDraw.Draw(body)
    d.polygon([(S * .29, S * .27), (S * .76, S * .50), (S * .29, S * .73), (S * .38, S * .50)], fill=(255, 255, 255, 255))
    return body.resize((size, size), Image.LANCZOS)


class HeaderBar(tk.Canvas):
    """The gradient strip across the top: logo, title, and a row of glassy pill buttons."""
    HEIGHT = 64

    def __init__(self, parent, title: str, subtitle: str, theme: dict):
        super().__init__(parent, height=self.HEIGHT, highlightthickness=0, bd=0, bg=theme["header"])
        self.theme = theme
        self.title_text, self.subtitle_text = title, subtitle
        self.specs: list[list] = []            # [key, label, callback]
        self._pics = []
        self._boxes: dict[str, tuple] = {}
        self._width = 0
        self.bind("<Configure>", self._configured)

    def set_theme(self, theme: dict):
        self.theme = theme
        self.config(bg=theme["header"])
        self._redraw()

    def set_buttons(self, specs):
        self.specs = [list(s) for s in specs]
        self._redraw()

    def set_label(self, key: str, label: str):
        for spec in self.specs:
            if spec[0] == key and spec[1] != label:
                spec[1] = label
                self._redraw()

    def anchor_of(self, key: str):
        """Screen position just under a pill (where its menu should open)."""
        x0, y0, x1, y1 = self._boxes.get(key, (0, 0, 0, self.HEIGHT))
        return self.winfo_rootx() + int(x0), self.winfo_rooty() + int(y1) + 4

    def _configured(self, event):
        if event.width != self._width:
            self._width = event.width
            self._redraw()

    def _redraw(self):
        w, h, t = self._width, self.HEIGHT, self.theme
        if w < 80:
            return
        self.delete("all")
        self._pics = []
        self._boxes = {}

        def keep(img):
            ph = photo(img)
            self._pics.append(ph)
            return ph

        self.create_image(0, 0, image=keep(_hgradient(w, h, [t["header"], t["header2"]])), anchor="nw")
        self.create_image(10, h // 2, image=keep(logo_image(34, pad=6)), anchor="w")
        if w >= 780:
            self.create_text(66, 24, text=self.title_text, anchor="w", fill="white", font=font(13, True))
            self.create_text(66, 43, text=self.subtitle_text, anchor="w", fill="#F1EAFF", font=font(9))

        meas = tkfont.Font(family=family(), size=9, weight="bold")
        x = w - 14
        for key, label, callback in reversed(self.specs):
            pw = meas.measure(label) + 30
            x0 = x - pw
            calm, hover = keep(glass_image(pw, 34, 48)), keep(glass_image(pw, 34, 96))
            tag = f"pill_{key}"
            img = self.create_image(x0, 15, image=calm, anchor="nw", tags=tag)
            self.create_text(x0 + pw / 2, 32, text=label, fill="white", font=font(9, True), tags=tag)
            self.tag_bind(tag, "<Button-1>", lambda e, cb=callback: cb())
            self.tag_bind(tag, "<Enter>", lambda e, i=img, ph=hover: (self.itemconfigure(i, image=ph), self.config(cursor="hand2")))
            self.tag_bind(tag, "<Leave>", lambda e, i=img, ph=calm: (self.itemconfigure(i, image=ph), self.config(cursor="")))
            self._boxes[key] = (x0, 15, x0 + pw, 49)
            x = x0 - 8


class PeopleList(tk.Canvas):
    """Who's online: avatar with a status dot, name, and their status note. Hover + select highlights."""
    ROW = 54

    def __init__(self, parent, theme: dict, avatar_for, on_open, on_menu):
        super().__init__(parent, highlightthickness=0, bd=0, bg=theme["sidebar"], yscrollincrement=self.ROW)
        self.theme = theme
        self._avatar_for, self.on_open, self.on_menu = avatar_for, on_open, on_menu
        self.rows: list[dict] = []
        self.selected = None
        self.hover = None
        self._pics = []
        self._width = 0
        self.bind("<Configure>", self._configured)
        self.bind("<Motion>", self._moved)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<Button-1>", self._clicked)
        self.bind("<Double-Button-1>", self._double)
        self.bind("<Button-3>", self._menu)
        self.bind("<Button-2>", self._menu)
        self.bind("<MouseWheel>", lambda e: self._wheel(-1 if e.delta > 0 else 1))
        self.bind("<Button-4>", lambda e: self._wheel(-1))
        self.bind("<Button-5>", lambda e: self._wheel(1))

    def set_theme(self, theme: dict):
        self.theme = theme
        self.config(bg=theme["sidebar"])
        self._redraw()

    def set_people(self, rows: list[dict]):
        """rows: [{name, title, sub, status}]"""
        keep = self.rows[self.selected]["name"] if self.selected is not None and self.selected < len(self.rows) else None
        self.rows = rows
        self.selected = next((i for i, r in enumerate(rows) if r["name"] == keep), None)
        self._redraw()

    HEADER = 34          # height of an "ONLINE - 3" / "OFFLINE - 5" section label

    def _row_h(self, row) -> int:
        return self.HEADER if row.get("header") else self.ROW

    def _total_h(self) -> int:
        return sum(self._row_h(r) for r in self.rows)

    def name_at(self, y: int):
        i = self._index_at(y)
        return self.rows[i]["name"] if i is not None else None

    def _index_at(self, y: int):
        """Which PERSON row is under y (section labels are not clickable -> None)."""
        cy, top = self.canvasy(y), 0
        for i, row in enumerate(self.rows):
            h = self._row_h(row)
            if top <= cy < top + h:
                return None if row.get("header") else i
            top += h
        return None

    def _configured(self, event):
        if event.width != self._width:
            self._width = event.width
        self._redraw()

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self._redraw()

    def _moved(self, event):
        self._set_hover(self._index_at(event.y))

    def _clicked(self, event):
        i = self._index_at(event.y)
        if i != self.selected:
            self.selected = i
            self._redraw()
        if i is not None:                          # one click opens the private chat, online or offline
            self.on_open(self.rows[i]["name"])

    def _double(self, event):
        name = self.name_at(event.y)
        if name:
            self.on_open(name)

    def _menu(self, event):
        i = self._index_at(event.y)
        if i is None:
            return
        self.selected = i
        self._redraw()
        self.on_menu(self.rows[i]["name"], event)

    def _wheel(self, step: int):
        if self._total_h() > self.winfo_height():
            self.yview_scroll(step, "units")

    def _redraw(self):
        w, t, R = self._width, self.theme, self.ROW
        if w < 40:
            return
        self.delete("all")
        self._pics = []
        y = 0
        for i, row in enumerate(self.rows):
            if row.get("header"):
                self.create_text(18, y + self.HEADER - 10, text=row["title"], anchor="w",
                                 fill=t["muted"], font=font(8, True))
                y += self.HEADER
                continue
            if i == self.selected or i == self.hover:
                hl = photo(rounded_image(w - 12, R - 6, 16, t["selected"] if i == self.selected else t["hover"]))
                self._pics.append(hl)
                self.create_image(6, y + 3, image=hl, anchor="nw")
            av = self._avatar_for(row["name"], 34)
            if av is not None:
                self._pics.append(av)
                self.create_image(20, y + R // 2, image=av, anchor="w")
            else:
                self.create_oval(20, y + R // 2 - 17, 54, y + R // 2 + 17, fill=t["accent"], outline="")
            dot = STATUS_DOT.get(row.get("status"), "#22C55E")
            cx, cy = 52, y + R // 2 + 12
            self.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill=t["selected"] if i == self.selected else t["sidebar"], outline="")
            self.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=dot, outline="")
            badge = int(row.get("badge") or 0)                       # unread messages from this person
            room = max(8, (w - 74 - (30 if badge else 0)) // 8)
            self.create_text(68, y + R // 2 - 9, text=clip(row["title"], room), anchor="w",
                             fill=t["muted"] if row.get("dim") else t["sidebar_fg"], font=font(10, True))
            if badge:
                bx, by = w - 24, y + R // 2
                self.create_oval(bx - 11, by - 11, bx + 11, by + 11, fill="#EF4444", outline="")
                self.create_text(bx, by, text="9+" if badge > 9 else str(badge), fill="white", font=font(8, True))
            if row.get("sub"):
                self.create_text(68, y + R // 2 + 10, text=clip(row["sub"], room + 3), anchor="w",
                                 fill=t["muted"], font=font(8))
            y += R
        self.config(scrollregion=(0, 0, w, max(self._total_h(), self.winfo_height())))


class PillTabs(tk.Frame):
    """Replaces the square ttk.Notebook: a strip of pill tabs above the page. Same calls as a Notebook
    (add / select / index / tab / tabs, and the <<NotebookTabChanged>> event), so chat_window.py barely changes."""

    def __init__(self, parent, theme: dict):
        super().__init__(parent, bg=theme["window"])
        self.theme = theme
        self.strip = tk.Canvas(self, height=50, highlightthickness=0, bd=0, bg=theme["window"])
        self.strip.pack(fill="x", side="top")
        self.content = tk.Frame(self, bg=theme["window"])
        self.content.pack(fill="both", expand=True, side="top")
        self._tabs: list[list] = []            # [widget, text]
        self._current = None
        self._pics = []
        self._hits: list[tuple] = []
        self.strip.bind("<Button-1>", self._clicked)
        self.strip.bind("<Configure>", lambda e: self._redraw())

    # ----- Notebook-style API -----
    def add(self, widget, text: str = "", **kw):
        self._tabs.append([widget, text])
        if self._current is None:
            self.select(widget)
        else:
            self._redraw()

    def select(self, tab=None):
        if tab is None:
            return str(self._current) if self._current is not None else ""
        widget = self._resolve(tab)
        if widget is self._current:
            return ""
        for w, _ in self._tabs:
            if w is not widget:
                w.pack_forget()
        self._current = widget
        widget.pack(in_=self.content, fill="both", expand=True)
        self._redraw()
        self.after_idle(lambda: self.event_generate("<<NotebookTabChanged>>"))    # like ttk: after the switch is done
        return ""

    def index(self, tab) -> int:
        widget = self._resolve(tab)
        return next(i for i, (w, _) in enumerate(self._tabs) if w is widget)

    def tab(self, tab, option=None, **kw):
        entry = self._tabs[self.index(tab)]
        if "text" in kw:
            entry[1] = kw["text"]
            self._redraw()
            return None
        return entry[1] if option == "text" else None

    def tabs(self):
        return tuple(str(w) for w, _ in self._tabs)

    def _resolve(self, tab):
        if isinstance(tab, int):
            return self._tabs[tab][0]
        if isinstance(tab, str):
            for w, _ in self._tabs:
                if str(w) == tab:
                    return w
            raise KeyError(tab)
        return tab

    # ----- look -----
    def set_theme(self, theme: dict):
        self.theme = theme
        self.config(bg=theme["window"])
        self.strip.config(bg=theme["window"])
        self.content.config(bg=theme["window"])
        self._redraw()

    def _redraw(self):
        t = self.theme
        self.strip.delete("all")
        self._pics = []
        self._hits = []
        meas = tkfont.Font(family=t["font"], size=max(8, t["font_size"] - 1), weight="bold")
        x = 14
        for widget, text in self._tabs:
            label = clip(text, 16)
            pw = max(64, meas.measure(label) + 30)
            selected = widget is self._current
            fill = [t["accent"], t["accent2"]] if selected else t["tab_idle"]
            ph = photo(rounded_image(pw, 34, 17, fill))
            self._pics.append(ph)
            self.strip.create_image(x, 8, image=ph, anchor="nw")
            self.strip.create_text(x + pw / 2, 25, text=label, font=(t["font"], max(8, t["font_size"] - 1), "bold"),
                                   fill=t["accent_text"] if selected else t["text"])
            self._hits.append((x, x + pw, widget))
            x += pw + 8

    def _clicked(self, event):
        for x0, x1, widget in self._hits:
            if x0 <= event.x <= x1:
                self.select(widget)
                return


class IconButton(tk.Canvas):
    """A round emoji/glyph button with a soft circle on hover."""

    def __init__(self, parent, glyph: str, command, size: int = 36):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0, cursor="hand2")
        self._size, self._command = size, command
        self._active = False
        self._circle = self.create_image(0, 0, anchor="nw", state="hidden")
        self._glyph = self.create_text(size // 2, size // 2, text=glyph, font=font(13))
        self._photo = None
        self.bind("<Enter>", lambda e: self._show(True))
        self.bind("<Leave>", lambda e: self._show(self._active))
        self.bind("<ButtonRelease-1>", lambda e: self._command() if 0 <= e.x <= size and 0 <= e.y <= size else None)

    def restyle(self, bg: str, fg: str, hover: str):
        self.config(bg=bg)
        self._photo = photo(rounded_image(self._size, self._size, self._size // 2, hover))
        self.itemconfigure(self._circle, image=self._photo)
        self.itemconfigure(self._glyph, fill=fg)

    def set_active(self, on: bool):
        self._active = on
        self._show(on)

    def _show(self, on: bool):
        self.itemconfigure(self._circle, state="normal" if on else "hidden")


class SendButton(tk.Canvas):
    """The round gradient send button."""
    SIZE = 42

    def __init__(self, parent, command):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._imgs = {}
        self._item = self.create_image(0, 0, anchor="nw")
        self.bind("<Enter>", lambda e: self._set("hover"))
        self.bind("<Leave>", lambda e: self._set("calm"))
        self.bind("<ButtonPress-1>", lambda e: self._set("press"))
        self.bind("<ButtonRelease-1>", self._released)

    def restyle(self, bg: str, c1: str, c2: str):
        self.config(bg=bg)
        S = self.SIZE
        self._imgs = {"calm": photo(send_image(S, c1, c2)), "hover": photo(send_image(S, c1, c2, 0.15)),
                      "press": photo(send_image(S - 4, c1, c2))}
        self._set("calm")

    def _set(self, name: str):
        if self._imgs:
            self.itemconfigure(self._item, image=self._imgs[name])
            off = 2 if name == "press" else 0
            self.coords(self._item, off, off)

    def _released(self, event):
        inside = 0 <= event.x <= self.SIZE and 0 <= event.y <= self.SIZE
        self._set("hover" if inside else "calm")
        if inside:
            self._command()


class InputBar(tk.Canvas):
    """The rounded message box: icons on the left, the text entry in the middle, send on the right.
    It glows in the accent color while you're typing."""
    H = 58

    def __init__(self, parent, theme: dict):
        super().__init__(parent, height=self.H, highlightthickness=0, bd=0, bg=theme["window"])
        self.theme = theme
        self._left, self._entry, self._right = [], None, None
        self._win = {}
        self._width = 0
        self._focus = False
        self._pic = None
        self._bg_item = self.create_image(0, 0, anchor="nw", tags="bg")
        self.bind("<Configure>", self._configured)

    def layout(self, left: list, entry, right):
        self._left, self._entry, self._right = left, entry, right
        for w in left:
            self._win[w] = self.create_window(0, 0, window=w, anchor="w")
        self._win[entry] = self.create_window(0, 0, window=entry, anchor="w")
        self._win[right] = self.create_window(0, 0, window=right, anchor="e")
        entry.bind("<FocusIn>", lambda e: self._set_focus(True), add="+")
        entry.bind("<FocusOut>", lambda e: self._set_focus(False), add="+")
        self._place()

    def restyle(self, theme: dict):
        self.theme = theme
        self.config(bg=theme["window"])
        self._place()

    def _set_focus(self, on: bool):
        self._focus = on
        self._place()

    def _configured(self, event):
        if event.width != self._width:
            self._width = event.width
            self._place()

    def _place(self):
        w, h, t = self._width, self.H, self.theme
        if w < 120 or self._entry is None:
            return
        border = t["accent"] if self._focus else mix_hex(t["input_bg"], t["accent"], 0.25)
        self._pic = photo(rounded_image(w - 4, h - 8, (h - 8) // 2, t["input_bg"], border, 2 if self._focus else 1))
        self.itemconfigure(self._bg_item, image=self._pic)
        self.coords(self._bg_item, 2, 4)
        x = 14
        for widget in self._left:
            self.coords(self._win[widget], x, h // 2)
            x += 38
        self.coords(self._win[self._entry], x + 4, h // 2)
        self.itemconfigure(self._win[self._entry], width=max(40, w - x - 4 - 62), height=30)
        self.coords(self._win[self._right], w - 12, h // 2)
        self.tag_lower("bg")
