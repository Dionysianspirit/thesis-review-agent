from __future__ import annotations

import json
from pathlib import Path

ALLOWED_EVENT_KEYS = frozenset({"op", "ok", "heading", "code"})
HEADING_LIMIT = 80

OP_ZH = {
    "open_draft": "正在打开稿件",
    "list_outline": "正在看章节大纲",
    "read_paragraphs": "正在读正文",
    "find_text": "正在检索原文",
    "run_checks": "正在核对语言和格式",
    "get_history_candidates": "正在核对是否复犯",
    "confirm_history_finding": "已写入一条历史复犯批注",
    "record_argument_finding": "已写入一条论证批注",
    "commit_review": "正在写出 Word 审改稿",
    "done": "初筛完成",
}


def live_dir(output_dir: Path | str) -> Path:
    return Path(output_dir) / "live"


def reset_live(directory: Path | None) -> None:
    if directory is None:
        return
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path / "events.jsonl").write_text("", encoding="utf-8")
    (path / "findings.json").write_text("[]", encoding="utf-8")


def chinese_message(op: str, heading: str = "", previous: str = "") -> str:
    if op == "read_section":
        title = str(heading or "").strip()
        if title:
            return f"正在读：{title}"
        return "正在读章节"
    mapped = OP_ZH.get(op)
    if mapped is None:
        return previous
    return mapped


def append_event(directory: Path | None, event: dict) -> None:
    if directory is None:
        return
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    safe: dict = {}
    if "op" in ALLOWED_EVENT_KEYS and "op" in event:
        safe["op"] = str(event.get("op") or "")
    if "ok" in ALLOWED_EVENT_KEYS and "ok" in event:
        safe["ok"] = bool(event.get("ok"))
    heading = str(event.get("heading") or "").strip()[:HEADING_LIMIT]
    if heading:
        safe["heading"] = heading
    if event.get("code"):
        safe["code"] = str(event.get("code"))
    with (path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe, ensure_ascii=False) + "\n")
        handle.flush()


def write_findings(directory: Path | None, findings: list) -> None:
    if directory is None:
        return
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    payload = [item.to_dict() if hasattr(item, "to_dict") else item for item in findings]
    (path / "findings.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_progress(directory: Path | None) -> dict:
    empty = {"message": "", "findings": [], "tech_log": []}
    if directory is None:
        return dict(empty)
    path = Path(directory)
    events_path = path / "events.jsonl"
    findings_path = path / "findings.json"
    events: list[dict] = []
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    findings: list = []
    if findings_path.is_file():
        try:
            raw = json.loads(findings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = []
        if isinstance(raw, list):
            findings = raw
    message = ""
    tech_log: list[dict] = []
    for event in events:
        op = str(event.get("op") or "")
        heading = str(event.get("heading") or "")
        message = chinese_message(op, heading=heading, previous=message)
        entry: dict = {"op": op, "ok": event.get("ok", True)}
        if heading:
            entry["heading"] = heading
        tech_log.append(entry)
    return {"message": message, "findings": findings, "tech_log": tech_log}
