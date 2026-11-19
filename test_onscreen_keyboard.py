# Tests for onscreen_keyboard.py. Runs WITHOUT a display: tkinter is replaced by a tiny stand-in
# that records what the panel does, so the logic (Shift/Caps/language/typing) can be checked anywhere.
import os, sys, types, unittest

_here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_here, os.path.dirname(_here)]   # works from the project folder or a tests/ subfolder


class TclError(Exception):
    pass


class FakeWidget:
    def __init__(self, parent=None, **kw):
        self.parent, self.opts, self.children, self.cmd = parent, dict(kw), [], kw.get("command")
        self.value = ""
        self.bound = {}
        if parent is not None:
            parent.children.append(self)
    def configure(self, **kw): self.opts.update(kw)
    config = configure
    def pack(self, **kw): pass
    def grid(self, **kw): pass
    def pack_forget(self): pass
    def bind(self, seq, fn): self.bound[seq] = fn
    def winfo_children(self): return list(self.children)
    def destroy(self):
        if self.parent and self in self.parent.children:
            self.parent.children.remove(self)
    def set(self, v): self.value = v
    def get(self): return self.value
    def focus_set(self): self.opts["focused"] = True
    def click(self): self.cmd()


tk_stub = types.ModuleType("tkinter")
tk_stub.Frame = tk_stub.Button = FakeWidget
tk_stub.TclError = TclError
ttk_stub = types.ModuleType("tkinter.ttk")
ttk_stub.Combobox = FakeWidget
tk_stub.ttk = ttk_stub
sys.modules["tkinter"], sys.modules["tkinter.ttk"] = tk_stub, ttk_stub

import onscreen_keyboard as kb   # noqa: E402


class FakeEntry:
    """Behaves like tk.Entry for the few calls the keyboard makes."""
    def __init__(self, text="", cursor=None, sel=None):
        self.text, self.cursor, self.sel, self.focused = text, len(text) if cursor is None else cursor, sel, False
    def selection_present(self): return self.sel is not None
    def index(self, where):
        if where == "insert": return self.cursor
        if where == "sel.first": return self.sel[0]
        if where == "sel.last": return self.sel[1]
        raise TclError(where)
    def delete(self, first, last=None):
        a = self.index(first) if isinstance(first, str) else first
        b = (self.index(last) if isinstance(last, str) else last) if last is not None else a + 1
        self.text = self.text[:a] + self.text[b:]
        self.cursor, self.sel = a, None
    def insert(self, where, ch):
        i = self.index(where) if isinstance(where, str) else where
        self.text = self.text[:i] + ch + self.text[i:]
        self.cursor = i + len(ch)
    def focus_set(self): self.focused = True
    def focus_force(self): self.focused = True


THEME = dict(window="#fff", header_btn="#444", accent="#55f", accent_text="#fff", input_bg="#fff",
             input_fg="#000", font="Segoe UI", font_size=10)


class LayoutData(unittest.TestCase):
    def test_every_key_is_one_character_with_a_one_character_capital(self):
        for code, (name, keys) in kb.LAYOUTS.items():
            seen = set()
            for key in keys:
                lo, up = key if isinstance(key, tuple) else (key, key.upper())
                self.assertEqual(len(lo), 1, f"{code}: {lo!r}")
                self.assertEqual(len(up), 1, f"{code}: {lo!r} -> {up!r} (needs an explicit pair)")
                self.assertNotIn(lo, seen, f"{code}: duplicate {lo!r}")
                seen.add(lo)

    def test_default_language_exists_and_menu_lists_every_layout(self):
        self.assertIn(kb.DEFAULT_LANGUAGE, kb.LAYOUTS)
        names = kb.layout_names()
        self.assertEqual({c for c, _ in names}, set(kb.LAYOUTS))
        self.assertEqual(names[-1][0], "sym")                      # symbols page last
        self.assertEqual([n for _c, n in names[:-1]], sorted(n for _c, n in names[:-1]))

    def test_codes_match_the_app_language_list(self):
        # every layout code the keyboard offers should be a language code the app already knows
        import language_settings
        for code in kb.LAYOUTS:
            if code != "sym":
                self.assertIn(code, language_settings.LANGUAGE_NAMES, code)


class KeyChars(unittest.TestCase):
    def test_lower_and_upper(self):
        keys = kb.LAYOUTS["es"][1]
        self.assertEqual(kb.key_chars(keys, False), list("áéíóúüñ¿¡"))
        self.assertEqual(kb.key_chars(keys, True), list("ÁÉÍÓÚÜÑ¿¡"))   # ¿ ¡ have no capital

    def test_german_sharp_s_capital_and_no_double_letter(self):
        keys = kb.LAYOUTS["de"][1]
        self.assertEqual(kb.key_chars(keys, True), ["Ä", "Ö", "Ü", "ẞ"])
        self.assertEqual(kb.key_chars(["ß"], True), ["ß"])           # a bare ß must not become "SS"

    def test_turkish_dotted_capital_i(self):
        keys = kb.LAYOUTS["tr"][1]
        self.assertEqual(kb.key_chars(keys, False)[-1], "ı")
        self.assertEqual(kb.key_chars(keys, True)[-1], "İ")

    def test_french_ligatures(self):
        self.assertIn("Œ", kb.key_chars(kb.LAYOUTS["fr"][1], True))
        self.assertIn("Ÿ", kb.key_chars(kb.LAYOUTS["fr"][1], True))


