/* Atlas — local-first data intelligence. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const charts = window.AtlasCharts;
  const fmt = charts.fmt;
  const esc = charts.escape;

  /* ------------------------------------------------------------------ */
  /* Icons                                                               */
  /* ------------------------------------------------------------------ */
  const PATHS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M9 9v11"/>',
    sparkles: '<path d="M12 3l1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7L12 3z"/><path d="M18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z"/>',
    chart: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M7 15l3.5-4 3 2.5L20 7"/>',
    shield: '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    file: '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    upload: '<path d="M12 16V4"/><path d="M8 8l4-4 4 4"/><path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3"/>',
    settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2.4"/><circle cx="8" cy="17" r="2.4"/>',
    chevron: '<path d="M9 6l6 6-6 6"/>',
    arrow: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 011-1h10"/>',
    download: '<path d="M12 4v11"/><path d="M8 11l4 4 4-4"/><path d="M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2"/>',
    trash: '<path d="M4 7h16"/><path d="M9 7V5h6v2"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v5M14 11v5"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    alert: '<path d="M12 4l9 16H3L12 4z"/><path d="M12 10v4M12 17.2v.2"/>',
    database: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/><path d="M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    play: '<path d="M7 5l11 7-11 7V5z"/>',
    refresh: '<path d="M20 11a8 8 0 10-2.2 5.6"/><path d="M20 4v7h-7"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    external: '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 13v6a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h6"/>',
    terminal: '<path d="M4 5h16a1 1 0 011 1v12a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1z"/><path d="M7 9l3 3-3 3M13 15h4"/>',
    message: '<path d="M21 12a8 8 0 01-8 8H5l-2 2V12a8 8 0 018-8h2a8 8 0 018 8z"/>',
    activity: '<path d="M3 12h4l2.5-7 4 14 2.5-7h5"/>',
    columns: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M10 4v16M16 4v16"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    moon: '<path d="M20 14.5A8 8 0 1110.5 4a7 7 0 009.5 10.5z"/>',
    arrowUp: '<path d="M12 19V5"/><path d="M6 11l6-6 6 6"/>',
    arrowDown: '<path d="M12 5v14"/><path d="M18 13l-6 6-6-6"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5"/><path d="M3 16l9 5 9-5"/>',
  };

  function icon(name, size = 14) {
    const path = PATHS[name] || PATHS.grid;
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  }

  /* ------------------------------------------------------------------ */
  /* Helpers                                                             */
  /* ------------------------------------------------------------------ */
  const VIEWS = ["overview", "explore", "ask", "forecast", "quality", "report"];
  const VIEW_META = {
    overview: { label: "Overview", icon: "grid" },
    explore: { label: "Explore", icon: "terminal" },
    ask: { label: "Ask Atlas", icon: "sparkles" },
    forecast: { label: "Forecast", icon: "chart" },
    quality: { label: "Quality", icon: "shield" },
    report: { label: "Report", icon: "file" },
  };
  const KIND_META = {
    anomaly: { label: "Anomaly", cls: "amber" },
    driver: { label: "Driver", cls: "" },
    association: { label: "Association", cls: "violet" },
    correlation: { label: "Relationship", cls: "blue" },
    concentration: { label: "Concentration", cls: "blue" },
    trend: { label: "Trend", cls: "" },
    efficiency: { label: "Efficiency", cls: "violet" },
  };

  function titleCase(text) {
    return String(text || "").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function prettyName(name) {
    return titleCase(String(name || "dataset").replace(/[_-]+/g, " ").replace(/\.[a-z0-9]+$/i, "").trim());
  }

  function pct(value, digits = 1) {
    const n = Number(value);
    return Number.isFinite(n) ? `${n.toFixed(digits)}%` : "—";
  }

  function humanBytes(bytes) {
    let n = Number(bytes) || 0;
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${i === 0 ? Math.round(n) : n.toFixed(1)} ${units[i]}`;
  }

  function period(value) {
    if (!value) return "—";
    const text = String(value).replace("T00:00:00", "").slice(0, 10);
    const m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return text;
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${months[Number(m[2]) - 1]} ${m[1]}`;
  }

  function dateTime(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
    } catch { return String(value); }
  }

  function relTime(ms) {
    if (!Number.isFinite(Number(ms))) return "—";
    const n = Number(ms);
    return n < 1000 ? `${Math.round(n)} ms` : `${(n / 1000).toFixed(1)} s`;
  }

  function safe(value) {
    return value === null || value === undefined || value === "";
  }

  function displayCell(value) {
    if (value === null || value === undefined) return '<span class="faint">null</span>';
    if (typeof value === "number") return esc(Number.isInteger(value) ? value.toLocaleString("en-US") : value.toLocaleString("en-US", { maximumFractionDigits: 3 }));
    if (typeof value === "boolean") return value ? "true" : "false";
    const text = String(value);
    if (/^\d{4}-\d{2}-\d{2}(T00:00:00)?$/.test(text)) return esc(period(text));
    return esc(text.length > 90 ? `${text.slice(0, 89)}…` : text);
  }

  function measureCols(profile) { return (profile?.columns || []).filter((c) => c.role === "measure"); }
  function dimCols(profile) { return (profile?.columns || []).filter((c) => c.role === "dimension" && !["date", "datetime"].includes(c.semantic)); }
  function timeCols(profile) { return (profile?.columns || []).filter((c) => c.role === "time"); }
  function labelOf(col) { return col?.label || prettyName(col?.name); }

  function tableHTML(columns, rows, opts = {}) {
    const limit = opts.limit || rows.length;
    const slice = rows.slice(0, limit);
    const numeric = new Set();
    columns.forEach((c, i) => {
      const vals = slice.map((r) => r[i]).filter((v) => v !== null && v !== undefined && v !== "");
      if (vals.length && vals.every((v) => typeof v === "number" || (!Number.isNaN(Number(v)) && typeof v !== "boolean"))) numeric.add(i);
    });
    let html = '<div class="table-scroll"><table class="data"><thead><tr>';
    columns.forEach((c) => { html += `<th class="${numeric.has(columns.indexOf(c)) ? "num" : ""}">${esc(prettyName(c))}</th>`; });
    html += "</tr></thead><tbody>";
    if (!slice.length) {
      html += `<tr><td colspan="${columns.length}" class="faint" style="text-align:center;padding:24px">No rows returned.</td></tr>`;
    }
    slice.forEach((row) => {
      html += "<tr>";
      columns.forEach((_, i) => {
        const value = row[i];
        const isNum = numeric.has(i) && value !== null;
        html += `<td class="${isNum ? "num" : ""} ${safe(value) ? "null" : ""}" title="${esc(value ?? "null")}">${displayCell(value)}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    if (opts.meta !== false) {
      html += `<div class="table-meta"><span>${slice.length.toLocaleString()} ${slice.length === 1 ? "row" : "rows"} shown</span>${opts.note ? `<span>${esc(opts.note)}</span>` : ""}${opts.actions || ""}</div>`;
    }
    return html;
  }

  function downloadCSV(filename, columns, rows) {
    const escape = (v) => {
      if (v === null || v === undefined) return "";
      const s = String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [columns.map(escape).join(",")];
    rows.forEach((row) => lines.push(row.map(escape).join(",")));
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied to clipboard", "ok");
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      toast("Copied to clipboard", "ok");
    }
  }

  function toast(message, kind = "ok", ms = 3400) {
    const root = $("#toasts");
    if (!root) return;
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.innerHTML = `<span class="toast-icon">${icon(kind === "error" ? "alert" : "check", 14)}</span><span>${esc(message)}</span>`;
    root.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateY(6px)"; setTimeout(() => el.remove(), 220); }, ms);
  }

  function skeleton(height = 120, style = "") {
    return `<div class="skeleton" style="height:${height}px;${style}"></div>`;
  }

  function spinnerLabel(text) {
    return `<span style="display:inline-flex;align-items:center;gap:8px"><span class="spinner"></span>${esc(text)}</span>`;
  }

  /* ------------------------------------------------------------------ */
  /* API                                                                 */
  /* ------------------------------------------------------------------ */
  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, { ...options, headers });
    const type = response.headers.get("content-type") || "";
    let data;
    if (type.includes("application/json")) data = await response.json();
    else data = await response.text();
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      let detail = data;
      if (data && typeof data === "object") {
        const d = data.detail;
        if (typeof d === "string") message = d;
        else if (d && typeof d === "object") message = d.error || d.detail || message;
        else if (data.error) message = data.error;
      } else if (typeof data === "string" && data.trim()) {
        message = data.slice(0, 300);
      }
      const error = new Error(message);
      error.status = response.status;
      error.payload = detail;
      throw error;
    }
    return data;
  }

  const getJSON = (path) => api(path);
  const postJSON = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
  const putJSON = (path, body) => api(path, { method: "PUT", body: JSON.stringify(body) });
  const del = (path) => api(path, { method: "DELETE" });

  /* ------------------------------------------------------------------ */
  /* State                                                               */
  /* ------------------------------------------------------------------ */
  const state = {
    datasets: [],
    dataset: null,
    view: "overview",
    health: null,
    settings: null,
    loadingDataset: false,
    chats: {},
    forecast: {},
    forecastParams: {},
    forecastLoading: false,
    forecastAuto: {},
    anomalies: {},
    anomaliesLoading: false,
    explore: {},
    streaming: false,
    activeRun: null,
    modalOpen: false,
    sidebarOpen: false,
    runSeq: 0,
  };

  function chatFor(id) {
    if (!state.chats[id]) state.chats[id] = [];
    return state.chats[id];
  }

  function exploreFor(id) {
    if (!state.explore[id]) {
      state.explore[id] = {
        sql: "SELECT * FROM {table} LIMIT 50",
        result: null,
        error: null,
        mode: "table",
        running: false,
      };
    }
    return state.explore[id];
  }

  function currentRun() {
    const chat = state.dataset ? chatFor(state.dataset.id) : [];
    for (let i = chat.length - 1; i >= 0; i--) if (chat[i].role === "run") return chat[i];
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* Routing                                                             */
  /* ------------------------------------------------------------------ */
  function parseHash() {
    const match = location.hash.match(/^#\/d\/([^/]+)\/([a-z]+)/);
    if (!match) return {};
    return { id: decodeURIComponent(match[1]), view: match[2] };
  }

  function setHash(id, view) {
    const target = `#/d/${encodeURIComponent(id)}/${view}`;
    if (location.hash !== target) history.replaceState(null, "", target);
  }

  async function navigate(view, opts = {}) {
    if (!VIEWS.includes(view)) view = "overview";
    if (!state.dataset) return;
    if (view === state.view && !opts.force) {
      if (view === "ask" && opts.focus) focusComposer();
      return;
    }
    state.view = view;
    setHash(state.dataset.id, view);
    localStorage.setItem("atlas.view", view);
    renderTabs();
    await renderView();
    if (view === "ask" && opts.focus) setTimeout(focusComposer, 30);
  }

  async function selectDataset(id, opts = {}) {
    if (!id || (state.dataset && state.dataset.id === id && !opts.force)) return;
    state.loadingDataset = true;
    renderSidebar();
    renderView();
    try {
      const dataset = await getJSON(`/api/datasets/${encodeURIComponent(id)}`);
      state.dataset = dataset;
      state.view = VIEWS.includes(opts.view) ? opts.view : "overview";
      localStorage.setItem("atlas.dataset", id);
      setHash(id, state.view);
      renderSidebar();
      renderTopbar();
      renderTabs();
      await renderView();
    } catch (error) {
      toast(error.message, "error");
      const first = state.datasets.find((d) => d.id !== id);
      if (first) return selectDataset(first.id, { view: state.view });
      state.dataset = null;
      renderShell();
    } finally {
      state.loadingDataset = false;
      renderSidebar();
    }
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                                */
  /* ------------------------------------------------------------------ */
  async function boot() {
    try {
      const [health, datasets, settings] = await Promise.all([
        getJSON("/api/health"),
        getJSON("/api/datasets"),
        getJSON("/api/settings"),
      ]);
      state.health = health;
      state.datasets = datasets.datasets || [];
      state.settings = settings;
      const hash = parseHash();
      const saved = localStorage.getItem("atlas.dataset");
      const chosen = state.datasets.find((d) => d.id === hash.id)
        || state.datasets.find((d) => d.id === saved)
        || state.datasets[0];
      if (chosen) {
        const view = VIEWS.includes(hash.view) ? hash.view : (VIEWS.includes(localStorage.getItem("atlas.view")) ? localStorage.getItem("atlas.view") : "overview");
        await selectDataset(chosen.id, { view });
      } else {
        state.dataset = null;
        state.view = "overview";
        renderShell();
      }
    } catch (error) {
      $("#boot").innerHTML = `<div style="max-width:420px;text-align:center;padding:24px"><div class="boot-mark" style="margin:0 auto 18px">A</div><h2 style="font-size:16px;margin-bottom:8px">Atlas could not reach its local service</h2><p class="muted" style="font-size:12px;line-height:1.6">${esc(error.message)}</p><button class="btn primary" style="margin-top:16px" onclick="location.reload()">Retry</button></div>`;
      return;
    }
    setTimeout(() => $("#boot")?.classList.add("hide"), 250);
  }

  /* ------------------------------------------------------------------ */
  /* Shell                                                               */
  /* ------------------------------------------------------------------ */
  function renderShell() {
    renderSidebar();
    renderTopbar();
    renderTabs();
    renderView();
  }

  function llmMeta() {
    const s = state.settings;
    if (!s || !s.llm_enabled) return { on: false, label: "Local engine", sub: "deterministic · no API key" };
    const provider = s.provider === "ollama" ? "Ollama" : "OpenAI";
    return { on: true, label: provider, sub: s.model || "model ready" };
  }

  function renderSidebar() {
    const el = $("#sidebar");
    if (!el) return;
    const meta = llmMeta();
    const datasets = state.datasets || [];
    el.innerHTML = `
      <a class="brand" href="/" title="Back to the Atlas landing page">
        <div class="brand-mark">A</div>
        <div><div class="brand-word">ATLAS</div><div class="brand-sub">Data intelligence</div></div>
      </a>
      <div class="side-section">
        <div class="side-label"><span>Workspace</span><button data-action="upload-open" title="Add a dataset" aria-label="Add a dataset">${icon("plus", 14)}</button></div>
        <div class="ds-list">
          ${datasets.length ? datasets.map((d) => `
            <button class="ds-item ${state.dataset?.id === d.id ? "active" : ""}" data-dataset="${esc(d.id)}">
              <span class="ds-icon">${icon("database", 13)}</span>
              <span><span class="ds-name">${esc(d.name)}</span><span class="ds-meta">${Number(d.rows || 0).toLocaleString()} rows · ${d.cols || 0} cols</span></span>
              ${d.grade ? `<span class="ds-grade">${esc(d.grade)}</span>` : ""}
            </button>`).join("") : '<div class="faint" style="font-size:10.5px;padding:8px">No datasets yet.</div>'}
        </div>
      </div>
      <div class="side-drop" data-action="upload-open">
        <strong>Drop a file to analyse</strong>
        CSV, Excel, JSON or Parquet
      </div>
      <div class="side-spacer"></div>
      <div class="side-footer">
        <div class="side-label" style="padding:0 8px 6px;margin:0"><span>Engine</span></div>
        <button class="llm-row" data-action="settings-open">
          <span class="status-dot ${meta.on ? "on" : ""}"></span>
          <span><span class="llm-label">${esc(meta.label)}</span><span class="llm-sub">${esc(meta.sub)}</span></span>
          <span style="margin-left:auto;color:var(--faint)">${icon("settings", 13)}</span>
        </button>
        <div class="side-version">ATLAS v${esc(state.health?.version || "1.0")} · ${Number(state.health?.datasets || 0)} datasets</div>
      </div>
    `;
  }

  function renderTopbar() {
    const el = $("#topbar");
    if (!el) return;
    const d = state.dataset;
    const meta = llmMeta();
    if (!d) {
      el.innerHTML = `<button class="icon-btn mobile-menu" data-action="sidebar-toggle">${icon("menu", 18)}</button><div class="crumbs"><span class="crumb-dot"></span><span class="crumb-name">Atlas</span></div><div class="top-actions"><button class="btn" data-action="upload-open">${icon("upload", 13)} Add data</button></div>`;
      return;
    }
    const quality = d.profile?.quality || {};
    el.innerHTML = `
      <button class="icon-btn mobile-menu" data-action="sidebar-toggle" aria-label="Menu">${icon("menu", 18)}</button>
      <div class="crumbs">
        <span class="crumb-dot"></span>
        <span class="crumb-name">${esc(d.name)}</span>
        <span class="crumb-meta">${Number(d.rows || 0).toLocaleString()} rows · ${d.cols || 0} columns · ${esc(quality.grade || "—")} quality</span>
      </div>
      <div class="top-actions">
        <span class="kbd-hint" title="Keyboard shortcut">${icon("search", 11)}<kbd>⌘K</kbd></span>
        <button class="btn ${state.view === "ask" ? "" : "primary"}" data-action="go-ask">${icon("sparkles", 13)} Ask Atlas</button>
        <button class="icon-btn" data-action="settings-open" title="Settings">${icon("settings", 15)}</button>
      </div>
    `;
  }

  function renderTabs() {
    const el = $("#tabs");
    if (!el) return;
    if (!state.dataset) { el.innerHTML = ""; return; }
    el.innerHTML = VIEWS.map((view) => {
      const meta = VIEW_META[view];
      return `<button class="tab ${state.view === view ? "active" : ""}" data-view="${view}">${icon(meta.icon, 13)}${meta.label}</button>`;
    }).join("");
  }

  async function renderView() {
    const el = $("#view");
    if (!el) return;
    el.scrollTop = 0;
    if (state.loadingDataset && !state.dataset) {
      el.innerHTML = `<div class="view-inner">${skeleton(34, "width:280px;margin-bottom:14px")}${skeleton(64, "width:60%;margin-bottom:28px")}<div class="kpi-grid">${skeleton(90)}${skeleton(90)}${skeleton(90)}${skeleton(90)}</div><div style="margin-top:18px">${skeleton(220)}</div></div>`;
      return;
    }
    if (!state.dataset) {
      el.innerHTML = emptyWorkspace();
      bindWorkspace();
      return;
    }
    if (state.view === "overview") el.innerHTML = renderOverview();
    else if (state.view === "explore") el.innerHTML = renderExplore();
    else if (state.view === "ask") el.innerHTML = renderAsk();
    else if (state.view === "forecast") el.innerHTML = renderForecast();
    else if (state.view === "quality") el.innerHTML = renderQuality();
    else if (state.view === "report") el.innerHTML = renderReport();
    bindView();
  }

  function emptyWorkspace() {
    return `
      <div class="view-inner">
        <div class="ask-empty" style="padding-top:12vh">
          <div class="ask-hero">
            <div class="page-kicker"><span class="dot"></span> Local-first intelligence</div>
            <h1>Your data,<br><em>understood.</em></h1>
            <p>Atlas profiles a file, finds the signals that matter, and answers questions in plain language. Everything stays on this machine.</p>
            <div style="display:flex;gap:9px;margin-top:24px;flex-wrap:wrap">
              <button class="btn primary lg" data-action="upload-open">${icon("upload", 15)} Add a dataset</button>
              <button class="btn lg" data-action="upload-open">${icon("file", 15)} CSV, Excel, JSON, Parquet</button>
            </div>
          </div>
        </div>
      </div>`;
  }

  function bindWorkspace() {
    // global delegation covers actions
  }

  /* ------------------------------------------------------------------ */
  /* Overview                                                            */
  /* ------------------------------------------------------------------ */
  function qualityScore() {
    return Number(state.dataset?.profile?.quality?.score || 0);
  }

  function suggestQuestions(dataset) {
    const profile = dataset?.profile || {};
    const measures = measureCols(profile);
    const dims = dimCols(profile);
    const time = timeCols(profile);
    const booleans = (profile.columns || []).filter((c) => c.semantic === "boolean");
    const out = [];
    const m = measures[0];
    const m2 = measures[1];
    const d = dims.find((x) => x.semantic === "category") || dims[0];
    const d2 = dims.find((x) => x.name !== d?.name && x.semantic === "category");
    const b = booleans[0];
    if (b && d) out.push(`Which ${labelOf(d).toLowerCase()} has the highest ${labelOf(b).toLowerCase()} rate?`);
    if (m && d) out.push(`Which ${labelOf(d).toLowerCase()} has the highest ${labelOf(m).toLowerCase()}?`);
    if (m && time.length) out.push(`How has ${labelOf(m).toLowerCase()} changed over time?`);
    if (m) out.push(`Show ${labelOf(m).toLowerCase()} distribution`);
    if (m && m2) out.push(`What is the correlation between ${labelOf(m).toLowerCase()} and ${labelOf(m2).toLowerCase()}?`);
    if (d && d2) out.push(`Compare records by ${labelOf(d2).toLowerCase()}`);
    out.push("How many rows are there?");
    return [...new Set(out)].slice(0, 4);
  }

  function insightQuestion(insight) {
    const cols = (insight.columns || []).map((c) => {
      const found = (state.dataset?.profile?.columns || []).find((x) => x.name === c);
      return found ? labelOf(found) : prettyName(c);
    });
    if (insight.kind === "correlation" && cols.length >= 2) return `What is the correlation between ${cols[0].toLowerCase()} and ${cols[1].toLowerCase()}?`;
    if (insight.kind === "trend" && cols.length >= 2) return `How has ${cols[1].toLowerCase()} changed over time?`;
    if (insight.kind === "anomaly" && cols.length >= 2) return `How has ${cols[1].toLowerCase()} changed over time?`;
    if (["driver", "concentration", "efficiency"].includes(insight.kind) && cols.length >= 2) return `Which ${cols[0].toLowerCase()} has the highest ${cols[1].toLowerCase()}?`;
    return `How many rows are there?`;
  }

  function renderOverview() {
    const d = state.dataset;
    const profile = d.profile || {};
    const quality = profile.quality || {};
    const insights = d.insights || [];
    const time = profile.time;
    const measures = measureCols(profile);
    const dims = dimCols(profile);
    const completeness = quality.dimensions?.completeness ?? 0;
    const questions = suggestQuestions(d);
    const previewState = state.preview || {};
    const topIssues = (quality.issues || []).slice(0, 3);
    const notes = d.notes || [];

    return `
      <div class="view-inner">
        <div class="page-head">
          <div>
            <div class="page-kicker"><span class="dot"></span> Dataset overview</div>
            <h1 class="page-title">${esc(d.name)}</h1>
            <p class="page-sub">${Number(d.rows || 0).toLocaleString()} rows profiled across ${d.cols || 0} columns${time ? ` · ${period(time.min)} → ${period(time.max)}` : ""} · ${measures.length} measures, ${dims.length} dimensions.</p>
          </div>
          <div class="page-actions">
            <button class="btn" data-action="refresh-insights">${icon("refresh", 13)} Re-scan</button>
            <button class="btn" data-action="open-report">${icon("file", 13)} Report</button>
            <button class="icon-btn danger" data-action="delete-dataset" title="Delete dataset">${icon("trash", 14)}</button>
          </div>
        </div>

        <div class="kpi-grid">
          <div class="kpi"><div class="kpi-label">Rows analysed</div><div class="kpi-value">${Number(d.rows || 0).toLocaleString()}</div><div class="kpi-foot">${Number(profile.duplicate_rows || 0).toLocaleString()} duplicate rows</div></div>
          <div class="kpi"><div class="kpi-label">Columns profiled</div><div class="kpi-value">${d.cols || 0}</div><div class="kpi-foot">${measures.length} measures · ${dims.length} dimensions</div></div>
          <div class="kpi"><div class="kpi-label">Quality score</div><div class="kpi-value">${qualityScore().toFixed(1)}<small>/ 100</small></div><div class="kpi-foot"><span class="up">${esc(quality.grade || "—")}</span> grade · ${completeness.toFixed(1)}% complete</div></div>
          <div class="kpi"><div class="kpi-label">${time ? "Time coverage" : "Signals found"}</div><div class="kpi-value" style="font-size:${time ? "20px" : "25px"};margin-top:10px">${time ? `${period(time.min)} → ${period(time.max)}` : insights.length}</div><div class="kpi-foot">${time ? `${Number(time.periods || 0).toLocaleString()} ${time.granularity || "period"}s · ${time.column}` : "ranked by effect size"}</div></div>
        </div>

        <div class="section-head"><h2>What stands out <span class="count">${insights.length}</span></h2><span class="aside">Ranked by effect size and statistical support</span></div>
        ${insights.length ? `<div class="insight-grid">${insights.slice(0, 6).map(insightCard).join("")}</div>` : `<div class="empty"><div class="empty-icon">${icon("activity", 18)}</div><h3>No strong signals</h3><p>Atlas could not find a pattern that clears its significance thresholds. The data may be uniform, small, or mostly text.</p></div>`}

        <div class="grid-2" style="margin-top:14px">
          <div class="card card-pad">
            <div class="section-head" style="margin:0 0 14px"><h2>Ask this dataset</h2><span class="aside">Deterministic answers, grounded in the rows</span></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              ${questions.map((q) => `<button class="followup" data-question="${esc(q)}">${esc(q)}</button>`).join("")}
            </div>
            <div style="display:flex;gap:8px;margin-top:14px">
              <input class="input" id="overview-ask" placeholder="Or type your own question…" maxlength="500">
              <button class="btn primary" data-action="overview-ask">${icon("sparkles", 13)} Ask</button>
            </div>
          </div>
          <div class="card card-pad">
            <div class="section-head" style="margin:0 0 12px"><h2>Data quality</h2><span class="tag ${qualityScore() >= 85 ? "" : "amber"}">${esc(quality.grade || "—")}</span></div>
            <div style="display:flex;gap:16px;align-items:center">
              <div class="score-ring" style="--score:${qualityScore()};width:76px;height:76px;flex:0 0 76px"><div class="score-ring-inner"><div class="score-ring-value" style="font-size:20px">${qualityScore().toFixed(0)}</div></div></div>
              <div style="flex:1;min-width:0">
                ${Object.entries(quality.dimensions || {}).slice(0, 2).map(([k, v]) => `<div class="dim-row" style="grid-template-columns:74px 1fr 36px;margin-bottom:9px"><span class="dim-name">${titleCase(k)}</span><span class="dim-track"><span class="dim-fill" style="width:${Math.max(0, Math.min(100, Number(v)))}%"></span></span><span class="dim-val">${Number(v).toFixed(0)}%</span></div>`).join("")}
                <div class="faint" style="font-size:10.5px;line-height:1.5">${topIssues.length ? esc(topIssues[0].detail) : "No material issues detected."}</div>
              </div>
            </div>
            <div style="display:flex;gap:8px;margin-top:14px"><button class="btn sm" data-view="quality">Full quality report ${icon("arrow", 12)}</button></div>
          </div>
        </div>

        <div class="section-head"><h2>Schema</h2><span class="aside"><strong>${d.cols || 0}</strong> columns · click a column to inspect</span></div>
        <div class="table-wrap"><table class="data"><thead><tr><th>Column</th><th>Type</th><th>Role</th><th class="num">Missing</th><th class="num">Distinct</th><th>Sample</th></tr></thead><tbody>
          ${(profile.columns || []).map((c) => {
            const sample = (c.top_values || [])[0]?.value ?? (c.examples || [])[0] ?? "";
            return `<tr style="cursor:pointer" data-column="${esc(c.name)}">
              <td><strong style="color:var(--text-soft)">${esc(labelOf(c))}</strong>${c.pii ? ' <span class="tag rose" style="height:16px;font-size:8px">PII</span>' : ""}<div class="faint mono" style="font-size:9px;margin-top:2px">${esc(c.name)}</div></td>
              <td><span class="tag neutral" style="height:18px;font-size:8.5px">${esc(c.dtype)}</span></td>
              <td class="muted">${esc(c.role)}<div class="faint" style="font-size:9px">${esc(c.semantic)}</div></td>
              <td class="num">${Number(c.null_pct || 0).toFixed(1)}%</td>
              <td class="num">${Number(c.distinct || 0).toLocaleString()}</td>
              <td class="faint" style="max-width:240px;overflow:hidden;text-overflow:ellipsis">${esc(String(sample).slice(0, 60))}</td>
            </tr>`;
          }).join("")}
        </tbody></table></div>

        <div class="section-head"><h2>Preview</h2><span class="aside">${notes.length ? `<strong>${notes.length}</strong> cleaning note${notes.length === 1 ? "" : "s"}` : "first rows from the cleaned table"}</span></div>
        <div class="card" style="padding:0;overflow:hidden" id="preview-card">
          <div style="padding:16px" class="faint">${spinnerLabel("Loading preview")}</div>
        </div>
      </div>
    `;
  }

  function insightCard(insight) {
    const meta = KIND_META[insight.kind] || { label: titleCase(insight.kind || "Signal"), cls: "neutral" };
    const chart = insight.chart || {};
    const svg = chart.type ? charts.render(chart, { mini: true }) : "";
    return `
      <article class="insight-card" data-insight="${esc(insight.id)}">
        <div class="insight-top"><span class="tag ${meta.cls}">${esc(meta.label)}</span><span class="conf">${esc(insight.confidence || "medium")} confidence</span></div>
        <h3 class="insight-title">${esc(insight.title)}</h3>
        <div class="insight-detail">${esc(insight.detail)}</div>
        ${svg ? `<div class="insight-chart">${svg}</div>` : ""}
        <div class="insight-foot">
          <span class="score-bar"><span class="score-track"><span class="score-fill" style="width:${Math.max(0, Math.min(100, Number(insight.score) || 0))}%"></span></span>score ${Number(insight.score || 0).toFixed(0)}</span>
          <span class="faint">${icon("arrow", 12)}</span>
        </div>
      </article>`;
  }

  async function loadPreview() {
    const card = $("#preview-card");
    if (!card || !state.dataset) return;
    try {
      const result = await getJSON(`/api/datasets/${encodeURIComponent(state.dataset.id)}/preview?limit=8`);
      card.innerHTML = tableHTML(result.columns, result.rows, {
        meta: true,
        note: `${Number(result.total || 0).toLocaleString()} total rows`,
        actions: `<button class="btn sm ghost" data-view="explore" style="margin-left:auto">Open in Explore ${icon("arrow", 11)}</button>`,
      });
    } catch (error) {
      card.innerHTML = `<div style="padding:16px" class="faint">${esc(error.message)}</div>`;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Ask                                                                 */
  /* ------------------------------------------------------------------ */
  function renderAsk() {
    const d = state.dataset;
    const chat = chatFor(d.id);
    const questions = suggestQuestions(d);
    const run = currentRun();
    const traceRun = run || null;
    return `
      <div class="view-inner">
        <div class="ask-layout">
          <div class="ask-main">
            ${chat.length ? `<div class="chat">${chat.map((item) => {
              if (item.role === "user") return `<div class="msg-user">${esc(item.text)}</div>`;
              if (item.role === "run") return answerMessage(item);
              return "";
            }).join("")}</div>` : askHero(questions)}
            <form class="composer" id="ask-form">
              <div class="composer-inner">
                <textarea id="ask-input" rows="1" maxlength="500" placeholder="Ask anything about ${esc(d.name)}…" aria-label="Question"></textarea>
                <div class="composer-actions">
                  <button type="submit" class="btn primary" id="ask-send" ${state.streaming ? "disabled" : ""}>${state.streaming ? '<span class="spinner" style="border-top-color:#04201c"></span>' : icon("arrow", 14)} ${state.streaming ? "Working" : "Ask"}</button>
                </div>
              </div>
              <div class="composer-hint">
                <span class="left"><span><kbd>Enter</kbd> to send</span><span><kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line</span></span>
                <span>${state.settings?.llm_enabled ? "Model polish enabled · numbers verified" : "Deterministic engine · no API key"}</span>
              </div>
            </form>
          </div>
          <aside class="trace-panel ${run?.streaming ? "running" : ""}" id="trace-panel">${tracePanel(run)}</aside>
        </div>
      </div>
    `;
  }

  function askHero(questions) {
    return `
      <div class="ask-empty">
        <div class="ask-hero">
          <div class="page-kicker"><span class="dot"></span> Ask Atlas</div>
          <h1>Interrogate<br><em>${esc(state.dataset.name)}.</em></h1>
          <p>Plain-language questions become read-only SQL, then charts and a grounded summary. No sampling tricks, no invented numbers.</p>
        </div>
        <div class="prompt-grid">
          ${questions.map((q, i) => `<button class="prompt-chip" data-question="${esc(q)}"><span style="flex:0 0 14px">${icon(i === 0 ? "sparkles" : i === 1 ? "chart" : i === 2 ? "activity" : "search", 14)}</span><span><span>${["Start here", "Break it down", "Over time", "Explore"][i] || "Explore"}</span>${esc(q)}</span></button>`).join("")}
        </div>
      </div>`;
  }

  function answerMessage(run) {
    if (run.streaming) {
      const last = run.steps[run.steps.length - 1];
      return `<div class="msg-atlas"><div class="answer-card" style="padding:16px 19px"><div class="stream-status"><span class="spinner"></span><span id="ask-status">${esc(last?.label || "Reading the dataset")}</span></div><div class="skeleton" style="height:8px;width:72%;margin:12px 0 8px"></div><div class="skeleton" style="height:8px;width:52%"></div></div></div>`;
    }
    if (run.error) {
      return `<div class="msg-atlas"><div class="answer-card" style="padding:17px 19px"><div class="answer-kicker" style="color:var(--rose)">${icon("alert", 12)} Analysis stopped</div><h3 class="answer-title" style="font-size:15px">${esc(run.error)}</h3>${run.hint ? `<p class="narrative" style="margin-top:7px;color:var(--muted)">${esc(run.hint)}</p>` : ""}${run.detail ? `<details style="margin-top:10px"><summary class="faint" style="font-size:10.5px;cursor:pointer">Technical detail</summary><pre class="sql-code" style="margin-top:8px">${esc(run.detail)}</pre></details>` : ""}</div></div>`;
    }
    if (!run.answer) return "";
    const a = run.answer;
    const chart = a.chart || {};
    const meta = KIND_META[a.plan?.intent] || null;
    const confidence = a.confidence || {};
    const svg = chart.type && chart.type !== "table" ? charts.render(chart, { mini: false }) : "";
    const table = chart.type === "table" ? tableHTML(chart.columns || [], chart.rows || [], { meta: true, limit: 40 }) : "";
    return `
      <div class="msg-atlas">
        <div class="answer-card">
          <div class="answer-head">
            <div>
              <div class="answer-kicker"><span class="dot"></span> ${esc(a.engine === "llm" ? "Model-assisted plan" : "Deterministic plan")}${a.plan?.intent ? ` · ${esc(titleCase(a.plan.intent.replace(/_/g, " ")))}` : ""}</div>
              <h3 class="answer-title">${esc(a.plan?.title || a.question)}</h3>
            </div>
            <span class="tag ${confidence.label === "high" ? "" : confidence.label === "low" ? "rose" : "amber"}">${esc(confidence.label || "medium")} confidence</span>
          </div>
          <div class="answer-body">
            <p class="narrative">${esc(a.narrative || "")}</p>
            ${svg ? `<div class="answer-chart">${svg}</div>` : ""}
            ${table}
            ${a.highlights?.length ? `<div class="highlights">${a.highlights.map((h) => `<span class="highlight">${esc(h)}</span>`).join("")}</div>` : ""}
            ${a.caveats?.length ? `<div class="caveats">${a.caveats.map((c) => `<div class="caveat">${icon("alert", 12)}<span>${esc(c)}</span></div>`).join("")}</div>` : ""}
            <div class="sql-block hidden" id="sql-${run.id}">
              <div class="sql-head"><span>DuckDB · read-only</span><button class="btn sm ghost" data-copy-sql="${run.id}">${icon("copy", 11)} Copy</button></div>
              <pre class="sql-code">${esc(a.sql || "")}</pre>
            </div>
          </div>
          <div class="answer-foot">
            <button class="btn sm ghost" data-toggle-sql="${run.id}">${icon("terminal", 12)} SQL</button>
            <button class="btn sm ghost" data-answer-csv="${run.id}">${icon("download", 12)} CSV</button>
            <span class="conf-chip"><span class="bar"><span class="fill" style="width:${Math.round((confidence.score || 0) * 100)}%"></span></span>${Math.round((confidence.score || 0) * 100)}%</span>
            <span class="foot-spacer"></span>
            <span class="faint" style="font-size:9.5px">${Number(a.result?.row_count || 0).toLocaleString()} rows · ${relTime(a.elapsed_ms)}</span>
          </div>
        </div>
        ${a.followups?.length ? `<div class="followups" style="margin-top:8px">${a.followups.map((q) => `<button class="followup" data-question="${esc(q)}">${esc(q)}</button>`).join("")}</div>` : ""}
      </div>`;
  }

  function tracePanel(run) {
    const steps = run?.steps || [];
    const answer = run?.answer;
    const stats = answer ? `
      <div class="trace-stats">
        <div class="trace-stat"><div class="v">${relTime(answer.elapsed_ms)}</div><div class="k">Total time</div></div>
        <div class="trace-stat"><div class="v">${answer.attempts || 0}</div><div class="k">Query attempts</div></div>
        <div class="trace-stat"><div class="v">${answer.result?.row_count ?? "—"}</div><div class="k">Rows returned</div></div>
        <div class="trace-stat"><div class="v">${esc(answer.plan?.intent || "—")}</div><div class="k">Intent</div></div>
      </div>` : "";
    return `
      <div class="trace-head"><h3>Analysis trace</h3><span class="live">live</span></div>
      <div class="trace-body" id="trace-body">
        ${steps.length ? steps.map((step) => `
          <div class="trace-step ${step.status === "error" ? "error" : ""}">
            <span class="trace-icon">${icon(step.status === "error" ? "x" : "check", 9)}</span>
            <div><div class="trace-label">${esc(step.label)}</div>${step.detail ? `<div class="trace-detail" title="${esc(step.detail)}">${esc(step.detail)}</div>` : ""}</div>
            <span class="trace-ms">${Math.round(step.ms || 0)}ms</span>
          </div>`).join("") : `<div class="trace-idle">
            ${[
              ["sparkles", "Plan", "Resolve intent, columns and filters."],
              ["terminal", "Query", "Run read-only SQL with a hard row cap."],
              ["check", "Ground", "Verify every number against the result."],
            ].map(([name2, label, detail]) => `<div class="trace-step"><span class="trace-icon">${icon(name2, 8)}</span><div><div class="trace-label">${label}</div><div class="trace-detail">${detail}</div></div></div>`).join("")}
            <div class="trace-empty">Ask a question and this panel fills in live.</div>
          </div>`}
        ${stats}
      </div>`;
  }

  function focusComposer() {
    const input = $("#ask-input");
    if (input) {
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  async function askQuestion(question, opts = {}) {
    const q = String(question || "").trim();
    if (!q || state.streaming || !state.dataset) return;
    if (state.view !== "ask") await navigate("ask");
    const id = state.dataset.id;
    const chat = chatFor(id);
    chat.push({ role: "user", text: q });
    const run = {
      id: `run-${++state.runSeq}`,
      role: "run",
      question: q,
      steps: [],
      answer: null,
      error: null,
      hint: null,
      detail: null,
      streaming: true,
      started: performance.now(),
    };
    chat.push(run);
    state.streaming = true;
    state.activeRun = run;
    await renderView();
    scrollAskToBottom();
    await streamQuestion(id, q, run);
  }

  async function streamQuestion(datasetId, question, run) {
    try {
      const response = await fetch(`/api/datasets/${encodeURIComponent(datasetId)}/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!response.ok || !response.body) {
        let payload = null;
        try { payload = await response.json(); } catch { /* ignore */ }
        const detail = payload?.detail;
        throw Object.assign(new Error(detail?.error || detail || `Request failed (${response.status})`), { payload });
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      while (!finished) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index;
        while ((index = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          const frame = parseSSE(chunk);
          if (!frame) continue;
          handleFrame(frame, run);
          if (frame.event === "answer" || frame.event === "error") finished = true;
        }
      }
      if (run.streaming) {
        run.streaming = false;
        if (!run.answer && !run.error) {
          run.error = "The stream ended before an answer arrived.";
          run.hint = "Try the question again.";
        }
      }
    } catch (error) {
      run.streaming = false;
      run.error = error.message || "The question could not be answered.";
      const detail = error.payload?.detail;
      if (detail && typeof detail === "object") {
        run.hint = detail.hint || null;
        run.detail = detail.detail || null;
        run.answerSql = detail.sql || null;
      }
    } finally {
      run.streaming = false;
      state.streaming = false;
      state.activeRun = null;
      // ensure the run has a terminal state even on a malformed stream
      await renderView();
      scrollAskToBottom();
    }
  }

  function parseSSE(chunk) {
    let event = "message";
    const data = [];
    chunk.split(/\r?\n/).forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    });
    if (!data.length) return null;
    try {
      return { event, data: JSON.parse(data.join("\n")) };
    } catch {
      return { event, data: { text: data.join("\n") } };
    }
  }

  function handleFrame(frame, run) {
    if (frame.event === "step") {
      run.steps.push(frame.data);
      updateTraceLive(run);
      const status = $("#ask-status");
      if (status) status.textContent = frame.data.label || "Working";
    } else if (frame.event === "answer") {
      run.answer = frame.data;
      run.streaming = false;
    } else if (frame.event === "error") {
      run.streaming = false;
      run.error = frame.data.error || "The question could not be answered.";
      run.hint = frame.data.hint || null;
      run.detail = frame.data.detail || null;
    }
  }

  function updateTraceLive(run) {
    const panel = $("#trace-panel");
    if (!panel) return;
    panel.classList.toggle("running", !!run.streaming);
    panel.innerHTML = tracePanel(run);
  }

  function scrollAskToBottom() {
    const view = $("#view");
    if (!view) return;
    const toBottom = () => { view.scrollTop = view.scrollHeight; };
    requestAnimationFrame(() => {
      toBottom();
      requestAnimationFrame(toBottom);
    });
    // The chart is inline SVG and settles a beat after the card mounts.
    setTimeout(toBottom, 180);
  }

  /* ------------------------------------------------------------------ */
  /* Explore                                                             */
  /* ------------------------------------------------------------------ */
  function renderExplore() {
    const d = state.dataset;
    const ex = exploreFor(d.id);
    const profile = d.profile || {};
    return `
      <div class="view-inner">
        <div class="page-head">
          <div>
            <div class="page-kicker"><span class="dot"></span> SQL console</div>
            <h1 class="page-title">Explore the rows</h1>
            <p class="page-sub">Read-only DuckDB. Queries are capped and time-limited. Use <span class="mono">{table}</span> for this dataset; every identifier is quoted automatically in the examples.</p>
          </div>
          <div class="page-actions">
            <button class="btn" data-action="explore-preview">${icon("refresh", 13)} Preview</button>
            <button class="btn primary" data-action="explore-run">${icon("play", 13)} Run query</button>
          </div>
        </div>
        <div class="explore-layout">
          <div>
            <div class="editor-card">
              <div class="editor-head">
                <span class="editor-dots"><i></i><i></i><i></i></span>
                <span class="editor-title">query.sql</span>
                <div class="editor-actions">
                  <span class="faint" style="font-size:9.5px">⌘ / Ctrl + Enter</span>
                  <button class="btn sm" data-action="explore-run">${icon("play", 11)} Run</button>
                </div>
              </div>
              <textarea class="sql-editor" id="sql-editor" spellcheck="false" aria-label="SQL query">${esc(ex.sql)}</textarea>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:9px">
              <button class="followup" data-query="SELECT * FROM {table} LIMIT 50">Sample 50 rows</button>
              <button class="followup" data-query="SELECT COUNT(*) AS rows FROM {table}">Count rows</button>
              <button class="followup" data-query="SELECT * FROM {table} WHERE 1=0">Show schema</button>
              <span style="margin-left:auto;font-size:10px;color:var(--faint);align-self:center">${profile.rows?.toLocaleString() || 0} rows available</span>
            </div>
            <div class="section-head"><h2>Result</h2><span class="aside" id="explore-meta"></span></div>
            <div id="explore-result">${renderExploreResult()}</div>
          </div>
          <aside class="card card-pad" style="position:sticky;top:0">
            <div class="section-head" style="margin:0 0 10px"><h2>Columns</h2><span class="aside">${d.cols || 0}</span></div>
            <div class="schema-list">
              ${(profile.columns || []).map((c) => {
                const dot = c.role === "measure" ? "measure" : c.role === "time" ? "time" : c.role === "dimension" ? "dimension" : "id";
                return `<button class="schema-item" data-insert-col="${esc(c.name)}" title="Insert ${esc(c.name)}"><span class="type-dot ${dot}"></span><span class="schema-name">${esc(labelOf(c))}</span><span class="schema-type">${esc(c.dtype)}</span></button>`;
              }).join("")}
            </div>
            <div class="faint" style="font-size:9.5px;margin-top:12px;line-height:1.5">Click a column to append it to the editor. Results are limited by the server row cap.</div>
          </aside>
        </div>
      </div>
    `;
  }

  function renderExploreResult() {
    const ex = state.dataset ? exploreFor(state.dataset.id) : null;
    if (!ex) return "";
    if (ex.running) {
      return `<div class="card" style="padding:18px">${spinnerLabel("Running query")}</div>`;
    }
    if (ex.error) {
      return `<div class="card" style="padding:16px 18px;border-color:rgba(251,113,133,.3)"><div style="display:flex;gap:9px;color:var(--rose);font-size:12px;font-weight:600">${icon("alert", 14)} Query failed</div><pre class="sql-code" style="margin-top:9px;color:#e7b1ba">${esc(ex.error)}</pre></div>`;
    }
    if (!ex.result) {
      return `<div class="empty"><div class="empty-icon">${icon("terminal", 18)}</div><h3>Run a query</h3><p>Use the editor above. Atlas wraps every result with a hard row limit and a watchdog timeout.</p></div>`;
    }
    const r = ex.result;
    const twoCols = r.columns.length === 2 && r.rows.some((row) => typeof row[1] === "number");
    const modeToggle = twoCols ? `<div class="seg" style="margin-left:auto"><button class="${ex.mode === "table" ? "active" : ""}" data-explore-mode="table">Table</button><button class="${ex.mode === "chart" ? "active" : ""}" data-explore-mode="chart">Chart</button></div>` : "";
    const chart = ex.mode === "chart" && twoCols ? charts.bar(r.rows.map((row) => row[0]), r.rows.map((row) => row[1]), { format: "number" }) : "";
    return `
      <div class="card" style="padding:0;overflow:hidden">
        <div style="display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--line-soft)">
          <span class="tag neutral">${Number(r.row_count || 0).toLocaleString()} rows</span>
          <span class="faint" style="font-size:10px">${Number(r.elapsed_ms || 0).toFixed(1)} ms${r.truncated ? " · truncated" : ""}</span>
          ${modeToggle}
          <button class="btn sm ghost" data-export-explore>${icon("download", 11)} CSV</button>
        </div>
        ${chart ? `<div style="padding:12px 14px 0">${chart}</div>` : ""}
        ${ex.mode === "chart" && chart ? "" : tableHTML(r.columns, r.rows, { limit: 500, meta: false })}
        <div class="table-meta"><span>${r.truncated ? "Result truncated by the server limit." : "Complete result set."}</span><button class="btn sm ghost" style="margin-left:auto" data-copy-query>${icon("copy", 11)} Copy SQL</button></div>
      </div>`;
  }

  async function runExploreQuery() {
    const d = state.dataset;
    if (!d) return;
    const ex = exploreFor(d.id);
    const editor = $("#sql-editor");
    if (editor) ex.sql = editor.value;
    if (!ex.sql.trim()) { toast("Write a query first.", "error"); return; }
    ex.running = true;
    ex.error = null;
    const target = $("#explore-result");
    if (target) target.innerHTML = renderExploreResult();
    try {
      const result = await postJSON(`/api/datasets/${encodeURIComponent(d.id)}/query`, { sql: ex.sql, limit: 1000 });
      ex.result = result;
      ex.mode = "table";
    } catch (error) {
      ex.error = error.message;
      ex.result = null;
    } finally {
      ex.running = false;
      const resultTarget = $("#explore-result");
      if (resultTarget) resultTarget.innerHTML = renderExploreResult();

    }
  }

  function insertColumn(name) {
    const editor = $("#sql-editor");
    if (!editor) return;
    const quoted = `"${name}"`;
    const start = editor.selectionStart ?? editor.value.length;
    const end = editor.selectionEnd ?? start;
    editor.value = editor.value.slice(0, start) + quoted + editor.value.slice(end);
    editor.selectionStart = editor.selectionEnd = start + quoted.length;
    editor.focus();
    if (state.dataset) exploreFor(state.dataset.id).sql = editor.value;
  }

  /* ------------------------------------------------------------------ */
  /* Forecast                                                            */
  /* ------------------------------------------------------------------ */
  function forecastDefaults(dataset) {
    const profile = dataset.profile || {};
    const time = timeCols(profile);
    const measures = measureCols(profile);
    const preferred = measures.find((m) => m.semantic === "currency") || measures.find((m) => m.semantic === "count") || measures[0];
    return {
      date_col: profile.time?.column || time[0]?.name || "",
      value_col: preferred?.name || "",
      horizon: 6,
      freq: "auto",
      agg: "sum",
    };
  }

  function renderForecast() {
    const d = state.dataset;
    const profile = d.profile || {};
    const time = timeCols(profile);
    const measures = measureCols(profile);
    if (!time.length || !measures.length) {
      return `<div class="view-inner"><div class="page-head"><div><div class="page-kicker"><span class="dot"></span> Forecast</div><h1 class="page-title">Time-series forecasting</h1></div></div><div class="empty"><div class="empty-icon">${icon("clock", 18)}</div><h3>No time series available</h3><p>This dataset needs a date column and a numeric measure before Atlas can forecast. Add a dated file and try again.</p></div></div>`;
    }
    if (!state.forecastParams[d.id]) state.forecastParams[d.id] = forecastDefaults(d);
    const params = state.forecastParams[d.id];
    const result = state.forecast[d.id];
    const anomaly = state.anomalies[d.id];
    return `
      <div class="view-inner">
        <div class="page-head">
          <div>
            <div class="page-kicker"><span class="dot"></span> Forecast studio</div>
            <h1 class="page-title">Project the next periods</h1>
            <p class="page-sub">Holt-Winters and seasonal-naive models compete on a holdout window. Atlas reports the backtest, not just the pretty line.</p>
          </div>
        </div>
        <div class="card card-pad">
          <div class="forecast-controls">
            <div class="field"><label>Date column</label><select class="select" id="fc-date">${time.map((c) => `<option value="${esc(c.name)}" ${params.date_col === c.name ? "selected" : ""}>${esc(labelOf(c))}</option>`).join("")}</select></div>
            <div class="field"><label>Measure</label><select class="select" id="fc-value">${measures.map((c) => `<option value="${esc(c.name)}" ${params.value_col === c.name ? "selected" : ""}>${esc(labelOf(c))}</option>`).join("")}</select></div>
            <div class="field"><label>Horizon</label><select class="select" id="fc-horizon">${[3, 6, 9, 12, 18, 24].map((n) => `<option ${Number(params.horizon) === n ? "selected" : ""}>${n}</option>`).join("")}</select></div>
            <div class="field"><label>Frequency</label><select class="select" id="fc-freq">${[["auto", "Auto"], ["D", "Daily"], ["W", "Weekly"], ["M", "Monthly"], ["Q", "Quarterly"]].map(([v, l]) => `<option value="${v}" ${params.freq === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
            <div class="field"><label>Aggregate</label><select class="select" id="fc-agg"><option value="sum" ${params.agg === "sum" ? "selected" : ""}>Sum</option><option value="mean" ${params.agg === "mean" ? "selected" : ""}>Average</option></select></div>
            <button class="btn primary" data-action="forecast-run" ${state.forecastLoading ? "disabled" : ""}>${state.forecastLoading ? '<span class="spinner" style="border-top-color:#04201c"></span>' : icon("play", 13)} Run</button>
          </div>
        </div>
        <div id="forecast-result">${renderForecastResult()}</div>
        <div class="section-head"><h2>Anomaly scan</h2><span class="aside">Seasonally adjusted robust z-scores</span></div>
        <div id="anomaly-result">${renderAnomalyResult()}</div>
      </div>
    `;
  }

  function renderForecastResult() {
    const d = state.dataset;
    const result = d ? state.forecast[d.id] : null;
    const params = d ? state.forecastParams[d.id] : null;
    if (state.forecastLoading) return `<div class="card" style="padding:18px;margin-top:14px">${spinnerLabel("Fitting models and backtesting")}</div>`;
    if (!result) {
      return `<div class="empty" style="margin-top:14px"><div class="empty-icon">${icon("chart", 18)}</div><h3>Ready when you are</h3><p>Pick a date column and measure, then run the forecast. Atlas will hold out the last 20% of periods to score the model.</p></div>`;
    }
    const s = result.summary || {};
    const m = result.metrics || {};
    const fmtKind = result.value_format || "number";
    const direction = s.direction === "up" ? "up" : s.direction === "down" ? "down" : "flat";
    const unitMap = { daily: ["day", "days"], weekly: ["week", "weeks"], monthly: ["month", "months"], quarterly: ["quarter", "quarters"] };
    const unit = unitMap[result.frequency] || ["period", "periods"];
    const periods = Number(result.horizon) || (result.forecast || []).length || 1;
    return `
      <div class="card card-pad" style="margin-top:14px">
        <div style="display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;align-items:flex-start">
          <div>
            <div class="answer-kicker"><span class="dot"></span> ${esc(titleCase(result.frequency))} forecast · ${esc(result.model)}</div>
            <div style="font-size:24px;font-weight:620;letter-spacing:-.03em;margin-top:4px">Next ${periods} ${periods === 1 ? unit[0] : unit[1]}: ${fmt(s.next, fmtKind)}</div>
            <div class="muted" style="font-size:12px;margin-top:5px">${direction === "flat" ? "Broadly flat" : `Expected to ${direction === "up" ? "rise" : "fall"}`} ${Number.isFinite(Number(s.change_pct)) ? `${Number(s.change_pct) > 0 ? "+" : ""}${Number(s.change_pct).toFixed(1)}%` : ""} versus the last observed period (${fmt(s.last, fmtKind)}).</div>
          </div>
          <div class="forecast-metrics">
            <div class="metric"><div class="k">Backtest MAPE</div><div class="v">${Number.isFinite(Number(m.mape)) ? `${Number(m.mape).toFixed(1)}%` : "—"}</div></div>
            <div class="metric"><div class="k">MAE</div><div class="v">${fmt(m.mae, fmtKind)}</div></div>
            <div class="metric"><div class="k">R²</div><div class="v">${Number.isFinite(Number(m.r2)) ? Number(m.r2).toFixed(2) : "—"}</div></div>
            <div class="metric"><div class="k">Model</div><div class="v" style="font-size:13px;margin-top:6px">${esc(result.model)}</div></div>
          </div>
        </div>
        <div class="answer-chart" style="margin-top:18px">${charts.forecastChart(result.history || [], result.forecast || [], { format: fmtKind, width: 920, height: 330 })}</div>
        <div class="legend" style="margin-top:8px"><span><i style="background:var(--accent)"></i>Actual</span><span><i style="background:var(--accent-2)"></i>Forecast</span><span><i style="background:rgba(94,234,212,.18)"></i>95% interval</span><span style="margin-left:auto">${esc(result.history?.length || 0)} periods of history · horizon ${esc(result.horizon)}</span></div>
        ${(result.warnings || []).length ? `<div class="forecast-note" style="margin-top:14px">${(result.warnings || []).map(esc).join("<br>")}</div>` : ""}
      </div>`;
  }

  async function runForecast() {
    const d = state.dataset;
    if (!d || state.forecastLoading) return;
    const params = {
      date_col: $("#fc-date")?.value || state.forecastParams[d.id]?.date_col,
      value_col: $("#fc-value")?.value || state.forecastParams[d.id]?.value_col,
      horizon: Number($("#fc-horizon")?.value || 6),
      freq: $("#fc-freq")?.value || "auto",
      agg: $("#fc-agg")?.value || "sum",
    };
    state.forecastParams[d.id] = params;
    state.forecastLoading = true;
    const target = $("#forecast-result");
    if (target) target.innerHTML = renderForecastResult();
    try {
      const result = await postJSON(`/api/datasets/${encodeURIComponent(d.id)}/forecast`, params);
      state.forecast[d.id] = result;
      state.forecastLoading = false;
      if (target) target.innerHTML = renderForecastResult();
      await runAnomalies(true);
    } catch (error) {
      state.forecastLoading = false;
      if (target) target.innerHTML = `<div class="card" style="padding:18px;margin-top:14px;border-color:rgba(251,113,133,.3)"><div style="color:var(--rose);display:flex;gap:8px;align-items:center">${icon("alert", 14)} ${esc(error.message)}</div></div>`;
    }
  }

  function renderAnomalyResult() {
    const d = state.dataset;
    const result = d ? state.anomalies[d.id] : null;
    if (state.anomaliesLoading) return `<div class="card" style="padding:18px">${spinnerLabel("Scanning for unusual periods")}</div>`;
    if (!result) return `<div class="empty"><div class="empty-icon">${icon("activity", 18)}</div><h3>No scan yet</h3><p>Run a forecast to trigger a seasonally-adjusted anomaly scan on the same measure.</p></div>`;
    const values = (result.series || []).map((p) => p.value);
    const labels = (result.series || []).map((p) => p.date);
    const flags = (result.anomalies || []).map((a) => ({ index: (result.series || []).findIndex((p) => p.date === a.date), value: a.value, label: a.date, z: a.z }));
    return `
      <div class="card card-pad">
        <div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap">
          <div><div class="muted" style="font-size:12.5px">${esc(result.summary)}</div><div class="faint" style="font-size:10.5px;margin-top:4px">Threshold ${result.threshold} · baseline ${fmt(result.baseline, result.value_format)} · ${Number(result.count || 0)} flagged</div></div>
          <button class="btn sm" data-action="anomaly-run">${icon("refresh", 11)} Re-scan</button>
        </div>
        <div class="answer-chart">${charts.line(labels, values, { anomalies: flags, format: result.value_format, width: 920, height: 250 })}</div>
        ${(result.anomalies || []).length ? `<div class="table-wrap" style="margin-top:12px"><table class="data"><thead><tr><th>Date</th><th class="num">Value</th><th class="num">Robust z</th><th>Direction</th></tr></thead><tbody>${result.anomalies.slice(0, 6).map((a) => `<tr><td>${esc(a.date)}</td><td class="num">${fmt(a.value, result.value_format)}</td><td class="num">${Number(a.z).toFixed(1)}</td><td>${esc(a.direction)}</td></tr>`).join("")}</tbody></table></div>` : ""}
      </div>`;
  }

  async function runAnomalies(auto = false) {
    const d = state.dataset;
    if (!d || state.anomaliesLoading) return;
    const params = state.forecastParams[d.id];
    if (!params) return;
    state.anomaliesLoading = true;
    const target = $("#anomaly-result");
    if (target) target.innerHTML = renderAnomalyResult();
    try {
      const query = new URLSearchParams({ date_col: params.date_col, value_col: params.value_col, agg: params.agg || "sum", threshold: "3.5" });
      const result = await getJSON(`/api/datasets/${encodeURIComponent(d.id)}/anomalies?${query}`);
      state.anomalies[d.id] = result;
    } catch (error) {
      if (!auto) toast(error.message, "error");
    } finally {
      state.anomaliesLoading = false;
      const t = $("#anomaly-result");
      if (t) t.innerHTML = renderAnomalyResult();
    }
  }

  /* ------------------------------------------------------------------ */
  /* Quality                                                             */
  /* ------------------------------------------------------------------ */
  function renderQuality() {
    const d = state.dataset;
    const profile = d.profile || {};
    const q = profile.quality || {};
    const dims = q.dimensions || {};
    const issues = q.issues || [];
    const missing = (profile.missingness || []).slice(0, 8);
    const corr = profile.correlations || {};
    const pii = (profile.columns || []).filter((c) => c.pii);
    const score = Number(q.score || 0);
    return `
      <div class="view-inner">
        <div class="page-head">
          <div>
            <div class="page-kicker"><span class="dot"></span> Data quality</div>
            <h1 class="page-title">Know what would distort the answer</h1>
            <p class="page-sub">Completeness, uniqueness, consistency and validity are measured before any question is asked. PII and drift are called out explicitly.</p>
          </div>
          <div class="page-actions"><button class="btn" data-action="refresh-insights">${icon("refresh", 13)} Re-scan signals</button></div>
        </div>
        <div class="card card-pad">
          <div class="quality-top">
            <div style="display:grid;place-items:center">
              <div class="score-ring" style="--score:${score}"><div class="score-ring-inner"><div class="score-ring-value">${score.toFixed(1)}</div><div class="score-ring-label">Grade ${esc(q.grade || "—")}</div></div></div>
              <div class="faint" style="font-size:10px;margin-top:10px">${Number(q.missing_cells || 0).toLocaleString()} missing cells · ${Number(q.duplicate_rows || 0).toLocaleString()} duplicate rows</div>
            </div>
            <div>
              ${Object.entries(dims).map(([key, value]) => `<div class="dim-row"><span class="dim-name">${titleCase(key)}</span><span class="dim-track"><span class="dim-fill" style="width:${Math.max(0, Math.min(100, Number(value)))}%;${Number(value) < 80 ? "background:linear-gradient(90deg,#fbbf24,#fb7185)" : ""}"></span></span><span class="dim-val">${Number(value).toFixed(1)}%</span></div>`).join("")}
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">
                ${pii.length ? `<span class="tag rose">${pii.length} PII column${pii.length === 1 ? "" : "s"}</span>` : `<span class="tag">No PII detected</span>`}
                <span class="tag neutral">${issues.length} issue${issues.length === 1 ? "" : "s"}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="grid-2" style="margin-top:14px">
          <div class="card card-pad">
            <div class="section-head" style="margin:0 0 12px"><h2>Issues that matter</h2><span class="aside">${esc(q.grade || "")} grade</span></div>
            ${issues.length ? issues.slice(0, 8).map((i) => `
              <div class="issue">
                <span class="issue-sev" style="background:${i.severity === "high" ? "var(--rose)" : i.severity === "medium" ? "var(--amber)" : "var(--accent-2)"}"></span>
                <div style="flex:1"><div class="issue-title">${esc(i.title)} ${i.column ? `<span class="issue-col">${esc(i.column)}</span>` : ""}</div><div class="issue-detail">${esc(i.detail)}</div></div>
                <span class="tag ${i.severity === "high" ? "rose" : i.severity === "medium" ? "amber" : "blue"}" style="height:18px;font-size:8px">${esc(i.severity)}</span>
              </div>`).join("") : `<div class="empty" style="padding:24px"><div class="empty-icon">${icon("check", 18)}</div><h3>Clean bill of health</h3><p>No material issues detected.</p></div>`}
          </div>
          <div class="card card-pad">
            <div class="section-head" style="margin:0 0 12px"><h2>Missingness</h2><span class="aside">top columns</span></div>
            ${missing.length ? missing.map((m) => `<div class="dim-row" style="grid-template-columns:130px 1fr 42px"><span class="dim-name" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(prettyName(m.column))}</span><span class="dim-track"><span class="dim-fill" style="width:${Math.max(0, Math.min(100, Number(m.missing_pct)))}%;${Number(m.missing_pct) > 5 ? "background:linear-gradient(90deg,#fbbf24,#fb7185)" : ""}"></span></span><span class="dim-val">${Number(m.missing_pct).toFixed(1)}%</span></div>`).join("") : '<div class="faint">No missing values.</div>'}
            <div class="faint" style="font-size:10.5px;margin-top:12px;line-height:1.5">Missing values are excluded from calculations, never silently imputed.</div>
          </div>
        </div>

        ${corr.columns?.length ? `
        <div class="section-head"><h2>Correlation map</h2><span class="aside">Pearson r on complete pairs · ${corr.columns.length} measures</span></div>
        <div class="card card-pad"><div class="heatmap-wrap">${correlationHeatmap(corr)}</div></div>` : ""}

        <div class="section-head"><h2>Column dictionary</h2><span class="aside"><strong>${(profile.columns || []).length}</strong> columns</span></div>
        <div class="table-wrap"><table class="data"><thead><tr><th>Column</th><th>Type</th><th>Role</th><th class="num">Missing</th><th class="num">Distinct</th><th>Flags</th><th>Sample</th></tr></thead><tbody>
          ${(profile.columns || []).map((c) => {
            const sample = (c.top_values || [])[0]?.value ?? (c.examples || [])[0] ?? "";
            return `<tr>
              <td><strong style="color:var(--text-soft)">${esc(labelOf(c))}</strong>${c.pii ? ' <span class="tag rose" style="height:15px;font-size:7.5px">PII</span>' : ""}<div class="faint mono" style="font-size:9px">${esc(c.name)}</div></td>
              <td><span class="tag neutral" style="height:18px;font-size:8.5px">${esc(c.dtype)}</span></td>
              <td class="muted">${esc(c.role)}<div class="faint" style="font-size:9px">${esc(c.semantic)}</div></td>
              <td class="num">${Number(c.null_pct || 0).toFixed(1)}%</td>
              <td class="num">${Number(c.distinct || 0).toLocaleString()}</td>
              <td>${(c.flags || []).map((f) => `<span class="tag neutral" style="height:17px;font-size:8px">${esc(f.replace(/_/g, " "))}</span>`).join(" ") || '<span class="faint">—</span>'}</td>
              <td class="faint" style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${esc(String(sample).slice(0, 50))}</td>
            </tr>`;
          }).join("")}
        </tbody></table></div>

        ${(d.notes || []).length ? `<div class="section-head"><h2>Cleaning log</h2><span class="aside">${d.notes.length} note${d.notes.length === 1 ? "" : "s"} from ingest</span></div><div class="card card-pad"><div style="display:flex;flex-direction:column;gap:8px">${d.notes.map((n) => `<div style="display:flex;gap:8px;font-size:11.5px;color:var(--muted);line-height:1.5"><span style="color:var(--accent);flex:0 0 12px">${icon("check", 12)}</span><span>${esc(n)}</span></div>`).join("")}</div></div>` : ""}
      </div>
    `;
  }

  function correlationHeatmap(corr) {
    const labels = corr.labels || corr.columns;
    const matrix = corr.matrix || [];
    const n = labels.length;
    const limit = Math.min(n, 12);
    let html = `<div class="heatmap" style="grid-template-columns:92px repeat(${limit},minmax(26px,1fr))">`;
    html += `<div></div>`;
    for (let j = 0; j < limit; j++) html += `<div class="hm-col" title="${esc(labels[j])}">${esc(labels[j])}</div>`;
    for (let i = 0; i < limit; i++) {
      html += `<div class="hm-label" title="${esc(labels[i])}">${esc(labels[i])}</div>`;
      for (let j = 0; j < limit; j++) {
        const v = matrix[i]?.[j];
        const alpha = v === null || v === undefined ? 0 : 0.08 + Math.min(1, Math.abs(Number(v))) * 0.62;
        const bg = v === null || v === undefined ? "rgba(255,255,255,.03)" : Number(v) >= 0 ? `rgba(94,234,212,${alpha})` : `rgba(251,113,133,${alpha})`;
        html += `<div class="hm-cell" style="background:${bg}" title="${esc(labels[i])} × ${esc(labels[j])}: ${v === null || v === undefined ? "—" : Number(v).toFixed(2)}"></div>`;
      }
    }
    html += "</div>";
    return html;
  }

  /* ------------------------------------------------------------------ */
  /* Report                                                              */
  /* ------------------------------------------------------------------ */
  function renderReport() {
    const d = state.dataset;
    const url = `/api/datasets/${encodeURIComponent(d.id)}/report`;
    return `
      <div class="view-inner">
        <div class="page-head">
          <div>
            <div class="page-kicker"><span class="dot"></span> Export</div>
            <h1 class="page-title">A report you can hand over</h1>
            <p class="page-sub">Self-contained HTML: inline SVG charts, no scripts, no external fonts, no CDN. Opens offline and prints cleanly to PDF.</p>
          </div>
          <div class="page-actions">
            <a class="btn" href="${url}" target="_blank" rel="noopener">${icon("external", 13)} Open</a>
            <a class="btn primary" href="${url}?download=1">${icon("download", 13)} Download HTML</a>
          </div>
        </div>
        <div class="grid-2">
          <div class="card card-pad">
            <div class="section-head" style="margin:0 0 12px"><h2>What's inside</h2><span class="aside">generated live</span></div>
            ${["Executive read of the top three signals", "Six evidence panels with inline charts", "Data quality score, dimensions and issues", "Column dictionary with types and coverage", "Cleaning log and method provenance"].map((t) => `<div style="display:flex;gap:9px;padding:7px 0;border-bottom:1px solid var(--line-soft);font-size:12px;color:var(--text-soft)"><span style="color:var(--accent)">${icon("check", 12)}</span>${esc(t)}</div>`).join("")}
            <div class="faint" style="font-size:10.5px;margin-top:12px;line-height:1.55">The export is deterministic: the same dataset produces the same report. Numbers are copied from the analysis, not regenerated by a model.</div>
          </div>
          <div class="card card-pad">
            <div class="section-head" style="margin:0 0 12px"><h2>Share safely</h2><span class="aside">watch PII</span></div>
            <p class="narrative" style="font-size:12px">${(d.profile?.columns || []).filter((c) => c.pii).length ? "This dataset contains columns flagged as personal data. Mask them before sending the report outside your organisation." : "No PII columns were detected. The report still includes column samples — review them before sharing."}</p>
            <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
              <span class="tag neutral">${Number(d.rows || 0).toLocaleString()} rows</span>
              <span class="tag neutral">${d.cols || 0} columns</span>
              <span class="tag neutral">${esc(d.profile?.quality?.grade || "—")} quality</span>
            </div>
          </div>
        </div>
        <div class="section-head"><h2>Preview</h2><span class="aside">rendered in an isolated frame</span></div>
        <iframe class="report-frame" src="${url}" title="Atlas report preview" loading="lazy"></iframe>
      </div>
    `;
  }

  /* ------------------------------------------------------------------ */
  /* Modals                                                              */
  /* ------------------------------------------------------------------ */
  function openModal(html, opts = {}) {
    const root = $("#modal-root");
    state.modalOpen = true;
    root.innerHTML = `<div class="modal-backdrop" data-modal-backdrop><div class="modal ${opts.wide ? "wide" : ""}" role="dialog" aria-modal="true">${html}</div></div>`;
    const backdrop = $("[data-modal-backdrop]", root);
    backdrop.addEventListener("click", (event) => { if (event.target === backdrop) closeModal(); });
    if (opts.onMount) opts.onMount(root);
    return root;
  }

  function closeModal() {
    $("#modal-root").innerHTML = "";
    state.modalOpen = false;
  }

  function openSettings() {
    const s = state.settings || {};
    openModal(`
      <div class="modal-head">
        <div><div class="modal-title">Engine settings</div><div class="modal-sub">Atlas works without a model. Add one only for broader question coverage and prose polish; numbers are still verified against the result.</div></div>
        <button class="icon-btn" data-action="modal-close">${icon("x", 16)}</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field full"><label>Provider</label><select class="select" id="set-provider"><option value="none" ${s.provider === "none" ? "selected" : ""}>None — deterministic engine only</option><option value="openai" ${s.provider === "openai" ? "selected" : ""}>OpenAI-compatible</option><option value="ollama" ${s.provider === "ollama" ? "selected" : ""}>Ollama (local)</option></select></div>
          <div class="field"><label>Model</label><input class="input" id="set-model" value="${esc(s.model || "")}" placeholder="gpt-4o-mini / llama3.2"></div>
          <div class="field"><label>Base URL</label><input class="input" id="set-base" value="${esc(s.base_url || "")}" placeholder="https://api.openai.com/v1"></div>
          <div class="field full"><label>API key</label><input class="input" id="set-key" type="password" value="${esc(s.api_key || "")}" placeholder="sk-… (stored locally)"><div class="form-note">Leave as *** to keep the saved key. Stored in data/settings.json, never sent anywhere except the provider.</div></div>
          <div class="field"><label>Temperature</label><input class="input" id="set-temp" type="number" step="0.05" min="0" max="1.5" value="${Number(s.temperature ?? 0.2)}"></div>
          <div class="field"><label>Query timeout (s)</label><input class="input" id="set-timeout" type="number" step="1" min="1" max="60" value="${Number(s.query_timeout ?? 8)}"></div>
          <div class="field"><label>Row limit</label><input class="input" id="set-limit" type="number" step="100" min="10" max="10000" value="${Number(s.row_limit ?? 1000)}"></div>
        </div>
        <div id="settings-test" class="form-note" style="margin-top:12px"></div>
      </div>
      <div class="modal-foot">
        <button class="btn" data-action="settings-test">${icon("activity", 12)} Test connection</button>
        <span style="flex:1"></span>
        <button class="btn ghost" data-action="modal-close">Cancel</button>
        <button class="btn primary" data-action="settings-save">Save settings</button>
      </div>
    `);
  }

  async function saveSettings() {
    const payload = {
      provider: $("#set-provider")?.value,
      model: $("#set-model")?.value,
      base_url: $("#set-base")?.value,
      api_key: $("#set-key")?.value,
      temperature: Number($("#set-temp")?.value || 0.2),
      query_timeout: Number($("#set-timeout")?.value || 8),
      row_limit: Number($("#set-limit")?.value || 1000),
    };
    try {
      state.settings = await putJSON("/api/settings", payload);
      toast("Settings saved", "ok");
      closeModal();
      renderSidebar(); renderTopbar();
    } catch (error) { toast(error.message, "error"); }
  }

  async function testSettings() {
    const target = $("#settings-test");
    if (target) target.innerHTML = spinnerLabel("Contacting the model");
    try {
      // Save first so the backend tests the values on screen.
      const payload = {
        provider: $("#set-provider")?.value,
        model: $("#set-model")?.value,
        base_url: $("#set-base")?.value,
        api_key: $("#set-key")?.value,
        temperature: Number($("#set-temp")?.value || 0.2),
        query_timeout: Number($("#set-timeout")?.value || 8),
        row_limit: Number($("#set-limit")?.value || 1000),
      };
      state.settings = await putJSON("/api/settings", payload);
      const result = await postJSON("/api/settings/test", {});
      if (target) target.innerHTML = `<span style="color:var(--accent)">${icon("check", 12)} Connected to ${esc(result.provider)} · ${esc(result.model)}</span>`;
      renderSidebar(); renderTopbar();
    } catch (error) {
      if (target) target.innerHTML = `<span style="color:var(--rose)">${icon("alert", 12)} ${esc(error.message)}</span>`;
    }
  }

  function openUpload() {
    openModal(`
      <div class="modal-head">
        <div><div class="modal-title">Add a dataset</div><div class="modal-sub">CSV, TSV, Excel, JSON or Parquet. Atlas detects encoding, delimiters, types and messy business formatting.</div></div>
        <button class="icon-btn" data-action="modal-close">${icon("x", 16)}</button>
      </div>
      <div class="modal-body">
        <div class="field" style="margin-bottom:13px"><label>Dataset name <span class="faint">(optional)</span></label><input class="input" id="upload-name" placeholder="e.g. Q4 revenue"></div>
        <div class="dropzone" id="dropzone" tabindex="0">
          <div style="color:var(--accent)">${icon("upload", 22)}</div>
          <div class="big" id="drop-title">Drop a file here, or click to browse</div>
          <div class="small" id="drop-sub">Up to 128 MB · files are analysed locally</div>
          <input type="file" id="file-input" accept=".csv,.tsv,.txt,.json,.xlsx,.xlsm,.parquet,.pq" hidden>
        </div>
        <div id="upload-status" class="form-note" style="margin-top:12px"></div>
      </div>
      <div class="modal-foot"><button class="btn ghost" data-action="modal-close">Cancel</button><button class="btn primary" data-action="upload-submit" id="upload-btn" disabled>${icon("upload", 13)} Analyse file</button></div>
    `, {
      onMount: () => {
        const input = $("#file-input");
        const zone = $("#dropzone");
        let selected = null;
        const choose = () => input.click();
        zone.addEventListener("click", choose);
        zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(); } });
        input.addEventListener("change", () => {
          selected = input.files?.[0] || null;
          if (selected) {
            $("#drop-title").textContent = selected.name;
            $("#drop-sub").textContent = `${humanBytes(selected.size)} · ready to profile`;
            $("#upload-btn").disabled = false;
            if (!$("#upload-name").value) $("#upload-name").value = prettyName(selected.name);
          }
        });
        ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("drag"); }));
        ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("drag"); }));
        zone.addEventListener("drop", (e) => {
          const file = e.dataTransfer?.files?.[0];
          if (file) {
            selected = file;
            $("#drop-title").textContent = file.name;
            $("#drop-sub").textContent = `${humanBytes(file.size)} · ready to profile`;
            $("#upload-btn").disabled = false;
            if (!$("#upload-name").value) $("#upload-name").value = prettyName(file.name);
          }
        });
        state._uploadFile = () => selected;
      }
    });
  }

  async function uploadSelected() {
    const file = state._uploadFile?.();
    if (!file) { toast("Choose a file first.", "error"); return; }
    const name = $("#upload-name")?.value?.trim();
    const status = $("#upload-status");
    const button = $("#upload-btn");
    if (button) button.disabled = true;
    if (status) status.innerHTML = `<div>${spinnerLabel("Reading, cleaning and profiling the file")}</div><div class="upload-progress"><i></i></div>`;
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    try {
      const created = await api("/api/datasets", { method: "POST", body: form });
      closeModal();
      toast(`${created.name} added · ${Number(created.rows || 0).toLocaleString()} rows`, "ok");
      await refreshDatasets();
      await selectDataset(created.id, { view: "overview" });
    } catch (error) {
      if (status) status.innerHTML = `<span style="color:var(--rose)">${esc(error.message)}</span>`;
      if (button) button.disabled = false;
    }
  }

  function openInsight(id) {
    const insight = (state.dataset?.insights || []).find((i) => i.id === id);
    if (!insight) return;
    const meta = KIND_META[insight.kind] || { label: titleCase(insight.kind), cls: "neutral" };
    const chart = insight.chart ? charts.render(insight.chart, {}) : "";
    const stats = Object.entries(insight.stats || {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
    const statLabel = (k) => ({ r: "Pearson r", rho: "Spearman ρ", p: "p-value", n: "Complete rows", eta2: "Effect size η²", cramers_v: "Cramér's V", growth: "Growth", r2: "R²", multiple: "× typical", z: "Robust z", share: "Share", gap: "Gap", periods: "Periods", agg: "Aggregation" }[k] || titleCase(k.replace(/_/g, " ")));
    let statValue = (k, v) => {
      if (typeof v === "number") {
        if (["r", "rho", "r2", "cramers_v", "eta2"].includes(k)) return Number(v).toFixed(2);
        if (["growth", "share", "gap"].includes(k)) return `${(Number(v) * 100).toFixed(1)}%`;
        if (k === "p") return Number(v) < 0.001 ? "< 0.001" : Number(v).toFixed(3);
        return Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
      }
      return String(v);
    };
    const question = insightQuestion(insight);
    openModal(`
      <div class="modal-head">
        <div><span class="tag ${meta.cls}">${esc(meta.label)}</span><div class="modal-title" style="margin-top:10px">${esc(insight.title)}</div><div class="modal-sub">${esc(insight.detail)}</div></div>
        <button class="icon-btn" data-action="modal-close">${icon("x", 16)}</button>
      </div>
      <div class="modal-body">
        ${chart ? `<div class="card" style="padding:12px 14px">${chart}</div>` : ""}
        ${stats.length ? `<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px">${stats.map(([k, v]) => `<div class="highlight"><span class="faint">${esc(statLabel(k))}</span> <strong style="color:var(--text);margin-left:4px">${esc(statValue(k, v))}</strong></div>`).join("")}</div>` : ""}
        <div class="form-note" style="margin-top:14px">Confidence: <strong style="color:var(--text-soft)">${esc(insight.confidence || "medium")}</strong> · Score ${Number(insight.score || 0).toFixed(0)}/100 · columns ${esc((insight.columns || []).join(", "))}</div>
      </div>
      <div class="modal-foot">
        <button class="btn" data-copy-insight="${esc(insight.id)}">${icon("copy", 12)} Copy finding</button>
        <span style="flex:1"></span>
        <button class="btn" data-action="modal-close">Close</button>
        <button class="btn primary" data-ask-insight="${esc(question)}">${icon("sparkles", 12)} Ask a follow-up</button>
      </div>
    `, { wide: true });
  }

  function openDelete() {
    const d = state.dataset;
    if (!d) return;
    openModal(`
      <div class="modal-head"><div><div class="modal-title">Delete ${esc(d.name)}?</div><div class="modal-sub">The table, profile, insights and archived upload are removed from this machine. This cannot be undone.</div></div><button class="icon-btn" data-action="modal-close">${icon("x", 16)}</button></div>
      <div class="modal-body"><div class="forecast-note" style="border-color:var(--rose)">${Number(d.rows || 0).toLocaleString()} rows · ${d.cols || 0} columns · ${d.insights?.length || 0} insights will be deleted.</div></div>
      <div class="modal-foot"><button class="btn ghost" data-action="modal-close">Cancel</button><button class="btn danger" data-action="confirm-delete">${icon("trash", 13)} Delete dataset</button></div>
    `);
  }

  async function confirmDelete() {
    const d = state.dataset;
    if (!d) return;
    try {
      await del(`/api/datasets/${encodeURIComponent(d.id)}`);
      closeModal();
      toast(`${d.name} deleted`, "ok");
      state.dataset = null;
      delete state.chats[d.id];
      delete state.forecast[d.id];
      delete state.anomalies[d.id];
      delete state.explore[d.id];
      await refreshDatasets();
      const next = state.datasets[0];
      if (next) await selectDataset(next.id, { view: "overview" });
      else { state.dataset = null; renderShell(); }
    } catch (error) { toast(error.message, "error"); }
  }

  /* ------------------------------------------------------------------ */
  /* Actions                                                             */
  /* ------------------------------------------------------------------ */
  async function refreshDatasets() {
    try {
      const data = await getJSON("/api/datasets");
      state.datasets = data.datasets || [];
      state.health = await getJSON("/api/health");
      renderSidebar();
    } catch (error) { toast(error.message, "error"); }
  }

  async function refreshInsights() {
    const d = state.dataset;
    if (!d) return;
    toast("Re-scanning signals…", "ok");
    try {
      const data = await postJSON(`/api/datasets/${encodeURIComponent(d.id)}/insights/refresh`, {});
      d.insights = data.insights || [];
      if (data.profile) d.profile = data.profile;
      if (state.view === "overview") await renderView();
      else if (state.view === "quality") await renderView();
      toast(`${d.insights.length} signals ranked`, "ok");
    } catch (error) { toast(error.message, "error"); }
  }

  function openReport() {
    if (!state.dataset) return;
    navigate("report");
  }

  /* ------------------------------------------------------------------ */
  /* Event delegation                                                    */
  /* ------------------------------------------------------------------ */
  document.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-action], [data-view], [data-dataset], [data-question], [data-insight], [data-toggle-sql], [data-answer-csv], [data-copy-sql], [data-insert-col], [data-query], [data-explore-mode], [data-export-explore], [data-copy-query], [data-copy-insight], [data-ask-insight]");
    if (!target) return;
    if (target.matches("[data-modal-backdrop]")) return;
    const action = target.dataset.action;

    if (target.dataset.dataset) {
      closeMobileSidebar();
      await selectDataset(target.dataset.dataset);
      return;
    }
    if (target.dataset.view) {
      await navigate(target.dataset.view);
      return;
    }
    if (target.dataset.question) {
      const q = target.dataset.question;
      closeModal();
      await askQuestion(q);
      return;
    }
    if (target.dataset.insight) {
      openInsight(target.dataset.insight);
      return;
    }
    if (target.dataset.askInsight) {
      const q = target.dataset.askInsight;
      closeModal();
      await askQuestion(q);
      return;
    }
    if (target.dataset.copyInsight) {
      const insight = (state.dataset?.insights || []).find((i) => i.id === target.dataset.copyInsight);
      if (insight) copyText(`${insight.title}\n${insight.detail}`);
      return;
    }
    if (target.dataset.toggleSql) {
      const block = $(`#sql-${target.dataset.toggleSql}`);
      if (block) block.classList.toggle("hidden");
      return;
    }
    if (target.dataset.copySql) {
      const run = currentRun();
      const el = document.querySelector(`[data-copy-sql="${target.dataset.copySql}"]`);
      const block = el?.closest(".sql-block");
      if (block) copyText(block.querySelector(".sql-code")?.textContent || "");
      return;
    }
    if (target.dataset.answerCsv) {
      const run = currentRun();
      if (run?.answer?.result) {
        const r = run.answer.result;
        downloadCSV(`atlas-answer-${run.id}.csv`, r.columns, r.rows);
      }
      return;
    }
    if (target.dataset.insertCol) { insertColumn(target.dataset.insertCol); return; }
    if (target.dataset.query) {
      const editor = $("#sql-editor");
      if (editor) { editor.value = target.dataset.query; editor.focus(); }
      if (state.dataset) exploreFor(state.dataset.id).sql = target.dataset.query;
      return;
    }
    if (target.dataset.exploreMode) {
      const ex = exploreFor(state.dataset.id);
      ex.mode = target.dataset.exploreMode;
      $("#explore-result").innerHTML = renderExploreResult();

      return;
    }
    if (target.dataset.exportExplore !== undefined) {
      const ex = exploreFor(state.dataset.id);
      if (ex.result) downloadCSV(`atlas-query-${state.dataset.id}.csv`, ex.result.columns, ex.result.rows);
      return;
    }
    if (target.dataset.copyQuery !== undefined) {
      const ex = exploreFor(state.dataset.id);
      copyText(ex.sql || $("#sql-editor")?.value || "");
      return;
    }

    switch (action) {
      case "sidebar-toggle": {
        const sidebar = $("#sidebar");
        sidebar?.classList.toggle("open");
        if (sidebar?.classList.contains("open")) {
          const scrim = document.createElement("div");
          scrim.className = "scrim";
          scrim.dataset.scrim = "1";
          document.body.appendChild(scrim);
          scrim.addEventListener("click", closeMobileSidebar);
        } else closeMobileSidebar();
        break;
      }
      case "upload-open": openUpload(); break;
      case "settings-open": openSettings(); break;
      case "modal-close": closeModal(); break;
      case "settings-save": await saveSettings(); break;
      case "settings-test": await testSettings(); break;
      case "upload-submit": await uploadSelected(); break;
      case "go-ask": await navigate("ask", { focus: true }); break;
      case "overview-ask": {
        const q = $("#overview-ask")?.value?.trim();
        if (q) await askQuestion(q);
        else focusComposer();
        break;
      }
      case "refresh-insights": await refreshInsights(); break;
      case "open-report": await navigate("report"); break;
      case "delete-dataset": openDelete(); break;
      case "confirm-delete": await confirmDelete(); break;
      case "explore-run": await runExploreQuery(); break;
      case "explore-preview": {
        const editor = $("#sql-editor");
        const ex = exploreFor(state.dataset.id);
        ex.sql = "SELECT * FROM {table} LIMIT 50";
        if (editor) editor.value = ex.sql;
        await runExploreQuery();
        break;
      }
      case "forecast-run": await runForecast(); break;
      case "anomaly-run": await runAnomalies(false); break;
      case "open-insight": openInsight(target.dataset.id); break;
      default: break;
    }
  });

  document.addEventListener("keydown", async (event) => {
    if (event.target.id === "ask-input" && event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!state.streaming) $("#ask-form")?.requestSubmit();
    }
    if (event.key === "Escape") {
      if (state.modalOpen) closeModal();
      else closeMobileSidebar();
    }
    const meta = event.metaKey || event.ctrlKey;
    if (meta && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (!$("#ask-input")) await navigate("ask", { focus: true });
      else focusComposer();
    }
    if (meta && event.key === "Enter" && $("#sql-editor") === document.activeElement) {
      event.preventDefault();
      await runExploreQuery();
    }
  });

  document.addEventListener("input", (event) => {
    if (event.target.id === "ask-input") {
      const el = event.target;
      el.style.height = "auto";
      el.style.height = `${Math.min(150, el.scrollHeight)}px`;
    }
    if (event.target.id === "sql-editor" && state.dataset) {
      exploreFor(state.dataset.id).sql = event.target.value;
    }
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id !== "ask-form") return;
    event.preventDefault();
    const input = $("#ask-input");
    const q = input?.value?.trim();
    if (!q) return;
    input.value = "";
    input.style.height = "auto";
    askQuestion(q);
  });

  document.addEventListener("change", (event) => {
    if (event.target.closest(".forecast-controls") && state.dataset) {
      const p = state.forecastParams[state.dataset.id] || {};
      if ($("#fc-date")) p.date_col = $("#fc-date").value;
      if ($("#fc-value")) p.value_col = $("#fc-value").value;
      if ($("#fc-horizon")) p.horizon = Number($("#fc-horizon").value);
      if ($("#fc-freq")) p.freq = $("#fc-freq").value;
      if ($("#fc-agg")) p.agg = $("#fc-agg").value;
      state.forecastParams[state.dataset.id] = p;
    }
  });

  function bindView() {
    if (state.view === "overview") loadPreview();
    if (state.view === "ask") {
      const textarea = $("#ask-input");
      if (textarea && !state.streaming) setTimeout(() => textarea.focus({ preventScroll: true }), 60);
    }
    if (state.view === "forecast" && state.dataset) {
      const id = state.dataset.id;
      const hasTime = timeCols(state.dataset.profile || {}).length && measureCols(state.dataset.profile || {}).length;
      if (hasTime && !state.forecast[id] && !state.forecastAuto[id]) {
        state.forecastAuto[id] = true;
        setTimeout(() => { if (state.view === "forecast" && state.dataset?.id === id) runForecast(); }, 80);
      }
    }
  }

  function closeMobileSidebar() {
    $("#sidebar")?.classList.remove("open");
    document.querySelector("[data-scrim]")?.remove();
  }

  window.addEventListener("hashchange", () => {
    const hash = parseHash();
    if (!hash.id) return;
    if (hash.id !== state.dataset?.id) selectDataset(hash.id, { view: hash.view });
    else if (hash.view && hash.view !== state.view && VIEWS.includes(hash.view)) navigate(hash.view);
  });

  // Close sidebar after navigation on mobile.
  window.addEventListener("resize", () => { if (window.innerWidth > 760) closeMobileSidebar(); });

  boot();
})();
