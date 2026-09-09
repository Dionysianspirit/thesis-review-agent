from __future__ import annotations

import json
from pathlib import Path

from thesis_review.cli import main
from thesis_review.demo import GATE_FILENAME, TEACHER_EDIT_TEXT
from thesis_review.word.adapter import WordAdapter


def test_demo_command_writes_teacher_approved_word_comments(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESIS_REVIEW_HOME", str(tmp_path / "home"))
    out = tmp_path / "out"
    assert main(["--home", str(tmp_path / "home"), "demo", "--out", str(out)]) == 0
    reviewed = out / "new-reviewed.docx"
    findings = out / "new-findings.json"
    gate_path = out / GATE_FILENAME
    assert reviewed.is_file()
    assert findings.is_file()
    assert gate_path.is_file()
    payload = json.loads(gate_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["comments_before"] == 0
    assert payload["source_comments"] == 0
    assert payload["original_comments"] == 0
    assert payload["candidates"] >= 1
    assert payload["n_exported"] >= 1
    assert payload["comments_after"] >= 1
    assert payload["stats"]["pending"] == 0
    assert payload["stats"]["formal"] >= 1
    comments = WordAdapter().extract_comments(WordAdapter().open_path(reviewed))
    blob = "\n".join(item.text for item in comments)
    assert TEACHER_EDIT_TEXT in blob
    for problem in payload["rejected_problems"]:
        assert problem not in blob
    source = WordAdapter().extract_comments(WordAdapter().open_path(out / "new-source.docx"))
    assert source == []


def test_export_command_rewrites_teacher_docx(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESIS_REVIEW_HOME", str(tmp_path / "home"))
    out = tmp_path / "out"
    assert main(["--home", str(tmp_path / "home"), "demo", "--out", str(out)]) == 0
    payload = json.loads((out / GATE_FILENAME).read_text(encoding="utf-8"))
    dest = tmp_path / "formal.docx"
    assert (
        main(
            [
                "--home",
                str(tmp_path / "home"),
                "export",
                "--session",
                payload["session_id"],
                "--out",
                str(dest),
            ]
        )
        == 0
    )
    assert dest.is_file()
    comments = WordAdapter().extract_comments(WordAdapter().open_path(dest))
    assert comments
    assert TEACHER_EDIT_TEXT in "\n".join(item.text for item in comments)
