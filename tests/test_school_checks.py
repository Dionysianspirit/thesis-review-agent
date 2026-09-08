"""大连财经学院 2026 届格式标准中可自动检查的条款。"""
from __future__ import annotations

from tests.helpers import sample_new_draft
from thesis_review.checks.format import check_format
from thesis_review.word.adapter import WordAdapter


def test_school_rules_flag_missing_sections_and_thin_references():
    adapter = WordAdapter()
    opened = adapter.open_bytes(sample_new_draft())
    findings = check_format(adapter.list_paragraphs(opened), adapter.list_tables(opened))
    codes = {item.code for item in findings}
    assert "missing_required_section" in codes
    assert "references_too_few" in codes
    assert "reference_missing_type_marker" in codes
    assert any("大连财经学院" in item.rationale for item in findings)
