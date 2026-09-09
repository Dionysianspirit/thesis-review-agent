from __future__ import annotations

from pathlib import Path

from tests.helpers import OVERCLAIM_CLAIM_QUOTE, OVERCLAIM_EVIDENCE_QUOTE, sample_new_draft, sample_overclaim_draft
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.types import DECISION_ACCEPTED, DECISION_EDITED, DECISION_PENDING, DECISION_REJECTED
from thesis_review.word.adapter import WordAdapter


def _service(tmp_path: Path) -> ThesisReviewService:
    return ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )


def test_candidates_do_not_enter_final_word_including_format(tmp_path: Path):
    service = _service(tmp_path)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    assert result.findings
    assert any(item.kind == "format" or item.category == "C" for item in result.findings)
    assert all(item.teacher_decision == DECISION_PENDING for item in result.findings)
    comments = WordAdapter().extract_comments(WordAdapter().open_path(result.reviewed_path))
    assert comments == []


def test_accepted_and_edited_export_rejects_pending(tmp_path: Path):
    service = _service(tmp_path)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="overclaim",
        data=sample_overclaim_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
        use_pi=True,
        faux=True,
        faux_scenario="overclaim",
    )
    session_id = result.session_id
    argument = next(item for item in result.findings if item.source == "argument")
    language = next((item for item in result.findings if item.kind == "language" or item.category == "A"), None)
    fmt = next((item for item in result.findings if item.kind == "format" or item.category == "C"), None)
    service.decide_finding(session_id=session_id, finding_id=argument.id, decision=DECISION_EDITED, edited_text="老师改写：请补显著性检验后再写显著提升。")
    if language:
        service.decide_finding(session_id=session_id, finding_id=language.id, decision=DECISION_REJECTED)
    blocked = service.export_final(session_id=session_id, allow_pending=False)
    assert blocked["ok"] is False
    assert blocked["pending"] >= 1
    if fmt:
        service.decide_finding(session_id=session_id, finding_id=fmt.id, decision=DECISION_ACCEPTED)
    for item in service.sessions.get(session_id).findings:
        if item.teacher_decision == DECISION_PENDING:
            service.decide_finding(session_id=session_id, finding_id=item.id, decision=DECISION_REJECTED)
    exported = service.export_final(session_id=session_id, allow_pending=False)
    assert exported["ok"] is True
    comments = WordAdapter().extract_comments(WordAdapter().open_path(exported["reviewed_path"]))
    blob = "\n".join(item.text for item in comments)
    assert "老师改写：请补显著性检验后再写显著提升。" in blob
    assert OVERCLAIM_CLAIM_QUOTE in blob or "显著提升" in blob
    if language:
        assert language.problem not in blob
    original = WordAdapter().open_bytes(sample_overclaim_draft())
    assert WordAdapter().extract_comments(original) == []


def test_pending_and_rejected_are_not_written(tmp_path: Path):
    service = _service(tmp_path)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    pending_item = result.findings[0]
    rejected_item = result.findings[1] if len(result.findings) > 1 else None
    accepted_item = result.findings[-1]
    service.decide_finding(session_id=result.session_id, finding_id=accepted_item.id, decision=DECISION_ACCEPTED)
    if rejected_item and rejected_item.id != accepted_item.id:
        service.decide_finding(session_id=result.session_id, finding_id=rejected_item.id, decision=DECISION_REJECTED)
    exported = service.export_final(session_id=result.session_id, allow_pending=True)
    assert exported["ok"] is True
    assert exported["pending"] >= 1
    comments = WordAdapter().extract_comments(WordAdapter().open_path(exported["reviewed_path"]))
    blob = "\n".join(item.text for item in comments)
    assert accepted_item.problem in blob
    assert pending_item.id == accepted_item.id or pending_item.problem not in blob or pending_item.id == accepted_item.id
    if rejected_item and rejected_item.id != accepted_item.id:
        assert rejected_item.problem not in blob


def test_batch_accept_format_then_individual_reject(tmp_path: Path):
    service = _service(tmp_path)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    formats = [item for item in result.findings if item.kind == "format" or item.category == "C"]
    assert formats
    service.accept_format_findings(result.session_id)
    session = service.sessions.get(result.session_id)
    assert all(item.teacher_decision == DECISION_ACCEPTED for item in session.findings if item.kind == "format" or item.category == "C")
    first = formats[0]
    service.decide_finding(session_id=result.session_id, finding_id=first.id, decision=DECISION_REJECTED)
    exported = service.export_final(session_id=result.session_id, allow_pending=True)
    blob = "\n".join(
        item.text for item in WordAdapter().extract_comments(WordAdapter().open_path(exported["reviewed_path"]))
    )
    assert first.problem not in blob
    kept = [item for item in service.sessions.get(result.session_id).findings if (item.kind == "format" or item.category == "C") and item.id != first.id]
    if kept:
        assert any(item.problem in blob for item in kept)
