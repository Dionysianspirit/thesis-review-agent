from __future__ import annotations

import uuid

from thesis_review.types import Evidence, Finding, ParagraphView

PADDED_ADVERBS = (
    ("非常非常", "较为"),
    ("特别特别", "较为"),
    ("一定一定", "需要"),
)


def check_language(paragraphs: list[ParagraphView], *, draft_id: str = "") -> list[Finding]:
    findings: list[Finding] = []
    for paragraph in paragraphs:
        for old, new in PADDED_ADVERBS:
            if old not in paragraph.text:
                continue
            findings.append(
                Finding(
                    id=uuid.uuid4().hex,
                    category="A",
                    source="rule",
                    code="padded_adverb",
                    problem="叠用程度副词，表述空泛。",
                    rationale="本科论文应避免「非常非常」一类加强语，改为可核验的表述。",
                    quote=old,
                    anchor=paragraph.anchor,
                    paragraph_index=paragraph.ordinal,
                    apply="both",
                    kind="language",
                    suggested_old=old,
                    suggested_new=new,
                    draft_id=draft_id,
                    evidence=[Evidence(kind="rule", draft_id=draft_id, text=paragraph.text)],
                )
            )
    return findings
