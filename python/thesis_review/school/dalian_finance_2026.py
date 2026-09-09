"""大连财经学院 2026 届可自动检查的格式条款。

依据：
- 《关于做好 2026 届本科毕业论文（设计）工作的通知》（大财教发〔2025〕78 号）
- 《论文指导工作手册（2025）》第四节、第九节
- 《大连财经学院本科毕业论文（设计）格式标准》（2024 年 11 月修订）
"""
from __future__ import annotations

import re
import uuid

from thesis_review.types import Evidence, Finding, ParagraphView

SCHOOL = "大连财经学院"
FORMAT_STANDARD = "《大连财经学院本科毕业论文（设计）格式标准》（2024 年 11 月修订）"
HANDBOOK = "《论文指导工作手册（2025）》"
NOTICE = "大财教发〔2025〕78 号"

REQUIRED_SECTIONS = (
    ("大连财经学院本科毕业论文", "封面文头"),
    ("摘要", "中文内容摘要"),
    ("关键词", "中文关键词"),
    ("Abstract", "英文摘要"),
    ("目录", "目录"),
    ("参考文献", "参考文献"),
    ("致谢", "致谢"),
)

REF_ITEM_RE = re.compile(r"^\[(\d+)\]")
YEAR_RE = re.compile(r"(19|20)\d{2}")
TYPE_MARK_RE = re.compile(r"\[(M|J|C|N|D|R|EB/OL|EB)\]", re.I)
LATIN_RE = re.compile(r"[A-Za-z]{4,}")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _finding(**kwargs) -> Finding:
    kwargs.setdefault("category", "C")
    kwargs.setdefault("source", "rule")
    kwargs.setdefault("apply", "comment")
    kwargs.setdefault("kind", "format")
    kwargs.setdefault("id", uuid.uuid4().hex)
    kwargs.setdefault("suggested_old", None)
    kwargs.setdefault("suggested_new", None)
    kwargs.setdefault("issue_id", None)
    return Finding(**kwargs)


def check_school_rules(paragraphs: list[ParagraphView], *, draft_id: str = "") -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_missing_sections(paragraphs, draft_id=draft_id))
    findings.extend(_abstract_and_keywords(paragraphs, draft_id=draft_id))
    findings.extend(_body_length(paragraphs, draft_id=draft_id))
    findings.extend(_references(paragraphs, draft_id=draft_id))
    return findings


def _missing_sections(paragraphs: list[ParagraphView], *, draft_id: str) -> list[Finding]:
    blob = _norm("".join(item.text for item in paragraphs))
    findings = []
    first = paragraphs[0] if paragraphs else None
    for needle, label in REQUIRED_SECTIONS:
        if needle.lower() not in blob.lower() and needle not in blob:
            findings.append(
                _finding(
                    code="missing_required_section",
                    problem=f"缺少必备项目「{label}」。",
                    rationale=f"{FORMAT_STANDARD} 规定构成项目含{label}；不符合标准不能参加答辩。",
                    quote=needle,
                    anchor=first.anchor if first else "",
                    paragraph_index=first.ordinal if first else 0,
                    draft_id=draft_id,
                    evidence=[Evidence(kind="rule", draft_id=draft_id, text=label)],
                )
            )
    return findings


def _section_after(paragraphs: list[ParagraphView], title: str) -> tuple[int | None, list[ParagraphView]]:
    start = None
    for index, paragraph in enumerate(paragraphs):
        if title.lower() in _norm(paragraph.text).lower() or _norm(paragraph.text) == title:
            start = index
            break
    if start is None:
        return None, []
    collected: list[ParagraphView] = []
    stop_tokens = {"关键词", "Abstract", "Keywords", "目录", "引言", "参考文献", "致谢", "附录"}
    for paragraph in paragraphs[start + 1 :]:
        token = _norm(paragraph.text)
        if any(token.startswith(stop) or token == stop for stop in stop_tokens):
            break
        if paragraph.text.strip():
            collected.append(paragraph)
    return start, collected


def _abstract_and_keywords(paragraphs: list[ParagraphView], *, draft_id: str) -> list[Finding]:
    findings: list[Finding] = []
    start, body = _section_after(paragraphs, "摘要")
    if start is not None:
        text = "".join(item.text for item in body)
        n_han = len(HAN_RE.findall(text))
        if n_han and not (400 <= n_han <= 500):
            anchor = body[0] if body else paragraphs[start]
            findings.append(
                _finding(
                    code="abstract_length",
                    problem=f"中文摘要约 {n_han} 字，应控制在 400–500 字。",
                    rationale=f"{FORMAT_STANDARD} 2.2.2：内容摘要字数控制在 400-500 字之间。",
                    quote=text[:40],
                    anchor=anchor.anchor,
                    paragraph_index=anchor.ordinal,
                    draft_id=draft_id,
                    evidence=[Evidence(kind="rule", draft_id=draft_id, text=str(n_han))],
                )
            )
    keywords_para = next((item for item in paragraphs if "关键词" in _norm(item.text) and "keywords" not in item.text.lower()), None)
    if keywords_para is not None:
        payload = re.split(r"关键词[:：]?", keywords_para.text, maxsplit=1)
        content = payload[-1] if payload else ""
        parts = [part.strip() for part in re.split(r"[;；]", content) if part.strip()]
        if not (3 <= len(parts) <= 5):
            findings.append(
                _finding(
                    code="keyword_count",
                    problem=f"中文关键词 {len(parts)} 个，应为 3～5 个，词间用分号隔开。",
                    rationale=f"{FORMAT_STANDARD} 3.3.4：关键词为 3～5 个，词间用分号隔开。",
                    quote=keywords_para.text,
                    anchor=keywords_para.anchor,
                    paragraph_index=keywords_para.ordinal,
                    draft_id=draft_id,
                    evidence=[Evidence(kind="rule", draft_id=draft_id, text=keywords_para.text)],
                )
            )
    return findings


