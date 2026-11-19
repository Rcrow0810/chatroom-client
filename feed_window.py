# feed_window.py
# ---------------------------------------------------------
# THE FEED: an Instagram-style wall everybody on the server shares.
#   * share a post (words, a photo, or both)
#   * like a post (tap the heart, or double-click its photo)
#   * comment on posts
#   * delete your own posts, and comments on your posts
#
# This window only DRAWS things and sends small requests. The server keeps the posts in the database and tells
# every connected client what changed, so everything updates live. Captions, comments and photos are encrypted
# with the chat key before they leave this computer (just like chat messages), so the server only stores
# scrambled text.
# ---------------------------------------------------------

import base64
import io
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog, ttk

from PIL import Image, ImageOps, ImageTk

import protocol as proto
import themes
from popup_kit import PillButton, add_header, messagebox

CAPTION_MAX = 1000                 # characters in a post
COMMENT_MAX = 300                  # characters in a comment
IMAGE_MAX_SIDE = 1080              # photos are shrunk to fit inside this many pixels
IMAGE_MAX_BYTES = 300 * 1024       # ...and squeezed (as JPEG) until they're under this
SHOW_WIDTH = 460                   # photos are drawn at most this wide
SHOW_MAX_HEIGHT = 560
PREVIEW_COMMENTS = 2               # comments shown under a post before "View all"
HEART_RED = "#ef4444"
PLACEHOLDER = "What's on your mind?"

_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


# ─────────────────────────────────────────────────────────────
# small helpers (no windows involved, so they're easy to test)
# ─────────────────────────────────────────────────────────────

def time_ago(iso, now=None) -> str:
    """'just now', '5m', '3h', '2d', or 'Mar 04' for a server timestamp (UTC, like 2026-03-04T10:00:00Z)."""
    try:
        then = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    secs = ((now or datetime.now(timezone.utc)) - then).total_seconds()
    if secs < 45:
        return "just now"
    if secs < 3600:
        return f"{max(1, int(secs // 60))}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    if secs < 7 * 86400:
        return f"{int(secs // 86400)}d"
    return then.astimezone().strftime("%b %d")


def compress_image(source) -> bytes:
    """Open any picture (a path or a file object) and return JPEG bytes: upright, at most IMAGE_MAX_SIDE pixels
    on the long side, and no bigger than IMAGE_MAX_BYTES (it lowers the quality, then the size, until it fits)."""
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)                 # phone photos come in rotated
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")  # JPEG has no see-through: put it on white
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        im.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE), _LANCZOS)
    buf = io.BytesIO()
    while True:
        for quality in (85, 75, 65, 55, 45):
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() <= IMAGE_MAX_BYTES:
                return buf.getvalue()
        if max(im.size) < 240:                           # can't sensibly shrink any further
            return buf.getvalue()
        im = im.resize((max(1, int(im.width * 0.8)), max(1, int(im.height * 0.8))), _LANCZOS)


def _font(t: dict, delta: int = 0, bold: bool = False):
    return (t["font"], t["font_size"] + delta, "bold" if bold else "normal")


# ─────────────────────────────────────────────────────────────
# ONE POST
# ─────────────────────────────────────────────────────────────

