from __future__ import annotations

from pathlib import Path

from thesis_review.cli import main


def test_demo_command_writes_review_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESIS_REVIEW_HOME", str(tmp_path / "home"))
    assert main(["--home", str(tmp_path / "home"), "demo", "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "new-reviewed.docx").is_file()
    assert (tmp_path / "out" / "new-findings.json").is_file()
