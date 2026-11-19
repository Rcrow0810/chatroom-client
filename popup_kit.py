# popup_kit.py  --  CLIENT SIDE
# ---------------------------------------------------------
# Makes the POP-UPS (Settings, Wallet, payment requests, game invites, profile cards, message boxes...)
# look like the chat window and the login screen: same colors, same rounded pill buttons, same gradient
# header strip.  Everything here reads colors from the theme dict in themes.py, so a popup follows
# whichever theme the person picked (Pop, Pop Dark, Midnight, ...).
#
#   set_theme(t)        - the chat window calls this whenever the theme changes
#   style_ttk(t)        - recolors every ttk widget (tabs, entries, combo boxes, tables, scrollbars...)
#   PillButton          - the rounded gradient button (primary / soft / danger / ghost)
#   RoundEntry          - the rounded text box with an accent glow (add values=[...] for a drop-down)
#   Header / add_header - the gradient strip across the top of a popup
#   Themer              - walks a popup's widgets and recolors the plain Tk ones, so old code
#                         (tk.Label, tk.Button, tk.Entry...) matches without being rewritten
#   messagebox          - drop-in for tkinter.messagebox (showinfo/showwarning/showerror/askyesno...)
#   simpledialog        - drop-in for tkinter.simpledialog.askstring
# ---------------------------------------------------------

import tkinter as tk
from tkinter import font as tkfont, ttk
from types import SimpleNamespace

import themes
import ui_kit as ui
from themes import readable_on
from ui_kit import mix_hex, photo, rounded_image

DANGER = ui.DANGER
WARN = "#F59E0B"
OK = "#14A44D"

# ── the theme popups should use ─────────────────────────────────────────────────────
_current = None
_default = None


def default_theme() -> dict:
    global _default
    if _default is None:
        _default = themes.build_theme(themes.DEFAULT_PREFS)
    return _default


def set_theme(t: dict | None):
    """Chat window: call with the live theme. Call with None to go back to the default (login) look."""
    global _current
    _current = t


def current() -> dict:
    return _current or default_theme()


def fnt(t: dict, delta: int = 0, bold: bool = False) -> tuple:
    size = max(7, t["font_size"] + delta)
    return (t["font"], size, "bold") if bold else (t["font"], size)


