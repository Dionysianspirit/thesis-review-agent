"""Offline review writes a clean copy and labelled candidate findings until the teacher exports."""
from __future__ import annotations

from pathlib import Path

from docx import Document

from tests.helpers import sample_history_v1, sample_new_draft, sample_overclaim_draft
from thesis_review.history.store import HistoryStore
from thesis_review.quality import summarize_quality
from thesis_review.service import ThesisReviewService
from thesis_review.settings import AppSettings
from thesis_review.word.adapter import WordAdapter


def test_offline_review_labels_history_and_rule_findings(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    subjective = next(item for item in candidates if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)

    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    sources = {item.source for item in result.findings}
    assert "history" in sources
    assert "rule" in sources
    assert "model" not in sources
    history_item = next(item for item in result.findings if item.source == "history")
    assert history_item.issue_id == subjective.id
    assert "待老师判断" in history_item.problem
    snippet = (subjective.problem or subjective.original_text or "").strip()[:8]
    assert snippet in history_item.problem
    assert "仍出现已确认的历史问题" not in history_item.problem
    assert any("避免主观评价" in evidence.text for evidence in history_item.evidence)
    assert all(item.teacher_decision == "pending" for item in result.findings)
    assert result.reviewed_path.exists()
    assert result.findings_path.exists()
    Document(str(result.reviewed_path))
    opened = WordAdapter().open_path(result.reviewed_path)
    comments = WordAdapter().extract_comments(opened)
    texts = [comment.text for comment in comments]
    assert not any("历次" in text or "已指出" in text for text in texts)
    assert not any(comment.author == "审改助手" for comment in comments)
    quality = summarize_quality(result.findings, {})
    assert quality["history_recall"] >= 1
    assert quality["history_recidivism"] == 0
    assert "api_key" not in quality


def test_offline_review_has_no_argument_source(tmp_path: Path):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="overclaim",
        data=sample_overclaim_draft(),
        output_dir=tmp_path / "out",
        use_model=False,
    )
    assert all(item.source != "argument" for item in result.findings)


def test_pi_failure_with_key_skips_history_but_keeps_rules(tmp_path: Path, monkeypatch):
    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )
    candidates = service.ingest_history(
        teacher_id="teacher-a",
        student_id="zhou",
        major="人工智能",
        draft_id="v1",
        data=sample_history_v1(),
    )
    subjective = next(item for item in candidates if "主观评价" in item.original_text)
    service.confirm_issue(teacher_id="teacher-a", student_id="zhou", issue_id=subjective.id)

    def _boom(self, **_kwargs):
        raise RuntimeError("pi down")

    monkeypatch.setattr(ThesisReviewService, "_review_with_pi", _boom)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=True,
        settings=AppSettings(api_key="sk-test", model="gpt-4o-mini"),
    )
    sources = {item.source for item in result.findings}
    assert "history" not in sources
    assert "rule" in sources
    assert "argument" not in sources
    assert result.warning
    assert "复犯" in result.warning or "历史" in result.warning or "离线" in result.warning


def test_pi_failure_hides_node_stack_from_teachers(tmp_path: Path, monkeypatch):
    from thesis_review.service import offline_fallback_warning

    stacked = (
        "Error: connect ECONNREFUSED 127.0.0.1:62852 at "
        "TCPConnectWrap.afterConnect [as oncomplete] (node:net:1637:16)"
    )
    warning = offline_fallback_warning(RuntimeError(stacked), semantic=True)
    assert "离线规则" in warning
    assert "请再试一次" in warning
    assert "复犯" in warning
    assert "TCPConnectWrap" not in warning
    assert "62852" not in warning
    assert "ECONNREFUSED" not in warning

    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )

    def _boom(self, **_kwargs):
        raise RuntimeError(stacked)

    monkeypatch.setattr(ThesisReviewService, "_review_with_pi", _boom)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=True,
        settings=AppSettings(api_key="sk-test", model="gpt-4o-mini"),
    )
    assert "TCPConnectWrap" not in result.warning
    assert "ECONNREFUSED" not in result.warning
    assert "离线规则" in result.warning


def test_timeout_warning_hides_command_list():
    from thesis_review.service import offline_fallback_warning

    timed = RuntimeError(
        "Command '['C:\\\\Users\\\\ASUS\\\\Downloads\\\\thesis-review-agent-v0.6.1-windows\\\\runtime\\\\node\\\\node.exe', "
        "'C:\\\\Users\\\\ASUS\\\\Downloads\\\\thesis-review-agent-v0.6.1-windows\\\\agent\\\\review.mjs']' timed out after 180 seconds"
    )
    warning = offline_fallback_warning(timed, semantic=True)
    assert "Command" not in warning
    assert "node.exe" not in warning
    assert "等待时间" in warning
    assert "复犯" in warning


def test_pi_timeout_keeps_live_findings(tmp_path: Path, monkeypatch):
    from thesis_review.errors import ReviewError
    from thesis_review.live import write_findings

    service = ThesisReviewService(
        store=HistoryStore(tmp_path / "history.sqlite"),
        adapter=WordAdapter(),
        home=tmp_path,
    )

    def _boom(self, **_kwargs):
        write_findings(
            tmp_path / "out" / "live",
            [
                {
                    "id": "content-1",
                    "source": "model",
                    "kind": "content",
                    "subtype": "argument",
                    "category": "论证",
                    "problem": "主张缺少证据。",
                    "rationale": "实验段落未给出对照。",
                    "quote": "准确率显著提升",
                    "anchor": "p1",
                }
            ],
        )
        raise ReviewError("pi_timeout", "模型初审超过等待时间，已停止。")

    monkeypatch.setattr(ThesisReviewService, "_review_with_pi", _boom)
    result = service.review(
        teacher_id="teacher-a",
        student_id="zhou",
        draft_id="new",
        data=sample_new_draft(),
        output_dir=tmp_path / "out",
        use_model=True,
        settings=AppSettings(api_key="sk-test", model="gpt-4o-mini"),
    )
    assert any(item.id == "content-1" for item in result.findings)
    assert result.used_model is True
    assert "已保留" in result.warning
    assert "离线规则" not in result.warning
    assert "Command" not in result.warning

