from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path

import webview

from thesis_review.cli import build_service, main as cli_main
from thesis_review.worker import main as worker_main
from thesis_review.fixtures import write_demo_drafts
from thesis_review.paths import app_home, gui_dir
from thesis_review.service import ThesisReviewService
from thesis_review.settings import AppSettings, load_settings, save_settings


class Bridge:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.service: ThesisReviewService = build_service(home)
        self.settings: AppSettings = load_settings(home)
        self.window = None
        self.reviewed_path = ""
        self.output_dir = str(self._default_output())
        self.status = "准备就绪。"
        self.findings: list[dict] = []
        self.recall: dict = self._empty_recall()
        self.used_model = False
        self.warning = ""

    @staticmethod
    def _empty_recall() -> dict:
        return {"confirmed": 0, "recalled": 0, "written": 0, "skipped": [], "absent": []}

    def state(self) -> dict:
        issues = [
            asdict(item)
            for item in self.service.store.list_issues(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
            )
        ]
        payload = asdict(self.settings)
        payload.update(
            {
                "issues": issues,
                "reviewed_path": self.reviewed_path,
                "output_dir": self.output_dir,
                "status": self.status,
                "findings": self.findings,
                "recall": self.recall,
                "used_model": self.used_model,
                "warning": self.warning,
            }
        )
        return payload

    def save_identity(self, payload: dict) -> dict:
        self.settings.teacher_name = str(payload.get("teacher_name") or self.settings.teacher_name)
        self.settings.student_id = str(payload.get("student_id") or self.settings.student_id).strip()
        self.settings.major = str(payload.get("major") or self.settings.major)
        if not self.settings.teacher_id:
            self.settings.teacher_id = "teacher-a"
        save_settings(self.home, self.settings)
        self.status = "已保存身份。"
        return {"ok": True}

    def save_model(self, payload: dict) -> dict:
        self.settings.provider = str(payload.get("provider") or "openai-compatible")
        self.settings.model = str(payload.get("model") or "")
        self.settings.base_url = str(payload.get("base_url") or "")
        self.settings.api_key = str(payload.get("api_key") or "")
        save_settings(self.home, self.settings)
        return {"ok": True}

    def ingest_files(self) -> dict:
        files = self._pick(multiple=True)
        if not files:
            return {"ok": False, "message": "未选择文件。"}
        count = 0
        for index, path in enumerate(files, start=1):
            self.service.ingest_history(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
                major=self.settings.major,
                draft_id=Path(path).stem or f"history-{index}",
                data=Path(path).read_bytes(),
            )
            count += 1
        self.status = f"已导入 {count} 份历史稿，请确认问题。"
        return {"ok": True, "message": self.status}

    def load_demo(self) -> dict:
        drafts = write_demo_drafts(self.home / "demo")
        self.settings.student_id = "zhou"
        self.settings.teacher_name = "老师甲"
        self.settings.major = "人工智能"
        save_settings(self.home, self.settings)
        for draft_id, path in drafts.items():
            if draft_id == "new":
                continue
            self.service.ingest_history(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
                major=self.settings.major,
                draft_id=draft_id,
                data=path.read_bytes(),
            )
        self.status = "已载入小周的演示稿。请确认历史问题后审查 new.docx。"
        return {"ok": True, "message": self.status}

    def set_issue(self, issue_id: str, confirmed: bool) -> dict:
        if confirmed:
            self.service.confirm_issue(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
                issue_id=issue_id,
            )
        else:
            self.service.disable_issue(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
                issue_id=issue_id,
            )
        return {"ok": True}

    def review_file(self) -> dict:
        files = self._pick(multiple=False)
        if not files:
            return {"ok": False, "message": "未选择新稿。"}
        path = Path(files[0])
        data = path.read_bytes()
        output_dir = self._default_output()
        confirmed = self.service.store.list_issues(
            teacher_id=self.settings.teacher_id,
            student_id=self.settings.student_id,
            status="confirmed",
        )
        try:
            hits = self.service.search_history(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
                data=data,
            )
        except Exception:  # noqa: BLE001 - recall snapshot is best-effort
            hits = []
        recalled_ids = {hit.issue_id for hit in hits}
        try:
            result = self.service.review(
                teacher_id=self.settings.teacher_id,
                student_id=self.settings.student_id,
                draft_id=path.stem or "new",
                data=data,
                output_dir=output_dir,
                use_model=bool(self.settings.api_key),
                settings=self.settings,
            )
        except Exception as exc:  # noqa: BLE001 - surface to teachers
            self.status = f"审查失败：{exc}"
            self.findings = []
            self.recall = self._empty_recall()
            self.warning = ""
            return {"ok": False, "message": self.status}
        written_ids = {item.issue_id for item in result.findings if item.issue_id}
        skipped = []
        for hit in hits:
            if hit.issue_id in written_ids:
                continue
            issue = self.service.store.get(hit.issue_id)
            if result.warning:
                reason = "模型审查未完成，按规则不把字符串命中写成复犯。"
            else:
                reason = "在新稿中召回了相似原文，但未判定为复犯（可能已修复或依据不足），未写入批注。"
            skipped.append(
                {
                    "issue_id": hit.issue_id,
                    "category": issue.category,
                    "problem": issue.problem or issue.original_text,
                    "original_text": issue.original_text,
                    "new_quote": hit.new_quote,
                    "reason": reason,
                }
            )
        absent = [
            {
                "issue_id": issue.id,
                "category": issue.category,
                "problem": issue.problem or issue.original_text,
                "original_text": issue.original_text,
                "reason": "本次未在新稿中发现对应原文（可能已改正）。",
            }
            for issue in confirmed
            if issue.id not in recalled_ids
        ]
        self.recall = {
            "confirmed": len(confirmed),
            "recalled": len(recalled_ids),
            "written": len(written_ids),
            "skipped": skipped,
            "absent": absent,
        }
        self.findings = [item.to_dict() for item in result.findings]
        self.used_model = result.used_model
        self.warning = result.warning or ""
        self.reviewed_path = str(result.reviewed_path)
        self.output_dir = str(output_dir)
        extra = result.warning or ""
        self.status = f"完成，共 {len(result.findings)} 条建议。{extra}".strip()
        return {
            "ok": True,
            "message": self.status,
            "findings": self.findings,
            "recall": self.recall,
            "used_model": self.used_model,
            "warning": self.warning,
        }

    def open_reviewed(self) -> dict:
        if not self.reviewed_path:
            return {"ok": False, "message": "还没有审改稿。"}
        os.startfile(self.reviewed_path)  # type: ignore[attr-defined]
        return {"ok": True}

    def open_folder(self) -> dict:
        if not self.output_dir:
            return {"ok": False, "message": "还没有结果文件夹。"}
        os.startfile(self.output_dir)  # type: ignore[attr-defined]
        return {"ok": True}

    def _default_output(self) -> Path:
        documents = Path.home() / "Documents" / "论文审改结果"
        if self.settings.output_dir:
            return Path(self.settings.output_dir)
        documents.mkdir(parents=True, exist_ok=True)
        return documents

    def _pick(self, *, multiple: bool) -> list[str]:
        if self.window is None:
            return []
        dialog = getattr(webview, "FileDialog", None)
        mode = dialog.OPEN if dialog is not None else webview.OPEN_DIALOG
        selected = self.window.create_file_dialog(
            mode,
            allow_multiple=multiple,
            file_types=("Word 文档 (*.docx)",),
        )
        if not selected:
            return []
        return [str(item) for item in selected]


def start_gui() -> int:
    home = app_home()
    home.mkdir(parents=True, exist_ok=True)
    bridge = Bridge(home)
    html = gui_dir() / "ui.html"
    window = webview.create_window(
        "论文审改助手",
        str(html),
        js_api=bridge,
        width=1080,
        height=780,
        min_size=(880, 640),
    )
    bridge.window = window
    webview.start()
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        return worker_main(sys.argv[2:])
    if len(sys.argv) > 1:
        return cli_main(sys.argv[1:])
    return start_gui()


if __name__ == "__main__":
    raise SystemExit(main())
