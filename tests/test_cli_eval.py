from __future__ import annotations

import json
from pathlib import Path

from thesis_review.cli import main
from thesis_review.evalrun import NO_KEY_MESSAGE
from thesis_review.types import Finding, ReviewResult


def test_eval_exits_when_key_missing(tmp_path: Path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(
        json.dumps({"model": "gpt-4o-mini", "api_key": ""}, ensure_ascii=False),
        encoding="utf-8",
    )
    code = main(["--home", str(home), "eval", "--out", str(tmp_path / "out")])
    assert code == 2
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "模型设置" in text
    assert NO_KEY_MESSAGE in text or "密钥" in text
    assert "sk-" not in text


def test_eval_writes_summary_from_injected_reviews(tmp_path: Path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(
        json.dumps(
            {"model": "gpt-4o-mini", "api_key": "sk-secret-do-not-print", "provider": "openai-compatible"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_review(*, draft_id: str, output_dir: Path, **_kwargs) -> ReviewResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        if draft_id == "overclaim":
            findings = [Finding(
                id="argument-1",
                category="B",
                source="argument",
                problem="x",
                rationale="y",
                quote="q",
                anchor="P1",
                paragraph_index=1,
                apply="comment",
            )]
            ops = ["open_draft", "list_outline", "read_section", "record_argument_finding", "commit_review"]
        elif draft_id == "abandon":
            findings = []
            ops = ["open_draft", "list_outline", "read_paragraphs", "commit_review"]
        else:
            findings = [Finding(
                id="history-1",
                category="A",
                source="history",
                problem="x",
                rationale="y",
                quote="q",
                anchor="P1",
                paragraph_index=1,
                apply="comment",
                issue_id="i1",
            )]
            ops = ["open_draft", "get_history_candidates", "confirm_history_finding", "commit_review"]
        findings_path = output_dir / f"{draft_id}-findings.json"
        findings_path.write_text("[]", encoding="utf-8")
        (output_dir / f"{draft_id}-trace.json").write_text(
            json.dumps({"draft_id": draft_id, "ops": [{"op": name, "ok": True, "params": {}} for name in ops]}),
            encoding="utf-8",
        )
        reviewed = output_dir / f"{draft_id}-reviewed.docx"
        reviewed.write_bytes(b"PK")
        return ReviewResult(
            reviewed_path=reviewed,
            findings_path=findings_path,
            findings=findings,
            used_model=True,
        )

    from thesis_review import evalrun

    original = evalrun.review_live
    evalrun.review_live = lambda service, **kwargs: fake_review(**kwargs)
    try:
        code = main(["--home", str(home), "eval", "--out", str(tmp_path / "out")])
    finally:
        evalrun.review_live = original
    assert code == 0
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    names = [item["case"] for item in summary["cases"]]
    assert names == ["overclaim", "abandon", "history"]
    dumped = json.dumps(summary)
    captured = capsys.readouterr()
    blob = dumped + captured.out + captured.err
    assert "sk-secret-do-not-print" not in blob
    assert "api_key" not in summary
    settings_files = list((tmp_path / "out").rglob("settings.json"))
    for path in settings_files:
        assert "sk-secret" not in path.read_text(encoding="utf-8")
