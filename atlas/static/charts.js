/* Atlas — dependency-free SVG chart renderer. */
(() => {
  "use strict";

  const C = {
    text: "#e8eef6",
    soft: "#c3ceda",
    muted: "#8a98aa",
    faint: "#5d6c7e",
    grid: "#1b2735",
    gridSoft: "#151f2b",
    accent: "#5eead4",
    accent2: "#7dd3fc",
    amber: "#fbbf24",
    rose: "#fb7185",
    violet: "#a78bfa",
    panel: "#0e1620",
    font: "Inter, 'Segoe UI', system-ui, sans-serif",
  };

  let UID = 0;
  const uid = () => `atlas-g${++UID}`;

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function num(value) {
    if (value === null || value === undefined || typeof value === "boolean") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function compact(value, digits = 1) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    const n = Number(value);
    const sign = n < 0 ? "-" : "";
    const a = Math.abs(n);
    if (a >= 1e12) return `${sign}${(a / 1e12).toFixed(digits)}T`;
    if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(digits)}B`;
    if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(digits)}M`;
    if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(digits)}K`;
    if (a === Math.round(a)) return `${sign}${Math.round(a).toLocaleString("en-US")}`;
    return `${sign}${a.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  }

  function fmt(value, format = "number") {
    if (value === null || value === undefined || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return esc(value);
    if (format === "currency") {
      return `${n < 0 ? "-" : ""}$${compact(Math.abs(n))}`;
    }
    if (format === "percentage" || format === "percent_points") {
      return `${n.toFixed(1)}%`;
    }
    if (format === "ratio") return `${n.toFixed(2)}×`;
    if (Math.abs(n) >= 1000) return compact(n);
    if (n === Math.round(n)) return n.toLocaleString("en-US");
    return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }

  function shortDate(label) {
    const text = String(label ?? "").replace("T00:00:00", "").replace(" 00:00:00", "");
    const day = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (day) {
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return `${months[Number(day[2]) - 1]} ${Number(day[3])}`;
    }
    const month = text.match(/^(\d{4})-(\d{2})$/);
    if (month) {
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return `${months[Number(month[2]) - 1]} ${month[1]}`;
    }
    return text;
  }

  function axisDate(label, spanDays) {
    const text = String(label ?? "").replace("T00:00:00", "").replace(" 00:00:00", "");
    const day = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!day) return shortDate(label);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const base = `${months[Number(day[2]) - 1]} ${Number(day[3])}`;
    return spanDays > 300 ? `${months[Number(day[2]) - 1]} '${day[1].slice(2)}` : base;
  }

  function tickIndices(n, count) {
    if (n <= count) return Array.from({ length: n }, (_, i) => i);
    const out = new Set();
    for (let i = 0; i < count; i++) out.add(Math.round((i * (n - 1)) / (count - 1)));
    return [...out].sort((a, b) => a - b);
  }

  function truncate(text, limit) {
    const t = String(text ?? "");
    return esc(t.length > limit ? `${t.slice(0, limit - 1)}…` : t);
  }

  function svgOpen(w, h, label) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="100%" style="display:block;height:auto" role="img" aria-label="${esc(label || "chart")}" font-family="${C.font}">`;
  }

  function emptyChart(message, w, h) {
    return `${svgOpen(w, h, message)}<text x="${w / 2}" y="${h / 2}" text-anchor="middle" font-size="12" fill="${C.faint}">${esc(message)}</text></svg>`;
  }

  /* ---------------------------------------------------------------- */
  /* Bar                                                               */
  /* ---------------------------------------------------------------- */
  function bar(labels, values, opts = {}) {
    const mini = !!opts.mini;
    const w = opts.width || (mini ? 430 : 760);
    const h = opts.height || (mini ? 168 : 280);
    const horizontal = opts.horizontal !== false;
    let pairs = (labels || []).map((label, i) => ({ label: String(label ?? "—"), value: num((values || [])[i]) }));
    pairs = pairs.filter((p) => p.value !== null);
    if (!pairs.length) return emptyChart("No values to chart", w, h);
    if (horizontal) pairs.sort((a, b) => b.value - a.value);
    pairs = pairs.slice(0, mini ? 8 : 16);

    if (!horizontal) {
      const left = mini ? 36 : 58, right = 14, top = 16, bottom = 38;
      const pw = w - left - right, ph = h - top - bottom;
      const hi = Math.max(0, ...pairs.map((p) => p.value));
      const lo = Math.min(0, ...pairs.map((p) => p.value));
      const span = hi - lo || 1;
      const slot = pw / pairs.length;
      const bw = Math.min(mini ? 28 : 52, slot * 0.58);
      const zero = top + (hi / span) * ph;
      let out = svgOpen(w, h, opts.label);
      for (let t = 0; t < 4; t++) {
        const value = lo + (span * t) / 3;
        const y = top + ph - ((value - lo) / span) * ph;
        out += `<line x1="${left}" y1="${y.toFixed(1)}" x2="${left + pw}" y2="${y.toFixed(1)}" stroke="${C.grid}" stroke-width="1"/>`;
        if (!mini) out += `<text x="${left - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" font-size="9.5" fill="${C.faint}">${fmt(value, opts.format)}</text>`;
      }
      pairs.forEach((p, i) => {
        const cx = left + slot * (i + 0.5);
        const ey = top + ((hi - p.value) / span) * ph;
        const y = Math.min(zero, ey);
        const bh = Math.max(1.5, Math.abs(ey - zero));
        out += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="3" fill="${C.accent}" fill-opacity=".88"><title>${esc(p.label)}: ${fmt(p.value, opts.format)}</title></rect>`;
        if (!mini) out += `<text x="${cx.toFixed(1)}" y="${(y - 5).toFixed(1)}" text-anchor="middle" font-size="9.5" fill="${C.soft}">${fmt(p.value, opts.format)}</text>`;
        out += `<text x="${cx.toFixed(1)}" y="${top + ph + 17}" text-anchor="middle" font-size="${mini ? 8 : 10}" fill="${C.faint}">${truncate(p.label, mini ? 8 : 14)}</text>`;
      });
      out += "</svg>";
      return out;
    }

    const left = mini ? 98 : 152, right = mini ? 54 : 82, top = 8, bottom = 18;
    const pw = w - left - right, ph = h - top - bottom;
    const row = ph / pairs.length;
    const thick = Math.min(mini ? 15 : 23, row * 0.6);
    const hi = Math.max(0, ...pairs.map((p) => p.value));
    const lo = Math.min(0, ...pairs.map((p) => p.value));
    const span = hi - lo || 1;
    const zero = left + ((0 - lo) / span) * pw;
    let out = svgOpen(w, h, opts.label);
    for (let t = 0; t < 5; t++) {
      const value = lo + (span * t) / 4;
      const x = left + (pw * t) / 4;
      out += `<line x1="${x.toFixed(1)}" y1="${top}" x2="${x.toFixed(1)}" y2="${top + ph}" stroke="${C.grid}" stroke-width="1" stroke-opacity="${t === 0 ? 0 : 1}"/>`;
      if (!mini) out += `<text x="${x.toFixed(1)}" y="${top + ph + 15}" text-anchor="middle" font-size="9" fill="${C.faint}">${fmt(value, opts.format)}</text>`;
    }
    pairs.forEach((p, i) => {
      const y = top + row * i + (row - thick) / 2;
      const end = left + ((p.value - lo) / span) * pw;
      const x = Math.min(zero, end);
      const bw = Math.max(1.5, Math.abs(end - zero));
      out += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${thick.toFixed(1)}" rx="3" fill="${p.value >= 0 ? C.accent : C.rose}" fill-opacity=".88"><title>${esc(p.label)}: ${fmt(p.value, opts.format)}</title></rect>`;
      out += `<text x="${left - 9}" y="${(y + thick / 2 + 3.5).toFixed(1)}" text-anchor="end" font-size="${mini ? 8.5 : 10.5}" fill="${C.soft}">${truncate(p.label, mini ? 14 : 24)}</text>`;
      out += `<text x="${(end + (p.value >= 0 ? 7 : -7)).toFixed(1)}" y="${(y + thick / 2 + 3.5).toFixed(1)}" text-anchor="${p.value >= 0 ? "start" : "end"}" font-size="${mini ? 8.5 : 10}" font-weight="600" fill="${C.text}" fill-opacity=".9">${fmt(p.value, opts.format)}</text>`;
    });
    out += "</svg>";
    return out;
  }

  /* ---------------------------------------------------------------- */
  /* Line                                                              */
  /* ---------------------------------------------------------------- */
  function line(labels, values, opts = {}) {
    const mini = !!opts.mini;
    const w = opts.width || (mini ? 430 : 760);
    const h = opts.height || (mini ? 160 : 280);
    const left = mini ? 34 : 58, right = mini ? 14 : 26, top = 14, bottom = mini ? 24 : 34;
    const pw = w - left - right, ph = h - top - bottom;
    let pts = [];
    (labels || []).forEach((label, i) => {
      const v = num((values || [])[i]);
      if (v !== null) pts.push({ label: String(label ?? ""), value: v, index: i });
    });
    if (pts.length < 2) return emptyChart("Not enough points for a trend", w, h);
    const vals = pts.map((p) => p.value);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.12;
    lo -= pad; hi += pad;
    const span = hi - lo || 1;
    const xAt = (i) => left + (pw * i) / (pts.length - 1);
    const yAt = (v) => top + ((hi - v) / span) * ph;
    const coords = pts.map((p, i) => [xAt(i), yAt(p.value)]);
    const path = "M" + coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L");
    const area = `${path} L${coords[coords.length - 1][0].toFixed(1)},${(top + ph).toFixed(1)} L${coords[0][0].toFixed(1)},${(top + ph).toFixed(1)} Z`;
    const gradient = uid();
    let out = svgOpen(w, h, opts.label);
    out += `<defs><linearGradient id="${gradient}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.accent}" stop-opacity=".26"/><stop offset="1" stop-color="${C.accent}" stop-opacity="0"/></linearGradient></defs>`;
    for (let t = 0; t < 4; t++) {
      const value = lo + (span * t) / 3;
      const y = top + ph - ((value - lo) / span) * ph;
      out += `<line x1="${left}" y1="${y.toFixed(1)}" x2="${left + pw}" y2="${y.toFixed(1)}" stroke="${C.grid}" stroke-width="1"/>`;
      if (!mini) out += `<text x="${left - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" font-size="9" fill="${C.faint}">${fmt(value, opts.format)}</text>`;
    }
    out += `<path d="${area}" fill="url(#${gradient})"/>`;
    out += `<path d="${path}" fill="none" stroke="${C.accent}" stroke-width="${mini ? 2 : 2.3}" stroke-linejoin="round" stroke-linecap="round"/>`;
    if (pts.length <= 36) {
      pts.forEach((p, i) => {
        const [x, y] = coords[i];
        out += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${mini ? 2.1 : 3}" fill="${C.panel}" stroke="${C.accent}" stroke-width="1.6"><title>${esc(p.label)}: ${fmt(p.value, opts.format)}</title></circle>`;
      });
    }
    if (opts.anomalies && opts.anomalies.length) {
      opts.anomalies.forEach((flag) => {
        const idx = Number(flag.index);
        if (!Number.isInteger(idx) || idx < 0 || idx >= coords.length) return;
        const [x, y] = coords[idx];
        out += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${mini ? 3.2 : 4.3}" fill="none" stroke="${C.rose}" stroke-width="1.7" stroke-opacity=".95"><title>${esc(flag.label || "")}: ${fmt(flag.value, opts.format)}</title></circle>`;
      });
    }
    const spanDays = (() => {
      const first = String(pts[0].label).slice(0, 10), last = String(pts[pts.length - 1].label).slice(0, 10);
      const d1 = Date.parse(first), d2 = Date.parse(last);
      return Number.isFinite(d1) && Number.isFinite(d2) ? Math.abs(d2 - d1) / 86400000 : 0;
    })();
    tickIndices(pts.length, mini ? 4 : 6).forEach((i, n, arr) => {
      const x = coords[i][0];
      const anchor = i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle";
      out += `<text x="${x.toFixed(1)}" y="${top + ph + (mini ? 15 : 19)}" text-anchor="${anchor}" font-size="${mini ? 8 : 9.5}" fill="${C.faint}">${esc(axisDate(pts[i].label, spanDays))}</text>`;
    });
    if (!mini) {
      const [lx, ly] = coords[coords.length - 1];
      const label = fmt(pts[pts.length - 1].value, opts.format);
      const pill = Math.max(42, label.length * 6.5 + 14);
      const px = Math.min(w - pill - 4, lx - pill / 2);
      const py = Math.max(2, ly - 29);
      out += `<rect x="${px.toFixed(1)}" y="${py.toFixed(1)}" width="${pill.toFixed(1)}" height="19" rx="9.5" fill="${C.accent}" fill-opacity=".13" stroke="${C.accent}" stroke-opacity=".35"/><text x="${(px + pill / 2).toFixed(1)}" y="${(py + 13).toFixed(1)}" text-anchor="middle" font-size="9.5" font-weight="600" fill="${C.accent}">${label}</text>`;
    }
    out += "</svg>";
    return out;
  }

  /* ---------------------------------------------------------------- */
  /* Scatter                                                           */
  /* ---------------------------------------------------------------- */
  function scatter(points, opts = {}) {
    const mini = !!opts.mini;
    const w = opts.width || (mini ? 430 : 760);
    const h = opts.height || (mini ? 170 : 280);
    const left = mini ? 34 : 60, right = 18, top = 12, bottom = mini ? 24 : 42;
    const pw = w - left - right, ph = h - top - bottom;
    let clean = (points || []).filter((p) => Array.isArray(p) && num(p[0]) !== null && num(p[1]) !== null).map((p) => [Number(p[0]), Number(p[1])]);
    if (clean.length < 2) return emptyChart("Not enough paired values", w, h);
    if (clean.length > 1400) {
      const step = clean.length / 1400;
      clean = Array.from({ length: 1400 }, (_, i) => clean[Math.floor(i * step)]);
    }
    const xs = clean.map((p) => p[0]), ys = clean.map((p) => p[1]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (x0 === x1) { x0 -= 1; x1 += 1; }
    if (y0 === y1) { y0 -= 1; y1 += 1; }
    const xp = (x1 - x0) * 0.05, yp = (y1 - y0) * 0.08;
    x0 -= xp; x1 += xp; y0 -= yp; y1 += yp;
    const sx = (v) => left + ((v - x0) / (x1 - x0)) * pw;
    const sy = (v) => top + ((y1 - v) / (y1 - y0)) * ph;
    let out = svgOpen(w, h, opts.label);
    for (let t = 0; t < 4; t++) {
      const y = top + (ph * t) / 3;
      const val = y1 - ((y1 - y0) * t) / 3;
      out += `<line x1="${left}" y1="${y.toFixed(1)}" x2="${left + pw}" y2="${y.toFixed(1)}" stroke="${C.grid}" stroke-width="1"/>`;
      if (!mini) out += `<text x="${left - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" font-size="9" fill="${C.faint}">${fmt(val, opts.yFormat)}</text>`;
    }
    for (let t = 0; t < 4; t++) {
      const x = left + (pw * t) / 3;
      out += `<line x1="${x.toFixed(1)}" y1="${top}" x2="${x.toFixed(1)}" y2="${top + ph}" stroke="${C.gridSoft}" stroke-width="1"/>`;
      if (!mini) out += `<text x="${x.toFixed(1)}" y="${top + ph + 16}" text-anchor="middle" font-size="9" fill="${C.faint}">${fmt(x0 + ((x1 - x0) * t) / 3, opts.xFormat)}</text>`;
    }
    clean.forEach(([x, y]) => {
      out += `<circle cx="${sx(x).toFixed(1)}" cy="${sy(y).toFixed(1)}" r="${mini ? 2.1 : 2.8}" fill="${C.accent2}" fill-opacity=".48"/>`;
    });
    if (clean.length >= 3) {
      const n = clean.length;
      const mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
      let den = 0, cov = 0;
      for (let i = 0; i < n; i++) { den += (xs[i] - mx) ** 2; cov += (xs[i] - mx) * (ys[i] - my); }
      if (den) {
        const slope = cov / den, intercept = my - slope * mx;
        out += `<line x1="${sx(x0).toFixed(1)}" y1="${sy(intercept + slope * x0).toFixed(1)}" x2="${sx(x1).toFixed(1)}" y2="${sy(intercept + slope * x1).toFixed(1)}" stroke="${C.amber}" stroke-width="1.4" stroke-dasharray="6 5" stroke-opacity=".8"/>`;
      }
    }
    if (!mini) {
      out += `<text x="${left + pw / 2}" y="${h - 7}" text-anchor="middle" font-size="10" fill="${C.faint}">${esc(opts.xLabel || "X")}</text>`;
      out += `<text transform="translate(12,${(top + ph / 2).toFixed(1)}) rotate(-90)" text-anchor="middle" font-size="10" fill="${C.faint}">${esc(opts.yLabel || "Y")}</text>`;
    }
    out += "</svg>";
    return out;
  }

  /* ---------------------------------------------------------------- */
  /* Histogram                                                         */
  /* ---------------------------------------------------------------- */
  function histogram(counts, edges, opts = {}) {
    const mini = !!opts.mini;
    const w = opts.width || (mini ? 430 : 760);
    const h = opts.height || (mini ? 160 : 260);
    const left = mini ? 28 : 52, right = 16, top = 12, bottom = mini ? 26 : 36;
    const pw = w - left - right, ph = h - top - bottom;
    const cs = (counts || []).map((c) => Number(c) || 0);
    if (cs.length < 2) return emptyChart("Not enough values", w, h);
    const hi = Math.max(...cs) || 1;
    const slot = pw / cs.length;
    const bw = Math.max(2, slot - 2);
    let out = svgOpen(w, h, opts.label);
    for (let t = 0; t < 4; t++) {
      const y = top + ph - (ph * t) / 3;
      out += `<line x1="${left}" y1="${y.toFixed(1)}" x2="${left + pw}" y2="${y.toFixed(1)}" stroke="${C.grid}" stroke-width="1"/>`;
      if (!mini) out += `<text x="${left - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" font-size="9" fill="${C.faint}">${compact((hi * t) / 3)}</text>`;
    }
    cs.forEach((count, i) => {
      const bh = (count / hi) * ph;
      const x = left + i * slot + (slot - bw) / 2;
      out += `<rect x="${x.toFixed(1)}" y="${(top + ph - bh).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, bh).toFixed(1)}" rx="2" fill="${C.amber}" fill-opacity=".78"><title>${count.toLocaleString()} rows</title></rect>`;
    });
    if (!mini && edges && edges.length >= 2) {
      out += `<text x="${left}" y="${h - 7}" text-anchor="start" font-size="9" fill="${C.faint}">${fmt(edges[0], opts.format)}</text>`;
      out += `<text x="${left + pw}" y="${h - 7}" text-anchor="end" font-size="9" fill="${C.faint}">${fmt(edges[edges.length - 1], opts.format)}</text>`;
    }
    out += "</svg>";
    return out;
  }

  /* ---------------------------------------------------------------- */
  /* Forecast (history + interval band)                                */
  /* ---------------------------------------------------------------- */
  function forecastChart(history, rows, opts = {}) {
    const w = opts.width || 760, h = opts.height || 310;
    const left = 64, right = 26, top = 18, bottom = 38;
    const pw = w - left - right, ph = h - top - bottom;
    const hist = (history || []).map((p) => ({ date: p.date, value: Number(p.value) })).filter((p) => Number.isFinite(p.value));
    const fut = (rows || []).map((p) => ({ date: p.date, value: Number(p.value), lower: Number(p.lower), upper: Number(p.upper) })).filter((p) => Number.isFinite(p.value));
    const all = hist.concat(fut);
    if (all.length < 3) return emptyChart("Not enough data to forecast", w, h);
    const vals = all.flatMap((p) => [p.value, Number.isFinite(p.lower) ? p.lower : p.value, Number.isFinite(p.upper) ? p.upper : p.value]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    lo = Math.max(0, lo - pad); hi += pad;
    const span = hi - lo || 1;
    const n = all.length;
    const xAt = (i) => left + (pw * i) / (n - 1);
    const yAt = (v) => top + ((hi - v) / span) * ph;
    let out = svgOpen(w, h, opts.label || "Forecast");
    for (let t = 0; t < 4; t++) {
      const y = top + ph - (ph * t) / 3;
      const value = lo + (span * t) / 3;
      out += `<line x1="${left}" y1="${y.toFixed(1)}" x2="${left + pw}" y2="${y.toFixed(1)}" stroke="${C.grid}" stroke-width="1"/>`;
      out += `<text x="${left - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" font-size="9" fill="${C.faint}">${fmt(value, opts.format)}</text>`;
    }
    // interval band
    if (fut.length) {
      const start = hist.length - 1;
      const upper = fut.map((p, i) => [xAt(start + 1 + i), yAt(p.upper)]);
      const lower = fut.map((p, i) => [xAt(start + 1 + i), yAt(p.lower)]).reverse();
      const bandPts = [[xAt(start), yAt(hist[hist.length - 1].value)], ...upper, ...lower];
      out += `<path d="M${bandPts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L")} Z" fill="${C.accent}" fill-opacity=".09"/>`;
      const dash = fut.map((p, i) => `${xAt(start + 1 + i).toFixed(1)},${yAt(p.value).toFixed(1)}`);
      out += `<path d="M${xAt(start).toFixed(1)},${yAt(hist[hist.length - 1].value).toFixed(1)} L${dash.join(" L")}" fill="none" stroke="${C.accent2}" stroke-width="2" stroke-dasharray="5 5"/>`;
      fut.forEach((p, i) => {
        out += `<circle cx="${xAt(start + 1 + i).toFixed(1)}" cy="${yAt(p.value).toFixed(1)}" r="2.6" fill="${C.panel}" stroke="${C.accent2}" stroke-width="1.5"><title>${esc(p.date)}: ${fmt(p.value, opts.format)}</title></circle>`;
      });
    }
    const histPts = hist.map((p, i) => `${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`);
    out += `<path d="M${histPts.join(" L")}" fill="none" stroke="${C.accent}" stroke-width="2.2" stroke-linejoin="round"/>`;
    if (opts.anomalies && opts.anomalies.length) {
      const byDate = new Map(hist.map((point, index) => [String(point.date), index]));
      opts.anomalies.forEach((flag) => {
        let index = byDate.get(String(flag.date));
        if (index === undefined && Number.isInteger(Number(flag.index))) index = Number(flag.index);
        if (!Number.isInteger(index) || index < 0 || index >= hist.length) return;
        const [x, y] = [xAt(index), yAt(hist[index].value)];
        out += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.2" fill="none" stroke="${C.rose}" stroke-width="1.6"><title>${esc(flag.date)}: ${fmt(flag.value, opts.format)}${flag.z !== undefined ? ` · z ${Number(flag.z).toFixed(1)}` : ""}</title></circle>`;
      });
    }
    const labels = all.map((p) => p.date);
    tickIndices(n, 7).forEach((i) => {
      const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
      out += `<text x="${xAt(i).toFixed(1)}" y="${top + ph + 18}" text-anchor="${anchor}" font-size="9" fill="${C.faint}">${esc(axisDate(labels[i], 1))}</text>`;
    });
    if (hist.length && fut.length) {
      const box = [left + 6, top + 2, 170, 18];
      out += `<rect x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" rx="5" fill="${C.panel}" fill-opacity=".7"/>`;
      out += `<text x="${box[0] + 8}" y="${box[1] + 12.5}" font-size="8.5" fill="${C.faint}">forecast begins ${esc(shortDate(fut[0].date))}</text>`;
    }
    out += "</svg>";
    return out;
  }

  /* ---------------------------------------------------------------- */
  /* Dispatch                                                          */
  /* ---------------------------------------------------------------- */
  function render(chart, opts = {}) {
    if (!chart || !chart.type || chart.type === "table" || chart.type === "empty") {
      return "";
    }
    if (chart.type === "kpi") {
      return `<div class="chart-kpi"><div class="value">${fmt(chart.value, chart.format)}</div><div class="label">${esc(chart.label || chart.y_label || "Result")}</div></div>`;
    }
    if (chart.type === "bar") {
      return bar(chart.labels || [], chart.values || [], {
        mini: opts.mini,
        format: chart.format,
        horizontal: chart.horizontal !== false,
        label: chart.y_label,
      });
    }
    if (chart.type === "line") {
      return line(chart.labels || [], chart.values || [], {
        mini: opts.mini,
        format: chart.format,
        anomalies: chart.anomalies || [],
        label: chart.y_label,
      });
    }
    if (chart.type === "scatter") {
      return scatter(chart.points || [], {
        mini: opts.mini,
        xLabel: chart.x_label,
        yLabel: chart.y_label,
        xFormat: chart.x_format,
        yFormat: chart.y_format,
        label: `${chart.x_label || "X"} vs ${chart.y_label || "Y"}`,
      });
    }
    if (chart.type === "histogram") {
      return histogram(chart.counts || [], chart.edges || [], {
        mini: opts.mini,
        format: chart.format,
        label: chart.x_label,
      });
    }
    return "";
  }

  window.AtlasCharts = { fmt, compact, escape: esc, shortDate, bar, line, scatter, histogram, forecastChart, render };
})();
