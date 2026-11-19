# secure_connection.py
# ---------------------------------------------------------
# Opens the encrypted connection to the chat server.
#
# The server proves who it is with a certificate, and we only accept
# the ONE certificate in server.crt (the file the server's owner gives you,
# kept next to chat.key). So even someone on your network who redirects your
# traffic to their own computer can't read your password or payment links:
# their certificate won't match and the connection is refused.
# ---------------------------------------------------------

import os
import socket
import ssl

CERT_FILE = None          # None = look for server.crt next to the app (see app_paths.find_resource)


class SecureConnectionError(Exception):
    """Something to show the person, in plain words."""


def connect_secure(host: str, port: int, cert_path: str | None = None, timeout: float = 8.0) -> ssl.SSLSocket:
    if cert_path is None:
        import app_paths
        cert_path = CERT_FILE or app_paths.find_resource("server.crt")
    if not os.path.exists(cert_path):
        raise SecureConnectionError(
            "server.crt is missing.\n\nAsk whoever runs the chat server for their "
            "server.crt file and put it next to the app.")

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = False                    # we pin the exact certificate instead of trusting a name
    try:
        ctx.load_verify_locations(cafile=cert_path)   # the ONLY certificate we will accept
    except (ssl.SSLError, OSError) as e:
        raise SecureConnectionError(f"server.crt couldn't be read ({e}).") from e

    raw = None
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
        tls = ctx.wrap_socket(raw)
        tls.settimeout(None)
        return tls
    except ssl.SSLCertVerificationError as e:
        if raw:
            raw.close()
        raise SecureConnectionError(
            "This server's security certificate does NOT match your server.crt.\n\n"
            "Either the server was given a new certificate (ask its owner for the new server.crt), or "
            "something on the network is pretending to be the server. Don't log in until you know which.") from e
    except ssl.SSLError as e:
        if raw:
            raw.close()
        raise SecureConnectionError(f"Couldn't make a secure connection ({e.reason or e}). "
                                    f"Is the server running the new encrypted version?") from e
    except OSError as e:
        if raw:
            raw.close()
        raise SecureConnectionError(f"Could not reach {host}:{port}. Is the server running?\n\n{e}") from e
