/* Atlas — landing interactions. No dependencies, no tracking. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  /* ------------------------------------------------------------------ */
  /* Chrome: nav, progress, cursor, reveals                             */
  /* ------------------------------------------------------------------ */
  function initChrome() {
    const nav = $("#nav");
    const bar = $("#scrollBar");
    const glow = $("#cursorGlow");
    let ticking = false;

    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY || document.documentElement.scrollTop;
        const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
        if (nav) nav.classList.toggle("is-scrolled", y > 18);
        if (bar) bar.style.transform = `scaleX(${clamp(y / max, 0, 1)})`;
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    if (glow && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      document.body.classList.add("has-pointer");
      let gx = window.innerWidth * 0.5;
      let gy = window.innerHeight * 0.3;
      let gTicking = false;
      window.addEventListener("pointermove", (event) => {
        gx = event.clientX;
        gy = event.clientY;
        if (gTicking) return;
        gTicking = true;
        requestAnimationFrame(() => {
          glow.style.setProperty("--cx", `${gx}px`);
          glow.style.setProperty("--cy", `${gy}px`);
          gTicking = false;
        });
      }, { passive: true });
    }

    const revealEls = $$(".reveal");
    if (reduced || !("IntersectionObserver" in window)) {
      revealEls.forEach((el) => el.classList.add("in"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    revealEls.forEach((el) => observer.observe(el));

    $$(".bento-card").forEach((card) => {
      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        card.style.setProperty("--mx", `${event.clientX - rect.left}px`);
        card.style.setProperty("--my", `${event.clientY - rect.top}px`);
      }, { passive: true });
    });

    $$("[data-copy]").forEach((button) => {
      button.addEventListener("click", async () => {
        const value = button.dataset.copy || "atlas";
        const label = button.querySelector("span:not(.cmd-prompt)");
        try {
          await navigator.clipboard.writeText(value);
        } catch {
          const field = document.createElement("textarea");
          field.value = value;
          field.style.position = "fixed";
          field.style.opacity = "0";
          document.body.appendChild(field);
          field.select();
          document.execCommand("copy");
          field.remove();
        }
        if (label) {
          const old = label.textContent;
          label.textContent = "copied";
          button.classList.add("copied");
          setTimeout(() => {
            label.textContent = old;
            button.classList.remove("copied");
          }, 1600);
        }
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* The data instrument                                                */
  /* ------------------------------------------------------------------ */
  function initOrb() {
    const canvas = $("#dataOrb");
    const orb = $("#orb");
    const title = $("#orbTitle");
    const meta = $("#orbMeta");
    if (!canvas || !orb || !canvas.getContext) return;

    const ctx = canvas.getContext("2d");
    const COUNT = 132;
    const FORMATIONS = ["bars", "wave", "orbit"];
    const CAPTIONS = [
      ["Revenue by plan", "4 categories · one clear leader"],
      ["Growth over time", "Monthly revenue · trend + season"],
      ["Segment clusters", "Rows projected into signal space"],
    ];
    const palette = ["#a7ffdd", "#a9c9ff", "#ffb86b", "#ff9cae"];
    const rgb = (hex) => {
      const n = parseInt(hex.slice(1), 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    };
    const paletteRGB = palette.map(rgb);
    const rand = (lo, hi) => lo + Math.random() * (hi - lo);

    function makeTargets(name) {
      const out = [];
      if (name === "bars") {
        const bars = [
          { x: 0.235, h: 0.57, color: 0 },
          { x: 0.43, h: 0.38, color: 1 },
          { x: 0.625, h: 0.245, color: 2 },
          { x: 0.82, h: 0.115, color: 3 },
        ];
        for (let i = 0; i < COUNT; i++) {
          const bar = bars[i % bars.length];
          out.push({
            x: bar.x + rand(-0.048, 0.048),
            y: 0.785 - rand(0.015, bar.h),
            r: rand(0.75, 1.9),
            color: paletteRGB[bar.color],
          });
        }
      } else if (name === "wave") {
        for (let i = 0; i < COUNT; i++) {
          const t = i / (COUNT - 1);
          const x = 0.075 + t * 0.85;
          const y = 0.71
            - 0.42 * t
            + 0.045 * Math.sin(t * Math.PI * 3.2 + 0.5)
            + 0.022 * Math.sin(t * Math.PI * 9)
            + rand(-0.009, 0.009);
          const c = t < 0.55 ? 0 : t < 0.82 ? 1 : 2;
          out.push({ x, y, r: rand(0.75, 1.85), color: paletteRGB[c] });
        }
      } else {
        const rings = [
          { rx: 0.345, ry: 0.118, rot: -0.5, color: 0, n: 46 },
          { rx: 0.305, ry: 0.105, rot: 0.55, color: 1, n: 43 },
          { rx: 0.265, ry: 0.09, rot: 1.6, color: 2, n: 43 },
        ];
        for (const ring of rings) {
          for (let i = 0; i < ring.n; i++) {
            const theta = (i / ring.n) * Math.PI * 2;
            const ex = ring.rx * Math.cos(theta);
            const ey = ring.ry * Math.sin(theta);
            out.push({
              x: 0.5 + ex * Math.cos(ring.rot) - ey * Math.sin(ring.rot),
              y: 0.5 + ex * Math.sin(ring.rot) + ey * Math.cos(ring.rot),
              r: rand(0.8, 2.0),
              color: paletteRGB[ring.color],
            });
          }
        }
      }
      return out;
    }

    const targets = Object.fromEntries(FORMATIONS.map((name) => [name, makeTargets(name)]));
    let formation = 0;
    let particles = targets.bars.map((target) => ({
      x: target.x, y: target.y, r: target.r,
      color: [...target.color],
      tx: target.x, ty: target.y, colorT: [...target.color],
    }));

    let width = 0;
    let height = 0;
    let dpr = 1;
    let visible = true;
    let mouse = { x: 0.5, y: 0.5, active: false };
    let lastMouse = { x: 0.5, y: 0.5 };
    let raf = 0;
    let autoTimer = 0;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function setFormation(next) {
      formation = (next + FORMATIONS.length) % FORMATIONS.length;
      const targetList = targets[FORMATIONS[formation]];
      particles.forEach((particle, index) => {
        const target = targetList[index] || targetList[0];
        particle.tx = target.x;
        particle.ty = target.y;
        particle.targetR = target.r;
        particle.colorT = target.color;
      });
      if (title && meta) {
        title.style.opacity = "0";
        meta.style.opacity = "0";
        setTimeout(() => {
          title.textContent = CAPTIONS[formation][0];
          meta.textContent = CAPTIONS[formation][1];
          title.style.opacity = "1";
          meta.style.opacity = "1";
        }, 140);
      }
    }

    function cycle() {
      setFormation(formation + 1);
    }

    function drawBarsGuide() {
      const bars = [
        { x: 0.235, h: 0.57 }, { x: 0.43, h: 0.38 },
        { x: 0.625, h: 0.245 }, { x: 0.82, h: 0.115 },
      ];
      ctx.save();
      ctx.lineWidth = 0.8;
      for (const bar of bars) {
        const x = bar.x * width;
        const w = width * 0.118;
        const top = (0.785 - bar.h) * height;
        const bottom = 0.785 * height;
        ctx.fillStyle = "rgba(94, 234, 212, 0.032)";
        ctx.strokeStyle = "rgba(167, 255, 221, 0.075)";
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x - w / 2, top, w, bottom - top, [5, 5, 0, 0]);
        else ctx.rect(x - w / 2, top, w, bottom - top);
        ctx.fill();
        ctx.stroke();
      }
      ctx.strokeStyle = "rgba(255, 255, 255, 0.09)";
      ctx.beginPath();
      ctx.moveTo(width * 0.1, height * 0.785);
      ctx.lineTo(width * 0.9, height * 0.785);
      ctx.stroke();
      ctx.font = "7px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(139, 151, 156, 0.55)";
      ctx.textAlign = "center";
      ["ENTERPRISE", "SCALE", "GROWTH", "STARTER"].forEach((label, i) => {
        ctx.fillText(label, bars[i].x * width, height * 0.835);
      });
      ctx.restore();
    }

    function drawWaveGuide() {
      const points = particles.map((p) => ({ x: p.x * width, y: p.y * height })).sort((a, b) => a.x - b.x);
      if (!points.length) return;
      ctx.save();
      const grad = ctx.createLinearGradient(0, height * 0.15, 0, height * 0.8);
      grad.addColorStop(0, "rgba(94, 234, 212, 0.14)");
      grad.addColorStop(1, "rgba(94, 234, 212, 0)");
      ctx.beginPath();
      ctx.moveTo(points[0].x, height * 0.785);
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        if (i === 0) ctx.lineTo(p.x, p.y);
        else {
          const prev = points[i - 1];
          const mx = (prev.x + p.x) / 2;
          const my = (prev.y + p.y) / 2;
          ctx.quadraticCurveTo(prev.x, prev.y, mx, my);
        }
      }
      ctx.lineTo(points[points.length - 1].x, height * 0.785);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.beginPath();
      points.forEach((p, i) => {
        if (i === 0) ctx.moveTo(p.x, p.y);
        else {
          const prev = points[i - 1];
          const mx = (prev.x + p.x) / 2;
          const my = (prev.y + p.y) / 2;
          ctx.quadraticCurveTo(prev.x, prev.y, mx, my);
        }
      });
      ctx.strokeStyle = "rgba(167, 255, 221, 0.7)";
      ctx.lineWidth = 1.15;
      ctx.shadowColor = "rgba(94, 234, 212, 0.5)";
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.restore();
    }

    function drawOrbitGuide() {
      const rings = [
        { rx: 0.345, ry: 0.118, rot: -0.5, color: "rgba(167, 255, 221, 0.16)" },
        { rx: 0.305, ry: 0.105, rot: 0.55, color: "rgba(169, 201, 255, 0.14)" },
        { rx: 0.265, ry: 0.09, rot: 1.6, color: "rgba(255, 184, 107, 0.12)" },
      ];
      ctx.save();
      ctx.translate(width * 0.5, height * 0.5);
      for (const ring of rings) {
        ctx.save();
        ctx.rotate(ring.rot);
        ctx.beginPath();
        ctx.ellipse(0, 0, ring.rx * width, ring.ry * height, 0, 0, Math.PI * 2);
        ctx.strokeStyle = ring.color;
        ctx.lineWidth = 0.8;
        ctx.stroke();
        ctx.restore();
      }
      ctx.restore();
    }

    function drawGuides() {
      ctx.save();
      ctx.strokeStyle = "rgba(255, 255, 255, 0.035)";
      ctx.lineWidth = 0.8;
      for (const radius of [0.18, 0.3, 0.42]) {
        ctx.beginPath();
        ctx.arc(width * 0.5, height * 0.5, Math.min(width, height) * radius, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.moveTo(width * 0.5, height * 0.06);
      ctx.lineTo(width * 0.5, height * 0.94);
      ctx.moveTo(width * 0.06, height * 0.5);
      ctx.lineTo(width * 0.94, height * 0.5);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.025)";
      ctx.stroke();
      ctx.restore();
    }

    function frame() {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const reduce = reduced;
      ctx.clearRect(0, 0, width, height);
      drawGuides();
      const name = FORMATIONS[formation];
      if (name === "bars") drawBarsGuide();
      else if (name === "wave") drawWaveGuide();
      else drawOrbitGuide();

      const driftX = (lastMouse.x - 0.5) * 0.018;
      const driftY = (lastMouse.y - 0.5) * 0.012;
      const targetList = targets[name];

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const target = targetList[i] || targetList[0];
        let tx = target.x + driftX;
        let ty = target.y + driftY;
        if (mouse.active && !reduce) {
          const dx = tx - mouse.x;
          const dy = ty - mouse.y;
          const dist = Math.hypot(dx, dy);
          if (dist < 0.09 && dist > 0.0001) {
            const push = (0.09 - dist) * 0.75;
            tx += (dx / dist) * push;
            ty += (dy / dist) * push;
          }
        }
        p.x += (tx - p.x) * (reduce ? 1 : 0.085);
        p.y += (ty - p.y) * (reduce ? 1 : 0.085);
        p.r += ((target.r || 1.4) - p.r) * (reduce ? 1 : 0.08);
        const c = target.color;
        p.color[0] += (c[0] - p.color[0]) * 0.06;
        p.color[1] += (c[1] - p.color[1]) * 0.06;
        p.color[2] += (c[2] - p.color[2]) * 0.06;

        const px = p.x * width;
        const py = p.y * height;
        if (px < -20 || px > width + 20 || py < -20 || py > height + 20) continue;
        ctx.beginPath();
        ctx.arc(px, py, Math.max(0.3, p.r), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${Math.round(p.color[0])}, ${Math.round(p.color[1])}, ${Math.round(p.color[2])}, 0.9)`;
        ctx.shadowColor = `rgba(${Math.round(p.color[0])}, ${Math.round(p.color[1])}, ${Math.round(p.color[2])}, 0.45)`;
        ctx.shadowBlur = 7;
        ctx.fill();
      }
      ctx.shadowBlur = 0;
    }

    function onPointer(event) {
      if (reduced) return;
      const rect = canvas.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width;
      const y = (event.clientY - rect.top) / rect.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) {
        mouse.active = false;
        return;
      }
      mouse = { x, y, active: true };
      lastMouse = { x, y };
    }

    if (orb) {
      orb.tabIndex = 0;
      orb.setAttribute("role", "button");
      orb.setAttribute("aria-label", "Morph the data visual between a bar chart, a trend line and segment clusters");
      orb.addEventListener("click", cycle);
      orb.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          cycle();
        }
      });
      orb.addEventListener("pointermove", onPointer, { passive: true });
      orb.addEventListener("pointerleave", () => { mouse.active = false; });
    }

    const resizeObserver = new ResizeObserver(() => {
      resize();
      if (reduced) frameOnce();
    });
    resizeObserver.observe(canvas);
    resize();

    function frameOnce() {
      visible = true;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(frame);
      setTimeout(() => cancelAnimationFrame(raf), 80);
    }

    if (reduced) {
      // Draw one settled frame, then leave the canvas alone.
      particles = targets.bars;
      frameOnce();
      if (title) title.textContent = CAPTIONS[0][0];
      if (meta) meta.textContent = CAPTIONS[0][1];
      return;
    }

    const visibilityObserver = new IntersectionObserver((entries) => {
      visible = entries.some((entry) => entry.isIntersecting);
    }, { threshold: 0.05 });
    visibilityObserver.observe(canvas);
    frame();
    autoTimer = window.setInterval(() => {
      if (visible && !document.hidden) setFormation(formation + 1);
    }, 5600);
    window.addEventListener("pagehide", () => {
      cancelAnimationFrame(raf);
      clearInterval(autoTimer);
    }, { once: true });
  }

  /* ------------------------------------------------------------------ */
  /* Live demo                                                          */
  /* ------------------------------------------------------------------ */
  function initDemo() {
    const section = $("#demo");
    const form = $("#demoForm");
    const input = $("#demoInput");
    const send = $("#demoSend");
    const chips = $("#demoChips");
    const trace = $("#demoTrace");
    const answer = $("#demoAnswer");
    if (!section || !form || !input || !send || !trace || !answer) return;

    const DATASET = "saas-revenue";
    const FIRST = "Which plan has the highest revenue?";
    let busy = false;
    let started = false;

    function setBusy(next) {
      busy = next;
      send.disabled = next;
      form.classList.toggle("is-busy", next);
      input.setAttribute("aria-busy", next ? "true" : "false");
    }

    function markChip(question) {
      $$("button[data-question]", chips || document).forEach((chip) => {
        chip.classList.toggle("active", chip.dataset.question === question);
      });
    }

    function busyTrace() {
      trace.innerHTML = `<div class="trace-empty"><span class="trace-orbit"></span>Reading the dataset…</div>`;
    }

    function busyAnswer() {
      answer.innerHTML = `
        <div class="answer-placeholder demo-busy">
          <div class="spinner-line"></div>
          <p class="placeholder-kicker">Running the local engine</p>
          <p class="placeholder-copy">Validating a read-only query and grounding the result.</p>
        </div>`;
    }

    function renderTrace(steps) {
      const rows = (steps || []).map((step, index) => `
        <div class="trace-step" style="animation-delay:${index * 55}ms">
          <span class="trace-icon">✓</span>
          <div class="trace-body">
            <div class="trace-label">${escapeHTML(step.label || "Working")}</div>
            ${step.detail ? `<div class="trace-detail" title="${escapeHTML(step.detail)}">${escapeHTML(step.detail)}</div>` : ""}
          </div>
          <span class="trace-ms">${Math.round(Number(step.ms) || 0)}ms</span>
        </div>`).join("");
      trace.innerHTML = rows + `<div class="trace-count">${(steps || []).length} stages · one query attempt</div>`;
    }

    function answerTable(result) {
      const columns = result?.columns || [];
      const rows = result?.rows || [];
      if (!columns.length) return "";
      const head = columns.map((c) => `<th>${escapeHTML(c)}</th>`).join("");
      const body = rows.slice(0, 8).map((row) => `<tr>${row.map((cell) => `<td>${escapeHTML(cell)}</td>`).join("")}</tr>`).join("");
      return `<div style="overflow:auto;margin-top:8px"><table style="width:100%;border-collapse:collapse;font-family:var(--mono);font-size:8px;color:var(--muted)"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    }

    function renderAnswer(data) {
      const chart = data.chart || {};
      const confidence = data.confidence || {};
      const plan = data.plan || {};
      const result = data.result || {};
      const chartHTML = (chart.type && chart.type !== "table" && window.AtlasCharts)
        ? window.AtlasCharts.render(chart)
        : answerTable(result);
      const highlights = (data.highlights || []).map((item) => `<span>${escapeHTML(item)}</span>`).join("");
      const caveats = (data.caveats || []).map((item) => `<div style="color:var(--amber);font-size:10px;line-height:1.6;margin-top:6px">${escapeHTML(item)}</div>`).join("");
      const confidenceClass = confidence.label === "low" ? " low" : confidence.label === "medium" ? " medium" : "";
      const kicker = data.engine === "llm" ? "Model-assisted plan" : "Deterministic plan";
      const intent = plan.intent ? plan.intent.replace(/_/g, " ") : "";
      const sqlId = `demo-sql-${Date.now()}`;

      answer.innerHTML = `
        <div class="answer-shell">
          <div class="answer-top">
            <div>
              <div class="answer-kicker"><i></i>${escapeHTML(kicker)}${intent ? ` · ${escapeHTML(intent)}` : ""}</div>
              <h3 class="answer-title">${escapeHTML(plan.title || data.question || "Answer")}</h3>
            </div>
            <span class="answer-conf${confidenceClass}">${escapeHTML(confidence.label || "medium")} confidence</span>
          </div>
          <p class="answer-narrative">${escapeHTML(data.narrative || "")}</p>
          ${chartHTML ? `<div class="answer-chart">${chartHTML}</div>` : ""}
          ${highlights ? `<div class="answer-highlights">${highlights}</div>` : ""}
          ${caveats}
          <div class="answer-foot">
            <button type="button" data-sql-toggle="${sqlId}">SQL</button>
            <span>${Number(result.row_count || 0).toLocaleString()} rows</span>
            <span>${Math.round(Number(data.elapsed_ms) || 0)} ms</span>
            <span class="spacer"></span>
            <span>${escapeHTML((data.engine || "deterministic").toUpperCase())}</span>
          </div>
          <div class="answer-sql hidden" id="${sqlId}" hidden><pre>${escapeHTML(data.sql || "")}</pre></div>
        </div>`;
    }

    function renderError(message, hint) {
      trace.innerHTML = `<div class="trace-empty"><span class="trace-orbit"></span>No answer returned.</div>`;
      answer.innerHTML = `
        <div class="answer-error">
          <h3>Analysis stopped.</h3>
          <p>${escapeHTML(message || "The local engine could not answer that question.")}</p>
          ${hint ? `<p style="color:var(--faint);margin-top:6px">${escapeHTML(hint)}</p>` : ""}
          <p style="color:var(--faint);margin-top:10px">Try one of the prompts or start Atlas with <code style="color:var(--mint)">atlas</code>.</p>
        </div>`;
    }

    async function ask(question) {
      const q = String(question || "").trim();
      if (!q || busy) return;
      input.value = q;
      markChip(q);
      setBusy(true);
      busyTrace();
      busyAnswer();
      const startedAt = performance.now();
      try {
        const response = await fetch(`/api/datasets/${encodeURIComponent(DATASET)}/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q }),
        });
        let payload = null;
        try { payload = await response.json(); } catch { /* no body */ }
        if (!response.ok) {
          const detail = payload?.detail;
          throw new Error(detail?.error || detail?.hint || (typeof detail === "string" ? detail : `Request failed (${response.status})`));
        }
        const wait = Math.max(0, 520 - (performance.now() - startedAt));
        if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
        renderTrace(payload.trace || []);
        await new Promise((resolve) => setTimeout(resolve, 360));
        renderAnswer(payload);
      } catch (error) {
        renderError(error.message, "The demo is live, so the local service must be running.");
      } finally {
        setBusy(false);
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      ask(input.value);
    });
    if (chips) {
      chips.addEventListener("click", (event) => {
        const button = event.target.closest("[data-question]");
        if (button) ask(button.dataset.question);
      });
    }
    answer.addEventListener("click", (event) => {
      const button = event.target.closest("[data-sql-toggle]");
      if (!button) return;
      const panel = document.getElementById(button.dataset.sqlToggle);
      if (!panel) return;
      panel.hidden = !panel.hidden;
      button.textContent = panel.hidden ? "SQL" : "Hide SQL";
    });

    if (reduced || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      if (started) return;
      if (entries.some((entry) => entry.isIntersecting)) {
        started = true;
        observer.disconnect();
        ask(FIRST);
      }
    }, { threshold: 0.22 });
    observer.observe(section);
  }

  function boot() {
    initChrome();
    initOrb();
    initDemo();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
