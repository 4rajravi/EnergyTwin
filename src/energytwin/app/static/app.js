const state = {
  scenario: "normal",
  source: "demo",
  forecast: [],
  optimized: null,
  comparison: null,
  model: null,
  evaluation: null,
  dataHealth: null,
};

const $ = (selector) => document.querySelector(selector);
const svgNS = "http://www.w3.org/2000/svg";

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json();
}

function money(value) {
  return `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function number(value, suffix = "") {
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;
}

function metric(label, value, detail = "") {
  return `<article class="metric"><span>${label}</span><strong>${value}</strong><small>${detail}</small></article>`;
}

function policyCard(label, metrics) {
  return `<article class="policy">
    <span>${label}</span>
    <strong>${money(metrics.total_cost_usd)}</strong>
    <small>${number(metrics.cost_savings_pct, "%")} saved, ${money(metrics.demand_charge_usd)} demand charge</small>
  </article>`;
}

function setTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      $(`#${button.dataset.tab}`).classList.add("active");
    });
  });
}

async function loadScenarios() {
  const data = await getJson("/api/scenarios");
  const select = $("#scenario");
  select.innerHTML = data.scenarios.map((item) => `<option value="${item.key}">${item.label}</option>`).join("");
  select.addEventListener("change", async () => {
    state.scenario = select.value;
    await refresh();
  });
}

async function loadSources() {
  const data = await getJson("/api/data-sources");
  const select = $("#source");
  select.innerHTML = data.sources
    .map((item) => `<option value="${item.key}" ${item.available ? "" : "disabled"}>${item.label}${item.available ? "" : " (not imported)"}</option>`)
    .join("");
  select.value = state.source;
  select.addEventListener("change", async () => {
    state.source = select.value;
    await refresh();
  });
}

async function refresh() {
  const [forecastData, optimizedData, comparisonData, modelData, evaluationData, dataHealth] = await Promise.all([
    getJson(`/api/forecast?scenario=${state.scenario}&source=${state.source}`),
    getJson(`/api/simulate?scenario=${state.scenario}&source=${state.source}&controller=optimized`),
    getJson(`/api/optimize?scenario=${state.scenario}&source=${state.source}`),
    getJson(`/api/model-status?source=${state.source}&scenario=${state.scenario}`),
    getJson(`/api/forecast-evaluation?source=${state.source}&scenario=${state.scenario}`),
    getJson(`/api/data-health?scenario=${state.scenario}&source=${state.source}`),
  ]);
  state.forecast = forecastData.forecast;
  state.optimized = optimizedData;
  state.comparison = comparisonData.comparison;
  state.model = modelData;
  state.evaluation = evaluationData;
  state.dataHealth = dataHealth;
  render();
}

function render() {
  const metrics = state.optimized.metrics;
  const first = state.optimized.points[0];
  const maxRisk = Math.max(...state.forecast.map((point) => point.peak_risk));

  $("#liveMetrics").innerHTML = [
    metric("Grid import now", number(first.grid_import_kw, " kW"), "Current optimized hour"),
    metric("Battery state", number(first.battery_soc_kwh, " kWh"), "Usable capacity tracked"),
    metric("24h cost", money(metrics.total_cost_usd), `${number(metrics.grid_import_kwh, " kWh")} imported`),
    metric("Peak risk", number(maxRisk * 100, "%"), "Forecast peak exposure"),
  ].join("");

  $("#forecastMetrics").innerHTML = [
    metric("Peak demand", number(Math.max(...state.forecast.map((point) => point.demand_kw)), " kW"), "P90 band included"),
    metric("Solar max", number(Math.max(...state.forecast.map((point) => point.solar_kw)), " kW"), "Scenario adjusted"),
    metric("Avg price", money(avg(state.forecast.map((point) => point.price_usd_per_kwh)) * 1000), "per MWh equivalent"),
    metric("Carbon max", number(Math.max(...state.forecast.map((point) => point.carbon_kg_per_kwh)), " kg/kWh"), "Grid estimate"),
  ].join("");

  $("#policyGrid").innerHTML = [
    policyCard("Baseline", state.comparison.baseline),
    policyCard("Rule controller", state.comparison.rule),
    policyCard("Optimized controller", state.comparison.optimized),
    metric("Battery wear", money(state.comparison.optimized.battery_wear_cost_usd), `${number(state.comparison.optimized.battery_cycles, " cycles")} optimized`),
  ].join("");

  $("#modelMetrics").innerHTML = [
    metric("Active model", state.model.active_model, state.model.stage),
    metric("MAE", number(state.evaluation.mae_kw, " kW"), `RMSE ${number(state.evaluation.rmse_kw, " kW")}`),
    metric("sMAPE", number(state.evaluation.smape * 100, "%"), `Bias ${number(state.evaluation.bias_kw, " kW")}`),
    metric("P10-P90 coverage", number(state.evaluation.coverage_p10_p90 * 100, "%"), `${state.evaluation.evaluated_points} backtest points`),
    metric("Data health", `${state.dataHealth.valid_rows}/${state.dataHealth.row_count}`, `${state.dataHealth.invalid_rows} invalid rows`),
  ].join("");

  drawForecast();
  drawLive();
  drawCostBreakdown();
  drawPolicy();
}

