import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

globalThis.window = globalThis;
vm.runInThisContext(fs.readFileSync("atlas/static/charts.js", "utf8"));
const charts = globalThis.window.AtlasCharts;

test("escape neutralises markup and quotes", () => {
  const output = charts.escape('<img src=x onerror="alert(1)">&');
  assert.equal(output, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;");
  assert.ok(!output.includes("<"));
});

test("fmt handles currency, percentages, ratios and missing values", () => {
  assert.equal(charts.fmt(1234.5), "1.2K");
  assert.equal(charts.fmt(1234.5, "currency"), "$1.2K");
  assert.equal(charts.fmt(-1200, "currency"), "-$1.2K");
  assert.equal(charts.fmt(12.34, "percentage"), "12.3%");
  assert.equal(charts.fmt(1.234, "ratio"), "1.23×");
  assert.equal(charts.fmt(null), "—");
  assert.equal(charts.fmt("not a number"), "not a number");
});

test("compact crosses unit boundaries", () => {
  assert.equal(charts.compact(999), "999");
  assert.equal(charts.compact(1000), "1.0K");
  assert.equal(charts.compact(1_500_000), "1.5M");
  assert.equal(charts.compact(-2_000_000_000), "-2.0B");
  assert.equal(charts.compact(Number.NaN), "—");
});

test("shortDate normalises ISO days and months", () => {
  assert.equal(charts.shortDate("2026-01-09"), "Jan 9");
  assert.equal(charts.shortDate("2026-01-09T00:00:00"), "Jan 9");
  assert.equal(charts.shortDate("2026-11"), "Nov 2026");
  assert.equal(charts.shortDate("Q3"), "Q3");
});

test("bar renders escaped labels and an SVG", () => {
  const svg = charts.bar(
    ["<script>alert(1)</script>", "EMEA"],
    [10, 20],
    { label: "<b>Revenue</b>" },
  );
  assert.ok(svg.startsWith("<svg"));
  assert.ok(!svg.includes("<script>"));
  assert.ok(svg.includes("&lt;script&gt;"));
  assert.ok(!svg.includes("<b>Revenue</b>"));
});

test("line refuses a single point and escapes tooltip labels", () => {
  assert.match(charts.line(["only"], [1]), /Not enough points/);
  const svg = charts.line(
    ['2026-01-0<script>1</script>', "2026-01-02", "2026-01-03"],
    [10, 12, 11],
  );
  assert.ok(!svg.includes("<script>"));
  assert.ok(svg.includes("&lt;script&gt;"));
});

test("histogram and scatter handle empty input without throwing", () => {
  assert.match(charts.histogram([], []), /Not enough values/);
  assert.match(charts.scatter([[1, 2]]), /Not enough paired values/);
});

test("forecastChart draws historical anomaly markers and escapes dates", () => {
  const history = [
    { date: "2026-01-01", value: 10 },
    { date: "2026-01-02", value: 30 },
    { date: "2026-01-03", value: 12 },
    { date: "2026-01-04", value: 14 },
  ];
  const future = [{ date: "2026-01-05", value: 15, lower: 12, upper: 18 }];
  const svg = charts.forecastChart(history, future, {
    anomalies: [{ date: "2026-01-02", value: 30, z: 3.9 }],
  });
  assert.ok(svg.includes("z 3.9"));
  assert.ok(svg.includes("2026-01-02"));
  assert.ok(svg.includes('stroke="#fb7185"'));
});

test("render treats table and empty charts as inert", () => {
  assert.equal(charts.render({ type: "table" }), "");
  assert.equal(charts.render({ type: "empty" }), "");
  assert.ok(!charts.render({ type: "kpi", value: 5, label: "<x>" }).includes("<x>"));
});
