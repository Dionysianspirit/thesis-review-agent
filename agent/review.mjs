import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

import { Agent } from "@earendil-works/pi-agent-core";
import {
  Type,
  createModels,
  createProvider,
  envApiKeyAuth,
  fauxAssistantMessage,
  fauxProvider,
  fauxToolCall,
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { anthropicProvider } from "@earendil-works/pi-ai/providers/anthropic";
import { openaiProvider } from "@earendil-works/pi-ai/providers/openai";

const here = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const out = { selftest: false, faux: false, request: null };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--selftest") out.selftest = true;
    else if (argv[i] === "--faux") out.faux = true;
    else if (argv[i] === "--request") out.request = argv[++i];
  }
  return out;
}

function waitForPortfile(file, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (existsSync(file)) {
        const text = readFileSync(file, "utf8").trim();
        if (text) {
          clearInterval(timer);
          resolve(Number(text));
          return;
        }
      }
      if (Date.now() - started > timeoutMs) {
        clearInterval(timer);
        reject(new Error("worker portfile timeout"));
      }
    }, 50);
  });
}

async function startWorker(cfg) {
  const args = [
    ...(cfg.worker_args || [
      "-m",
      "thesis_review.worker",
      "--home",
      cfg.home,
      "--teacher",
      cfg.teacher_id,
      "--student",
      cfg.student_id,
      "--major",
      cfg.major || "人工智能",
    ]),
    "--portfile",
    path.join(cfg.output_dir, "worker.port"),
  ];
  const child = spawn(cfg.python, args, {
    env: {
      ...process.env,
      PYTHONPATH: cfg.pythonpath,
      PYTHONIOENCODING: "utf-8",
      THESIS_REVIEW_ROOT: process.env.THESIS_REVIEW_ROOT || "",
    },
    stdio: ["ignore", "ignore", "pipe"],
    windowsHide: true,
  });
  let stderr = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const port = await waitForPortfile(path.join(cfg.output_dir, "worker.port"));
  const socket = net.createConnection({ host: "127.0.0.1", port });
  await new Promise((resolve, reject) => {
    const onError = (error) => reject(error);
    socket.once("connect", () => {
      socket.off("error", onError);
      resolve();
    });
    socket.once("error", onError);
  });
  const pending = new Map();
  const rl = readline.createInterface({ input: socket });
  rl.on("error", () => {});
  socket.on("error", () => {});
  rl.on("line", (line) => {
    if (!line.trim()) return;
    const message = JSON.parse(line);
    const waiter = pending.get(String(message.id));
    if (waiter) {
      pending.delete(String(message.id));
      if (message.error) waiter.reject(new Error(message.error.message));
      else waiter.resolve(message.result);
    }
  });
  let nextId = 0;
  async function call(op, params = {}) {
    const id = String(++nextId);
    const result = new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
    });
    socket.write(`${JSON.stringify({ id, op, params })}\n`);
    return result;
  }
  return { call, child, socket, stderr: () => stderr };
}

const HOUSEKEEPING_PROMPT = [
  "你是本科毕业论文 Word 审改助手的第一阶段。",
  "必须先 open_draft，再 run_checks，再 get_history_candidates。",
  "对每条候选自行判断是不是同一条历史问题仍未改正。",
  "只有判定复犯、且能给出本稿中真实存在的原文时，才调用 confirm_history_finding。",
  "不确定，或标题未改但所批内容已经修好，则跳过，不要 confirm。",
  "没有 confirm_history_finding 成功返回的 issue_id，禁止使用「再次」「屡次」。",
  "不要审查论证，不要列出全文，不要 commit_review。",
  "批注作者为审改助手。不要整段重写。",
].join("");

const CLAIM_EVIDENCE_PROMPT = [
  "你是本科毕业论文审改助手的第二阶段。目标只有一项：关键主张是否被实验或数据支持。",
  "先 list_outline，再按疑点 read_section 或 read_paragraphs。禁止为了省事列出全文。",
  "对「显著」「提高」「有效」等主张，必须去实验或结果里核对，并主动找反证（有无基线、有无显著性、提升是否配得上用词）。",
  "证据不够或无法判断时，不要调用 record_argument_finding。",
  "写批注必须同时给出稿件中真实存在的主张原文和证据或反证原文。",
  "最多形成 3 条 finding，然后必须 commit_review。",
  "不要审格式，不要当历史复查，不要使用「再次」「屡次」。",
  "不要用修订改论证。",
].join("");

