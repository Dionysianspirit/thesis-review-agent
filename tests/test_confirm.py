"""String recall stays deterministic; Python no longer httpx-confirms history hits."""
from __future__ import annotations

from pathlib import Path

from tests.helpers import sample_history_v1, sample_new_draft, sample_same_heading_fixed_body
from thesis_review.history.confirm import keep_confirmed_hit
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter

ROOT = Path(__file__).resolve().parents[1]


def test_keep_rejects_when_model_says_different_issue():
    paragraph = "3.1 实验设计"
    raw = {
        "same_issue": False,
        "confidence": 0.92,
        "quote": paragraph,
        "rationale": "标题未改，内容问题已不在此段。",
    }
    assert keep_confirmed_hit(raw, paragraph) is False


def test_keep_accepts_high_confidence_quote_in_paragraph():
    paragraph = "本研究非常非常有效。"
    raw = {
        "same_issue": True,
        "confidence": 0.86,
        "quote": "本研究非常非常有效。",
        "rationale": "仍是无依据的主观评价。",
    }
    assert keep_confirmed_hit(raw, paragraph) is True


def test_keep_rejects_low_confidence():
    paragraph = "本研究非常非常有效。"
    raw = {
        "same_issue": True,
        "confidence": 0.4,
        "quote": paragraph,
        "rationale": "不确定。",
    }
    assert keep_confirmed_hit(raw, paragraph) is False


def test_keep_rejects_quote_missing_from_paragraph():
    paragraph = "3.1 实验设计"
    raw = {
        "same_issue": True,
        "confidence": 0.9,
        "quote": "本节仍缺少评价指标。",
        "rationale": "模型编造了原文。",
    }
    assert keep_confirmed_hit(raw, paragraph) is False


def test_offline_review_still_writes_history_without_a_key(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    subjective = next(item for item in candidates if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    sources = {item.source for item in result.findings}
    assert "history" in sources
    assert "model" not in sources


def test_string_recall_still_hits_unchanged_heading(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_same_heading_fixed_body(history=True),
    )
    heading = next(item for item in candidates if "实验步骤" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=heading.id)
    hits = service.search_history(
        teacher_id="teacher-a",
        student_id="zhou",
        data=sample_same_heading_fixed_body(history=False),
    )
    assert hits, "V0.2 string recall should still hit the unchanged heading"


def test_pi_review_path_does_not_call_python_httpx_confirm():
    worker = (ROOT / "python" / "thesis_review" / "worker.py").read_text(encoding="utf-8")
    service = (ROOT / "python" / "thesis_review" / "service.py").read_text(encoding="utf-8")
    llm = (ROOT / "python" / "thesis_review" / "llm.py").read_text(encoding="utf-8")
    confirm = (ROOT / "python" / "thesis_review" / "history" / "confirm.py").read_text(
        encoding="utf-8"
    )
    agent = (ROOT / "agent" / "review.mjs").read_text(encoding="utf-8")
    assert "confirm_history_hit" not in worker
    assert "confirm_history_hit" not in service
    assert "suggest_language_findings" not in worker
    assert "suggest_language_findings" not in service
    assert "suggest_language_findings" not in llm
    assert "httpx" not in confirm
    assert "httpx" not in llm
    assert "confirm_history_hit" not in agent
    assert "get_history_candidates" in agent
    assert "confirm_history_finding" in agent