class PostCard(tk.Frame):
    def __init__(self, win: "FeedWindow", post: dict):
        super().__init__(win.list_frame, bg=win.card, highlightthickness=1, highlightbackground=win.border)
        self.win, self.post = win, post
        self.owner, self.t = win.owner, win.t
        self.expanded = False                    # showing every comment, not just the latest few
        self._photo = None                       # keeps the Tk image alive
        t, card, fg, muted = self.t, win.card, self.t["text"], self.t["muted"]
        author, post_id = post["author"], post["id"]

        # who + when (+ a bin on your own posts)
        head = tk.Frame(self, bg=card)
        head.pack(fill="x", padx=12, pady=(10, 8))
        self._avatar = self.owner.avatar_for(author, 36)
        tk.Label(head, image=self._avatar, bg=card).pack(side="left")
        name = tk.Label(head, text=author, bg=card, fg=self.owner.color_for(author), font=_font(t, 0, True),
                        cursor="hand2")
        name.pack(side="left", padx=(10, 0))
        name.bind("<Button-1>", lambda e: self.owner.show_profile(author))
        if author == self.owner.username:
            bin_ = tk.Label(head, text="🗑", bg=card, fg=muted, font=_font(t, 1), cursor="hand2")
            bin_.pack(side="right", padx=(10, 0))
            bin_.bind("<Button-1>", lambda e: win.delete_post(post_id))
        self.when = tk.Label(head, bg=card, fg=muted, font=_font(t, -1))
        self.when.pack(side="right")
        self.refresh_time()

        # the photo (arrives a moment after the post; double-click it to like, like on Instagram)
        self.photo_label = None
        if post["has_image"]:
            self.photo_label = tk.Label(self, text="Loading photo…", bg=win.field, fg=muted, font=_font(t, -1),
                                        pady=70)
            self.photo_label.pack(fill="x")
            self.photo_label.bind("<Double-Button-1>", lambda e: win.like(post_id))

        # heart + comment button, and who liked it
        acts = tk.Frame(self, bg=card)
        acts.pack(fill="x", padx=12, pady=(8, 0))
        self.heart = tk.Label(acts, text="♡", bg=card, fg=fg, font=_font(t, 8), cursor="hand2")
        self.heart.pack(side="left")
        self.heart.bind("<Button-1>", lambda e: win.like(post_id))
        talk = tk.Label(acts, text="💬", bg=card, fg=fg, font=_font(t, 5), cursor="hand2")
        talk.pack(side="left", padx=(12, 0))
        talk.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.likes_lbl = tk.Label(self, anchor="w", bg=card, fg=fg, font=_font(t, -1, True), cursor="hand2")
        self.likes_lbl.pack(fill="x", padx=12)
        self.likes_lbl.bind("<Button-1>", lambda e: self._show_likers())

        # the words
        if post["text"]:
            tk.Label(self, text=post["text"], anchor="w", justify="left", bg=card, fg=fg, font=_font(t),
                     wraplength=SHOW_WIDTH - 24).pack(fill="x", padx=12, pady=(4, 0))

        # comments, then the box to write one
        self.comments_box = tk.Frame(self, bg=card)
        self.comments_box.pack(fill="x", padx=12, pady=(6, 0))
        erow = tk.Frame(self, bg=card)
        erow.pack(fill="x", padx=12, pady=(6, 10))
        self.entry = tk.Entry(erow, bg=win.field, fg=t["input_fg"], insertbackground=t["accent"], relief="flat",
                              highlightthickness=1, highlightbackground=win.border, highlightcolor=t["accent"],
                              font=_font(t), validate="key",
                              validatecommand=(self.register(lambda s: len(s) <= COMMENT_MAX), "%P"))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self._submit_comment())
        send = tk.Label(erow, text="Post", bg=card, fg=t["accent"], font=_font(t, 0, True), cursor="hand2")
        send.pack(side="right", padx=(10, 2))
        send.bind("<Button-1>", lambda e: self._submit_comment())

        self.refresh_likes()
        self.refresh_comments()

    # ── updates ───────────────────────────────────────────────
    def refresh_time(self):
        self.when.config(text=time_ago(self.post.get("created")))

    def refresh_likes(self):
        likes = self.post["likes"]
        liked = self.owner.username in likes
        self.heart.config(text="♥" if liked else "♡", fg=HEART_RED if liked else self.t["text"])
        if likes:
            self.likes_lbl.config(text=f"{len(likes)} like{'s' if len(likes) != 1 else ''}", fg=self.t["text"])
        else:
            self.likes_lbl.config(text="Be the first to like this", fg=self.t["muted"])

    def refresh_comments(self):
        for child in self.comments_box.winfo_children():
            child.destroy()
        t, card = self.t, self.win.card
        comments = self.post["comments"]
        shown = comments
        if len(comments) > PREVIEW_COMMENTS:
            text = "Hide comments" if self.expanded else f"View all {len(comments)} comments"
            link = tk.Label(self.comments_box, text=text, anchor="w", bg=card, fg=t["muted"], font=_font(t, -1),
                            cursor="hand2")
            link.pack(fill="x", pady=(0, 2))
            link.bind("<Button-1>", lambda e: self._toggle_comments())
            if not self.expanded:
                shown = comments[-PREVIEW_COMMENTS:]
        for comment in shown:
            row = tk.Frame(self.comments_box, bg=card)
            row.pack(fill="x", pady=1)
            can_delete = self.owner.username in (comment["author"], self.post["author"])
            if can_delete:
                x = tk.Label(row, text="✕", bg=card, fg=t["muted"], font=_font(t, -2), cursor="hand2")
                x.pack(side="right", anchor="n", padx=(6, 0))
                x.bind("<Button-1>", lambda e, c=comment: self.win.delete_comment(self.post["id"], c["id"]))
            tk.Label(row, text=comment["author"], bg=card, fg=self.owner.color_for(comment["author"]),
                     font=_font(t, 0, True)).pack(side="left", anchor="n")
            tk.Label(row, text=" " + comment["text"], bg=card, fg=t["text"], font=_font(t), anchor="w",
                     justify="left", wraplength=SHOW_WIDTH - 120).pack(side="left", anchor="n")

    def set_image(self, photo):
        """photo = a Tk image, or None if it couldn't be loaded."""
        if self.photo_label is None:
            return
        if photo is None:
            self.photo_label.config(text="📷 Photo unavailable")
            return
        self._photo = photo
        self.photo_label.config(image=photo, text="", pady=0, bg=self.win.card)

    # ── actions ───────────────────────────────────────────────
    def _toggle_comments(self):
        self.expanded = not self.expanded
        self.refresh_comments()

    def _show_likers(self):
        if self.post["likes"]:
            messagebox.showinfo("Liked by", "\n".join(self.post["likes"]), parent=self.win)

    def _submit_comment(self):
        text = self.entry.get().strip()
        if text:
            self.win.comment(self.post["id"], text)
            self.entry.delete(0, "end")


