from __future__ import annotations

from thesis_review.evalscore import score_case


def _trace(*ops: str) -> dict:
    return {"ops": [{"op": name, "ok": True, "params": {}} for name in ops]}


def test_overclaim_passes_when_argument_follows_navigation():
    findings = [{"source": "argument", "category": "B"}]
    trace = _trace(
        "open_draft",
        "list_outline",
        "read_section",
        "record_argument_finding",
        "commit_review",
    )
    result = score_case("overclaim", findings, trace)
    assert result.passed is True
    assert result.reasons == []
    assert result.tool_ops[:3] == ["open_draft", "list_outline", "read_section"]


def test_overclaim_fails_without_navigation_before_record():
    findings = [{"source": "argument", "category": "B"}]
    trace = _trace("open_draft", "record_argument_finding", "commit_review")
    result = score_case("overclaim", findings, trace)
    assert result.passed is False
    assert any("导航" in reason for reason in result.reasons)


def test_overclaim_fails_when_argument_missing():
    findings = [{"source": "rule", "category": "C"}]
    trace = _trace("open_draft", "list_outline", "read_section", "commit_review")
    result = score_case("overclaim", findings, trace)
    assert result.passed is False
    assert any("论证" in reason or "argument" in reason for reason in result.reasons)


def test_abandon_fails_when_argument_is_recorded():
    findings = [{"source": "argument", "category": "B"}]
    trace = _trace("open_draft", "list_outline", "find_text", "record_argument_finding", "commit_review")
    result = score_case("abandon", findings, trace)
    assert result.passed is False
    assert any("误批" in reason or "argument" in reason for reason in result.reasons)


def test_abandon_passes_with_navigation_and_no_argument():
    findings = [{"source": "rule", "category": "A"}]
    trace = _trace("open_draft", "list_outline", "read_paragraphs", "commit_review")
    result = score_case("abandon", findings, trace)
    assert result.passed is True


def test_history_requires_history_finding():
    trace = _trace("open_draft", "get_history_candidates", "confirm_history_finding", "commit_review")
    missing = score_case("history", [{"source": "rule"}], trace)
    assert missing.passed is False
    kept = score_case("history", [{"source": "history"}], trace)
    assert kept.passed is True


def test_error_case_fails_closed():
    result = score_case("overclaim", [], {"ops": []}, error="pi_failed")
    assert result.passed is False
    assert "pi_failed" in result.error
    assert result.reasons
