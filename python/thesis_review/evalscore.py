from __future__ import annotations

from dataclasses import dataclass

NAV_READ = frozenset({"read_section", "read_paragraphs", "find_text"})


@dataclass
class CaseScore:
    case: str
    passed: bool
    reasons: list[str]
    tool_ops: list[str]
    n_findings: int
    sources: dict[str, int]
    error: str = ""


def score_case(
    name: str,
    findings: list,
    trace: dict | list,
    *,
    error: str = "",
) -> CaseScore:
    ops = _tool_ops(trace)
    sources = _source_counts(findings)
    reasons: list[str] = []
    if error:
        reasons.append(f"审查失败：{error}")
        return CaseScore(
            case=name,
            passed=False,
            reasons=reasons,
            tool_ops=ops,
            n_findings=len(findings or []),
            sources=sources,
            error=error,
        )
    if name == "overclaim":
        if sources.get("argument", 0) < 1:
            reasons.append("缺少论证批注")
        if not _navigated(_window_before(ops, "record_argument_finding")):
            reasons.append("记录论证前缺少导航（list_outline 与有界读取）")
    elif name == "abandon":
        if sources.get("argument", 0):
            reasons.append("证据充分的主张被误批")
        if "commit_review" not in ops:
            reasons.append("未提交审改")
        if not _navigated(_window_before(ops, "commit_review")):
            reasons.append("放弃前缺少导航（list_outline 与有界读取）")
    elif name == "history":
        if sources.get("history", 0) < 1:
            reasons.append("缺少历史复犯批注")
    else:
        reasons.append(f"未知金标：{name}")
    return CaseScore(
        case=name,
        passed=not reasons,
        reasons=reasons,
        tool_ops=ops,
        n_findings=len(findings or []),
        sources=sources,
    )


def _tool_ops(trace: dict | list) -> list[str]:
    if isinstance(trace, dict):
        items = trace.get("ops") or []
    else:
        items = trace or []
    ops: list[str] = []
    for item in items:
        if isinstance(item, dict):
            ops.append(str(item.get("op") or ""))
        else:
            ops.append(str(item))
    return [op for op in ops if op]


def _window_before(ops: list[str], marker: str) -> list[str]:
    if marker in ops:
        return ops[: ops.index(marker)]
    return list(ops)


def _navigated(ops: list[str]) -> bool:
    return "list_outline" in ops and any(op in NAV_READ for op in ops)


def _source_counts(findings: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in findings or []:
        source = item.get("source") if isinstance(item, dict) else getattr(item, "source", "")
        if not source:
            continue
        counts[source] = counts.get(source, 0) + 1
    return counts
