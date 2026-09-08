from __future__ import annotations

from thesis_review.settings import AppSettings


def model_available(settings: AppSettings) -> bool:
    return bool(settings.api_key.strip() and settings.model.strip())
