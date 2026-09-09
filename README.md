# Thesis Review Agent

面向大数据、人工智能相关本科毕业论文的 Word 审改助手，用来减少教师重复指出和解释同类问题的工作。

**这是可本地试用的原型（当前 V0.5），不是已经验收过的学校正式产品。**老师在窗口里选文件、确认历史问题、点审查；结果仍是带批注和修订的 Word 副本。Windows 目录包内置 Node 与 pi，老师不用再安装 Python 或 Node。自动化测试仍是预定工具路径，只证明链路。论证是否真会取证，要另跑本机真实模型 eval；未通过前不要当成已经会审论证。

学校格式条款已按大连财经学院 2026 届手册做成确定性检查。授权真稿只在本机对照，不进本仓库。历史复查仍用收紧后的字符串匹配召回候选；有密钥时由 Pi 判断是不是同一条问题，Python 只负责召回和校验原文。判定复犯且 quote 是本稿子串，才写复发批注。不确定，或标题未改、内容已修，则跳过。无密钥时仍按字符串命中写历史批注，不是语义判断。语言模型建议已去掉，叠词仍走语言规则。有密钥时，Pi 对关键主张是否被实验或数据支持做多步取证；证据不足或原文对不上就不写论证批注。这还不是四类论证问题都审完，也不是语义历史召回。

## 已确认的方向

- Word DOCX 输入，使用批注和修订交付建议。
- 每名学生固定对应一位老师；支持不同专业、不同老师的要求。
- 优先识别学生在历次稿件中重复出现的问题，先覆盖格式规范和语言表达。
- 执行底座使用 [pi](https://github.com/earendil-works/pi) 的 agent core；文档写入仍在 Python 适配层。安装包内置 Node，老师不用自己装。
- 允许调用云端模型。未配置密钥时走离线规则和已确认的历史问题。
- 作者计划免费提供给学校使用；本仓库原创内容采用 MIT，允许下游商业使用。
- 流程：历史意见 → 教师确认 → 新稿审查 → 带原文依据的建议 → Word 审改副本。

## 当前进度与下一步

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| V0.1 | 已完成 | 老师窗口、内置 Node / pi、历史入库与确认、离线规则、批注/修订写回 Word |
| V0.2 | 已完成 | 收紧历史匹配：空锚点、短批注、章节号/表图题重编号、目录点线不再当成复发；批注区分旧稿原文与本稿位置 |
| V0.3 | 已完成 | 历史问题按规则结构化；字符串召回命中后，有密钥时由模型确认是否同一条问题；确认失败则不写复发批注 |
| V0.4 | 已完成 | Pi 对主张-证据做多步取证，证据不足不批；历史复发改由 Pi 判定，Python 只召回和校验。无密钥跳过取证，历史仍用字符串。不是四类 B 审完，也不是语义历史召回 |
| V0.5 | 已完成入口 | 真实模型金标：工具轨迹、评分器、`thesis-review eval`。默认 pytest 仍是 faux。live 结果取决于本机模型，不进 CI |

已知限制：中英文混排时正文字数检查会偏短；无密钥时，标题原文没改仍可能把标题下的内容问题当成复发；过短的老师批注仍不会进入字符串召回；主张-证据取证在未配置密钥时不会运行。有密钥时默认自动化测试走预定工具路径，证明链路能跑；真实模型是否会取证见 [docs/eval-protocol.md](docs/eval-protocol.md)，未跑过或未通过前不把论证审查写成已验证。Pi 调用失败时格式规则仍离线可用，历史复发改为不写，避免把未确认的字符串命中当成再次犯错。

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

本机密钥下的真实模型金标（会调用云端模型，结果写在 `artifacts/eval/`，不进 git）：

```bash
python -m thesis_review.cli eval --out artifacts/eval
```

说明见 [docs/eval-protocol.md](docs/eval-protocol.md)。密钥来自窗口「模型设置」或环境变量，stdout 不会打印密钥或原文。

CLI 只供开发和测试。老师入口是窗口或 EXE。

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| [docs/requirements.md](docs/requirements.md) | 已确认需求、第一版范围与验收方式 |
| [docs/dalian-finance-2026.md](docs/dalian-finance-2026.md) | 大连财经 2026 届可自动抽查的格式条款摘要 |
| [docs/open-source-plan.md](docs/open-source-plan.md) | 开源选型、许可与取舍 |
| [docs/eval-protocol.md](docs/eval-protocol.md) | 真实模型金标怎么跑、期望与真稿约定 |
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

本机已用 Microsoft Word 打开过审改副本并读到助手批注；学校条款抽查与授权真稿对照也做过。V0.5 提供带密钥的金标入口；是否通过取决于本机模型，结果留在 `artifacts/`。仍未完成：全文排版验收、live eval 通过后的其余论证类型与语义历史召回。授权真稿和学校文件全文不进本仓库。

## 还不做

全文代写、自动评分、创新性判定、学生画像、在线 Word 编辑器、多模型裁决、把一次局部修订升成全校规则。

## 许可与贡献

原创文档、探针和原型代码采用 [MIT](LICENSE)。外部项目保留自己的许可，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。请只提交模拟或已获授权的脱敏样例；真实学生论文、教师批注、模型密钥和私人历史记录应留在本地。
