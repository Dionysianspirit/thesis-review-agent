from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from thesis_review.types import HistoryHit, IssueRecord, ParagraphView


def normalize(text: str) -> str:
    compact = unicodedata.normalize("NFKC", text)
    compact = re.sub(r"\s+", "", compact)
    return compact


def match_issue(issue: IssueRecord, paragraphs: list[ParagraphView]) -> HistoryHit | None:
    needle = issue.original_span or issue.original_text
    if not needle.strip():
        return None
    for paragraph in paragraphs:
        if needle in paragraph.text:
            return _hit(issue, paragraph)
    compact = normalize(needle)
    if compact:
        for paragraph in paragraphs:
            if compact in normalize(paragraph.text):
                return _hit(issue, paragraph)
    if len(needle) <= 40:
        best: tuple[float, ParagraphView] | None = None
        for paragraph in paragraphs:
            if not paragraph.text:
                continue
            score = SequenceMatcher(None, compact, normalize(paragraph.text)).ratio()
            if score >= 0.72 and (best is None or score > best[0]):
                best = (score, paragraph)
        if best is not None:
            return _hit(issue, best[1])
    return None


def _hit(issue: IssueRecord, paragraph: ParagraphView) -> HistoryHit:
    return HistoryHit(
        issue_id=issue.id,
        new_anchor=paragraph.anchor,
        new_quote=paragraph.text,
        paragraph_index=paragraph.ordinal,
        evidence_text=issue.original_text,
        original_span=issue.original_span,
        category=issue.category,
    )
