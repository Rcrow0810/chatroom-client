# translator.py
# ---------------------------------------------------------
# Translates INCOMING chat messages into the language you picked.
#
# WHY IT RUNS ON THE RECEIVER'S COMPUTER
# Your messages are encrypted before they leave your computer and the
# server never sees the readable text (see crypto_utils.py). So the
# server can't translate anything -- each person's own client decrypts
# a message and then translates it for its own screen. That is also why
# it works the way you wanted: you type English, your friend has Spanish
# selected, and THEIR screen shows your message in Spanish while yours
# still shows your English.
#
# HOW IT TRANSLATES (backend "auto", the default)
# 1. Google Translate, called directly over HTTPS (nothing extra to install). Google also detects what
#    language the sender wrote in, which is far more reliable than guessing on a short chat message.
#    Several messages are translated at the same time, so a reply shows up in a fraction of a second.
# 2. If Google can't be reached (offline, blocked), the OFFLINE backend (Argos Translate) takes over
#    for any language pack you installed with install_languages.py. That part is optional.
#
# PRIVACY NOTE
# While Google is used, the text of a message that gets translated is sent to Google. The rest of the
# chat stays end-to-end encrypted. If that bothers you, set DEFAULT_BACKEND = "argos" at the bottom of
# this file (offline only), or switch translation off in the Language menu.
# ---------------------------------------------------------

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

MAX_CHUNK = 4500          # Google's free endpoint refuses ~5000+ characters per request
CACHE_SIZE = 2000         # translated messages kept in memory (never written to disk)

# Bits we must not let the translator touch: links, @mentions, :emoji_codes:
_PROTECT = re.compile(r"https?://\S+|www\.\S+|@\w+|:[a-z0-9_+\-]+:", re.IGNORECASE)


# Google's free endpoint is meant for a few requests, not a stream. Hitting it too fast gets this
# computer blocked for a while ("TooManyRequests"), and every further try while blocked makes the
# block last longer. So: send one request at a time with a gap between them, and when Google says
# stop, stop asking for a few minutes instead of failing on every single message.
MIN_GAP_SECONDS = 0.0         # pause between requests (only used by a backend that sets paced = True)
COOLDOWN_SECONDS = 180        # after "too many requests": don't ask again for this long
MAX_WAITING = 200             # more than this many messages queued up -> skip extras
GOOGLE_RETRY_SECONDS = 20     # after a network failure, use the offline backend for this long before trying Google again
WORKERS = 6                   # messages translated at the same time

# deep-translator / Google call some languages by other codes. Menu code -> code Google accepts.
LANG_ALIASES = {"he": "iw", "jv": "jw", "zh": "zh-CN", "zh-cn": "zh-CN", "zh-tw": "zh-TW", "fil": "tl", "nb": "no", "nn": "no"}


def normalize_target(code: str) -> str:
    return LANG_ALIASES.get((code or "").strip().lower(), code)


class TranslatorUnavailable(RuntimeError):
    """The translation library isn't installed (or no backend could be loaded)."""


class TranslatorBusy(RuntimeError):
    """We're deliberately not asking right now (Google blocked us, or too many are queued)."""

    def __init__(self, message, retry_in=0):
        super().__init__(message)
        self.retry_in = retry_in


def friendly_error(error) -> str:
    """One plain sentence saying WHY a translation failed (for the chat window to show)."""
    name = type(error).__name__
    if isinstance(error, TranslatorUnavailable):
        return f"Translation isn't set up: {error}"
    if isinstance(error, TranslatorBusy):
        mins = max(1, round(error.retry_in / 60))
        return (f"Google asked us to slow down, so translation is paused for about {mins} min."
                if error.retry_in else "Too many messages to translate at once; some were left as they are.")
    if name == "TooManyRequests":
        return "Google blocked translation for a few minutes (too many requests)."
    if name in ("LanguageNotSupportedException", "InvalidSourceOrTargetLanguage"):
        return "Google doesn't support the language you picked."
    if name in ("RequestError", "ConnectionError", "Timeout", "ConnectTimeout", "ReadTimeout") or \
            isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return "Couldn't reach Google Translate (check the internet connection)."
    return f"Translation failed ({name})."


# ─────────────────────────────────────────────────────────────
# backends: anything with  translate(text, target_code) -> str
# ─────────────────────────────────────────────────────────────
class TooManyRequests(RuntimeError):
    """Google asked us to slow down (HTTP 429)."""


def lang_base(code: str) -> str:
    """'zh-CN' -> 'zh', 'iw' -> 'he': what two codes must share to count as the same language."""
    code = (code or "").strip().lower().replace("_", "-")
    code = {"iw": "he", "jw": "jv", "fil": "tl"}.get(code, code)
    return code.split("-")[0]


