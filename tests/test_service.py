"""Offline review writes a commented copy and a labelled findings file."""
from __future__ import annotations

from pathlib import Path

from docx import Document

from tests.helpers import sample_history_v1, sample_new_draft
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter


def test_offline_review_labels_history_and_rule_findings(tmp_path: Path):
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
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)

    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    sources = {item.source for item in result.findings}
    assert "history" in sources
    assert "rule" in sources
    assert "model" not in sources
    history_item = next(item for item in result.findings if item.source == "history")
    assert history_item.issue_id == subjective.id
    assert any("避免主观评价" in evidence.text for evidence in history_item.evidence)
    assert result.reviewed_path.exists()
    assert result.findings_path.exists()
    Document(str(result.reviewed_path))
    opened = WordAdapter().open_path(result.reviewed_path)
    comments = WordAdapter().extract_comments(opened)
    texts = [comment.text for comment in comments]
    assert any("历次" in text or "已指出" in text for text in texts)
    assert any(comment.author == "审改助手" for comment in comments)
