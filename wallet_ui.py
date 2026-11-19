# wallet_ui.py  --  CLIENT SIDE: the Wallet window and the "you got paid" popup.
# ---------------------------------------------------------
# This file only DRAWS things and sends requests.  All the money rules live on the server
# (wallet.py there), so nothing in here can create, change or move money by itself.
# Amounts arrive from the server in cents; fmt() turns 1250 into "12.50".
# ---------------------------------------------------------

import tkinter as tk
import uuid
from datetime import datetime
from tkinter import ttk

import protocol as proto

GOOD = "#2e9e5b"
BAD = "#d9534f"


def fmt(cents) -> str:
    cents = int(cents or 0)
    return f"{cents // 100:,}.{cents % 100:02d}"


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d  %I:%M %p").replace(" 0", " ")
    except (ValueError, TypeError):
        return ""


class WalletWindow(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.t = t = owner.theme
        self.title("Wallet")
        self.configure(bg=t["window"])
        self.geometry("460x640")
        self.minsize(420, 560)
        self.transient(owner)

        fam, size = t["font"], t["font_size"]
        self._pending_id = None            # same id is reused until the server answers, so a retry can't pay twice
        self._unlock_job = None
        self._can_claim = False

        pad = dict(padx=16)
        tk.Label(self, text="WALLET  ·  play money", bg=t["window"], fg=t["muted"],
                 font=(fam, max(8, size - 2), "bold")).pack(anchor="w", pady=(14, 0), **pad)
        self.balance_label = tk.Label(self, text="🪙 …", bg=t["window"], fg=t["text"],
                                      font=(fam, size + 16, "bold"))
        self.balance_label.pack(anchor="w", **pad)

        self.claim_btn = tk.Button(self, text="🎁  Claim your free starter money", command=self._claim,
                                   relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                                   bg=t["accent"], fg=t["accent_text"], activebackground=t["accent"],
                                   activeforeground=t["accent_text"], font=(fam, size, "bold"))

        # ---- send form ----
        self.form = tk.Frame(self, bg=t["window"])
        self.form.pack(fill="x", pady=(12, 0), **pad)
        tk.Label(self.form, text="Send money", bg=t["window"], fg=t["text"],
                 font=(fam, size + 1, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.to_var, self.amount_var, self.note_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        rows = (("To", self.to_var), ("Amount", self.amount_var), ("Note", self.note_var))
        for i, (label, var) in enumerate(rows, start=1):
            tk.Label(self.form, text=label, bg=t["window"], fg=t["muted"], font=(fam, size),
                     width=7, anchor="w").grid(row=i, column=0, sticky="w", pady=3)
            if label == "To":
                self.to_box = ttk.Combobox(self.form, textvariable=var, font=(fam, size))
                self.to_box.grid(row=i, column=1, sticky="ew", pady=3)
            else:
                e = tk.Entry(self.form, textvariable=var, font=(fam, size), bg=t["input_bg"], fg=t["input_fg"],
                             insertbackground=t["input_fg"], relief="flat", highlightthickness=1,
                             highlightbackground=t["muted"], highlightcolor=t["accent"])
                e.grid(row=i, column=1, sticky="ew", pady=3, ipady=3)
                if label == "Amount":
                    self.amount_entry = e
                else:
                    self.note_entry = e
                    var.trace_add("write", lambda *a: len(self.note_var.get()) > 100 and self.note_var.set(self.note_var.get()[:100]))
                e.bind("<Return>", lambda ev: self._send())
        self.form.columnconfigure(1, weight=1)
        self.send_btn = tk.Button(self.form, text="Send  ➤", command=self._send, relief="flat", bd=0,
                                  padx=14, pady=6, cursor="hand2", bg=t["accent"], fg=t["accent_text"],
                                  activebackground=t["accent"], activeforeground=t["accent_text"],
                                  font=(fam, size, "bold"))
        self.send_btn.grid(row=4, column=1, sticky="e", pady=(8, 0))

        self.status = tk.Label(self, text="", bg=t["window"], fg=t["muted"], font=(fam, size),
                               anchor="w", justify="left", wraplength=400)
        self.status.pack(fill="x", pady=(6, 0), **pad)

        # ---- history ----
        tk.Label(self, text="History", bg=t["window"], fg=t["text"],
                 font=(fam, size + 1, "bold")).pack(anchor="w", pady=(10, 4), **pad)
        style = ttk.Style(self)
        style.configure("Wallet.Treeview", background=t["input_bg"], fieldbackground=t["input_bg"],
                        foreground=t["input_fg"], rowheight=int(size * 2.2), borderwidth=0, font=(fam, size))
        style.configure("Wallet.Treeview.Heading", font=(fam, size, "bold"))
        holder = tk.Frame(self, bg=t["window"])
        holder.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.tree = ttk.Treeview(holder, style="Wallet.Treeview", columns=("who", "amount", "when"),
                                 show="headings", selectmode="browse")
        for col, text, width, anchor in (("who", "With", 190, "w"), ("amount", "Amount", 90, "e"),
                                         ("when", "When", 110, "e")):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "who"))
        bar = ttk.Scrollbar(holder, command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.tag_configure("in", foreground=GOOD)
        self.tree.tag_configure("out", foreground=BAD)
        self.tree.bind("<<TreeviewSelect>>", self._show_note)

        self._notes = {}
        self.bind("<Escape>", lambda e: self.destroy())
        self.refresh_people()

    # ---- what the server told us ---------------------------------------------------------
    def update_snapshot(self, snap: dict):
        self.balance_label.config(text=f"🪙 {fmt(snap.get('balance_cents'))}")
        self._can_claim = bool(snap.get("can_claim"))
        if self._can_claim:
            self.claim_btn.pack(anchor="w", padx=16, pady=(8, 0), before=self.form)
        else:
            self.claim_btn.pack_forget()
        self.tree.delete(*self.tree.get_children())
        self._notes.clear()
        for h in snap.get("history", []):
            incoming = h.get("direction") == "in"
            who = "🎁 Starter money" if h.get("kind") == "grant" else (
                ("from " if incoming else "to ") + str(h.get("other", "")))
            sign = "+" if incoming else "−"
            item = self.tree.insert("", "end", values=(who, f"{sign}{fmt(h.get('amount_cents'))}", _when(h.get("time"))),
                                    tags=("in" if incoming else "out",))
            if h.get("note"):
                self._notes[item] = h["note"]
        self.refresh_people()

    def show_result(self, res: dict):
        if res.get("action") == "send":
            self._pending_id = None
            self._unlock_send()
            if res.get("ok"):
                self.amount_var.set("")
                self.note_var.set("")
        ok = bool(res.get("ok"))
        self.status.config(text=res.get("message", ""), fg=GOOD if ok else BAD)

    def refresh_people(self):
        me = self.owner.username
        self.to_box["values"] = [u for u in getattr(self.owner, "online_users", []) if u != me]

    # ---- what the person does ------------------------------------------------------------
    def _claim(self):
        self.owner.send_json({"type": proto.WALLET_CLAIM})

    def _send(self):
        if str(self.send_btn["state"]) == "disabled":
            return
        to, amount = self.to_var.get().strip(), self.amount_var.get().strip()
        if not to:
            self.status.config(text="Choose who to send money to.", fg=BAD)
            return
        if not amount:
            self.status.config(text="Type an amount, like 5 or 12.50.", fg=BAD)
            return
        if self._pending_id is None:
            self._pending_id = uuid.uuid4().hex
        self.send_btn.config(state="disabled")
        self.status.config(text="Sending…", fg=self.t["muted"])
        self.owner.send_json({"type": proto.WALLET_SEND, "to": to, "amount": amount,
                              "note": self.note_var.get().strip(), "request_id": self._pending_id})
        # if no answer ever comes (connection hiccup) let them try again; the SAME id is reused, so it can't pay twice
        self._unlock_job = self.after(12000, self._unlock_send)

    def _unlock_send(self):
        if self._unlock_job is not None:
            try:
                self.after_cancel(self._unlock_job)
            except tk.TclError:
                pass
            self._unlock_job = None
        try:
            self.send_btn.config(state="normal")
        except tk.TclError:
            pass

    def _show_note(self, event=None):
        sel = self.tree.selection()
        if sel and sel[0] in self._notes:
            self.status.config(text=f"Note: {self._notes[sel[0]]}", fg=self.t["muted"])


def show_toast(owner, text: str, on_click=None, seconds: int = 7):
    """A small 'you got paid' popup in the corner of the chat window. Click it to open the wallet."""
    t = owner.theme
    try:
        toast = tk.Toplevel(owner)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        label = tk.Label(toast, text=text, bg=t["accent"], fg=t["accent_text"], padx=18, pady=12,
                         font=(t["font"], t["font_size"], "bold"), cursor="hand2", justify="left")
        label.pack()
        owner.update_idletasks()
        toast.update_idletasks()
        x = owner.winfo_rootx() + owner.winfo_width() - toast.winfo_reqwidth() - 24
        y = owner.winfo_rooty() + owner.winfo_height() - toast.winfo_reqheight() - 48
        toast.geometry(f"+{max(0, x)}+{max(0, y)}")

        def close(_e=None):
            try:
                toast.destroy()
            except tk.TclError:
                pass

        def clicked(_e=None):
            close()
            if on_click:
                on_click()
        label.bind("<Button-1>", clicked)
        toast.after(seconds * 1000, close)
    except tk.TclError:
        pass
