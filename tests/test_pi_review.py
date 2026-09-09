from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import (
    OVERCLAIM_CLAIM_QUOTE,
    OVERCLAIM_EVIDENCE_QUOTE,
    sample_history_v1,
    sample_new_draft,
    sample_overclaim_draft,
    sample_same_heading_fixed_body,
    sample_supported_claim_draft,
)
from thesis_review.history.store import HistoryStore
from thesis_review.service import ThesisReviewService
from thesis_review.word.adapter import WordAdapter


def test_faux_pi_review_writes_history_and_rule_findings(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "thesis-review.sqlite"),
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
        use_pi=True,
        faux=True,
    )
    sources = {item.source for item in result.findings}
    assert "rule" in sources
    assert "history" in sources
    assert "argument" not in sources
    assert result.reviewed_path.is_file()


def test_faux_overclaim_records_argument_finding(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "thesis-review.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="overclaim",
        data=sample_overclaim_draft(),
        output_dir=tmp_path / "out",
        use_pi=True,
        faux=True,
        faux_scenario="overclaim",
    )
    argument = [item for item in result.findings if item.source == "argument"]
    assert argument
    assert all(item.category == "B" for item in argument)
    assert all(item.code == "claim_without_evidence" for item in argument)
    comments = WordAdapter().extract_comments(WordAdapter().open_path(result.reviewed_path))
    blob = "\n".join(item.text for item in comments)
    assert OVERCLAIM_CLAIM_QUOTE not in blob
    assert OVERCLAIM_EVIDENCE_QUOTE not in blob
    trace_path = result.findings_path.with_name("overclaim-trace.json")
    assert trace_path.is_file()
    ops = [item["op"] for item in json.loads(trace_path.read_text(encoding="utf-8"))["ops"]]
    assert "list_outline" in ops
    assert "record_argument_finding" in ops


def test_faux_skips_history_when_heading_unchanged_body_fixed(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "thesis-review.sqlite"),
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
    assert hits, "string recall should still surface the heading"
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="heading",
        data=sample_same_heading_fixed_body(history=False),
        output_dir=tmp_path / "out",
        use_pi=True,
        faux=True,
        faux_scenario="skip_history",
    )
    assert result.reviewed_path.is_file()
    assert all(item.source != "history" for item in result.findings)


def test_faux_supported_claim_abandons_without_argument(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "thesis-review.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="supported",
        data=sample_supported_claim_draft(),
        output_dir=tmp_path / "out",
        use_pi=True,
        faux=True,
        faux_scenario="abandon",
    )
    assert result.reviewed_path.is_file()
    assert all(item.source != "argument" for item in result.findings)