# ── ttk (tabs, entries, combo boxes, tables, scrollbars) ────────────────────────────
def style_ttk(t: dict) -> str:
    """Recolor all ttk widgets from the theme. Returns the ttk theme that was active before, so a
    window that only borrows the look can put it back."""
    s = ttk.Style()
    previous = s.theme_use()
    try:
        s.theme_use("clam")                      # the one built-in look that lets us recolor everything
    except tk.TclError:
        pass
    fam, size = t["font"], t["font_size"]
    bg, fg, muted = t["window"], t["text"], t["muted"]
    field, ifg = t["input_bg"], t["input_fg"]
    acc, acct = t["accent"], t["accent_text"]
    idle = t["tab_idle"]
    edge = mix_hex(field, acc, 0.28)
    hover = mix_hex(acc, "#ffffff", 0.15)
    press = mix_hex(acc, "#000000", 0.15)
    tint = mix_hex(idle, acc, 0.22)

    s.configure(".", background=bg, foreground=fg, fieldbackground=field, font=(fam, size), bordercolor=edge,
                lightcolor=bg, darkcolor=bg, troughcolor=idle, focuscolor=bg, selectbackground=acc,
                selectforeground=acct, insertcolor=acc)
    s.configure("TFrame", background=bg)
    s.configure("TLabel", background=bg, foreground=fg)
    s.configure("TLabelframe", background=bg, bordercolor=edge, lightcolor=edge, darkcolor=edge,
                borderwidth=1, relief="solid")
    s.configure("TLabelframe.Label", background=bg, foreground=readable_on(acc, bg, 3.0),
                font=(fam, size, "bold"))

    s.configure("TButton", background=acc, foreground=acct, bordercolor=acc, lightcolor=acc, darkcolor=acc,
                borderwidth=0, relief="flat", focusthickness=0, padding=(16, 7), font=(fam, size, "bold"))
    s.map("TButton",
          background=[("disabled", idle), ("pressed", press), ("active", hover)],
          bordercolor=[("disabled", idle), ("pressed", press), ("active", hover)],
          lightcolor=[("disabled", idle), ("pressed", press), ("active", hover)],
          darkcolor=[("disabled", idle), ("pressed", press), ("active", hover)],
          foreground=[("disabled", muted)])

    s.configure("TEntry", fieldbackground=field, foreground=ifg, bordercolor=edge, lightcolor=field,
                darkcolor=field, padding=6, insertcolor=acc)
    s.map("TEntry", bordercolor=[("focus", acc)], lightcolor=[("focus", acc)], darkcolor=[("focus", acc)],
          fieldbackground=[("disabled", idle)], foreground=[("disabled", muted)])

    s.configure("TCombobox", fieldbackground=field, background=field, foreground=ifg, arrowcolor=acc,
                bordercolor=edge, lightcolor=field, darkcolor=field, padding=5, selectbackground=field,
                selectforeground=ifg)
    s.map("TCombobox", fieldbackground=[("readonly", field), ("disabled", idle)],
          background=[("active", idle), ("readonly", field)],
          bordercolor=[("focus", acc)], lightcolor=[("focus", acc)], darkcolor=[("focus", acc)],
          foreground=[("disabled", muted)], selectbackground=[("readonly", field)],
          selectforeground=[("readonly", ifg)], arrowcolor=[("disabled", muted)])
    # the same combo box with no outline of its own (RoundEntry draws the outline)
    s.configure("Round.TCombobox", fieldbackground=field, background=field, foreground=ifg, arrowcolor=acc,
                bordercolor=field, lightcolor=field, darkcolor=field, borderwidth=0, padding=2,
                selectbackground=field, selectforeground=ifg)
    s.map("Round.TCombobox", fieldbackground=[("readonly", field), ("disabled", field)],
          background=[("active", field), ("readonly", field), ("disabled", field)],
          bordercolor=[("focus", field)], lightcolor=[("focus", field)], darkcolor=[("focus", field)],
          foreground=[("disabled", muted)], selectbackground=[("readonly", field)],
          selectforeground=[("readonly", ifg)], arrowcolor=[("disabled", muted)])
    try:                                              # the drop-down list itself is a plain Tk listbox
        root = s.master
        root.option_add("*TCombobox*Listbox.background", field)
        root.option_add("*TCombobox*Listbox.foreground", ifg)
        root.option_add("*TCombobox*Listbox.selectBackground", acc)
        root.option_add("*TCombobox*Listbox.selectForeground", acct)
        root.option_add("*TCombobox*Listbox.font", (fam, size))
    except Exception:
        pass

    for name in ("TCheckbutton", "TRadiobutton"):
        s.configure(name, background=bg, foreground=fg, indicatorbackground=field, indicatorforeground=acc,
                    upperbordercolor=edge, lowerbordercolor=edge, focuscolor=bg)
        s.map(name, background=[("active", bg)], indicatorbackground=[("selected", acc), ("!selected", field)],
              indicatorforeground=[("selected", acct)], foreground=[("disabled", muted)])

    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        s.configure(name, background=mix_hex(idle, acc, 0.35), troughcolor=bg, bordercolor=bg, lightcolor=bg,
                    darkcolor=bg, arrowcolor=acc, relief="flat", borderwidth=0, gripcount=0)
        s.map(name, background=[("active", acc), ("pressed", press)])

    s.configure("Treeview", background=field, fieldbackground=field, foreground=ifg, borderwidth=0,
                relief="flat", rowheight=int(size * 2.4), font=(fam, size))
    s.map("Treeview", background=[("selected", acc)], foreground=[("selected", acct)])
    s.configure("Treeview.Heading", background=idle, foreground=fg, relief="flat", borderwidth=0, padding=7,
                font=(fam, size, "bold"))
    s.map("Treeview.Heading", background=[("active", tint)])

    s.configure("TNotebook", background=bg, borderwidth=0, tabmargins=(2, 4, 2, 0))
    s.configure("TNotebook.Tab", background=idle, foreground=fg, padding=(12, 6), borderwidth=0,
                font=(fam, size, "bold"))
    s.map("TNotebook.Tab", background=[("selected", acc), ("active", tint)],
          foreground=[("selected", acct)])
    s.configure("TSeparator", background=edge)
    return previous


