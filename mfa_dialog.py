# mfa_dialog.py  --  CLIENT SIDE
# ---------------------------------------------------------
# The pop-up that asks for the Google Authenticator code (styled to match the login window, see ui_kit.py).
#
#   * First login ever (setup given): shows a QR code to scan, plus the same key as text for typing in by
#     hand, then asks for the first code.
#   * Every login after that: just asks for the 6-digit code.
#
#     code = AuthCodeDialog(parent, setup=None_or_dict, message=None_or_text).show()   # None = cancelled
#
# The QR code needs the `qrcode` package (pip install qrcode). Without it the dialog still works: it shows
# the key to type into the app ("Enter a setup key").
# ---------------------------------------------------------

import tkinter as tk

import ui_kit as ui

WIDTH = 400
BODY_W = 320


def _qr_tile(uri: str):
    """The QR code on a rounded white tile, as a Tk image -- or None if the qrcode package isn't installed."""
    try:
        import qrcode
        from PIL import Image
        qr = qrcode.QRCode(border=1, box_size=6, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1E1B3A", back_color="white")
        img = getattr(img, "get_image", lambda: img)().convert("RGBA")
        pad = 14
        tile = ui.rounded_image(img.width + 2 * pad, img.height + 2 * pad, 20, ui.WHITE, ui.FIELD_EDGE, 2)
        tile.alpha_composite(img, (pad, pad))
        return ui.photo(tile)
    except Exception:
        return None


def _grouped(secret: str) -> str:
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


class AuthCodeDialog(tk.Toplevel):
    def __init__(self, parent, setup: dict | None = None, message: str | None = None):
        super().__init__(parent)
        self.result = None
        self._setup = setup
        self._pictures = []                        # keep references, or Tk throws the pictures away

        self.title("Set up Google Authenticator" if setup else "Two-step verification")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(bg=ui.WHITE)

        # ── gradient header ─────────────────────────────────────────────
        head_h = 96
        head = tk.Canvas(self, width=WIDTH, height=head_h, highlightthickness=0, bd=0, bg=ui.INDIGO)
        head.pack()
        bg = ui.photo(ui.gradient_bg(WIDTH, head_h))
        self._pictures.append(bg)
        head.create_image(0, 0, image=bg, anchor="nw")
        head.create_text(WIDTH // 2, 38, fill="white", font=ui.font(16, True),
                         text="One-time setup" if setup else "Enter your code")
        head.create_text(WIDTH // 2, 66, fill="#F1EAFF", font=ui.font(10),
                         text="Link Google Authenticator to your account" if setup
                         else "Open Google Authenticator for your 6-digit code")

        body = tk.Frame(self, bg=ui.WHITE)
        body.pack(padx=(WIDTH - BODY_W) // 2, pady=(18, 22))

        if setup:
            steps = ("1.  Install Google Authenticator on your phone.\n"
                     "2.  In the app tap  +  \u2192  Scan a QR code:")
            tk.Label(body, text=steps, bg=ui.WHITE, fg=ui.INK, font=ui.font(10), justify="left",
                     wraplength=BODY_W, anchor="w").pack(anchor="w", pady=(0, 10))

            qr = _qr_tile(setup["uri"])
            if qr is not None:
                self._pictures.append(qr)
                tk.Label(body, image=qr, bg=ui.WHITE, bd=0).pack(pady=(0, 10))
                hint = "Can't scan?  Choose  Enter a setup key  and type:"
            else:
                hint = ("(The QR picture needs  pip install qrcode.)  In the app choose  + \u2192 Enter a "
                        "setup key  and type:")
            tk.Label(body, text=hint, bg=ui.WHITE, fg=ui.MUTED, font=ui.font(9), wraplength=BODY_W,
                     justify="left", anchor="w").pack(anchor="w")

            row = tk.Frame(body, bg=ui.WHITE)
            row.pack(pady=(6, 14))
            key = ui.ModernEntry(row, width=BODY_W - 72, height=44, size=11, readonly=True)
            key.entry.config(state="normal")
            key.insert(0, _grouped(setup["secret"]))
            key.entry.config(state="readonly")
            key.pack(side="left")
            ui.ModernButton(row, "Copy", self._copy_key, width=64, height=44, style="soft", size=10).pack(
                side="left", padx=(8, 0))

            tk.Label(body, text="3.  Type the 6-digit code the app shows now:", bg=ui.WHITE, fg=ui.INK,
                     font=ui.font(10), anchor="w").pack(anchor="w", pady=(0, 6))

        self.entry_box = ui.ModernEntry(body, width=BODY_W, height=58, size=20, justify="center")
        self.entry_box.pack(pady=(0, 8))
        self.entry_box.bind("<Return>", lambda event: self._submit())

        self._note_holder = tk.Frame(body, bg=ui.WHITE)
        self._note_holder.pack(fill="x")
        self._note = tk.Label(self._note_holder, bg=ui.DANGER_BG, fg=ui.DANGER, font=ui.font(9, True),
                              wraplength=BODY_W - 24, justify="left", anchor="w", padx=12, pady=8)
        self._set_note(message)

        ui.ModernButton(body, "Continue", self._submit, width=BODY_W).pack(pady=(10, 4))
        ui.ModernButton(body, "Cancel", self._cancel, width=BODY_W, height=38, style="ghost", size=10).pack()

        self.bind("<Escape>", lambda event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()                    # centre over the window it came from
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_reqheight()) // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def show(self):
        """Open the box, wait until it is answered, return the typed code (or None if cancelled)."""
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.entry_box.focus_set()
        self.wait_window(self)
        return self.result

    def _set_note(self, text: str | None):
        if text:
            self._note.config(text=text)
            self._note.pack(fill="x")
        else:
            self._note.pack_forget()

    def _copy_key(self):
        self.clipboard_clear()
        self.clipboard_append(self._setup["secret"])

    def _submit(self):
        code = self.entry_box.get().replace(" ", "").strip()
        if len(code) != 6 or not code.isdigit():
            self._set_note("The code is 6 digits, like 123456.")
            self.entry_box.focus_set()
            return
        self.result = code
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
