# wallet_window.py
# ---------------------------------------------------------
# The payment screens:
#   WalletWindow   - your balance, payout setup, "request money" form, history
#   PaymentPrompt  - the pop-up when someone asks YOU for money
#
# These windows only DISPLAY what the server says and send small requests
# ("ask bob for 2500 cents", "pay request <id>"). The server and Stripe decide
# everything about money; nothing here can change an amount or a recipient
# after a request exists, and card details are only ever typed on Stripe's page.
# ---------------------------------------------------------

import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk

import popup_kit
import protocol as proto
from money import format_cents, parse_amount_to_cents
from popup_kit import PillButton, RoundEntry, Themer, add_header, fnt, messagebox
from ui_kit import mix_hex, photo, rounded_image

STATUS_TEXT = {
    "pending": "Waiting for answer",
    "awaiting_payment": "Paying…",
    "paid": "Paid",
    "declined": "Declined",
    "cancelled": "Cancelled",
    "expired": "Expired",
    "review": "Under review",
}


def local_time(iso: str | None) -> str:
    """The server sends UTC; show it in this computer's own time."""
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).astimezone()
        return when.strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return iso


def note_suffix(request: dict) -> str:
    return f' — "{request["note"]}"' if request.get("note") else ""


class _Hero(tk.Canvas):
    """The gradient banner with your balance on it (same colors as the chat's header)."""

    def __init__(self, parent, t: dict):
        super().__init__(parent, height=96, highlightthickness=0, bd=0, bg=t["window"])
        self.t = t
        self.balance, self.detail = "Loading…", ""
        self._cw, self._pic = 0, None
        tk.Canvas.bind(self, "<Configure>", self._configured)

    def restyle(self, t: dict):
        self.t = t
        self.configure(bg=t["window"])
        self._draw()

    def set(self, balance: str | None = None, detail: str | None = None):
        if balance is not None:
            self.balance = balance
        if detail is not None:
            self.detail = detail
        self._draw()

    def _configured(self, event):
        if event.width != self._cw:
            self._cw = event.width
            self._draw()

    def _draw(self):
        w, t = self._cw, self.t
        if w < 120:
            return
        self.delete("all")
        fg = t["accent_text"]
        top = self.create_text(26, 20, text=self.balance, anchor="nw", fill=fg, font=fnt(t, 9, True), width=w - 52)
        y = self.bbox(top)[3] + 4
        if self.detail:
            soft = self.create_text(26, y, text=self.detail, anchor="nw", fill=mix_hex(fg, t["accent"], .18),
                                    font=fnt(t, -1), width=w - 52)
            y = self.bbox(soft)[3]
        h = max(84, y + 22)
        self._pic = photo(rounded_image(w, h, 24, [t["accent"], t["accent2"]]))
        back = self.create_image(0, 0, image=self._pic, anchor="nw")
        self.tag_lower(back)
        if int(float(self.cget("height"))) != h:
            self.configure(height=h)


class _Proxy:
    """Lets old code say  window.balance_label.config(text=...)  while the text really lives on the banner."""

    def __init__(self, hero: _Hero, which: str):
        self.hero, self.which = hero, which

    def config(self, **kw):
        if "text" in kw:
            self.hero.set(**{self.which: kw["text"]})

    configure = config


