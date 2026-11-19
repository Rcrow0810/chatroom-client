# account_api.py  --  CLIENT SIDE
# ---------------------------------------------------------
# Account actions (register, change password, recovery, ...) go to the chat SERVER over the same
# encrypted connection as logging in; the server talks to the database. The client never connects
# to MySQL itself, so no database password ships with the app.
# Each call opens a short connection, sends one request, reads one answer and closes. The answers
# are the same (ok, message) pairs the old db.py calls gave, so the screens barely changed.
# ---------------------------------------------------------

import protocol as proto
from protocol import JSONStreamReader, send_json
from secure_connection import SecureConnectionError, connect_secure

SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was the name of your first school?",
    "What was your childhood nickname?",
    "What is the name of the street you grew up on?",
    "What was the make of your first car?",
    "What is your favorite teacher's last name?",
    "What was the first concert you attended?",
    "What was the name of your first boss?",
    "What was your dream job as a kid?",
]

_server = {"host": None, "port": 5555}


def set_host(host: str, port: int = 5555):
    _server["host"] = (host or "").strip() or None
    _server["port"] = port


def call(action: str, **fields) -> dict:
    """Send one account request. Always returns a dict with at least 'ok' and 'message'."""
    host = _server["host"]
    if not host:
        return {"ok": False, "message": "Type the server's IP address first."}
    try:
        sock = connect_secure(host, _server["port"])
    except SecureConnectionError as e:
        return {"ok": False, "message": str(e)}
    try:
        sock.settimeout(20)
        send_json(sock, {"type": proto.ACCOUNT, "action": action, **fields})
        reply = JSONStreamReader(sock).read_message()
    except OSError as e:
        return {"ok": False, "message": f"Lost the connection to the chat server.\n\n({e})"}
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not reply or reply.get("type") != proto.ACCOUNT_RESULT:
        return {"ok": False, "message": "The server gave an unexpected answer. Is it up to date?"}
    return reply


def _pair(r: dict) -> tuple[bool, str]:
    return bool(r.get("ok")), str(r.get("message", ""))


def _questions(r: dict) -> list[str]:
    if not r.get("ok"):
        raise RuntimeError(r.get("message") or "The server couldn't answer.")
    return [q for q in r.get("questions", []) if isinstance(q, str)]


def create_user(username, password):
    return _pair(call("register", username=username, password=password))


def change_password(username, current, new):
    return _pair(call("change_password", username=username, password=current, new_password=new))


def change_username(username, new_username, password):
    return _pair(call("change_username", username=username, new_username=new_username, password=password))


def delete_account(username, password):
    return _pair(call("delete_account", username=username, password=password))


def get_security_questions(username):
    return _questions(call("get_security_questions", username=username))


def get_recovery_questions(username):
    return _questions(call("get_recovery_questions", username=username))


def set_security_questions(username, password, qa):
    return _pair(call("set_security_questions", username=username, password=password,
                      qa=[[q, a] for q, a in qa]))


def reset_password_with_answers(username, answers, new_password):
    return _pair(call("reset_password", username=username, answers=list(answers), new_password=new_password))
