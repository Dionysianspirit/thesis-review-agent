# Thesis Review Agent

面向大数据、人工智能相关本科毕业论文的 Word 审改助手，目标是减少教师重复指出和解释同类问题的工作。

**当前处于需求规划与技术验证阶段，不是已经可用的论文审改产品。**目前包含需求、开源选型、Word 文档引擎测试证据和可复现的中文 DOCX 探针。尚未实现完整 pi agent、模型选择界面或学生历史问题语义检索。

## 已确认的方向

- Word DOCX 输入，使用批注和修订交付建议。
- 每名学生固定对应一位老师；支持不同专业、不同老师的要求。
- 优先识别学生在历次稿件中重复出现的问题，先覆盖格式规范和语言表达。
- 计划基于 [pi](https://github.com/earendil-works/pi)；兼容多个模型提供方，让老师自行选择可用模型。
- 允许调用云端模型。兼容性需验证工具调用、结构化输出等实际能力，不等于承诺任意接口都可直接使用。
- 作者计划免费提供给学校使用；本仓库原创内容采用 MIT，允许下游商业使用。
- 保持流程小而完整：历史意见 → 新稿审查 → 带原文依据的建议 → Word 审改副本。

## 内容

| 路径 | 内容 |
| --- | --- |
| [docs/requirements.md](docs/requirements.md) | 已确认需求、第一版范围与验收方式 |
| [docs/open-source-plan.md](docs/open-source-plan.md) | 8 个开源或公开源码项目的选型、许可与取舍 |
| [evidence/oss-validation.json](evidence/oss-validation.json) | 2026-09-08 技术验证记录 |
| [scripts/probe_chinese_docx.py](scripts/probe_chinese_docx.py) | 独立中文文档集成探针 |
| [scripts/fetch_docxengine.py](scripts/fetch_docxengine.py) | 下载固定提交的测试候选源码，保留其许可文件 |
| [scripts/run_upstream_tests.py](scripts/run_upstream_tests.py) | 运行本次选定的上游测试 |

## 复现文档层验证

需要 Python 3.12 或更新版本。建议使用独立虚拟环境。以下探针只使用内存中的模拟文档，不需要模型密钥，不会上传论文。

```bash
python -m venv .venv
```

激活虚拟环境：Windows PowerShell 使用 `.venv\Scripts\Activate.ps1`；macOS/Linux 使用 `source .venv/bin/activate`。然后执行：

```bash
python -m pip install -r requirements-probe.txt
python scripts/fetch_docxengine.py
python scripts/probe_chinese_docx.py
python scripts/run_upstream_tests.py
```

下载脚本只访问公开 GitHub，将 DocxEngine 固定提交放入 `.vendor/docxengine`，不会执行安装脚本或修改全局配置。已有正确版本时跳过；存在其他内容时拒绝覆盖。测试临时输出位于 `artifacts/`，不进入版本库。

## 验证结果与限制

2026-09-08：选定上游测试 **130 通过、5 跳过**；跳过原因是上游仓库缺少 conformance 测试样本。中文探针验证了批注提取、跨 run 中文修订、保留教师修订、单独拒绝助手修订及文档部分结构保留。

同时复现了上游缺陷：过期定位添加批注时，接口报错但已修改内存中的 `comments.xml`。探针故意保留此复现，并验证临时副本隔离可以保住上一次成功结果。**探针退出成功表示这些明确断言成立，不代表上游缺陷已修复。**候选引擎尚未选为正式生产依赖。

尚未验证 Microsoft Word 打开和排版、真实学校模板、论文审改质量、历史问题语义识别以及 pi 端到端集成。结构测试不能替代真实论文验收。

## 接下来的小流程

1. 封装可替换的 Word 工具，显式开启修订，失败丢弃临时副本。
2. 接入 pi 自定义工具，提供兼容模型选择与调用配置。
3. 保存老师确认的历史问题及原文证据，在新稿中复查。
4. 导出批注和修订副本，由老师决定是否接受。
5. 用老师提供的脱敏历史稿件与当年规范验证误报、采纳情况和总耗时。

## 许可与贡献

原创文档和探针采用 [MIT](LICENSE)。项目不售卖的计划不限制 MIT 赋予他人的使用权。外部项目保留自己的许可，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。本仓库没有合并 Supervisor-Skills 的非商业许可内容或其他候选项目的完整实现。

请只提交模拟或已获授权的脱敏样例；真实学生论文、教师批注、模型密钥和私人历史记录应保留在本地或受控存储中。