class WalletWindow(tk.Toplevel):
    REFRESH_MS = 8000

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.me = owner.username
        self.wallet_data: dict | None = None
        self.requests: list[dict] = []
        t = owner.theme
        self.title("Wallet")
        self.geometry("660x640")
        self.minsize(600, 560)
        self.configure(bg=t["window"])
        self.transient(owner)
        self._build(t)
        self.render()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    # ── layout ─────────────────────────────────────────────────────
    def _label(self, parent, text="", bold=False, size_delta=0, muted=False, **kw):
        t = self.owner.theme
        lbl = tk.Label(parent, text=text, bg=t["window"], fg=t["muted"] if muted else t["text"],
                       font=(t["font"], t["font_size"] + size_delta, "bold" if bold else "normal"), **kw)
        lbl._pk_role = "muted" if muted else "text"
        return lbl

    def _button(self, parent, text, command, primary=False):
        return PillButton(parent, text, command, t=self.owner.theme, style="primary" if primary else "soft")

    def _build(self, t):
        add_header(self, t, "Wallet", "Send, request and track money", height=54)
        body = tk.Frame(self, bg=t["window"])
        body.pack(fill="both", expand=True, padx=22, pady=(16, 16))

        # -- balance / payout setup
        self.hero = _Hero(body, t)
        self.hero.pack(fill="x")
        self.balance_label = _Proxy(self.hero, "balance")
        self.detail_label = _Proxy(self.hero, "detail")
        self.setup_row = tk.Frame(body, bg=t["window"])
        self.setup_row.pack(fill="x")
        self.setup_button = self._button(self.setup_row, "Set up payouts", self.on_setup, primary=True)
        self.setup_button.pack(anchor="w", pady=(12, 0))

        # -- request money
        self._label(body, "Request money", bold=True, size_delta=1, anchor="w").pack(fill="x", pady=(18, 6))
        row = tk.Frame(body, bg=t["window"])
        row.pack(fill="x")
        self._label(row, "From", muted=True, size_delta=-1).grid(row=0, column=0, sticky="w", padx=(4, 0))
        self._label(row, "Amount ($)", muted=True, size_delta=-1).grid(row=0, column=1, sticky="w", padx=(14, 0))
        self._label(row, "What for (optional)", muted=True, size_delta=-1).grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.person_box = RoundEntry(row, t, width=150, height=40, values=self._other_users())
        self.person_box.grid(row=1, column=0, sticky="we", pady=(2, 0))
        self.amount_entry = RoundEntry(row, t, width=100, height=40)
        self.amount_entry.grid(row=1, column=1, sticky="we", padx=(10, 0), pady=(2, 0))
        self.note_entry = RoundEntry(row, t, width=190, height=40)
        self.note_entry.grid(row=1, column=2, sticky="we", padx=(10, 0), pady=(2, 0))
        row.columnconfigure(2, weight=1)
        self.send_button = self._button(row, "Send request", self.on_request, primary=True)
        self.send_button.grid(row=1, column=3, padx=(10, 0), pady=(2, 0))
        self.request_hint = self._label(body, "", muted=True, size_delta=-1, anchor="w")
        self.request_hint.pack(fill="x", pady=(6, 0), padx=(4, 0))
        self.amount_entry.bind("<Return>", lambda e: self.on_request())
        self.note_entry.bind("<Return>", lambda e: self.on_request())

        # -- history
        self._label(body, "Requests & payments", bold=True, size_delta=1, anchor="w").pack(fill="x", pady=(14, 6))
        self._tree_border = tk.Frame(body, bg=mix_hex(t["input_bg"], t["accent"], .28), padx=1, pady=1)
        self._tree_border._pk_skip = True             # keeps its outline color (see retheme)
        self._tree_border.pack(fill="both", expand=True)
        frame = tk.Frame(self._tree_border, bg=t["input_bg"])
        frame.pack(fill="both", expand=True)
        cols = ("when", "what", "amount", "status")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse", height=8)
        for col, title, width, anchor in (("when", "When", 110, "w"), ("what", "Who / what for", 260, "w"),
                                          ("amount", "Amount", 80, "e"), ("status", "Status", 120, "w")):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "what"))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_actions())

        actions = tk.Frame(body, bg=t["window"])
        actions.pack(fill="x", pady=(12, 0))
        self.pay_button = self._button(actions, "Pay now", lambda: self.on_respond("pay"), primary=True)
        self.decline_button = self._button(actions, "Decline", lambda: self.on_respond("decline"))
        self.cancel_button = self._button(actions, "Cancel request", lambda: self.on_respond("cancel"))
        for b in (self.pay_button, self.decline_button, self.cancel_button):
            b.pack(side="left", padx=(0, 8))
        self.footer = self._label(body, "", muted=True, size_delta=-1, anchor="w", justify="left", wraplength=590)
        self.footer.pack(fill="x", pady=(12, 0))
        self._themer = Themer(self, lambda: self.owner.theme)
        self._update_actions()

    def retheme(self):
        """The theme changed while the Wallet was open: recolor everything."""
        t = self.owner.theme
        self.configure(bg=t["window"])
        self._themer.apply()
        self._tree_border.configure(bg=mix_hex(t["input_bg"], t["accent"], .28))
        self._tree_border.winfo_children()[0].configure(bg=t["input_bg"])

    def _other_users(self) -> list[str]:
        return [u for u in self.owner.online_users if u != self.me]

    # ── talking to the server ──────────────────────────────────────
    def refresh(self):
        """Ask for fresh numbers now, and again every few seconds while the window is open
        (this is also how it notices you finished setting up at Stripe)."""
        if not self.winfo_exists():
            return
        self.owner.send_json({"type": proto.PAY_WALLET})
        self._refresh_job = self.after(self.REFRESH_MS, self.refresh)

    def close(self):
        try:
            self.after_cancel(self._refresh_job)
        except Exception:
            pass
        self.owner.wallet_window = None
        self.destroy()

    def on_setup(self):
        status = (self.wallet_data or {}).get("account")
        kind = proto.PAY_DASHBOARD if status == "ready" else proto.PAY_ONBOARD
        self.owner.send_json({"type": kind})

    def on_request(self):
        person = self.person_box.get().strip()
        cents = parse_amount_to_cents(self.amount_entry.get())
        if not person:
            messagebox.showwarning("Request money", "Choose who to ask.", parent=self)
            return
        if cents is None:
            messagebox.showwarning("Request money", "Type an amount like 12 or 12.50.", parent=self)
            return
        self.owner.send_json({"type": proto.PAY_REQUEST, "payer": person, "amount_cents": cents,
                              "note": self.note_entry.get().strip()})
        self.amount_entry.delete(0, "end")
        self.note_entry.delete(0, "end")

    def selected_request(self) -> dict | None:
        sel = self.tree.selection()
        return next((r for r in self.requests if r["id"] == sel[0]), None) if sel else None

    def on_respond(self, action: str):
        req = self.selected_request()
        if not req:
            return
        if action == "pay":
            self.owner.send_json({"type": proto.PAY_RESPOND, "request_id": req["id"], "action": "pay"})
        else:
            word = "Decline" if action == "decline" else "Cancel"
            if messagebox.askyesno(word, f"{word} the {format_cents(req['amount_cents'], req['currency'])} "
                                         f"request?", parent=self):
                self.owner.send_json({"type": proto.PAY_RESPOND, "request_id": req["id"], "action": action})

    # ── receiving state ────────────────────────────────────────────
    def set_state(self, state: dict):
        self.wallet_data = state
        self.requests = list(state.get("requests") or [])
        self.render()

    def apply_update(self, request: dict):
        """One request changed: swap it in (or add it) without waiting for the next refresh."""
        for i, existing in enumerate(self.requests):
            if existing["id"] == request["id"]:
                self.requests[i] = request
                break
        else:
            self.requests.insert(0, request)
        self.render()

    def prefill(self, person: str):
        self.person_box.set(person)
        self.amount_entry.focus_set()

    # ── drawing ────────────────────────────────────────────────────
    def render(self):
        if not self.winfo_exists():
            return
        state = self.wallet_data
        cur = (state or {}).get("currency", "usd")
        demo = bool((state or {}).get("demo", getattr(self.owner, "wallet_demo", False)))
        self.person_box.configure(values=self._other_users())
        self.footer.config(text="Play money: nothing here is real, and no card or bank details are used. "
                                "When you pay a request the money moves instantly." if demo else
                           "Payments are handled by Stripe. Your card details are typed on Stripe's own page "
                           "and never reach this app or the chat server.")

        if state is None:
            self.balance_label.config(text="Loading…")
            self.detail_label.config(text="")
            self.setup_button.pack_forget()
            ready = False
        else:
            account = state.get("account")
            ready = account == "ready"
            totals = state.get("totals") or {}
            if account == "none":
                self.balance_label.config(text="Payouts not set up")
                self.detail_label.config(text="To receive money you create a free Stripe payout account "
                                              "(Stripe checks your identity and asks where to send your money). "
                                              "You do not need one just to pay someone.")
                self.setup_button.config(text="Set up payouts")
            elif account == "incomplete":
                self.balance_label.config(text="Finish setting up payouts")
                self.detail_label.config(text="Your Stripe sign-up isn't finished yet. This window updates by "
                                              "itself once you're done.")
                self.setup_button.config(text="Continue setup at Stripe")
            else:
                bal = state.get("balance")
                if bal:
                    self.balance_label.config(text=f"{format_cents(bal['available_cents'], cur)} available")
                    pending = f"{format_cents(bal['pending_cents'], cur)} on the way · " if bal["pending_cents"] else ""
                else:
                    self.balance_label.config(text="Balance unavailable")
                    pending = ""
                self.detail_label.config(
                    text=f"{pending}Received through chat {format_cents(totals.get('received_cents', 0), cur)} · "
                         f"Paid through chat {format_cents(totals.get('sent_cents', 0), cur)}. " +
                         ("Play money, so there's nothing to set up." if demo else
                          "Stripe sends your balance to your bank automatically."))
                self.setup_button.config(text="Open my Stripe dashboard")
            if demo and ready:
                self.setup_button.pack_forget()          # no payouts or dashboard with play money
            else:
                self.setup_button.pack(anchor="w", pady=(12, 0))

        # request form only works once payouts are ready
        for widget in (self.person_box, self.amount_entry, self.note_entry, self.send_button):
            widget.config(state="normal" if ready else "disabled")
        self.request_hint.config(text="" if ready else "Set up payouts first, then you can ask people for money.")

        # history, keeping the selection if the row is still there
        keep = (self.tree.selection() or (None,))[0]
        self.tree.delete(*self.tree.get_children())
        for r in self.requests:
            mine_out = r["requester"] == self.me
            who = f"Asked {r['payer']}" if mine_out else f"{r['requester']} asked you"
            amount = format_cents(r["amount_cents"], r["currency"])
            if r["status"] == "paid":
                amount = ("+" if mine_out else "−") + amount
            self.tree.insert("", "end", iid=r["id"],
                             values=(local_time(r.get("paid_at") or r.get("created_at")),
                                     who + note_suffix(r), amount, STATUS_TEXT.get(r["status"], r["status"])))
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
        self._update_actions()

    def _update_actions(self):
        req = self.selected_request()
        am_payer = bool(req) and req["payer"] == self.me
        am_requester = bool(req) and req["requester"] == self.me
        status = req["status"] if req else None
        self.pay_button.config(state="normal" if am_payer and status in ("pending", "awaiting_payment") else "disabled",
                               text="Resume payment" if status == "awaiting_payment" else "Pay now")
        self.decline_button.config(state="normal" if am_payer and status == "pending" else "disabled")
        self.cancel_button.config(state="normal" if am_requester and status == "pending" else "disabled")


