# mfa_client.py  --  CLIENT SIDE
# ---------------------------------------------------------
# The whole login conversation with the chat server, with no window code in it (so the terminal client
# can use it too):
#
#     password  ->  Google Authenticator code  ->  an open, logged-in connection
#
# `ask_code(setup, message)` is the only thing that talks to the person. It is called each time a code is
# needed and must return the typed text, or None if they gave up.
#     setup   None for someone who already has the app set up; otherwise a dict
#             {secret, uri, issuer} to show as a QR code (first login only)
#     message None, or a note such as "That code didn't work..." after a wrong try
# ---------------------------------------------------------

import socket

import protocol as proto
from protocol import JSONStreamReader, send_json
from secure_connection import SecureConnectionError, connect_secure

REPLY_TIMEOUT = 30          # seconds to wait for the server to answer (the person's typing time isn't counted)


class LoginError(Exception):
    """Login failed; the text is safe to show the person as it is."""


class LoginCancelled(Exception):
    """The person closed the code box."""


def _read(reader: JSONStreamReader) -> dict:
    try:
        msg = reader.read_message()
    except (TimeoutError, socket.timeout):
        raise LoginError("The server took too long to answer. Is it running the newest version?")
    except (OSError, ValueError) as e:
        raise LoginError(f"Lost the connection to the server ({e}).")
    if msg is None:
        raise LoginError("The server closed the connection.")
    return msg


def login(host: str, port: int, username: str, password: str, ask_code):
    """Returns (sock, reader, username). Hand BOTH sock and reader to the chat window: the server starts
    sending the chat the instant the code is accepted, and some of it may already be inside `reader`.
    Raises LoginError / LoginCancelled / SecureConnectionError."""
    sock = connect_secure(host, port)                  # encrypted, certificate-checked
    try:
        reader = JSONStreamReader(sock)
        sock.settimeout(REPLY_TIMEOUT)
        send_json(sock, {"type": proto.AUTH, "username": username, "password": password})

        first = _read(reader)
        kind = first.get("type")
        if kind == proto.ERROR:
            raise LoginError(first.get("text") or "Login failed.")
        if kind == proto.MFA_SETUP:
            secret, uri = first.get("secret"), first.get("uri")
            if not isinstance(secret, str) or not isinstance(uri, str):
                raise LoginError("The server sent a broken authenticator setup. Is it up to date?")
            setup = {"secret": secret, "uri": uri, "issuer": first.get("issuer") or "Chat Room"}
        elif kind == proto.MFA_REQUIRED:
            setup = None
        else:
            # An older server that doesn't ask for a code. Refuse: logging in without one is exactly what
            # this version is meant to stop.
            raise LoginError("This server doesn't support Google Authenticator logins.\n"
                             "Ask whoever runs it to update the server, then try again.")

        message = None
        while True:
            code = ask_code(setup, message)
            if code is None:
                raise LoginCancelled()
            send_json(sock, {"type": proto.MFA_CODE, "code": code})
            reply = _read(reader)
            kind = reply.get("type")
            if kind == proto.MFA_OK:
                sock.settimeout(None)
                return sock, reader, (reply.get("username") or username)
            if kind == proto.MFA_FAIL:
                message = reply.get("text") or "That code didn't work."
                left = reply.get("attempts_left")
                if isinstance(left, int):
                    message += f"  ({left} {'try' if left == 1 else 'tries'} left)"
                continue
            if kind == proto.ERROR:
                raise LoginError(reply.get("text") or "Login failed.")
            raise LoginError("The server gave an unexpected answer. Is it up to date?")
    except BaseException:
        try:
            sock.close()
        except OSError:
            pass
        raise


__all__ = ["login", "LoginError", "LoginCancelled", "SecureConnectionError"]
