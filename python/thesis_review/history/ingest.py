from __future__ import annotations

import re
from dataclasses import dataclass

from thesis_review.history.store import HistoryStore, _now, new_issue_id
from thesis_review.types import CommentRecord, IssueRecord, RevisionRecord

_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*|[图表]\s*\d+)")


@dataclass(frozen=True)
class StructuredIssue:
    issue_type: str
    problem: str
    scope: str
    teacher_intent: str
    suggested_fix: str


def classify_comment(text: str) -> str:
    if any(token in text for token in ("格式", "标题", "页眉", "参考文献", "题注", "字体")):
        return "C"
    if any(token in text for token in ("结构", "论证", "依据", "实验", "创新")):
        return "B"
    return "A"


def structure_issue(*, comment: str, span: str, kind: str) -> StructuredIssue:
    text = (comment or "").strip()
    return StructuredIssue(
        issue_type=_issue_type(text, kind),
        problem=_problem(text),
        scope=_scope(span or ""),
        teacher_intent=text,
        suggested_fix=_suggested_fix(text),
    )


def issues_from_comments(
    *,
    teacher_id: str,
    student_id: str,
    major: str,
    draft_id: str,
    comments: list[CommentRecord],
) -> list[IssueRecord]:
    records: list[IssueRecord] = []
    for comment in comments:
        structured = structure_issue(
            comment=comment.text, span=comment.span, kind="comment"
        )
        records.append(
            IssueRecord(
                id=new_issue_id(),
                teacher_id=teacher_id,
                student_id=student_id,
                major=major,
                source_draft_id=draft_id,
                category=classify_comment(comment.text),
                status="candidate",
                original_kind="comment",
                original_text=comment.text,
                original_span=comment.span,
                original_context=comment.span,
                original_anchor=comment.anchor,
                suggested_fix=structured.suggested_fix,
                issue_type=structured.issue_type,
                problem=structured.problem,
                scope=structured.scope,
                teacher_intent=structured.teacher_intent,
                created_at=_now(),
            )
        )
    return records


def issues_from_revisions(
    *,
    teacher_id: str,
    student_id: str,
    major: str,
    draft_id: str,
    revisions: list[RevisionRecord],
    assistant_author: str = "审改助手",
) -> list[IssueRecord]:
    records: list[IssueRecord] = []
    for revision in revisions:
        if revision.author == assistant_author:
            continue
        comment = f"{revision.kind}: {revision.text}"
        structured = structure_issue(comment=comment, span=revision.text, kind="revision")
        records.append(
            IssueRecord(
                id=new_issue_id(),
                teacher_id=teacher_id,
                student_id=student_id,
                major=major,
                source_draft_id=draft_id,
                category="A",
                status="candidate",
                original_kind="revision",
                original_text=comment,
                original_span=revision.text,
                original_context=revision.text,
                original_anchor="",
                suggested_fix=structured.suggested_fix,
                issue_type=structured.issue_type,
                problem=structured.problem,
                scope=structured.scope,
                teacher_intent=structured.teacher_intent,
                created_at=_now(),
            )
        )
    return records


def persist(store: HistoryStore, records: list[IssueRecord]) -> list[IssueRecord]:
    return [store.add(record) for record in records]


def _issue_type(comment: str, kind: str) -> str:
    if "主观" in comment:
        return "subjective_claim"
    if any(token in comment for token in ("格式", "标题", "页眉", "字体", "题注")):
        return "format"
    if any(token in comment for token in ("依据", "证据", "实验")):
        return "missing_evidence"
    if any(token in comment for token in ("结构", "论证")):
        return "argument"
    if kind == "revision":
        return "revision"
    return "language"


def _problem(comment: str) -> str:
    text = comment.strip()
    for separator in ("，", "。", "；", ",", ";"):
        if separator in text:
            return text.split(separator, 1)[0].strip()
    return text


def _scope(span: str) -> str:
    stripped = span.strip()
    if stripped.startswith("表"):
        return "table"
    if stripped.startswith("图"):
        return "figure"
    if _HEADING_RE.match(stripped):
        return "heading"
    if "摘要" in stripped:
        return "abstract"
    if "参考文献" in stripped:
        return "references"
    return "body"


def _suggested_fix(comment: str) -> str:
    index = comment.find("请")
    if index < 0:
        return ""
    return comment[index:].strip()
