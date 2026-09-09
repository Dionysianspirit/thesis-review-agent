from __future__ import annotations

import json
from pathlib import Path

from thesis_review.applog import ERROR_LOG, OPS_LOG, RUN_LOG, log_dir, redact, setup, write_error, write_op, write_run
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.worker import Worker
from thesis_review.word.adapter import WordAdapter
from tests.helpers import sample_new_draft, sample_overclaim_draft


def test_redact_strips_keys_and_openai_tokens():
    text = "api_key=sk-secret-token-value THESIS_API_KEY=sk-live-abcdefgh"
    cleaned = redact(text)
    assert "sk-secret-token-value" not in cleaned
    assert "sk-live-abcdefgh" not in cleaned
    assert "***" in cleaned


def test_three_log_files_and_no_quotes_in_ops(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("THESIS_LOG_DIR", raising=False)
    setup(tmp_path, kind="gui")
    write_run(tmp_path, "review start", session="sess-1", api_key="sk-should-drop")
    write_op(
        tmp_path,
        "record_content_finding",
        ok=False,
        code="quote_not_in_draft",
        quote="本文准确率达到 99.9%。",
        session="sess-1",
    )
    write_error(tmp_path, "pi_failed api_key=sk-leak-me", exc=RuntimeError("boom sk-leak-me"))
    logs = log_dir(tmp_path)
    run_text = (logs / RUN_LOG).read_text(encoding="utf-8")
    ops_text = (logs / OPS_LOG).read_text(encoding="utf-8")
    err_text = (logs / ERROR_LOG).read_text(encoding="utf-8")
    assert "[run] gui start" in run_text
    assert "review start" in run_text
    assert "sk-should-drop" not in run_text
    row = json.loads(ops_text.strip().splitlines()[-1])
    assert row["op"] == "record_content_finding"
    assert row["ok"] is False
    assert row["code"] == "quote_not_in_draft"
    assert "99.9" not in ops_text
    assert "quote" not in row
    assert "sk-leak-me" not in err_text
    assert "boom" in err_text


def test_worker_failed_op_logs_code_not_quote(tmp_path: Path, monkeypatch):
    import base64

    monkeypatch.delenv("THESIS_LOG_DIR", raising=False)
    worker = Worker(
        home=tmp_path,
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
    )
    worker.dispatch("open_draft", {"bytes_b64": base64.b64encode(sample_overclaim_draft()).decode("ascii")})
    try:
        worker.dispatch(
            "record_content_finding",
            {
                "kind": "content",
                "subtype": "argument",
                "quote": "本文准确率达到 99.9%。",
                "evidence_quote": "准确率由 0.81 提高到 0.83。",
                "problem": "编造。",
                "rationale": "编造。",
            },
        )
    except Exception:
        pass
    ops = (log_dir(tmp_path) / OPS_LOG).read_text(encoding="utf-8")
    assert "quote_not_in_draft" in ops
    assert "99.9" not in ops
    assert "record_content_finding" in ops


def test_service_review_writes_run_log(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("THESIS_LOG_DIR", raising=False)

    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    run_text = (log_dir(tmp_path) / RUN_LOG).read_text(encoding="utf-8")
    assert "review start" in run_text
    assert "review done" in run_text
