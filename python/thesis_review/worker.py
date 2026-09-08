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
from thesis_review.llm import model_available
from thesis_review.service import ASSISTANT_AUTHOR, _comment_body
from thesis_review.settings import load_settings
from thesis_review.types import Finding
from thesis_review.word.adapter import OpenedDocument, WordAdapter


class Worker:
    def __init__(self, *, home: Path, teacher_id: str, student_id: str, major: str) -> None:
        self.home = Path(home)
        self.teacher_id = teacher_id
        self.student_id = student_id
        self.major = major
        self.service = build_service(self.home)
        self.adapter = WordAdapter()
        self.opened: OpenedDocument | None = None
        self.original: bytes = b""
        self.findings: list[Finding] = []

    def dispatch(self, op: str, params: dict) -> dict:
        handler = getattr(self, f"op_{op}", None)
        if handler is None:
            raise ReviewError("unknown_op", f"未知操作：{op}")
        return handler(params)

    def op_open_draft(self, params: dict) -> dict:
        if params.get("path"):
            data = Path(params["path"]).read_bytes()
        else:
            import base64

            data = base64.b64decode(params["bytes_b64"])
        self.original = data
        self.opened = self.adapter.open_bytes(data)
        self.findings = []
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

    def op_search_history(self, params: dict) -> dict:
        self._require_open()
        settings = load_settings(self.home)
        extra = self.service.history_findings(
            teacher_id=self.teacher_id,
            student_id=self.student_id,
            data=self.original,
            draft_id=str(params.get("draft_id") or "new"),
            settings=settings,
            confirm_with_model=model_available(settings),
        )
        self._apply(extra)
        self.findings.extend(extra)
        return {
            "hits": [
                {
                    "issue_id": item.issue_id,
                    "quote": item.quote,
                    "evidence": next(
                        (row.text for row in item.evidence if row.kind == "history"),
                        item.rationale,
                    ),
                }
                for item in extra
            ]
        }

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
    args = parser.parse_args(argv)
    worker = Worker(home=args.home, teacher_id=args.teacher, student_id=args.student, major=args.major)
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
