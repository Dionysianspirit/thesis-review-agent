const $ = (id) => document.getElementById(id);

const hasBridge = () => Boolean(window.pywebview && window.pywebview.api);

async function api(name, ...args) {
  return window.pywebview.api[name](...args);
}

function log(message, cls) {
  const node = $("log");
  node.textContent = message;
  node.className = "log mono" + (cls ? " " + cls : "");
}

function setStatus(text, state) {
  $("status-text").textContent = text;
  $("status-dot").className = "status-dot " + (state || "idle");
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* ---------- grouping ---------- */

const GROUPS = {
  language: { label: "语言规则", chip: "A · 语言规则", cls: "" },
  format: { label: "格式规则", chip: "C · 格式规则", cls: "" },
  history: { label: "历史复犯", chip: "D · 历史复犯", cls: "chip-history" },
  argument: { label: "论证取证", chip: "B · 论证取证", cls: "chip-argument" },
};

function groupOf(finding) {
  if (finding.source === "history") return "history";
  if (finding.source === "argument") return "argument";
  return finding.category === "C" ? "format" : "language";
}

const APPLY_LABELS = { comment: "批注", revision: "修订", both: "批注 + 修订" };

const EVIDENCE_LABELS = {
  history: "历次批注",
  history_span: "旧稿原文",
  claim: "主张原文",
  evidence: "对照证据",
};

/* ---------- issues (step 2) ---------- */

const STATUS_LABELS = { candidate: "待确认", confirmed: "已确认", disabled: "已停用" };

function renderIssues(issues) {
  const box = $("issues");
  box.innerHTML = "";
  if (!issues.length) {
    box.className = "issues empty";
    box.textContent = "还没有历史问题。先导入历史稿，或载入演示稿。";
    return;
  }
  box.className = "issues";
  for (const item of issues) {
    const label = document.createElement("label");
    label.className = "issue";
    const checked = item.status === "confirmed" ? "checked" : "";
    const statusCls = item.status === "confirmed" ? "confirmed" : item.status === "disabled" ? "disabled" : "";
    const title = item.problem || item.original_text || "（无摘要）";
    const kind = item.issue_type || item.category || "";
    const scope = item.scope ? ` · ${item.scope}` : "";
    const span = item.original_span ? ` · 原文：「${item.original_span}」` : "";
    const intent = item.teacher_intent || item.original_text || "";
    label.innerHTML = `
      <input type="checkbox" data-id="${esc(item.id)}" ${checked}>
      <div class="issue-body">
        <span class="issue-title">${esc(title)}<span class="issue-status ${statusCls}">${esc(STATUS_LABELS[item.status] || item.status)}</span></span>
        <span class="issue-meta">${esc(kind)}${esc(scope)}${esc(span)}</span>
        <span class="issue-intent">${esc(intent)}</span>
      </div>`;
    box.appendChild(label);
  }
  box.querySelectorAll("input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", async () => {
      if (!hasBridge()) return;
      await api("set_issue", input.dataset.id, input.checked);
      await refresh();
    });
  });
}

/* ---------- findings (results layer) ---------- */

let lastFindings = [];
let lastRecall = { confirmed: 0, recalled: 0, written: 0, skipped: [], absent: [] };
let activeTab = "all";

function findingCard(finding) {
  const group = groupOf(finding);
  const meta = GROUPS[group];
  const apply = APPLY_LABELS[finding.apply] || "批注";
  const loc = finding.paragraph_index
    ? `第 ${finding.paragraph_index} 段 · ${finding.anchor || ""}`
    : (finding.anchor || "");
  const quote = finding.quote
    ? `<blockquote class="quote">「${esc(finding.quote)}」</blockquote>`
    : "";
  const evidence = (finding.evidence || [])
    .map((item) => {
      const kind = EVIDENCE_LABELS[item.kind] || item.kind || "依据";
      const draft = item.draft_id ? ` · ${item.draft_id}` : "";
      return `<div class="ev-item"><span class="ev-kind">${esc(kind)}${esc(draft)}</span><span>${esc(item.text)}</span></div>`;
    })
    .join("");
  const evidenceBlock = evidence ? `<div class="evidence">${evidence}</div>` : "";
  const suggest = finding.suggested_old && finding.suggested_new
    ? `<div class="suggest">建议将 <span class="old">「${esc(finding.suggested_old)}」</span> 改为 <span class="new">「${esc(finding.suggested_new)}」</span></div>`
    : "";
  return `
    <article class="finding" data-group="${group}">
      <div class="finding-head">
        <span class="chip ${meta.cls}">${meta.chip}</span>
        <span class="loc">${esc(loc)}</span>
        <span class="apply-badge">写入：${esc(apply)}</span>
      </div>
      <h4>${esc(finding.problem)}</h4>
      <p class="rationale">${esc(finding.rationale)}</p>
      ${quote}
      ${evidenceBlock}
      ${suggest}
    </article>`;
}

