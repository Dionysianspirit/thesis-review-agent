"""History records stay per teacher/student and ignore unconfirmed issues."""
from __future__ import annotations

import threading
from pathlib import Path

from tests.helpers import sample_history_v1, sample_new_draft
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.types import IssueRecord
from thesis_review.word.adapter import WordAdapter


def test_store_can_be_used_from_another_thread(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite")
    record = IssueRecord(
        id="cross-thread-1",
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        source_draft_id="v1",
        category="A",
        status="confirmed",
        original_kind="comment",
        original_text="避免主观评价",
        original_span="本研究非常非常有效。",
        original_context="本研究非常非常有效。",
        original_anchor="P3",
        created_at="2026-01-01T00:00:00+00:00",
    )
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            store.add(record)
            listed = store.list_issues(teacher_id="teacher-a", student_id="zhou")
            fetched = store.get(record.id)
            students = store.list_students("teacher-a")
            updated = store.set_status(
                teacher_id="teacher-a",
                student_id="zhou",
                issue_id=record.id,
                status="disabled",
            )
            assert listed and listed[0].id == record.id
            assert fetched.original_text == record.original_text
            assert students == ["zhou"]
            assert updated.status == "disabled"
        except BaseException as exc:  # noqa: BLE001 - capture for the joining thread
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert store.get(record.id).status == "disabled"


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
