# games.py
# ---------------------------------------------------------
# Game rules and bookkeeping. This file knows NOTHING about
# sockets or Tkinter -- it only takes "who did what" and hands
# back "who should be told what", which is why it can be tested
# on its own. server.py is the thin layer that plugs it in.
#
# The server is the referee: it owns every board, checks every
# move, and rolls every die. A modified client can't cheat
# because it never decides anything -- it only asks.
#
# Games (two players, invite first):
#   ttt  - Tic-Tac-Toe
#   rps  - Rock-Paper-Scissors, first to 2 round wins
# Instant (no invite):
#   dice - /roll, /roll 2d20, /roll d100
#   coin - /flip
#
# Nothing here is saved to the database. Games live in memory
# and disappear when they end or when the server restarts.
# ---------------------------------------------------------

import random
import secrets
import threading
import time
import uuid

import protocol as proto

GAME_NAMES = {"ttt": "Tic-Tac-Toe", "rps": "Rock-Paper-Scissors"}
INVITE_TTL = 120            # seconds an unanswered invite stays open
MAX_LIVE_GAMES_PER_USER = 4   # pending + active, so nobody can flood someone with invites
ROLL_COOLDOWN = 0.6         # seconds between dice/coin rolls per person

DICE_SIDES = (4, 6, 8, 10, 12, 20, 100)
MAX_DICE = 5

RPS_CHOICES = ("rock", "paper", "scissors")
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
RPS_WINS_NEEDED = 2

TTT_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))

_rng = secrets.SystemRandom()   # unpredictable, so nobody can guess the next roll


