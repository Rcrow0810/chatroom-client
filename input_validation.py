# input_validation.py
# ---------------------------------------------------------
# Centralized validation for user-supplied input.
# This is an additional defense layer alongside parameterized
# SQL queries in db.py.
# ---------------------------------------------------------

import re

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")


def validate_username(username: str) -> tuple[bool, list[str]]:
    """
    Validate usernames before they are passed to the database.

    Returns:
        (True, []) if valid
        (False, [issues...]) if invalid
    """

    issues = []
    username = username.strip()

    if len(username) < 3:
        issues.append("Username must be at least 3 characters.")

    if len(username) > 30:
        issues.append("Username must be 30 characters or fewer.")

    if not USERNAME_PATTERN.fullmatch(username):
        issues.append(
            "Username may contain only letters, numbers, and underscores."
        )

    return len(issues) == 0, issues