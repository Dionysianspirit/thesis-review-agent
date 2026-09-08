"""History matching ignores empty anchors, short notes, and heading collisions."""
from __future__ import annotations

from thesis_review.history.match import match_issue
from thesis_review.types import IssueRecord, ParagraphView


def _issue(*, span: str, text: str) -> IssueRecord:
    return IssueRecord(
        id="i1",
        teacher_id="t",
        student_id="s",
        major="人工智能",
        source_draft_id="v1",
        category="A",
        status="confirmed",
        original_kind="comment",
        original_text=text,
        original_span=span,
        original_context=span,
        original_anchor="P1",
    )


def _paras(*texts: str) -> list[ParagraphView]:
    return [ParagraphView(ordinal=i + 1, anchor=f"P{i + 1}", text=text) for i, text in enumerate(texts)]


def test_empty_span_and_short_comment_do_not_match():
    issue = _issue(span="", text="格式")
    paras = _paras("请按学校格式标准调整页边距和字体。")
    assert match_issue(issue, paras) is None


def test_punctuation_span_does_not_match_formula_paragraph():
    issue = _issue(span="()", text="这里要插入公式")
    paras = _paras("初始模型，h(x)为第 m 棵树拟合的残差，则第m 轮的模型更新公式为：")
    assert match_issue(issue, paras) is None


def test_substantial_span_still_matches():
    issue = _issue(span="本研究非常非常有效。", text="避免主观评价")
    paras = _paras("本研究非常非常有效。", "其他段落")
    hit = match_issue(issue, paras)
    assert hit is not None
    assert "非常非常有效" in hit.new_quote


def test_short_unique_cover_line_still_matches():
    issue = _issue(span="作 者 王佳宁", text="把文字尽量都居中 调整好看一点")
    paras = _paras("作 者 王佳宁", "摘 要")
    hit = match_issue(issue, paras)
    assert hit is not None
    assert "王佳宁" in hit.new_quote


def test_renumbered_heading_does_not_count_as_repeat():
    issue = _issue(span="2.2.2 梯度提升树算法的适用性分析", text="写优劣势")
    paras = _paras("2.3.2 梯度提升树算法的适用性分析")
    assert match_issue(issue, paras) is None


def test_renumbered_table_title_does_not_count_as_repeat():
    issue = _issue(span="表 1数据基本情况表", text="格式 表格中表1居左")
    paras = _paras("表 2 数据基本情况表")
    assert match_issue(issue, paras) is None


def test_toc_dotted_line_is_not_a_hit():
    issue = _issue(span="3.1 梯度提升树模型设计", text="插入公式")
    paras = _paras("3.1 梯度提升树模型设计........................................................6")
    assert match_issue(issue, paras) is None
