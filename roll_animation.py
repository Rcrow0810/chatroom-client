# roll_animation.py
# ---------------------------------------------------------
# The little animation that plays in the chat when somebody rolls dice or flips a coin:
#   * a coin that is tossed up, spins, and lands showing Heads or Tails
#   * dice that tumble, flicker through numbers, slow down, and land on their number
#
# IMPORTANT: this is only for show. The SERVER rolls the dice and flips the coin (see games.py), so nobody can
# cheat; this code is handed the result and always finishes on exactly that.
#
# The maths (poses) and the drawing are plain functions, separate from the Tk widget, so they can be tested
# without a window. RollAnimation at the bottom is the widget the chat puts into the message log.
# ---------------------------------------------------------

import math
import random
import time
import tkinter as tk

FRAME_MS = 30                      # ~33 frames per second
COIN_MS = 1500                     # how long a coin toss lasts
DIE_MS = 1100                      # how long the first die tumbles; each further die goes a bit longer
DIE_STAGGER_MS = 180
CANVAS_H = 160

GOLD, GOLD_RIM, GOLD_INK = "#F5C542", "#C99A1E", "#8A6510"
DIE_FACE, DIE_INK = "#FFFFFF", "#1F2937"

# faces of the die, as (column, row) pip positions on a 3x3 grid
PIPS = {
    1: [(0, 0)],
    2: [(-1, -1), (1, 1)],
    3: [(-1, -1), (0, 0), (1, 1)],
    4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
    5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
    6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)],
}
# how many corners to draw for each kind of die (d6 is the pipped square)
POLYGON_SIDES = {4: 3, 8: 4, 10: 5, 12: 5, 20: 6, 100: 8}


# ─────────────────────────────────────────────────────────────
# POSES (pure maths: given the time, where is everything?)
# ─────────────────────────────────────────────────────────────

def coin_pose(elapsed_ms: float, result: str) -> dict:
    """Where the coin is `elapsed_ms` after it was thrown. It always ends flat, showing `result`.
    Returns {"lift": 0..1 (how high above the ground), "scale": 0.08..1 (how edge-on it is), "face": "Heads"|"Tails"}."""
    p = max(0.0, min(1.0, elapsed_ms / COIN_MS))
    half_turns = 8 if result == "Heads" else 9          # starts showing Heads, so an odd number of half-turns lands on Tails
    spin = 1 - (1 - p) ** 3                            # fast at first, slowing as it lands
    phase = half_turns * spin                          # in half-turns
    face = "Heads" if round(phase) % 2 == 0 else "Tails"
    scale = max(0.08, abs(math.cos(math.pi * phase)))
    lift = 4 * p * (1 - p)                             # a smooth up-and-down arc
    if p >= 1.0:
        face, scale, lift = result, 1.0, 0.0
    return {"lift": lift, "scale": scale, "face": face}


class Die:
    """One tumbling die: what number it shows, how it's turned and how high it's bouncing, at any moment."""

    def __init__(self, sides: int, result: int, duration_ms: float, rng=random):
        self.sides, self.result, self.duration = sides, result, duration_ms
        self._rng = rng
        self.turn = rng.choice((-1, 1))                 # which way it spins
        self._shown = result
        self._next_change = 0.0

    def pose(self, elapsed_ms: float) -> dict:
        q = max(0.0, min(1.0, elapsed_ms / self.duration))
        if q >= 1.0:
            return {"value": self.result, "angle": 0.0, "lift": 0.0, "shake": 0.0, "done": True}
        if elapsed_ms >= self._next_change:             # flicker to a new number, more and more slowly
            choices = [n for n in range(1, self.sides + 1) if n != self._shown] or [self.result]
            self._shown = self._rng.choice(choices)
            self._next_change = elapsed_ms + 40 + 150 * q * q
        return {"value": self._shown,
                "angle": self.turn * 720.0 * (1 - q) ** 2,                       # spins fast, then settles flat
                "lift": abs(math.sin(q * math.pi * 3)) * (1 - q),              # three bounces, each smaller
                "shake": math.sin(elapsed_ms / 23.0) * 3.0 * (1 - q),
                "done": False}


# ─────────────────────────────────────────────────────────────
# DRAWING (works on anything with Tk Canvas's create_* methods)
# ─────────────────────────────────────────────────────────────

def _rotate(points, angle_deg, cx, cy):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in points]


def _flat(points):
    return [c for p in points for c in p]


def draw_coin(c, width: int, ground: int, pose: dict, colors: dict):
    radius = 30
    cx = width / 2
    lift = pose["lift"] * 58
    cy = ground - radius - lift
    # shadow on the ground: smaller and fainter the higher the coin is
    shrink = 1 - 0.45 * pose["lift"]
    c.create_oval(cx - radius * shrink, ground - 4, cx + radius * shrink, ground + 6, fill=colors["shadow"], outline="")
    half_h = max(2.0, radius * pose["scale"])
    c.create_oval(cx - radius, cy - half_h, cx + radius, cy + half_h, fill=GOLD, outline=GOLD_RIM, width=3)
    if pose["scale"] > 0.3:                              # the engraved ring and the letter, only when it's face-on enough
        r2, h2 = radius * 0.74, half_h * 0.74
        c.create_oval(cx - r2, cy - h2, cx + r2, cy + h2, fill="", outline=GOLD_RIM, width=2)
        c.create_text(cx, cy, text="H" if pose["face"] == "Heads" else "T", fill=GOLD_INK, font=("Segoe UI", 20, "bold"))


