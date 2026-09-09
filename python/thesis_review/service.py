from __future__ import annotations

import json
import sys
from pathlib import Path

from thesis_review.checks.format import check_format
from thesis_review.checks.language import check_language
from thesis_review.errors import ReviewError
from thesis_review.history.ingest import issues_from_comments, issues_from_revisions, persist
from thesis_review.history.match import match_issue
from thesis_review.history.store import HistoryStore
from thesis_review.live import append_event, live_dir, reset_live, write_findings
from thesis_review.llm import model_available
from thesis_review.settings import AppSettings, load_settings
from thesis_review.types import Evidence, Finding, HistoryHit, IssueRecord, ReviewResult
from thesis_review.word.adapter import WordAdapter

ASSISTANT_AUTHOR = "审改助手"


class ThesisReviewService:
    def __init__(
        self,
        *,
        store: HistoryStore,
        adapter: WordAdapter | None = None,
        home: Path,
    ) -> None:
        self.store = store
        self.adapter = adapter or WordAdapter()
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)

    def ingest_history(
        self,
        *,
        teacher_id: str,
        student_id: str,
        major: str,
        draft_id: str,
        data: bytes,
    ) -> list[IssueRecord]:
        opened = self.adapter.open_bytes(data)
        comments = issues_from_comments(
            teacher_id=teacher_id,
            student_id=student_id,
            major=major,
            draft_id=draft_id,
            comments=self.adapter.extract_comments(opened),
        )
        revisions = issues_from_revisions(
            teacher_id=teacher_id,
            student_id=student_id,
            major=major,
            draft_id=draft_id,
            revisions=self.adapter.extract_revisions(opened),
            assistant_author=ASSISTANT_AUTHOR,
        )
        return persist(self.store, comments + revisions)

    def confirm_issue(self, *, teacher_id: str, student_id: str, issue_id: str) -> IssueRecord:
        return self.store.set_status(
            teacher_id=teacher_id,
            student_id=student_id,
            issue_id=issue_id,
            status="confirmed",
        )

    def disable_issue(self, *, teacher_id: str, student_id: str, issue_id: str) -> IssueRecord:
        return self.store.set_status(
            teacher_id=teacher_id,
            student_id=student_id,
            issue_id=issue_id,
            status="disabled",
        )

    def search_history(
        self,
        *,
        teacher_id: str,
        student_id: str,
        data: bytes,
    ) -> list[HistoryHit]:
        opened = self.adapter.open_bytes(data)
        paragraphs = self.adapter.list_paragraphs(opened)
        hits: list[HistoryHit] = []
        for issue in self.store.list_issues(
            teacher_id=teacher_id, student_id=student_id, status="confirmed"
        ):
            hit = match_issue(issue, paragraphs)
            if hit is not None:
                hits.append(hit)
        return hits

    def history_findings(
        self,
        *,
        teacher_id: str,
        student_id: str,
        data: bytes,
        draft_id: str,
    ) -> list[Finding]:
        hits = self.search_history(
            teacher_id=teacher_id, student_id=student_id, data=data
        )
        return [_history_finding(hit, self.store.get(hit.issue_id), draft_id) for hit in hits]

    def review(
        self,
        *,
        teacher_id: str,
        student_id: str,
        draft_id: str,
        data: bytes,
        output_dir: Path,
        use_model: bool = False,
        settings: AppSettings | None = None,
        use_pi: bool = False,
        faux: bool = False,
        faux_scenario: str = "",
        pi_timeout: int = 180,
        offline_fallback: bool = True,
    ) -> ReviewResult:
        current = settings or load_settings(self.home)
        warning = ""
        semantic = use_model and model_available(current)
        should_pi = faux or use_pi or semantic
        live = live_dir(output_dir)
        reset_live(live)
        if should_pi:
            try:
                return self._review_with_pi(
                    teacher_id=teacher_id,
                    student_id=student_id,
                    draft_id=draft_id,
                    data=data,
                    output_dir=output_dir,
                    settings=current,
                    faux=faux,
                    faux_scenario=faux_scenario,
                    timeout=pi_timeout,
                )
            except Exception as exc:  # noqa: BLE001 - fall back to offline rules
                if not offline_fallback:
                    raise
                warning = f"模型审查未能完成，已改用离线规则。{exc}"
                if semantic:
                    warning += " 历史问题未经确认，未写成复犯。"
        append_event(live, {"op": "open_draft", "ok": True})
        opened = self.adapter.open_bytes(data)
        paragraphs = self.adapter.list_paragraphs(opened)
        tables = self.adapter.list_tables(opened)
        findings: list[Finding] = []
        findings.extend(check_language(paragraphs, draft_id=draft_id))
        findings.extend(check_format(paragraphs, tables, draft_id=draft_id))
        append_event(live, {"op": "run_checks", "ok": True})
        write_findings(live, findings)
        if not (semantic and warning):
            findings.extend(
                self.history_findings(
                    teacher_id=teacher_id,
                    student_id=student_id,
                    data=data,
                    draft_id=draft_id,
                )
            )
            append_event(live, {"op": "get_history_candidates", "ok": True})
            write_findings(live, findings)
        used_model = False
        if use_model and not warning and not model_available(current):
            warning = "未配置模型密钥，已改用离线规则。"

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

        output_dir.mkdir(parents=True, exist_ok=True)
        reviewed_path = output_dir / f"{draft_id}-reviewed.docx"
        findings_path = output_dir / f"{draft_id}-findings.json"
        self.adapter.save(opened, reviewed_path)
        findings_path.write_text(
            json.dumps([item.to_dict() for item in findings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        append_event(live, {"op": "commit_review", "ok": True})
        write_findings(live, findings)
        append_event(live, {"op": "done", "ok": True})
        return ReviewResult(
            reviewed_path=reviewed_path,
            findings_path=findings_path,
            findings=findings,
            used_model=used_model,
            warning=warning,
        )

    def _review_with_pi(
        self,
        *,
        teacher_id: str,
        student_id: str,
        draft_id: str,
        data: bytes,
        output_dir: Path,
        settings: AppSettings,
        faux: bool,
        faux_scenario: str = "",
        timeout: int = 180,
    ) -> ReviewResult:
        from thesis_review.runtime import python_path, run_pi_review

        output_dir.mkdir(parents=True, exist_ok=True)
        source = output_dir / f"{draft_id}-source.docx"
        source.write_bytes(data)
        payload = run_pi_review(
            {
                "home": str(self.home),
                "teacher_id": teacher_id,
                "student_id": student_id,
                "major": settings.major,
                "draft_path": str(source),
                "draft_id": draft_id,
                "output_dir": str(output_dir),
                "provider": settings.provider,
                "model": settings.model or "gpt-4o-mini",
                "api_key": settings.api_key,
                "base_url": settings.base_url,
                "python": sys.executable,
                "pythonpath": python_path(),
                "faux_scenario": faux_scenario,
            },
            faux=faux,
            timeout=timeout,
        )
        findings_path = Path(payload["findings_path"])
        raw = json.loads(findings_path.read_text(encoding="utf-8"))
        findings = [Finding.from_dict(item) for item in raw]
        return ReviewResult(
            reviewed_path=Path(payload["reviewed_path"]),
            findings_path=findings_path,
            findings=findings,
            used_model=not faux,
            warning="",
        )


def _history_finding(hit: HistoryHit, issue: IssueRecord, draft_id: str) -> Finding:
    return Finding(
        id=f"history-{hit.issue_id}",
        issue_id=hit.issue_id,
        category=issue.category,
        source="history",
        problem="学生在新稿中仍出现已确认的历史问题。",
        rationale=f"历次稿件已指出：{issue.original_text}",
        quote=hit.new_quote,
        anchor=hit.new_anchor,
        paragraph_index=hit.paragraph_index,
        apply="comment",
        draft_id=draft_id,
        evidence=[
            Evidence(kind="history", draft_id=issue.source_draft_id, text=issue.original_text),
            Evidence(
                kind="history_span",
                draft_id=issue.source_draft_id,
                text=issue.original_span or hit.original_span,
            ),
        ],
    )


def _comment_body(finding: Finding) -> str:
    lines = [finding.problem, finding.rationale]
    if finding.source == "history":
        comment = next((item.text for item in finding.evidence if item.kind == "history"), "")
        old_span = next((item.text for item in finding.evidence if item.kind == "history_span"), "")
        lines = [f"历次稿件已指出：{comment or finding.rationale}"]
        if old_span:
            lines.append(f"旧稿原文：「{old_span}」。")
        if finding.quote:
            lines.append(f"本稿对应位置：「{finding.quote}」。")
        lines.append("请对照修改，并补上可核验的依据。")
    elif finding.source == "argument":
        evidence = next((item.text for item in finding.evidence if item.kind == "evidence"), "")
        lines = [finding.problem, finding.rationale]
        if finding.quote:
            lines.append(f"主张：「{finding.quote}」。")
        if evidence:
            lines.append(f"对照证据：「{evidence}」。")
    elif finding.suggested_new:
        lines.append(f"建议将「{finding.suggested_old}」改为「{finding.suggested_new}」。")
    return "\n".join(line for line in lines if line)