function skippedCard(item, kindLabel) {
  const quote = item.new_quote
    ? `<blockquote class="quote">本稿召回：「${esc(item.new_quote)}」</blockquote>`
    : "";
  return `
    <article class="finding skipped" data-group="skipped">
      <div class="finding-head">
        <span class="chip chip-skipped">${esc(kindLabel)}</span>
        <span class="loc">历史问题 ${esc(item.issue_id)}</span>
        <span class="apply-badge">未写入</span>
      </div>
      <h4>${esc(item.problem)}</h4>
      <div class="evidence">
        <div class="ev-item"><span class="ev-kind">历次批注</span><span>${esc(item.original_text)}</span></div>
      </div>
      ${quote}
      <p class="skip-reason">${esc(item.reason)}</p>
    </article>`;
}

function renderResults(findings, recall, usedModel, warning) {
  lastFindings = findings || [];
  lastRecall = recall || lastRecall;
  const has = lastFindings.length || (lastRecall.skipped || []).length || (lastRecall.absent || []).length;
  $("results-empty").hidden = Boolean(has);
  $("results").hidden = !has;
  if (!has) return;

  const counts = { language: 0, format: 0, history: 0, argument: 0 };
  for (const f of lastFindings) counts[groupOf(f)] += 1;
  const skippedCount = (lastRecall.skipped || []).length + (lastRecall.absent || []).length;
  $("count-all").textContent = lastFindings.length;
  $("count-language").textContent = counts.language;
  $("count-format").textContent = counts.format;
  $("count-history").textContent = counts.history;
  $("count-argument").textContent = counts.argument;
  $("count-skipped").textContent = skippedCount;

  const badge = $("mode-badge");
  badge.textContent = usedModel ? "模型辅助" : "离线规则";
  badge.className = "mode-badge mono" + (usedModel ? " model" : "");
  $("recall-line").textContent =
    `已确认历史问题 ${lastRecall.confirmed} · 召回 ${lastRecall.recalled} · 写成复犯 ${lastRecall.written}`;

  const banner = $("warning-banner");
  if (warning) {
    banner.textContent = warning;
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }
  renderTab();
}

function renderTab() {
  const box = $("findings");
  const parts = [];
  if (activeTab === "skipped") {
    for (const item of lastRecall.skipped || []) {
      parts.push(skippedCard(item, "召回未确认"));
    }
    for (const item of lastRecall.absent || []) {
      parts.push(skippedCard(item, "本次未命中"));
    }
    if (!parts.length) {
      parts.push(`<div class="card placeholder">没有未写入的条目。召回的历史问题均已确认并写入。</div>`);
    }
  } else {
    const selected = activeTab === "all"
      ? lastFindings
      : lastFindings.filter((f) => groupOf(f) === activeTab);
    if (!selected.length) {
      parts.push(`<div class="card placeholder">该分组下没有命中。</div>`);
    } else {
      for (const f of selected) parts.push(findingCard(f));
    }
  }
  box.innerHTML = parts.join("");
}

$("tabs").addEventListener("click", (event) => {
  const btn = event.target.closest(".tab");
  if (!btn) return;
  activeTab = btn.dataset.tab;
  document.querySelectorAll("#tabs .tab").forEach((tab) => {
    tab.classList.toggle("active", tab === btn);
  });
  renderTab();
});

