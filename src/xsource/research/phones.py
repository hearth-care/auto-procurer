"""UK phone normalisation to E.164."""

from __future__ import annotations

import re


def normalise_uk_phone(raw: str) -> str | None:
    digits = re.sub(r"[^\d+]", "", raw or "")
    if not digits:
        return None
    if digits.startswith("+44"):
        digits = "0" + digits[3:]
    elif digits.startswith("44") and len(digits) >= 11:
        digits = "0" + digits[2:]
    if re.fullmatch(r"0\d{9,10}", digits):
        return "+44" + digits[1:]
    return None