function drawForecast() {
  const svg = $("#forecastChart");
  clear(svg);
  const rows = state.forecast;
  const maxY = Math.max(...rows.map((point) => point.demand_p90_kw)) * 1.08;
  const x = scale(0, rows.length - 1, 54, 930);
  const y = scale(0, maxY, 290, 22);
  drawGrid(svg, y, maxY);
  drawBand(svg, rows, x, y);
  drawLine(svg, rows.map((point, index) => [x(index), y(point.demand_kw)]), "line-demand");
  drawLine(svg, rows.map((point, index) => [x(index), y(point.solar_kw)]), "line-solar");
  drawLegend(svg, [["Demand", 64, "var(--blue)"], ["Solar", 150, "var(--green)"], ["P10-P90", 220, "rgba(104,167,255,0.45)"]]);
  drawHourLabels(svg, rows, x);
}

function drawLive() {
  const svg = $("#liveChart");
  clear(svg);
  const rows = state.optimized.points;
  const maxY = Math.max(...rows.flatMap((point) => [point.grid_import_kw, point.solar_kw, Math.abs(point.battery_kw)])) * 1.12;
  const x = scale(0, rows.length - 1, 54, 930);
  const y = scale(0, maxY, 290, 22);
  drawGrid(svg, y, maxY);
  drawLine(svg, rows.map((point, index) => [x(index), y(point.grid_import_kw)]), "line-demand");
  drawLine(svg, rows.map((point, index) => [x(index), y(point.solar_kw)]), "line-solar");
  drawLine(svg, rows.map((point, index) => [x(index), y(Math.abs(point.battery_kw))]), "line-battery");
  drawLegend(svg, [["Grid", 64, "var(--blue)"], ["Solar", 128, "var(--green)"], ["Battery", 194, "var(--amber)"]]);
  drawHourLabels(svg, rows, x);
}

function drawPolicy() {
  const svg = $("#policyChart");
  clear(svg);
  const policies = [
    ["Baseline", state.comparison.baseline],
    ["Rule", state.comparison.rule],
    ["Optimized", state.comparison.optimized],
  ];
  const maxCost = Math.max(...policies.map(([, item]) => item.total_cost_usd));
  const maxCarbon = Math.max(...policies.map(([, item]) => item.carbon_kg));
  const maxPeak = Math.max(...policies.map(([, item]) => item.peak_grid_kw));
  const groups = [
    ["Cost", "total_cost_usd", maxCost, "bar-cost"],
    ["Carbon", "carbon_kg", maxCarbon, "bar-carbon"],
    ["Peak", "peak_grid_kw", maxPeak, "bar-peak"],
  ];
  groups.forEach((group, groupIndex) => {
    const baseX = 92 + groupIndex * 292;
    label(svg, group[0], baseX, 28, "chart-label");
    policies.forEach(([name, item], policyIndex) => {
      const height = (item[group[1]] / group[2]) * 210;
      rect(svg, baseX + policyIndex * 58, 266 - height, 38, height, group[3]);
      label(svg, name, baseX + policyIndex * 58 - 4, 292, "chart-label");
    });
  });
}

