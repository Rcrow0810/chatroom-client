# login_app.py
# ---------------------------------------------------------
# The login window: a gradient background, a logo, and one rounded card with a "Log in / Sign up" switch.
# (All the modern-looking pieces live in ui_kit.py.)
#
# Logging in = password, then a Google Authenticator code (see mfa_client.py), both checked by the chat
# server. Register / Forgot password go to the server through account_api.py and show the result.
#
# Run with:  python3 login_app.py
# ---------------------------------------------------------

import re
import tkinter as tk

import account_api
import app_paths
import ui_kit as ui
from chat_window import ChatWindow
from mfa_client import LoginCancelled, LoginError, login as login_with_mfa
from mfa_dialog import AuthCodeDialog
from popup_kit import messagebox
from password_policy import check_password_strength, strength_label
from recovery_dialog import RecoveryDialog
from secure_connection import SecureConnectionError

WIDTH = 440            # window width
CARD_W = 380           # white card width
CARD_TOP = 196         # where the card starts (logo + title are above it)
BOTTOM = 40
INSET = 30             # space between the card's edge and its contents (also hides the frame's square corners)
FIELD_W = CARD_W - 2 * INSET


class LoginApp(tk.Tk):
    def __init__(self):
        super().__init__()
        app_paths.set_app_icon(self)
        self.title("Chat Room")
        self.resizable(False, False)
        self.configure(bg=ui.INDIGO)

        self.canvas = tk.Canvas(self, width=WIDTH, height=640, highlightthickness=0, bd=0, bg=ui.INDIGO)
        self.canvas.pack()
        self._pictures = []                      # Tk drops pictures nobody holds on to

        # the card's contents (built once, so what you typed survives switching between Log in / Sign up)
        self.card = tk.Frame(self.canvas, bg=ui.WHITE)
        self.switch = ui.SegmentedSwitch(self.card, ("Log in", "Sign up"), self._switch, width=FIELD_W)
        self.switch.pack(pady=(0, 20))
        self.body = tk.Frame(self.card, bg=ui.WHITE)
        self.body.pack()

        self.login_tab = LoginTab(self.body, on_success=self.handle_logged_in, require_server=self.require_server)
        self.register_tab = RegisterTab(self.body, require_server=self.require_server, on_created=self._after_register)
        self.login_tab.pack()

        self._card_window = self.canvas.create_window(WIDTH // 2, 0, window=self.card, anchor="center")
        self._relayout()
        self._center_on_screen()
        self.after(100, self.login_tab.username_entry.focus_set)

    # ------------------------------------------------------------------ layout
    def _switch(self, index: int):
        (self.register_tab if index else self.login_tab).pack()
        (self.login_tab if index else self.register_tab).pack_forget()
        self._relayout()

    def _relayout(self):
        """Size the window and redraw the background + card to fit whichever view is showing."""
        self.card.update_idletasks()
        content_h = self.card.winfo_reqheight()
        card_h = content_h + 2 * INSET
        total_h = CARD_TOP + card_h + BOTTOM
        self.canvas.config(height=total_h)
        self.geometry(f"{WIDTH}x{total_h}")

        c = self.canvas
        c.delete("deco")
        self._pictures = [
            ui.photo(ui.gradient_bg(WIDTH, total_h)),
            ui.photo(ui.card_image(CARD_W, card_h)),
            ui.photo(ui.logo_image(76)),
        ]
        c.create_image(0, 0, image=self._pictures[0], anchor="nw", tags="deco")
        c.create_image((WIDTH - CARD_W) // 2 - ui.SHADOW_PAD, CARD_TOP - ui.SHADOW_PAD,
                       image=self._pictures[1], anchor="nw", tags="deco")
        c.create_image(WIDTH // 2, 62, image=self._pictures[2], anchor="center", tags="deco")
        c.create_text(WIDTH // 2, 132, text="Chat Room", fill="white", font=ui.font(24, True), tags="deco")
        c.create_text(WIDTH // 2, 164, text="Hang out. Talk. Play.", fill="#F1EAFF", font=ui.font(11), tags="deco")
        c.tag_lower("deco")
        c.coords(self._card_window, WIDTH // 2, CARD_TOP + card_h // 2)

    def _center_on_screen(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------ shared
    def require_server(self):
        """Read the IP typed on the Log In tab and point the database at it. Returns the address,
        or None (after saying what's wrong, and jumping to the Log In tab) if it's empty or
        doesn't look like one. Register and Forgot-password use the same box."""
        entry = self.login_tab.server_ip_entry
        host = entry.get().strip()
        problem = None
        if not host:
            problem = ("Server IP needed", "Type the server's IP address on the Log In tab first.")
        elif not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}", host):
            problem = ("That doesn't look right", "A server address is numbers and dots, like 192.168.1.50")
        if problem:
            self.switch.select(0)
            messagebox.showwarning(*problem)
            entry.focus_set()
            return None
        account_api.set_host(host)
        return host

    def handle_logged_in(self, username: str, server_ip: str, sock, reader):
        """
        Called the moment a login (password AND authenticator code) succeeds. Hides the login window and
        opens the styled chat window on the connection that is already logged in.
        """
        self.withdraw()  # hide the login window instead of destroying it
        ChatWindow(self, username=username, server_ip=server_ip, sock=sock, reader=reader)

    def _after_register(self, username: str):
        """Account made: flip to Log in with the name filled in."""
        self.switch.select(1, notify=False)
        self.switch.select(0)
        self.login_tab.username_entry.delete(0, tk.END)
        self.login_tab.username_entry.insert(0, username)
        self.login_tab.password_entry.focus_set()


class LoginTab(tk.Frame):
    def __init__(self, parent, on_success, require_server):
        super().__init__(parent, bg=ui.WHITE)
        self.on_success = on_success
        self.require_server = require_server

        ui.field_label(self, "Username").pack(anchor="w")
        self.username_entry = ui.ModernEntry(self, width=FIELD_W)
        self.username_entry.pack(pady=(4, 14))

        ui.field_label(self, "Password").pack(anchor="w")
        self.password_entry = ui.ModernEntry(self, width=FIELD_W, secret=True)
        self.password_entry.pack(pady=(4, 14))

        ui.field_label(self, "Server address").pack(anchor="w")
        self.server_ip_entry = ui.ModernEntry(self, width=FIELD_W)
        self.server_ip_entry.pack(pady=(4, 20))

        self.login_button = ui.ModernButton(self, "Log in", self.attempt_login, width=FIELD_W)
        self.login_button.pack()

        ui.LinkLabel(self, "Forgot password?", self.open_recovery).pack(pady=(14, 4))
        tk.Label(self, text="Protected with Google Authenticator", bg=ui.WHITE, fg=ui.MUTED,
                 font=ui.font(8)).pack()

        for entry in (self.username_entry, self.password_entry, self.server_ip_entry):
            entry.bind("<Return>", lambda event: self.attempt_login())

    def open_recovery(self):
        if not self.require_server():
            return
        RecoveryDialog(self.winfo_toplevel(), prefill=self.username_entry.get().strip(),
                       on_done=self._after_reset)

    def _after_reset(self, username: str):
        """Password was reset: put their username back and wait for the new password."""
        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(0, username)
        self.password_entry.delete(0, tk.END)
        self.password_entry.focus_set()

    def attempt_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        server_ip = self.require_server()
        if not server_ip:
            return
        if not username or not password:
            messagebox.showwarning("Log in", "Type your username and password.")
            return

        root = self.winfo_toplevel()

        def ask_code(setup, message):
            return AuthCodeDialog(root, setup=setup, message=message).show()

        self.login_button.set_enabled(False)
        self.login_button.set_text("Logging in\u2026")
        try:
            root.config(cursor="watch")
            root.update_idletasks()
            # The server checks the password, then asks for the authenticator code (and shows the QR
            # code the very first time). We get back a connection that is fully logged in.
            sock, reader, name = login_with_mfa(server_ip, 5555, username, password, ask_code)
        except LoginCancelled:
            return
        except (LoginError, SecureConnectionError) as e:
            messagebox.showerror("Login failed", str(e))
            return
        except Exception as e:
            messagebox.showerror("Login failed", f"Could not log in to {server_ip}:\n\n{e}")
            return
        finally:
            root.config(cursor="")
            self.login_button.set_enabled(True)
            self.login_button.set_text("Log in")
            password = ""

        self.password_entry.delete(0, tk.END)           # don't leave it sitting in the box
        self.on_success(name, server_ip, sock, reader)


class RegisterTab(tk.Frame):
    def __init__(self, parent, require_server, on_created=None):
        super().__init__(parent, bg=ui.WHITE)
        self.require_server = require_server
        self.on_created = on_created

        ui.field_label(self, "Choose a username").pack(anchor="w")
        self.username_entry = ui.ModernEntry(self, width=FIELD_W)
        self.username_entry.pack(pady=(4, 14))

        ui.field_label(self, "Choose a password").pack(anchor="w")
        self.password_entry = ui.ModernEntry(self, width=FIELD_W, secret=True)
        self.password_entry.pack(pady=(4, 8))
        self.password_entry.bind("<KeyRelease>", self.update_strength_display)

        self.strength_bar = ui.StrengthBar(self, width=FIELD_W)
        self.strength_bar.pack()
        self.strength_label = tk.Label(self, text="", bg=ui.WHITE, fg=ui.MUTED, font=ui.font(9),
                                       anchor="w", justify="left", wraplength=FIELD_W, height=2)
        self.strength_label.pack(fill="x", pady=(4, 6))

        ui.field_label(self, "Confirm password").pack(anchor="w")
        self.confirm_entry = ui.ModernEntry(self, width=FIELD_W, secret=True)
        self.confirm_entry.pack(pady=(4, 20))
        self.confirm_entry.bind("<Return>", lambda event: self.attempt_register())

        ui.ModernButton(self, "Create account", self.attempt_register, width=FIELD_W).pack(pady=(0, 6))
        self.update_strength_display()

    def update_strength_display(self, event=None):
        password = self.password_entry.get()
        label, color = strength_label(password)
        _, issues = check_password_strength(password)
        score = 0 if not password else max(1, min(4, 4 - len(issues) + (1 if not issues else 0)))
        if issues:
            hint = "Still needs: " + ", ".join(i[0].lower() + i[1:] for i in issues[:2])
            hint += "\u2026" if len(issues) > 2 else ""
        else:
            hint = "Looks strong!" if password else "At least 12 characters with upper, lower, a number and a symbol."
        self.strength_bar.set(score, color if password else ui.TRACK)
        self.strength_label.config(text=(f"{label}  \u2022  {hint}" if password else hint),
                                   fg=color if password and not issues else ui.MUTED)

    def attempt_register(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()

        if password != confirm:
            messagebox.showerror("Mismatch", "Passwords don't match.")
            return

        is_valid, issues = check_password_strength(password)
        if not is_valid:
            messagebox.showerror(
                "Password too weak",
                "Your password is missing:\n\n" + "\n".join(f"- {i}" for i in issues),
            )
            return

        if not self.require_server():
            return

        success, message = account_api.create_user(username, password)

        if success:
            messagebox.showinfo("Success", message + "\n\nThe first time you log in you will set up "
                                "Google Authenticator on your phone.")
            name = username.strip()
            self.username_entry.delete(0, tk.END)
            self.password_entry.delete(0, tk.END)
            self.confirm_entry.delete(0, tk.END)
            self.update_strength_display()
            if self.on_created:
                self.on_created(name)
        else:
            messagebox.showerror("Registration failed", message)


if __name__ == "__main__":
    app = LoginApp()
    app.mainloop()