class GoogleBackend:
    """Google Translate, called directly over HTTPS with the standard library (no extra package).
    The sender's language is detected by Google. Text of any length is fine: the caller splits it
    into pieces of at most MAX_CHUNK characters and each piece is one POST request."""
    paced = False                  # requests are independent: run as many at once as we have workers
    max_waiting = 500
    URL = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, timeout: float = 8.0):
        self._timeout = timeout

    def translate_detect(self, text: str, target: str):
        """-> (translated text, detected source language code)."""
        body = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": normalize_target(target),
                                       "dt": "t", "q": text}).encode("utf-8")
        request = urllib.request.Request(self.URL, data=body, headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 403):
                raise TooManyRequests(f"HTTP {e.code}") from e
            raise
        pieces = payload[0] or []
        out = "".join(seg[0] for seg in pieces if seg and isinstance(seg[0], str))
        source = payload[2] if len(payload) > 2 and isinstance(payload[2], str) else ""
        return out, source

    def translate(self, text: str, target: str) -> str:
        out, source = self.translate_detect(text, target)
        if source and lang_base(source) == lang_base(target):
            return text                       # it was already in the target language
        return out or text

    def warm_up(self, target: str):
        """Open the connection and do the TLS handshake now, so the first real message isn't slower."""
        self.translate_detect("hello", target)


# Argos uses plain two-letter codes. Menu code -> Argos code.
ARGOS_ALIASES = {"iw": "he", "zh-cn": "zh", "zh-tw": "zh", "zh-hans": "zh", "zh-hant": "zh", "fil": "tl", "jw": "jv"}
DETECT_MIN_CONFIDENCE = 0.6

# Everyday English words. A message made ONLY of these is English, whatever the detector thinks.
COMMON_ENGLISH = set("""
a about after again all also am an and any are as at back be because been but by can could day did do does done
for from get go going good great had has have he hello hey hi him her here how i if in is it its just know like
little lol love me more morning my need never night no not now of oh ok okay on one or our out please really
right see she so some sorry sounds sure thank thanks that the their them then there they this to today tomorrow
too up us very was we well what when where which who why will with would yeah yes yesterday you your
afternoon evening bye goodbye later welcome nice cool awesome haha wow bro dude friend friends buddy
""".split())


def argos_code(code: str) -> str:
    code = (code or "").strip().lower()
    return ARGOS_ALIASES.get(code, code.split("-")[0] if code not in ARGOS_ALIASES else code)


