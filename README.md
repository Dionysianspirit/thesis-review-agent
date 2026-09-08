# Thesis Review Agent

面向大数据、人工智能相关本科毕业论文的 Word 审改助手，用来减少教师重复指出和解释同类问题的工作。

**这是可本地试用的原型，不是已经验收过的学校正式产品。**老师在窗口里选文件、确认历史问题、点审查；结果仍是带批注和修订的 Word 副本。Windows 目录包内置 Node 与 pi，老师不用再安装 Python 或 Node。尚未用真实学校模板和真稿做过质量验收。

## 已确认的方向

- Word DOCX 输入，使用批注和修订交付建议。
- 每名学生固定对应一位老师；支持不同专业、不同老师的要求。
- 优先识别学生在历次稿件中重复出现的问题，先覆盖格式规范和语言表达。
- 执行底座使用 [pi](https://github.com/earendil-works/pi) 的 agent core；文档写入仍在 Python 适配层。安装包内置 Node，老师不用自己装。
- 允许调用云端模型。未配置密钥时走离线规则和已确认的历史问题。
- 作者计划免费提供给学校使用；本仓库原创内容采用 MIT，允许下游商业使用。
- 流程：历史意见 → 教师确认 → 新稿审查 → 带原文依据的建议 → Word 审改副本。

## 老师怎么用

目标机器：Windows 10/11，已安装 Microsoft Word。不要求安装 Python 或 Node。

1. 运行 `scripts/build_windows.ps1`，得到 `dist/论文审改助手/`。
2. 把整个文件夹拷给老师，双击 `论文审改助手.exe`。
3. 填写老师与学生身份，导入带批注的历史稿，勾选要复查的问题，再选新稿审查。
4. 用 Word 打开审改副本，由老师接受或拒绝修订。

打包时内部先用英文名，再改成中文目录，避免 Windows 控制台把「论文审改助手」弄成乱码。首次启动可能被 SmartScreen 拦截，选择仍要运行。密钥保存在 `%APPDATA%\ThesisReviewAgent\`，不打进 EXE。没有密钥也可以审查。可用「载入演示稿」走一遍模拟学生小周的例子。

若 Word 里已经打开同一文件，请先关闭再导出，否则可能无法覆盖。

## 开发者怎么跑

需要 Python 3.12 或更新版本。

```bash
python -m venv .venv
```

Windows PowerShell：`.venv\Scripts\Activate.ps1`。然后：

```bash
python -m pip install -r requirements.txt
python scripts/fetch_docxengine.py
python scripts/fetch_node.py
cd agent
npm ci --omit=dev
cd ..
python -m pytest tests -q
powershell -File scripts/start_gui.ps1
```

无窗口的离线演示：

```bash
python -m thesis_review.cli demo --out artifacts/demo
```

CLI 只供开发和测试。老师入口是窗口或 EXE。

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| [docs/requirements.md](docs/requirements.md) | 已确认需求、第一版范围与验收方式 |
| [docs/open-source-plan.md](docs/open-source-plan.md) | 开源选型、许可与取舍 |
| [python/thesis_review](python/thesis_review) | 审查服务、历史库、规则检查、老师窗口 |
| [agent](agent) | 内置 pi 审查循环 |
| [tests](tests) | 适配器、历史匹配、离线审查、pi 自检 |
| [evidence/oss-validation.json](evidence/oss-validation.json) | 2026-09-08 文档引擎验证记录 |
| [scripts/probe_chinese_docx.py](scripts/probe_chinese_docx.py) | 独立中文文档集成探针 |
| [scripts/fetch_docxengine.py](scripts/fetch_docxengine.py) | 下载固定提交的 DocxEngine |
| [scripts/fetch_node.py](scripts/fetch_node.py) | 下载便携 Node 运行时 |
| [scripts/build_windows.ps1](scripts/build_windows.ps1) | PyInstaller 目录版打包，并打进 Node 与 pi |

## 文档层验证

探针只使用内存中的模拟文档，不需要模型密钥，不会上传论文。

```bash
python -m pip install -r requirements-probe.txt
python scripts/fetch_docxengine.py
python scripts/probe_chinese_docx.py
python scripts/run_upstream_tests.py
```

下载脚本只访问公开 GitHub，将 DocxEngine 固定提交放入 `.vendor/docxengine`。已有正确版本时跳过；存在其他内容时拒绝覆盖。

2026-09-08：选定上游测试 **130 通过、5 跳过**。中文探针覆盖批注提取、跨 run 中文修订、保留教师修订、单独拒绝助手修订。过期定位添加批注时，上游仍会改 `comments.xml`；本原型在隔离副本上写入，失败不提交。**探针成功不代表上游缺陷已修复，也不代表可以当生产依赖。**

尚未验证：Microsoft Word 排版、真实学校模板、审改质量、语义级历史识别、pi 端到端集成。

## 还不做

全文代写、自动评分、创新性判定、学生画像、在线 Word 编辑器、多模型裁决、把一次局部修订升成全校规则。

## 许可与贡献

原创文档、探针和原型代码采用 [MIT](LICENSE)。外部项目保留自己的许可，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。请只提交模拟或已获授权的脱敏样例；真实学生论文、教师批注、模型密钥和私人历史记录应留在本地。
