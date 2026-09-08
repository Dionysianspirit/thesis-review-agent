from __future__ import annotations

import base64
from pathlib import Path

from tests.helpers import sample_new_draft
from thesis_review.worker import Worker


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