class ArgosBackend:
    """Offline translation with Argos Translate. The sender's language is detected with `langdetect`
    (also offline). Language packs are installed once with install_languages.py. Two quiet rules:
      * a message in a language we have no pack for is simply shown as it was sent;
      * non-English -> non-English goes through English, so you need the pack pair for both languages.
    """
    paced = False          # no server to be polite to: translate as fast as the CPU allows
    max_waiting = 500      # offline work is cheap: a whole chat history can queue up

    def __init__(self):
        try:
            import argostranslate.translate as _argos
        except ImportError as e:
            raise TranslatorUnavailable("argostranslate is not installed (pip install argostranslate)") from e
        try:
            from langdetect import DetectorFactory, detect_langs
        except ImportError as e:
            raise TranslatorUnavailable("langdetect is not installed (pip install langdetect)") from e
        DetectorFactory.seed = 0                      # same text -> same answer every time
        logging.getLogger("stanza").setLevel(logging.ERROR)    # its harmless "package default expects mwt" warnings
        self._argos, self._detect_langs = _argos, detect_langs
        self._languages = None
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()            # the models run one translation at a time

    def installed(self) -> dict:
        """{code: Language} for every language pack installed."""
        with self._lock:
            if self._languages is None:
                self._languages = {lang.code: lang for lang in self._argos.get_installed_languages()}
            return self._languages

    def detect(self, text: str):
        """Best-guess language code of `text`, or None if we can't tell. Short chat messages ("hello",
        "good morning") fool language detectors, so very common English words are recognised directly and
        the detector's guesses are only trusted for languages we actually have a pack for."""
        installed = self.installed()
        words = re.findall(r"[a-z']+", text.lower())
        if words and "en" in installed and all(w in COMMON_ENGLISH for w in words):
            return "en"
        try:
            guesses = self._detect_langs(text)
        except Exception:                             # langdetect raises on text with no letters
            return None
        top = guesses[0]
        code = top.lang.split("-")[0]
        # Mostly everyday English words in plain ASCII: English, even if the detector says otherwise.
        mostly_english = (text.isascii() and "en" in installed and bool(words)
                          and sum(w in COMMON_ENGLISH for w in words) / len(words) >= 0.6)
        short_plain = text.isascii() and len(words) <= 3 and "en" in installed
        if top.prob >= DETECT_MIN_CONFIDENCE:
            if code in installed:
                return code
            return "en" if (short_plain or mostly_english) else None   # sure of a language we have no pack for
        usable = [g for g in guesses if g.lang.split("-")[0] in installed and g.prob >= 0.2]
        if usable:
            return usable[0].lang.split("-")[0]
        english = any(g.lang == "en" and g.prob >= 0.2 for g in guesses)
        return "en" if (short_plain or mostly_english or (english and "en" in installed)) else None

    def warm_up(self, target: str, max_languages: int = 4):
        """Load the models BEFORE the first real message. Loading a language pack is what makes the
        first translation slow; after that each one is quick. We load the packs that lead INTO
        `target` (a few of them, to keep memory reasonable); anything else loads when first needed."""
        langs = self.installed()
        to_lang = langs.get(argos_code(target))
        if to_lang is None:
            return
        self._detect_langs("hello, how are you today")          # also loads the language detector
        english, loaded = langs.get("en"), 0
        for code, lang in langs.items():
            if code == to_lang.code or loaded >= max_languages:
                continue
            path = lang.get_translation(to_lang)
            if path is not None:
                path.translate("ok")
            elif english is not None and lang is not english:    # no direct pack: it goes through English
                first, second = lang.get_translation(english), english.get_translation(to_lang)
                if first is None or second is None:
                    continue
                second.translate(first.translate("ok"))
            else:
                continue
            loaded += 1

    def translate(self, text: str, target: str) -> str:
        with self._run_lock:
            return self._translate_locked(text, target)

    def _translate_locked(self, text: str, target: str) -> str:
        langs = self.installed()
        to_lang = langs.get(argos_code(target))
        source = self.detect(text)
        from_lang = langs.get(source) if source else None
        if to_lang is None or from_lang is None or from_lang.code == to_lang.code:
            return text                               # nothing we can do offline -> show it as sent
        path = from_lang.get_translation(to_lang)
        if path is not None:
            return path.translate(text)
        # no direct pack (say Spanish -> French): go through English if both halves are installed
        english = langs.get("en")
        if english is not None:
            first, second = from_lang.get_translation(english), english.get_translation(to_lang)
            if first is not None and second is not None:
                return second.translate(first.translate(text))
        return text                                   # can't be done offline -> show it as sent


class AutoBackend:
    """Google first (fast, detects the sender's language), the offline Argos packs as the safety net."""
    paced = False
    max_waiting = 500

    def __init__(self):
        self._google = GoogleBackend()
        self._argos = None
        self._argos_tried = False
        self._argos_lock = threading.Lock()
        self._google_down_until = 0.0
        self._last_error = None

    def _get_argos(self):
        with self._argos_lock:
            if not self._argos_tried:
                self._argos_tried = True
                try:
                    self._argos = ArgosBackend()
                except TranslatorUnavailable:
                    self._argos = None
            return self._argos

    def _offline_ready(self, target: str):
        """The Argos backend, if it is installed AND has a pack for this language; otherwise None."""
        argos = self._get_argos()
        try:
            if argos is not None and argos_code(target) in argos.installed():
                return argos
        except Exception:
            pass
        return None

    def translate(self, text: str, target: str) -> str:
        if time.monotonic() >= self._google_down_until:
            try:
                return self._google.translate(text, target)
            except Exception as e:                    # offline, blocked, rate-limited...
                self._last_error = e
                rate_limited = type(e).__name__ == "TooManyRequests"
                # Only sit out Google when an offline pack can take over; otherwise keep trying it, so the
                # very first message after the connection comes back is translated.
                if rate_limited:
                    self._google_down_until = time.monotonic() + COOLDOWN_SECONDS
                elif self._offline_ready(target) is not None:
                    self._google_down_until = time.monotonic() + GOOGLE_RETRY_SECONDS
        argos = self._offline_ready(target)
        if argos is not None:
            try:
                return argos.translate(text, target)
            except Exception:
                pass
        raise self._last_error or TranslatorBusy("translation is unavailable right now")

    def warm_up(self, target: str):
        try:
            self._google.warm_up(target)
        except Exception:
            pass                                      # the first real message will try again


def available_language_codes() -> list[str]:
    """Offline packs installed right now (the Language menu adds Google's languages to these)."""
    try:
        return sorted(ArgosBackend().installed())
    except TranslatorUnavailable:
        return []


