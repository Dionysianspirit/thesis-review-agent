from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from thesis_review.types import IssueRecord

_COLUMNS = (
    "id, teacher_id, student_id, major, source_draft_id, category, status, "
    "original_kind, original_text, original_span, original_context, original_anchor, "
    "suggested_fix, issue_type, problem, scope, teacher_intent, created_at, confirmed_at"
)
_PLACEHOLDERS = ",".join("?" * 19)
_NEW_COLUMNS = (
    ("issue_type", "TEXT NOT NULL DEFAULT ''"),
    ("problem", "TEXT NOT NULL DEFAULT ''"),
    ("scope", "TEXT NOT NULL DEFAULT ''"),
    ("teacher_intent", "TEXT NOT NULL DEFAULT ''"),
)


class HistoryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issues (
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
                    issue_type TEXT NOT NULL DEFAULT '',
                    problem TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT '',
                    teacher_intent TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL DEFAULT '',
                    UNIQUE(teacher_id, student_id, source_draft_id, original_anchor, original_text)
                )
                """
            )
            self._migrate()
            self._conn.commit()

    def add(self, record: IssueRecord) -> IssueRecord:
        with self._lock:
            conn = self._connect()
            existing = conn.execute(
                """
                SELECT id FROM issues
                WHERE teacher_id=? AND student_id=? AND source_draft_id=?
                  AND original_anchor=? AND original_text=?
                """,
                (
                    record.teacher_id,
                    record.student_id,
                    record.source_draft_id,
                    record.original_anchor,
                    record.original_text,
                ),
            ).fetchone()
            if existing:
                return self.get(existing["id"])
            conn.execute(
                f"INSERT INTO issues ({_COLUMNS}) VALUES ({_PLACEHOLDERS})",
                (
                    record.id,
                    record.teacher_id,
                    record.student_id,
                    record.major,
                    record.source_draft_id,
                    record.category,
                    record.status,
                    record.original_kind,
                    record.original_text,
                    record.original_span,
                    record.original_context,
                    record.original_anchor,
                    record.suggested_fix,
                    record.issue_type,
                    record.problem,
                    record.scope,
                    record.teacher_intent,
                    record.created_at,
                    record.confirmed_at,
                ),
            )
            conn.commit()
            return record

    def get(self, issue_id: str) -> IssueRecord:
        with self._lock:
            row = self._connect().execute(
                f"SELECT {_COLUMNS} FROM issues WHERE id=?", (issue_id,)
            ).fetchone()
            if row is None:
                raise KeyError(issue_id)
            return _row_to_record(row)

    def list_issues(
        self,
        *,
        teacher_id: str,
        student_id: str,
        status: str | None = None,
    ) -> list[IssueRecord]:
        sql = f"SELECT {_COLUMNS} FROM issues WHERE teacher_id=? AND student_id=?"
        params: list[object] = [teacher_id, student_id]
        if status is not None:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at"
        with self._lock:
            rows = self._connect().execute(sql, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def set_status(
        self,
        *,
        teacher_id: str,
        student_id: str,
        issue_id: str,
        status: str,
    ) -> IssueRecord:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM issues WHERE id=? AND teacher_id=? AND student_id=?",
                (issue_id, teacher_id, student_id),
            ).fetchone()
            if row is None:
                raise KeyError(issue_id)
            confirmed_at = _now() if status == "confirmed" else ""
            conn.execute(
                "UPDATE issues SET status=?, confirmed_at=? WHERE id=?",
                (status, confirmed_at, issue_id),
            )
            conn.commit()
            return self.get(issue_id)

    def list_students(self, teacher_id: str) -> list[str]:
        with self._lock:
            rows = self._connect().execute(
                "SELECT DISTINCT student_id FROM issues WHERE teacher_id=? ORDER BY student_id",
                (teacher_id,),
            ).fetchall()
        return [row["student_id"] for row in rows]

    def _migrate(self) -> None:
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(issues)")}
        for name, spec in _NEW_COLUMNS:
            if name not in existing:
                self._conn.execute(f"ALTER TABLE issues ADD COLUMN {name} {spec}")

    def _connect(self) -> sqlite3.Connection:
        return self._conn


def new_issue_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_record(row: sqlite3.Row) -> IssueRecord:
    return IssueRecord(
        id=row["id"],
        teacher_id=row["teacher_id"],
        student_id=row["student_id"],
        major=row["major"],
        source_draft_id=row["source_draft_id"],
        category=row["category"],
        status=row["status"],
        original_kind=row["original_kind"],
        original_text=row["original_text"],
        original_span=row["original_span"],
        original_context=row["original_context"],
        original_anchor=row["original_anchor"],
        suggested_fix=_cell(row, "suggested_fix"),
        issue_type=_cell(row, "issue_type"),
        problem=_cell(row, "problem"),
        scope=_cell(row, "scope"),
        teacher_intent=_cell(row, "teacher_intent"),
        created_at=row["created_at"],
        confirmed_at=_cell(row, "confirmed_at"),
    )


def _cell(row: sqlite3.Row, name: str, default: str = "") -> str:
    if name not in row.keys():
        return default
    value = row[name]
    return default if value is None else str(value)