/* ---------- state sync ---------- */

function applyState(state) {
  $("teacher-name").value = state.teacher_name || "";
  $("student-id").value = state.student_id || "";
  $("major").value = state.major || "";
  $("provider").value = state.provider || "";
  $("model").value = state.model || "";
  $("base-url").value = state.base_url || "";
  $("api-key").value = state.api_key || "";
  renderIssues(state.issues || []);
  $("btn-open-doc").disabled = !state.reviewed_path;
  $("btn-open-folder").disabled = !state.output_dir;
  $("reviewed-path").textContent = state.reviewed_path || "";
  renderResults(state.findings || [], state.recall, state.used_model, state.warning);
  if (state.status) log(state.status);
}

async function refresh() {
  if (!hasBridge()) return;
  applyState(await api("state"));
}

/* ---------- actions ---------- */

$("btn-save-identity").addEventListener("click", async () => {
  if (!hasBridge()) return;
  await api("save_identity", {
    teacher_name: $("teacher-name").value,
    student_id: $("student-id").value,
    major: $("major").value,
  });
  log("已保存老师与学生身份。", "ok");
  setStatus("身份已保存", "done");
});

$("btn-ingest").addEventListener("click", async () => {
  if (!hasBridge()) return;
  setStatus("正在导入历史稿…", "busy");
  const result = await api("ingest_files");
  log(result.message, result.ok ? "ok" : "err");
  setStatus(result.ok ? "历史稿已导入，待确认" : "未导入", result.ok ? "done" : "err");
  await refresh();
});

$("btn-demo").addEventListener("click", async () => {
  if (!hasBridge()) return;
  setStatus("正在载入演示稿…", "busy");
  const result = await api("load_demo");
  log(result.message, result.ok ? "ok" : "err");
  setStatus("演示稿已载入", result.ok ? "done" : "err");
  await refresh();
});

