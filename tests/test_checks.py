"""Deterministic format and language checks on the fixture draft."""
from __future__ import annotations

from tests.helpers import sample_new_draft
from thesis_review.checks.format import check_format
from thesis_review.checks.language import check_language
from thesis_review.word.adapter import WordAdapter


def test_language_check_flags_padded_adverbs():
    adapter = WordAdapter()
    opened = adapter.open_bytes(sample_new_draft())
    findings = check_language(adapter.list_paragraphs(opened))
    assert any(item.quote == "非常非常" or "非常非常" in item.quote for item in findings)
    assert all(item.source == "rule" for item in findings)
    assert all(item.category == "A" for item in findings)


def test_format_check_flags_missing_caption_and_skipped_reference():
    adapter = WordAdapter()
    opened = adapter.open_bytes(sample_new_draft())
    findings = check_format(adapter.list_paragraphs(opened), adapter.list_tables(opened))
    kinds = {item.code for item in findings}
    assert "missing_table_caption" in kinds
    assert "reference_number_gap" in kinds
    assert all(item.source == "rule" for item in findings)
    assert all(item.category == "C" for item in findings)
