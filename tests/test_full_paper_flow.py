from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import sample_full_thesis_draft, sample_history_v1
from thesis_review.history.store import HistoryStore
from thesis_review.quality import summarize_quality
from thesis_review.service import ThesisReviewService
from thesis_review.session_store import SessionStore
from thesis_review.types import DECISION_ACCEPTED, DECISION_EDITED, DECISION_REJECTED
from thesis_review.word.adapter import WordAdapter


def test_full_synthetic_thesis_teacher_gate_roundtrip(tmp_path: Path):
    paper = tmp_path / "thesis.docx"
    paper.write_bytes(sample_full_thesis_draft())
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    history = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
        source_path=str(tmp_path / "v1.docx"),
    )
    (tmp_path / "v1.docx").write_bytes(sample_history_v1())
    subjective = next(item for item in history if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)

    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="thesis",
        data=paper.read_bytes(),
        output_dir=tmp_path / "out",
        use_model=False,
        use_pi=True,
        faux=True,
        faux_scenario="data_mismatch",
        paper_path=str(paper),
    )
    assert result.session_id
    sources = {item.source for item in result.findings} | {item.kind for item in result.findings}
    assert "rule" in {item.source for item in result.findings} or "format" in sources or "language" in sources
    assert any(item.subtype == "data_consistency" or item.source == "history" or item.kind == "language" for item in result.findings)
    comments = WordAdapter().extract_comments(WordAdapter().open_path(result.reviewed_path))
    assert comments == []

    session = service.sessions.get(result.session_id)
    accepted = session.findings[0]
    edited = session.findings[1] if len(session.findings) > 1 else session.findings[0]
    rejected = session.findings[2] if len(session.findings) > 2 else None
    service.decide_finding(session_id=session.id, finding_id=accepted.id, decision=DECISION_ACCEPTED)
    if edited.id != accepted.id:
        service.decide_finding(
            session_id=session.id,
            finding_id=edited.id,
            decision=DECISION_EDITED,
            edited_text="老师最终文本：请统一准确率口径。",
        )
    if rejected and rejected.id not in {accepted.id, edited.id}:
        service.decide_finding(session_id=session.id, finding_id=rejected.id, decision=DECISION_REJECTED)

    restored = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
        sessions=SessionStore(tmp_path / "review-sessions.sqlite"),
    )
    loaded = restored.sessions.get(session.id)
    assert any(item.teacher_decision == DECISION_ACCEPTED for item in loaded.findings)
    exported = restored.export_final(session_id=loaded.id, allow_pending=True)
    assert exported["ok"] is True
    blob = "\n".join(
        item.text for item in WordAdapter().extract_comments(WordAdapter().open_path(exported["reviewed_path"]))
    )
    assert accepted.problem in blob or accepted.original_problem in blob
    if edited.id != accepted.id:
        assert "老师最终文本：请统一准确率口径。" in blob
    if rejected and rejected.id not in {accepted.id, edited.id}:
        assert rejected.problem not in blob
    original_blob = "\n".join(
        item.text for item in WordAdapter().extract_comments(WordAdapter().open_bytes(paper.read_bytes()))
    )
    assert original_blob == ""
    quality = summarize_quality(restored.sessions.get(loaded.id).findings, json.loads((tmp_path / "out" / "thesis-trace.json").read_text(encoding="utf-8")))
    assert quality["ai_candidates"] >= 1
    assert quality["accepted"] >= 1
    (tmp_path / "out" / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    assert "api_key" not in json.dumps(quality)
