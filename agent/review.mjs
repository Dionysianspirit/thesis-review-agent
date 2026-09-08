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
    socket.once("connect", resolve);
    socket.once("error", reject);
  });
  const pending = new Map();
  const rl = readline.createInterface({ input: socket });
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

function tools(call) {
  return [
    makeTool(call, "open_draft", "打开稿件", "打开待审的 Word 稿件。", Type.Object({
      path: Type.Optional(Type.String()),
      bytes_b64: Type.Optional(Type.String()),
    })),
    makeTool(call, "list_paragraphs", "列出段落", "列出正文段落和定位锚点。", Type.Object({})),
    makeTool(call, "run_checks", "规则检查", "运行格式和语言规则，并写入批注修订。", Type.Object({
      draft_id: Type.Optional(Type.String()),
    })),
    makeTool(call, "search_history", "历史复查", "匹配教师已确认的历史问题并写批注。", Type.Object({
      draft_id: Type.Optional(Type.String()),
    })),
    makeTool(call, "add_comment", "添加批注", "在指定锚点添加助手批注。", Type.Object({
      anchor: Type.String(),
      text: Type.String(),
      author: Type.Optional(Type.String()),
    })),
    makeTool(call, "replace_tracked", "修订替换", "按修订记录替换原文。", Type.Object({
      anchor: Type.String(),
      old: Type.String(),
      new: Type.String(),
      author: Type.Optional(Type.String()),
    })),
    makeTool(call, "commit_review", "提交审改", "导出带批注修订的 Word 副本。完成后不要再调用其他工具。", Type.Object({
      draft_id: Type.Optional(Type.String()),
      output_dir: Type.String(),
    }), { terminate: true }),
  ];
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
      systemPrompt: [
        "你是本科毕业论文 Word 审改助手。",
        "必须先 open_draft，再 run_checks，再 search_history，最后 commit_review。",
        "没有 search_history 返回的 issue_id，禁止使用「再次」「屡次」。",
        "批注作者为审改助手。不要整段重写。",
      ].join(""),
      model,
      tools: tools(call),
      thinkingLevel: "off",
    },
    convertToLlm,
    streamFn: models.streamSimple.bind(models),
    getApiKey: () => process.env.THESIS_API_KEY || process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY,
    toolExecution: "sequential",
  });
  await agent.prompt(
    `打开稿件 path=${cfg.draft_path}，draft_id=${cfg.draft_id}，output_dir=${cfg.output_dir}。完成后调用 commit_review。`,
  );
}

async function runFaux(cfg, call) {
  const faux = fauxProvider({ models: [{ id: "faux-review" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([
    fauxAssistantMessage([
      fauxToolCall("open_draft", { path: cfg.draft_path }),
    ]),
    fauxAssistantMessage([
      fauxToolCall("run_checks", { draft_id: cfg.draft_id }),
      fauxToolCall("search_history", { draft_id: cfg.draft_id }),
    ]),
    fauxAssistantMessage([
      fauxToolCall("commit_review", { draft_id: cfg.draft_id, output_dir: cfg.output_dir }),
    ]),
    fauxAssistantMessage("已提交审改副本。"),
  ]);
  const agent = new Agent({
    initialState: {
      systemPrompt: "按工具结果完成论文审改。",
      model: faux.getModel(),
      tools: tools(call),
      thinkingLevel: "off",
    },
    convertToLlm,
    streamFn: models.streamSimple.bind(models),
    toolExecution: "sequential",
  });
  await agent.prompt("开始审查。");
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
  } finally {
    worker.socket.end();
    worker.child.kill();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
