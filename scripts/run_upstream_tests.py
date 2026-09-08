"""Run only the selected upstream tests and retain their report in artifacts/."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.vendor/docxengine'
TESTS = ['test_comments.py', 'test_revisions.py', 'test_edit.py',
         'test_anchors.py', 'test_validate.py', 'test_adversarial.py']


def main() -> int:
    if not (SOURCE / 'tests/conftest.py').is_file():
        raise SystemExit('Run python scripts/fetch_docxengine.py first.')
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix='upstream-', dir=artifacts))
    env = os.environ.copy()
    paths = [str(SOURCE / 'src')]
    if env.get('PYTHONPATH'):
        paths.append(env['PYTHONPATH'])
    env['PYTHONPATH'] = os.pathsep.join(paths)
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    env['DOCXENGINE_AUTO_FETCH_SOFFICE'] = '0'
    command = [sys.executable, '-m', 'pytest', *[f'tests/{name}' for name in TESTS],
               '-q', '-p', 'no:cacheprovider', f'--basetemp={run_dir / "tmp"}',
               f'--junitxml={run_dir / "junit.xml"}']
    return subprocess.run(command, cwd=SOURCE, env=env, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
