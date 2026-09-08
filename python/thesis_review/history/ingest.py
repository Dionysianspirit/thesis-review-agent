from __future__ import annotations

from thesis_review.history.store import HistoryStore, _now, new_issue_id
from thesis_review.types import CommentRecord, IssueRecord, RevisionRecord


def classify_comment(text: str) -> str:
    if any(token in text for token in ("格式", "标题", "页眉", "参考文献", "题注", "字体")):
        return "C"
    if any(token in text for token in ("结构", "论证", "依据", "实验", "创新")):
        return "B"
    return "A"


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
                original_text=f"{revision.kind}: {revision.text}",
                original_span=revision.text,
                original_context=revision.text,
                original_anchor="",
                created_at=_now(),
            )
        )
    return records


def persist(store: HistoryStore, records: list[IssueRecord]) -> list[IssueRecord]:
    return [store.add(record) for record in records]
