from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from thesis_review.types import HistoryHit, IssueRecord, ParagraphView

# Cover lines like 「作者王佳宁」 compact to 5 CJK chars; 格式 / () stay below this.
MIN_NEEDLE_CHARS = 5
HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*|[图表]\s*\d+)")
TOC_DOTS_RE = re.compile(r"\.{5,}|…{2,}")
WEAK_NEEDLE_RE = re.compile(r"^[\s()（）\[\]【】.,，。:：;；?？!！\-—_]+$")


def normalize(text: str) -> str:
    compact = unicodedata.normalize("NFKC", text)
    compact = re.sub(r"\s+", "", compact)
    return compact


def match_issue(issue: IssueRecord, paragraphs: list[ParagraphView]) -> HistoryHit | None:
    needle = _usable_needle(issue)
    if needle is None:
        return None
    compact = normalize(needle)
    heading = _is_heading_like(needle)
    for paragraph in paragraphs:
        if _is_toc_line(paragraph.text):
            continue
        if heading:
            if normalize(paragraph.text) == compact:
                return _hit(issue, paragraph)
            continue
        if needle in paragraph.text or compact in normalize(paragraph.text):
            return _hit(issue, paragraph)
    if heading or len(needle) > 40:
        return None
    best: tuple[float, ParagraphView] | None = None
    for paragraph in paragraphs:
        if not paragraph.text or _is_toc_line(paragraph.text):
            continue
        hay = normalize(paragraph.text)
        if not hay:
            continue
        score = SequenceMatcher(None, compact, hay).ratio()
        if score >= 0.88 and abs(len(hay) - len(compact)) <= max(8, len(compact) // 2):
            if best is None or score > best[0]:
                best = (score, paragraph)
    if best is not None:
        return _hit(issue, best[1])
    return None


def _usable_needle(issue: IssueRecord) -> str | None:
    span = (issue.original_span or "").strip()
    comment = (issue.original_text or "").strip()
    if _is_strong_needle(span):
        return span
    if _is_strong_needle(comment) and len(normalize(comment)) >= 20:
        return comment
    return None


def _is_strong_needle(text: str) -> bool:
    compact = normalize(text)
    if len(compact) < MIN_NEEDLE_CHARS:
        return False
    if WEAK_NEEDLE_RE.match(text) or WEAK_NEEDLE_RE.match(compact):
        return False
    return True


def _is_heading_like(text: str) -> bool:
    stripped = text.strip()
    if not HEADING_RE.match(stripped):
        return False
    return len(normalize(stripped)) <= 40


def _is_toc_line(text: str) -> bool:
    return TOC_DOTS_RE.search(text) is not None


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
