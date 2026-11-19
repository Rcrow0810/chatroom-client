# onscreen_keyboard.py
# ---------------------------------------------------------
# A small on-screen keyboard for typing accented letters (and a few symbols)
# into the message box, for computers whose own keyboard or input method
# can't produce them (common with Tkinter on Linux).
#
#   LAYOUTS          - which keys each language offers (plain data: easy to edit)
#   key_chars        - Shift / Caps handling (pure function, no window needed)
#   type_into        - puts a character into an Entry like real typing does
#   backspace_in     - same for the backspace key
#   KeyboardPanel    - the strip of buttons that sits above the message box
#
# TO ADD A LANGUAGE: add one line to LAYOUTS. A key is a lowercase letter, and
# its capital is worked out automatically. Where the capital is NOT just
# letter.upper(), write the pair as (lower, upper) -- see Turkish and German.
#
# This only inserts characters into the box on YOUR screen. Nothing about it is
# sent to the server; the message goes out exactly as any typed message does.
# ---------------------------------------------------------

import tkinter as tk
from tkinter import ttk

# code -> (name shown in the menu, keys)
LAYOUTS: dict[str, tuple[str, list]] = {
    "ca": ("Catalan",    list("àéèíïòóúüç·")),
    "cs": ("Czech",      list("áčďéěíňóřšťúůýž")),
    "da": ("Danish",     list("åæøé")),
    "de": ("German",     ["ä", "ö", "ü", ("ß", "ẞ")]),
    "eo": ("Esperanto",  list("ĉĝĥĵŝŭ")),
    "es": ("Spanish",    list("áéíóúüñ¿¡")),
    "fi": ("Finnish",    list("åäöšž")),
    "fr": ("French",     list("àâæçéèêëîïôœùûüÿ«»")),
    "ga": ("Irish",      list("áéíóú")),
    "hu": ("Hungarian",  list("áéíóöőúüű")),
    "it": ("Italian",    list("àèéìíòóùú")),
    "lt": ("Lithuanian", list("ąčęėįšųūž")),
    "lv": ("Latvian",    list("āčēģīķļņšūž")),
    "nb": ("Norwegian",  list("åæøé")),
    "nl": ("Dutch",      list("ëïéèêóöü")),
    "pl": ("Polish",     list("ąćęłńóśźż")),
    "pt": ("Portuguese", list("áàâãçéêíóôõú")),
    "ro": ("Romanian",   list("ăâîșț")),
    "sk": ("Slovak",     list("áäčďéíĺľňóôŕšťúýž")),
    "sq": ("Albanian",   list("çë")),
    "sv": ("Swedish",    list("åäöé")),
    # Turkish / Azerbaijani: the one key below shows dotless ı, and İ (capital dotted I) when
    # Shift is on. Plain i and I are typed on your normal keyboard as usual.
    "tr": ("Turkish",    list("çğöşü") + [("ı", "İ")]),
    "az": ("Azerbaijani", list("əçğöşü") + [("ı", "İ")]),
    "tl": ("Filipino",   list("ñ")),
    "af": ("Afrikaans",  list("áâèéêëîïôöûü")),
    "bg": ("Bulgarian",  list("абвгдежзийклмнопрстуфхцчшщъьюя")),
    "bs": ("Bosnian",    list("čćđšž")),
    "cy": ("Welsh",      list("âêîôûŵŷäëïöüẁẃẅỳýÿ")),
    "el": ("Greek",      list("αβγδεζηθικλμνξοπρστυφχψωάέήίόύώϊϋ")),
    "et": ("Estonian",   list("äõöüšž")),
    "hr": ("Croatian",   list("čćđšž")),
    "is": ("Icelandic",  list("áðéíóúýþæö")),
    "mt": ("Maltese",    list("ċġħż")),
    "ru": ("Russian",    list("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")),
    "sl": ("Slovenian",  list("čšž")),
    "sr": ("Serbian",    list("čćđšž")),
    "uk": ("Ukrainian",  list("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя")),
    "vi": ("Vietnamese", list("àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ")),
    "sym": ("Symbols",   list("€£¥¢°±×÷§©®™“”‘’„–—…•½¼¾²³")),
}

DEFAULT_LANGUAGE = "es"


def layout_names() -> list[tuple[str, str]]:
    """[(code, name), ...] for the menu: the symbols page last, the rest A-Z by name."""
    langs = sorted(((c, n) for c, (n, _k) in LAYOUTS.items() if c != "sym"), key=lambda p: p[1])
    return langs + [("sym", LAYOUTS["sym"][0])]


def key_chars(keys: list, upper: bool) -> list[str]:
    """The character each key types right now.

    Letters follow Shift/Caps. A key whose capital would be more than one letter
    (str.upper() turns 'ß' into 'SS') is left alone unless it has an explicit capital.
    """
    out = []
    for key in keys:
        if isinstance(key, tuple):
            out.append(key[1] if upper else key[0])
        elif upper and len(key.upper()) == 1:
            out.append(key.upper())
        else:
            out.append(key)
    return out


def type_into(entry, ch: str) -> None:
    """Insert `ch` at the cursor, replacing any selected text (what real typing does)."""
    try:
        if entry.selection_present():
            entry.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    entry.insert("insert", ch)


def backspace_in(entry) -> None:
    """Delete the selection, or else the character before the cursor."""
    try:
        if entry.selection_present():
            entry.delete("sel.first", "sel.last")
            return
    except tk.TclError:
        pass
    pos = entry.index("insert")
    if pos > 0:
        entry.delete(pos - 1)


