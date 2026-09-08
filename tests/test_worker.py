from __future__ import annotations

import base64
from pathlib import Path

from tests.helpers import sample_new_draft, sample_same_heading_fixed_body
from thesis_review.history.confirm import HitConfirmation
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.settings import AppSettings, save_settings
from thesis_review.worker import Worker
from thesis_review.word.adapter import WordAdapter


def test_worker_lists_paragraphs_from_open_draft(tmp_path: Path):
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能")
    payload = base64.b64encode(sample_new_draft()).decode("ascii")
    opened = worker.dispatch("open_draft", {"bytes_b64": payload})
    assert opened["n_paragraphs"] >= 3
    paragraphs = worker.dispatch("list_paragraphs", {})["paragraphs"]
    assert any("非常非常有效" in item["text"] for item in paragraphs)


def test_worker_commit_review_writes_findings(tmp_path: Path):
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能")
    worker.dispatch("open_draft", {"bytes_b64": base64.b64encode(sample_new_draft()).decode("ascii")})
    worker.dispatch("run_checks", {"draft_id": "new"})
    result = worker.dispatch("commit_review", {"draft_id": "new", "output_dir": str(tmp_path / "out")})
    assert Path(result["reviewed_path"]).is_file()
    assert Path(result["findings_path"]).is_file()


def test_worker_search_history_drops_model_rejected_heading_hit(tmp_path: Path, monkeypatch):
    save_settings(tmp_path, AppSettings(api_key="sk-test", model="gpt-4o-mini"))
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
    heading = next(item for item in candidates if "实验步骤" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=heading.id)
    monkeypatch.setattr(
        "thesis_review.history.confirm.confirm_history_hit",
        lambda **_kwargs: HitConfirmation(
            same_issue=False,
            confidence=0.93,
            quote="3.1 实验设计",
            rationale="标题未改，内容已补。",
        ),
    )
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能")
    worker.dispatch(
        "open_draft",
        {"bytes_b64": base64.b64encode(sample_same_heading_fixed_body(history=False)).decode("ascii")},
    )
    result = worker.dispatch("search_history", {"draft_id": "new"})
    assert result["hits"] == []
