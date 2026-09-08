"""History records stay per teacher/student and ignore unconfirmed issues."""
from __future__ import annotations

from pathlib import Path

from tests.helpers import sample_history_v1, sample_new_draft
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter


def test_unconfirmed_issue_is_not_matched(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite")
    service = ThesisReviewService(store=store, adapter=WordAdapter(), home=tmp_path)
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    assert candidates
    assert all(item.status == "candidate" for item in candidates)
    hits = service.search_history(
        teacher_id="teacher-a",
        student_id="zhou",
        data=sample_new_draft(),
    )
    assert hits == []


def test_confirmed_issue_matches_new_draft_with_old_evidence(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite")
    service = ThesisReviewService(store=store, adapter=WordAdapter(), home=tmp_path)
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    subjective = next(item for item in candidates if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)
    hits = service.search_history(
        teacher_id="teacher-a",
        student_id="zhou",
        data=sample_new_draft(),
    )
    assert len(hits) == 1
    assert hits[0].issue_id == subjective.id
    assert "避免主观评价" in hits[0].evidence_text
    assert "非常非常有效" in hits[0].new_quote


def test_history_is_isolated_by_student(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite")
    service = ThesisReviewService(store=store, adapter=WordAdapter(), home=tmp_path)
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=candidates[0].id)
    hits = service.search_history(
        teacher_id="teacher-a",
        student_id="other",
        data=sample_new_draft(),
    )
    assert hits == []
