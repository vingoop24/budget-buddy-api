"""Field-level scoring of a receipt scan against the correct answers."""

import re
from datetime import date

FIELDS = ("merchant", "amount", "date", "category", "currency")
SUCCESS_FIELDS = ("merchant", "amount", "date", "category")  # the PRD's scan success rate


def _merchant_key(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def field_correct(field: str, predicted, expected) -> bool:
    """Blank expected value = not on the receipt: only a blank answer is right.
    Otherwise a field the scan couldn't read (None) is wrong."""
    if expected in (None, ""):
        return predicted is None
    if predicted is None:
        return False
    if field == "merchant":
        p, e = _merchant_key(predicted), _merchant_key(expected)
        # "TRADER JOE'S #552" still matches "Trader Joe's"
        return bool(p and e) and (p == e or e in p or p in e)
    if field == "amount":
        return abs(float(predicted) - float(expected)) <= 0.01
    if field == "date":
        p = predicted.isoformat() if isinstance(predicted, date) else str(predicted)
        return p == str(expected)
    return str(predicted).strip().casefold() == str(expected).strip().casefold()


def score(predicted: dict, expected: dict) -> dict:
    """{field: True/False} plus 'all_correct' over the success-rate fields."""
    result = {f: field_correct(f, predicted.get(f), expected.get(f)) for f in FIELDS}
    result["all_correct"] = all(result[f] for f in SUCCESS_FIELDS)
    return result
