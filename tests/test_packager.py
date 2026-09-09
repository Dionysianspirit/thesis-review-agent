from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packager_collects_docx_templates_and_docxengine_stdlib():
    packager = (ROOT / "scripts" / "pyinstaller_build.py").read_text(encoding="utf-8")
    assert "--collect-all" in packager
    assert '"docx"' in packager
    assert "webview" in packager
    assert "--exclude-module" not in packager
    assert "xml.etree.ElementTree" in packager
    assert "docxengine" in packager
    assert "ensure_docx_layout" in packager
    smoke = (ROOT / "scripts" / "smoke_packaged_demo.py").read_text(encoding="utf-8")
    assert "pyinstaller_build" in smoke
    assert "teacher-gate.json" in smoke
    assert "comments_before" in smoke
    assert "smoke_worker_teacher_gate" in smoke
    assert "smoke_worker_tcp_teacher_gate" in smoke
    assert "assert_gui_bundle" in smoke
    assert "--faux" in smoke
    assert "--portfile" in smoke
    assert "CREATE_NO_WINDOW" in smoke
    assert "论文审改助手.exe" in smoke
    assert "smoke_pi_selftest" in smoke
    assert "revisions_before" in smoke
    windows = (ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "pyinstaller_build.py" in windows
    assert "rename_dist.py" in windows
    assert "LASTEXITCODE" in windows
    assert "smoke_packaged_demo.py" in windows
    assert "--dist" in windows
    assert "Select-Object -Last 1" in windows
    # Quoted PowerShell strings must stay ASCII so Windows parse cannot see a
    # stray quote byte inside a UTF-8 Chinese path.
    for index, line in enumerate(windows.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        assert line.count('"') % 2 == 0, f"unbalanced quotes on line {index}: {line}"
        for chunk in line.split('"')[1::2]:
            assert chunk.isascii(), f"non-ascii quoted string on line {index}: {chunk}"
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "build_windows.ps1" in workflow
    assert "windows-latest" in workflow
    assert "python -m pytest tests -q" in workflow


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


def test_readme_does_not_ship_v04_as_v06():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "仍是 V0.4" in text
    assert "build_windows.ps1" in text
    assert "论文审改助手.exe" in text
    # Latest GitHub Release is still V0.4; do not send teachers there as V0.6.
    assert "](https://github.com/Dionysianspirit/thesis-review-agent/releases/latest)" not in text
    assert "thesis-review-agent-windows" in text
    assert "/actions" in text


def test_rename_dist_survives_windows_console_encoding():
    text = (ROOT / "scripts" / "rename_dist.py").read_text(encoding="utf-8")
    assert "UnicodeEncodeError" in text
    assert "论文审改助手" in text


def test_word_engine_traces_frozen_stdlib_deps():
    engine = (ROOT / "python" / "thesis_review" / "word" / "engine.py").read_text(encoding="utf-8")
    assert "xml.etree.ElementTree" in engine
    assert "unicodedata" in engine
    assert "zipfile" in engine


def test_assert_gui_bundle_requires_teacher_workstation_html(tmp_path: Path):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from smoke_packaged_demo import assert_gui_bundle

    gui = tmp_path / "_internal" / "thesis_review" / "gui"
    gui.mkdir(parents=True)
    try:
        assert_gui_bundle(tmp_path)
    except SystemExit as exc:
        assert "ui.html" in str(exc)
    else:
        raise AssertionError("missing ui.html should fail")
    (gui / "ui.html").write_text("<html>开始 AI 初审 生成正式审稿稿件</html>", encoding="utf-8")
    (gui / "ui.js").write_text("/* js */", encoding="utf-8")
    (gui / "ui.css").write_text("/* css */", encoding="utf-8")
    assert assert_gui_bundle(tmp_path) == gui
