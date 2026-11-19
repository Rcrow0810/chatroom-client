"""
Forgot-password dialog (opened from the login screen).

  1. type your username      -> your 3 security questions appear
  2. answer all 3 + choose a new password -> Reset password

All the real checking (lockout, answers, password rules) happens in
account_api.reset_password_with_answers; this file is only the screen.
"""
import tkinter as tk

import account_api
import popup_kit
from password_policy import check_password_strength, strength_label
from popup_kit import PillButton, RoundEntry, Themer, add_header, messagebox


class RecoveryDialog(tk.Toplevel):
    def __init__(self, master, prefill: str = "", on_done=None):
        super().__init__(master)
        t = self.t = popup_kit.current()          # the login screen's look
        self.title("Forgot password")
        self.resizable(False, False)
        self.transient(master)
        self.configure(bg=t["window"])
        self.on_done = on_done
        self.username = ""
        self.answer_entries: list[RoundEntry] = []
        add_header(self, t, "Forgot password", "Reset it with your security questions", height=58)

        body = tk.Frame(self, bg=t["window"])
        body.pack(fill="both", expand=True, padx=26, pady=(16, 18))
        self.body = body
        self._label(body, "This only works if you set up security questions in Settings\n"
                          "before you forgot your password.", muted=True, small=True, justify="left").pack(anchor="w")

        self._label(body, "Username", muted=True, small=True).pack(anchor="w", pady=(14, 2))
        self.username_entry = RoundEntry(body, t, width=360, height=42)
        self.username_entry.pack(fill="x")
        self.username_entry.insert(0, prefill)
        self.username_entry.bind("<Return>", lambda e: self._load_questions())
        self.continue_btn = PillButton(body, "Continue", self._load_questions, t=t, width=360, height=42)
        self.continue_btn.pack(pady=(12, 4))

        self.questions_frame = tk.Frame(body, bg=t["window"])      # filled in once a username is chosen
        self.questions_frame.pack(fill="x")

        self._themer = Themer(self, lambda: self.t)
        popup_kit.center_on(self, master)
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.username_entry.focus_set()

    def _label(self, parent, text, muted=False, small=False, **kw):
        t = self.t
        lbl = tk.Label(parent, text=text, bg=t["window"], fg=t["muted"] if muted else t["text"],
                       font=(t["font"], t["font_size"] - 1 if small else t["font_size"], "bold" if small and muted else "normal"),
                       anchor="w", **kw)
        lbl._pk_role = "muted" if muted else "text"
        return lbl

    # ---- step 1 -> 2 -------------------------------------------------------
    def _load_questions(self):
        username = self.username_entry.get().strip()
        if not username:
            messagebox.showwarning("Username needed", "Type your username first.", parent=self)
            return
        try:
            questions = account_api.get_recovery_questions(username)
        except Exception as e:
            messagebox.showerror("Couldn't load questions",
                                 f"Couldn't reach the server.\n({e})", parent=self)
            return
        self.username = username
        self.username_entry.configure(state="disabled")
        self.continue_btn.configure(state="disabled")
        self._build_questions(questions)

    def _start_over(self):
        for child in self.questions_frame.winfo_children():
            child.destroy()
        self.username_entry.configure(state="normal")
        self.continue_btn.configure(state="normal")
        self.username_entry.focus_set()

    def _build_questions(self, questions):
        frame, t = self.questions_frame, self.t
        for child in frame.winfo_children():
            child.destroy()
        self.answer_entries = []

        for i, question in enumerate(questions, start=1):
            self._label(frame, f"{i}. {question}", wraplength=360, justify="left").pack(anchor="w", pady=(10, 3))
            entry = RoundEntry(frame, t, width=360, height=40)
            entry.pack(fill="x")
            self.answer_entries.append(entry)

        self._label(frame, "New password", muted=True, small=True).pack(anchor="w", pady=(16, 3))
        self.new_pw_entry = RoundEntry(frame, t, width=360, height=40, show="*")
        self.new_pw_entry.pack(fill="x")
        self.new_pw_entry.bind("<KeyRelease>", self._update_strength)
        self.strength_lbl = tk.Label(frame, text="", bg=t["window"], font=(t["font"], t["font_size"] - 1, "bold"))
        self.strength_lbl.pack(anchor="w", pady=(4, 0))
        self.requirements_lbl = tk.Label(frame, text="", bg=t["window"], fg=t["muted"],
                                         font=(t["font"], max(7, t["font_size"] - 2)), justify="left")
        self.requirements_lbl._pk_role = "muted"
        self.requirements_lbl.pack(anchor="w")
        self._label(frame, "Confirm new password", muted=True, small=True).pack(anchor="w", pady=(8, 3))
        self.confirm_entry = RoundEntry(frame, t, width=360, height=40, show="*")
        self.confirm_entry.pack(fill="x")
        self.show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="Show passwords", variable=self.show_var, command=self._toggle_show,
                       font=(t["font"], t["font_size"] - 1)).pack(anchor="w", pady=(6, 0))

        buttons = tk.Frame(frame, bg=t["window"])
        buttons.pack(pady=(14, 0))
        PillButton(buttons, "Reset password", self._reset, t=t, width=170, height=42).pack(side="left", padx=4)
        PillButton(buttons, "Start over", self._start_over, t=t, style="soft", width=120, height=42).pack(side="left", padx=4)
        self._themer.apply()
        popup_kit.center_on(self, self.master)
        self.answer_entries[0].focus_set()

    def _toggle_show(self):
        mark = "" if self.show_var.get() else "*"
        self.new_pw_entry.configure(show=mark)
        self.confirm_entry.configure(show=mark)

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

    # ---- the actual reset ---------------------------------------------------
    def _reset(self):
        answers = [e.get() for e in self.answer_entries]
        new = self.new_pw_entry.get()
        if new != self.confirm_entry.get():
            messagebox.showerror("Mismatch", "The new passwords don't match.", parent=self)
            return
        ok, message = account_api.reset_password_with_answers(self.username, answers, new)
        if not ok:
            messagebox.showerror("Couldn't reset password", message, parent=self)
            return
        messagebox.showinfo("Password reset",
                            "Your password was changed.\nYou can log in with it now.", parent=self)
        username, callback = self.username, self.on_done
        self.destroy()
        if callback:
            callback(username)
