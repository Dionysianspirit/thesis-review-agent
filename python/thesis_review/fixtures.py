from __future__ import annotations

import io
from pathlib import Path

from docx import Document

OVERCLAIM_CLAIM_QUOTE = "实验结果表明该方法显著提升了分类准确率。"
OVERCLAIM_EVIDENCE_QUOTE = "准确率由 0.81 提高到 0.83。"
SUPPORTED_CLAIM_QUOTE = "实验结果表明准确率达到 0.91，显著高于基线 0.72。"
SUPPORTED_EVIDENCE_QUOTE = "准确率为 0.91，基线模型为 0.72。配对检验 p<0.01。"


def write_demo_drafts(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    mapping = {
        "v1": _history_v1(),
        "v2": _history_v2(),
        "new": _new_draft(),
    }
    paths: dict[str, Path] = {}
    for name, data in mapping.items():
        path = directory / f"{name}.docx"
        path.write_bytes(data)
        paths[name] = path
    (directory / "overclaim.docx").write_bytes(overclaim_draft())
    return paths


def overclaim_draft() -> bytes:
    """Conclusion overclaims a tiny accuracy bump with no significance test."""
    doc = Document()
    doc.add_paragraph("本科毕业论文")
    doc.add_paragraph("1 摘要")
    doc.add_paragraph("本文研究一种用于图像分类的卷积神经网络方法。")
    doc.add_paragraph("2 方法")
    doc.add_paragraph("本文使用卷积神经网络提取图像特征并完成分类。")
    doc.add_paragraph("3 实验结果")
    doc.add_paragraph(f"在测试集上，{OVERCLAIM_EVIDENCE_QUOTE}未报告显著性检验，也未给出基线对照。")
    doc.add_paragraph("4 结论")
    doc.add_paragraph(OVERCLAIM_CLAIM_QUOTE)
    doc.add_paragraph("参考文献")
    doc.add_paragraph("[1] 张三. 示例文献. 期刊, 2024.")
    return _save(doc)


def supported_claim_draft() -> bytes:
    """Conclusion claim is backed by a baseline and a significance test."""
    doc = Document()
    doc.add_paragraph("本科毕业论文")
    doc.add_paragraph("1 摘要")
    doc.add_paragraph("本文研究一种用于图像分类的卷积神经网络方法。")
    doc.add_paragraph("2 方法")
    doc.add_paragraph("本文使用卷积神经网络提取图像特征并完成分类。")
    doc.add_paragraph("3 实验结果")
    doc.add_paragraph(SUPPORTED_EVIDENCE_QUOTE)
    doc.add_paragraph("4 结论")
    doc.add_paragraph(SUPPORTED_CLAIM_QUOTE)
    doc.add_paragraph("参考文献")
    doc.add_paragraph("[1] 张三. 示例文献. 期刊, 2024.")
    return _save(doc)


def _history_v1() -> bytes:
    doc = Document()
    doc.add_paragraph("本科毕业论文")
    doc.add_paragraph("本研究使用卷积神经网络（CNN）进行分类。")
    paragraph = doc.add_paragraph()
    paragraph.add_run("本研究")
    paragraph.add_run("非常").bold = True
    paragraph.add_run("非常")
    paragraph.add_run("有效。")
    doc.add_comment(paragraph.runs, text="避免主观评价，请给出实验依据。", author="老师甲", initials="甲")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "模型"
    table.cell(0, 1).text = "准确率"
    table.cell(1, 0).text = "示例模型"
    table.cell(1, 1).text = "示例值"
    return _save(doc)


def _history_v2() -> bytes:
    doc = Document()
    doc.add_paragraph("本科毕业论文")
    doc.add_paragraph("本研究使用卷积神经网络（CNN）进行图像分类。")
    paragraph = doc.add_paragraph()
    paragraph.add_run("本研究非常非常有效。")
    doc.add_comment(paragraph.runs, text="此句仍缺实验依据。", author="老师甲", initials="甲")
    return _save(doc)


def _new_draft() -> bytes:
    doc = Document()
    doc.add_paragraph("本科毕业论文")
    doc.add_paragraph("本研究使用卷积神经网络（CNN）进行图像分类。")
    doc.add_paragraph("本研究非常非常有效。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "模型"
    table.cell(0, 1).text = "准确率"
    table.cell(1, 0).text = "示例模型"
    table.cell(1, 1).text = "示例值"
    doc.add_paragraph("参考文献")
    doc.add_paragraph("[1] 张三. 示例文献. 期刊, 2024.")
    doc.add_paragraph("[3] 李四. 另一篇文献. 期刊, 2025.")
    return _save(doc)


def _save(doc: Document) -> bytes:
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
