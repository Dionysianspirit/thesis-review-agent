from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

from thesis_review.checks.format import check_format
from thesis_review.checks.language import check_language
from thesis_review.cli import build_service
from thesis_review.errors import ReviewError
from thesis_review.live import append_event, reset_live, write_findings
from thesis_review.history.match import HEADING_RE, match_issue, normalize
from thesis_review.service import ASSISTANT_AUTHOR, _comment_body, _history_finding
from thesis_review.types import Evidence, Finding, HistoryHit, IssueRecord, ParagraphView
from thesis_review.word.adapter import OpenedDocument, WordAdapter

NAV_OPS = frozenset({"list_outline", "read_section", "read_paragraphs", "find_text"})
LIVE_FINDING_OPS = frozenset({"run_checks", "confirm_history_finding", "record_argument_finding"})
NAV_BUDGET = 12
TRACE_PARAM_KEYS = frozenset({"start_ordinal", "limit", "max_hits", "draft_id", "issue_id"})
MAX_READ_PARAS = 8
MAX_READ_CHARS = 2000
MAX_ARGUMENT_FINDINGS = 3
MAX_FIND_HITS = 5
OUTLINE_TEXT_LIMIT = 80
FIND_CONTEXT = 40
NAMED_HEADINGS = (
    "摘要",
    "绪论",
    "引言",
    "相关工作",
    "研究方法",
    "实验",
    "实验结果",
    "结果与分析",
    "结论",
    "参考文献",
)