def _body_length(paragraphs: list[ParagraphView], *, draft_id: str) -> list[Finding]:
    start = 0
    end = len(paragraphs)
    for index, paragraph in enumerate(paragraphs):
        token = _norm(paragraph.text)
        if token in {"目录"} or token.startswith("1") and len(token) < 20:
            start = index
        if token.startswith("参考文献"):
            end = index
            break
    body = "".join(item.text for item in paragraphs[start:end])
    n_han = len(HAN_RE.findall(body))
    if n_han >= 10000:
        return []
    first = paragraphs[start] if paragraphs else None
    if first is None:
        return []
    if n_han < 8000:
        problem = f"正文汉字约 {n_han} 字，学校要求不少于 8000 字，格式标准要求 10000 字以上。"
        code = "body_too_short"
    else:
        problem = f"正文汉字约 {n_han} 字，已过手册 8000 字门槛，但 {FORMAT_STANDARD} 要求 10000 字以上。"
        code = "body_below_format_standard"
    return [
        _finding(
            code=code,
            problem=problem,
            rationale=f"{HANDBOOK} 第四节：不少于 8000 字；{FORMAT_STANDARD} 2.2.5：正文字数 10000 字以上。",
            quote=first.text[:30],
            anchor=first.anchor,
            paragraph_index=first.ordinal,
            draft_id=draft_id,
            evidence=[Evidence(kind="rule", draft_id=draft_id, text=str(n_han))],
        )
    ]


def _reference_entries(paragraphs: list[ParagraphView]) -> list[ParagraphView]:
    start = None
    for index, paragraph in enumerate(paragraphs):
        if _norm(paragraph.text).startswith("参考文献"):
            start = index
            break
    if start is None:
        return []
    entries = []
    for paragraph in paragraphs[start + 1 :]:
        token = _norm(paragraph.text)
        if token.startswith("致谢") or token.startswith("附录"):
            break
        if REF_ITEM_RE.match(paragraph.text.strip()):
            entries.append(paragraph)
    return entries


def _references(paragraphs: list[ParagraphView], *, draft_id: str) -> list[Finding]:
    entries = _reference_entries(paragraphs)
    if not entries:
        return []
    findings: list[Finding] = []
    last = entries[-1]
    if len(entries) < 15:
        findings.append(
            _finding(
                code="references_too_few",
                problem=f"参考文献 {len(entries)} 篇，手册要求不少于 15 篇（格式标准下限为 10 篇）。",
                rationale=f"{HANDBOOK} 第四节：参考文献不少于 15 篇，其中至少 5 篇外文；{FORMAT_STANDARD} 2.2.7：不低于 10 个。",
                quote=last.text,
                anchor=last.anchor,
                paragraph_index=last.ordinal,
                draft_id=draft_id,
                evidence=[Evidence(kind="rule", draft_id=draft_id, text=str(len(entries)))],
            )
        )
    foreign = [item for item in entries if LATIN_RE.search(item.text)]
    if len(foreign) < 5:
        findings.append(
            _finding(
                code="references_need_foreign",
                problem=f"外文文献约 {len(foreign)} 篇，手册要求至少 5 篇。",
                rationale=f"{HANDBOOK} 第四节：参考文献不少于 15 篇，其中至少有 5 篇外文文献。",
                quote=last.text,
                anchor=last.anchor,
                paragraph_index=last.ordinal,
                draft_id=draft_id,
                evidence=[Evidence(kind="rule", draft_id=draft_id, text=str(len(foreign)))],
            )
        )
    years = []
    for item in entries:
        match = YEAR_RE.search(item.text)
        if match:
            years.append(int(match.group(0)))
    if years:
        recent = [year for year in years if year >= 2024]
        ratio = len(recent) / len(years)
        if ratio < 0.6:
            findings.append(
                _finding(
                    code="references_not_recent",
                    problem=f"近三年文献约占 {ratio:.0%}，手册要求不少于文献总数的 60%。",
                    rationale=f"{HANDBOOK} 第四节：近三年内的文献不少于文献总数的 60%。",
                    quote=last.text,
                    anchor=last.anchor,
                    paragraph_index=last.ordinal,
                    draft_id=draft_id,
                    evidence=[Evidence(kind="rule", draft_id=draft_id, text=str(years))],
                )
            )
    unmarked = [item for item in entries if not TYPE_MARK_RE.search(item.text)]
    if unmarked:
        findings.append(
            _finding(
                code="reference_missing_type_marker",
                problem="参考文献未标注文献类型标识，如 [M]、[J]、[D]、[EB/OL]。",
                rationale=f"{FORMAT_STANDARD} 2.2.7：著录应符合 GB/T 7714，需含文献类型标志。",
                quote=unmarked[0].text,
                anchor=unmarked[0].anchor,
                paragraph_index=unmarked[0].ordinal,
                draft_id=draft_id,
                evidence=[Evidence(kind="rule", draft_id=draft_id, text=unmarked[0].text)],
            )
        )
    return findings
