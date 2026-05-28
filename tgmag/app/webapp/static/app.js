const tg = window.Telegram?.WebApp;
const initData = tg?.initData || "";
const state = {
  bootstrap: null,
  activeView: "dashboard",
};

if (tg) {
  tg.ready();
  tg.expand();
}

const qs = (selector, root = document) => root.querySelector(selector);
const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

function showNotice(text, type = "") {
  const box = qs("#notice");
  box.textContent = text;
  box.className = `notice ${type}`.trim();
  if (!text) box.classList.add("hidden");
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`/mini-app/api${path}`, {
    ...options,
    headers: {
      "X-Telegram-Init-Data": initData,
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

async function downloadApi(path, payload) {
  const response = await fetch(`/mini-app/api${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : "tg_sessions.txt";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return {
    exported: response.headers.get("X-Exported-Count"),
    skipped: response.headers.get("X-Skipped-Count"),
  };
}

function switchView(view) {
  state.activeView = view;
  qsa(".tab").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  qsa(".view").forEach((section) => section.classList.remove("active"));
  qs(`#${view}View`).classList.add("active");
}

function statusLabel(status) {
  const labels = {
    normal: "正常",
    limited: "限制",
    banned: "封禁",
    unknown: "未知",
    active: "未检测",
    new: "未检测",
  };
  return labels[status] || status || "未知";
}

function accountRow(account, compact = false) {
  const row = document.createElement("article");
  row.className = "account-row";
  const name = account.name || "-";
  const username = account.username ? `@${account.username}` : "-";
  row.innerHTML = `
    <div class="row-main">
      <div>
        <div class="row-title">#${account.id} ${account.phone_masked}</div>
        <div class="row-meta">${username} · ${name} · TG ${account.user_id || "-"}</div>
      </div>
      <span class="status ${account.status || ""}">${statusLabel(account.status)}</span>
    </div>
  `;
  if (!compact) {
    const actions = document.createElement("div");
    actions.className = "row-actions";
    actions.innerHTML = `
      <button class="text-button" type="button" data-action="detail">详情</button>
      <button class="text-button" type="button" data-action="export_session">导出</button>
      <button class="text-button" type="button" data-action="refresh_status">刷新检测</button>
      <button class="text-button" type="button" data-action="reconnect">重连</button>
      <button class="text-button" type="button" data-action="spam">SpamBot</button>
      <button class="text-button" type="button" data-action="service_check">777000</button>
    `;
    actions.addEventListener("click", (event) => {
      const action = event.target?.dataset?.action;
      if (!action) return;
      if (action === "detail") {
        loadAccountDetail(account.id);
      } else if (action === "export_session") {
        exportSessions({ mode: "single", account_id: account.id });
      } else {
        runAccountAction(account.id, action);
      }
    });
    row.append(actions);
  }
  return row;
}

function renderBootstrap(data) {
  state.bootstrap = data;
  qs("#metricAccounts").textContent = data.status.accounts;
  qs("#metricUsable").textContent = data.status.usable;
  qs("#metricConnected").textContent = data.status.connected;
  qs("#metricJobs").textContent = data.status.running_jobs;

  const recent = qs("#recentAccounts");
  recent.replaceChildren(...data.accounts.slice(0, 8).map((account) => accountRow(account, true)));
  renderAccounts(data.accounts);
  renderTargets(data.targets);
  renderRates(data.rates);
}

function renderAccounts(accounts) {
  const list = qs("#accountsList");
  list.replaceChildren(...accounts.map((account) => accountRow(account)));
}

function renderTargets(targets) {
  const list = qs("#targetsList");
  list.replaceChildren(
    ...targets.map((target) => {
      const row = document.createElement("article");
      row.className = "account-row";
      row.innerHTML = `
        <div class="row-main">
          <div>
            <div class="row-title">${target.target_ref}</div>
            <div class="row-meta">${target.target_type} · ${target.title || "-"}</div>
          </div>
          <button class="text-button" type="button">删除</button>
        </div>
      `;
      qs("button", row).addEventListener("click", () => removeTarget(target.target_ref));
      return row;
    })
  );
}

function renderRates(rates) {
  const list = qs("#ratesList");
  list.replaceChildren(
    ...rates.map((rate) => {
      const row = document.createElement("article");
      row.className = "account-row";
      row.innerHTML = `
        <div class="row-title">${rate.scope}</div>
        <div class="row-meta">${rate.max_actions}/${rate.per_seconds}s · jitter ${rate.jitter_min}-${rate.jitter_max}s</div>
      `;
      if (rate.scope === "batch") {
        qs("[name=max_actions]").value = rate.max_actions;
        qs("[name=per_seconds]").value = rate.per_seconds;
        qs("[name=jitter_min]").value = rate.jitter_min;
        qs("[name=jitter_max]").value = rate.jitter_max;
      }
      return row;
    })
  );
}

async function loadBootstrap() {
  if (!initData) {
    showNotice("请从 Telegram Bot 内打开此应用。", "error");
    return;
  }
  showNotice("正在加载...");
  try {
    const data = await api("/bootstrap");
    renderBootstrap(data);
    showNotice("");
  } catch (error) {
    showNotice(`加载失败：${error.message}`, "error");
  }
}

async function searchAccounts() {
  try {
    const q = encodeURIComponent(qs("#accountSearch").value.trim());
    const data = await api(`/accounts?q=${q}`);
    renderAccounts(data.accounts);
    showNotice("");
  } catch (error) {
    showNotice(`搜索失败：${error.message}`, "error");
  }
}

async function submitPhoneLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const step = event.submitter?.dataset?.step || "start";
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    if (step === "start") {
      showNotice("正在发送验证码...");
      const data = await api("/accounts/login/start", {
        method: "POST",
        body: JSON.stringify({ phone: payload.phone }),
      });
      if (data.already_exists) {
        showNotice(data.message, "ok");
        await loadBootstrap();
        switchView("accounts");
        await loadAccountDetail(data.account.id);
        return;
      }
      form.elements.login_id.value = data.login_id;
      showNotice(data.message || "验证码已发送", "ok");
      return;
    }
    if (!payload.login_id) {
      showNotice("请先发送验证码。", "error");
      return;
    }
    showNotice("正在确认登录...");
    const data = await api("/accounts/login/verify", {
      method: "POST",
      body: JSON.stringify({
        login_id: payload.login_id,
        code: payload.code,
        password: payload.password,
      }),
    });
    if (data.needs_password) {
      showNotice("该账号需要 2FA 密码，请填写后再次点击确认添加。");
      return;
    }
    showNotice(data.message, "ok");
    form.reset();
    await loadBootstrap();
    switchView("accounts");
    await loadAccountDetail(data.account.id);
  } catch (error) {
    showNotice(`添加账号失败：${error.message}`, "error");
  }
}

async function submitSessionImport(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    showNotice("正在导入 Session...");
    const data = await api("/accounts/import-session", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(data.message, "ok");
    form.reset();
    await loadBootstrap();
    switchView("accounts");
    await loadAccountDetail(data.account.id);
  } catch (error) {
    showNotice(`Session 导入失败：${error.message}`, "error");
  }
}

async function exportSessions(payload) {
  try {
    showNotice("正在生成 Session 导出文件...");
    const result = await downloadApi("/accounts/export-sessions", payload);
    showNotice(`导出完成：${result.exported || 0} 个，跳过 ${result.skipped || 0} 个。`, "ok");
  } catch (error) {
    showNotice(`Session 导出失败：${error.message}`, "error");
  }
}

async function submitSessionExport(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const mode = event.submitter?.dataset?.mode || "selection";
  const raw = Object.fromEntries(new FormData(form).entries());
  if (mode === "range") {
    if (!raw.start_id || !raw.count) {
      showNotice("请填写起始账号 ID 和数量。", "error");
      return;
    }
    await exportSessions({
      mode: "range",
      start_id: Number(raw.start_id),
      count: Number(raw.count),
    });
    return;
  }
  if (!raw.selection.trim()) {
    showNotice("请填写要导出的账号 ID，例如 1,3,5-8。", "error");
    return;
  }
  await exportSessions({
    mode: "selection",
    selection: raw.selection,
  });
}

async function loadAccountDetail(accountId) {
  try {
    const data = await api(`/accounts/${accountId}`);
    const account = data.account;
    const detail = qs("#accountDetail");
    detail.classList.remove("hidden");
    detail.innerHTML = `
      <div class="panel-head">
        <h2>账号 #${account.id}</h2>
        <span class="status ${account.status || ""}">${statusLabel(account.status)}</span>
      </div>
      <div class="list compact">
        <p><strong>用户名：</strong>${account.username ? `@${account.username}` : "-"}</p>
        <p><strong>姓名：</strong>${account.name || "-"}</p>
        <p><strong>Telegram ID：</strong>${account.user_id || "-"}</p>
        <p><strong>本地 Session：</strong>${account.has_active_session ? "可用" : "不可用"}</p>
        <p><strong>2FA：</strong>${account.has_2fa ? "已启用" : "未启用/未知"}</p>
        <p><strong>隐私快照：</strong>${JSON.stringify(account.privacy || {})}</p>
        <p><strong>SpamBot：</strong>${account.latest_spam ? statusLabel(account.latest_spam.status) : "未检测"}</p>
      </div>
      <div class="detail-actions">
        <button class="text-button" type="button" data-action="reconnect">重连</button>
        <button class="text-button" type="button" data-action="export_session">导出Session</button>
        <button class="text-button" type="button" data-action="refresh_status">刷新检测</button>
        <button class="text-button" type="button" data-action="spam">SpamBot</button>
        <button class="text-button" type="button" data-action="service_check">拉取777000</button>
        <button class="text-button" type="button" data-action="service_messages">查看777000</button>
      </div>
      <div class="detail-grid">
        <form id="profileForm" class="subpanel form">
          <h3>资料设置</h3>
          <div class="split">
            <label><span>First Name</span><input name="first_name" value="${account.name.split(" ")[0] || ""}" /></label>
            <label><span>Last Name</span><input name="last_name" value="${account.name.split(" ").slice(1).join(" ")}" /></label>
          </div>
          <label><span>用户名</span><input name="username" value="${account.username || ""}" placeholder="不用带 @" /></label>
          <label><span>简介</span><textarea name="bio" rows="3" placeholder="留空则不修改简介"></textarea></label>
          <button class="primary-button" type="submit">保存资料</button>
        </form>

        <form id="avatarForm" class="subpanel form">
          <h3>头像设置</h3>
          <label><span>上传头像</span><input name="avatar" type="file" accept="image/*" /></label>
          <label><span>服务器路径</span><input name="path" placeholder="/root/avatar.jpg" /></label>
          <div class="split">
            <button class="text-button" type="submit" data-mode="upload">上传设置</button>
            <button class="text-button" type="submit" data-mode="path">路径设置</button>
            <button class="text-button" type="submit" data-mode="random">随机头像</button>
          </div>
        </form>

        <form id="privacyForm" class="subpanel form">
          <h3>隐私设置</h3>
          <div class="split">
            <label>
              <span>隐私项</span>
              <select name="key">
                <option value="phone">手机号</option>
                <option value="last_seen">在线时间</option>
                <option value="profile_photo">头像</option>
                <option value="forwards">转发来源</option>
                <option value="calls">通话</option>
                <option value="groups">拉群</option>
              </select>
            </label>
            <label>
              <span>范围</span>
              <select name="rule">
                <option value="everybody">所有人</option>
                <option value="contacts">联系人</option>
                <option value="nobody">没有人</option>
              </select>
            </label>
          </div>
          <button class="primary-button" type="submit">保存隐私</button>
        </form>

        <form id="twofaForm" class="subpanel form">
          <h3>2FA 管理</h3>
          <label>
            <span>操作</span>
            <select name="action">
              <option value="check">查询状态</option>
              <option value="set">设置 2FA</option>
              <option value="change">修改 2FA</option>
              <option value="email">配置 2FA 邮箱</option>
              <option value="disable">关闭 2FA</option>
              <option value="confirm">确认邮箱验证码</option>
            </select>
          </label>
          <div class="split">
            <label><span>当前密码</span><input name="current_password" type="password" /></label>
            <label><span>新密码</span><input name="new_password" type="password" /></label>
          </div>
          <div class="split">
            <label><span>提示</span><input name="hint" /></label>
            <label><span>邮箱</span><input name="email" type="email" /></label>
          </div>
          <label><span>邮箱验证码</span><input name="code" inputmode="numeric" /></label>
          <button class="primary-button" type="submit">执行 2FA 操作</button>
        </form>

        <form id="loginEmailForm" class="subpanel form">
          <h3>登录邮箱</h3>
          <label><span>邮箱</span><input name="email" type="email" /></label>
          <label><span>验证码</span><input name="code" inputmode="numeric" /></label>
          <div class="split">
            <button class="text-button" type="submit" data-action="send">发送验证码</button>
            <button class="text-button" type="submit" data-action="confirm">确认验证码</button>
          </div>
        </form>
      </div>
      <section id="serviceMessagesPanel" class="subpanel hidden">
        <h3>777000 消息</h3>
        <div id="serviceMessagesList" class="list compact"></div>
      </section>
    `;
    qs(".detail-actions", detail).addEventListener("click", (event) => {
      const action = event.target?.dataset?.action;
      if (!action) return;
      if (action === "service_messages") {
        loadServiceMessages(accountId);
      } else if (action === "export_session") {
        exportSessions({ mode: "single", account_id: accountId });
      } else {
        runAccountAction(accountId, action);
      }
    });
    qs("#profileForm", detail).addEventListener("submit", (event) => submitProfile(event, accountId));
    qs("#avatarForm", detail).addEventListener("submit", (event) => submitAvatar(event, accountId));
    qs("#privacyForm", detail).addEventListener("submit", (event) => submitPrivacy(event, accountId));
    qs("#twofaForm", detail).addEventListener("submit", (event) => submitTwoFA(event, accountId));
    qs("#loginEmailForm", detail).addEventListener("submit", (event) => submitLoginEmail(event, accountId));
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showNotice(`详情加载失败：${error.message}`, "error");
  }
}

async function submitProfile(event, accountId) {
  event.preventDefault();
  const form = event.currentTarget;
  const raw = Object.fromEntries(new FormData(form).entries());
  const payload = {};
  if (raw.first_name || raw.last_name) {
    payload.first_name = raw.first_name;
    payload.last_name = raw.last_name;
  }
  if (raw.username) payload.username = raw.username;
  if (raw.bio) payload.bio = raw.bio;
  if (!Object.keys(payload).length) {
    showNotice("没有需要保存的资料字段。", "error");
    return;
  }
  try {
    const data = await api(`/accounts/${accountId}/profile`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(data.message, "ok");
    await loadBootstrap();
    await loadAccountDetail(accountId);
  } catch (error) {
    showNotice(`资料保存失败：${error.message}`, "error");
  }
}

async function submitAvatar(event, accountId) {
  event.preventDefault();
  const mode = event.submitter?.dataset?.mode || "upload";
  const form = event.currentTarget;
  const formData = new FormData();
  formData.append("mode", mode);
  if (mode === "upload") {
    const file = qs("[name=avatar]", form).files[0];
    if (!file) {
      showNotice("请先选择头像图片。", "error");
      return;
    }
    formData.append("avatar", file);
  } else if (mode === "path") {
    formData.append("path", qs("[name=path]", form).value.trim());
  }
  try {
    const data = await api(`/accounts/${accountId}/avatar`, {
      method: "POST",
      body: formData,
    });
    showNotice(data.message, "ok");
  } catch (error) {
    showNotice(`头像设置失败：${error.message}`, "error");
  }
}

async function submitPrivacy(event, accountId) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const data = await api(`/accounts/${accountId}/privacy`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(data.message, "ok");
    await loadAccountDetail(accountId);
  } catch (error) {
    showNotice(`隐私设置失败：${error.message}`, "error");
  }
}

async function submitTwoFA(event, accountId) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const data = await api(`/accounts/${accountId}/twofa`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(data.message || JSON.stringify(data.info || {}), data.needs_code ? "" : "ok");
    if (!data.needs_code) await loadAccountDetail(accountId);
  } catch (error) {
    showNotice(`2FA 操作失败：${error.message}`, "error");
  }
}

async function submitLoginEmail(event, accountId) {
  event.preventDefault();
  const action = event.submitter?.dataset?.action || "send";
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  payload.action = action;
  try {
    const data = await api(`/accounts/${accountId}/login-email`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(data.message || "登录邮箱操作完成", data.needs_code ? "" : "ok");
  } catch (error) {
    showNotice(`登录邮箱操作失败：${error.message}`, "error");
  }
}

async function loadServiceMessages(accountId) {
  try {
    const data = await api(`/accounts/${accountId}/service-messages?limit=20`);
    const panel = qs("#serviceMessagesPanel");
    const list = qs("#serviceMessagesList");
    panel.classList.remove("hidden");
    list.replaceChildren(
      ...data.messages.map((message) => {
        const row = document.createElement("article");
        row.className = "account-row";
        row.innerHTML = `
          <div class="row-title">消息 #${message.message_id}</div>
          <div class="row-meta">${message.received_at}</div>
          <p>${message.text_preview || ""}</p>
        `;
        return row;
      })
    );
    if (!data.messages.length) {
      list.innerHTML = '<p class="muted">暂无 777000 消息</p>';
    }
  } catch (error) {
    showNotice(`777000 消息加载失败：${error.message}`, "error");
  }
}

async function runAccountAction(accountId, action) {
  showNotice("正在执行账号操作...");
  try {
    const data = await api(`/accounts/${accountId}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    showNotice(data.message || "操作完成", "ok");
    await loadBootstrap();
  } catch (error) {
    showNotice(`操作失败：${error.message}`, "error");
  }
}

async function removeTarget(targetRef) {
  showNotice("正在删除授权目标...");
  try {
    const data = await api("/targets", {
      method: "POST",
      body: JSON.stringify({ action: "remove", target_ref: targetRef }),
    });
    showNotice(data.message, "ok");
    await loadBootstrap();
  } catch (error) {
    showNotice(`删除失败：${error.message}`, "error");
  }
}

function batchFieldMode() {
  const type = qs("#batchForm [name=type]").value;
  qsa(".message-fields").forEach((node) =>
    node.classList.toggle("hidden", !["react", "unreact", "view_post", "forward"].includes(type))
  );
  qsa(".react-only").forEach((node) => node.classList.toggle("hidden", type !== "react"));
  qsa(".forward-only").forEach((node) => node.classList.toggle("hidden", type !== "forward"));
  qsa(".text-only").forEach((node) => node.classList.toggle("hidden", type !== "send"));
}

async function submitBatch(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  const payload = {
    ...data,
    account_mode: "range",
    start_id: Number(data.start_id),
    count: Number(data.count),
    message_id: data.message_id ? Number(data.message_id) : undefined,
  };
  showNotice("正在运行批量任务，请保持页面打开...");
  try {
    const result = await api("/batch/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(result.message, "ok");
    await loadBootstrap();
  } catch (error) {
    showNotice(`批量任务失败：${error.message}`, "error");
  }
}

async function submitTarget(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  payload.action = "add";
  try {
    const result = await api("/targets", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(result.message, "ok");
    event.currentTarget.reset();
    qs("#targetForm [name=target_type]").value = "channel";
    await loadBootstrap();
  } catch (error) {
    showNotice(`添加失败：${error.message}`, "error");
  }
}

async function submitRate(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  for (const key of ["max_actions", "per_seconds", "jitter_min", "jitter_max"]) {
    payload[key] = Number(payload[key]);
  }
  try {
    const result = await api("/rates", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice(result.message, "ok");
    await loadBootstrap();
  } catch (error) {
    showNotice(`保存失败：${error.message}`, "error");
  }
}

qsa(".tab").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
qsa("[data-view-jump]").forEach((button) =>
  button.addEventListener("click", () => switchView(button.dataset.viewJump))
);
qs("#refreshBtn").addEventListener("click", loadBootstrap);
qs("#searchBtn").addEventListener("click", searchAccounts);
qs("#accountSearch").addEventListener("keydown", (event) => {
  if (event.key === "Enter") searchAccounts();
});
qs("#batchForm").addEventListener("submit", submitBatch);
qs("#batchForm [name=type]").addEventListener("change", batchFieldMode);
qs("#phoneLoginForm").addEventListener("submit", submitPhoneLogin);
qs("#sessionImportForm").addEventListener("submit", submitSessionImport);
qs("#sessionExportForm").addEventListener("submit", submitSessionExport);
qs("#targetForm").addEventListener("submit", submitTarget);
qs("#rateForm").addEventListener("submit", submitRate);
qs("#reloadTargetsBtn").addEventListener("click", loadBootstrap);

batchFieldMode();
loadBootstrap();
