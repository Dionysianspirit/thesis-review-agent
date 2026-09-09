from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import OVERCLAIM_CLAIM_QUOTE, sample_overclaim_draft
from thesis_review.live import append_event, chinese_message, read_progress
from thesis_review.paths import repo_root
from thesis_review.worker import Worker


def test_intent_status_is_user_visible_and_not_tech_log():
    text = chinese_message("report_intent", intent="正在检查摘要中的核心结论")
    assert text == "正在检查摘要中的核心结论"
    assert "chain" not in text.lower()


def test_live_intent_updates_message_without_leaking_quotes(tmp_path: Path):
    live = tmp_path / "live"
    append_event(live, {"op": "report_intent", "ok": True, "intent": "正在核对第 3 章与第 5 章中的准确率数据"})
    progress = read_progress(live)
    assert "正在核对第 3 章与第 5 章中的准确率数据" in progress["message"]
    assert progress["tech_log"] == []
    append_event(live, {"op": "list_outline", "ok": True, "quote": OVERCLAIM_CLAIM_QUOTE, "api_key": "sk-secret"})
    progress = read_progress(live)
    assert progress["tech_log"][0]["op"] == "list_outline"
    assert all(item["op"] != "report_intent" for item in progress["tech_log"])
    dumped = (live / "events.jsonl").read_text(encoding="utf-8")
    assert OVERCLAIM_CLAIM_QUOTE not in dumped
    assert "sk-secret" not in dumped


def test_findings_appear_before_commit(tmp_path: Path):
    live = tmp_path / "live"
    worker = Worker(home=tmp_path, teacher_id="teacher-a", student_id="zhou", major="人工智能", live=live)
    import base64

    worker.dispatch("open_draft", {"bytes_b64": base64.b64encode(sample_overclaim_draft()).decode("ascii")})
    worker.dispatch("report_intent", {"message": "正在读：3 实验结果"})
    worker.dispatch("run_checks", {"draft_id": "overclaim"})
    snapshot = json.loads((live / "findings.json").read_text(encoding="utf-8"))
    assert snapshot
    events = [json.loads(line) for line in (live / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "commit_review" not in [item["op"] for item in events]
    assert any(item.get("op") == "report_intent" for item in events)
    progress = read_progress(live)
    assert progress["findings"]


def test_first_pass_prompt_has_no_preinjected_claim():
    text = (repo_root() / "agent" / "review.mjs").read_text(encoding="utf-8")
    prompt = text.split("const OVERCLAIM_CLAIM")[0]
    assert "实验结果表明该方法显著提升了分类准确率" not in prompt
    assert "list_outline" in prompt
    assert "report_intent" in prompt
