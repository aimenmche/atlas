"""Self-contained HTML report export.

No scripts, no external fonts, no CDN. Every chart is inline SVG, so the file
opens correctly offline and can be attached to an email or printed to PDF.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from .charts import fmt_value, render_chart
from .semantics import pretty
from .util import human_bytes

KIND_LABEL = {
    "correlation": "Relationship",
    "driver": "Driver",
    "association": "Association",
    "efficiency": "Efficiency",
    "concentration": "Concentration",
    "trend": "Trend",
    "anomaly": "Anomaly",
}

SEVERITY_COLOR = {"high": "#fb7185", "medium": "#fbbf24", "low": "#7dd3fc"}


def build_report(dataset: dict, generated_at: datetime | None = None) -> str:
    profile = dataset.get("profile") or {}
    insights = dataset.get("insights") or []
    quality = profile.get("quality") or {}
    notes = dataset.get("notes") or []
    name = dataset.get("name") or "Dataset"
    generated = (generated_at or datetime.now()).strftime("%d %B %Y, %H:%M")
    rows = int(profile.get("rows") or 0)
    cols = int(profile.get("cols") or 0)
    score = quality.get("score", 0)
    grade = quality.get("grade", "—")
    dims = quality.get("dimensions") or {}
    time_info = profile.get("time") or {}

    top = insights[:6]
    lead = insights[0] if insights else None

    lead_text = (
        lead.get("detail")
        if lead
        else "Atlas profiled this dataset but did not find a signal strong enough to lead the report."
    )
    summary = (
        f"{name} contains {rows:,} rows across {cols} columns. "
        f"Data quality scores {score:.1f}/100 (grade {grade}). "
        + (f"The strongest signal is: {lead.get('title')}. " if lead else "")
        + (f"Coverage runs from {_period(time_info.get('min'))} to {_period(time_info.get('max'))}." if time_info else "")
    )

    body: list[str] = []
    body.append(_header(name, generated))
    body.append(
        f"""
        <section class="hero">
          <div class="eyebrow"><span class="dot"></span> Dataset intelligence</div>
          <h1>{_e(name)}</h1>
          <p class="lede">{_e(summary)}</p>
          <div class="chips">
            <span class="chip">{rows:,} rows</span>
            <span class="chip">{cols} columns</span>
            <span class="chip">{_e(_source(dataset))}</span>
            <span class="chip">Quality {score:.1f} · {_e(grade)}</span>
            {f'<span class="chip">{_e(_period(time_info.get("min")))} → {_e(_period(time_info.get("max")))}</span>' if time_info else ''}
          </div>
        </section>
        """
    )

    body.append(
        f"""
        <section class="kpis">
          {_kpi(f"{rows:,}", "Rows analysed", "100% of the cleaned file")}
          {_kpi(str(cols), "Columns profiled", f"{len(profile.get('measures') or [])} measures · {len(profile.get('dimensions') or [])} dimensions")}
          {_kpi(f"{score:.1f}", f"Quality score · {grade}", "completeness, uniqueness, consistency, validity")}
          {_kpi(f"{dims.get('completeness', 0):.1f}%", "Completeness", f"{quality.get('missing_cells', 0):,} missing cells")}
        </section>
        """
    )

    # ---- The read ---------------------------------------------------- #
    body.append('<section class="section"><div class="section-head"><h2>The read</h2><span>Ranked by effect size and statistical support</span></div>')
    if top:
        for index, insight in enumerate(top[:3], start=1):
            body.append(
                f"""
                <article class="read">
                  <div class="read-index">{index:02d}</div>
                  <div>
                    <div class="read-kicker">{_e(KIND_LABEL.get(insight.get('kind'), insight.get('kind', 'Signal')))} · score {_num(insight.get('score'))}</div>
                    <h3>{_e(insight.get('title'))}</h3>
                    <p>{_e(insight.get('detail'))}</p>
                  </div>
                </article>
                """
            )
    else:
        body.append('<p class="muted">No ranked insights were produced for this dataset.</p>')
    body.append("</section>")

    # ---- Evidence ---------------------------------------------------- #
    body.append('<section class="section"><div class="section-head"><h2>Evidence</h2><span>Charts rendered from the same rows as the text</span></div>')
    body.append('<div class="evidence">')
    for insight in top:
        chart = insight.get("chart") or {}
        svg = render_chart(chart, width=720, height=250)
        stats = _stat_chips(insight)
        body.append(
            f"""
            <article class="card kind-{_e(insight.get('kind', 'other'))}">
              <div class="card-top">
                <span class="tag">{_e(KIND_LABEL.get(insight.get('kind'), insight.get('kind', 'Signal')))}</span>
                <span class="conf">{_e(str(insight.get('confidence', 'medium')).title())} confidence</span>
              </div>
              <h3>{_e(insight.get('title'))}</h3>
              <div class="chart">{svg}</div>
              {f'<div class="statline">{stats}</div>' if stats else ''}
            </article>
            """
        )
    body.append("</div></section>")

    # ---- Quality ------------------------------------------------------ #
    body.append('<section class="section"><div class="section-head"><h2>Data quality</h2><span>What would distort a naive answer</span></div>')
    body.append('<div class="quality-grid">')
    body.append('<div class="quality-bars">')
    for key, label in (
        ("completeness", "Completeness"),
        ("uniqueness", "Uniqueness"),
        ("consistency", "Consistency"),
        ("validity", "Validity"),
    ):
        value = float(dims.get(key) or 0)
        body.append(
            f"""
            <div class="qbar">
              <div class="qbar-head"><span>{label}</span><strong>{value:.1f}%</strong></div>
              <div class="track"><div class="fill" style="width:{max(0, min(100, value)):.1f}%"></div></div>
            </div>
            """
        )
    body.append("</div>")
    issues = quality.get("issues") or []
    if issues:
        body.append('<div class="issues">')
        for issue in issues[:8]:
            color = SEVERITY_COLOR.get(str(issue.get("severity")), "#8b98a9")
            body.append(
                f"""
                <div class="issue">
                  <span class="sev" style="background:{color}"></span>
                  <div><strong>{_e(issue.get("title"))}</strong><p>{_e(issue.get("detail"))}</p></div>
                </div>
                """
            )
        body.append("</div>")
    else:
        body.append('<p class="muted">No material quality issues detected.</p>')
    body.append("</div></section>")

    # ---- Columns ------------------------------------------------------ #
    body.append('<section class="section"><div class="section-head"><h2>Column dictionary</h2><span>Inferred types, roles and coverage</span></div>')
    body.append('<div class="table-wrap"><table><thead><tr><th>Column</th><th>Type</th><th>Role</th><th class="num">Missing</th><th class="num">Distinct</th><th>Sample</th></tr></thead><tbody>')
    for col in profile.get("columns") or []:
        sample = ""
        examples = col.get("top_values") or col.get("examples") or []
        if examples:
            first = examples[0]
            sample = str(first.get("value") if isinstance(first, dict) else first)
        pii = '<span class="pii">PII</span>' if col.get("pii") else ""
        body.append(
            f"""
            <tr>
              <td><strong>{_e(col.get('label') or col.get('name'))}</strong> {pii}<div class="colname">{_e(col.get('name'))}</div></td>
              <td><span class="type">{_e(col.get('dtype'))}</span></td>
              <td>{_e(col.get('role'))}<div class="colname">{_e(col.get('semantic'))}</div></td>
              <td class="num">{float(col.get('null_pct') or 0):.1f}%</td>
              <td class="num">{int(col.get('distinct') or 0):,}</td>
              <td class="sample">{_e(sample)}</td>
            </tr>
            """
        )
    body.append("</tbody></table></div></section>")

    # ---- Method ------------------------------------------------------- #
    method_notes = "".join(f"<li>{_e(note)}</li>" for note in notes[:8])
    body.append(
        f"""
        <section class="section method">
          <div class="section-head"><h2>Method & provenance</h2><span>How these numbers were produced</span></div>
          <div class="method-grid">
            <div>
              <h4>Grounded by construction</h4>
              <p>Every figure in this report comes from a SQL aggregate or a statistic computed over the cleaned rows. Nothing is generated by a language model unless a model is explicitly configured, and even then the prose is rejected if it introduces a number that is not present in the result set.</p>
              <h4>Storage</h4>
              <p>{rows:,} rows · {human_bytes(int(profile.get('memory_bytes') or 0))} in memory · {int(profile.get('duplicate_rows') or 0):,} duplicate rows. The database is local and read-only during analysis.</p>
            </div>
            <div>
              <h4>Cleaning log</h4>
              <ul>{method_notes or '<li>The file required no structural cleaning.</li>'}</ul>
            </div>
          </div>
        </section>
        """
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas report · {_e(name)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
{''.join(body)}
<footer>
  <div class="brand">ATLAS<span>·</span></div>
  <div>Generated {_e(generated)} from {_e(dataset.get('source') or 'an uploaded file')}. Charts and statistics computed locally.</div>
</footer>
</div>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Fragments
# --------------------------------------------------------------------------- #
def _header(name: str, generated: str) -> str:
    return f"""
    <header class="topbar">
      <div class="wordmark"><span class="mark">A</span> ATLAS</div>
      <div class="topbar-meta">Intelligence report <span>·</span> {_e(generated)}</div>
    </header>
    """


def _kpi(value: str, label: str, note: str) -> str:
    return f"""
    <div class="kpi-card">
      <div class="kpi-value">{_e(value)}</div>
      <div class="kpi-label">{_e(label)}</div>
      <div class="kpi-note">{_e(note)}</div>
    </div>
    """


def _stat_chips(insight: dict) -> str:
    stats = insight.get("stats") or {}
    chips: list[str] = []
    for key in ("r", "rho", "growth", "r2", "multiple", "z", "share", "gap", "v"):
        if key not in stats or stats[key] is None:
            continue
        value = stats[key]
        if key == "growth":
            chips.append(f"growth {float(value) * 100:+.1f}%")
        elif key == "r2":
            chips.append(f"R² {float(value):.2f}")
        elif key == "multiple":
            chips.append(f"{float(value):.1f}× typical")
        elif key == "z":
            chips.append(f"z {float(value):.1f}")
        elif key in {"share", "gap"}:
            chips.append(f"{key} {fmt_value(value, 'percentage')}")
        elif key in {"r", "rho"}:
            chips.append(f"{key} {float(value):.2f}")
        else:
            chips.append(f"{key} {fmt_value(value)}")
        if len(chips) == 3:
            break
    return "".join(f'<span class="stat">{_e(chip)}</span>' for chip in chips)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _e(text: Any) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _num(value: Any) -> str:
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return "—"


def _period(value: Any) -> str:
    if not value:
        return "—"
    text = str(value).replace("T00:00:00", "")[:10]
    for fmt_in, fmt_out in (("%Y-%m-%d", "%b %Y"), ("%Y-%m", "%b %Y"), ("%Y", "%Y")):
        try:
            return datetime.strptime(text, fmt_in).strftime(fmt_out)
        except ValueError:
            continue
    return text


def _source(dataset: dict) -> str:
    source = str(dataset.get("source") or "file")
    return {"csv": "CSV upload", "excel": "Excel upload", "json": "JSON upload", "parquet": "Parquet upload"}.get(source, source.title())


CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#080c11;color:#e7eef6;font-family:Inter,'Segoe UI',system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
.page{max-width:1080px;margin:0 auto;padding:28px 34px 60px}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:10px 0 24px;border-bottom:1px solid #1a2430}
.wordmark{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:700;letter-spacing:.22em}
.mark{display:grid;place-items:center;width:26px;height:26px;border-radius:8px;background:linear-gradient(145deg,#5eead4,#22d3ee);color:#041014;font-size:14px;letter-spacing:0}
.topbar-meta{font-size:11.5px;color:#8b98a9;letter-spacing:.06em;text-transform:uppercase}
.topbar-meta span{margin:0 6px;color:#3a4a5d}
.hero{padding:56px 0 30px}
.eyebrow{display:flex;align-items:center;gap:9px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#5eead4;font-weight:600}
.dot{width:6px;height:6px;border-radius:50%;background:#5eead4;box-shadow:0 0 12px #5eead4}
h1{font-size:54px;line-height:1.02;letter-spacing:-.035em;margin:18px 0 18px;font-weight:650}
.lede{max-width:780px;font-size:16px;line-height:1.65;color:#a9b6c7;margin:0 0 22px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:11.5px;padding:6px 11px;border:1px solid #243142;border-radius:999px;color:#b6c2d2;background:#0e1520}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 46px}
.kpi-card{padding:18px 18px 16px;border:1px solid #1b2634;border-radius:14px;background:linear-gradient(160deg,#101823,#0b1119)}
.kpi-value{font-size:30px;font-weight:650;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.kpi-label{font-size:12px;color:#b6c2d2;margin-top:7px}
.kpi-note{font-size:10.5px;color:#66758a;margin-top:5px;line-height:1.4}
.section{margin:0 0 50px}
.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:20px;border-top:1px solid #1a2430;padding-top:16px;margin-bottom:22px}
.section-head h2{font-size:13px;letter-spacing:.15em;text-transform:uppercase;margin:0;font-weight:650}
.section-head span{font-size:11.5px;color:#66758a}
.read{display:grid;grid-template-columns:58px 1fr;gap:18px;padding:18px 0;border-bottom:1px solid #141d28}
.read:last-child{border-bottom:0}
.read-index{font-size:12px;color:#5eead4;font-variant-numeric:tabular-nums;letter-spacing:.12em;padding-top:5px}
.read-kicker{font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:#66758a;margin-bottom:7px}
.read h3{font-size:21px;letter-spacing:-.02em;margin:0 0 7px;font-weight:600}
.read p{margin:0;color:#9aa8ba;line-height:1.62;font-size:13.8px;max-width:830px}
.evidence{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.card{border:1px solid #1b2634;border-radius:16px;background:linear-gradient(165deg,#0f1620,#0a1017);padding:18px 18px 10px;break-inside:avoid}
.card-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.tag{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:#5eead4;border:1px solid #1d4a47;background:#0d2523;border-radius:999px;padding:4px 8px}
.kind-anomaly .tag{color:#fbbf24;border-color:#4a3a15;background:#241c0a}
.kind-concentration .tag{color:#7dd3fc;border-color:#173f52;background:#0a2028}
.conf{font-size:10.5px;color:#66758a}
.card h3{font-size:14.5px;line-height:1.4;margin:0 0 8px;font-weight:600;letter-spacing:-.01em}
.chart{margin:2px -4px 0}
.chart svg{display:block;width:100%;height:auto}
.statline{display:flex;flex-wrap:wrap;gap:6px;padding:2px 0 10px}
.stat{font-size:10.5px;color:#a9b6c7;border:1px solid #1e2b3a;border-radius:6px;padding:3px 7px;font-variant-numeric:tabular-nums}
.quality-grid{display:grid;grid-template-columns:1fr 1fr;gap:34px}
.qbar{margin-bottom:15px}
.qbar-head{display:flex;justify-content:space-between;font-size:12px;color:#a9b6c7;margin-bottom:7px}
.qbar-head strong{color:#e7eef6;font-variant-numeric:tabular-nums}
.track{height:6px;background:#131c27;border-radius:99px;overflow:hidden}
.fill{height:100%;border-radius:99px;background:linear-gradient(90deg,#22d3ee,#5eead4)}
.issue{display:flex;gap:11px;padding:10px 0;border-bottom:1px solid #141d28}
.issue:last-child{border-bottom:0}
.sev{width:6px;height:6px;border-radius:50%;margin-top:6px;flex:0 0 6px}
.issue strong{font-size:12.5px;font-weight:600}
.issue p{margin:2px 0 0;font-size:12px;color:#8b98a9;line-height:1.5}
.table-wrap{border:1px solid #1b2634;border-radius:14px;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;padding:11px 14px;background:#0e1520;color:#66758a;font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;border-bottom:1px solid #1b2634}
td{padding:11px 14px;border-bottom:1px solid #131c27;color:#b6c2d2;vertical-align:top}
tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.colname{font-family:ui-monospace,'Cascadia Code',monospace;font-size:10px;color:#66758a;margin-top:2px}
.type{font-family:ui-monospace,'Cascadia Code',monospace;font-size:10.5px;color:#7dd3fc}
.sample{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11.5px;color:#8b98a9}
.pii{font-size:9px;letter-spacing:.08em;color:#fb7185;border:1px solid #4a1f29;background:#241016;border-radius:4px;padding:2px 5px;margin-left:5px;vertical-align:1px}
.method-grid{display:grid;grid-template-columns:1fr 1fr;gap:40px}
.method h4{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#8b98a9;margin:0 0 8px;font-weight:600}
.method p{font-size:13px;line-height:1.65;color:#8b98a9;margin:0 0 22px}
.method ul{margin:0;padding-left:18px;color:#8b98a9;font-size:12.5px;line-height:1.7}
.method li{margin-bottom:5px}
.muted{color:#66758a;font-size:13px}
footer{display:flex;justify-content:space-between;gap:24px;border-top:1px solid #1a2430;padding-top:18px;font-size:10.5px;color:#66758a;letter-spacing:.02em}
footer .brand{letter-spacing:.2em;font-weight:700;color:#b6c2d2}
footer .brand span{margin:0 6px;color:#3a4a5d}
@media (max-width:820px){
  .page{padding:20px}
  h1{font-size:38px}
  .kpis,.evidence,.quality-grid,.method-grid{grid-template-columns:1fr}
  .section-head{flex-direction:column;gap:6px}
}
@media print{
  body{background:#080c11;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .page{max-width:none;padding:0}
  .card,.read,.kpi-card{break-inside:avoid}
}
"""
