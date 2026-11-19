# password_policy.py
# ---------------------------------------------------------
# Central place for "what counts as a strong password".
# Used by db.py (so the rule can never be bypassed) and by
# login_app.py (so the user gets live feedback while typing).
# ---------------------------------------------------------

import re

MIN_LENGTH = 12

# A short list of extremely common passwords/patterns to block outright.
# This isn't meant to be exhaustive -- it's a quick sanity filter, not a
# replacement for the character-variety rules below.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456", "12345678",
    "123456789", "1234567890", "qwerty", "qwerty123", "abc123",
    "letmein", "monkey", "111111", "iloveyou", "admin", "welcome",
    "football", "dragon", "baseball", "sunshine", "princess",
    "trustno1", "master", "login", "starwars", "whatever",
}


def check_password_strength(password: str) -> tuple[bool, list[str]]:
    """
    Check a password against the policy.
    Returns (is_valid, list_of_unmet_requirements).
    If the list is empty, the password meets every requirement.
    """
    issues = []

    if len(password) < MIN_LENGTH:
        issues.append(f"At least {MIN_LENGTH} characters")
    if not re.search(r"[a-z]", password):
        issues.append("At least one lowercase letter")
    if not re.search(r"[A-Z]", password):
        issues.append("At least one uppercase letter")
    if not re.search(r"[0-9]", password):
        issues.append("At least one number")
    if not re.search(r"[^a-zA-Z0-9]", password):
        issues.append("At least one special character (e.g. ! @ # $ %)")
    if password.lower() in COMMON_PASSWORDS:
        issues.append("Not a commonly used password")

    return (len(issues) == 0, issues)


def strength_label(password: str) -> tuple[str, str]:
    """
    A rough at-a-glance strength rating for live GUI feedback.
    Returns (label, color). Not a substitute for check_password_strength --
    a password can look "Strong" here but still be missing a specific
    requirement (e.g. long but no digits).
    """
    if not password:
        return ("", "#888888")

    if password.lower() in COMMON_PASSWORDS:
        return ("Weak -- too common", "#e06c75")

    score = 0
    if len(password) >= MIN_LENGTH:
        score += 1
    if len(password) >= 16:
        score += 1
    if re.search(r"[a-z]", password) and re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"[0-9]", password):
        score += 1
    if re.search(r"[^a-zA-Z0-9]", password):
        score += 1

    if score <= 2:
        return ("Weak", "#e06c75")
    elif score == 3:
        return ("Fair", "#e5c07b")
    elif score == 4:
        return ("Good", "#61afef")
    else:
        return ("Strong", "#43b581")