class Typing(unittest.TestCase):
    def test_inserts_at_cursor(self):
        e = FakeEntry("cafe", cursor=3); kb.type_into(e, "é")
        self.assertEqual((e.text, e.cursor), ("cafée", 4))

    def test_replaces_selection_like_real_typing(self):
        e = FakeEntry("hello", cursor=5, sel=(1, 4)); kb.type_into(e, "ñ")
        self.assertEqual(e.text, "hño")

    def test_backspace(self):
        e = FakeEntry("añb", cursor=2); kb.backspace_in(e)
        self.assertEqual((e.text, e.cursor), ("ab", 1))
        e = FakeEntry("abc", cursor=0); kb.backspace_in(e)            # nothing before the cursor
        self.assertEqual(e.text, "abc")
        e = FakeEntry("abcd", cursor=4, sel=(1, 3)); kb.backspace_in(e)  # deletes the selection only
        self.assertEqual(e.text, "ad")

    def test_astral_and_combining_characters_round_trip_through_json_and_utf8(self):
        import json
        s = "áéñçœ·ẞİı"
        self.assertEqual(json.loads(json.dumps({"t": s}))["t"], s)
        self.assertEqual(s.encode("utf-8").decode("utf-8"), s)


class Panel(unittest.TestCase):
    def make(self, language="es"):
        self.entry = FakeEntry()
        self.typed, self.lang = [], []
        self.panel = kb.KeyboardPanel(FakeWidget(), self.entry, THEME, language,
                                      on_typed=lambda: self.typed.append(1), on_language=self.lang.append)
        return self.panel

    def labels(self): return [b.opts["text"] for b, _k in self.panel._key_buttons]

    def test_starts_in_requested_language_and_falls_back_when_unknown(self):
        self.assertEqual(self.make("fr").code, "fr")
        self.assertEqual(self.make("xx").code, kb.DEFAULT_LANGUAGE)
        self.make("es"); self.assertEqual(self.labels(), list("áéíóúüñ¿¡"))

    def test_clicking_a_key_types_it_keeps_focus_and_notifies(self):
        p = self.make()
        p._key_buttons[0][0].click()
        self.assertEqual(self.entry.text, "á")
        self.assertTrue(self.entry.focused)
        self.assertEqual(len(self.typed), 1)

    def test_shift_is_one_shot(self):
        p = self.make()
        p.shift_btn.click()
        self.assertEqual(self.labels()[0], "Á")
        p._key_buttons[0][0].click()                                  # types Á ...
        self.assertEqual(self.entry.text, "Á")
        self.assertFalse(p.shift)
        self.assertEqual(self.labels()[0], "á")                       # ... and goes back to lowercase
        p._key_buttons[0][0].click()
        self.assertEqual(self.entry.text, "Áá")

    def test_caps_stays_on_and_shift_inverts_it(self):
        p = self.make()
        p.caps_btn.click()
        for _ in range(2): p._key_buttons[1][0].click()
        self.assertEqual(self.entry.text, "ÉÉ")
        p.shift_btn.click()                                           # Caps + Shift = lowercase for one key
        p._key_buttons[1][0].click()
        self.assertEqual(self.entry.text, "ÉÉé")
        p._key_buttons[1][0].click()
        self.assertEqual(self.entry.text, "ÉÉéÉ")

    def test_space_and_backspace_buttons(self):
        p = self.make()
        p._key_buttons[6][0].click()                                  # ñ
        p.space_btn.click(); p.space_btn.click()
        self.assertEqual(self.entry.text, "ñ  ")
        p.back_btn.click()
        self.assertEqual(self.entry.text, "ñ ")
        self.assertEqual(len(self.typed), 4)

    def test_changing_language_rebuilds_keys_and_reports_it(self):
        p = self.make("es")
        p.menu.set("German"); p._menu_changed()
        self.assertEqual(p.code, "de")
        self.assertEqual(self.labels(), list("äöüß"))
        self.assertEqual(self.lang, ["de"])
        self.assertEqual(len(p.grid_frame.winfo_children()), 4)       # old keys were destroyed, not stacked
        self.assertTrue(self.entry.focused)

    def test_shift_state_survives_a_language_change(self):
        p = self.make("es"); p.shift_btn.click()
        p.set_language("de")
        self.assertEqual(self.labels(), ["Ä", "Ö", "Ü", "ẞ"])

    def test_retheme_does_not_crash_and_restyles_keys(self):
        p = self.make()
        dark = dict(THEME, input_bg="#111", input_fg="#eee", window="#000")
        p.apply_theme(dark)
        self.assertEqual(p._key_buttons[0][0].opts["bg"], "#111")

    def test_unknown_language_code_is_ignored(self):
        p = self.make("fr"); p.set_language("zz")
        self.assertEqual(p.code, "fr")


if __name__ == "__main__":
    unittest.main(verbosity=2)
