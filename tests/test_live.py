from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import OVERCLAIM_CLAIM_QUOTE, sample_new_draft, sample_overclaim_draft
from thesis_review.history.store import HistoryStore
from thesis_review.live import append_event, chinese_message, read_progress, write_findings
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter


def test_chinese_message_read_section_includes_heading():
    text = chinese_message("read_section", heading="3 实验结果")
    assert "正在读" in text
    assert "3 实验结果" in text


def test_chinese_message_unknown_op_keeps_previous():
    previous = "正在看章节大纲"
    assert chinese_message("list_paragraphs", previous=previous) == previous


def test_append_event_strips_quotes_and_api_key(tmp_path: Path):
    live = tmp_path / "live"
    append_event(
        live,
        {
            "op": "record_argument_finding",
            "ok": True,
            "claim_quote": OVERCLAIM_CLAIM_QUOTE,
            "quote": "段落全文不应出现",
            "api_key": "sk-secret",
        },
    )
    dumped = (live / "events.jsonl").read_text(encoding="utf-8")
    assert OVERCLAIM_CLAIM_QUOTE not in dumped
    assert "段落全文不应出现" not in dumped
    assert "sk-secret" not in dumped
    assert "api_key" not in dumped
    event = json.loads(dumped.strip())
    assert event["op"] == "record_argument_finding"
    assert event["ok"] is True


def test_read_progress_returns_current_sentence_and_findings(tmp_path: Path):
    live = tmp_path / "live"
    append_event(live, {"op": "open_draft", "ok": True})
    append_event(live, {"op": "list_outline", "ok": True})
    append_event(live, {"op": "list_paragraphs", "ok": True})
    append_event(live, {"op": "read_section", "ok": True, "heading": "3 实验结果"})
    write_findings(
        live,
        [
            {
                "id": "rule-A-1",
                "source": "rule",
                "category": "A",
                "problem": "叠词加强语气。",
            }
        ],
    )
    progress = read_progress(live)
    assert "正在读" in progress["message"]
    assert "3 实验结果" in progress["message"]
    assert "list_paragraphs" not in progress["message"]
    assert progress["findings"][0]["id"] == "rule-A-1"
    ops = [item["op"] for item in progress["tech_log"]]
    assert ops == ["open_draft", "list_outline", "list_paragraphs", "read_section"]


def test_read_progress_missing_dir_is_empty(tmp_path: Path):
    progress = read_progress(tmp_path / "missing")
    assert progress["message"] == ""
    assert progress["findings"] == []
    assert progress["tech_log"] == []


def test_offline_review_writes_live_events_ending_with_done(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    assert result.reviewed_path.is_file()
    events_path = tmp_path / "out" / "live" / "events.jsonl"
    assert events_path.is_file()
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ops = [item["op"] for item in events]
    assert "open_draft" in ops
    assert "run_checks" in ops
    assert ops[-2:] == ["commit_review", "done"]
    dumped = events_path.read_text(encoding="utf-8")
    assert "api_key" not in dumped
    assert OVERCLAIM_CLAIM_QUOTE not in dumped


def test_offline_overclaim_live_events_omit_body_quotes(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="overclaim",
        data=sample_overclaim_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    dumped = (tmp_path / "out" / "live" / "events.jsonl").read_text(encoding="utf-8")
    assert OVERCLAIM_CLAIM_QUOTE not in dumped
