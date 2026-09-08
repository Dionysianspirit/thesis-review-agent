from __future__ import annotations


MIN_CONFIDENCE = 0.7


def keep_confirmed_hit(raw: dict, paragraph: str) -> bool:
    if not isinstance(raw, dict) or not raw.get("same_issue"):
        return False
    if _confidence(raw.get("confidence")) < MIN_CONFIDENCE:
        return False
    quote = str(raw.get("quote") or "").strip()
    return bool(quote) and quote in paragraph


def _confidence(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100.0
    return max(0.0, min(number, 1.0))
