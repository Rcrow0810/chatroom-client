# protocol.py
# ---------------------------------------------------------
# Everything server.py and the clients need to agree on:
#   1. How a message is framed on the wire (so recv() never
#      chops a message in half or glues two together).
#   2. What "types" of message exist and what fields each
#      one carries.
#
# THE FRAMING BUG THIS FIXES:
# The original code did `client_socket.recv(1024).decode()`
# and assumed that was exactly one message. TCP doesn't work
# that way -- a single recv() can return part of a message,
# or several messages stuck together. JSONStreamReader below
# buffers bytes and only hands back a message once it's seen
# a full line, no matter how the OS chopped up the packets.
# ---------------------------------------------------------

import json

# One JSON object per line. Simple, human-readable if you sniff
# the traffic, and easy to debug.
ENCODING = "utf-8"

# File transfer tuning. Keep chunks small enough that a slow
# connection doesn't block typing indicators / other traffic
# for too long behind one giant send() call.
FILE_CHUNK_SIZE = 32 * 1024        # 32 KB of raw file bytes per chunk
MAX_FILE_SIZE = 8 * 1024 * 1024    # 8 MB cap per file

# How many old room messages a client gets on join.
ROOM_HISTORY_LIMIT = 50
DM_HISTORY_LIMIT = 50


def send_json(sock, obj: dict):
    """Encode a dict as one line of JSON and send it whole."""
    line = json.dumps(obj) + "\n"
    sock.sendall(line.encode(ENCODING))


class JSONStreamReader:
    """
    Wraps a raw socket. Call read_message() to get exactly one
    decoded JSON dict, however many recv() calls it takes to
    arrive, and however many messages happen to be sitting in
    the OS buffer at once.

    Returns None when the other side has closed the connection.
    """

    def __init__(self, sock, recv_size: int = 65536, max_line: int = 16 * 1024 * 1024):
        self.sock = sock
        self.recv_size = recv_size
        self.max_line = max_line      # a peer that never sends a newline can't make us buffer forever
        self._buffer = b""

    def read_message(self):
        while b"\n" not in self._buffer:
            if len(self._buffer) > self.max_line:
                raise ValueError("message too large")
            chunk = self.sock.recv(self.recv_size)
            if not chunk:
                return None  # peer disconnected
            self._buffer += chunk

        line, self._buffer = self._buffer.split(b"\n", 1)
        line = line.strip()
        if not line:
            return self.read_message()  # skip stray blank lines
        return json.loads(line.decode(ENCODING))


