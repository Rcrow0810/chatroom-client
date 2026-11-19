# ai_friend_window.py
# ---------------------------------------------------------
# AI FRIEND: a private chat with an AI you customize (name, gender, personality).
#
# This window only DRAWS things and sends small requests. The AI itself runs on the chat
# server (see ai_friend.py there); nothing in here talks to an AI directly.
#
# Two screens inside one window:
#   * the setup form (first time, or when you press "Customize")
#   * the chat
# ---------------------------------------------------------

import tkinter as tk

import protocol as proto
from popup_kit import PillButton, RoundEntry, Themer, add_header, messagebox

PRESETS = [
    ("😎 Chill", "laid-back, relaxed and easy to talk to"),
    ("😂 Funny", "playful and witty, loves jokes and banter"),
    ("🤗 Supportive", "warm, encouraging and a great listener"),
    ("😏 Sarcastic", "dry and sarcastic, teasing but never mean"),
    ("🤓 Nerdy", "curious and nerdy, loves explaining cool facts"),
    ("🔥 Hype man", "super energetic, always cheering you on"),
]
GENDERS = (("He / him", "he"), ("She / her", "she"), ("They / them", "they"))
PRONOUNS = {"he": "he/him", "she": "she/her", "they": "they/them"}
NAME_MAX, PERSONALITY_MAX = 24, 300


