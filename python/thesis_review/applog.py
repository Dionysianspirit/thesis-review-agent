"""File logs for diagnosis. Never write API keys or draft quotes."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

MAX_BYTES = 2_000_000
RUN_LOG = "run.log"
OPS_LOG = "ops.log"
ERROR_LOG = "error.log"

_LOCK = threading.Lock()
_SECRET_LINE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|THESIS_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY)"
    r"([\"']?\s*[=:]\s*[\"']?)([^\s\"']+)"
)
_SK = re.compile(r"sk-[A-Za-z0-9_-]{6,}")
_DROP_KEYS = frozenset(
    {
        "api_key",
        "quote",
        "claim_quote",
        "evidence_quote",
        "new_quote",
        "original_text",
        "needle",
        "bytes_b64",
        "text",
        "snippet",
    }
)


def log_dir(home: Path) -> Path:
    override = os.environ.get("THESIS_LOG_DIR")
    if override:
        path = Path(override)
    else:
        path = Path(home) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def redact(text: str) -> str:
    if not text:
        return ""
    cleaned = _SECRET_LINE.sub(r"\1\2***", text)
    return _SK.sub("sk-***", cleaned)


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _rotate(path: Path) -> None:
    if path.is_file() and path.stat().st_size >= MAX_BYTES:
        backup = path.with_name(path.name + ".1")
        backup.unlink(missing_ok=True)
        path.replace(backup)


def _append(path: Path, line: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            _rotate(path)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                if not line.endswith("\n"):
                    handle.write("\n")
    except OSError:
        return


def safe_fields(payload: dict | None) -> dict:
    if not payload:
        return {}
    out: dict = {}
    for key, value in payload.items():
        if key in _DROP_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            text = redact(str(value)) if isinstance(value, str) else value
            if isinstance(text, str) and len(text) > 240:
                text = text[:240] + "…"
            out[key] = text
    return out


def write_run(home: Path, message: str, **fields: object) -> None:
    extra = ""
    if fields:
        extra = " " + json.dumps(safe_fields(fields), ensure_ascii=False)
    _append(log_dir(home) / RUN_LOG, f"{_stamp()} [run] {redact(message)}{extra}")


def write_op(home: Path, op: str, *, ok: bool = True, code: str = "", **fields: object) -> None:
    payload = {
        "ts": _stamp(),
        "op": op,
        "ok": bool(ok),
        "code": code or "",
        **safe_fields(fields),
    }
    _append(log_dir(home) / OPS_LOG, json.dumps(payload, ensure_ascii=False))


def write_error(home: Path, message: str, *, exc: BaseException | None = None, **fields: object) -> None:
    lines = [f"{_stamp()} [error] {redact(message)}"]
    if fields:
        lines.append(json.dumps(safe_fields(fields), ensure_ascii=False))
    if exc is not None:
        lines.append(redact(f"{type(exc).__name__}: {exc}"))
        lines.append(redact("".join(traceback.format_exception(exc))))
    _append(log_dir(home) / ERROR_LOG, "\n".join(lines) + "\n")


def setup(home: Path, *, kind: str = "app") -> Path:
    directory = log_dir(home)
    write_run(
        home,
        f"{kind} start",
        pid=os.getpid(),
        frozen=bool(getattr(sys, "frozen", False)),
    )
    return directory