const OVERCLAIM_CLAIM = "实验结果表明该方法显著提升了分类准确率。";
const OVERCLAIM_EVIDENCE = "准确率由 0.81 提高到 0.83。";

function makeTool(call, name, label, description, parameters, extra = {}) {
  return {
    name,
    label,
    description,
    parameters,
    executionMode: extra.executionMode || "sequential",
    async execute(_toolCallId, params) {
      const result = await call(name, params);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: result,
        terminate: Boolean(extra.terminate),
      };
    },
  };
}

function allTools(call) {
  return [
    makeTool(call, "open_draft", "打开稿件", "打开待审的 Word 稿件。", Type.Object({
      path: Type.Optional(Type.String()),
      bytes_b64: Type.Optional(Type.String()),
    })),
    makeTool(call, "run_checks", "规则检查", "运行格式和语言规则，并写入批注修订。", Type.Object({
      draft_id: Type.Optional(Type.String()),
    })),
    makeTool(call, "get_history_candidates", "历史候选", "用字符串召回教师已确认的历史问题候选，只返回原文片段，不写批注。", Type.Object({
      draft_id: Type.Optional(Type.String()),
    })),
    makeTool(call, "confirm_history_finding", "确认复发", "判定同一问题仍未改正后，校验 new_quote 为本稿子串才写历史批注。不要编造原文。", Type.Object({
      issue_id: Type.String(),
      new_quote: Type.String(),
      rationale: Type.Optional(Type.String()),
      draft_id: Type.Optional(Type.String()),
    })),
    makeTool(call, "list_outline", "列出大纲", "列出标题性段落的序号、锚点和短文本，供导航。不是全文。", Type.Object({})),
    makeTool(call, "read_section", "阅读章节", "从指定段落读到下一标题，最多 8 段或有限字数。", Type.Object({
      start_ordinal: Type.Number(),
      limit: Type.Optional(Type.Number()),
    })),
    makeTool(call, "read_paragraphs", "阅读段落", "从指定序号起读取有限段落，最多 8 段。", Type.Object({
      start_ordinal: Type.Number(),
      limit: Type.Optional(Type.Number()),
    })),
    makeTool(call, "find_text", "检索原文", "在正文中查找短词，返回少量命中上下文。", Type.Object({
      needle: Type.String(),
      max_hits: Type.Optional(Type.Number()),
    })),
    makeTool(call, "record_argument_finding", "记录论证缺口", "主张原文和证据原文都必须是稿件中的真实子串，校验通过后才写批注。不要编造原文。", Type.Object({
      claim_quote: Type.String(),
      evidence_quote: Type.String(),
      problem: Type.String(),
      rationale: Type.String(),
      draft_id: Type.Optional(Type.String()),
    })),
    makeTool(call, "commit_review", "提交审改", "导出带批注修订的 Word 副本。完成后不要再调用其他工具。", Type.Object({
      draft_id: Type.Optional(Type.String()),
      output_dir: Type.String(),
    }), { terminate: true }),
  ];
}

function toolsNamed(call, names) {
  const wanted = new Set(names);
  return allTools(call).filter((tool) => wanted.has(tool.name));
}

function housekeepingTools(call) {
  return toolsNamed(call, ["open_draft", "run_checks", "get_history_candidates", "confirm_history_finding"]);
}

function claimTools(call) {
  return toolsNamed(call, [
    "list_outline",
    "read_section",
    "read_paragraphs",
    "find_text",
    "record_argument_finding",
    "commit_review",
  ]);
}

