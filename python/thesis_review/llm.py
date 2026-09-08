from __future__ import annotations

import json

import httpx

from thesis_review.settings import AppSettings
from thesis_review.types import Evidence, Finding, ParagraphView


def model_available(settings: AppSettings) -> bool:
    return bool(settings.api_key.strip() and settings.model.strip())


def suggest_language_findings(
    *,
    settings: AppSettings,
    paragraphs: list[ParagraphView],
    draft_id: str,
) -> list[Finding]:
    if not model_available(settings):
        return []
    excerpt = "\n".join(f"{item.ordinal}. {item.text}" for item in paragraphs if item.text)[:6000]
    payload = {
        "model": settings.model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是本科毕业论文语言审改助手。只指出空泛措辞或明显语病。"
                    "没有历史记录时禁止使用「再次」「屡次」。"
                    "只返回 JSON 数组，每项含 quote, problem, rationale, suggested_old, suggested_new。"
                    "quote 必须是原文中出现过的短片段。"
                ),
            },
            {"role": "user", "content": excerpt},
        ],
    }
    url = (settings.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=45.0)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(_extract_json(content))
    except (httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    findings: list[Finding] = []
    by_text = [item for item in paragraphs if item.text]
    for index, item in enumerate(data[:8]):
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue
        paragraph = next((row for row in by_text if quote in row.text), None)
        if paragraph is None:
            continue
        findings.append(
            Finding(
                id=f"model-{index}",
                category="A",
                source="model",
                problem=str(item.get("problem") or "语言表达可收紧。"),
                rationale=str(item.get("rationale") or ""),
                quote=quote,
                anchor=paragraph.anchor,
                paragraph_index=paragraph.ordinal,
                apply="comment",
                suggested_old=item.get("suggested_old"),
                suggested_new=item.get("suggested_new"),
                draft_id=draft_id,
                evidence=[Evidence(kind="model", draft_id=draft_id, text=quote)],
            )
        )
    return findings


def _extract_json(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text
