# 本科论文审改 Agent 开源选型与技术验证

核查日期：2026 年 9 月 8 日。面向大数据、人工智能相关本科毕业论文；输入与交付采用 Word DOCX；老师主要使用批注、修订，每名学生固定对应一位老师。核心需求是依据历史指导意见识别学生重复出现的问题，先覆盖格式规范和语言表达，再扩展论证结构。

**结论：可以基于 pi 开发，但适合按能力组合，不能把多个完整平台直接拼在一起。**建议用 pi 的 agent core 和模型接入层，配可替换的 Word 文档适配层、按老师与学生隔离的历史问题记录，以及可配置检查规则。此次完成公开项目检索、许可证核对、源码抽查和一个 Word 引擎的运行验证，尚未完成 pi 与模型、Word 工具的端到端集成。

## 候选项目与取舍

以下能力描述来自项目文档；只有 DocxEngine 做了本次列明的运行验证。许可证按仓库文件核查，具体复用时仍须保留适用声明。

| 项目 | 许可证 | 可参考或复用部分 | 本项目的取舍 |
| --- | --- | --- | --- |
| [Pi](https://github.com/earendil-works/pi) | MIT | 多模型接入、工具执行、agent 状态与事件 | 执行底座候选。优先嵌入 agent core，不需要把整个编码 CLI 改成论文产品 |
| [DocxEngine](https://github.com/ruwadgroup/docxengine) | Apache-2.0 | 原文定位校验、批注、修订、文档结构校验 | 轻量实验候选，核心声明无运行依赖。但标为 Alpha，本次发现失败操作会修改内存的缺陷，不能直接作为正式依赖 |
| [docxreview](https://github.com/SchmidtPaul/docxreview) | MIT；DESCRIPTION 与 LICENSE.md 确认 | 提取批注、作者、日期、被批注文本、段落上下文及修订 | 很贴近历史意见提取需求。参考字段和处理流程；它是实验性 R 包，暂不为它新增整套 R 运行环境 |
| [docx-mcp](https://github.com/SecurityRonin/docx-mcp) | MIT | Word 批注、修订、样式检查等工具 | 备选文档实现。当前必需依赖含 Presidio、spaCy，工具范围很广；第一版只需要少量操作，不整套接入 |
| [Agentic Paper Review](https://github.com/ngstcf/agentic-paper-review) | MIT | 可配置审查标准、逐项提取证据与原文、人工核对 | 参考审查标准和证据结构。它主要输出 Markdown、CSV；读取 DOCX 不等于能保留排版并写回 Word 批注。暂不复制多模型评分与裁决流程 |
| [Mem0](https://github.com/mem0ai/mem0) | Apache-2.0 | 按用户组织、提取和检索长期记忆 | 参考历史检索设计，暂缓作为依赖。聊天记忆不能直接替代带稿件来源的教师指导记录 |
| [SuperDoc](https://github.com/superdoc/docx-editor) | AGPLv3；另提供商业许可 | 浏览器内 DOCX 编辑、批注修订及 agent 文档 API | 如果以后需要在线审改，再评估。老师目前使用 Word，第一版上传下载即可；AGPL 许可方案也需单独评估 |
| [Supervisor-Skills](https://github.com/HKUSTDial/Supervisor-Skills) | CC BY-NC-SA 4.0 | 学术写作、投稿前检查等方法材料 | 作为另行评估的方法参考。当前许可带非商业与相同方式共享条件，不作为可随意混入 MIT/Apache 产品的代码或提示词来源 |

Pi 原仓库地址 badlogic/pi-mono 当前重定向到 earendil-works/pi；接入应以核实后的包名和固定版本为准。官方当前 agent core 包名为 `@earendil-works/pi-agent-core`，模型层为 `@earendil-works/pi-ai`。代码开源并不代表所调用的模型服务免费。

## 推荐的组合方式

`Word 稿件 → 文档适配层 → 带定位的正文与老师意见 → pi 调用检查和历史检索工具 → 待核对建议 → 文档适配层 → 带批注与修订的 Word 副本`

**执行层。**pi 负责调用工具和组织模型过程。只暴露论文读取、历史问题检索、检查和生成审改副本所需的工具。官方说明 pi 本身没有文件、进程和网络访问的完整内置权限隔离，应用仍需限制工具可访问的目录与记录范围。

**文档层。**保留 DOCX 包及原始定位；供模型阅读的纯文本是派生视图，不作为重建原文件的唯一来源。原文定位至少绑定稿件版本、段落和文本校验值。批注与修订写入副本，显式开启修订并标明助手身份。失败则丢弃临时结果；成功并校验后，才提交新版本。同一文档的写入顺序执行。

**历史层。**先保存可核对的问题记录：老师、学生、专业、稿件版本、原批注或修订、对应原文、上下文、问题类别、教师确认状态、当前是否适用。新稿命中时同时呈现旧稿依据和新稿位置。自动归纳先是候选，不能把一次局部修订提升为所有论文通用的要求。第一版可以用本地轻量存储进行实验；正式持久化、多人访问和部署方案尚未锁定。

**审查层。**参考 Agentic Paper Review 的标准配置和证据提取形式，输出“位置、问题、依据、解释、建议改法”。学校规范有明确条款的项目采用确定性检查；语言与论证建议由模型辅助判断。不要把本科论文直接套入顶会审稿分数或创新性门槛。

## 已完成的运行验证

测试对象是 DocxEngine 提交 `c4ca7ce5f540ef2e638fbf79cc5f7074702b2967`，项目版本声明 `1.0.0`，开发状态标为 Alpha。本次在任务工作目录保存固定源码及许可证，未全局安装或启动其 MCP 服务。

**上游选定测试：130 通过，5 跳过。**覆盖批注、修订、编辑、定位、结构校验与异常输入。5 项跳过原因均为 `conformance corpus not present`，涉及按作者接受修订、拒绝全部修订、跨 run 替换、修订替换和段落差异，不能计作通过。

**另做中文 DOCX 内存集成样例。**用独立的 python-docx 1.2.0 创建包含中文分段文字、老师批注、页眉、表格的样例，再使用候选引擎读写，并重新解析。验证结果如下：

- 可提取已有中文老师批注。
- 可跨不同 run 替换中文文字并记录修订。
- 新增助手批注与修订时，测试中的老师原有修订、批注内容保留。
- 测试中的页眉字节与表格 XML 保持一致，粗体标记仍存在。
- 导出内容可以由 python-docx 独立解析。
- 可单独拒绝助手修订，恢复测试句子，同时保留老师修订。
- 临时副本操作失败时，上一次已提交文档字节保持不变。

结构校验为 valid，仍有一条关于 `stylesWithEffects` 关系未被引用的 warning，原样记录在验证 JSON 中；这不是完整 OOXML 标准验证，也不是 Word 排版验收。

**发现的真实缺陷。**给批注传入过期定位，接口抛出 `anchor_stale`，但 `word/comments.xml` 已经追加内容。源码 `_comments.py` 的 `_add` 先追加批注，再调用 `_wire_document` 校验并连接原文，解释了失败后的内存变化。此次复现了该问题，没有修改上游代码，也没有向维护者发送消息。

接入层以“在隔离副本上执行，成功后导出并提交”为边界，可以保住上次成功结果；本次已验证这个边界。它不能证明整个引擎不存在其他问题。相关源码：[固定提交中的批注实现](https://github.com/ruwadgroup/docxengine/blob/c4ca7ce5f540ef2e638fbf79cc5f7074702b2967/src/docxengine/_comments.py#L193)。

## 下一步原型范围

1. 保持 Word 引擎可替换，封装最少的读取、提取意见、定位、批注、修订、校验和副本输出能力；加入已复现缺陷的失败隔离检查。
2. 对接 pi 的自定义工具接口。可以直接调用受控的 Python 文档进程，不必为了接入强行引入完整 MCP 工具集。先测调用与错误返回，再接真实模型。
3. 用模拟或脱敏记录跑通“同一学生历史问题 → 新稿复查 → 带依据的 Word 批注”。明确区分预置样例规则与模型真实判断，不能把关键词匹配演示称为语义记忆能力。
4. 老师材料到位后，接入当年规范与真实历史批注，用未参与调试的稿件验证有效建议比例、重复问题识别质量和审改总耗时。

2026-09-08 当日选型结论仍有效。之后原型已做到：Word 适配层隔离写入、老师窗口与内置 pi、大连财经 2026 格式抽查、历史字符串匹配收紧（V0.2），以及用 Word 打开审改副本核对批注。仍未完成：全文排版验收、语义级复发确认（V0.3）、带密钥的模型审改质量、正式部署与预算控制。授权真稿不进本仓库。

## 证据与版本快照

详细机器可读结果见 `../evidence/oss-validation.json`。本仓库 `scripts/` 提供固定版本下载和复现入口。

| 项目 | 核查的默认分支提交 |
| --- | --- |
| Pi | `b2602be77cb7b0de45dd616407fd210daa48aa75` |
| DocxEngine | `c4ca7ce5f540ef2e638fbf79cc5f7074702b2967` |
| docxreview | `f67b43cb2339f6e59d199de91ffb9c0e77b52743` |
| docx-mcp | `9c0c0b7694d8123e82fe6b7c480899890dca0695` |
| Agentic Paper Review | `c117aba2dbb26fece9ab2de12b84c1874fa63e6f` |
| Mem0 | `dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3` |
| SuperDoc | `7dcf2395f24c297ef055b081330f5558ab5c2e55` |
| Supervisor-Skills | `207bc6f7a1aa107e544099c2c7cc86816fba9628` |

许可证和能力一手来源：[Pi LICENSE](https://github.com/earendil-works/pi/blob/b2602be77cb7b0de45dd616407fd210daa48aa75/LICENSE)、[Pi agent README](https://raw.githubusercontent.com/earendil-works/pi/main/packages/agent/README.md)、[DocxEngine pyproject](https://github.com/ruwadgroup/docxengine/blob/c4ca7ce5f540ef2e638fbf79cc5f7074702b2967/pyproject.toml)、[docxreview README](https://raw.githubusercontent.com/SchmidtPaul/docxreview/master/README.md)、[docxreview LICENSE](https://github.com/SchmidtPaul/docxreview/blob/f67b43cb2339f6e59d199de91ffb9c0e77b52743/LICENSE.md)、[docx-mcp pyproject](https://github.com/SecurityRonin/docx-mcp/blob/9c0c0b7694d8123e82fe6b7c480899890dca0695/pyproject.toml)、[Agentic Paper Review README](https://raw.githubusercontent.com/ngstcf/agentic-paper-review/main/README.md)、[Mem0 README](https://raw.githubusercontent.com/mem0ai/mem0/main/README.md)、[SuperDoc README](https://raw.githubusercontent.com/superdoc/docx-editor/main/README.md)、[Supervisor-Skills LICENSE](https://raw.githubusercontent.com/HKUSTDial/Supervisor-Skills/main/LICENSE)。
