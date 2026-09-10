#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the thesis-review-agent repo.
# Prepares the Python virtualenv, project + probe dependencies, the vendored
# DocxEngine test source, and the Node-based Pi agent runtime.
set -euo pipefail

cd "$(dirname "$0")/.."

# The default image ships python3.12 but not the venv/ensurepip module.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3.12-venv
fi

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install -r requirements-probe.txt

# Vendored, pinned public DocxEngine source used by the upstream probe tests.
./.venv/bin/python scripts/fetch_docxengine.py

# Pi agent runtime dependencies (Node). fetch_node.py is Windows-packaging only;
# on Linux the system Node runtime is used directly.
( cd agent && npm ci --omit=dev )

echo "Cloud Agent install complete."
