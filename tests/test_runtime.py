from __future__ import annotations

import json
from pathlib import Path

from thesis_review.runtime import agent_entry, redact_pi_request, resolve_node, run_agent_selftest, run_pi_review


def test_resolve_node_uses_env_override(tmp_path: Path, monkeypatch):
    fake = tmp_path / "node.exe"
    fake.write_bytes(b"MZ")
    monkeypatch.setenv("THESIS_NODE_PATH", str(fake))
    assert resolve_node() == fake.resolve()


def test_agent_entry_points_at_review_script():
    path = agent_entry()
    assert path.name == "review.mjs"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "unlinkSync" in text
    assert "removeIfExists" in text
    assert "connectWorker" in text


def test_bundled_pi_selftest_runs():
    result = run_agent_selftest()
    assert result.returncode == 0
    assert "pi-ok" in result.stdout


def test_redact_pi_request_drops_api_key():
    redacted = redact_pi_request(
        {"home": "/x", "api_key": "sk-secret", "model": "gpt-4o-mini", "base_url": "https://example"}
    )
    assert "api_key" not in redacted
    assert redacted["model"] == "gpt-4o-mini"
    assert "sk-secret" not in json.dumps(redacted)


def test_run_pi_review_adds_live_worker_arg(tmp_path: Path, monkeypatch):
    captured: dict = {}

    class Result:
        returncode = 0
        stdout = json.dumps({"findings_path": str(tmp_path / "out.json")})
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Result()

    monkeypatch.setattr("thesis_review.runtime.subprocess.run", fake_run)
    monkeypatch.setattr("thesis_review.runtime.resolve_node", lambda: Path("node"))
    out = tmp_path / "eval-case"
    run_pi_review(
        {
            "home": str(tmp_path),
            "teacher_id": "teacher-a",
            "student_id": "zhou",
            "output_dir": str(out),
            "api_key": "sk-secret",
        }
    )
    dumped = json.loads((out / "pi-request.json").read_text(encoding="utf-8"))
    args = dumped["worker_args"]
    assert "--live" in args
    assert Path(args[args.index("--live") + 1]) == out / "live"
    assert "api_key" not in dumped
    assert "sk-secret" not in json.dumps(dumped)


def test_run_pi_review_deletes_stale_worker_portfile(tmp_path: Path, monkeypatch):
    class Result:
        returncode = 0
        stdout = json.dumps({"findings_path": str(tmp_path / "out.json")})
        stderr = ""

    monkeypatch.setattr("thesis_review.runtime.subprocess.run", lambda *a, **k: Result())
    monkeypatch.setattr("thesis_review.runtime.resolve_node", lambda: Path("node"))
    out = tmp_path / "eval-case"
    out.mkdir()
    stale = out / "worker.port"
    stale.write_text("62852", encoding="ascii")
    run_pi_review(
        {
            "home": str(tmp_path),
            "teacher_id": "teacher-a",
            "student_id": "zhou",
            "output_dir": str(out),
        }
    )
    assert not stale.exists()


def test_run_pi_review_maps_timeout_to_review_error(tmp_path: Path, monkeypatch):
    import subprocess

    from thesis_review.errors import ReviewError

    def boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["node", "review.mjs"], timeout=180)

    monkeypatch.setattr("thesis_review.runtime.subprocess.run", boom)
    monkeypatch.setattr("thesis_review.runtime.resolve_node", lambda: Path("node"))
    try:
        run_pi_review(
            {
                "home": str(tmp_path),
                "teacher_id": "teacher-a",
                "student_id": "zhou",
                "output_dir": str(tmp_path / "eval-case"),
            }
        )
    except ReviewError as exc:
        assert exc.code == "pi_timeout"
        assert "Command" not in str(exc)
    else:
        raise AssertionError("expected pi_timeout")


def test_run_pi_review_writes_redacted_request_and_honors_timeout(tmp_path: Path, monkeypatch):
    captured: dict = {}

    class Result:
        returncode = 0
        stdout = json.dumps({"findings_path": str(tmp_path / "out.json")})
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["timeout"] = kwargs.get("timeout")
        captured["env"] = kwargs.get("env")
        return Result()

    monkeypatch.setattr("thesis_review.runtime.subprocess.run", fake_run)
    monkeypatch.setattr("thesis_review.runtime.resolve_node", lambda: Path("node"))
    out = tmp_path / "eval-case"
    run_pi_review(
        {
            "home": str(tmp_path),
            "teacher_id": "teacher-a",
            "student_id": "zhou",
            "output_dir": str(out),
            "api_key": "sk-secret",
            "model": "gpt-4o-mini",
            "worker_args": ["-m", "thesis_review.worker"],
        },
        timeout=600,
    )
    request_path = out / "pi-request.json"
    dumped = request_path.read_text(encoding="utf-8")
    assert "sk-secret" not in dumped
    assert "api_key" not in json.loads(dumped)
    assert captured["timeout"] == 600
    assert captured["env"]["THESIS_API_KEY"] == "sk-secret"


def test_frozen_worker_args_use_exe_worker_subcommand(monkeypatch):
    import sys

    from thesis_review.runtime import _default_worker_args

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    args = _default_worker_args(
        {
            "home": "/appdata/home",
            "teacher_id": "teacher-a",
            "student_id": "zhou",
            "major": "人工智能",
            "session_id": "sess-1",
        }
    )
    assert args[0] == "worker"
    assert "-m" not in args
    assert args[args.index("--home") + 1] == "/appdata/home"
    assert "--session" in args
    assert args[args.index("--session") + 1] == "sess-1"


def test_python_path_uses_meipass_when_frozen(monkeypatch, tmp_path: Path):
    import sys

    import thesis_review.runtime as runtime

    mei = tmp_path / "MEI123"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    assert runtime.python_path() == str(mei)


def test_gui_app_worker_tcp_blocks_direct_word_writes(tmp_path: Path):
    import json
    import socket
    import subprocess
    import sys
    import time

    portfile = tmp_path / "worker.port"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "thesis_review.gui.app",
            "worker",
            "--home",
            str(tmp_path),
            "--teacher",
            "teacher-a",
            "--student",
            "zhou",
            "--portfile",
            str(portfile),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            if portfile.is_file() and portfile.read_text(encoding="ascii").strip().isdigit():
                break
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read() if proc.stderr else "worker exited")
            time.sleep(0.05)
        else:
            raise AssertionError("worker did not write portfile")
        port = int(portfile.read_text(encoding="ascii").strip())
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(
                (json.dumps({"id": 1, "op": "add_comment", "params": {"text": "no"}}) + "\n").encode()
            )
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
        line = json.loads(buf.decode().strip().splitlines()[-1])
        assert (line.get("error") or {}).get("code") == "teacher_gate"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
