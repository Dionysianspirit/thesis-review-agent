"""Existing SQLite files gain the V0.3 columns without losing rows."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from thesis_review.history.store import HistoryStore


def test_store_migrates_pre_v03_schema(tmp_path: Path):
    path = tmp_path / "history.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE issues (
            id TEXT PRIMARY KEY,
            teacher_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            major TEXT NOT NULL DEFAULT '',
            source_draft_id TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            original_kind TEXT NOT NULL,
            original_text TEXT NOT NULL,
            original_span TEXT NOT NULL DEFAULT '',
            original_context TEXT NOT NULL DEFAULT '',
            original_anchor TEXT NOT NULL DEFAULT '',
            suggested_fix TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            confirmed_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        INSERT INTO issues (
            id, teacher_id, student_id, major, source_draft_id, category, status,
            original_kind, original_text, original_span, original_context, original_anchor,
            suggested_fix, created_at, confirmed_at
        ) VALUES (
            'old-1', 'teacher-a', 'zhou', '人工智能', 'v1', 'A', 'confirmed',
            'comment', '避免主观评价', '本研究非常非常有效。', '本研究非常非常有效。', 'P3',
            '', '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
        )
        """
    )
    conn.commit()
    conn.close()

    record = HistoryStore(path).get("old-1")
    assert record.original_text == "避免主观评价"
    assert record.issue_type == ""
    assert record.problem == ""
    assert record.scope == ""
    assert record.teacher_intent == ""
