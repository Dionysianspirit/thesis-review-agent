from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from thesis_review.llm import model_available
from thesis_review.settings import AppSettings
from thesis_review.types import HistoryHit, IssueRecord

MIN_CONFIDENCE = 0.7


@dataclass(frozen=True)
class HitConfirmation:
    same_issue: bool
    confidence: float
    quote: str
    rationale: str


def keep_confirmed_hit(raw: dict, paragraph: str) -> bool:
    if not isinstance(raw, dict) or not raw.get("same_issue"):
        return False
    if _confidence(raw.get("confidence")) < MIN_CONFIDENCE:
        return False
    quote = str(raw.get("quote") or "").strip()
    return bool(quote) and quote in paragraph


def confirm_history_hit(
    *,
    settings: AppSettings,
    issue: IssueRecord,
    hit: HistoryHit,
) -> HitConfirmation | None:
    if not model_available(settings):
        return None
    payload = {
        "model": settings.model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你核对本科论文的历史问题是否在新稿同一处仍未改正。"
                    "只根据给定旧批注、结构化摘要和新段落判断，不要发明原文。"
                    "只返回 JSON 对象，字段为 same_issue, confidence, quote, rationale。"
                    "confidence 为 0 到 1。quote 必须是新段落中出现过的短片段。"
                    "标题没改但批注针对的内容已经改掉时，same_issue 必须为 false。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "issue_type": issue.issue_type,
                        "problem": issue.problem or issue.original_text,
                        "scope": issue.scope,
                        "teacher_intent": issue.teacher_intent or issue.original_text,
                        "expected_fix": issue.suggested_fix,
                        "old_quote": issue.original_span or hit.original_span,
                        "old_comment": issue.original_text,
                        "new_paragraph": hit.new_quote,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    url = (settings.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=45.0)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(_extract_json_object(content))
    except (httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return HitConfirmation(
        same_issue=bool(data.get("same_issue")),
        confidence=_confidence(data.get("confidence")),
        quote=str(data.get("quote") or "").strip(),
        rationale=str(data.get("rationale") or "").strip(),
    )


def _confidence(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100.0
    return max(0.0, min(number, 1.0))


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text
