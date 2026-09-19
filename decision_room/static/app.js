/* Decision Room: dependency-free UI, streamed events, and local history. */
"use strict";
const $ = (selector) => document.querySelector(selector);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const roles = {
  strategist: {
    name: "The strategist",
    focus: "Value & opportunity",
    icon: "↗",
  },
  engineer: {
    name: "The engineer",
    focus: "Feasibility & execution",
    icon: "⌘",
  },
  skeptic: { name: "The skeptic", focus: "Risk & assumptions", icon: "◇" },
};
let config,
  mode = "demo",
  selectedScenario = "search",
  report = null,
  controller = null;
let chosenModels = ["openai", "anthropic", "openai"];
let partial = {},
  activeTab = "overview",
  token = "";
const headers = () => (token ? { Authorization: `Bearer ${token}` } : {});
const money = (value) =>
  value == null ? "Unavailable" : `$${value.toFixed(4)}`;
const list = (values) =>
  `<ul>${values.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>`;
const avatar = (role) =>
  `<span class="role-avatar ${role}" aria-hidden="true">${roles[role].icon}</span>`;

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...headers(), ...options.headers },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : "Check your brief and try again.";
    throw new Error(detail || `Request failed (${res.status}).`);
  }
  return res;
}
function notice(message) {
  $("#notice").textContent = message;
  $("#notice").hidden = !message;
}
function dialog(html) {
  $("#dialog-content").innerHTML = html;
  $("#info-dialog").showModal();
}
function setScenario(id) {
  selectedScenario = id;
  const scenario = config.scenarios.find((s) => s.id === id);
  $("#question").value = scenario.question;
  $("#context").value = scenario.context;
  document
    .querySelectorAll(".example-button")
    .forEach((b) => b.classList.toggle("active", b.dataset.scenario === id));
}
function renderPanelists() {
  $("#panelists").innerHTML = Object.entries(roles)
    .map(
      ([key, r], index) =>
        `<div class="panelist-row">${avatar(key)}<div class="panelist-name">${r.name}<small>${r.focus}</small></div>${mode === "demo" ? '<span class="demo-provider">Example role</span>' : `<select id="model-${key}" aria-label="Model for ${r.name}" data-index="${index}">${config.providers.map((p) => `<option value="${p.id}" ${p.id === chosenModels[index] ? "selected" : ""} ${!p.available ? "disabled" : ""}>${esc(p.label)}${!p.available ? " · no key" : ""}</option>`).join("")}</select>`}</div>`,
    )
    .join("");
  document.querySelectorAll("#panelists select").forEach((s) =>
    s.addEventListener("change", () => {
      chosenModels[Number(s.dataset.index)] = s.value;
    }),
  );
}
function setMode(next) {
  if (next === "live" && !config.live_enabled) {
    settings();
    return;
  }
  if (next === "live" && !config.providers.some((p) => p.available)) {
    settings();
    return;
  }
  mode = next;
  $("#demo-mode").classList.toggle("active", next === "demo");
  $("#live-mode").classList.toggle("active", next === "live");
  $("#question").readOnly = $("#context").readOnly = mode === "demo";
  $("#config-note").textContent =
    mode === "demo"
      ? "Explore a curated decision. Tools run for real; the panel’s written responses are examples."
      : "Three independent roles, using the models you choose. Usage is tracked for every provider call.";
  $("#mode-explanation").textContent =
    mode === "demo"
      ? "● Curated example · no API keys needed"
      : "● Live analysis · provider usage charges apply";
  $("#run-note").textContent =
    mode === "demo"
      ? "3 perspectives · 1 critique round · 1 decision memo"
      : "Bounded requests · 5-minute limit · stop anytime";
  if (mode === "demo") setScenario(selectedScenario);
  renderPanelists();
}
function setBusy(busy) {
  document.body.classList.toggle("busy", busy);
  $("#run-button").disabled = busy;
  $("#run-button").innerHTML = busy
    ? "The room is deliberating… <span>◌</span>"
    : "Open the decision room <span>↗</span>";
  $("#demo-mode").disabled = $("#live-mode").disabled = busy;
  document
    .querySelectorAll("#examples button, #panelists select")
    .forEach((b) => (b.disabled = busy));
  $("#question").disabled = $("#context").disabled = busy;
  $("#run-status").hidden = !busy;
  $("#cancel-button").hidden = !busy;
}
function newDecision() {
  if (controller) return;
  report = null;
  $("#live-feed").hidden = true;
  document.body.classList.remove("showing-results");
  $("#results").hidden = true;
  $("#empty-guide").hidden = false;
  $("#page-label").textContent = "New decision";
  notice("");
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function updateLiveFeed(event) {
  if (!roles[event.role]) return;
  const item = (partial[event.role] ||= {});
  if (event.type === "agent_start") {
    item.model = event.model;
    item.status =
      event.phase === "review"
        ? "Reviewing the panel…"
        : "Considering the brief…";
  }
  if (event.type === "opinion") {
    item.opinion = event.data;
    item.status = "Initial perspective ready";
  }
  if (event.type === "review") {
    item.review = event.data;
    item.status = "Critique complete";
  }
  if (event.type === "agent_error") item.status = "Stage unavailable";
  $("#live-feed").innerHTML = Object.entries(roles)
    .map(([role, r]) => {
      const p = partial[role] || {};
      return `<article class="panel stream-card"><div class="opinion-mini-header">${avatar(role)}<div><h3>${r.name}</h3><small>${esc(p.model || (mode === "demo" ? "Curated demo" : "Waiting"))}</small></div></div><div class="stream-status">${esc(p.status || "Waiting for this role")}</div>${p.opinion ? `<h4>${esc(p.opinion.recommendation)}</h4><p>${esc(p.opinion.rationale)}</p>` : '<p class="stream-placeholder">An independent perspective is on its way.</p>'}${p.review ? `<div class="stream-review"><strong>After hearing the room</strong><p>${esc(p.review.revised_position)}</p></div>` : ""}</article>`;
    })
    .join("");
}
function eventReceived(event) {
  updateLiveFeed(event);
  if (event.type === "phase") {
    $("#status-text").textContent = event.label;
    const order = ["opinion", "review", "memo"];
    document.querySelectorAll("[data-stage]").forEach((s) => {
      s.classList.toggle("active", s.dataset.stage === event.phase);
      s.classList.toggle(
        "complete",
        order.indexOf(s.dataset.stage) < order.indexOf(event.phase),
      );
    });
  }
  if (event.type === "agent_start")
    $("#status-text").textContent =
      `${roles[event.role]?.name || "The editor"} is ${event.phase === "review" ? "reviewing the panel" : event.phase === "memo" ? "writing the memo" : "considering your decision"}…`;
  if (event.type === "opinion" || event.type === "review")
    $("#status-text").textContent =
      `${roles[event.role].name} shared ${event.type === "opinion" ? "a perspective" : "a critique"}.`;
  if (event.type === "tool")
    $("#status-text").textContent =
      `Calculated ${event.name.replaceAll("_", " ")}.`;
  if (event.type === "agent_error")
    notice(
      `${roles[event.role]?.name || "A panelist"} could not complete a stage. This will be disclosed in the memo.`,
    );
  if (event.type === "error") throw new Error(event.message);
  if (event.type === "done") {
    renderReport(event.report);
    loadHistory();
  }
}
async function run(event) {
  event.preventDefault();
  if (controller) return;
  notice("");
  partial = {};
  $("#live-feed").innerHTML = "";
  $("#live-feed").hidden = false;
  $("#results").hidden = true;
  $("#empty-guide").hidden = true;
  document.body.classList.remove("showing-results");
  const payload = {
    question: $("#question").value,
    context: $("#context").value,
    mode,
    scenario: selectedScenario,
    models: chosenModels,
  };
  controller = new AbortController();
  setBusy(true);
  try {
    const response = await api("/api/decisions/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "",
      completed = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let end;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6));
          eventReceived(data);
          if (data.type === "done") completed = true;
        }
      }
    }
    if (!completed)
      throw new Error(
        "The connection closed before a complete memo arrived. Please try again.",
      );
  } catch (error) {
    controller?.abort();
    notice(
      error.name === "AbortError"
        ? "Run stopped. No partial memo was saved. A provider may still bill work already processed."
        : error.message,
    );
  } finally {
    controller = null;
    setBusy(false);
  }
}
function renderMetrics(r) {
  const known = r.calls.every(
    (c) => c.input_tokens != null && c.output_tokens != null,
  );
  const tokens = known
    ? r.calls.reduce((n, c) => n + c.input_tokens + c.output_tokens, 0)
    : null;
  const costKnown = r.calls.every((c) => c.cost_usd != null);
  const cost = costKnown ? r.calls.reduce((n, c) => n + c.cost_usd, 0) : null;
  const metrics = [
    [
      "PANEL PERSPECTIVES",
      String(Object.keys(r.opinions).length).padStart(2, "0"),
      r.mode === "demo"
        ? "Curated example responses"
        : `${new Set(Object.values(r.models)).size} distinct model(s)`,
    ],
    [
      "TOKENS USED",
      tokens == null ? "—" : tokens.toLocaleString(),
      r.mode === "demo"
        ? "Demo · no model calls"
        : `${r.calls.length} provider calls · reported usage`,
    ],
    [
      "ESTIMATED COST",
      r.mode === "demo" ? "$0.00" : cost == null ? "—" : money(cost),
      r.mode === "demo"
        ? "No API usage in this replay"
        : costKnown
          ? "Model price estimate, not a bill"
          : "Pricing unavailable for some calls",
    ],
    [
      r.mode === "demo" ? "TOOLS EXECUTED" : "ELAPSED TIME",
      r.mode === "demo"
        ? String(r.tools.length).padStart(2, "0")
        : `${(r.duration_ms / 1000).toFixed(1)}s`,
      r.mode === "demo"
        ? "Computed locally in Python"
        : `${r.tools.length} tool requests`,
    ],
  ];
  $("#metrics").innerHTML = metrics
    .map(
      ([label, value, detail]) =>
        `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${esc(value)}</div><div class="metric-detail">${esc(detail)}</div></div>`,
    )
    .join("");
}
function renderOverview(r) {
  const m = r.memo,
    matrix = m.matrix;
  const weightTotal = matrix.criteria.reduce((n, c) => n + c.weight, 0);
  $("#view-overview").innerHTML =
    `<div class="overview-grid"><div><article class="recommendation"><div class="eyebrow">↗ &nbsp; THE RECOMMENDATION</div><h3>${esc(m.recommendation)}</h3><p>${esc(m.summary)}</p></article><div class="split-memo"><section class="memo-section"><h3><span>⊕</span> Common ground</h3>${list(m.agreement)}</section><section class="memo-section dissent"><h3><span>⇄</span> Still up for debate</h3>${list(m.disagreements)}</section></div><aside class="revisit"><strong>↺ &nbsp; WHAT WOULD CHANGE THIS DECISION?</strong><p>${esc(m.revisit_when)}</p></aside></div><div><section class="panel score-panel"><h3>How the options compare <span style="margin-left:auto;color:#9aa98c;font-size:10px">/ 10</span></h3><p class="score-subtitle">Weighted scores · higher is better</p>${r.ranking.ranking.map((row) => `<div class="score-row"><div class="score-label"><span>${esc(row.name)}</span><strong>${row.score.toFixed(1)}</strong></div><div class="score-track"><div class="score-fill" style="width:${Math.max(0, Math.min(100, row.score * 10))}%"></div></div></div>`).join("")}<div class="matrix-wrap"><table class="matrix"><thead><tr><th>CRITERIA</th>${matrix.options.map((o) => `<th class="numeric">${esc(o.name)}</th>`).join("")}</tr></thead><tbody>${matrix.criteria.map((c, i) => `<tr><td>${esc(c.name)}<small style="display:block;color:#a3ad95">${Math.round((c.weight / weightTotal) * 100)}% weight</small></td>${matrix.options.map((o) => `<td class="numeric">${o.scores[i]}</td>`).join("")}</tr>`).join("")}</tbody></table></div><p class="score-note">${r.mode === "demo" ? "Illustrative scores from the curated scenario." : "Model-assigned scores and weights."} Totals are calculated in Python. These are judgments, not measured performance or probabilities.</p></section><section class="memo-section"><h3><span>↗</span> Your next moves</h3><ul class="steps-list">${m.next_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></section></div></div><div class="panel-summary-grid">${Object.entries(
      r.opinions,
    )
      .map(
        ([role, o]) =>
          `<article class="opinion-mini"><div class="opinion-mini-header">${avatar(role)}<div><h4>${roles[role].name}</h4><small>${esc(r.models[role])}</small></div></div><p>${esc(o.recommendation)}</p></article>`,
      )
      .join("")}</div>`;
}
function renderDeliberation(r) {
  $("#view-deliberation").innerHTML =
    `<div class="deliberation-grid">${Object.entries(r.opinions)
      .map(([role, o]) => {
        const rev = r.reviews[role];
        return `<article class="panel opinion-card"><div class="role-header">${avatar(role)}<div><h3>${roles[role].name}</h3><small>${esc(r.models[role])}</small></div></div><span class="section-label">01 / INDEPENDENT PERSPECTIVE</span><h4>${esc(o.recommendation)}</h4><p>${esc(o.rationale)}</p><span class="section-label">ASSUMPTIONS</span>${list(o.assumptions)}<span class="section-label">RISKS TO WATCH</span>${list(o.risks)}<div class="critique"><span class="section-label">02 / AFTER HEARING THE ROOM</span>${rev ? `<strong>The challenge</strong><p>${esc(rev.challenge)}</p><strong>A fair point</strong><p>${esc(rev.concession)}</p><div class="revised"><strong>Revised position</strong><p>${esc(rev.revised_position)}</p></div>` : "<p>This panelist’s review was unavailable.</p>"}</div></article>`;
      })
      .join("")}</div>`;
}
function renderActivity(r) {
  $("#view-activity").innerHTML =
    `<section class="panel activity-panel"><h3>Provider calls</h3><p class="activity-note">${r.mode === "demo" ? "This replay uses curated responses. There are no provider calls, model latency measurements, or token charges." : "Each row is one provider response, including tool continuations and JSON repair attempts. Costs are estimates from the model price catalog."}</p>${r.calls.length ? `<div class="matrix-wrap"><table class="usage-table"><thead><tr><th>ROLE / STAGE</th><th>MODEL</th><th>INPUT</th><th>OUTPUT</th><th>LATENCY</th><th>EST. COST</th></tr></thead><tbody>${r.calls.map((c) => `<tr><td>${esc(c.role)} / ${esc(c.phase)}</td><td>${esc(c.model)}</td><td>${c.input_tokens ?? "—"}</td><td>${c.output_tokens ?? "—"}</td><td>${(c.latency_ms / 1000).toFixed(2)}s</td><td>${money(c.cost_usd)}</td></tr>`).join("")}</tbody></table></div>` : ""}</section><section class="panel activity-panel"><h3>Tool activity <span class="small-tag">${r.tools.length} REQUESTS</span></h3><p class="activity-note">Validated inputs. Deterministic Python outputs. Expand a call to inspect the calculation.</p>${r.tools.length ? r.tools.map((t) => `<details class="tool-item"><summary>${esc(t.name)}<span>${esc(t.role)} · ${t.result.error ? "Rejected" : "Completed"}</span></summary><div class="tool-data"><div><strong>INPUT</strong><pre>${esc(JSON.stringify(t.arguments, null, 2))}</pre></div><div><strong>OUTPUT</strong><pre>${esc(JSON.stringify(t.result, null, 2))}</pre></div></div></details>`).join("") : '<p class="activity-note">No tools were requested by the panel.</p>'}</section>${r.failures.length ? `<section class="panel activity-panel"><h3>Incomplete stages</h3>${list(r.failures.map((f) => `${f.role} / ${f.phase}: ${f.message}`))}</section>` : ""}<p class="activity-note">Run ${esc(r.id)} · ${esc(new Date(r.created_at).toLocaleString())} · ${r.mode === "demo" ? "Demo replay" : "Live inference"} · Total elapsed ${(r.duration_ms / 1000).toFixed(1)}s</p>`;
}
function setTab(tab) {
  activeTab = tab;
  document.querySelectorAll("[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.setAttribute("aria-selected", String(b.dataset.tab === tab));
    b.tabIndex = b.dataset.tab === tab ? 0 : -1;
  });
  ["overview", "deliberation", "activity"].forEach((t) => {
    $(`#view-${t}`).hidden = t !== tab;
  });
}
function renderReport(r) {
  report = r;
  $("#live-feed").hidden = true;
  document.body.classList.add("showing-results");
  $("#results").hidden = false;
  $("#empty-guide").hidden = true;
  $("#page-label").textContent = "Decision memo";
  $("#result-provenance").textContent =
    r.mode === "demo"
      ? "CURATED DEMO · NO LIVE MODEL CALLS"
      : "LIVE DECISION · COMPLETE";
  $("#result-title").textContent = r.memo.title;
  $("#result-question").textContent = r.question;
  if (r.failures.length)
    notice(
      `${r.failures.length} stage(s) could not be completed. See Activity & usage for details.`,
    );
  else notice("");
  renderMetrics(r);
  renderOverview(r);
  renderDeliberation(r);
  renderActivity(r);
  setTab("overview");
  window.scrollTo({ top: 0, behavior: "smooth" });
}
async function loadHistory() {
  try {
    const history = await (await api("/api/decisions")).json();
    if (!history.length) return;
    $("#history").innerHTML = history
      .map(
        (d) =>
          `<button class="history-item ${report?.id === d.id ? "active" : ""}" data-id="${esc(d.id)}"><span class="history-dot">◇</span><span><span class="history-text">${esc(d.question.replace(/^Should we /, ""))}</span><small>${d.mode === "demo" ? "Demo" : "Live"} · ${esc(new Date(d.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }))}</small></span></button>`,
      )
      .join("");
    document.querySelectorAll(".history-item").forEach((b) =>
      b.addEventListener("click", async () => {
        if (controller) return;
        try {
          renderReport(
            await (await api(`/api/decisions/${b.dataset.id}`)).json(),
          );
          loadHistory();
        } catch (e) {
          notice(e.message);
        }
      }),
    );
  } catch (error) {
    if (!config.auth_required) notice(error.message);
  }
}
async function download(format) {
  if (!report) return;
  try {
    const res = await api(
      `/api/decisions/${report.id}/export?format=${format}`,
    );
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `decision-${report.id}.${format === "json" ? "json" : "md"}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    notice(e.message);
  }
}
function settings() {
  dialog(
    `<h2>Workspace settings</h2><p>Demo replay works without credentials. Enable live mode with <code>ENABLE_LIVE=1</code> and configure provider keys in the server’s <code>.env</code> file.</p><p>Live mode is <strong>${config.live_enabled ? "enabled" : "disabled"}</strong>. Model selections are restricted to this server’s configuration.</p>${config.providers.map((p) => `<div class="settings-provider"><span>${esc(p.label)}<br><small>${esc(p.model)}</small></span><span class="${p.available ? "ready" : ""}">${p.available ? "Configured" : "Not configured"}</span></div>`).join("")}${config.auth_required ? '<label for="access-token">Workspace access token</label><input id="access-token" type="password" autocomplete="off" placeholder="Stored in memory for this page only"><button id="save-token" class="primary-button">Unlock workspace</button>' : "<p>This is a local workspace. Set <code>ROOM_API_TOKEN</code> before exposing live mode to a network.</p>"}`,
  );
  $("#save-token")?.addEventListener("click", async () => {
    token = $("#access-token").value;
    try {
      await api("/api/decisions");
      $("#info-dialog").close();
      loadHistory();
      notice("");
    } catch (e) {
      token = "";
      $("#access-token").setCustomValidity(e.message);
      $("#access-token").reportValidity();
    }
  });
  $("#access-token")?.addEventListener("input", () =>
    $("#access-token").setCustomValidity(""),
  );
}
function howItWorks() {
  dialog(
    "<h2>A room with a method.</h2><ol><li><strong>Independent analysis.</strong> Three roles see your brief, but not each other’s answers. Models can request validated cost and scoring tools.</li><li><strong>Challenge and refine.</strong> Each role reads the initial positions, challenges one point, acknowledges another, and revises its recommendation.</li><li><strong>A decision memo.</strong> An editor summarizes the recommendation, disagreements, weighted comparison, and next actions.</li></ol><p>Agreement between models is not proof. Scores are subjective. Use the result to guide your own judgment.</p><p>The demo uses curated examples and real Python calculations. Live mode calls your selected providers. Activity & usage exposes each call; JSON export includes the full record.</p>",
  );
}
async function init() {
  try {
    config = await (await api("/api/config")).json();
    const available = config.providers
      .filter((p) => p.available)
      .map((p) => p.id);
    chosenModels = chosenModels.map((p, i) =>
      available.includes(p)
        ? p
        : available[i % Math.max(1, available.length)] || "openai",
    );
    $("#examples").innerHTML = config.scenarios
      .map(
        (s) =>
          `<button type="button" class="example-button" data-scenario="${s.id}">${esc(s.label)} ↗</button>`,
      )
      .join("");
    document
      .querySelectorAll(".example-button")
      .forEach((b) =>
        b.addEventListener("click", () => setScenario(b.dataset.scenario)),
      );
    setMode("demo");
    await loadHistory();
    if (config.auth_required) settings();
  } catch (e) {
    notice(`Unable to connect to the workspace: ${e.message}`);
    $("#run-button").disabled = true;
  }
}
$("#decision-form").addEventListener("submit", run);
$("#demo-mode").addEventListener("click", () => setMode("demo"));
$("#live-mode").addEventListener("click", () => setMode("live"));
$("#cancel-button").addEventListener("click", () => controller?.abort());
$("#new-button").addEventListener("click", newDecision);
$("#new-sidebar").addEventListener("click", newDecision);
$("#workspace-nav").addEventListener("click", newDecision);
$("#settings-button").addEventListener("click", () => config && settings());
$("#how-button").addEventListener("click", howItWorks);
$(".dialog-close").addEventListener("click", () => $("#info-dialog").close());
$("#export-md").addEventListener("click", () => download("markdown"));
$("#export-json").addEventListener("click", () => download("json"));
document
  .querySelectorAll("[data-tab]")
  .forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
$(".results-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const tabs = ["overview", "deliberation", "activity"];
  let i = tabs.indexOf(activeTab);
  i =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? 2
        : (i + (event.key === "ArrowRight" ? 1 : 2)) % 3;
  setTab(tabs[i]);
  $(`#tab-${tabs[i]}`).focus();
});
document.addEventListener("keydown", (e) => {
  if (
    (e.metaKey || e.ctrlKey) &&
    e.key === "Enter" &&
    !$("#setup").closest(".showing-results") &&
    !controller
  ) {
    e.preventDefault();
    $("#decision-form").requestSubmit();
  }
});
init();
