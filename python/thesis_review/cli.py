from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from thesis_review.fixtures import write_demo_drafts
from thesis_review.history.store import HistoryStore
from thesis_review.paths import app_home
from thesis_review.service import ThesisReviewService
from thesis_review.settings import load_settings
from thesis_review.word.adapter import WordAdapter


def build_service(home: Path) -> ThesisReviewService:
    home.mkdir(parents=True, exist_ok=True)
    return ThesisReviewService(
        store=HistoryStore(home / "thesis-review.sqlite"),
        adapter=WordAdapter(),
        home=home,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thesis-review", description="毕业论文审改助手（开发用命令行）")
    parser.add_argument("--home", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="导入历史稿")
    ingest.add_argument("--teacher", required=True)
    ingest.add_argument("--student", required=True)
    ingest.add_argument("--major", default="人工智能")
    ingest.add_argument("--draft", required=True)
    ingest.add_argument("docx", type=Path)

    confirm = sub.add_parser("confirm", help="确认一条历史问题")
    confirm.add_argument("--teacher", required=True)
    confirm.add_argument("--student", required=True)
    confirm.add_argument("--issue", required=True)

    review = sub.add_parser("review", help="审查新稿")
    review.add_argument("--teacher", required=True)
    review.add_argument("--student", required=True)
    review.add_argument("--draft", default="new")
    review.add_argument("--offline", action="store_true")
    review.add_argument("--out", type=Path, required=True)
    review.add_argument("docx", type=Path, nargs="?")

    demo = sub.add_parser("demo", help="用内置模拟稿跑通离线审查")
    demo.add_argument("--out", type=Path, required=True)

    evaluate = sub.add_parser("eval", help="用本机密钥跑真实模型金标（不进 CI）")
    evaluate.add_argument("--out", type=Path, required=True)
    evaluate.add_argument("--manifest", type=Path, default=None, help="可选：本机授权真稿清单，不提交")

    args = parser.parse_args(argv)
    home = args.home or app_home()
    service = build_service(home)

    if args.command == "ingest":
        records = service.ingest_history(
            teacher_id=args.teacher,
            student_id=args.student,
            major=args.major,
            draft_id=args.draft,
            data=args.docx.read_bytes(),
        )
        print(json.dumps([record.id for record in records], ensure_ascii=False))
        return 0
    if args.command == "confirm":
        record = service.confirm_issue(
            teacher_id=args.teacher, student_id=args.student, issue_id=args.issue
        )
        print(record.status)
        return 0
    if args.command == "review":
        if args.docx is None:
            raise SystemExit("review 需要 docx 路径")
        result = service.review(
            teacher_id=args.teacher,
            student_id=args.student,
            draft_id=args.draft,
            data=args.docx.read_bytes(),
            output_dir=args.out,
            use_model=not args.offline,
            settings=load_settings(home),
        )
        print(result.reviewed_path)
        print(result.findings_path)
        return 0
    if args.command == "demo":
        drafts = write_demo_drafts(args.out / "demo-drafts")
        candidates = service.ingest_history(
            teacher_id="teacher-a",
            student_id="zhou",
            major="人工智能",
            draft_id="v1",
            data=drafts["v1"].read_bytes(),
        )
        for item in candidates:
            service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=item.id)
        result = service.review(
            teacher_id="teacher-a",
            student_id="zhou",
            draft_id="new",
            data=drafts["new"].read_bytes(),
            output_dir=args.out,
            use_model=False,
        )
        print(result.reviewed_path)
        print(result.findings_path)
        return 0
    if args.command == "eval":
        from thesis_review.evalrun import run_eval_command

        return run_eval_command(
            settings_home=home,
            out=args.out,
            manifest=args.manifest,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