def _die_outline(sides: int, cx: float, cy: float, size: float, angle: float):
    if sides == 6:
        h = size / 2
        return _rotate([(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)], angle, cx, cy)
    n = POLYGON_SIDES.get(sides, 6)
    r = size * 0.62
    points = [(cx + r * math.cos(math.radians(-90 + 360 * i / n)),
               cy + r * math.sin(math.radians(-90 + 360 * i / n))) for i in range(n)]
    return _rotate(points, angle, cx, cy)


def draw_die(c, cx: float, cy: float, sides: int, value: int, angle: float, colors: dict, size: float = 52):
    pts = _die_outline(sides, cx, cy, size, angle)
    if sides == 6:
        # a thick outline with round joins gives the square rounded corners
        c.create_polygon(_flat(pts), fill=DIE_FACE, outline=DIE_FACE, width=8, joinstyle="round")
        c.create_polygon(_flat(pts), fill=DIE_FACE, outline=colors["die_edge"], width=2)
        if value in PIPS:
            step = size * 0.27
            for col, row in PIPS[value]:
                (px, py), = _rotate([(cx + col * step, cy + row * step)], angle, cx, cy)
                c.create_oval(px - 4.5, py - 4.5, px + 4.5, py + 4.5, fill=DIE_INK, outline="")
    else:
        c.create_polygon(_flat(pts), fill=colors["accent"], outline=colors["die_edge"], width=2, joinstyle="round")
        c.create_text(cx, cy, text=str(value), fill=colors["accent_text"],
                      font=("Segoe UI", 15 if value < 100 else 12, "bold"))


# ─────────────────────────────────────────────────────────────
# THE WIDGET
# ─────────────────────────────────────────────────────────────

class RollAnimation(tk.Canvas):
    """Put this in the message log: it plays the roll once, then stays there showing the result and `caption`.
        roll    = {"kind": "coin", "result": "Heads"}  or  {"kind": "dice", "sides": 6, "results": [3, 5]}
        colors  = {"bg", "fg", "accent", "accent_text", "shadow", "die_edge"}"""

    def __init__(self, parent, roll: dict, caption: str, colors: dict):
        self.roll, self.caption, self.colors = roll, caption, colors
        self.is_coin = roll.get("kind") == "coin"
        if self.is_coin:
            self.dice = []
            width, self.total_ms = 240, COIN_MS
        else:
            results = [int(n) for n in roll.get("results") or []]
            sides = int(roll.get("sides") or 6)
            self.dice = [Die(sides, value, DIE_MS + DIE_STAGGER_MS * i) for i, value in enumerate(results)]
            width = max(240, 76 * len(self.dice) + 24)
            self.total_ms = max((d.duration for d in self.dice), default=0)
        super().__init__(parent, width=width, height=CANVAS_H, bg=colors["bg"], highlightthickness=0, bd=0)
        self._pix_w = width
        self._t0 = time.monotonic()
        self._job = None
        self.bind("<Destroy>", self._stop, add="+")
        self._step()

    def recolor(self, colors: dict):
        """The chat's theme changed: use the new colors (a finished roll is simply drawn again)."""
        self.colors = colors
        self.configure(bg=colors["bg"])
        if self._job is None:
            self._step()

    def _stop(self, _event=None):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _step(self):
        elapsed = (time.monotonic() - self._t0) * 1000
        finished = elapsed >= self.total_ms
        try:
            self.delete("all")
            self.paint(elapsed, finished)
        except tk.TclError:
            return                                       # the window was closed mid-roll
        self._job = None if finished else self.after(FRAME_MS, self._step)

    def paint(self, elapsed_ms: float, finished: bool):
        """Draw one frame (also used for the very last one, which includes the caption)."""
        if self.is_coin:
            draw_coin(self, self._pix_w, 118, coin_pose(elapsed_ms, self.roll.get("result", "Heads")), self.colors)
        else:
            gap = self._pix_w / max(1, len(self.dice))
            for i, die in enumerate(self.dice):
                pose = die.pose(elapsed_ms)
                cx = gap * (i + 0.5) + pose["shake"]
                ground = 118
                c_y = ground - 30 - pose["lift"] * 34
                c = self
                c.create_oval(cx - 22, ground - 2, cx + 22, ground + 7, fill=self.colors["shadow"], outline="")
                draw_die(c, cx, c_y, die.sides, pose["value"], pose["angle"], self.colors)
        if finished and self.caption:
            self.create_text(self._pix_w / 2, CANVAS_H - 14, text=self.caption, fill=self.colors["fg"],
                             font=("Segoe UI", 10, "bold"), width=self._pix_w - 12, justify="center")
