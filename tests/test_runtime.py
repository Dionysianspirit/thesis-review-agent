from __future__ import annotations

from pathlib import Path

from thesis_review.runtime import agent_entry, resolve_node, run_agent_selftest


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