# ─────────────────────────────────────────────────────────────
# THE WINDOW
# ─────────────────────────────────────────────────────────────

class FeedWindow(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("Feed")
        self.geometry("540x780")
        self.minsize(480, 560)
        self.transient(owner)

        self.posts: dict[int, dict] = {}         # id -> post (already decrypted)
        self.order: list[int] = []               # newest first
        self.cards: dict[int, PostCard] = {}
        self.images: dict[int, object] = {}      # id -> Tk photo, so a redraw doesn't fetch again
        self.requested: set[int] = set()         # photos we've already asked for
        self.more = False                        # are there older posts to load?
        self.loading = True
        self.pending_image: bytes | None = None  # the photo chosen for the post being written
        self.preview_photo = None
        self._tick_job = None
        self._colors()

        self.header = add_header(self, self.t, "Feed", "Share a moment with everyone", height=54)
        body = tk.Frame(self, bg=self.bg)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=self.bg, highlightthickness=0, yscrollincrement=30)
        self.scroll = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=self.bg)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._inner_id, width=e.width))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(seq, self._on_wheel)

        self._build_body()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.owner.send_json({"type": proto.FEED_GET})
        self._tick()

    # ── look ──────────────────────────────────────────────────
    def _colors(self):
        t = self.t = self.owner.theme
        self.bg = t["window"]
        self.card = t["input_bg"]                        # post cards
        self.border = themes.mix(t["window"], t["text"], 0.14)
        self.field = t["window"]                         # text boxes sit a shade away from the card

    def _build_body(self):
        """Everything inside the scrolling area: the 'new post' box, a status line, the posts, a 'load more' button."""
        t = self.t
        self._build_composer()
        self.status = tk.Label(self.inner, bg=self.bg, fg=t["muted"], font=_font(t), pady=30)
        self.list_frame = tk.Frame(self.inner, bg=self.bg)
        self.list_frame.pack(fill="x")
        self.more_btn = PillButton(self.inner, "Load older posts", self._load_more, t=t, style="soft", height=34)
        self._update_footer()

    def retheme(self):
        """The chat's theme changed: redraw everything in the new colors (keeping whatever is being typed)."""
        draft, photo = self.get_caption(), self.pending_image
        self._colors()
        self.configure(bg=self.bg)
        try:
            self.header.restyle(self.t)
        except Exception:
            pass
        self.canvas.configure(bg=self.bg)
        self.inner.configure(bg=self.bg)
        for child in self.inner.winfo_children():
            child.destroy()
        self.cards = {}
        self._build_body()
        if draft:
            self._hide_placeholder()
            self.caption.insert("1.0", draft)
        if photo is not None:
            self._set_preview(photo)
        for post_id in self.order:
            self._add_card(self.posts[post_id])
        self._update_footer()

    # ── the "new post" box ────────────────────────────────────
    def _build_composer(self):
        t = self.t
        self.composer = box = tk.Frame(self.inner, bg=self.card, highlightthickness=1, highlightbackground=self.border)
        box.pack(fill="x", padx=14, pady=(14, 6))
        top = tk.Frame(box, bg=self.card)
        top.pack(fill="x", padx=12, pady=(12, 6))
        self._my_avatar = self.owner.avatar_for(self.owner.username, 36)
        tk.Label(top, image=self._my_avatar, bg=self.card).pack(side="left", anchor="n")
        self.caption = tk.Text(top, height=3, wrap="word", bg=self.field, fg=t["input_fg"], relief="flat",
                               insertbackground=t["accent"], highlightthickness=1, highlightbackground=self.border,
                               highlightcolor=t["accent"], font=_font(t), padx=8, pady=6)
        self.caption.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.caption.tag_configure("ph", foreground=t["muted"])
        self._placeholder_on = False
        self._show_placeholder()
        self.caption.bind("<FocusIn>", lambda e: self._hide_placeholder())
        self.caption.bind("<FocusOut>", lambda e: self._show_placeholder())
        self.caption.bind("<KeyRelease>", lambda e: self._on_caption_key())
        self.caption.bind("<Control-Return>", lambda e: (self.share(), "break")[1])

        self.preview_row = tk.Frame(box, bg=self.card)           # shown once a photo is picked
        self.preview_label = tk.Label(self.preview_row, bg=self.card)
        self.preview_label.pack(side="left")
        remove = tk.Label(self.preview_row, text="✕ Remove photo", bg=self.card, fg=t["muted"], font=_font(t, -1),
                          cursor="hand2")
        remove.pack(side="left", padx=12)
        remove.bind("<Button-1>", lambda e: self._clear_photo())

        self.btn_row = row = tk.Frame(box, bg=self.card)
        row.pack(fill="x", padx=12, pady=(2, 12))
        PillButton(row, "📷  Add photo", self.choose_photo, t=t, style="soft", height=32).pack(side="left")
        self.share_btn = PillButton(row, "Share", self.share, t=t, height=32, width=90)
        self.share_btn.pack(side="right")
        self.counter = tk.Label(row, text="", bg=self.card, fg=t["muted"], font=_font(t, -1))
        self.counter.pack(side="right", padx=10)

    def _show_placeholder(self):
        if not self._placeholder_on and not self.caption.get("1.0", "end-1c").strip():
            self.caption.delete("1.0", "end")
            self.caption.insert("1.0", PLACEHOLDER, "ph")
            self._placeholder_on = True

    def _hide_placeholder(self):
        if self._placeholder_on:
            self.caption.delete("1.0", "end")
            self._placeholder_on = False

    def get_caption(self) -> str:
        return "" if self._placeholder_on else self.caption.get("1.0", "end-1c").strip()

    def _on_caption_key(self):
        text = self.caption.get("1.0", "end-1c")
        if len(text) > CAPTION_MAX:
            self.caption.delete(f"1.0+{CAPTION_MAX}c", "end")
            text = text[:CAPTION_MAX]
        self.counter.config(text=f"{len(text)}/{CAPTION_MAX}" if len(text) > CAPTION_MAX * 0.8 else "")

    def choose_photo(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a photo", filetypes=[
            ("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = compress_image(path)
        except Exception:
            messagebox.showerror("Photo", "That file couldn't be opened as a picture.", parent=self)
            return
        self._set_preview(data)

    def _set_preview(self, data: bytes):
        self.pending_image = data
        with Image.open(io.BytesIO(data)) as im:
            im.thumbnail((140, 140), _LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(im)
        self.preview_label.config(image=self.preview_photo)
        self.preview_row.pack(fill="x", padx=12, pady=(0, 6), before=self.btn_row)

    def _clear_photo(self):
        self.pending_image = None
        self.preview_row.pack_forget()

    def share(self):
        text = self.get_caption()
        if not text and self.pending_image is None:
            return
        msg = {"type": proto.POST_CREATE, "text": self.owner.encrypt(text)}
        if self.pending_image is not None:
            msg["image"] = self.owner.encrypt(base64.b64encode(self.pending_image).decode("ascii"))
        self.owner.send_json(msg)
        # empty the box; the post itself shows up when the server announces it
        self.caption.delete("1.0", "end")
        self._placeholder_on = False
        self._show_placeholder()
        self.counter.config(text="")
        self._clear_photo()
        self.share_btn.config(state="disabled")                  # the server asks for a short pause between posts
        self.after(2000, lambda: self.share_btn.winfo_exists() and self.share_btn.config(state="normal"))

    # ── the posts ─────────────────────────────────────────────
    def _prep(self, p: dict) -> dict:
        """A post as the server sent it -> the same post with its words decrypted."""
        decrypt = self.owner.decrypt
        return {"id": p["id"], "author": p["author"], "text": decrypt(p.get("text") or ""),
                "has_image": bool(p.get("has_image")), "created": p.get("created"),
                "likes": list(p.get("likes") or []),
                "comments": [self._prep_comment(c) for c in p.get("comments") or []]}

    def _prep_comment(self, c: dict) -> dict:
        return {"id": c["id"], "author": c["author"], "text": self.owner.decrypt(c.get("text") or ""),
                "created": c.get("created")}

    def _add_card(self, post: dict, top: bool = False):
        card = PostCard(self, post)
        slaves = self.list_frame.pack_slaves()
        if top and slaves:
            card.pack(fill="x", padx=14, pady=6, before=slaves[0])
        else:
            card.pack(fill="x", padx=14, pady=6)
        self.cards[post["id"]] = card
        if post["has_image"]:
            if post["id"] in self.images:
                card.set_image(self.images[post["id"]])
            elif post["id"] not in self.requested:
                self.requested.add(post["id"])
                self.owner.send_json({"type": proto.POST_IMAGE_GET, "post_id": post["id"]})

    def _update_footer(self):
        if self.loading:
            self.status.config(text="Loading…")
        elif not self.order:
            self.status.config(text="No posts yet — be the first to share something!")
        if self.loading or not self.order:
            self.status.pack(before=self.list_frame)
        else:
            self.status.pack_forget()
        if self.more:
            self.more_btn.pack(pady=(4, 18))
        else:
            self.more_btn.pack_forget()

    def _load_more(self):
        if self.order:
            self.owner.send_json({"type": proto.FEED_GET, "before": min(self.order)})

    def _remove_card(self, post_id: int):
        card = self.cards.pop(post_id, None)
        if card is not None:
            card.destroy()
        self.posts.pop(post_id, None)
        self.images.pop(post_id, None)
        if post_id in self.order:
            self.order.remove(post_id)

    # ── what the window asks the server to do ─────────────────
    def like(self, post_id: int):
        self.owner.send_json({"type": proto.POST_LIKE, "post_id": post_id})

    def comment(self, post_id: int, text: str):
        self.owner.send_json({"type": proto.POST_COMMENT, "post_id": post_id,
                              "text": self.owner.encrypt(text[:COMMENT_MAX])})

    def delete_post(self, post_id: int):
        if messagebox.askyesno("Delete post", "Delete this post? Its likes and comments will go too.", parent=self):
            self.owner.send_json({"type": proto.POST_DELETE, "post_id": post_id})

    def delete_comment(self, post_id: int, comment_id: int):
        self.owner.send_json({"type": proto.COMMENT_DELETE, "post_id": post_id, "comment_id": comment_id})

    # ── what the server tells the window ──────────────────────
    def on_feed(self, msg: dict):
        self.loading = False
        if not msg.get("append"):
            for card in self.cards.values():
                card.destroy()
            self.cards, self.posts, self.order = {}, {}, []
        for wire in msg.get("posts") or []:
            if wire["id"] in self.posts:
                continue
            post = self._prep(wire)
            self.posts[post["id"]] = post
            self.order.append(post["id"])
            self._add_card(post)
        self.more = bool(msg.get("more"))
        self._update_footer()

    def on_new_post(self, wire: dict):
        if wire["id"] in self.posts:
            return
        post = self._prep(wire)
        self.posts[post["id"]] = post
        self.order.insert(0, post["id"])
        self._add_card(post, top=True)
        self._update_footer()
        if post["author"] == self.owner.username:
            self.canvas.yview_moveto(0)                          # your own post: jump up to see it

    def on_image(self, msg: dict):
        post_id = msg.get("post_id")
        photo = None
        try:
            raw = base64.b64decode(self.owner.decrypt(msg.get("image") or ""), validate=True)
            with Image.open(io.BytesIO(raw)) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                room = min(SHOW_WIDTH, max(220, self.canvas.winfo_width() - 60))
                scale = min(room / im.width, SHOW_MAX_HEIGHT / im.height, 1.0)
                if scale < 1.0:
                    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), _LANCZOS)
                photo = ImageTk.PhotoImage(im)
        except Exception:
            photo = None
        if photo is not None:
            self.images[post_id] = photo
        card = self.cards.get(post_id)
        if card is not None:
            card.set_image(photo)

    def on_likes(self, msg: dict):
        post = self.posts.get(msg.get("post_id"))
        if post is not None:
            post["likes"] = list(msg.get("likes") or [])
            self.cards[post["id"]].refresh_likes()

    def on_comment(self, msg: dict):
        post = self.posts.get(msg.get("post_id"))
        comment = msg.get("comment") or {}
        if post is None or any(c["id"] == comment.get("id") for c in post["comments"]):
            return
        post["comments"].append(self._prep_comment(comment))
        self.cards[post["id"]].refresh_comments()

    def on_comment_gone(self, msg: dict):
        post = self.posts.get(msg.get("post_id"))
        if post is not None:
            post["comments"] = [c for c in post["comments"] if c["id"] != msg.get("comment_id")]
            self.cards[post["id"]].refresh_comments()

    def on_post_gone(self, msg: dict):
        self._remove_card(msg.get("post_id"))
        self._update_footer()

    def on_user_deleted(self, name: str):
        """Someone deleted their account: their posts, comments and likes disappear."""
        for post_id in [i for i, p in self.posts.items() if p["author"] == name]:
            self._remove_card(post_id)
        for post in self.posts.values():
            post["comments"] = [c for c in post["comments"] if c["author"] != name]
            post["likes"] = [n for n in post["likes"] if n != name]
            card = self.cards.get(post["id"])
            if card is not None:
                card.refresh_comments()
                card.refresh_likes()
        self._update_footer()

    # ── housekeeping ──────────────────────────────────────────
    def _on_wheel(self, event):
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        up = getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0
        self.canvas.yview_scroll(-2 if up else 2, "units")

    def _tick(self):
        """Once a minute, refresh the '5m' / '3h' labels."""
        try:
            for card in self.cards.values():
                card.refresh_time()
            self._tick_job = self.after(60_000, self._tick)
        except tk.TclError:
            pass                                                 # the window is already gone

    def close(self):
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
        self.destroy()
