from __future__ import annotations

from pathlib import Path

from tests.helpers import sample_history_v1, sample_new_draft, sample_same_heading_fixed_body
from thesis_review.history.semantic import semantic_recall
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.session_store import TeacherFeedback, feedback_as_soft_reference, now_iso, new_feedback_id
from thesis_review.word.adapter import WordAdapter
from thesis_review.worker import Worker


def _open(worker: Worker, data: bytes) -> None:
    import base64

    worker.dispatch("open_draft", {"bytes_b64": base64.b64encode(data).decode("ascii")})


def test_semantic_recall_does_not_mark_recidivism(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "thesis-review.sqlite"),
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
    issue = next(item for item in candidates if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=issue.id)
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能")
    _open(worker, sample_new_draft())
    payload = worker.dispatch("semantic_history_candidates", {"draft_id": "new"})
    assert payload["candidates"]
    assert all(item["auto_recidivism"] is False for item in payload["candidates"])
    assert all(item["needs_context_check"] is True for item in payload["candidates"])
    assert worker.findings == []


def test_semantic_similar_heading_still_requires_confirm(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "thesis-review.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_same_heading_fixed_body(history=True),
    )
    issue = next(item for item in candidates if "实验步骤" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=issue.id)
    opened = WordAdapter().open_bytes(sample_same_heading_fixed_body(history=False))
    hits = semantic_recall(
        service.store.list_issues(teacher_id="teacher-a", student_id="zhou", status="confirmed"),
        WordAdapter().list_paragraphs(opened),
    )
    assert hits
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能")
    _open(worker, sample_same_heading_fixed_body(history=False))
    assert worker.findings == []


def test_rejected_teacher_feedback_is_not_a_positive_rule(tmp_path: Path):
    store = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    ).sessions
    store.add_feedback(
        TeacherFeedback(
            id=new_feedback_id(),
            session_id="s1",
            finding_id="f1",
            teacher_id="teacher-a",
            student_id="zhou",
            paper_path="new.docx",
            section="结论",
            decision="rejected",
            original_payload={"problem": "不要再报文风偏好", "kind": "language"},
            edited_text="",
            created_at=now_iso(),
            kind="language",
            category="A",
            problem="不要再报文风偏好",
        )
    )
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能")
    items = worker.dispatch("get_teacher_feedback", {"limit": 5})["items"]
    assert items
    assert items[0]["positive_rule"] is False
    assert "驳回" in items[0]["hint"]
    accepted = feedback_as_soft_reference(
        TeacherFeedback(
            id="x",
            session_id="s",
            finding_id="f",
            teacher_id="teacher-a",
            student_id="zhou",
            paper_path="",
            section="",
            decision="accepted",
            original_payload={},
            edited_text="",
            created_at=now_iso(),
            kind="content",
            problem="一次采用",
        )
    )
    assert "永久" in accepted["hint"]
    assert accepted["positive_rule"] is False
