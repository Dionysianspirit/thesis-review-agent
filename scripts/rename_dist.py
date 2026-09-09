"""Rename the onedir package to a proper Chinese folder and exe name."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ASCII_NAME = "ThesisReviewAgent"
PRODUCT_NAME = "论文审改助手"


def _print_path(path: Path) -> None:
    text = str(path)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main() -> None:
    DIST.mkdir(exist_ok=True)
    src = DIST / ASCII_NAME
    dst = DIST / PRODUCT_NAME
    if not src.is_dir():
        raise SystemExit(f"Missing ASCII build directory: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    src.rename(dst)
    exe = dst / f"{ASCII_NAME}.exe"
    product_exe = dst / f"{PRODUCT_NAME}.exe"
    if exe.is_file():
        if product_exe.exists():
            product_exe.unlink()
        exe.rename(product_exe)
    for child in DIST.iterdir():
        if child.is_dir() and child.name not in {ASCII_NAME, PRODUCT_NAME}:
            shutil.rmtree(child)
        elif child.is_file() and child.suffix == ".exe" and child.stem not in {ASCII_NAME, PRODUCT_NAME}:
            child.unlink()
    if not product_exe.is_file():
        raise SystemExit(f"Missing product exe: {product_exe}")
    _print_path(product_exe)


if __name__ == "__main__":
    main()
