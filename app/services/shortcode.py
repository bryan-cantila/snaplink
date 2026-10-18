"""Short-code generation: 7-char base62 from the `secrets` module.

Custom codes are validated against [A-Za-z0-9_-]{3,16} in schemas.py;
uniqueness (random or custom) is enforced by a DB check with retry.
"""
import re
import secrets
import string

ALPHABET = string.ascii_letters + string.digits  # base62
CODE_LENGTH = 7
CUSTOM_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,16}$")


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_custom_code(code: str | None) -> bool:
    return code is not None and bool(CUSTOM_CODE_RE.match(code))
