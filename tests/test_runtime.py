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
