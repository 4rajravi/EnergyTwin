const state = {
  scenario: "normal",
  source: "demo",
  building: "Hog_office_Betsy",
  buildings: [],
  forecast: [],
  optimized: null,
  comparison: null,
  model: null,
  evaluation: null,
  dataHealth: null,
  mlopsRun: null,
  mlopsRuns: [],
  mlopsMonitoring: null,
  economics: {
    demandCharge: 3.2,
    exportCredit: 0.32,
    batteryWear: 0.018,
  },
  customScenario: {
    tempDelta: 0,
    cloudCover: 0.25,
    priceMultiplier: 1,
    evSpike: 0,
    comfort: 0.5,
  },
};

const $ = (selector) => document.querySelector(selector);
const svgNS = "http://www.w3.org/2000/svg";
let authPromptActive = false;

async function getJson(path) {
  let response = await fetch(path, authFetchOptions());
  if (response.status === 401) {
    const token = await requestAuthToken();
    if (token) {
      response = await fetch(path, authFetchOptions());
    }
  }
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json();
}

async function requestAuthToken() {
  if (authPromptActive) {
    while (authPromptActive) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    return window.localStorage.getItem("energytwinToken");
  }
  authPromptActive = true;
  const token = window.prompt("EnergyTwin API token");
  if (token) window.localStorage.setItem("energytwinToken", token);
  authPromptActive = false;
  return token;
}

function authFetchOptions() {
  const token = window.localStorage.getItem("energytwinToken");
  return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
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
    syncScenarioControlsToPreset();
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
    syncBuildingControl();
    await refresh();
  });
}

async function loadBuildings() {
  const data = await getJson("/api/buildings?limit=500");
  state.buildings = data.buildings || [];
  const select = $("#building");
  if (!state.buildings.length) {
    select.innerHTML = `<option value="">No Genome buildings</option>`;
    select.disabled = true;
    return;
  }
  select.innerHTML = state.buildings
    .map((item) => `<option value="${item.building_id}">${item.building_id} (${item.primaryspaceusage || item.site_id})</option>`)
    .join("");
  if (!state.buildings.some((item) => item.building_id === state.building)) {
    state.building = state.buildings[0].building_id;
  }
  select.value = state.building;
  select.addEventListener("change", async () => {
    state.building = select.value;
    await refresh();
  });
  syncBuildingControl();
}

function syncBuildingControl() {
  const select = $("#building");
  if (!select) return;
  select.disabled = state.source !== "genome" || !state.buildings.length;
}

function setEconomicsControls() {
  const controls = [
    ["#demandCharge", "demandCharge", (value) => Number(value)],
    ["#exportCredit", "exportCredit", (value) => Number(value) / 100],
    ["#batteryWear", "batteryWear", (value) => Number(value)],
  ];
  controls.forEach(([selector, key, parse]) => {
    const input = $(selector);
    input.addEventListener("change", async () => {
      const value = parse(input.value);
      if (Number.isFinite(value)) {
        state.economics[key] = value;
        await refresh();
      }
    });
  });
}

function setScenarioControls() {
  const controls = [
    ["#tempDelta", "tempDelta", (value) => Number(value)],
    ["#cloudCover", "cloudCover", (value) => Number(value) / 100],
    ["#priceMultiplier", "priceMultiplier", (value) => Number(value)],
    ["#evSpike", "evSpike", (value) => Number(value)],
    ["#comfort", "comfort", (value) => Number(value) / 100],
  ];
  controls.forEach(([selector, key, parse]) => {
    const input = $(selector);
    input.addEventListener("change", async () => {
      const value = parse(input.value);
      if (Number.isFinite(value)) {
        state.customScenario[key] = value;
        await refresh();
      }
    });
  });
}

function syncScenarioControlsToPreset() {
  const presets = {
    normal: { tempDelta: 0, cloudCover: 0.25, priceMultiplier: 1, evSpike: 0, comfort: 0.5 },
    hot: { tempDelta: 7, cloudCover: 0.18, priceMultiplier: 1, evSpike: 0, comfort: 0.8 },
    cloudy: { tempDelta: -1, cloudCover: 0.78, priceMultiplier: 1, evSpike: 0, comfort: 0.5 },
    price: { tempDelta: 0, cloudCover: 0.32, priceMultiplier: 1.65, evSpike: 0, comfort: 0.5 },
    ev: { tempDelta: 0, cloudCover: 0.25, priceMultiplier: 1, evSpike: 110, comfort: 0.5 },
    carbon: { tempDelta: 0, cloudCover: 0.4, priceMultiplier: 1.15, evSpike: 0, comfort: 0.5 },
  };
  state.customScenario = { ...presets[state.scenario] };
  $("#tempDelta").value = state.customScenario.tempDelta;
  $("#cloudCover").value = Math.round(state.customScenario.cloudCover * 100);
  $("#priceMultiplier").value = state.customScenario.priceMultiplier;
  $("#evSpike").value = state.customScenario.evSpike;
  $("#comfort").value = Math.round(state.customScenario.comfort * 100);
}

