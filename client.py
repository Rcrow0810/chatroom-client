# client.py
# ---------------------------------------------------------
# Bare-bones terminal client. Good for quick testing or a
# headless machine. For the full feature set -- DM tabs,
# presence sidebar, typing indicators, read receipts, file
# sharing, reactions, edit/delete -- use chat_window.py /
# login_app.py instead; this one only does room chat + DMs.
#
# Fixed from the original version:
#   - `sock.connect(...)` was called on an undefined name
#     `sock`; the socket variable was actually `client`.
#   - `msg.strip() -- ''` was a typo for `msg.strip() == ''`.
#   - recv(1024) assumed one recv() == one message, which
#     breaks as soon as a message is bigger than one packet
#     or two arrive back-to-back. Now uses the same
#     JSONStreamReader as the GUI so messages never get cut
#     off or glued together.
#
# Commands while chatting:
#   /dm <username> <message>   send a private message
#   /quit                      leave
# ---------------------------------------------------------

import getpass
import threading

import crypto_utils
import protocol as proto
from protocol import send_json
from mfa_client import LoginCancelled, LoginError, login
from secure_connection import SecureConnectionError


def ask_code(setup, message):
    """Terminal version of the authenticator box (see mfa_dialog.py for the window version)."""
    if setup:
        print("\nFirst login: set up Google Authenticator on your phone.")
        print("  In the app tap  +  ->  Enter a setup key, and type this key:")
        print(f"      {setup['secret']}")
        print(f"  (account: {setup['issuer']}, time-based)")
        try:                                           # a QR code in the terminal, if `qrcode` is installed
            import qrcode
            qr = qrcode.QRCode(border=1)
            qr.add_data(setup["uri"])
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        except Exception:
            pass
    if message:
        print(message)
    try:
        code = input("6-digit code from Google Authenticator (blank to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return code or None


def receive_messages(sock, reader, cipher, username):
    while True:
        msg = reader.read_message()
        if msg is None:
            print("\nDisconnected from server.")
            break

        kind = msg.get("type")

        if kind == proto.SYSTEM:
            print(f"*** {msg['text']} ***")

        elif kind == proto.PRESENCE:
            print(f"[online: {', '.join(msg.get('users', []))}]")

        elif kind == proto.TEXT:
            sender = msg["sender"]
            target = msg.get("target")
            text = crypto_utils.decrypt_message(cipher, msg["text"]) if msg["text"] else "[deleted]"
            prefix = f"(DM) {sender}" if target is not None else sender
            print(f"{prefix}: {text}")

        elif kind == proto.HISTORY:
            for row in msg.get("messages", []):
                if row.get("msg_type") != "text" or row.get("deleted"):
                    continue
                text = crypto_utils.decrypt_message(cipher, row["body"])
                print(f"[history] {row['sender']}: {text}")

        elif kind == proto.ERROR:
            print(f"[server error] {msg.get('text')}")
            if msg.get("fatal"):
                break

        elif kind == proto.PAY_UPDATE:        # payments need the GUI client, but say that something happened
            req = msg.get("request", {})
            if req.get("status") == "pending" and req.get("payer") == username and msg.get("event") != "open":
                print(f"*** {req.get('requester')} is asking you for money. Open the GUI client's Wallet to answer. ***")

        elif kind == proto.GAME_EVENT:       # dice / coin results (invites and board games need the GUI)
            print(msg.get("text", ""))

        # typing/reactions/edits/file transfer are intentionally not
        # rendered here -- use the GUI client for those.


def main():
    server_ip = input('Server IP (press Enter for this computer): ').strip() or '127.0.0.1'
    username = input('Username: ').strip()
    password = getpass.getpass('Password: ')

    try:
        cipher = crypto_utils.load_cipher()
    except FileNotFoundError as e:
        print(e)
        return

    try:
        client, reader, username = login(server_ip, 5555, username, password, ask_code)
    except LoginCancelled:
        print("Cancelled.")
        return
    except (LoginError, SecureConnectionError) as e:
        print(e)
        return

    print(f'\nConnected! Welcome, {username}')
    print('Type a message and press Enter to send.')
    print('Type /dm <username> <message> to send a private message.')
    print('Type /quit to leave.\n')

    receive_thread = threading.Thread(target=receive_messages, args=(client, reader, cipher, username), daemon=True)
    receive_thread.start()

    while True:
        try:
            msg = input()
        except KeyboardInterrupt:
            break

        if msg.lower() == '/quit':
            break
        if msg.strip() == '':
            continue

        if msg.startswith('/dm '):
            _, rest = msg.split(' ', 1)
            if ' ' not in rest:
                print("Usage: /dm <username> <message>")
                continue
            target, text = rest.split(' ', 1)
            encrypted = crypto_utils.encrypt_message(cipher, text)
            send_json(client, {"type": proto.TEXT, "target": target, "text": encrypted})
        else:
            encrypted = crypto_utils.encrypt_message(cipher, msg)
            send_json(client, {"type": proto.TEXT, "target": None, "text": encrypted})

    client.close()
    print('You left the chat.')


if __name__ == "__main__":
    main()