# ─────────────────────────────────────────────────────────────
# Message "types" -- every JSON object has a "type" field set
# to one of these. Fields listed are the ones each type carries
# (besides "type" itself).
# ─────────────────────────────────────────────────────────────
#
# Client -> Server
#   AUTH          {username}
#   TEXT          {target, text}                 target: null = room, else a username
#   TYPING        {target, state}                state: "start" | "stop"
#   READ          {message_id}
#   REACTION      {message_id, emoji, action}     action: "add" | "remove"
#   EDIT          {message_id, text}
#   DELETE        {message_id}
#   FILE_START    {file_id, target, filename, size, total_chunks}
#   FILE_CHUNK    {file_id, index, data}          data: base64 text
#   FILE_END      {file_id}
#   HISTORY_REQUEST {peer}                        ask for DM history with `peer`
#   SET_COLOR     {color}                         "#rrggbb" to pick your name color, ""/null to reset
#   SET_AVATAR    {data}                          base64 PNG (<=128x128) as your profile picture, null to remove
#   ACCOUNT_DELETED {}                            "I just deleted my account" (server double-checks the DB)
#   SET_STATUS    {status, text}                  status: a key of STATUSES below; text: optional short note
#   SET_PROFILE   {bio, pronouns, badge, banner}  your customizable profile card
#   PROFILE_REQUEST {username}                    "show me this person's card"
#   GAME_INVITE   {game, opponent}                game: "ttt" | "rps"
#   GAME_RESPOND  {game_id, accept}               accept: true | false (only the invited person)
#   GAME_MOVE     {game_id, move}                 ttt: square 0-8;  rps: "rock" | "paper" | "scissors"
#   GAME_QUIT     {game_id}                       leave (forfeits an active game, cancels/declines an invite)
#   GAME_ROLL     {target, kind, count, sides}    kind: "dice" | "coin"; target: null = room, else a username
#   PAY_WALLET    {}                              "show me my wallet"
#   PAY_ONBOARD   {}                              "let me set up (or finish) receiving payouts"
#   PAY_DASHBOARD {}                              "open my Stripe payout dashboard"
#   PAY_REQUEST   {payer, amount_cents, note}     ask `payer` for money (amount is WHOLE CENTS, an int)
#   PAY_RESPOND   {request_id, action}            action: "pay" | "decline" (payer)  or  "cancel" (requester)
#   AI_GET        {}                              "show me my AI friend" (persona + recent chat)
#   AI_SAVE       {name, gender, personality}     create / change my AI friend; gender: "he" | "she" | "they"
#   AI_SEND       {text}                          say something to my AI friend (the answer comes as AI_REPLY)
#   AI_RESET      {}                              clear my chat with my AI friend (the persona stays)
#
# Server -> Client
#   TEXT          {id, sender, target, text, ts}
#   SYSTEM        {text}                          join/leave/etc, not persisted
#   PRESENCE      {users, statuses, everyone, last_seen}   full online list, replaces old one
#                                                  statuses: {username: {status, text}} for everyone listed
#                                                  everyone: [username] -- EVERY account that exists, online or not
#                                                  last_seen: {username: iso time} of their last disconnect (offline people)
#   --- the FEED (posts, likes, comments; text + photos are encrypted with the chat key like messages) ---
#   FEED_GET      {before?}                       ask for the newest posts (or the 15 older than id `before`)
#   POST_CREATE   {text, image?}                  share a post; `image` = encrypted base64 JPEG (optional)
#   POST_IMAGE_GET {post_id}                      ask for one post's photo (photos are fetched one at a time)
#   POST_LIKE     {post_id}                       like it, or un-like it if you already did
#   POST_COMMENT  {post_id, text}                 comment on a post
#   POST_DELETE   {post_id}                       delete your own post
#   COMMENT_DELETE {post_id, comment_id}          delete your comment (or any comment on your post)
#   FEED          {posts, more, append}           newest posts, each {id, author, text, has_image, created, likes, comments}
#   POST_NEW      {post}                          somebody shared a post
#   POST_IMAGE    {post_id, image}                the photo you asked for
#   POST_LIKES    {post_id, likes, author, actor, liked}   the full list of likers changed (actor just liked / un-liked)
#   COMMENT_NEW   {post_id, comment, post_author} a new comment
#   COMMENT_GONE  {post_id, comment_id}           a comment was deleted
#   POST_GONE     {post_id}                       a post was deleted
#   UNREAD        {counts}                        sent on login: {sender: how many DMs to you you haven't read yet}
#   TYPING        {sender, target, state}
#   READ          {message_id, reader}
#   REACTION      {message_id, emoji, action, username}
#   EDIT          {message_id, text}
#   DELETE        {message_id}
#   FILE_START    {file_id, id, sender, target, filename, size, total_chunks, ts}
#   FILE_CHUNK    {file_id, index, data}
#   FILE_END      {file_id}
#   HISTORY       {target, messages}              target: null = room, else peer username
#   COLORS        {colors}                        {username: "#rrggbb"} for everyone who picked a color
#   AVATARS       {avatars}                       {username: base64 PNG} for everyone who has a picture (sent on join)
#   AVATAR        {username, data}                one person changed their picture (data null = removed)
#   USER_DELETED  {username}                      that account is gone: remove their messages from the screen
#   PROFILE       {username, bio, pronouns, badge, banner, created_at, online, status, status_text}
#                                                  (or {username, missing: true} if there's no such account)
#   GAME_INVITE   {game_id, game, sender, expires_in}   someone invited you to play
#   GAME_STATE    {game_id, game, players, status, winner, result, ...game-specific}
#                                                  status: "pending" | "active" | "over". Sent to BOTH players after
#                                                  every change; the whole board each time, so a client never has to
#                                                  guess. (RPS never includes anyone's pick until the round is decided.)
#   GAME_EVENT    {sender, target, text, roll?}   a dice roll / coin flip result for that chat. `roll` is the raw result so
#                                                  the client can animate it: {kind:"coin", result:"Heads"|"Tails"} or
#                                                  {kind:"dice", sides, results:[...]}; `text` is the caption (and what older clients show)
#   PAY_WALLET_STATE {account, balance, balance_error, totals, currency, requests}
#                                                  account: "none" | "incomplete" | "ready"
#   PAY_UPDATE    {request, event}                one request's latest state (sent to both people);
#                                                  event: "new" | "update" | "paid" | "open" (sent on login)
#   PAY_LINK      {url, purpose, request_id}      open this Stripe page in the browser;
#                                                  purpose: "onboard" | "dashboard" | "checkout"
#   ERROR         {text, fatal?}                  fatal = the server is hanging up (e.g. wrong password)
#
# AUTH (client -> server) is {username, password}. It must be the FIRST message, over TLS.
#
# LOGIN = password + Google Authenticator code (every account, no exceptions). After a correct password:
#   Server -> Client  MFA_REQUIRED {}                       this account already has an authenticator: send a code
#   Server -> Client  MFA_SETUP    {secret, uri, issuer}    first login: show the QR code (uri) / key (secret),
#                                                           the person adds it to Google Authenticator, then sends a code
#   Client -> Server  MFA_CODE     {code}                   the 6 digits the app shows right now
#   Server -> Client  MFA_OK       {username}               accepted (username = the name exactly as stored) -- the
#                                                           normal stream (colors, history...) follows
#   Server -> Client  MFA_FAIL     {text, attempts_left}    wrong/expired code; send another MFA_CODE
#   (too many wrong codes -> ERROR {fatal: true} and the connection closes)

