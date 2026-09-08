from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ParagraphView:
    ordinal: int
    anchor: str
    text: str


@dataclass(frozen=True)
class TableView:
    ordinal: int
    anchor: str
    previous_text: str
    previous_anchor: str = ""


@dataclass(frozen=True)
class CommentRecord:
    comment_id: str
    author: str
    text: str
    anchor: str
    span: str
    date: str = ""


@dataclass(frozen=True)
class RevisionRecord:
    revision_id: str
    kind: str
    text: str
    author: str
    date: str = ""


@dataclass
class ReplaceResult:
    n_replaced: int
    new_anchor: str
    new_text: str


@dataclass
class IssueRecord:
    id: str
    teacher_id: str
    student_id: str
    major: str
    source_draft_id: str
    category: str
    status: str
    original_kind: str
    original_text: str
    original_span: str
    original_context: str
    original_anchor: str
    suggested_fix: str = ""
    issue_type: str = ""
    problem: str = ""
    scope: str = ""
    teacher_intent: str = ""
    created_at: str = ""
    confirmed_at: str = ""


@dataclass
class HistoryHit:
    issue_id: str
    new_anchor: str
    new_quote: str
    paragraph_index: int
    evidence_text: str
    original_span: str
    category: str


@dataclass
class Evidence:
    kind: str
    draft_id: str
    text: str


@dataclass
class Finding:
    id: str
    category: str
    source: str
    problem: str
    rationale: str
    quote: str
    anchor: str
    paragraph_index: int
    apply: str
    issue_id: str | None = None
    code: str = ""
    suggested_old: str | None = None
    suggested_new: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    draft_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Finding":
        evidence = [
            Evidence(**item) if isinstance(item, dict) else item
            for item in raw.get("evidence") or []
        ]
        allowed = {key: raw.get(key) for key in cls.__dataclass_fields__ if key != "evidence"}
        allowed["evidence"] = evidence
        return cls(**allowed)


@dataclass
class ReviewResult:
    reviewed_path: Path
    findings_path: Path
    findings: list[Finding]
    used_model: bool
    warning: str = ""
