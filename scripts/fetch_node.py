"""Download a portable Node runtime for the teacher package."""
from __future__ import annotations

import io
import os
import shutil
import stat
import zipfile
from pathlib import Path
import urllib.request

VERSION = "22.20.0"
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".vendor" / "node"


def _url() -> str:
    if os.name == "nt":
        return f"https://nodejs.org/dist/v{VERSION}/node-v{VERSION}-win-x64.zip"
    raise SystemExit("This fetch script currently targets Windows packages.")


def main() -> None:
    marker = TARGET / ".node-version"
    exe = TARGET / "node.exe"
    if exe.is_file() and marker.is_file() and marker.read_text(encoding="ascii").strip() == VERSION:
        print(f"Already present: Node {VERSION}")
        return
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True, exist_ok=True)
    url = _url()
    request = urllib.request.Request(url, headers={"User-Agent": "thesis-review-agent-node"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            archive_bytes = response.read()
    except OSError:
        found = shutil.which("node")
        if not found:
            raise
        shutil.copy2(found, exe)
        marker.write_text(VERSION + "\n", encoding="ascii")
        print(f"Copied local Node from {found}")
        return
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = archive.namelist()
        root_name = names[0].split("/")[0]
        for item in archive.infolist():
            relative = Path(*Path(item.filename).parts[1:]) if Path(item.filename).parts[0] == root_name else Path(item.filename)
            dest = TARGET / relative
            if item.is_dir() or item.filename.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(item))
    if not exe.is_file():
        raise SystemExit("node.exe missing after extract")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    marker.write_text(VERSION + "\n", encoding="ascii")
    print(f"Downloaded Node {VERSION}")


if __name__ == "__main__":
    main()
