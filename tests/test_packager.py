from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packager_collects_docx_templates_and_docxengine_stdlib():
    packager = (ROOT / "scripts" / "pyinstaller_build.py").read_text(encoding="utf-8")
    assert "--collect-all" in packager
    assert '"docx"' in packager
    assert "xml.etree.ElementTree" in packager
    assert "docxengine" in packager
    assert "ensure_docx_layout" in packager
    windows = (ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "pyinstaller_build.py" in windows
    smoke = (ROOT / "scripts" / "smoke_packaged_demo.py").read_text(encoding="utf-8")
    assert "pyinstaller_build" in smoke
    assert "teacher-gate.json" in smoke
    assert "comments_before" in smoke
    assert "smoke_worker_teacher_gate" in smoke
    assert "smoke_pi_selftest" in smoke


def test_packager_teacher_gate_treats_zero_comments_before_as_success():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from smoke_packaged_demo import assert_teacher_gate

    payload = assert_teacher_gate(
        {"ok": True, "comments_before": 0, "n_exported": 3, "comments_after": 3}
    )
    assert payload["comments_before"] == 0
    try:
        assert_teacher_gate({"ok": True, "comments_before": 2, "n_exported": 2, "comments_after": 2})
    except SystemExit as exc:
        assert "teacher gate" in str(exc)
    else:
        raise AssertionError("expected comments_before>0 to fail")


def test_word_engine_traces_frozen_stdlib_deps():
    engine = (ROOT / "python" / "thesis_review" / "word" / "engine.py").read_text(encoding="utf-8")
    assert "xml.etree.ElementTree" in engine
    assert "unicodedata" in engine
    assert "zipfile" in engine