function drawCostBreakdown() {
  const svg = $("#costBreakdownChart");
  clear(svg);
  const policies = [
    ["Baseline", state.comparison.baseline],
    ["Rule", state.comparison.rule],
    ["Optimized", state.comparison.optimized],
  ];
  const components = [
    ["energy_cost_usd", "Energy", "bar-cost"],
    ["demand_charge_usd", "Demand", "bar-demand-charge"],
    ["battery_wear_cost_usd", "Wear", "bar-battery-wear"],
  ];
  const maxTotal = Math.max(...policies.map(([, item]) => item.energy_cost_usd + item.demand_charge_usd + item.battery_wear_cost_usd));
  const y = scale(0, maxTotal, 264, 34);
  drawGrid(svg, y, maxTotal);
  drawLegend(svg, [["Energy", 64, "var(--blue)"], ["Demand", 140, "var(--amber)"], ["Wear", 230, "var(--violet)"], ["Export credit", 294, "var(--red)"]]);

  policies.forEach(([name, item], policyIndex) => {
    const x = 170 + policyIndex * 245;
    let stackTop = 264;
    components.forEach(([field, , className]) => {
      const height = 264 - y(item[field]);
      rect(svg, x, stackTop - height, 86, height, className);
      stackTop -= height;
    });
    if (item.export_credit_usd > 0) {
      const creditHeight = 264 - y(item.export_credit_usd);
      rect(svg, x + 94, 264 - creditHeight, 16, creditHeight, "bar-export-credit");
    }
    label(svg, name, x - 2, 292, "chart-label");
    label(svg, money(item.total_cost_usd), x - 2, 312, "chart-label");
  });
}

function clear(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function scale(inMin, inMax, outMin, outMax) {
  return (value) => outMin + ((value - inMin) / (inMax - inMin || 1)) * (outMax - outMin);
}

function avg(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function drawGrid(svg, y, maxY) {
  [0, 0.25, 0.5, 0.75, 1].forEach((tick) => {
    const yy = y(maxY * tick);
    line(svg, 54, yy, 930, yy, "grid");
    label(svg, Math.round(maxY * tick), 12, yy + 4, "chart-label");
  });
  line(svg, 54, 290, 930, 290, "axis");
}

function drawBand(svg, rows, x, y) {
  const upper = rows.map((point, index) => [x(index), y(point.demand_p90_kw)]);
  const lower = rows.map((point, index) => [x(index), y(point.demand_p10_kw)]).reverse();
  const points = upper.concat(lower).map((point) => point.join(",")).join(" ");
  const polygon = document.createElementNS(svgNS, "polygon");
  polygon.setAttribute("points", points);
  polygon.setAttribute("class", "band");
  svg.appendChild(polygon);
}

function drawLine(svg, points, className) {
  const polyline = document.createElementNS(svgNS, "polyline");
  polyline.setAttribute("points", points.map((point) => point.join(",")).join(" "));
  polyline.setAttribute("class", className);
  svg.appendChild(polyline);
}

function drawLegend(svg, entries) {
  entries.forEach(([text, x, color]) => {
    const marker = document.createElementNS(svgNS, "circle");
    marker.setAttribute("cx", x);
    marker.setAttribute("cy", 18);
    marker.setAttribute("r", 5);
    marker.setAttribute("fill", color);
    svg.appendChild(marker);
    label(svg, text, x + 10, 22, "chart-label");
  });
}

function drawHourLabels(svg, rows, x) {
  rows.forEach((row, index) => {
    if (index % 4 === 0) label(svg, `${row.hour}:00`, x(index) - 12, 318, "chart-label");
  });
}

function line(svg, x1, y1, x2, y2, className) {
  const element = document.createElementNS(svgNS, "line");
  element.setAttribute("x1", x1);
  element.setAttribute("y1", y1);
  element.setAttribute("x2", x2);
  element.setAttribute("y2", y2);
  element.setAttribute("class", className);
  svg.appendChild(element);
}

function rect(svg, x, y, width, height, className) {
  const element = document.createElementNS(svgNS, "rect");
  element.setAttribute("x", x);
  element.setAttribute("y", y);
  element.setAttribute("width", width);
  element.setAttribute("height", height);
  element.setAttribute("rx", 4);
  element.setAttribute("class", className);
  svg.appendChild(element);
}

function label(svg, text, x, y, className) {
  const element = document.createElementNS(svgNS, "text");
  element.setAttribute("x", x);
  element.setAttribute("y", y);
  element.setAttribute("class", className);
  element.textContent = text;
  svg.appendChild(element);
}

window.addEventListener("DOMContentLoaded", async () => {
  setTabs();
  await loadSources();
  await loadScenarios();
  await refresh();
});
