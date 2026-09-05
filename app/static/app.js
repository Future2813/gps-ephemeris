// GPS 星历服务前端逻辑
const API = "/api";

// ---------- 工具函数 ----------
async function api(path, options = {}) {
  const resp = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (resp.status === 401) {
    showLogin();
    throw new Error("未登录");
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

function fmtTime(s) {
  if (!s) return "--";
  try {
    const d = new Date(s);
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch { return s; }
}

function fmtSize(b) {
  if (b == null) return "--";
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
  return (b / 1024 / 1024).toFixed(2) + " MB";
}

function statusBadge(status) {
  if (status === "success") return '<span class="badge badge-success">成功</span>';
  if (status === "failed") return '<span class="badge badge-failed">失败</span>';
  return '<span class="badge badge-none">未知</span>';
}

// ---------- 登录 ----------
async function checkAuth() {
  try {
    const data = await api("/me");
    if (data.authenticated) {
      document.getElementById("current-user").textContent = data.username;
      showMain();
      return true;
    }
  } catch {}
  showLogin();
  return false;
}

function showLogin() {
  document.getElementById("login-page").classList.remove("hidden");
  document.getElementById("main-page").classList.add("hidden");
}

function showMain() {
  document.getElementById("login-page").classList.add("hidden");
  document.getElementById("main-page").classList.remove("hidden");
  loadDashboard();
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("login-msg");
  msg.textContent = "";
  try {
    await api("/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
      }),
    });
    await checkAuth();
  } catch (err) {
    msg.textContent = err.message;
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/logout", { method: "POST" });
  showLogin();
});

// ---------- 标签切换 ----------
document.querySelectorAll(".nav-item").forEach((el) => {
  el.addEventListener("click", (e) => {
    e.preventDefault();
    const tab = el.dataset.tab;
    document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
    el.classList.add("active");
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    document.getElementById("tab-" + tab).classList.add("active");
    if (tab === "sources") loadSources();
    if (tab === "logs") loadLogs();
  });
});

// ---------- 概览 ----------
async function loadDashboard() {
  try {
    const s = await api("/status");
    document.getElementById("stat-download-time").textContent = fmtTime(s.last_download_time);
    document.getElementById("stat-convert-time").textContent = fmtTime(s.last_convert_time);
    document.getElementById("stat-rtcm3-size").textContent = fmtSize(s.last_rtcm3_size);
    document.getElementById("stat-scheduler").innerHTML = s.scheduler_running
      ? '<span class="badge badge-running">运行中</span>'
      : '<span class="badge badge-none">未运行</span>';
  } catch {}
}

document.getElementById("manual-download-btn").addEventListener("click", async () => {
  const result = document.getElementById("operation-result");
  result.className = "operation-result";
  result.textContent = "正在下载并转换，请稍候...";
  result.classList.add("show");
  document.getElementById("manual-download-btn").disabled = true;
  try {
    const data = await api("/download/trigger", { method: "POST" });
    if (data.success) {
      result.className = "operation-result success show";
      result.innerHTML = `下载成功！数据源: ${data.source}，RTCM3 大小: ${fmtSize(data.rtcm3_size)}`;
    } else {
      result.className = "operation-result error show";
      result.textContent = "失败: " + (data.message || "未知错误");
    }
  } catch (err) {
    result.className = "operation-result error show";
    result.textContent = "异常: " + err.message;
  } finally {
    document.getElementById("manual-download-btn").disabled = false;
    loadDashboard();
  }
});

// ---------- 数据源管理 ----------
async function loadSources() {
  try {
    const sources = await api("/sources");
    const tbody = document.getElementById("sources-tbody");
    tbody.innerHTML = sources.map((s) => `
      <tr>
        <td><strong>${s.name}</strong><br><small style="color:#6b7280">${s.remark || ""}</small></td>
        <td>${s.protocol}</td>
        <td class="url-cell">${s.url_template}</td>
        <td>${s.username || "-"}</td>
        <td>${s.priority}</td>
        <td>${s.enabled ? "✅" : "❌"}</td>
        <td>${statusBadge(s.last_status)}<br><small>${fmtTime(s.last_download_at)}</small></td>
        <td>
          <button class="btn btn-sm" onclick="editSource(${s.id})">编辑</button>
          <button class="btn btn-sm btn-danger" onclick="deleteSource(${s.id})">删除</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    alert("加载数据源失败: " + err.message);
  }
}

document.getElementById("add-source-btn").addEventListener("click", () => openModal());

function openModal(source = null) {
  document.getElementById("modal-title").textContent = source ? "编辑数据源" : "添加数据源";
  document.getElementById("source-id").value = source?.id || "";
  document.getElementById("source-name").value = source?.name || "";
  document.getElementById("source-name").disabled = !!source;
  document.getElementById("source-protocol").value = source?.protocol || "https";
  document.getElementById("source-url").value = source?.url_template || "";
  document.getElementById("source-username").value = source?.username || "";
  document.getElementById("source-password").value = "";
  document.getElementById("source-priority").value = source?.priority || 10;
  document.getElementById("source-remark").value = source?.remark || "";
  document.getElementById("source-enabled").checked = source ? source.enabled : true;
  document.getElementById("source-modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("source-modal").classList.add("hidden");
}

window.editSource = async (id) => {
  const sources = await api("/sources");
  const s = sources.find((x) => x.id === id);
  if (s) openModal(s);
};

window.deleteSource = async (id) => {
  if (!confirm("确认删除此数据源？")) return;
  try {
    await api("/sources/" + id, { method: "DELETE" });
    loadSources();
  } catch (err) {
    alert("删除失败: " + err.message);
  }
};

document.getElementById("source-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("source-id").value;
  const payload = {
    name: document.getElementById("source-name").value,
    protocol: document.getElementById("source-protocol").value,
    url_template: document.getElementById("source-url").value,
    username: document.getElementById("source-username").value || null,
    password: document.getElementById("source-password").value || null,
    priority: parseInt(document.getElementById("source-priority").value),
    remark: document.getElementById("source-remark").value || null,
    enabled: document.getElementById("source-enabled").checked,
  };
  try {
    if (id) {
      // 编辑时只传有变化的字段
      await api("/sources/" + id, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      await api("/sources", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    closeModal();
    loadSources();
  } catch (err) {
    alert("保存失败: " + err.message);
  }
});

// ---------- 日志 ----------
async function loadLogs() {
  try {
    const logs = await api("/logs?limit=100");
    const tbody = document.getElementById("logs-tbody");
    tbody.innerHTML = logs.map((l) => `
      <tr>
        <td>${fmtTime(l.created_at)}</td>
        <td>${l.source_name}</td>
        <td>${statusBadge(l.status)}</td>
        <td>${l.file_name || "-"}</td>
        <td style="max-width:400px;word-break:break-all">${l.message || ""}</td>
      </tr>
    `).join("");
  } catch (err) {
    alert("加载日志失败: " + err.message);
  }
}

document.getElementById("refresh-logs-btn").addEventListener("click", loadLogs);

// ---------- 启动 ----------
checkAuth();
// 每 30 秒刷新概览
setInterval(() => {
  if (!document.getElementById("main-page").classList.contains("hidden")) {
    loadDashboard();
  }
}, 30000);