BACKENDS = {"auto": AutoBackend, "google": GoogleBackend, "argos": ArgosBackend}
DEFAULT_BACKEND = "auto"


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────
def _protect(text: str):
    """Swap links/@mentions for neutral tokens so the translator leaves them alone."""
    saved = []

    def grab(m):
        saved.append(m.group(0))
        return f"QQ{len(saved) - 1}QQ"

    return _PROTECT.sub(grab, text), saved


def _restore(text: str, saved: list):
    """Put the originals back. Returns None if the translator ate a token."""
    for i, original in enumerate(saved):
        token = f"QQ{i}QQ"
        if token not in text:
            return None
        text = text.replace(token, original)
    return text


_SENTENCE = re.compile(r".*?(?:[.!?。！？]+\s+|\n+|$)", re.S)


def _chunks(text: str):
    """Split very long text at sentence / line ends into pieces of at most MAX_CHUNK characters.
    Whitespace stays attached to its piece, so joining the pieces back together gives the same layout."""
    if len(text) <= MAX_CHUNK:
        return [text]
    pieces, current = [], ""
    for part in _SENTENCE.findall(text):
        if not part:
            continue
        while len(part) > MAX_CHUNK:                       # one enormous "sentence" with no stops
            cut = part.rfind(" ", 0, MAX_CHUNK)
            cut = MAX_CHUNK if cut < MAX_CHUNK // 2 else cut + 1
            if current:
                pieces.append(current)
                current = ""
            pieces.append(part[:cut])
            part = part[cut:]
        if len(current) + len(part) > MAX_CHUNK and current:
            pieces.append(current)
            current = part
        else:
            current += part
    if current:
        pieces.append(current)
    return pieces


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def needs_translation(text: str) -> bool:
    """False for things with nothing to translate (empty, only links/emoji/numbers)."""
    if not text or not text.strip():
        return False
    stripped = _PROTECT.sub("", text)
    return any(ch.isalpha() for ch in stripped)


# Translation models sometimes go off the rails on a very short input (often a single word) and write the
# same few letters over and over until they run out of room ("mainstremainstremainstre..."). Never show that.
_RUNAWAY = re.compile(r"(.{2,12}?)\1{4,}")        # the same 2-12 characters, 5+ times in a row
_SOURCE_REPEATS = re.compile(r"(.{1,12}?)\1{3,}")  # ...unless the original did it too ("jajajajaja")


def looks_broken(source: str, out: str) -> bool:
    """True when `out` looks like runaway nonsense rather than a translation of `source`."""
    if len(out) > 6 * len(source) + 60:                      # translations don't grow this much
        return True
    return bool(_RUNAWAY.search(out)) and not _SOURCE_REPEATS.search(source)


def _attempts(text: str):
    """What to try, in order, if the first translation comes back as nonsense. A short word on its own
    gives the model very little to go on, so we retry it as a sentence ("Cándido" -> "Cándido.")
    and then in lower case. Returns [(text to translate, did we add a full stop?), ...]."""
    tries = [(text, False)]
    if len(text.split()) <= 3:
        base = text.rstrip()
        dotted = base if base.endswith((".", "!", "?", "…")) else base + "."
        tries.append((dotted, dotted != base))
        tries.append((dotted.lower(), dotted != base))
    seen, unique = set(), []
    for item in tries:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    return unique


