from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from thesis_review.evalscore import CaseScore, score_case
from thesis_review.fixtures import overclaim_draft, supported_claim_draft, write_demo_drafts
from thesis_review.history.store import HistoryStore
from thesis_review.llm import model_available
from thesis_review.service import ThesisReviewService
from thesis_review.settings import AppSettings, load_settings
from thesis_review.types import ReviewResult
from thesis_review.word.adapter import WordAdapter

NO_KEY_MESSAGE = "未配置模型密钥。请在窗口「模型设置」中填写后重试。"
EVAL_TIMEOUT_SEC = 600
GOLD_CASES = ("overclaim", "abandon", "history")
TEACHER_ID = "teacher-a"
STUDENT_ID = "zhou"
MAJOR = "人工智能"


def settings_for_eval(home: Path) -> AppSettings:
    settings = load_settings(home)
    if not settings.api_key.strip():
        settings.api_key = (
            os.environ.get("THESIS_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        ).strip()
    return settings


def review_live(
    service: ThesisReviewService,
    *,
    teacher_id: str,
    student_id: str,
    draft_id: str,
    data: bytes,
    output_dir: Path,
    settings: AppSettings,
) -> ReviewResult:
    return service.review(
        teacher_id=teacher_id,
        student_id=student_id,
        draft_id=draft_id,
        data=data,
        output_dir=output_dir,
        settings=settings,
        use_model=True,
        pi_timeout=EVAL_TIMEOUT_SEC,
        offline_fallback=False,
    )


def run_eval_command(
    *,
    settings_home: Path,
    out: Path,
    manifest: Path | None = None,
    review=None,
) -> int:
    settings = settings_for_eval(settings_home)
    if not model_available(settings):
        print(NO_KEY_MESSAGE, file=sys.stderr)
        return 2
    review_fn = review or review_live
    scores = list(run_gold_eval(settings, out, review_fn=review_fn))
    if manifest is not None:
        scores.extend(run_manifest_eval(settings, out, manifest, review_fn=review_fn))
    payload = {
        "model": settings.model,
        "provider": settings.provider,
        "passed": all(item.passed for item in scores),
        "cases": [_public_score(item) for item in scores],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for item in scores:
        status = "pass" if item.passed else "fail"
        print(f"{item.case}: {status}")
        if item.reasons:
            print("  " + "; ".join(item.reasons))
        if item.tool_ops:
            print("  tools: " + ",".join(item.tool_ops))
        if item.sources:
            print("  sources: " + ",".join(f"{key}={value}" for key, value in item.sources.items()))
    print("summary: " + str(out / "summary.json"))
    return 0 if payload["passed"] else 1


def _service(home: Path) -> ThesisReviewService:
    home.mkdir(parents=True, exist_ok=True)
    return ThesisReviewService(
        store=HistoryStore(home / "thesis-review.sqlite"),
        adapter=WordAdapter(),
        home=home,
    )


def run_gold_eval(settings: AppSettings, out: Path, *, review_fn) -> list[CaseScore]:
    workspace = out / "workspace"
    service = _service(workspace)
    scores: list[CaseScore] = []
    for name in GOLD_CASES:
        case_dir = out / name
        scores.append(_run_named_case(name, service, settings, case_dir, review_fn=review_fn))
    return scores


def run_manifest_eval(
    settings: AppSettings,
    out: Path,
    manifest: Path,
    *,
    review_fn,
) -> list[CaseScore]:
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    workspace = out / "real-workspace"
    service = _service(workspace)
    scores: list[CaseScore] = []
    for item in spec.get("cases") or []:
        name = str(item.get("name") or "real")
        case_dir = out / "real" / name
        scores.append(
            _run_manifest_case(
                item,
                service,
                settings,
                case_dir,
                manifest.parent,
                review_fn=review_fn,
            )
        )
    return scores


def _run_named_case(
    name: str,
    service: ThesisReviewService,
    settings: AppSettings,
    case_dir: Path,
    *,
    review_fn,
) -> CaseScore:
    if name == "overclaim":
        data = overclaim_draft()
        draft_id = "overclaim"
    elif name == "abandon":
        data = supported_claim_draft()
        draft_id = "abandon"
    else:
        drafts = write_demo_drafts(case_dir / "demo-drafts")
        candidates = service.ingest_history(
            teacher_id=TEACHER_ID,
            student_id=STUDENT_ID,
            major=MAJOR,
            draft_id="v1",
            data=drafts["v1"].read_bytes(),
        )
        for record in candidates:
            service.confirm_issue(teacher_id=TEACHER_ID, student_id=STUDENT_ID, issue_id=record.id)
        data = drafts["new"].read_bytes()
        draft_id = "history"
    return _score_review(
        name,
        service,
        settings,
        case_dir,
        draft_id=draft_id,
        data=data,
        review_fn=review_fn,
    )


def _run_manifest_case(
    item: dict,
    service: ThesisReviewService,
    settings: AppSettings,
    case_dir: Path,
    base: Path,
    *,
    review_fn,
) -> CaseScore:
    name = str(item.get("name") or "real")
    docx = _resolve_path(item.get("docx"), base)
    history = item.get("history")
    if history:
        history_path = _resolve_path(history, base)
        candidates = service.ingest_history(
            teacher_id=TEACHER_ID,
            student_id=STUDENT_ID,
            major=MAJOR,
            draft_id="history",
            data=history_path.read_bytes(),
        )
        for record in candidates:
            service.confirm_issue(teacher_id=TEACHER_ID, student_id=STUDENT_ID, issue_id=record.id)
    kind = "overclaim" if item.get("expect_argument") else "abandon"
    score = _score_review(
        kind,
        service,
        settings,
        case_dir,
        draft_id=name,
        data=docx.read_bytes(),
        review_fn=review_fn,
    )
    reasons = list(score.reasons)
    if item.get("expect_history") and score.sources.get("history", 0) < 1:
        reasons.append("缺少历史复犯批注")
    return CaseScore(
        case=name,
        passed=not reasons and not score.error,
        reasons=reasons,
        tool_ops=score.tool_ops,
        n_findings=score.n_findings,
        sources=score.sources,
        error=score.error,
    )


def _score_review(
    name: str,
    service: ThesisReviewService,
    settings: AppSettings,
    case_dir: Path,
    *,
    draft_id: str,
    data: bytes,
    review_fn,
) -> CaseScore:
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = review_fn(
            service,
            teacher_id=TEACHER_ID,
            student_id=STUDENT_ID,
            draft_id=draft_id,
            data=data,
            output_dir=case_dir,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 - eval fail-closed
        code = getattr(exc, "code", "") or type(exc).__name__
        return score_case(name, [], {"ops": []}, error=str(code or exc)[:200])
    findings = [item.to_dict() for item in result.findings]
    trace = _load_trace(case_dir / f"{draft_id}-trace.json")
    return score_case(name, findings, trace)


def _load_trace(path: Path) -> dict:
    if not path.is_file():
        return {"ops": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"ops": []}
    if isinstance(payload, dict):
        return payload
    return {"ops": []}


def _resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value))
    if path.is_file():
        return path
    return base / path


def _public_score(score: CaseScore) -> dict:
    return {
        "case": score.case,
        "passed": score.passed,
        "reasons": score.reasons,
        "tool_ops": score.tool_ops,
        "n_findings": score.n_findings,
        "sources": score.sources,
        "error": score.error,
    }
