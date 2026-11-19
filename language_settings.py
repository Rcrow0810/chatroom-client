# language_settings.py
# ---------------------------------------------------------
# Remembers, per person on this computer, which language they want incoming messages
# shown in (language_prefs.json next to the program). Window-free so it can be tested.
# ---------------------------------------------------------

import json
import os

import app_paths

# Saved in the per-user settings folder (a packaged app's own folder can be read-only or temporary).
PREFS_FILE = os.path.join(app_paths.user_data_dir(), "message_language_prefs.json")
# Older versions saved next to the program: still read from there if nothing has been saved yet.
LEGACY_PREFS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "language_prefs.json")

# Names for the menu. A code that isn't here just shows as its code.
LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "it": "Italian",
    "ru": "Russian", "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic", "hi": "Hindi",
    "he": "Hebrew", "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "uk": "Ukrainian", "vi": "Vietnamese",
    "id": "Indonesian", "sv": "Swedish", "da": "Danish", "fi": "Finnish", "el": "Greek", "cs": "Czech",
    "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian", "ca": "Catalan", "fa": "Persian", "ur": "Urdu",
    "th": "Thai", "tl": "Filipino", "bn": "Bengali", "ga": "Irish", "sk": "Slovak", "sq": "Albanian",
    "eo": "Esperanto", "az": "Azerbaijani", "nb": "Norwegian", "lt": "Lithuanian", "lv": "Latvian",
    "af": "Afrikaans", "sw": "Swahili", "ms": "Malay", "hr": "Croatian", "sl": "Slovenian", "et": "Estonian",
    "is": "Icelandic", "sr": "Serbian", "bs": "Bosnian", "mk": "Macedonian", "mt": "Maltese", "cy": "Welsh",
    "gl": "Galician", "eu": "Basque", "be": "Belarusian", "ka": "Georgian", "hy": "Armenian", "kk": "Kazakh",
    "ne": "Nepali", "ta": "Tamil", "te": "Telugu", "ml": "Malayalam", "kn": "Kannada", "mr": "Marathi",
    "gu": "Gujarati", "pa": "Punjabi", "si": "Sinhala", "km": "Khmer", "lo": "Lao", "my": "Burmese",
    "mn": "Mongolian", "uz": "Uzbek", "ky": "Kyrgyz", "la": "Latin", "yi": "Yiddish", "zu": "Zulu",
    "so": "Somali", "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo", "am": "Amharic", "ht": "Haitian Creole",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def _read_all() -> dict:
    data = _read_from(PREFS_FILE)
    if not data:
        data = _read_from(LEGACY_PREFS_FILE)
    return data


def load_language(username: str, path: str | None = None) -> str:
    """The saved language code for this person ("" = don't translate)."""
    data = _read_all() if path is None else _read_from(path)
    value = data.get(username.lower(), "")
    return value if isinstance(value, str) and len(value) <= 12 else ""


def _read_from(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_language(username: str, code: str, path: str | None = None) -> None:
    path = path or PREFS_FILE
    data = _read_from(path)
    data[username.lower()] = code if isinstance(code, str) else ""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass          # can't write -> it just won't be remembered next time