AUTH = "auth"
ACCOUNT = "account"                # client -> server (before login): {action, ...fields}  one account request
ACCOUNT_RESULT = "account_result"  # server -> client: {ok, message, questions?}
TEXT = "text"
SYSTEM = "system"
PRESENCE = "presence"
FEED_GET = "feed_get"
POST_CREATE = "post_create"
POST_IMAGE_GET = "post_image_get"
POST_LIKE = "post_like"
POST_COMMENT = "post_comment"
POST_DELETE = "post_delete"
COMMENT_DELETE = "comment_delete"
FEED = "feed"
POST_NEW = "post_new"
POST_IMAGE = "post_image"
POST_LIKES = "post_likes"
COMMENT_NEW = "comment_new"
COMMENT_GONE = "comment_gone"
POST_GONE = "post_gone"
UNREAD = "unread"                  # server -> client: {counts: {sender: n}} DMs that arrived while you were away
TYPING = "typing"
READ = "read"
REACTION = "reaction"
EDIT = "edit"
DELETE = "delete"
FILE_START = "file_start"
FILE_CHUNK = "file_chunk"
FILE_END = "file_end"
HISTORY = "history"
HISTORY_REQUEST = "history_request"
FILE_FETCH = "file_fetch"          # client -> server: {message_id}  ask to re-stream an old file
SET_COLOR = "set_color"        # client -> server: {color}
COLORS = "colors"              # server -> client: {colors: {username: "#rrggbb"}}
SET_AVATAR = "set_avatar"      # client -> server: {data}
AVATARS = "avatars"            # server -> client: {avatars: {username: b64png}}
AVATAR = "avatar"              # server -> client: {username, data}
ACCOUNT_DELETED = "account_deleted"  # client -> server: {}
USER_DELETED = "user_deleted"            # server -> client: {username}
SET_STATUS = "set_status"          # client -> server: {status, text}
SET_PROFILE = "set_profile"        # client -> server: {bio, pronouns, badge, banner}
PROFILE_REQUEST = "profile_request"  # client -> server: {username}
PROFILE = "profile"                # server -> client: one person's profile card data
GAME_INVITE = "game_invite"        # both directions (see above)
GAME_RESPOND = "game_respond"      # client -> server
GAME_MOVE = "game_move"            # client -> server
GAME_QUIT = "game_quit"            # client -> server
GAME_ROLL = "game_roll"            # client -> server
GAME_STATE = "game_state"          # server -> client
GAME_EVENT = "game_event"          # server -> client
PAY_WALLET = "pay_wallet"                  # client -> server
PAY_ONBOARD = "pay_onboard"                # client -> server
PAY_DASHBOARD = "pay_dashboard"            # client -> server
PAY_REQUEST = "pay_request"                # client -> server
PAY_RESPOND = "pay_respond"                # client -> server
PAY_WALLET_STATE = "pay_wallet_state"      # server -> client
PAY_UPDATE = "pay_update"                  # server -> client
PAY_LINK = "pay_link"                      # server -> client
AI_GET = "ai_get"                          # client -> server
AI_SAVE = "ai_save"                        # client -> server
AI_SEND = "ai_send"                        # client -> server
AI_RESET = "ai_reset"                      # client -> server
AI_STATE = "ai_state"                      # server -> client: {persona|None, history, remaining, available, reason}
AI_REPLY = "ai_reply"                      # server -> client: {ok, text, remaining}
MFA_REQUIRED = "mfa_required"      # server -> client: {}
MFA_SETUP = "mfa_setup"            # server -> client: {secret, uri, issuer}
MFA_CODE = "mfa_code"              # client -> server: {code}
MFA_OK = "mfa_ok"                  # server -> client: {username}
MFA_FAIL = "mfa_fail"              # server -> client: {text, attempts_left}
MFA_MAX_ATTEMPTS = 3               # wrong codes allowed on ONE connection before the server hangs up
MFA_TIMEOUT_SECONDS = 180          # how long a person gets to open the app and type the code
ERROR = "error"

# ─────────────────────────────────────────────────────────────
# STATUSES: key -> (emoji, fun name, what it means)
# "idle" is set automatically by the client after a few minutes of no
# activity; it is never saved. "ghost" = you show up as offline to others.
# ─────────────────────────────────────────────────────────────
STATUSES = {
    "active":   ("🟢", "Vibing",     "Active -- around and happy to chat"),
    "studying": ("📚", "Studying",   "Busy with the books"),
    "gaming":   ("🎮", "Gaming",     "In the zone"),
    "snacking": ("🍕", "Snack break", "Back in a few"),
    "napping":  ("😴", "Napping",    "Away -- might take a while to answer"),
    "dnd":      ("🔒", "Locked in",  "Do Not Disturb -- no notification sounds"),
    "ghost":    ("👻", "Ghost mode", "Appear offline to everyone"),
    "idle":     ("🌙", "Zoning out", "Idle -- no activity for a while (automatic)"),
}
DEFAULT_STATUS = "active"
PICKABLE_STATUSES = ["active", "studying", "gaming", "snacking", "napping", "dnd", "ghost"]
IDLE_AFTER_SECONDS = 5 * 60
STATUS_TEXT_MAX = 40
BIO_MAX = 160
PRONOUNS_MAX = 24
BADGE_MAX = 8