class Worker:
    def __init__(
        self,
        *,
        home: Path,
        teacher_id: str,
        student_id: str,
        major: str,
        live: Path | None = None,
    ) -> None:
        self.home = Path(home)
        self.teacher_id = teacher_id
        self.student_id = student_id
        self.major = major
        self.live = Path(live) if live else None
        self.service = build_service(self.home)
        self.adapter = WordAdapter()
        self.opened: OpenedDocument | None = None
        self.original: bytes = b""
        self.findings: list[Finding] = []
        self.nav_calls = 0
        self.argument_count = 0
        self.trace: list[dict] = []

    def dispatch(self, op: str, params: dict) -> dict:
        try:
            if op in NAV_OPS:
                if self.nav_calls >= NAV_BUDGET:
                    raise ReviewError("nav_budget", "导航次数已达上限，只能记录论证发现或提交审改。")
                self.nav_calls += 1
            handler = getattr(self, f"op_{op}", None)
            if handler is None:
                raise ReviewError("unknown_op", f"未知操作：{op}")
            result = handler(params)
            self._record_trace(op, params, ok=True)
            self._emit_live(op, params, ok=True)
            if op in LIVE_FINDING_OPS:
                self._write_live_findings()
            if op == "commit_review":
                result = dict(result)
                result["trace_path"] = self._write_trace(params)
                self._write_live_findings()
                self._emit_live("done", {}, ok=True)
            return result
        except ReviewError as exc:
            self._record_trace(op, params, ok=False, code=exc.code)
            self._emit_live(op, params, ok=False, code=exc.code)
            raise

    def _record_trace(self, op: str, params: dict, *, ok: bool, code: str = "") -> None:
        entry: dict = {"op": op, "ok": ok, "params": _safe_trace_params(params)}
        if not ok:
            entry["code"] = code
        self.trace.append(entry)

    def _write_trace(self, params: dict) -> str:
        output_dir = Path(params["output_dir"])
        draft_id = str(params.get("draft_id") or "new")
        output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = output_dir / f"{draft_id}-trace.json"
        trace_path.write_text(
            json.dumps({"draft_id": draft_id, "ops": self.trace}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(trace_path)

    def _emit_live(self, op: str, params: dict, *, ok: bool, code: str = "") -> None:
        event: dict = {"op": op, "ok": ok}
        heading = self._live_heading(op, params)
        if heading:
            event["heading"] = heading
        if code:
            event["code"] = code
        append_event(self.live, event)

    def _write_live_findings(self) -> None:
        write_findings(self.live, self.findings)

    def _live_heading(self, op: str, params: dict) -> str:
        if op != "read_section" or "start_ordinal" not in params:
            return ""
        try:
            ordinal = int(params["start_ordinal"])
        except (TypeError, ValueError):
            return ""
        try:
            items = self._paragraphs()
        except ReviewError:
            return ""
        for item in items:
            if item.ordinal == ordinal:
                return item.text[:OUTLINE_TEXT_LIMIT]
        return ""

    def op_open_draft(self, params: dict) -> dict:
        if params.get("path"):
            data = Path(params["path"]).read_bytes()
        else:
            import base64

            data = base64.b64decode(params["bytes_b64"])
        self.original = data
        self.opened = self.adapter.open_bytes(data)
        self.findings = []
        self.nav_calls = 0
        self.argument_count = 0
        self.trace = []
        reset_live(self.live)
        paragraphs = self.adapter.list_paragraphs(self.opened)
        return {"n_paragraphs": len(paragraphs)}

    def op_list_paragraphs(self, params: dict) -> dict:
        opened = self._require_open()
        return {
            "paragraphs": [
                {"ordinal": item.ordinal, "anchor": item.anchor, "text": item.text}
                for item in self.adapter.list_paragraphs(opened)
            ]
        }

    def op_run_checks(self, params: dict) -> dict:
        opened = self._require_open()
        draft_id = str(params.get("draft_id") or "new")
        findings = check_language(self.adapter.list_paragraphs(opened), draft_id=draft_id)
        findings.extend(check_format(self.adapter.list_paragraphs(opened), self.adapter.list_tables(opened), draft_id=draft_id))
        self._apply(findings)
        self.findings.extend(findings)
        return {"findings": [item.to_dict() for item in findings]}

    def op_get_history_candidates(self, params: dict) -> dict:
        self._require_open()
        hits = self.service.search_history(
            teacher_id=self.teacher_id,
            student_id=self.student_id,
            data=self.original,
        )
        candidates = []
        for hit in hits:
            issue = self.service.store.get(hit.issue_id)
            candidates.append(_candidate_payload(hit, issue))
        return {"candidates": candidates}

    def op_confirm_history_finding(self, params: dict) -> dict:
        self._require_open()
        issue_id = str(params.get("issue_id") or "").strip()
        new_quote = str(params.get("new_quote") or params.get("claim") or "").strip()
        draft_id = str(params.get("draft_id") or "new")
        if not new_quote:
            raise ReviewError("missing_quote", "缺少新稿原文，未写入批注。")
        issue = self._confirmed_issue(issue_id)
        if not _history_text_on_record(issue.original_span, issue) and not self._quote_in_source_or_opened(
            issue.original_span
        ):
            raise ReviewError("issue_mismatch", "旧稿原文与记录对不上，未写入批注。")
        if not _history_text_on_record(issue.original_text, issue) and not self._quote_in_source_or_opened(
            issue.original_text
        ):
            raise ReviewError("issue_mismatch", "旧稿批注与记录对不上，未写入批注。")
        original_paras = self._original_paragraphs()
        source_para = _paragraph_with_quote(new_quote, original_paras)
        if source_para is None and self._paragraph_with_quote(new_quote) is None:
            raise ReviewError("quote_not_in_draft", "新稿原文不在稿件中，未写入批注。")
        hit = match_issue(issue, original_paras)
        if hit is None or new_quote not in hit.new_quote:
            raise ReviewError("quote_not_in_draft", "新稿原文与历史召回位置对不上，未写入批注。")
        quote_para = self._paragraph_with_quote(new_quote)
        if quote_para is None:
            quote_para = next((item for item in self._paragraphs() if item.ordinal == hit.paragraph_index), None)
        if quote_para is None:
            raise ReviewError("quote_not_in_draft", "新稿原文不在稿件中，未写入批注。")
        finding = _history_finding(
            HistoryHit(
                issue_id=issue.id,
                new_anchor=quote_para.anchor,
                new_quote=new_quote,
                paragraph_index=quote_para.ordinal,
                evidence_text=issue.original_text,
                original_span=issue.original_span or hit.original_span,
                category=issue.category,
            ),
            issue,
            draft_id,
        )
        self._apply([finding])
        self.findings.append(finding)
        return {"ok": True, "id": finding.id}

    def _confirmed_issue(self, issue_id: str) -> IssueRecord:
        if not issue_id:
            raise ReviewError("issue_mismatch", "缺少历史问题编号，未写入批注。")
        try:
            issue = self.service.store.get(issue_id)
        except KeyError as exc:
            raise ReviewError("issue_mismatch", "历史问题不存在，未写入批注。") from exc
        if (
            issue.teacher_id != self.teacher_id
            or issue.student_id != self.student_id
            or issue.status != "confirmed"
        ):
            raise ReviewError("issue_mismatch", "历史问题不属于当前师生或尚未确认，未写入批注。")
        return issue

    def op_list_outline(self, params: dict) -> dict:
        outline = []
        for item in self._paragraphs():
            if not _is_outline_heading(item.text):
                continue
            outline.append(
                {
                    "ordinal": item.ordinal,
                    "anchor": item.anchor,
                    "text": item.text[:OUTLINE_TEXT_LIMIT],
                }
            )
        return {"outline": outline}

    def op_read_paragraphs(self, params: dict) -> dict:
        start = _require_ordinal(params)
        limit = int(params.get("limit") or MAX_READ_PARAS)
        selected = [item for item in self._paragraphs() if item.ordinal >= start]
        paragraphs, truncated = _clip_paragraphs(selected, limit=limit)
        return {"paragraphs": paragraphs, "truncated": truncated}

    def op_read_section(self, params: dict) -> dict:
        start = _require_ordinal(params)
        limit = int(params.get("limit") or MAX_READ_PARAS)
        items = self._paragraphs()
        end = next(
            (
                item.ordinal
                for item in items
                if item.ordinal > start and _is_outline_heading(item.text)
            ),
            None,
        )
        selected = [
            item
            for item in items
            if item.ordinal >= start and (end is None or item.ordinal < end)
        ]
        paragraphs, truncated = _clip_paragraphs(selected, limit=limit)
        return {"paragraphs": paragraphs, "truncated": truncated}

    def op_find_text(self, params: dict) -> dict:
        needle = str(params.get("needle") or "").strip()
        if not needle:
            raise ReviewError("invalid_params", "缺少检索词。")
        max_hits = min(int(params.get("max_hits") or MAX_FIND_HITS), MAX_FIND_HITS)
        hits: list[dict] = []
        for item in self._paragraphs():
            index = item.text.find(needle)
            if index < 0:
                continue
            start = max(0, index - FIND_CONTEXT)
            stop = min(len(item.text), index + len(needle) + FIND_CONTEXT)
            hits.append(
                {
                    "ordinal": item.ordinal,
                    "anchor": item.anchor,
                    "snippet": item.text[start:stop],
                }
            )
            if len(hits) >= max_hits:
                break
        return {"hits": hits}

    def op_record_argument_finding(self, params: dict) -> dict:
        claim = str(params.get("claim_quote") or "").strip()
        evidence = str(params.get("evidence_quote") or "").strip()
        problem = str(params.get("problem") or "").strip()
        rationale = str(params.get("rationale") or "").strip()
        draft_id = str(params.get("draft_id") or "new")
        if self.argument_count >= MAX_ARGUMENT_FINDINGS:
            raise ReviewError("argument_limit", "论证发现已达上限。")
        if "再次" in f"{problem}\n{rationale}" or "屡次" in f"{problem}\n{rationale}":
            raise ReviewError("repeat_wording", "论证批注不能使用「再次」「屡次」。")
        claim_para = self._paragraph_with_quote(claim)
        evidence_para = self._paragraph_with_quote(evidence)
        if claim_para is None or evidence_para is None:
            raise ReviewError("quote_not_in_draft", "主张或证据原文不在稿件中，未写入批注。")
        self.argument_count += 1
        finding = Finding(
            id=f"argument-{self.argument_count}",
            category="B",
            source="argument",
            code="claim_without_evidence",
            problem=problem or "关键主张缺少与用词相符的实验证据。",
            rationale=rationale or "对照实验或结果原文后，主张未能被数据支持。",
            quote=claim,
            anchor=claim_para.anchor,
            paragraph_index=claim_para.ordinal,
            apply="comment",
            draft_id=draft_id,
            evidence=[
                Evidence(kind="claim", draft_id=draft_id, text=claim),
                Evidence(kind="evidence", draft_id=draft_id, text=evidence),
            ],
        )
        self._apply([finding])
        self.findings.append(finding)
        return {"ok": True, "id": finding.id}

    def op_add_comment(self, params: dict) -> dict:
        opened = self._require_open()
        self.adapter.add_comment(
            opened,
            anchor=str(params["anchor"]),
            text=str(params["text"]),
            author=str(params.get("author") or ASSISTANT_AUTHOR),
        )
        return {"ok": True}

    def op_replace_tracked(self, params: dict) -> dict:
        opened = self._require_open()
        result = self.adapter.replace_tracked(
            opened,
            anchor=str(params["anchor"]),
            old=str(params["old"]),
            new=str(params["new"]),
            author=str(params.get("author") or ASSISTANT_AUTHOR),
        )
        return {"n_replaced": result.n_replaced, "new_anchor": result.new_anchor}

    def op_commit_review(self, params: dict) -> dict:
        opened = self._require_open()
        output_dir = Path(params["output_dir"])
        draft_id = str(params.get("draft_id") or "new")
        output_dir.mkdir(parents=True, exist_ok=True)
        reviewed_path = output_dir / f"{draft_id}-reviewed.docx"
        findings_path = output_dir / f"{draft_id}-findings.json"
        self.adapter.save(opened, reviewed_path)
        findings_path.write_text(
            json.dumps([item.to_dict() for item in self.findings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "reviewed_path": str(reviewed_path),
            "findings_path": str(findings_path),
            "n_findings": len(self.findings),
        }

    def _require_open(self) -> OpenedDocument:
        if self.opened is None:
            raise ReviewError("not_open", "尚未打开稿件。")
        return self.opened

    def _paragraphs(self) -> list[ParagraphView]:
        return self.adapter.list_paragraphs(self._require_open())

    def _original_paragraphs(self) -> list[ParagraphView]:
        return self.adapter.list_paragraphs(self.adapter.open_bytes(self.original))

    def _paragraph_with_quote(self, quote: str) -> ParagraphView | None:
        return _paragraph_with_quote(quote, self._paragraphs())

    def _quote_in_source_or_opened(self, quote: str) -> bool:
        if not quote:
            return True
        if _paragraph_with_quote(quote, self._original_paragraphs()) is not None:
            return True
        return self._paragraph_with_quote(quote) is not None

    def _apply(self, findings: list[Finding]) -> None:
        opened = self._require_open()
        for finding in findings:
            if finding.apply in {"comment", "both"} and finding.anchor.startswith("P"):
                try:
                    self.adapter.add_comment(
                        opened,
                        anchor=finding.anchor,
                        text=_comment_body(finding),
                        author=ASSISTANT_AUTHOR,
                    )
                except ReviewError:
                    continue
        for finding in findings:
            if finding.apply in {"revision", "both"} and finding.suggested_old and finding.suggested_new:
                try:
                    self.adapter.replace_tracked(
                        opened,
                        anchor=finding.anchor,
                        old=finding.suggested_old,
                        new=finding.suggested_new,
                        author=ASSISTANT_AUTHOR,
                    )
                except ReviewError:
                    continue


def _safe_trace_params(params: dict) -> dict:
    safe = {key: params[key] for key in TRACE_PARAM_KEYS if key in params}
    if "needle" in params:
        safe["needle_len"] = len(str(params.get("needle") or ""))
    return safe


def _paragraph_with_quote(quote: str, paragraphs: list[ParagraphView]) -> ParagraphView | None:
    if not quote:
        return None
    for item in paragraphs:
        if quote in item.text:
            return item
    return None


def _candidate_payload(hit: HistoryHit, issue: IssueRecord) -> dict:
    return {
        "issue_id": hit.issue_id,
        "category": issue.category,
        "problem": issue.problem or issue.original_text,
        "original_text": issue.original_text,
        "old_span": issue.original_span or hit.original_span,
        "new_quote": hit.new_quote,
        "new_anchor": hit.new_anchor,
        "issue_type": issue.issue_type,
        "scope": issue.scope,
        "teacher_intent": issue.teacher_intent,
        "expected_fix": issue.suggested_fix,
    }


def _history_text_on_record(text: str, issue: IssueRecord) -> bool:
    value = (text or "").strip()
    if not value:
        return True
    return value in {issue.original_span, issue.original_text, issue.problem}


def _is_outline_heading(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if HEADING_RE.match(stripped) and len(normalize(stripped)) <= 40:
        return True
    compact = normalize(stripped)
    return compact in {normalize(name) for name in NAMED_HEADINGS}


def _require_ordinal(params: dict) -> int:
    if "start_ordinal" not in params:
        raise ReviewError("invalid_params", "缺少 start_ordinal。")
    return int(params["start_ordinal"])


def _clip_paragraphs(items: list[ParagraphView], *, limit: int) -> tuple[list[dict], bool]:
    cap = max(1, min(int(limit), MAX_READ_PARAS))
    selected: list[dict] = []
    chars = 0
    for item in items:
        if len(selected) >= cap or chars >= MAX_READ_CHARS:
            return selected, True
        text = item.text
        if chars + len(text) > MAX_READ_CHARS:
            remain = MAX_READ_CHARS - chars
            if remain > 0:
                selected.append(
                    {"ordinal": item.ordinal, "anchor": item.anchor, "text": text[:remain]}
                )
            return selected, True
        selected.append({"ordinal": item.ordinal, "anchor": item.anchor, "text": text})
        chars += len(text)
    return selected, False


def _handle_line(worker: Worker, line: str) -> str:
    request = json.loads(line)
    ident = request.get("id")
    try:
        result = worker.dispatch(str(request["op"]), request.get("params") or {})
        return json.dumps({"id": ident, "result": result}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - protocol boundary
        code = getattr(exc, "code", "error")
        return json.dumps({"id": ident, "error": {"code": code, "message": str(exc)}}, ensure_ascii=False)


def _serve_tcp(worker: Worker, portfile: Path) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    portfile.parent.mkdir(parents=True, exist_ok=True)
    portfile.write_text(str(server.getsockname()[1]), encoding="ascii")
    conn, _unused = server.accept()
    with conn:
        buffer = b""
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                conn.sendall((_handle_line(worker, line) + "\n").encode("utf-8"))
    server.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thesis-review-worker")
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--teacher", required=True)
    parser.add_argument("--student", required=True)
    parser.add_argument("--major", default="人工智能")
    parser.add_argument("--portfile", type=Path, default=None)
    parser.add_argument("--live", type=Path, default=None)
    args = parser.parse_args(argv)
    worker = Worker(
        home=args.home,
        teacher_id=args.teacher,
        student_id=args.student,
        major=args.major,
        live=args.live,
    )
    if args.portfile is not None:
        _serve_tcp(worker, args.portfile)
        return 0
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        sys.stdout.write(_handle_line(worker, line) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
