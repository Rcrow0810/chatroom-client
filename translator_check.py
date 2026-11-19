# translator_check.py  --  run on the computer where translation isn't working:
#       python3 translator_check.py
# It tells you the REAL reason, using exactly the same code the chat uses.
import sys, time
print("Python", sys.version.split()[0])

import translator

backend = translator.GoogleBackend()
print("\nGoogle Translate (the main translator):")
try:
    start = time.time()
    out, src = backend.translate_detect("Hello my friend, how are you today?", "es")
    print(f"  OK  ({time.time() - start:.2f}s)  detected '{src}'  ->  {out}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    print("  No internet, or a firewall / school or work network / VPN is blocking translate.googleapis.com.")
    print("  (HTTP 429 or 403 means Google is rate-limiting this computer: wait a few minutes.)")

print("\nSeveral languages:")
from language_settings import LANGUAGE_NAMES
bad = []
for code in ("es", "fr", "de", "pt", "ja", "ko", "zh", "ru", "ar", "hi", "tl", "he", "vi", "tr"):
    try:
        print(f"  {code:4} OK    {backend.translate_detect('good morning', code)[0]}")
    except Exception as e:
        bad.append(code)
        print(f"  {code:4} FAIL  {type(e).__name__}: {str(e)[:90]}")

print("\nOffline fallback (optional):")
packs = translator.available_language_codes()
print("  installed packs:", ", ".join(packs) if packs else "none  (fine -- only needed if you want it to work with no internet)")