function compatibleProvider(cfg) {
  const modelId = cfg.model || "gpt-4o-mini";
  const baseUrl = (cfg.base_url || "https://api.openai.com/v1").replace(/\/$/, "");
  const model = {
    id: modelId,
    name: modelId,
    api: "openai-completions",
    provider: "openai-compatible",
    baseUrl,
    reasoning: false,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128000,
    maxTokens: 8192,
  };
  return {
    provider: createProvider({
      id: "openai-compatible",
      name: "OpenAI Compatible",
      baseUrl,
      auth: { apiKey: envApiKeyAuth("API key", ["THESIS_API_KEY", "OPENAI_API_KEY"]) },
      models: [model],
      api: openAICompletionsApi(),
    }),
    model,
  };
}

function convertToLlm(messages) {
  return messages.filter((message) => message.role === "user" || message.role === "assistant" || message.role === "toolResult");
}

function parseToolJson(message) {
  if (!message || message.role !== "toolResult") return null;
  const text = (message.content || []).map((part) => part.text || "").join("");
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function lastToolJson(context) {
  const messages = context.messages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const parsed = parseToolJson(messages[i]);
    if (parsed) return parsed;
  }
  return {};
}

function findOutlineJson(context) {
  const messages = context.messages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const parsed = parseToolJson(messages[i]);
    if (parsed && Array.isArray(parsed.outline)) return parsed;
  }
  return lastToolJson(context);
}

function headingOrdinal(outline, keyword) {
  const items = outline?.outline || [];
  const hit = items.find((item) => String(item.text || "").includes(keyword));
  return hit ? hit.ordinal : 1;
}

async function runClaimEvidencePhase(agent, call, cfg) {
  agent.state.systemPrompt = CLAIM_EVIDENCE_PROMPT;
  agent.state.tools = claimTools(call);
  await agent.prompt(
    `对已打开的稿件核对关键主张是否被实验或数据支持。draft_id=${cfg.draft_id}，output_dir=${cfg.output_dir}。完成后调用 commit_review。`,
  );
}

async function runLive(cfg, call) {
  const models = createModels();
  let model;
  if (cfg.provider === "anthropic") {
    models.setProvider(anthropicProvider());
    model = models.getModel("anthropic", cfg.model);
  } else if (cfg.provider === "openai") {
    models.setProvider(openaiProvider());
    model = models.getModel("openai", cfg.model);
  } else {
    const created = compatibleProvider(cfg);
    models.setProvider(created.provider);
    model = created.model;
  }
  if (!model) {
    throw new Error(`找不到模型 ${cfg.provider}/${cfg.model}`);
  }
  const agent = new Agent({
    initialState: {
      systemPrompt: HOUSEKEEPING_PROMPT,
      model,
      tools: housekeepingTools(call),
      thinkingLevel: "off",
    },
    convertToLlm,
    streamFn: models.streamSimple.bind(models),
    getApiKey: () => process.env.THESIS_API_KEY || process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY,
    toolExecution: "sequential",
  });
  await agent.prompt(
    `打开稿件 path=${cfg.draft_path}，draft_id=${cfg.draft_id}。先完成规则检查和历史复查：召回候选后自行判断是否复犯。不要 commit。`,
  );
  await runClaimEvidencePhase(agent, call, cfg);
}

function findCandidatesJson(context) {
  const messages = context.messages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const parsed = parseToolJson(messages[i]);
    if (parsed && Array.isArray(parsed.candidates)) return parsed;
  }
  return { candidates: [] };
}

function repeatCandidate(data) {
  const candidates = data.candidates || [];
  return candidates.find((item) =>
    String(item.original_text || item.problem || "").includes("主观评价")
    || String(item.new_quote || "").includes("非常非常有效"),
  );
}

function fauxHousekeeping(cfg) {
  const scenario = cfg.faux_scenario || "housekeeping";
  const prelude = [
    fauxAssistantMessage([
      fauxToolCall("open_draft", { path: cfg.draft_path }),
    ]),
    fauxAssistantMessage([
      fauxToolCall("run_checks", { draft_id: cfg.draft_id }),
    ]),
    fauxAssistantMessage([
      fauxToolCall("get_history_candidates", { draft_id: cfg.draft_id }),
    ]),
  ];
  if (scenario === "skip_history") {
    return [
      ...prelude,
      fauxAssistantMessage("标题未改，所批内容已修好，不写复发。"),
    ];
  }
  if (scenario === "overclaim" || scenario === "abandon") {
    return [
      ...prelude,
      fauxAssistantMessage("没有判定为复犯的历史候选。"),
    ];
  }
  return [
    ...prelude,
    (context) => {
      const hit = repeatCandidate(findCandidatesJson(context));
      if (!hit) {
        return fauxAssistantMessage("没有判定为复犯的历史候选。");
      }
      return fauxAssistantMessage([
        fauxToolCall("confirm_history_finding", {
          issue_id: hit.issue_id,
          new_quote: hit.new_quote,
          rationale: "仍是无依据的主观评价。",
          draft_id: cfg.draft_id,
        }),
      ]);
    },
    fauxAssistantMessage("规则与历史复查已完成。"),
  ];
}

