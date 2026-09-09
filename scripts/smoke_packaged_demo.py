"""Build the onedir app and run the teacher-gate demo the Windows packager uses.

Linux cannot produce a .exe; this still freezes the same entry point
(python/thesis_review/gui/app.py) and requires teacher-approved Word comments.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pyinstaller_build import DIST_NAME, build  # noqa: E402


def _binary(out_dir: Path) -> Path:
    if os.name == "nt":
        exe = out_dir / f"{DIST_NAME}.exe"
        if exe.is_file():
            return exe
        raise SystemExit(f"missing {exe}")
    for name in (DIST_NAME, DIST_NAME.lower()):
        candidate = out_dir / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit(f"missing packaged binary in {out_dir}")


def _bundle_runtime(out_dir: Path) -> None:
    agent_src = ROOT / "agent"
    agent_out = out_dir / "agent"
    if agent_out.exists():
        shutil.rmtree(agent_out)
    shutil.copytree(agent_src, agent_out, ignore=shutil.ignore_patterns("node_modules", ".git"))
    node_modules = agent_src / "node_modules"
    if node_modules.is_dir():
        shutil.copytree(node_modules, agent_out / "node_modules")
    runtime = out_dir / "runtime" / "node"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    if os.name == "nt":
        vendor = ROOT / ".vendor" / "node"
        if vendor.is_dir():
            shutil.copytree(vendor, runtime, dirs_exist_ok=True)
        return
    runtime_bin = runtime / "bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    node = shutil.which("node")
    if not node:
        raise SystemExit("node is required to bundle the packaged runtime")
    dest = runtime_bin / "node"
    shutil.copy2(node, dest)
    dest.chmod(dest.stat().st_mode | 0o111)


def assert_teacher_gate(payload: dict) -> dict:
    if not payload.get("ok"):
        raise SystemExit(payload.get("error") or "teacher-gate demo failed")
    if int(payload.get("comments_before", 0)) != 0:
        raise SystemExit("teacher gate failed: comments written before teacher decisions")
    if int(payload.get("n_exported") or 0) < 1 or int(payload.get("comments_after") or 0) < 1:
        raise SystemExit("packaged demo did not export teacher-approved Word comments")
    return payload


def smoke(binary: Path, probe: Path) -> dict:
    if probe.exists():
        shutil.rmtree(probe)
    probe.mkdir(parents=True)
    result = subprocess.run(
        [str(binary), "--home", str(probe), "demo", "--out", str(probe)],
        cwd=str(binary.parent),
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"packaged demo failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
        )
    gate_path = probe / "teacher-gate.json"
    if not gate_path.is_file():
        raise SystemExit("packaged demo did not write teacher-gate.json")
    payload = json.loads(gate_path.read_text(encoding="utf-8"))
    return assert_teacher_gate(payload)


def smoke_pi_selftest(out_dir: Path) -> None:
    if os.name == "nt":
        node = out_dir / "runtime" / "node" / "node.exe"
    else:
        node = out_dir / "runtime" / "node" / "bin" / "node"
    script = out_dir / "agent" / "review.mjs"
    if not node.is_file() or not script.is_file():
        raise SystemExit(f"missing bundled pi runtime: {node} {script}")
    result = subprocess.run(
        [str(node), str(script), "--selftest"],
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or "pi-ok" not in (result.stdout or ""):
        raise SystemExit(f"bundled pi selftest failed\n{result.stdout}\n{result.stderr}")


def smoke_worker_teacher_gate(binary: Path, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(binary), "worker", "--home", str(home), "--teacher", "teacher-a", "--student", "zhou"],
        input=json.dumps({"id": 1, "op": "add_comment", "params": {"text": "no"}}, ensure_ascii=False) + "\n",
        cwd=str(binary.parent),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"frozen worker failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
        )
    line = json.loads((result.stdout or "").strip().splitlines()[-1])
    if (line.get("error") or {}).get("code") != "teacher_gate":
        raise SystemExit(f"frozen worker did not enforce teacher gate: {line}")


def main() -> int:
    out_dir = build()
    _bundle_runtime(out_dir)
    binary = _binary(out_dir)
    smoke_pi_selftest(out_dir)
    payload = smoke(binary, ROOT / "artifacts" / "packaged-demo")
    smoke_worker_teacher_gate(binary, ROOT / "artifacts" / "packaged-demo")
    print(
        json.dumps(
            {
                "binary": str(binary),
                **{
                    k: payload[k]
                    for k in ("ok", "candidates", "comments_before", "comments_after", "n_exported")
                },
                "worker_teacher_gate": True,
                "pi_selftest": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