async function refresh() {
  const economics = economicsQuery();
  const scenario = scenarioQuery();
  const base = baseQuery();
  const [forecastData, optimizedData, comparisonData, modelData, evaluationData, dataHealth, mlopsRun, mlopsRuns, mlopsMonitoring] = await Promise.all([
    getJson(`/api/forecast?${base}&${scenario}`),
    getJson(`/api/simulate?${base}&controller=optimized&${scenario}&${economics}`),
    getJson(`/api/optimize?${base}&${scenario}&${economics}`),
    getJson(`/api/model-status?${base}&${scenario}`),
    getJson(`/api/forecast-evaluation?${base}&${scenario}`),
    getJson(`/api/data-health?${base}&${scenario}`),
    getJson("/api/mlops-run"),
    getJson("/api/mlops-runs?limit=5"),
    getJson("/api/mlops-monitoring?limit=12"),
  ]);
  state.forecast = forecastData.forecast;
  state.optimized = optimizedData;
  state.comparison = comparisonData.comparison;
  state.model = modelData;
  state.evaluation = evaluationData;
  state.dataHealth = dataHealth;
  state.mlopsRun = mlopsRun.error ? null : mlopsRun;
  state.mlopsRuns = mlopsRuns.runs || [];
  state.mlopsMonitoring = mlopsMonitoring;
  render();
}

function baseQuery() {
  const params = new URLSearchParams({
    scenario: state.scenario,
    source: state.source,
  });
  if (state.source === "genome" && state.building) {
    params.set("building", state.building);
  }
  return params.toString();
}

function scenarioQuery() {
  const params = new URLSearchParams({
    temp_delta: String(state.customScenario.tempDelta),
    cloud_cover: String(state.customScenario.cloudCover),
    price_multiplier: String(state.customScenario.priceMultiplier),
    ev_spike: String(state.customScenario.evSpike),
    comfort: String(state.customScenario.comfort),
  });
  return params.toString();
}

function economicsQuery() {
  const params = new URLSearchParams({
    demand_charge: String(state.economics.demandCharge),
    export_credit: String(state.economics.exportCredit),
    battery_wear: String(state.economics.batteryWear),
  });
  return params.toString();
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
    metric("Avg price", money(avg(state.forecast.map((point) => point.price_usd_per_kwh)) * 1000), `${number(state.customScenario.priceMultiplier, "x")} multiplier`),
    metric("Weather", `${number(state.customScenario.tempDelta, "C")} / ${number(state.customScenario.cloudCover * 100, "%")}`, "temp delta / cloud cover"),
  ].join("");

  $("#policyGrid").innerHTML = [
    policyCard("Baseline", state.comparison.baseline),
    policyCard("Rule controller", state.comparison.rule),
    policyCard("Optimized controller", state.comparison.optimized),
    metric("Economics", money(state.comparison.optimized.battery_wear_cost_usd), `${money(state.comparison.optimized.demand_charge_usd)} demand, ${number(state.economics.exportCredit * 100, "%")} export`),
  ].join("");

  renderScenarioMetrics();
  renderModelMetrics();
  renderMonitoringMetrics();
  renderRunHistory();
  drawMlopsTrend();
  drawForecast();
  drawLive();
  drawCostBreakdown();
  drawPolicy();
}

function renderScenarioMetrics() {
  $("#scenarioMetrics").innerHTML = [
    metric("Optimized savings", number(state.comparison.optimized.cost_savings_pct, "%"), `${money(state.comparison.optimized.total_cost_usd)} total`),
    metric("Peak reduction", number(state.comparison.optimized.peak_reduction_pct, "%"), `${number(state.comparison.optimized.peak_grid_kw, " kW")} peak`),
    metric("Carbon reduction", number(state.comparison.optimized.carbon_reduction_pct, "%"), `${number(state.comparison.optimized.carbon_kg, " kg")} CO2`),
    metric("Assumptions", `${number(state.customScenario.priceMultiplier, "x")} price`, `${number(state.customScenario.tempDelta, "C")}, ${number(state.customScenario.cloudCover * 100, "%")} cloud`),
  ].join("");
}

function renderModelMetrics() {
  const latest = state.mlopsRun;
  $("#modelMetrics").innerHTML = [
    metric("Active model", state.model.active_model, state.model.artifact && state.model.artifact.available ? "saved artifact" : "live baseline"),
    metric("Forecast error", number(state.evaluation.mae_kw, " kW"), `RMSE ${number(state.evaluation.rmse_kw, " kW")}`),
    metric("Data source", state.source, `${activeBuildingLabel()} / ${state.dataHealth.valid_rows} rows`),
    metric("Latest run", latest ? shortRunId(latest.run_id) : "None", latest ? latest.created_at.replace("T", " ").slice(0, 19) : "Run local pipeline"),
  ].join("");
}

