from __future__ import annotations

import re
import uuid

from thesis_review.school.dalian_finance_2026 import check_school_rules
from thesis_review.types import Evidence, Finding, ParagraphView, TableView

CAPTION_RE = re.compile(r"^表\s*\d+")
REF_ITEM_RE = re.compile(r"^\[(\d+)\]")


def check_format(
    paragraphs: list[ParagraphView],
    tables: list[TableView],
    *,
    draft_id: str = "",
) -> list[Finding]:
    findings: list[Finding] = []
    for table in tables:
        if not CAPTION_RE.match(table.previous_text.strip()):
            findings.append(
                Finding(
                    id=uuid.uuid4().hex,
                    category="C",
                    source="rule",
                    code="missing_table_caption",
                    problem="表格缺少「表 n」题注。",
                    rationale="《大连财经学院本科毕业论文（设计）格式标准》3.4：表号居左，格式为「表 1」，位于表体上方。",
                    quote=table.previous_text or table.anchor,
                    anchor=table.previous_anchor or table.anchor,
                    paragraph_index=table.ordinal,
                    apply="comment",
                    kind="format",
                    draft_id=draft_id,
                    evidence=[Evidence(kind="rule", draft_id=draft_id, text=table.previous_text)],
                )
            )
    findings.extend(_reference_gaps(paragraphs, draft_id=draft_id))
    findings.extend(check_school_rules(paragraphs, draft_id=draft_id))
    return findings


def _reference_gaps(paragraphs: list[ParagraphView], *, draft_id: str) -> list[Finding]:
    start = None
    for index, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if text == "参考文献" or text.startswith("参考文献"):
            start = index
            break
    if start is None:
        return []
    numbers: list[tuple[int, ParagraphView]] = []
    for paragraph in paragraphs[start + 1 :]:
        match = REF_ITEM_RE.match(paragraph.text.strip())
        if match:
            numbers.append((int(match.group(1)), paragraph))
    if not numbers:
        return []
    values = [item[0] for item in numbers]
    expected = list(range(1, max(values) + 1))
    if values == expected:
        return []
    last = numbers[-1][1]
    return [
        Finding(
            id=uuid.uuid4().hex,
            category="C",
            source="rule",
            code="reference_number_gap",
            problem="参考文献编号不连续。",
            rationale=f"《格式标准》3.3.9 要求正文按 [1]、[2] 顺序编码。当前编号为 {values}。",
            quote=last.text,
            anchor=last.anchor,
            paragraph_index=last.ordinal,
            apply="comment",
            kind="format",
            draft_id=draft_id,
            evidence=[Evidence(kind="rule", draft_id=draft_id, text=" ".join(str(n) for n in values))],
        )
    ]