# ── small helpers ───────────────────────────────────────────────────────────────────
def center_on(win: tk.Misc, parent: tk.Misc | None = None):
    """Put `win` in the middle of `parent` (or of the screen if there is no visible parent)."""
    try:
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        if parent is not None and parent.winfo_viewable():
            top = parent.winfo_toplevel()
            x = top.winfo_rootx() + (top.winfo_width() - w) // 2
            y = top.winfo_rooty() + (top.winfo_height() - h) // 2
        else:
            x = (win.winfo_screenwidth() - w) // 2
            y = (win.winfo_screenheight() - h) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass


# ── the gradient strip ──────────────────────────────────────────────────────────────
class Header(tk.Canvas):
    """The gradient bar at the top of a popup: small logo, a title, and an optional second line."""

    def __init__(self, parent, t: dict | None = None, title: str = "", subtitle: str = "", height: int = 58):
        self.t = t or current()
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=self.t["header"])
        self.title_text, self.subtitle_text, self._h = title, subtitle, height
        self._cw = 0
        self._pics = []
        tk.Canvas.bind(self, "<Configure>", self._configured)

    def restyle(self, t: dict):
        self.t = t
        self.configure(bg=t["header"])
        self._redraw()

    def set_text(self, title: str, subtitle: str = ""):
        self.title_text, self.subtitle_text = title, subtitle
        self._redraw()

    def _configured(self, event):
        if event.width != self._cw:
            self._cw = event.width
            self._redraw()

    def _redraw(self):
        w, h, t = self._cw, self._h, self.t
        if w < 60:
            return
        self.delete("all")
        self._pics = [photo(ui._hgradient(w, h, [t["header"], t["header2"]])),
                      photo(ui.logo_image(32, pad=6))]
        self.create_image(0, 0, image=self._pics[0], anchor="nw")
        self.create_image(12, h // 2, image=self._pics[1], anchor="w")
        if self.subtitle_text:
            self.create_text(64, h // 2 - 10, text=self.title_text, anchor="w", fill="white", font=fnt(t, 3, True))
            self.create_text(64, h // 2 + 12, text=self.subtitle_text, anchor="w", fill="#F1EAFF", font=fnt(t, -1))
        else:
            self.create_text(64, h // 2, text=self.title_text, anchor="w", fill="white", font=fnt(t, 3, True))


def add_header(win: tk.Misc, t: dict | None, title: str, subtitle: str = "", height: int = 58) -> Header:
    head = Header(win, t, title, subtitle, height)
    head.pack(fill="x", side="top")
    return head


class _Bar(tk.Canvas):
    """A thin gradient line, used on top of small message boxes."""

    def __init__(self, parent, t: dict, height: int = 6):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=t["header"])
        self.t, self._h, self._cw, self._pic = t, height, 0, None
        tk.Canvas.bind(self, "<Configure>", self._configured)

    def _configured(self, event):
        if event.width == self._cw or event.width < 10:
            return
        self._cw = event.width
        self._pic = photo(ui._hgradient(self._cw, self._h, [self.t["header"], self.t["header2"], self.t["accent"]]))
        self.delete("all")
        self.create_image(0, 0, image=self._pic, anchor="nw")


# ── the pill button ─────────────────────────────────────────────────────────────────
class PillButton(tk.Canvas):
    """A rounded button.  style: 'primary' (accent gradient), 'soft' (pale accent), 'danger' (red),
    'ghost' (just text).  Works like a tk.Button for the calls the app uses: config(text=, state=,
    command=), cget('state'), pack/grid.  width=None sizes the button to its text."""

    def __init__(self, parent, text: str = "", command=None, t: dict | None = None, style: str = "primary",
                 width: int | None = None, height: int = 38, bg: str | None = None, size: int | None = None,
                 state: str = "normal"):
        self.t = t or current()
        super().__init__(parent, highlightthickness=0, bd=0, bg=bg or self.t["window"], cursor="hand2")
        self._text, self._command, self._style = text, command, style
        self._req_w, self._h, self._size = width, height, size
        self._fixed_bg = bg
        self._enabled = state != "disabled"
        self._imgs, self._pics = {}, []
        self._img_item = self._label = None
        self._wd = 0
        self._build()
        tk.Canvas.bind(self, "<Enter>", lambda e: self._set("hover"))
        tk.Canvas.bind(self, "<Leave>", lambda e: self._set("calm"))
        tk.Canvas.bind(self, "<ButtonPress-1>", lambda e: self._set("press"))
        tk.Canvas.bind(self, "<ButtonRelease-1>", self._released)

    # ----- drawing -----
    def _build(self):
        t, style, h = self.t, self._style, self._h
        size = self._size or t["font_size"]
        meas = tkfont.Font(family=t["font"], size=size, weight="bold")
        w = self._req_w or max(84, meas.measure(self._text) + 44)
        self._wd = w
        r = h // 2
        acc, window, idle = t["accent"], t["window"], t["tab_idle"]
        if style == "primary":
            fills = {"calm": [acc, t["accent2"]],
                     "hover": [mix_hex(acc, "#ffffff", .14), mix_hex(t["accent2"], "#ffffff", .14)],
                     "press": [mix_hex(acc, "#000000", .14), mix_hex(t["accent2"], "#000000", .14)],
                     "off": [mix_hex(acc, window, .65), mix_hex(t["accent2"], window, .65)]}
            fg = t["accent_text"]
        elif style == "danger":
            fills = {"calm": DANGER, "hover": mix_hex(DANGER, "#ffffff", .14), "press": mix_hex(DANGER, "#000000", .14),
                     "off": mix_hex(DANGER, window, .65)}
            fg = "#ffffff"
        elif style == "soft":
            fills = {"calm": idle, "hover": mix_hex(idle, acc, .22), "press": mix_hex(idle, acc, .36),
                     "off": mix_hex(idle, window, .55)}
            fg = readable_on(acc, idle, 3.0)
        else:                                                   # ghost
            fills, fg = {}, t["muted"]
        self._fg = fg
        self._fg_off = t["muted"] if style in ("soft", "ghost") else mix_hex(fg, window, .35)
        self._pics = [photo(rounded_image(w, h, r, f)) for f in fills.values()]
        self._imgs = dict(zip(fills.keys(), self._pics))
        tk.Canvas.configure(self, width=w, height=h, bg=self._fixed_bg or window)
        self.delete("all")
        self._img_item = self.create_image(0, 0, image=self._imgs["calm"], anchor="nw") if self._imgs else None
        self._label = self.create_text(w // 2, h // 2, text=self._text, fill=fg, font=(t["font"], size, "bold"))
        self._set("calm")

    def _set(self, name: str):
        if not self._enabled:
            name = "off"
        if self._img_item is not None:
            self.itemconfigure(self._img_item, image=self._imgs[name])
            self.itemconfigure(self._label, fill=self._fg_off if name == "off" else self._fg)
        else:
            lit = self._enabled and name in ("hover", "press")
            self.itemconfigure(self._label, fill=self.t["accent"] if lit else (self._fg if self._enabled else self._fg_off))

    def _released(self, event):
        inside = 0 <= event.x <= self._wd and 0 <= event.y <= self._h
        self._set("hover" if inside else "calm")
        if inside and self._enabled and self._command:
            self._command()

    # ----- tk.Button-style API -----
    def configure(self, cnf=None, **kw):
        if cnf:
            kw = {**cnf, **kw}
        if not kw:
            return super().configure()
        rebuild = False
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            tk.Canvas.configure(self, cursor="hand2" if self._enabled else "arrow")
            self._set("calm")
        if "text" in kw:
            self._text = kw.pop("text")
            rebuild = True
        if "command" in kw:
            self._command = kw.pop("command")
        if kw:
            super().configure(**kw)
        if rebuild:
            self._build()
        return None

    config = configure

    def cget(self, key):
        if key == "state":
            return "normal" if self._enabled else "disabled"
        if key == "text":
            return self._text
        return super().cget(key)

    def restyle(self, t: dict):
        self.t = t
        self._build()


# ── the rounded text box ────────────────────────────────────────────────────────────
class RoundEntry(tk.Canvas):
    """A rounded text box that glows in the accent color when you click into it.  Behaves like an Entry
    (get / set / insert / delete / focus_set / bind / config(state=, show=)).  Pass values=[...] to get a
    drop-down list instead (a Combobox: config(values=[...]) works too).  The box stretches sideways when
    you pack it with fill='x' or grid it with sticky='ew'."""

    def __init__(self, parent, t: dict | None = None, width: int = 240, height: int = 40,
                 textvariable=None, show: str = "", values=None, bg: str | None = None,
                 justify: str = "left", size: int | None = None):
        self.t = t or current()
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, bg=bg or self.t["window"])
        self._fixed_bg, self._h, self._cw = bg, height, 0
        self._size, self._focus, self._pic = size, False, None
        self._combo = values is not None
        if self._combo:
            self.entry = ttk.Combobox(self, style="Round.TCombobox", textvariable=textvariable,
                                      values=list(values), font=self._font())
        else:
            self.entry = tk.Entry(self, relief="flat", bd=0, highlightthickness=0, textvariable=textvariable,
                                  show=show, justify=justify)
        self._bg_item = self.create_image(0, 0, anchor="nw")
        self._win = self.create_window(14, height // 2, window=self.entry, anchor="w")
        self._paint_entry()
        tk.Canvas.bind(self, "<Configure>", self._configured)
        tk.Canvas.bind(self, "<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._set_focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False), add="+")

    def _font(self):
        return (self.t["font"], self._size or self.t["font_size"])

    def _paint_entry(self):
        t = self.t
        if self._combo:
            self.entry.configure(font=self._font())
            return
        field = t["input_bg"]
        self.entry.configure(bg=field, fg=t["input_fg"], insertbackground=t["accent"], font=self._font(),
                             selectbackground=t["accent"], selectforeground=t["accent_text"],
                             disabledbackground=mix_hex(field, t["window"], .5), disabledforeground=t["muted"],
                             readonlybackground=field)

    def _configured(self, event):
        if event.width != self._cw:
            self._cw = event.width
            self._redraw()

    def _set_focus(self, on: bool):
        self._focus = on
        self._redraw()

    def _redraw(self):
        w, h, t = self._cw, self._h, self.t
        if w < 40:
            return
        edge = t["accent"] if self._focus else mix_hex(t["input_bg"], t["accent"], .28)
        self._pic = photo(rounded_image(w - 2, h - 2, h // 3, t["input_bg"], edge, 2 if self._focus else 1))
        self.itemconfigure(self._bg_item, image=self._pic)
        self.coords(self._bg_item, 1, 1)
        self.coords(self._win, 14, h // 2)
        self.itemconfigure(self._win, width=max(20, w - 28), height=h - 14)
        self.tag_lower(self._bg_item)

    # ----- Entry-style API -----
    _ENTRY_KEYS = ("state", "values", "show", "textvariable", "justify")

    def configure(self, cnf=None, **kw):
        if cnf:
            kw = {**cnf, **kw}
        if not kw:
            return super().configure()
        inner = {k: kw.pop(k) for k in list(kw) if k in self._ENTRY_KEYS}
        if inner:
            self.entry.configure(**inner)
        if kw:
            super().configure(**kw)
        return None

    config = configure

    def cget(self, key):
        if key in self._ENTRY_KEYS:
            return self.entry.cget(key)
        return super().cget(key)

    def get(self):
        return self.entry.get()

    def set(self, value):
        if self._combo:
            self.entry.set(value)
        else:
            self.delete(0, "end")
            self.insert(0, value)

    def insert(self, index, text):
        self.entry.insert(index, text)

    def delete(self, first, last=None):
        self.entry.delete(first, last)

    def focus_set(self):
        self.entry.focus_set()

    def bind(self, sequence=None, func=None, add=None):
        return self.entry.bind(sequence, func, add)

    def restyle(self, t: dict):
        self.t = t
        tk.Canvas.configure(self, bg=self._fixed_bg or t["window"])
        self._paint_entry()
        self._redraw()


# ── recolor plain Tk widgets ────────────────────────────────────────────────────────
_TEXT_COLORS = {"black", "#000000", "systemwindowtext", "#222222", "#1e1b3a", "#333333", "#444444", "#1f2328"}
_MUTED_COLORS = {"#888888", "#888", "#555555", "#666666", "#777777", "gray", "grey"}
_DANGER_COLORS = {"#c0392b", "#d9534f", "#e5484d", "#b26a00"}
_OK_COLORS = {"#2e8b57", "#2e9e5b", "#14a44d", "#27ae60"}


def _guess_role(color: str) -> str | None:
    c = (color or "").lower()
    if c in _TEXT_COLORS or c == "":
        return "text"
    if c in _MUTED_COLORS:
        return "muted"
    if c in _DANGER_COLORS:
        return "danger"
    if c in _OK_COLORS:
        return "ok"
    return None                       # a color somebody chose on purpose: leave it alone


def _role_color(t: dict, role: str) -> str:
    if role == "muted":
        return t["muted"]
    if role == "danger":
        return readable_on(DANGER, t["window"], 3.0)
    if role == "ok":
        return readable_on(OK, t["window"], 3.0)
    return t["text"]


def _px(w: tk.Misc, option: str) -> int:
    try:
        return int(float(str(w.cget(option))))
    except (tk.TclError, ValueError):
        return 0


def _refont(w: tk.Misc, t: dict):
    """Switch a widget to the theme's font family, keeping its size and weight (emoji fonts are left alone)."""
    try:
        actual = tkfont.Font(font=w.cget("font")).actual()
        family = actual["family"]
        if "emoji" in family.lower() or "symbol" in family.lower():
            return
        w.configure(font=(t["font"], abs(int(actual["size"])) or t["font_size"],
                          "bold" if actual["weight"] == "bold" else "normal"))
    except (tk.TclError, KeyError, ValueError):
        pass


class Themer:
    """Recolors a popup so plain Tk widgets match the theme.  Call apply() after building the popup, and
    again whenever the theme changes.  Mark a widget you want left alone with  widget._pk_skip = True.
    A widget can also say what it is:  label._pk_role = 'muted' | 'text' | 'danger' | 'ok'."""

    def __init__(self, root: tk.Misc, theme_fn=None):
        self.root = root
        self.theme_fn = theme_fn or current

    def apply(self):
        t = self.theme_fn()
        try:
            self.root.configure(bg=t["window"])
        except tk.TclError:
            pass
        self._walk(self.root, t)

    def _walk(self, parent: tk.Misc, t: dict):
        try:
            children = parent.winfo_children()
        except tk.TclError:
            return
        for w in children:
            try:
                if getattr(w, "_pk_skip", False):
                    continue
                if hasattr(w, "restyle"):
                    w.restyle(t)
                    continue
                if hasattr(w, "set_theme"):
                    w.set_theme(t)
                self._one(w, w.winfo_class(), t)
                self._walk(w, t)
            except tk.TclError:
                pass

    def _one(self, w: tk.Misc, cls: str, t: dict):
        bg = t["window"]
        if cls == "Frame":
            w.configure(bg=bg)
        elif cls == "Labelframe":
            w.configure(bg=bg, fg=t["text"])
        elif cls == "Label":
            self._label(w, t)
        elif cls == "Button":
            self._button(w, t)
        elif cls == "Entry":
            field = t["input_bg"]
            w.configure(bg=field, fg=t["input_fg"], insertbackground=t["accent"], relief="flat",
                        highlightthickness=1, highlightbackground=mix_hex(field, t["accent"], .28),
                        highlightcolor=t["accent"], selectbackground=t["accent"],
                        selectforeground=t["accent_text"], disabledbackground=mix_hex(field, bg, .5),
                        disabledforeground=t["muted"], readonlybackground=field)
            _refont(w, t)
        elif cls == "Text":
            field = t["input_bg"]
            w.configure(bg=field, fg=t["input_fg"], insertbackground=t["accent"], relief="flat",
                        highlightthickness=1, highlightbackground=mix_hex(field, t["accent"], .28),
                        highlightcolor=t["accent"], selectbackground=t["accent"],
                        selectforeground=t["accent_text"])
            _refont(w, t)
        elif cls in ("Checkbutton", "Radiobutton"):
            w.configure(bg=bg, fg=t["text"], activebackground=bg, activeforeground=t["text"],
                        selectcolor=t["input_bg"], highlightthickness=0)
            _refont(w, t)

    def _label(self, w: tk.Label, t: dict):
        w.configure(bg=t["window"])
        if str(w.cget("image")):
            return
        cur = str(w.cget("fg")).lower()
        role = getattr(w, "_pk_role", None)
        if getattr(w, "_pk_assigned", None) not in (None, cur):       # the program recolored it since last time
            role = _guess_role(cur)
        elif role is None:
            role = _guess_role(cur)
        w._pk_role = role
        if role is not None:
            color = _role_color(t, role)
            w.configure(fg=color)
            w._pk_assigned = color.lower()
        _refont(w, t)

    def _button(self, w: tk.Button, t: dict):
        cur = str(w.cget("bg")).lower()
        role = getattr(w, "_pk_role", None)
        if getattr(w, "_pk_assigned", None) not in (None, cur) or role is None:
            role = "danger" if cur in ("#c0392b", "#a93226", "#e5484d") else "accent"
        w._pk_role = role
        if role == "danger":
            base, fg = DANGER, "#ffffff"
        else:
            base, fg = t["accent"], t["accent_text"]
        hover = mix_hex(base, "#ffffff", .14)
        w.configure(bg=base, fg=fg, activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                    highlightthickness=0, cursor="hand2", disabledforeground=mix_hex(fg, base, .45),
                    padx=max(_px(w, "padx"), 14), pady=max(_px(w, "pady"), 5))
        w._pk_assigned, w._pk_bg, w._pk_hbg = base.lower(), base, hover
        _refont(w, t)
        if not getattr(w, "_pk_hover", False):
            w._pk_hover = True
            w.bind("<Enter>", lambda e, b=w: str(b.cget("state")) != "disabled" and b.configure(bg=b._pk_hbg), add="+")
            w.bind("<Leave>", lambda e, b=w: b.configure(bg=b._pk_bg), add="+")


# ── message boxes (drop-in for tkinter.messagebox / simpledialog) ───────────────────
_ICONS = {"info": ("i", None), "warning": ("!", WARN), "error": ("✕", DANGER), "question": ("?", None)}


class _Box(tk.Toplevel):
    """The window behind messagebox.* : gradient line on top, round icon, title, message, pill buttons."""

    def __init__(self, parent, title: str, message: str, kind: str, buttons: list, default, cancel,
                 ask_text: bool = False, initial: str = ""):
        super().__init__(parent)
        t = current()
        self.t, self.result, self._cancel_value, self._default = t, cancel, cancel, default
        self.entry = None
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=t["window"])
        try:
            if parent is not None and parent.winfo_viewable():
                self.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass

        _Bar(self, t).pack(fill="x")
        body = tk.Frame(self, bg=t["window"])
        body.pack(fill="both", expand=True, padx=24, pady=(18, 8))
        glyph, color = _ICONS.get(kind, _ICONS["info"])
        icon = tk.Canvas(body, width=46, height=46, bg=t["window"], highlightthickness=0, bd=0)
        icon._img = photo(rounded_image(46, 46, 23, color or t["accent"]))
        icon.create_image(0, 0, image=icon._img, anchor="nw")
        icon.create_text(23, 23, text=glyph, fill="white", font=(t["font"], 17, "bold"))
        icon.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 16))
        tk.Label(body, text=title, bg=t["window"], fg=t["text"], font=fnt(t, 2, True), anchor="w",
                 justify="left", wraplength=360).grid(row=0, column=1, sticky="w")
        tk.Label(body, text=message, bg=t["window"], fg=t["text"], font=fnt(t), anchor="w", justify="left",
                 wraplength=360).grid(row=1, column=1, sticky="w", pady=(4, 0))
        if ask_text:
            self.entry = RoundEntry(body, t, width=360, height=42)
            self.entry.grid(row=2, column=1, sticky="ew", pady=(12, 0))
            self.entry.insert(0, initial or "")
        row = tk.Frame(self, bg=t["window"])
        row.pack(fill="x", padx=24, pady=(10, 18))
        for label, value, style in reversed(buttons):
            PillButton(row, label, lambda v=value: self._pick(v), t=t, style=style, width=96, height=38).pack(
                side="right", padx=(8, 0))
        self.bind("<Return>", lambda e: self._pick(default))
        self.bind("<Escape>", lambda e: self._pick(cancel))
        self.protocol("WM_DELETE_WINDOW", lambda: self._pick(cancel))

    def _pick(self, value):
        if self.entry is not None:
            self._typed = self.entry.get() if value is not None and value is not False else None
        self.result = value
        self.destroy()

    def run(self):
        center_on(self, self.master if self.master is not None else None)
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        try:
            self.focus_force()
            if self.entry is not None:
                self.entry.focus_set()
        except tk.TclError:
            pass
        self.wait_window(self)
        return self.result


def _root(parent):
    return parent if parent is not None else tk._default_root


def _show(kind: str, title: str, message: str, parent, buttons: list, default, cancel):
    root = _root(parent)
    if root is None:
        raise tk.TclError("no window")
    return _Box(root, title, message, kind, buttons, default, cancel).run()


def _native(name: str, *args, **kw):
    from tkinter import messagebox as native
    return getattr(native, name)(*args, **kw)


def _simple(kind: str, native_name: str):
    def show(title=None, message=None, parent=None, **kw):
        try:
            _show(kind, title or "", message or "", parent, [("OK", "ok", "primary")], "ok", "ok")
        except tk.TclError:
            _native(native_name, title, message, parent=parent)
        return "ok"
    return show


def _askyesno(title=None, message=None, parent=None, **kw):
    try:
        return bool(_show("question", title or "", message or "", parent,
                          [("No", False, "soft"), ("Yes", True, "primary")], True, False))
    except tk.TclError:
        return _native("askyesno", title, message, parent=parent)


def _askokcancel(title=None, message=None, parent=None, **kw):
    try:
        return bool(_show("question", title or "", message or "", parent,
                          [("Cancel", False, "soft"), ("OK", True, "primary")], True, False))
    except tk.TclError:
        return _native("askokcancel", title, message, parent=parent)


messagebox = SimpleNamespace(
    showinfo=_simple("info", "showinfo"),
    showwarning=_simple("warning", "showwarning"),
    showerror=_simple("error", "showerror"),
    askyesno=_askyesno,
    askokcancel=_askokcancel,
)


def _askstring(title=None, prompt=None, parent=None, initialvalue=None, **kw):
    try:
        root = _root(parent)
        if root is None:
            raise tk.TclError("no window")
        box = _Box(root, title or "", prompt or "", "question",
                   [("Cancel", None, "soft"), ("OK", "ok", "primary")], "ok", None, ask_text=True,
                   initial=initialvalue or "")
        box._typed = None
        result = box.run()
        return box._typed if result == "ok" else None
    except tk.TclError:
        from tkinter import simpledialog as native
        return native.askstring(title, prompt, parent=parent, initialvalue=initialvalue)


simpledialog = SimpleNamespace(askstring=_askstring)