$("btn-review").addEventListener("click", async () => {
  if (!hasBridge()) return;
  const btn = $("btn-review");
  btn.disabled = true;
  setStatus("正在初筛新稿…", "busy");
  log("正在初筛，请稍候。配置密钥时会多步核对主张与证据，耗时更长。");
  const result = await api("review_file");
  log(result.message, result.ok ? "ok" : "err");
  setStatus(result.ok ? "初筛完成" : "初筛未完成", result.ok ? "done" : "err");
  btn.disabled = false;
  await refresh();
  if (result.ok) {
    $("sec-results").scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

$("btn-open-doc").addEventListener("click", () => hasBridge() && api("open_reviewed"));
$("btn-open-folder").addEventListener("click", () => hasBridge() && api("open_folder"));
$("btn-settings").addEventListener("click", () => $("settings-modal").classList.remove("hidden"));
$("btn-close-settings").addEventListener("click", () => $("settings-modal").classList.add("hidden"));
$("settings-modal").addEventListener("click", (event) => {
  if (event.target === $("settings-modal")) $("settings-modal").classList.add("hidden");
});
$("btn-save-settings").addEventListener("click", async () => {
  if (!hasBridge()) return;
  await api("save_model", {
    provider: $("provider").value,
    model: $("model").value,
    base_url: $("base-url").value,
    api_key: $("api-key").value,
  });
  $("settings-modal").classList.add("hidden");
  log("已保存模型设置。密钥只留在本机。", "ok");
});

/* ---------- browser preview fallback (no pywebview) ---------- */

const DEMO_STATE = {
  teacher_name: "老师甲",
  student_id: "zhou",
  major: "人工智能",
  provider: "openai-compatible",
  model: "gpt-4o-mini",
  base_url: "",
  api_key: "",
  reviewed_path: "C:/Users/demo/Documents/论文审改结果/new-reviewed.docx",
  output_dir: "C:/Users/demo/Documents/论文审改结果",
  status: "演示数据：完成，共 4 条建议。",
  used_model: false,
  warning: "",
  issues: [
    {
      id: "i-001",
      status: "confirmed",
      category: "A",
      issue_type: "语言表达",
      scope: "全文",
      problem: "叠词加强语气，属无依据的主观评价",
      original_text: "不要用「非常非常有效」这类叠词主观评价，要有数据支撑。",
      original_span: "非常非常有效",
      teacher_intent: "不要用「非常非常有效」这类叠词主观评价，要有数据支撑。",
    },
    {
      id: "i-002",
      status: "candidate",
      category: "C",
      issue_type: "格式规范",
      scope: "表格",
      problem: "表格缺少题注",
      original_text: "表格上方要有「表 X 标题」格式的题注。",
      original_span: "表 2",
      teacher_intent: "表格上方要有「表 X 标题」格式的题注。",
    },
    {
      id: "i-003",
      status: "confirmed",
      category: "B",
      issue_type: "论证依据",
      scope: "实验章节",
      problem: "结论用词过满，与实验数据不匹配",
      original_text: "「显著提升」需要显著性检验支撑，0.02 的提升配不上这个用词。",
      original_span: "显著提升",
      teacher_intent: "「显著提升」需要显著性检验支撑，0.02 的提升配不上这个用词。",
    },
  ],
  findings: [
    {
      id: "rule-A-1",
      source: "rule",
      category: "A",
      code: "padded_adverb",
      problem: "叠词加强语气，属无依据的主观评价。",
      rationale: "「非常非常」是口语化叠词，学术论文应给出可核验的数据。",
      quote: "该方法非常非常有效。",
      anchor: "P0012",
      paragraph_index: 12,
      apply: "both",
      suggested_old: "非常非常有效",
      suggested_new: "有效",
      evidence: [],
    },
    {
      id: "rule-C-1",
      source: "rule",
      category: "C",
      code: "missing_table_caption",
      problem: "表格缺少题注。",
      rationale: "学校手册要求每个表格上方有「表 X 标题」格式的题注。",
      quote: "",
      anchor: "T0002",
      paragraph_index: 0,
      apply: "comment",
      evidence: [],
    },
    {
      id: "history-i-001",
      source: "history",
      category: "A",
      problem: "学生在新稿中仍出现已确认的历史问题。",
      rationale: "历次稿件已指出：不要用「非常非常有效」这类叠词主观评价，要有数据支撑。",
      quote: "非常非常有效",
      anchor: "P0012",
      paragraph_index: 12,
      apply: "comment",
      issue_id: "i-001",
      evidence: [
        { kind: "history", draft_id: "draft-2", text: "不要用「非常非常有效」这类叠词主观评价，要有数据支撑。" },
        { kind: "history_span", draft_id: "draft-2", text: "非常非常有效" },
      ],
    },
    {
      id: "argument-1",
      source: "argument",
      category: "B",
      code: "claim_without_evidence",
      problem: "结论用词过满，实验结果仅有微弱数值变化。",
      rationale: "未见显著性检验，提升幅度与「显著提升」不符。",
      quote: "实验结果表明该方法显著提升了分类准确率。",
      anchor: "P0041",
      paragraph_index: 41,
      apply: "comment",
      evidence: [
        { kind: "claim", draft_id: "new", text: "实验结果表明该方法显著提升了分类准确率。" },
        { kind: "evidence", draft_id: "new", text: "准确率由 0.81 提高到 0.83。" },
      ],
    },
  ],
  recall: {
    confirmed: 2,
    recalled: 2,
    written: 1,
    skipped: [
      {
        issue_id: "i-003",
        category: "B",
        problem: "结论用词过满，与实验数据不匹配",
        original_text: "「显著提升」需要显著性检验支撑，0.02 的提升配不上这个用词。",
        new_quote: "显著提升了分类准确率",
        reason: "在新稿中召回了相似原文，但未判定为复犯（可能已修复或依据不足），未写入批注。",
      },
    ],
    absent: [],
  },
};

if (!hasBridge()) {
  window.addEventListener("DOMContentLoaded", () => {
    applyState(DEMO_STATE);
    setStatus("浏览器预览 · 演示数据", "idle");
  });
} else {
  window.addEventListener("pywebviewready", () => {
    setStatus("准备就绪", "idle");
    refresh();
  });
}
