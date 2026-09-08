from __future__ import annotations

from pathlib import Path

from tests.helpers import sample_history_v1, sample_new_draft
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter


def test_faux_pi_review_writes_history_and_rule_findings(tmp_path: Path):
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
    subjective = next(item for item in candidates if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_pi=True,
        faux=True,
    )
    sources = {item.source for item in result.findings}
    assert "rule" in sources
    assert "history" in sources
    assert result.reviewed_path.is_file()
