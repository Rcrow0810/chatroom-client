# crypto_utils.py
# ---------------------------------------------------------
# End-to-end message encryption for the chat.
#
# Uses a single shared secret key (symmetric encryption) that
# every chat client must have a copy of. The server NEVER sees
# this key -- it only ever relays the encrypted text, so
# anyone watching the server's terminal or the raw network
# traffic just sees gibberish.
#
# IMPORTANT: the key file (chat.key) must be copied to every
# machine that runs the chat client, by hand -- USB stick,
# a private message, whatever. Never send it over the same
# network the chat itself runs on, or anyone snooping the
# network could grab it and decrypt everything.
# ---------------------------------------------------------

import os
from cryptography.fernet import Fernet, InvalidToken

DEFAULT_KEY_PATH = "chat.key"


def generate_key(path: str = DEFAULT_KEY_PATH):
    """Create a brand new secret key and save it to disk. Run this ONCE,
    then copy the resulting file to every machine that needs to chat."""
    key = Fernet.generate_key()
    with open(path, "wb") as f:
        f.write(key)
    return key


def load_cipher(path: str = DEFAULT_KEY_PATH) -> Fernet:
    """Load the shared key from disk and return a ready-to-use cipher."""
    if path == DEFAULT_KEY_PATH:
        import app_paths                      # works from a packaged app, not just the current folder
        path = app_paths.find_resource(path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Couldn't find '{path}'. Put the chat.key file from the server's owner next to the app."
        )
    with open(path, "rb") as f:
        key = f.read()
    return Fernet(key)


def encrypt_message(cipher: Fernet, plaintext: str) -> str:
    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_message(cipher: Fernet, ciphertext: str) -> str:
    """Raises cryptography.fernet.InvalidToken if the ciphertext can't be
    decrypted with this key (e.g. mismatched keys between machines)."""
    return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
