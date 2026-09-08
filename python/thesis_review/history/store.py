from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from thesis_review.types import IssueRecord

_COLUMNS = (
    "id, teacher_id, student_id, major, source_draft_id, category, status, "
    "original_kind, original_text, original_span, original_context, original_anchor, "
    "suggested_fix, created_at, confirmed_at"
)


class HistoryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
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
                created_at TEXT NOT NULL,
                confirmed_at TEXT NOT NULL DEFAULT '',
                UNIQUE(teacher_id, student_id, source_draft_id, original_anchor, original_text)
            )
            """
        )
        self._conn.commit()

    def add(self, record: IssueRecord) -> IssueRecord:
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
            return self.get(existing[0])
        conn.execute(
            f"INSERT INTO issues ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                record.created_at,
                record.confirmed_at,
            ),
        )
        conn.commit()
        return record

    def get(self, issue_id: str) -> IssueRecord:
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
        rows = self._connect().execute(
            "SELECT DISTINCT student_id FROM issues WHERE teacher_id=? ORDER BY student_id",
            (teacher_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return self._conn


def new_issue_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_record(row: tuple) -> IssueRecord:
    return IssueRecord(
        id=row[0],
        teacher_id=row[1],
        student_id=row[2],
        major=row[3],
        source_draft_id=row[4],
        category=row[5],
        status=row[6],
        original_kind=row[7],
        original_text=row[8],
        original_span=row[9],
        original_context=row[10],
        original_anchor=row[11],
        suggested_fix=row[12],
        created_at=row[13],
        confirmed_at=row[14],
    )
