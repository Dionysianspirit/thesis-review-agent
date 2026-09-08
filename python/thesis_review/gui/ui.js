const $ = (id) => document.getElementById(id);

function log(message, cls) {
  const node = $("log");
  node.textContent = message;
  node.className = cls || "";
}

async function api(name, ...args) {
  return window.pywebview.api[name](...args);
}

async function refresh() {
  const state = await api("state");
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
  if (state.status) log(state.status);
}

function renderIssues(issues) {
  const box = $("issues");
  box.innerHTML = "";
  if (!issues.length) {
    box.className = "issues empty";
    box.textContent = "还没有历史问题。";
    return;
  }
  box.className = "issues";
  for (const item of issues) {
    const label = document.createElement("label");
    label.className = "issue";
    const checked = item.status === "confirmed" ? "checked" : "";
    label.innerHTML = `
      <input type="checkbox" data-id="${item.id}" ${checked}>
      <div>
        <strong>${item.original_text}</strong>
        <span>原文：「${item.original_span || "无定位"}」 · ${item.status}</span>
      </div>`;
    box.appendChild(label);
  }
  box.querySelectorAll("input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", async () => {
      await api("set_issue", input.dataset.id, input.checked);
      await refresh();
    });
  });
}

$("btn-save-identity").addEventListener("click", async () => {
  await api("save_identity", {
    teacher_name: $("teacher-name").value,
    student_id: $("student-id").value,
    major: $("major").value,
  });
  log("已保存老师与学生身份。", "ok");
});

$("btn-ingest").addEventListener("click", async () => {
  log("正在选择历史稿…");
  const result = await api("ingest_files");
  log(result.message, result.ok ? "ok" : "err");
  await refresh();
});

$("btn-demo").addEventListener("click", async () => {
  log("正在载入演示稿…");
  const result = await api("load_demo");
  log(result.message, result.ok ? "ok" : "err");
  await refresh();
});

$("btn-review").addEventListener("click", async () => {
  log("正在审查，请稍候…");
  const result = await api("review_file");
  log(result.message, result.ok ? "ok" : "err");
  await refresh();
});

$("btn-open-doc").addEventListener("click", () => api("open_reviewed"));
$("btn-open-folder").addEventListener("click", () => api("open_folder"));
$("btn-settings").addEventListener("click", () => $("settings-modal").classList.remove("hidden"));
$("btn-close-settings").addEventListener("click", () => $("settings-modal").classList.add("hidden"));
$("btn-save-settings").addEventListener("click", async () => {
  await api("save_model", {
    provider: $("provider").value,
    model: $("model").value,
    base_url: $("base-url").value,
    api_key: $("api-key").value,
  });
  $("settings-modal").classList.add("hidden");
  log("已保存模型设置。密钥只留在本机。", "ok");
});

window.addEventListener("pywebviewready", refresh);
