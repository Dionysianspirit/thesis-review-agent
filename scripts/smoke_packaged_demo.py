"""Build the onedir app and run the teacher-gate demo the Windows packager uses.

Linux cannot produce a .exe; this still freezes the same entry point
(python/thesis_review/gui/app.py) and requires teacher-approved Word comments.

The teacher EXE talks to Pi by spawning itself as ``worker --portfile``.
Windows packaging is ``--windowed``, so stdin worker smoke is Linux-only;
TCP worker smoke is required on both.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pyinstaller_build import DIST_NAME, build  # noqa: E402


def _binary(out_dir: Path) -> Path:
    if os.name == "nt":
        for name in (f"{DIST_NAME}.exe", "论文审改助手.exe"):
            exe = out_dir / name
            if exe.is_file():
                return exe
        raise SystemExit(f"missing packaged exe in {out_dir}")
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


def assert_gui_bundle(out_dir: Path) -> Path:
    roots = [
        out_dir / "_internal" / "thesis_review" / "gui",
        out_dir / "thesis_review" / "gui",
    ]
    gui = next((path for path in roots if (path / "ui.html").is_file()), None)
    if gui is None:
        raise SystemExit(f"packaged GUI ui.html missing under {out_dir}")
    for name in ("ui.js", "ui.css"):
        if not (gui / name).is_file():
            raise SystemExit(f"packaged GUI {name} missing")
    html = (gui / "ui.html").read_text(encoding="utf-8")
    if "开始 AI 初审" not in html or "生成正式审稿稿件" not in html:
        raise SystemExit("packaged GUI is not the teacher workstation")
    return gui


def assert_teacher_gate(payload: dict) -> dict:
    if not payload.get("ok"):
        raise SystemExit(payload.get("error") or "teacher-gate demo failed")
    if int(payload.get("comments_before", 0)) != 0:
        raise SystemExit("teacher gate failed: comments written before teacher decisions")
    if int(payload.get("revisions_before", 0)) != 0:
        raise SystemExit("teacher gate failed: revisions written before teacher decisions")
    if int(payload.get("n_exported") or 0) < 1 or int(payload.get("comments_after") or 0) < 1:
        raise SystemExit("packaged demo did not export teacher-approved Word comments")
    if payload.get("tracked_revisions") and int(payload.get("revisions_after") or 0) < 1:
        raise SystemExit("packaged demo did not export teacher-approved tracked revisions")
    return payload


def smoke(binary: Path, probe: Path, *, faux: bool = True) -> dict:
    if probe.exists():
        shutil.rmtree(probe)
    probe.mkdir(parents=True)
    command = [str(binary), "--home", str(probe), "demo", "--out", str(probe)]
    if faux:
        command.append("--faux")
    run_kwargs: dict = {
        "cwd": str(binary.parent),
        "check": False,
        "text": True,
        "timeout": 240,
    }
    if os.name == "nt":
        # --windowed EXE: avoid stdout pipe deadlock; teacher-gate.json is the result.
        run_kwargs["stdout"] = subprocess.DEVNULL
        run_kwargs["stderr"] = subprocess.PIPE
        run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        run_kwargs["capture_output"] = True
    result = subprocess.run(command, **run_kwargs)
    if result.returncode != 0:
        stdout = "" if os.name == "nt" else (result.stdout or "")
        stderr = result.stderr or ""
        raise SystemExit(f"packaged demo failed ({result.returncode})\n{stdout}\n{stderr}")
    gate_path = probe / "teacher-gate.json"
    if not gate_path.is_file():
        raise SystemExit("packaged demo did not write teacher-gate.json")
    payload = json.loads(gate_path.read_text(encoding="utf-8"))
    if faux and payload.get("agent") != "faux-pi":
        raise SystemExit(f"packaged demo did not use the Pi agent path: {payload.get('agent')}")
    if faux and not payload.get("pi_trace_ok"):
        raise SystemExit("packaged demo missing Pi worker TCP trace")
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


def smoke_worker_tcp_teacher_gate(binary: Path, home: Path) -> None:
    """The packaged GUI/agent path: EXE worker --portfile, then add_comment → teacher_gate."""
    home.mkdir(parents=True, exist_ok=True)
    portfile = home / "worker.port"
    if portfile.exists():
        portfile.unlink()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [
            str(binary),
            "worker",
            "--home",
            str(home),
            "--teacher",
            "teacher-a",
            "--student",
            "zhou",
            "--portfile",
            str(portfile),
        ],
        cwd=str(binary.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            if portfile.is_file():
                text = portfile.read_text(encoding="ascii").strip()
                if text.isdigit():
                    break
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr else ""
                raise SystemExit(f"frozen TCP worker exited before portfile\n{err}")
            time.sleep(0.05)
        else:
            raise SystemExit("frozen TCP worker did not write portfile")
        port = int(portfile.read_text(encoding="ascii").strip())
        with socket.create_connection(("127.0.0.1", port), timeout=8) as sock:
            sock.sendall(
                (
                    json.dumps({"id": 1, "op": "add_comment", "params": {"text": "no"}}, ensure_ascii=False)
                    + "\n"
                ).encode("utf-8")
            )
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if not buf.strip():
            raise SystemExit("frozen TCP worker returned no response")
        line = json.loads(buf.decode("utf-8").strip().splitlines()[-1])
        if (line.get("error") or {}).get("code") != "teacher_gate":
            raise SystemExit(f"frozen TCP worker did not enforce teacher gate: {line}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def smoke_dist(out_dir: Path, probe: Path) -> dict:
    binary = _binary(out_dir)
    assert_gui_bundle(out_dir)
    smoke_pi_selftest(out_dir)
    if os.name != "nt":
        smoke_worker_teacher_gate(binary, probe / "stdin-home")
    smoke_worker_tcp_teacher_gate(binary, probe / "tcp-home")
    payload = smoke(binary, probe / "demo", faux=True)
    return {"binary": str(binary), **payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist",
        type=Path,
        default=None,
        help="Existing onedir folder (skip freeze). Windows packager passes the renamed 论文审改助手 folder.",
    )
    args = parser.parse_args(argv)
    if args.dist is not None:
        out_dir = args.dist
        if not out_dir.is_dir():
            raise SystemExit(f"missing dist folder: {out_dir}")
    else:
        out_dir = build()
        _bundle_runtime(out_dir)
    payload = smoke_dist(out_dir, ROOT / "artifacts" / "packaged-demo")
    print(
        json.dumps(
            {
                "binary": payload["binary"],
                **{
                    key: payload[key]
                    for key in (
                        "ok",
                        "candidates",
                        "comments_before",
                        "comments_after",
                        "n_exported",
                        "revisions_before",
                        "revisions_after",
                        "agent",
                        "pi_trace_ok",
                    )
                    if key in payload
                },
                "worker_teacher_gate": os.name != "nt",
                "worker_tcp_teacher_gate": True,
                "pi_selftest": True,
                "gui_bundle": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