class KeyboardPanel(tk.Frame):
    """The key strip. Clicking a key types into `entry`; the box keeps the keyboard focus."""

    COLUMNS = 14            # keys per row before wrapping to the next row

    def __init__(self, parent, entry, theme: dict, language: str = DEFAULT_LANGUAGE,
                 on_typed=None, on_language=None):
        super().__init__(parent)
        self.entry = entry
        self.theme = theme
        self.on_typed = on_typed              # called after every key (typing indicator, @-popup)
        self.on_language = on_language        # called with the new code when the menu changes
        self.shift = False                    # one-shot: applies to the next key only
        self.caps = False                     # stays on until switched off
        self.code = language if language in LAYOUTS else DEFAULT_LANGUAGE
        self._key_buttons: list[tuple[tk.Button, object]] = []

        self.top = tk.Frame(self)
        self.top.pack(fill="x", pady=(4, 2))
        self._names = layout_names()
        self.menu = ttk.Combobox(self.top, state="readonly", width=14, takefocus=0,
                                 values=[n for _c, n in self._names])
        self.menu.set(LAYOUTS[self.code][0])
        self.menu.pack(side="left", padx=(2, 6))
        self.menu.bind("<<ComboboxSelected>>", self._menu_changed)

        self.shift_btn = self._tool_button("⇧ Shift", self._toggle_shift)
        self.caps_btn = self._tool_button("Caps", self._toggle_caps)
        self.space_btn = self._tool_button("Space", lambda: self._type(" "))
        self.back_btn = self._tool_button("⌫", self._backspace)
        for b in (self.shift_btn, self.caps_btn, self.back_btn):
            b.pack(side="left", padx=2)
        self.space_btn.pack(side="left", padx=2, fill="x", expand=True)

        self.grid_frame = tk.Frame(self)
        self.grid_frame.pack(anchor="w", padx=2, pady=(0, 4))
        self._build_keys()
        self.apply_theme(theme)

    # ---- building ----------------------------------------------------------
    def _tool_button(self, text, command):
        return tk.Button(self.top, text=text, command=command, takefocus=0, relief="flat",
                         bd=0, padx=10, pady=3, cursor="hand2")

    def _build_keys(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self._key_buttons = []
        keys = LAYOUTS[self.code][1]
        for i, key in enumerate(keys):
            btn = tk.Button(self.grid_frame, width=3, takefocus=0, relief="flat", bd=0, pady=4,
                            cursor="hand2", command=lambda k=key: self._key_pressed(k))
            btn.grid(row=i // self.COLUMNS, column=i % self.COLUMNS, padx=1, pady=1)
            self._key_buttons.append((btn, key))
        self._refresh_labels()
        self._style_keys()

    def _refresh_labels(self):
        upper = self.shift != self.caps
        chars = key_chars([k for _b, k in self._key_buttons], upper)
        for (btn, _key), ch in zip(self._key_buttons, chars):
            btn.configure(text=ch)

    # ---- theming -----------------------------------------------------------
    def apply_theme(self, theme: dict):
        self.theme = theme
        fam, size = theme["font"], theme["font_size"]
        self.configure(bg=theme["window"])
        self.top.configure(bg=theme["window"])
        self.grid_frame.configure(bg=theme["window"])
        for b in (self.space_btn, self.back_btn):
            b.configure(bg=theme["header_btn"], fg="white", activebackground=theme["accent"],
                        activeforeground=theme["accent_text"],
                        font=(fam, max(8, size - 1)))
        self._style_modifiers()
        self._style_keys()

    def _style_keys(self):
        t = self.theme
        for btn, _key in self._key_buttons:
            btn.configure(bg=t["input_bg"], fg=t["input_fg"], activebackground=t["accent"],
                          activeforeground=t["accent_text"],
                          font=(t["font"], t["font_size"] + 2))

    def _style_modifiers(self):
        t = self.theme
        for btn, on in ((self.shift_btn, self.shift), (self.caps_btn, self.caps)):
            btn.configure(bg=t["accent"] if on else t["header_btn"],
                          fg=t["accent_text"] if on else "white",
                          activebackground=t["accent"], activeforeground="white",
                          font=(t["font"], max(8, t["font_size"] - 1)))

    def _refocus(self):
        """Keep the cursor in the message box. focus_force (not focus_set) because the keyboard may be
        its own little window, and then the message box has to take the focus back from it."""
        try:
            self.entry.focus_force()
        except tk.TclError:
            pass

    # ---- behavior ----------------------------------------------------------
    def _menu_changed(self, _event=None):
        name = self.menu.get()
        for code, n in self._names:
            if n == name:
                self.set_language(code)
                break
        self._refocus()

    def set_language(self, code: str):
        if code not in LAYOUTS:
            return
        self.code = code
        self.menu.set(LAYOUTS[code][0])
        self._build_keys()
        if self.on_language:
            self.on_language(code)

    def _toggle_shift(self):
        self.shift = not self.shift
        self._after_modifier_change()

    def _toggle_caps(self):
        self.caps = not self.caps
        self._after_modifier_change()

    def _after_modifier_change(self):
        self._style_modifiers()
        self._refresh_labels()
        self._refocus()

    def _key_pressed(self, key):
        upper = self.shift != self.caps
        ch = key_chars([key], upper)[0]
        self._type(ch)
        if self.shift:                       # Shift is for one letter only
            self.shift = False
            self._style_modifiers()
            self._refresh_labels()

    def _type(self, ch: str):
        type_into(self.entry, ch)
        self._refocus()
        if self.on_typed:
            self.on_typed()

    def _backspace(self):
        backspace_in(self.entry)
        self._refocus()
        if self.on_typed:
            self.on_typed()