class AIFriendWindow(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        t = owner.theme
        self.title("AI Friend")
        self.geometry("560x680")
        self.minsize(480, 560)
        self.configure(bg=t["window"])
        self.transient(owner)

        self.persona: dict | None = None
        self.waiting = False                 # True while we're waiting for the AI's answer
        self._wait_job = None
        self._editing = False
        self._remaining = None
        self._offline = ""                   # why the AI engine is unavailable (empty = fine)
        self._screen = "loading"             # "loading" | "setup" | "chat"

        add_header(self, t, "AI Friend", "A private chat, just you and your AI", height=54)
        self.body = tk.Frame(self, bg=t["window"])
        self.body.pack(fill="both", expand=True, padx=22, pady=(14, 16))

        self.loading = self._label(self.body, "Loading…", muted=True)
        self.loading.pack(pady=40)
        self._build_setup(t)
        self._build_chat(t)
        self._themer = Themer(self, lambda: self.owner.theme)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.owner.send_json({"type": proto.AI_GET})

    # ── small helpers ──────────────────────────────────────────────
    def _label(self, parent, text="", bold=False, size_delta=0, muted=False, **kw):
        t = self.owner.theme
        lbl = tk.Label(parent, text=text, bg=t["window"], fg=t["muted"] if muted else t["text"],
                       font=(t["font"], t["font_size"] + size_delta, "bold" if bold else "normal"), **kw)
        lbl._pk_role = "muted" if muted else "text"
        return lbl

    def _button(self, parent, text, command, style="soft"):
        return PillButton(parent, text, command, t=self.owner.theme, style=style)

    # ── layout: setup form ─────────────────────────────────────────
    def _build_setup(self, t):
        f = self.setup = tk.Frame(self.body, bg=t["window"])
        self.setup_title = self._label(f, "Meet your AI friend", bold=True, size_delta=4, anchor="w")
        self.setup_title.pack(fill="x")
        self._label(f, "Pick a name and a personality. You can change them any time.", muted=True,
                    anchor="w", justify="left", wraplength=480).pack(fill="x", pady=(2, 12))

        self._label(f, "Name", bold=True, anchor="w").pack(fill="x")
        self.name_entry = RoundEntry(f, t, height=40)
        self.name_entry.pack(fill="x", pady=(4, 12))

        self._label(f, "Pronouns", bold=True, anchor="w").pack(fill="x")
        row = tk.Frame(f, bg=t["window"])
        row.pack(fill="x", pady=(4, 12))
        self.gender_var = tk.StringVar(value="they")
        self._radios = []
        for text, key in GENDERS:
            rb = tk.Radiobutton(row, text=text, value=key, variable=self.gender_var, bd=0, highlightthickness=0,
                                cursor="hand2", font=(t["font"], t["font_size"]))
            rb._pk_skip = True               # recolored by retheme(), not by the generic Themer
            rb.pack(side="left", padx=(0, 16))
            self._radios.append(rb)

        self._label(f, "Personality", bold=True, anchor="w").pack(fill="x")
        presets = tk.Frame(f, bg=t["window"])
        presets.pack(fill="x", pady=(4, 6))
        for i, (label, text) in enumerate(PRESETS):
            b = self._button(presets, label, lambda s=text: self.personality_entry.set(s))
            b.grid(row=i // 3, column=i % 3, padx=(0, 8), pady=(0, 8), sticky="w")
        self.personality_entry = RoundEntry(f, t, height=40)
        self.personality_entry.pack(fill="x", pady=(0, 4))
        self._label(f, "Tap a style, or write your own. For example: \"talks like a pirate and loves basketball\"",
                    muted=True, size_delta=-1, anchor="w", justify="left", wraplength=480).pack(fill="x")

        self.setup_error = self._label(f, "", size_delta=-1, anchor="w", justify="left", wraplength=480)
        self.setup_error._pk_skip = True
        self.setup_error.configure(fg="#d9534f")
        self.setup_error.pack(fill="x", pady=(8, 0))

        buttons = tk.Frame(f, bg=t["window"])
        buttons.pack(fill="x", pady=(8, 0))
        self.save_button = self._button(buttons, "Save", self._save, style="primary")
        self.save_button.pack(side="left")
        self.cancel_button = self._button(buttons, "Cancel", self._show_chat, style="ghost")
        self._label(f, "Your AI friend is an AI, not a person. It runs on the chat server's computer, so the "
                       "server owner can read these chats (unlike private messages). Don't share passwords or "
                       "personal secrets.", muted=True, size_delta=-1, anchor="w", justify="left",
                    wraplength=480).pack(fill="x", pady=(14, 0))
        self.name_entry.bind("<Return>", lambda e: self._save())
        self.personality_entry.bind("<Return>", lambda e: self._save())

    # ── layout: the chat ───────────────────────────────────────────
    def _build_chat(self, t):
        f = self.chat = tk.Frame(self.body, bg=t["window"])
        top = tk.Frame(f, bg=t["window"])
        top.pack(fill="x")
        self.friend_label = self._label(top, "", bold=True, size_delta=3, anchor="w")
        self.friend_label.pack(side="left")
        self.clear_button = self._button(top, "Clear chat", self._clear, style="ghost")
        self.clear_button.pack(side="right")
        self.customize_button = self._button(top, "Customize", self._customize)
        self.customize_button.pack(side="right", padx=(0, 6))
        self.sub_label = self._label(f, "", muted=True, size_delta=-1, anchor="w")
        self.sub_label.pack(fill="x", pady=(0, 8))

        box = tk.Frame(f, bg=t["window"])
        box.pack(fill="both", expand=True)
        self.log = tk.Text(box, wrap="word", state="disabled", relief="flat", bd=0, padx=12, pady=10,
                           cursor="arrow", highlightthickness=1, font=(t["font"], t["font_size"]))
        self.log._pk_skip = True
        bar = tk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        self.status = self._label(f, "", muted=True, size_delta=-1, anchor="w", justify="left", wraplength=500)
        self.status.pack(fill="x", pady=(6, 4))
        row = tk.Frame(f, bg=t["window"])
        row.pack(fill="x")
        self.entry = RoundEntry(row, t, height=42)
        self.entry.pack(side="left", fill="x", expand=True)
        self.send_button = self._button(row, "Send", self._send, style="primary")
        self.send_button.pack(side="left", padx=(8, 0))
        self.entry.bind("<Return>", lambda e: self._send())
        self._style_log()

    def _style_log(self):
        t = self.owner.theme
        fam, size = t["font"], t["font_size"]
        self.log.configure(bg=t["input_bg"], fg=t["input_fg"], highlightbackground=t["muted"],
                           highlightcolor=t["accent"], insertbackground=t["input_fg"])
        self.log.tag_configure("ai_who", foreground=t["accent"], font=(fam, size, "bold"), spacing1=8)
        self.log.tag_configure("you_who", foreground=t["muted"], font=(fam, size, "bold"), spacing1=8)
        self.log.tag_configure("body", lmargin1=10, lmargin2=10, spacing3=2)
        self.log.tag_configure("note", foreground=t["muted"], lmargin1=10, lmargin2=10, spacing1=6)
        self.log.tag_configure("err", foreground="#d9534f", lmargin1=10, lmargin2=10, spacing1=6)
        for rb in self._radios:
            rb.configure(bg=t["window"], fg=t["text"], selectcolor=t["input_bg"], activebackground=t["window"],
                         activeforeground=t["text"], font=(fam, size))

    def retheme(self):
        t = self.owner.theme
        self.configure(bg=t["window"])
        self._themer.apply()
        self._style_log()

    # ── switching screens ──────────────────────────────────────────
    def _show(self, which):
        for frame in (self.loading, self.setup, self.chat):
            frame.pack_forget()
        self._screen = {id(self.loading): "loading", id(self.setup): "setup", id(self.chat): "chat"}[id(which)]
        if which is self.loading:
            which.pack(pady=40)
        else:
            which.pack(fill="both", expand=True)

    def _show_setup(self, first: bool):
        self._editing = not first
        p = self.persona or {}
        self.setup_title.config(text="Meet your AI friend" if first else "Customize your AI friend")
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, p.get("name", ""))
        self.gender_var.set(p.get("gender", "they"))
        self.personality_entry.delete(0, "end")
        self.personality_entry.insert(0, p.get("personality", ""))
        self.setup_error.config(text="")
        if first:
            self.cancel_button.pack_forget()
        else:
            self.cancel_button.pack(side="left", padx=(8, 0))
        self._show(self.setup)
        self.name_entry.focus_set()

    def _show_chat(self):
        self._show(self.chat)
        self.entry.focus_set()

    # ── what the server told us ────────────────────────────────────
    def set_state(self, state: dict):
        self.persona = state.get("persona")
        self._remaining = state.get("remaining")
        self._offline = "" if state.get("available", True) else (state.get("reason") or "The AI engine is off.")
        self._end_wait()
        if self.persona is None:
            self._show_setup(first=True)
            return
        self.friend_label.config(text=f"🤖 {self.persona['name']}")
        self.sub_label.config(text=PRONOUNS.get(self.persona["gender"], "they/them") +
                                   (" · " + self.persona["personality"] if self.persona["personality"] else ""))
        self._render(state.get("history") or [])
        self._refresh_status()
        if self._screen != "chat":
            self._show_chat()

    def on_reply(self, msg: dict):
        self._end_wait()
        if self._screen == "loading":                        # e.g. "AI Friend isn't available on this server."
            self.loading.config(text=msg.get("text", "AI Friend isn't available right now."))
            return
        if msg.get("remaining") is not None:
            self._remaining = msg["remaining"]
        if msg.get("ok"):
            self._append(self.persona["name"] if self.persona else "AI", msg.get("text", ""), "ai_who")
        else:
            if self._screen == "setup":                      # an error while saving the setup form
                self.setup_error.config(text=msg.get("text", ""))
                return
            self._note(msg.get("text", "Something went wrong."), "err")
        self._refresh_status()

    # ── drawing ────────────────────────────────────────────────────
    def _render(self, history: list):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        if not history:
            self._note(f"Say hi to {self.persona['name']}! Ask anything, or just chat.", "note")
        for h in history:
            is_ai = h.get("role") == "assistant"
            self._append(self.persona["name"] if is_ai else "You", h.get("content", ""),
                         "ai_who" if is_ai else "you_who")

    def _append(self, who: str, text: str, who_tag: str):
        self.log.configure(state="normal")
        self.log.insert("end", who + "\n", who_tag)
        self.log.insert("end", text + "\n", "body")
        self.log.configure(state="disabled")
        self.log.see("end")

    def _note(self, text: str, tag: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.configure(state="disabled")
        self.log.see("end")

    def _refresh_status(self):
        if self.waiting:
            self.status.config(text=f"{self.persona['name']} is typing…" if self.persona else "…",
                               fg=self.owner.theme["muted"])
        elif self._offline:
            self.status.config(text=f"Your AI friend is offline right now. ({self._offline})", fg="#d9534f")
        elif self._remaining is not None:
            self.status.config(text=f"{self._remaining} messages left today", fg=self.owner.theme["muted"])
        else:
            self.status.config(text="")

    # ── what the person does ───────────────────────────────────────
    def _send(self):
        if self.waiting or self.persona is None:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append("You", text, "you_who")
        self.waiting = True
        self.send_button.config(state="disabled")
        self._refresh_status()
        self.owner.send_json({"type": proto.AI_SEND, "text": text})
        # if no answer ever comes (connection trouble) let them try again
        self._wait_job = self.after(170000, self._timeout)

    def _timeout(self):
        self._wait_job = None
        if self.waiting:
            self._end_wait()
            self._note("No answer came back. Try again.", "err")
            self._refresh_status()

    def _end_wait(self):
        self.waiting = False
        if self._wait_job is not None:
            try:
                self.after_cancel(self._wait_job)
            except tk.TclError:
                pass
            self._wait_job = None
        try:
            self.send_button.config(state="normal")
        except tk.TclError:
            pass

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            self.setup_error.config(text="Give your AI friend a name.")
            return
        self.setup_error.config(text="")
        self.owner.send_json({"type": proto.AI_SAVE, "name": name[:NAME_MAX], "gender": self.gender_var.get(),
                              "personality": self.personality_entry.get().strip()[:PERSONALITY_MAX]})

    def _customize(self):
        self._show_setup(first=False)

    def _clear(self):
        if messagebox.askyesno("Clear chat", "Delete your whole chat with your AI friend? "
                                             "Their name and personality stay.", parent=self):
            self.owner.send_json({"type": proto.AI_RESET})

    def close(self):
        self._end_wait()
        self.owner.ai_window = None
        self.destroy()
