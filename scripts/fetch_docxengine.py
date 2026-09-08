"""Fetch a pinned public test dependency; never install or execute upstream code."""
from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

COMMIT = 'c4ca7ce5f540ef2e638fbf79cc5f7074702b2967'
URL = f'https://codeload.github.com/ruwadgroup/docxengine/zip/{COMMIT}'
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.vendor/docxengine'


def main() -> None:
    if TARGET.exists():
        marker = TARGET / '.upstream-commit'
        if marker.is_file() and marker.read_text(encoding='ascii').strip() == COMMIT:
            print(f'Already present: DocxEngine {COMMIT}')
            return
        raise SystemExit('Existing vendor directory has no matching commit marker; refusing overwrite.')
    request = urllib.request.Request(URL, headers={'User-Agent': 'thesis-review-agent-probe'})
    with urllib.request.urlopen(request, timeout=45) as response:
        archive_bytes = response.read(10 * 1024 * 1024 + 1)
    if len(archive_bytes) > 10 * 1024 * 1024:
        raise SystemExit('Archive exceeds the expected 10 MiB probe limit.')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='docxengine-', dir=TARGET.parent) as tmp:
        staging = Path(tmp) / 'source'
        staging.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = archive.infolist()
            if sum(item.file_size for item in members) > 50 * 1024 * 1024:
                raise SystemExit('Expanded source exceeds 50 MiB.')
            for item in members:
                parts = PurePosixPath(item.filename).parts
                if not parts or parts[0] != f'docxengine-{COMMIT}':
                    raise SystemExit('Unexpected archive root.')
                if len(parts) == 1:
                    continue
                relative = Path(*parts[1:])
                dest = (staging / relative).resolve()
                if not dest.is_relative_to(staging.resolve()):
                    raise SystemExit('Unsafe archive member.')
                if item.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open('xb') as stream:
                        stream.write(archive.read(item))
        for required in ['LICENSE', 'NOTICE', 'src/docxengine/__init__.py', 'tests/conftest.py']:
            if not (staging / required).is_file():
                raise SystemExit(f'Missing required upstream file: {required}')
        (staging / '.upstream-commit').write_text(COMMIT + '\n', encoding='ascii')
        if TARGET.exists():
            raise SystemExit('Vendor target appeared during download; refusing overwrite.')
        shutil.move(str(staging), str(TARGET))
    print(f'Downloaded DocxEngine {COMMIT}; LICENSE and NOTICE retained.')


if __name__ == '__main__':
    main()