function fauxClaimPhase(cfg) {
  const scenario = cfg.faux_scenario || "housekeeping";
  const commit = fauxAssistantMessage([
    fauxToolCall("commit_review", { draft_id: cfg.draft_id, output_dir: cfg.output_dir }),
  ]);
  if (scenario === "overclaim") {
    return [
      fauxAssistantMessage([fauxToolCall("list_outline", {})]),
      (context) => fauxAssistantMessage([
        fauxToolCall("read_section", { start_ordinal: headingOrdinal(lastToolJson(context), "4 结论") }),
      ]),
      (context) => fauxAssistantMessage([
        fauxToolCall("read_section", { start_ordinal: headingOrdinal(findOutlineJson(context), "3 实验结果") }),
      ]),
      fauxAssistantMessage([
        fauxToolCall("record_argument_finding", {
          claim_quote: OVERCLAIM_CLAIM,
          evidence_quote: OVERCLAIM_EVIDENCE,
          problem: "结论用词过满，实验结果仅有微弱数值变化。",
          rationale: "未见显著性检验，提升幅度与「显著提升」不符。",
          draft_id: cfg.draft_id,
        }),
      ]),
      commit,
      fauxAssistantMessage("已提交审改副本。"),
    ];
  }
  if (scenario === "abandon") {
    return [
      fauxAssistantMessage([fauxToolCall("list_outline", {})]),
      (context) => fauxAssistantMessage([
        fauxToolCall("read_section", { start_ordinal: headingOrdinal(lastToolJson(context), "4 结论") }),
      ]),
      (context) => fauxAssistantMessage([
        fauxToolCall("read_section", { start_ordinal: headingOrdinal(findOutlineJson(context), "3 实验结果") }),
      ]),
      commit,
      fauxAssistantMessage("证据充分，不写论证批注。已提交审改副本。"),
    ];
  }
  return [
    commit,
    fauxAssistantMessage("已提交审改副本。"),
  ];
}

async function runFaux(cfg, call) {
  const faux = fauxProvider({ models: [{ id: "faux-review" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([...fauxHousekeeping(cfg), ...fauxClaimPhase(cfg)]);
  const agent = new Agent({
    initialState: {
      systemPrompt: HOUSEKEEPING_PROMPT,
      model: faux.getModel(),
      tools: housekeepingTools(call),
      thinkingLevel: "off",
    },
    convertToLlm,
    streamFn: models.streamSimple.bind(models),
    toolExecution: "sequential",
  });
  await agent.prompt("开始审查。先完成规则检查和历史复查。");
  await runClaimEvidencePhase(agent, call, cfg);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selftest) {
    if (!Agent || !createModels || !Type) throw new Error("pi imports missing");
    process.stdout.write("pi-ok\n");
    return;
  }
  if (!args.request) throw new Error("missing --request");
  const cfg = JSON.parse(readFileSync(args.request, "utf8"));
  const worker = await startWorker(cfg);
  try {
    if (args.faux) await runFaux(cfg, worker.call);
    else await runLive(cfg, worker.call);
    const committed = {
      ok: true,
      reviewed_path: path.join(cfg.output_dir, `${cfg.draft_id}-reviewed.docx`),
      findings_path: path.join(cfg.output_dir, `${cfg.draft_id}-findings.json`),
    };
    process.stdout.write(`${JSON.stringify(committed)}\n`);
  } catch (error) {
    process.stderr.write(`${worker.stderr()}\n`);
    throw error;
  } finally {
    worker.socket.end();
    worker.child.kill();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
