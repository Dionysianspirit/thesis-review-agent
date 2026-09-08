"""Rule-based issue structure is derived from comments and spans, not a model."""
from __future__ import annotations

from pathlib import Path

from tests.helpers import sample_history_v1
from thesis_review.history.ingest import structure_issue
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter


def test_subjective_comment_gets_rule_based_fields():
    structured = structure_issue(
        comment="避免主观评价，请给出实验依据。",
        span="本研究非常非常有效。",
        kind="comment",
    )
    assert structured.issue_type == "subjective_claim"
    assert structured.problem == "避免主观评价"
    assert structured.scope == "body"
    assert "避免主观评价" in structured.teacher_intent
    assert "给出实验依据" in structured.suggested_fix


def test_heading_span_gets_heading_scope():
    structured = structure_issue(
        comment="写优劣势",
        span="2.2.2 梯度提升树算法的适用性分析",
        kind="comment",
    )
    assert structured.scope == "heading"
    assert structured.problem == "写优劣势"
    assert structured.issue_type == "language"


def test_format_comment_on_table_title():
    structured = structure_issue(
        comment="格式 表格中表1居左",
        span="表 1数据基本情况表",
        kind="comment",
    )
    assert structured.issue_type == "format"
    assert structured.scope == "table"


def test_ingest_fills_structured_fields_without_a_model(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    subjective = next(item for item in candidates if "主观评价" in item.original_text)
    assert subjective.issue_type == "subjective_claim"
    assert subjective.problem == "避免主观评价"
    assert subjective.scope == "body"
    assert "避免主观评价" in subjective.teacher_intent
    assert "给出实验依据" in subjective.suggested_fix
