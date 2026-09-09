from __future__ import annotations

from pathlib import Path

from thesis_review.settings import (
    AppSettings,
    apply_model,
    load_settings,
    public_settings,
    save_settings,
)


def test_saved_api_key_roundtrip_and_is_hidden_from_public_state(tmp_path: Path):
    settings = AppSettings()
    apply_model(
        settings,
        {
            "provider": "openai-compatible",
            "model": "gpt-4o-mini",
            "base_url": "https://example.test/v1",
            "api_key": "sk-keep-me",
        },
    )
    save_settings(tmp_path, settings)
    loaded = load_settings(tmp_path)
    assert loaded.api_key == "sk-keep-me"
    visible = public_settings(loaded)
    assert visible["api_key_set"] is True
    assert visible["api_key"] == ""
    assert "sk-keep-me" not in str(visible)


def test_empty_api_key_submit_does_not_wipe_saved_key(tmp_path: Path):
    settings = AppSettings(api_key="sk-keep-me", model="gpt-4o-mini")
    apply_model(settings, {"model": "gpt-4o-mini", "api_key": "   "})
    save_settings(tmp_path, settings)
    assert load_settings(tmp_path).api_key == "sk-keep-me"


def test_session_paths_roundtrip(tmp_path: Path):
    reviewed = tmp_path / "out" / "new-reviewed.docx"
    settings = AppSettings(
        last_reviewed_path=str(reviewed),
        last_output_dir=str(reviewed.parent),
    )
    save_settings(tmp_path, settings)
    loaded = load_settings(tmp_path)
    assert loaded.last_reviewed_path == str(reviewed)
    assert loaded.last_output_dir == str(reviewed.parent)