class PaymentPrompt(tk.Toplevel):
    """\"Sam is asking you for $12.00\" -- Pay / Decline / Later. Not modal: you can keep chatting."""

    def __init__(self, owner, request: dict):
        super().__init__(owner)
        self.owner = owner
        self.request = request
        self.request_id = request["id"]
        t = owner.theme
        self.title("Payment request")
        self.resizable(False, False)
        self.configure(bg=t["window"])
        add_header(self, t, "Payment request", "Someone is asking you for money", height=54)
        body = tk.Frame(self, bg=t["window"])
        body.pack(padx=32, pady=(16, 20))
        tk.Label(body, text="💸", bg=t["window"], font=("Segoe UI Emoji", 28)).pack()
        amount = format_cents(request["amount_cents"], request["currency"])
        tk.Label(body, text=f"{request['requester']} is asking you for {amount}", bg=t["window"], fg=t["text"],
                 font=(t["font"], t["font_size"] + 2, "bold"), justify="center", wraplength=340).pack(pady=(2, 2))
        if request.get("note"):
            tk.Label(body, text=f"“{request['note']}”", bg=t["window"], fg=t["muted"],
                     font=(t["font"], t["font_size"]), wraplength=340).pack()
        tk.Label(body, text=("Play money: if you pay, it moves right away.\n" if getattr(owner, "wallet_demo", False)
                             else "If you pay, you'll finish on Stripe's secure page in your browser.\n") +
                            "Only pay people you know and expect to hear from.",
                 bg=t["window"], fg=t["muted"], font=(t["font"], max(7, t["font_size"] - 1)), justify="center"
                 ).pack(pady=(8, 14))
        row = tk.Frame(body, bg=t["window"])
        row.pack()
        PillButton(row, "Pay now", lambda: self._answer("pay"), t=t, width=108).pack(side="left", padx=4)
        PillButton(row, "Decline", lambda: self._answer("decline"), t=t, style="soft", width=108).pack(side="left", padx=4)
        PillButton(row, "Later", self.close, t=t, style="ghost", width=80).pack(side="left", padx=4)
        self.protocol("WM_DELETE_WINDOW", self.close)      # closing = "later", never an accidental decline
        owner.pay_prompts[self.request_id] = self
        self.transient(owner)

    def _answer(self, action: str):
        self.owner.send_json({"type": proto.PAY_RESPOND, "request_id": self.request_id, "action": action})
        self.close()

    def close(self):
        self.owner.pay_prompts.pop(self.request_id, None)
        if self.winfo_exists():
            self.destroy()