# ─────────────────────────────────────────────────────────────
# One game
# ─────────────────────────────────────────────────────────────
class Game:
    """Shared bits: id, kind, the two players, and where it is in its life.
    status: "pending" (invite sent) -> "active" -> "over"."""

    def __init__(self, kind: str, inviter: str, invitee: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.players = [inviter, invitee]
        self.status = "pending"
        self.created = time.time()
        self.winner = None          # a username, or None for a draw / no result
        self.result_text = ""

    def other(self, user: str) -> str:
        return self.players[1] if user == self.players[0] else self.players[0]

    def start(self):
        self.status = "active"

    def finish(self, winner, text: str):
        self.status = "over"
        self.winner = winner
        self.result_text = text

    def move(self, user: str, move):    # overridden
        return "That game doesn't take moves."

    def public_state(self) -> dict:
        return {"type": proto.GAME_STATE, "game_id": self.id, "game": self.kind,
                "players": list(self.players), "status": self.status,
                "winner": self.winner, "result": self.result_text}


class TicTacToe(Game):
    def __init__(self, inviter, invitee):
        super().__init__("ttt", inviter, invitee)
        self.board = [None] * 9
        # the inviter plays X; who goes first is random so there's no built-in advantage
        self.turn = _rng.choice(self.players)
        self.line = None

    def mark_of(self, user):
        return "X" if user == self.players[0] else "O"

    def move(self, user, cell):
        if self.status != "active":
            return "That game isn't running."
        if user != self.turn:
            return "It's not your turn."
        if not isinstance(cell, int) or isinstance(cell, bool) or not 0 <= cell <= 8:
            return "That isn't a square."
        if self.board[cell] is not None:
            return "That square is taken."
        mark = self.mark_of(user)
        self.board[cell] = mark
        for line in TTT_LINES:
            if all(self.board[i] == mark for i in line):
                self.line = list(line)
                self.finish(user, f"{user} won Tic-Tac-Toe against {self.other(user)}!")
                return None
        if all(c is not None for c in self.board):
            self.finish(None, f"Tic-Tac-Toe between {self.players[0]} and {self.players[1]} was a draw.")
            return None
        self.turn = self.other(user)
        return None

    def public_state(self):
        s = super().public_state()
        s.update(board=list(self.board), turn=self.turn if self.status == "active" else None,
                 marks={self.players[0]: "X", self.players[1]: "O"}, line=self.line)
        return s


class RockPaperScissors(Game):
    def __init__(self, inviter, invitee):
        super().__init__("rps", inviter, invitee)
        self.picks = {}                                  # secret until both have chosen
        self.scores = {inviter: 0, invitee: 0}
        self.round = 1
        self.last = None                                 # {"picks": {...}, "winner": name|None}

    def move(self, user, choice):
        if self.status != "active":
            return "That game isn't running."
        if choice not in RPS_CHOICES:
            return "Pick rock, paper or scissors."
        if user in self.picks:
            return "You already picked this round."
        self.picks[user] = choice
        if len(self.picks) < 2:
            return None
        a, b = self.players
        pa, pb = self.picks[a], self.picks[b]
        winner = None if pa == pb else (a if RPS_BEATS[pa] == pb else b)
        self.last = {"picks": dict(self.picks), "winner": winner}
        if winner:
            self.scores[winner] += 1
        self.picks = {}
        self.round += 1
        for name in self.players:
            if self.scores[name] >= RPS_WINS_NEEDED:
                loser = self.other(name)
                self.finish(name, f"{name} won Rock-Paper-Scissors against {loser} "
                                  f"({self.scores[name]}-{self.scores[loser]})!")
                break
        return None

    def public_state(self):
        s = super().public_state()
        # NEVER include self.picks' values here -- only whether each person has chosen yet
        s.update(scores=dict(self.scores), round=self.round, last=self.last,
                 chosen={name: name in self.picks for name in self.players},
                 wins_needed=RPS_WINS_NEEDED)
        return s


GAME_CLASSES = {"ttt": TicTacToe, "rps": RockPaperScissors}


# ─────────────────────────────────────────────────────────────
# The referee: tracks every live game
# ─────────────────────────────────────────────────────────────
class GameManager:
    """Every method returns a list of (username, message_dict) -- the server just
    delivers them. Mistakes (not your turn, no such game...) come back as an ERROR
    message to the person who made them; nothing here raises on bad input, because
    the input comes from the network and can be anything."""

    def __init__(self):
        self.games: dict[str, Game] = {}
        self._last_roll: dict[str, float] = {}
        self._lock = threading.RLock()

    # ---- helpers ------------------------------------------------------
    @staticmethod
    def _err(user, text):
        return [(user, {"type": proto.ERROR, "text": text})]

    def _live_for(self, user):
        return [g for g in self.games.values() if user in g.players and g.status in ("pending", "active")]

    def _prune_expired(self, now):
        """Drop invites nobody answered, telling the inviter."""
        out = []
        for g in list(self.games.values()):
            if g.status == "pending" and now - g.created > INVITE_TTL:
                g.finish(None, f"{g.players[1]} didn't answer the {GAME_NAMES[g.kind]} invite.")
                out += self._announce(g)
                del self.games[g.id]
        return out

    def _announce(self, game, only=None):
        state = game.public_state()
        return [(p, state) for p in game.players if only is None or p in only]

    # ---- invites ------------------------------------------------------
    def invite(self, sender, opponent, kind, is_online, now=None):
        now = now if now is not None else time.time()
        with self._lock:
            out = self._prune_expired(now)
            if kind not in GAME_CLASSES:
                return out + self._err(sender, "Unknown game.")
            if not isinstance(opponent, str) or not opponent:
                return out + self._err(sender, "Pick someone to play with.")
            if opponent == sender:
                return out + self._err(sender, "You can't play against yourself.")
            if not is_online(opponent):
                return out + self._err(sender, f"{opponent} isn't online right now.")
            if len(self._live_for(sender)) >= MAX_LIVE_GAMES_PER_USER:
                return out + self._err(sender, "You have too many games going. Finish or quit one first.")
            if len(self._live_for(opponent)) >= MAX_LIVE_GAMES_PER_USER:
                return out + self._err(sender, f"{opponent} has too many games going right now.")
            for g in self._live_for(sender):
                if g.kind == kind and opponent in g.players:
                    return out + self._err(sender, f"You already have a {GAME_NAMES[kind]} game with {opponent}.")
            game = GAME_CLASSES[kind](sender, opponent)
            game.created = now
            self.games[game.id] = game
            invite = {"type": proto.GAME_INVITE, "game_id": game.id, "game": kind,
                      "sender": sender, "expires_in": INVITE_TTL}
            # inviter gets the state (shows "waiting..."), invitee gets the invite
            return out + [(opponent, invite), (sender, game.public_state())]

    def respond(self, user, game_id, accept):
        with self._lock:
            game = self.games.get(game_id)
            if game is None or game.status != "pending" or user != game.players[1]:
                return self._err(user, "That invite isn't open anymore.")
            if accept is True:
                game.start()
                return self._announce(game)
            game.finish(None, f"{user} declined the {GAME_NAMES[game.kind]} invite.")
            out = self._announce(game)
            del self.games[game.id]
            return out

    # ---- playing ------------------------------------------------------
    def move(self, user, game_id, move):
        with self._lock:
            game = self.games.get(game_id)
            if game is None or user not in game.players:
                return self._err(user, "That game doesn't exist anymore.")
            problem = game.move(user, move)
            if problem:
                return self._err(user, problem)
            out = self._announce(game)
            if game.status == "over":
                del self.games[game.id]
            return out

    def quit(self, user, game_id):
        """Leave a game. Quitting an active game forfeits it; cancelling/declining a
        pending invite just closes it."""
        with self._lock:
            game = self.games.get(game_id)
            if game is None or user not in game.players or game.status == "over":
                return []
            other = game.other(user)
            if game.status == "active":
                game.finish(other, f"{user} left the {GAME_NAMES[game.kind]} game, so {other} wins.")
            else:
                game.finish(None, f"{user} cancelled the {GAME_NAMES[game.kind]} invite.")
            out = self._announce(game)
            del self.games[game.id]
            return out

    def player_left(self, user):
        """Called when someone disconnects: end all their games."""
        with self._lock:
            out = []
            for game in list(self._live_for(user)):
                out += self.quit(user, game.id)
            self._last_roll.pop(user, None)
            return out

    # ---- instant games ------------------------------------------------
    def roll(self, user, kind, count=1, sides=6, now=None):
        """Returns (result_text, error_text). One of them is None."""
        text, _data, error = self.roll_full(user, kind, count, sides, now)
        return text, error

    def roll_full(self, user, kind, count=1, sides=6, now=None):
        """Returns (result_text, data, error_text). `data` is the raw result clients use to ANIMATE the roll:
        {"kind": "coin", "result": "Heads"}  or  {"kind": "dice", "sides": 6, "results": [3, 5]}.
        The server decides the result here; the animation on the clients is only for show and always ends on it."""
        now = now if now is not None else time.time()
        with self._lock:
            last = self._last_roll.get(user)
            if last is not None and now - last < ROLL_COOLDOWN:
                return None, None, "Slow down a little!"
            if kind == "coin":
                self._last_roll[user] = now
                side = _rng.choice(["Heads", "Tails"])
                return f"🪙 {user} flipped a coin: {side}!", {"kind": "coin", "result": side}, None
            if kind != "dice":
                return None, None, "Unknown game."
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_DICE:
                return None, None, f"You can roll 1 to {MAX_DICE} dice at a time."
            if sides not in DICE_SIDES:
                return None, None, "Dice sizes: " + ", ".join(f"d{s}" for s in DICE_SIDES) + "."
            self._last_roll[user] = now
            rolls = [_rng.randint(1, sides) for _ in range(count)]
            label = f"{count}d{sides}" if count > 1 else f"d{sides}"
            data = {"kind": "dice", "sides": sides, "results": rolls}
            if count == 1:
                return f"🎲 {user} rolled a {label}: {rolls[0]}", data, None
            return f"🎲 {user} rolled {label}: {' + '.join(map(str, rolls))} = {sum(rolls)}", data, None


def parse_roll(text: str):
    """'' -> (1, 6); '2d20' -> (2, 20); 'd100' -> (1, 100); '20' -> (1, 20).
    Returns (count, sides) or None if it doesn't make sense."""
    t = (text or "").strip().lower()
    if not t:
        return 1, 6
    try:
        if "d" in t:
            left, right = t.split("d", 1)
            return (int(left) if left else 1), int(right)
        return 1, int(t)
    except ValueError:
        return None
