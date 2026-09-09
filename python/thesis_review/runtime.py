from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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
        text=True,
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
    if request.get("api_key"):
        env["THESIS_API_KEY"] = str(request["api_key"])
        env["OPENAI_API_KEY"] = str(request["api_key"])
    if request.get("base_url"):
        env["THESIS_BASE_URL"] = str(request["base_url"])
    try:
        result = subprocess.run(
            command,
            cwd=str(agent_dir()),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReviewError("pi_timeout", "模型初审超过等待时间，已停止。") from exc
    if result.returncode != 0:
        raise ReviewError("pi_failed", result.stderr.strip() or result.stdout.strip() or "pi 进程失败")
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    return payload
