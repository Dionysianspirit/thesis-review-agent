from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    teacher_id: str = "teacher-a"
    teacher_name: str = "老师甲"
    student_id: str = "zhou"
    student_name: str = "小周"
    major: str = "人工智能"
    provider: str = "openai-compatible"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    output_dir: str = ""


def settings_path(home: Path) -> Path:
    return home / "settings.json"


def load_settings(home: Path) -> AppSettings:
    path = settings_path(home)
    if not path.is_file():
        return AppSettings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = {field.name for field in AppSettings.__dataclass_fields__.values()}
    return AppSettings(**{key: value for key, value in raw.items() if key in allowed})


def save_settings(home: Path, settings: AppSettings) -> None:
    home.mkdir(parents=True, exist_ok=True)
    settings_path(home).write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