function activeBuildingLabel() {
  if (state.source !== "genome") return state.dataHealth.source || state.source;
  return state.building;
}

function renderMonitoringMetrics() {
  const monitoring = state.mlopsMonitoring;
  if (!monitoring || !monitoring.latest) {
    $("#monitoringMetrics").innerHTML = [
      metric("Trend", "None", "Need at least one run"),
      metric("Best MAE", "-", "No run history"),
      metric("Promotion", "-", "No candidates"),
      metric("Latest decision", "-", "No candidate run"),
    ].join("");
    return;
  }
  const latestPromotion = monitoring.promotion.latest;
  $("#monitoringMetrics").innerHTML = [
    metric("Trend", monitoring.status, `${number(monitoring.mae_delta_kw, " kW")} from previous`),
    metric("Best MAE", number(monitoring.best.mae_kw, " kW"), shortRunId(monitoring.best.run_id)),
    metric("Promotion", `${monitoring.promotion.promoted}/${monitoring.promotion.candidate_runs}`, `${monitoring.promotion.rejected} rejected`),
    metric("Latest decision", latestPromotion ? (latestPromotion.promoted ? "Promoted" : "Rejected") : "None", latestPromotion ? shortReason(latestPromotion.reason) : "No candidate run"),
  ].join("");
  const pipelineData = $("#pipelineData");
  if (pipelineData) pipelineData.textContent = state.source === "imported" ? "imported CSV" : "demo profile";
}

function renderRunHistory() {
  const list = $("#runHistory");
  if (!state.mlopsRuns.length) {
    list.innerHTML = `<li><span>No runs yet</span><strong>Run local pipeline</strong></li>`;
    return;
  }
  list.innerHTML = state.mlopsRuns
    .map((run) => `<li>
      <span>${shortRunId(run.run_id)}<small>${run.created_at.replace("T", " ").slice(0, 19)}</small></span>
      <strong>${run.scenario_key} / ${number(run.mae_kw, " kW")}</strong>
    </li>`)
    .join("");
}

function drawMlopsTrend() {
  const svg = $("#mlopsTrendChart");
  if (!svg) return;
  clear(svg);
  const rows = (state.mlopsMonitoring && state.mlopsMonitoring.trend) || [];
  if (!rows.length) {
    label(svg, "No run history", 380, 170, "chart-label");
    return;
  }
  const maxY = Math.max(...rows.map((run) => run.mae_kw)) * 1.12;
  const minY = Math.min(0, Math.min(...rows.map((run) => run.mae_kw)) * 0.9);
  const x = scale(0, Math.max(1, rows.length - 1), 54, 930);
  const y = scale(minY, maxY, 278, 30);
  drawGrid(svg, y, maxY);
  drawLine(svg, rows.map((run, index) => [x(index), y(run.mae_kw)]), "line-demand");
  rows.forEach((run, index) => {
    const className = run.promoted ? "point-promoted" : "point-run";
    circle(svg, x(index), y(run.mae_kw), 5, className);
    if (index === 0 || index === rows.length - 1) {
      label(svg, `${number(run.mae_kw, " kW")}`, x(index) - 18, y(run.mae_kw) - 12, "chart-label");
    }
  });
  drawLegend(svg, [["MAE", 64, "var(--blue)"], ["Promoted", 126, "var(--green)"], ["Candidate/run", 220, "var(--amber)"]]);
}

function shortRunId(runId) {
  const parts = String(runId).split("-");
  return parts.slice(0, 2).join("-");
}

function shortReason(reason) {
  if (!reason) return "";
  if (reason.includes("improved")) return "candidate beat baseline";
  if (reason.includes("did not meet")) return "candidate stayed inactive";
  return reason.slice(0, 48);
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
    if (index % 4 === 0) label(svg, `${hourFor(row)}:00`, x(index) - 12, 318, "chart-label");
  });
}

function hourFor(row) {
  if (Number.isFinite(Number(row.hour))) return Number(row.hour);
  const parsed = new Date(row.timestamp);
  if (!Number.isNaN(parsed.getTime())) return parsed.getHours();
  return 0;
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

function circle(svg, x, y, radius, className) {
  const element = document.createElementNS(svgNS, "circle");
  element.setAttribute("cx", x);
  element.setAttribute("cy", y);
  element.setAttribute("r", radius);
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
  setEconomicsControls();
  setScenarioControls();
  syncScenarioControlsToPreset();
  await loadSources();
  await loadBuildings();
  await loadScenarios();
  await refresh();
});
