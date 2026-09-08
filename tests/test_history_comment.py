"""History comments must keep old-draft evidence distinct from the new quote."""
from __future__ import annotations

from thesis_review.service import _comment_body, _history_finding
from thesis_review.types import HistoryHit, IssueRecord


def test_history_comment_labels_old_span_and_new_quote_separately():
    issue = IssueRecord(
        id="issue-1",
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        source_draft_id="v1",
        category="A",
        status="confirmed",
        original_kind="comment",
        original_text="避免主观评价，请给出实验依据。",
        original_span="本研究非常非常有效。",
        original_context="本研究非常非常有效。",
        original_anchor="P3#abcd",
    )
    hit = HistoryHit(
        issue_id="issue-1",
        new_anchor="P3#efgh",
        new_quote="本研究较为有效。",
        paragraph_index=3,
        evidence_text=issue.original_text,
        original_span=issue.original_span,
        category="A",
    )
    body = _comment_body(_history_finding(hit, issue, "new"))
    assert "历次稿件已指出：避免主观评价，请给出实验依据。" in body
    assert "旧稿原文：「本研究非常非常有效。」" in body
    assert "本稿对应位置：「本研究较为有效。」" in body
    assert "旧稿原文：「本研究较为有效。」" not in body
