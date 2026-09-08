from __future__ import annotations

import sys

from thesis_review.errors import ReviewError
from thesis_review.paths import vendor_src


def ensure_engine() -> None:
    src = vendor_src()
    if not (src / "docxengine" / "__init__.py").is_file() and not (src / "__init__.py").is_file():
        raise ReviewError(
            "engine_missing",
            f"未找到 DocxEngine：{src}。请先运行 python scripts/fetch_docxengine.py。",
        )
    path = str(src)
    if path not in sys.path:
        sys.path.insert(0, path)