# ─────────────────────────────────────────────────────────────
# the translator the chat window uses
# ─────────────────────────────────────────────────────────────
class MessageTranslator:
    """
    translate_async(text, target, callback)
        Runs in a background thread (so the window never freezes) and then
        calls  callback(result, error)  FROM THAT THREAD -- so the callback must
        only hand the result over to the GUI thread (the chat window drops it
        in its incoming queue), never touch Tk widgets itself.

        result: None            -> nothing to show (already in your language,
                                   or nothing translatable)
                {"text": str}   -> the translation
        error:  None, or an Exception (TranslatorUnavailable if the library
                is missing). Failures are not cached, so a later try can work.
    """

    def __init__(self, backend: str = DEFAULT_BACKEND, workers: int = WORKERS, min_gap: float = MIN_GAP_SECONDS,
                 cooldown: float = COOLDOWN_SECONDS):
        self._backend_name = backend
        self._backend = None
        self._backend_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="translate")
        self._chunk_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="translate-piece")   # pieces of ONE long message
        self._min_gap, self._cooldown = min_gap, cooldown
        self._pace_lock = threading.Lock()
        self._last_call = 0.0
        self._blocked_until = 0.0
        self._waiting = 0
        self._count_lock = threading.Lock()
        self._cache: "OrderedDict[tuple, object]" = OrderedDict()   # (text, target) -> {"text":..} or None
        self._cache_lock = threading.Lock()
        self._warmed: set = set()

    # ---- public ------------------------------------------------------
    def translate_async(self, text: str, target: str, callback):
        limit = getattr(BACKENDS.get(self._backend_name), "max_waiting", MAX_WAITING)
        with self._count_lock:
            if self._waiting >= limit:
                too_many = True
            else:
                self._waiting += 1
                too_many = False
        if too_many:
            callback(None, TranslatorBusy("too many waiting"))
            return
        self._pool.submit(self._run, text, target, callback)

    def warm_up(self, target: str):
        """Get the backend ready in the background (it queues ahead of any message that arrives later).
        Safe to call again: a language is only warmed once."""
        if target in self._warmed:
            return
        self._warmed.add(target)

        def work():
            try:
                warm = getattr(self._get_backend(), "warm_up", None)
                if warm is not None:
                    warm(target)
            except Exception:
                self._warmed.discard(target)                    # not ready yet: a later call may try again
        self._pool.submit(work)

    def seconds_blocked(self) -> float:
        """How long we're sitting out because Google said stop (0 = not blocked)."""
        return max(0.0, self._blocked_until - time.monotonic())

    def translate(self, text: str, target: str):
        """Blocking version (used by tests). Same return value as the callback's `result`."""
        if not needs_translation(text):
            return None
        key = (text, target)
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        result = self._translate_uncached(text, target)
        with self._cache_lock:
            self._cache[key] = result
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return result

    # ---- internals ---------------------------------------------------
    def _run(self, text, target, callback):
        try:
            result, error = self.translate(text, target), None
        except Exception as e:          # network down, library missing, rate-limited...
            result, error = None, e
        finally:
            with self._count_lock:
                self._waiting = max(0, self._waiting - 1)
        try:
            callback(result, error)
        except Exception:
            pass

    def _get_backend(self):
        with self._backend_lock:
            if self._backend is None:
                cls = BACKENDS.get(self._backend_name)
                if cls is None:
                    raise TranslatorUnavailable(f"unknown translation backend: {self._backend_name}")
                self._backend = cls()
            return self._backend

    def _ask_backend(self, backend, piece: str, target: str) -> str:
        """The ONLY place that talks to a backend. Backends that say paced = True are spaced out one at a
        time; the others run in parallel. When told to stop (TooManyRequests) we sit out for a while."""
        wait = self.seconds_blocked()
        if wait:
            raise TranslatorBusy("blocked by Google", retry_in=wait)
        if getattr(backend, "paced", True):
            with self._pace_lock:
                gap = self._min_gap - (time.monotonic() - self._last_call)
                if gap > 0:
                    time.sleep(gap)
                self._last_call = time.monotonic()
        try:
            return backend.translate(piece, target)
        except Exception as e:
            if type(e).__name__ == "TooManyRequests":
                self._blocked_until = time.monotonic() + self._cooldown
            raise

    def _translate_uncached(self, text: str, target: str):
        backend = self._get_backend()

        restored = None
        for attempt, added_stop in _attempts(text):
            protected, saved = _protect(attempt)
            out = self._translate_pieces(backend, protected, target)
            candidate = _restore(out, saved)
            if candidate is None:                  # the translator mangled a token: redo with no protection
                candidate = self._translate_pieces(backend, attempt, target)
            if added_stop and candidate.endswith("."):
                candidate = candidate[:-1]          # we added that full stop ourselves; don't show it
            if not looks_broken(text, candidate):
                restored = candidate
                break
        if restored is None:                       # every try came back as nonsense: show nothing, not garbage
            return None

        # Translating text that's already in the target language hands it back
        # (nearly) unchanged -- in that case there's nothing to show.
        if _norm(restored) == _norm(text):
            return None
        return {"text": restored}

    def _translate_pieces(self, backend, text: str, target: str) -> str:
        parts = _chunks(text)
        if len(parts) == 1:
            return self._ask_backend(backend, parts[0], target)
        if getattr(backend, "paced", True):
            results = [self._ask_backend(backend, p, target) for p in parts]
        else:                                              # long text: all the pieces at once
            results = list(self._chunk_pool.map(lambda p: self._ask_backend(backend, p, target), parts))
        # a translated piece loses its trailing line break / space: put back what the original piece had
        return "".join(r.rstrip() + p[len(p.rstrip()):] for r, p in zip(results, parts)).strip()
