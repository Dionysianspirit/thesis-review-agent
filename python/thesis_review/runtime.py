from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from thesis_review.applog import log_dir, redact, write_error, write_run
from thesis_review.errors import ReviewError
from thesis_review.paths import repo_root


def vendor_node() -> Path:
    root = repo_root()
    if os.name == "nt":
        return root / ".vendor" / "node" / "node.exe"
    return root / ".vendor" / "node" / "bin" / "node"


def bundled_node() -> Path:
    root = repo_root()
    if os.name == "nt":
        return root / "runtime" / "node" / "node.exe"
    return root / "runtime" / "node" / "bin" / "node"


def resolve_node() -> Path:
    override = os.environ.get("THESIS_NODE_PATH")
    if override:
        path = Path(override)
        if path.is_file():
            return path.resolve()
        raise ReviewError("node_missing", f"THESIS_NODE_PATH 不是有效文件：{override}")
    for candidate in (bundled_node(), vendor_node()):
        if candidate.is_file():
            return candidate.resolve()
    found = shutil.which("node")
    if found:
        return Path(found).resolve()
    raise ReviewError("node_missing", "未找到 Node。请运行 scripts/fetch_node.py 或重新打包。")


def agent_dir() -> Path:
    bundled = repo_root() / "agent"
    if (bundled / "review.mjs").is_file():
        return bundled
    return repo_root() / "agent"


def agent_entry() -> Path:
    return agent_dir() / "review.mjs"


def python_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
    return str(repo_root() / "python")


def _default_worker_args(payload: dict) -> list[str]:
    extra = []
    if payload.get("session_id"):
        extra = ["--session", str(payload["session_id"])]
    if getattr(sys, "frozen", False):
        return [
            "worker",
            "--home",
            payload["home"],
            "--teacher",
            payload["teacher_id"],
            "--student",
            payload["student_id"],
            "--major",
            payload.get("major") or "人工智能",
            *extra,
        ]
    return [
        "-m",
        "thesis_review.worker",
        "--home",
        payload["home"],
        "--teacher",
        payload["teacher_id"],
        "--student",
        payload["student_id"],
        "--major",
        payload.get("major") or "人工智能",
        *extra,
    ]


def _with_session_arg(args: list[str], session_id: str) -> list[str]:
    if not session_id or "--session" in args:
        return list(args)
    return list(args) + ["--session", str(session_id)]


def _with_draft_args(args: list[str], payload: dict) -> list[str]:
    """Pass the true draft identity out-of-band so the worker never has to
    trust the model's transcription of paths (which normalizes characters)."""
    if "--draft-path" in args:
        return list(args)
    extra: list[str] = []
    if payload.get("draft_id"):
        extra += ["--draft-id", str(payload["draft_id"])]
    if payload.get("draft_path"):
        extra += ["--draft-path", str(payload["draft_path"])]
    if payload.get("output_dir"):
        extra += ["--output-dir", str(payload["output_dir"])]
    return list(args) + extra


def _with_live_arg(args: list[str], output_dir: str) -> list[str]:
    if "--live" in args:
        return list(args)
    return list(args) + ["--live", str(Path(output_dir) / "live")]


def run_agent_selftest() -> subprocess.CompletedProcess[str]:
    node = resolve_node()
    script = agent_entry()
    env = os.environ.copy()
    env["THESIS_REVIEW_ROOT"] = str(repo_root())
    return subprocess.run(
        [str(node), str(script), "--selftest"],
        cwd=str(agent_dir()),
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def redact_pi_request(request: dict) -> dict:
    payload = dict(request)
    payload.pop("api_key", None)
    return payload


def run_pi_review(request: dict, *, faux: bool = False, timeout: int = 180) -> dict:
    node = resolve_node()
    script = agent_entry()
    payload = dict(request)
    payload.setdefault("python", sys.executable)
    payload.setdefault("pythonpath", python_path())
    if "worker_args" not in payload:
        payload["worker_args"] = _default_worker_args(payload)
    payload["worker_args"] = _with_live_arg(payload["worker_args"], payload["output_dir"])
    payload["worker_args"] = _with_session_arg(payload["worker_args"], payload.get("session_id") or "")
    payload["worker_args"] = _with_draft_args(payload["worker_args"], payload)
    request_path = Path(payload["output_dir"]) / "pi-request.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(redact_pi_request(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stale_portfile = Path(payload["output_dir"]) / "worker.port"
    stale_portfile.unlink(missing_ok=True)
    command = [str(node), str(script), "--request", str(request_path)]
    if faux:
        command.append("--faux")
    env = os.environ.copy()
    env["THESIS_REVIEW_ROOT"] = str(repo_root())
    env["PYTHONPATH"] = python_path()
    env["PYTHONIOENCODING"] = "utf-8"
    home = Path(payload.get("home") or Path.cwd())
    logs = log_dir(home)
    env["THESIS_LOG_DIR"] = str(logs)
    if request.get("api_key"):
        env["THESIS_API_KEY"] = str(request["api_key"])
        env["OPENAI_API_KEY"] = str(request["api_key"])
    if request.get("base_url"):
        env["THESIS_BASE_URL"] = str(request["base_url"])
    write_run(
        home,
        "pi start",
        node=str(node),
        script=str(script),
        timeout=timeout,
        faux=faux,
        session=str(payload.get("session_id") or ""),
        draft=str(payload.get("draft_id") or ""),
    )
    try:
        result = subprocess.run(
            command,
            cwd=str(agent_dir()),
            env=env,
            capture_output=True,
            # The agent prints UTF-8 (PYTHONIOENCODING=utf-8 below); without an
            # explicit encoding Windows decodes with the ANSI code page, and a
            # GBK-invalid byte kills the reader thread, yielding stdout=None.
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        write_error(
            home,
            f"pi_timeout after {timeout}s",
            exc=exc,
            cmd=redact(" ".join(command)),
            session=str(payload.get("session_id") or ""),
        )
        raise ReviewError("pi_timeout", "模型初审超过等待时间，已停止。") from exc
    if result.returncode != 0:
        stderr = redact((result.stderr or result.stdout or "pi 进程失败").strip())[:4000]
        write_error(
            home,
            f"pi_failed exit={result.returncode}",
            cmd=redact(" ".join(command)),
            stderr=stderr,
            session=str(payload.get("session_id") or ""),
        )
        raise ReviewError("pi_failed", stderr or "pi 进程失败")
    write_run(home, "pi done", session=str(payload.get("session_id") or ""))
    stdout = (result.stdout or "").strip()
    if not stdout:
        raise ReviewError("pi_failed", "初审进程没有返回结果。")
    return json.loads(stdout.splitlines()[-1])
