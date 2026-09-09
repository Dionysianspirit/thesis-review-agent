"""Shared PyInstaller freeze for the teacher workstation entry (gui/app.py).

Windows teachers run this via scripts/build_windows.ps1. Linux CI/smoke uses
scripts/smoke_packaged_demo.py. Both must collect python-docx templates on disk
and stdlib modules DocxEngine imports at runtime (xml.etree, zipfile, ...).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_NAME = "ThesisReviewAgent"
SEP = ";" if os.name == "nt" else ":"

HIDDEN_IMPORTS = [
    "thesis_review",
    "thesis_review.gui.app",
    "thesis_review.demo",
    "docx",
    "docxengine",
    "xml.etree",
    "xml.etree.ElementTree",
    "xml.parsers.expat",
    "zipfile",
    "unicodedata",
]


def _python() -> str:
    return sys.executable


def _add_data(src: str, dest: str) -> str:
    return f"{src}{SEP}{dest}"


def pyinstaller_command() -> list[str]:
    gui_data = _add_data(str(ROOT / "python" / "thesis_review" / "gui"), "thesis_review/gui")
    engine_data = _add_data(str(ROOT / ".vendor" / "docxengine" / "src"), "docxengine")
    command = [
        _python(),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        DIST_NAME,
        "--paths",
        str(ROOT / "python"),
        "--paths",
        str(ROOT / ".vendor" / "docxengine" / "src"),
        "--add-data",
        gui_data,
        "--add-data",
        engine_data,
    ]
    for name in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", name])
    command.extend(
        [
            "--collect-submodules",
            "thesis_review",
            "--collect-submodules",
            "docxengine",
            "--collect-all",
            "docx",
        ]
    )
    if os.name == "nt":
        command.insert(command.index("--onedir") + 1, "--windowed")
        command.extend(["--collect-all", "webview"])
    else:
        # Linux smoke only needs the demo/worker argv path; skip GTK/WebKit.
        command.extend(["--exclude-module", "webview", "--exclude-module", "gi"])
    command.append(str(ROOT / "python" / "thesis_review" / "gui" / "app.py"))
    return command


def ensure_docx_layout(out_dir: Path) -> None:
    """python-docx resolves templates via parts/../templates; parts must exist on disk."""
    for root in (out_dir / "_internal" / "docx", out_dir / "docx"):
        templates = root / "templates" / "default-comments.xml"
        if templates.is_file():
            (root / "parts").mkdir(parents=True, exist_ok=True)


def build() -> Path:
    out_dir = ROOT / "dist" / DIST_NAME
    if out_dir.exists():
        shutil.rmtree(out_dir)
    subprocess.run(pyinstaller_command(), cwd=str(ROOT), check=True)
    ensure_docx_layout(out_dir)
    return out_dir


def main() -> int:
    out_dir = build()
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
