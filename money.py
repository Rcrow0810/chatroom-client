# money.py
# ---------------------------------------------------------
# Small, window-free helpers for money: turning what someone typed into whole
# cents, showing cents as dollars, and deciding which web addresses are safe
# to open for a payment. (Kept separate from the windows so they can be tested.)
# ---------------------------------------------------------

import re
from decimal import Decimal
from urllib.parse import urlparse


def parse_amount_to_cents(text) -> int | None:
    """"12", "$12.5", "1,250.00" -> whole cents. Anything else (letters, 3 decimals, negatives,
    scientific notation) -> None. Money is never handled as a float anywhere."""
    if not isinstance(text, str):
        return None
    t = text.strip().lstrip("$").replace(",", "").strip()
    if not re.fullmatch(r"[0-9]{1,7}(\.[0-9]{1,2})?", t):
        return None
    return int(Decimal(t) * 100)


def format_cents(cents: int, currency: str = "usd") -> str:
    symbol = "$" if str(currency).lower() == "usd" else str(currency).upper() + " "
    return f"{symbol}{cents // 100:,}.{cents % 100:02d}"


def is_stripe_url(url) -> bool:
    """True only for https://<something>.stripe.com addresses. The server tells us which page to
    open for onboarding / paying; we still refuse to open anything that isn't Stripe's own."""
    if not isinstance(url, str) or len(url) > 4000:
        return False
    try:
        parts = urlparse(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.username is None and port in (None, 443)
            and host is not None and (host == "stripe.com" or host.endswith(".stripe.com")))
