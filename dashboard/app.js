// GVMC grievance dashboard: a static page that reads the PI4C API from the browser (CORS is open).

const API = "http://localhost:8000/api/v1";
const API_ORIGIN = new URL(API).origin;

// Rough GVMC limits (Anakapalle in the west to Bheemunipatnam in the north-east), as minLon,minLat,maxLon,maxLat.
const GVMC_BBOX = "82.95,17.55,83.50,17.98";
const GVMC_CENTER = [17.7231, 83.3013];

const PAGE_SIZE = 25;
const AUTO_REFRESH_MS = 2 * 60 * 1000;

const STATUSES = ["new", "acknowledged", "in_progress", "resolved", "rejected"];
const CLOSED = new Set(["resolved", "rejected"]);
const SEVERITIES = ["critical", "high", "medium", "low"];

const state = {
  categories: {},     // id -> label
  subcategories: {},  // id -> label
  departments: {},    // id -> name
  category: "",
  view: "map",
  offset: 0,
  writeAccess: false,
  openReport: null,
};

const $ = (sel) => document.querySelector(sel);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---- helpers -------------------------------------------------------------------------------

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function humanize(id) {
  return id ? id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "—";
}

const catLabel = (id) => state.categories[id] || humanize(id);
const subLabel = (id) => state.subcategories[id] || humanize(id);
const deptLabel = (id) => (id ? state.departments[id] || humanize(id) : "Unassigned");
const statusColor = (s) => css(`--s-${s}`) || css("--s-rejected");
const sevColor = (s) => css(`--sev-${s}`) || "#9aa0a6";

// The API sends UTC timestamps without a zone suffix.
function parseUtc(iso) {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
}

function fmtDateTime(iso) {
  return parseUtc(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function pill(text, color, light = false) {
  return `<span class="pill${light ? " light" : ""}" style="background:${color}">${esc(text)}</span>`;
}

const sevPill = (s) => (s ? pill(humanize(s), sevColor(s), s === "medium") : "—");

async function api(path, params, options = {}) {
  const qs = params && params.toString() ? `?${params}` : "";
  const res = await fetch(`${API}${path}${qs}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

function showError(message) {
  const box = $("#error");
  box.textContent = message || "";
  box.hidden = !message;
}

// ---- filters -------------------------------------------------------------------------------

function filterParams() {
  const p = new URLSearchParams();
  if (state.category) p.set("category", state.category);
  for (const select of $("#selects").querySelectorAll("select")) {
    if (select.value) p.set(select.name, select.value);
  }
  if ($("#area").value === "gvmc") p.set("bbox", GVMC_BBOX);
  const f = $("#filters").elements;
  if (f.pwd_marker.checked) p.set("pwd_marker", "true");
  if (f.needs_review.checked) p.set("needs_review", "true");
  // Dates are picked in IST; the API takes any ISO time and "to" is exclusive, so use the next midnight.
  if (f.from.value) p.set("created_from", new Date(`${f.from.value}T00:00:00+05:30`).toISOString());
  if (f.to.value) {
    const end = new Date(`${f.to.value}T00:00:00+05:30`);
    end.setUTCDate(end.getUTCDate() + 1);
    p.set("created_to", end.toISOString());
  }
  return p;
}

function withParams(base, ...pairs) {
  const p = new URLSearchParams(base);
  for (const [k, v] of pairs) p.append(k, v);
  return p;
}

function fillSelect(select, options, { keepFirst = true } = {}) {
  const first = keepFirst ? select.options[0]?.outerHTML || "" : "";
  select.innerHTML = first + options.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
}

// ---- reference data ------------------------------------------------------------------------

async function loadMeta() {
  const [taxonomy, depts] = await Promise.all([api("/taxonomy"), api("/departments")]);
  for (const cat of taxonomy.categories) {
    state.categories[cat.id] = cat.label_en;
    for (const sub of cat.subcategories) state.subcategories[sub.id] = sub.label_en;
  }
  for (const d of depts.departments) state.departments[d.id] = d.name_en;

  const s = $("#selects");
  fillSelect(s.querySelector("[name=status]"), STATUSES.map((x) => [x, humanize(x)]));
  fillSelect(s.querySelector("[name=severity]"), SEVERITIES.map((x) => [x, humanize(x)]));
  fillSelect(s.querySelector("[name=department_id]"), depts.departments.map((d) => [d.id, d.name_en]));

  const d = $("#d-form").elements;
  fillSelect(d.status, STATUSES.map((x) => [x, humanize(x)]), { keepFirst: false });
  fillSelect(d.severity, SEVERITIES.map((x) => [x, humanize(x)]), { keepFirst: false });
  fillSelect(d.department_id, depts.departments.map((x) => [x.id, x.name_en]), { keepFirst: false });

  $("#legend").innerHTML = SEVERITIES
    .map((x) => `<div><span class="swatch" style="background:${sevColor(x)}"></span>${humanize(x)} severity</div>`)
    .join("");
}

// Write endpoints answer 403 when WRITE_ACCESS=false. Report 0 never exists, so 404 means writing is on.
async function probeWriteAccess() {
  try {
    const res = await fetch(`${API}/reports/0/log`);
    state.writeAccess = res.status !== 403;
  } catch {
    state.writeAccess = false;
  }
  const badge = $("#write-badge");
  badge.hidden = false;
  badge.textContent = state.writeAccess ? "Editing on" : "Read-only";
  badge.title = state.writeAccess ? "Reports can be updated from this dashboard" : "The server has WRITE_ACCESS=false";
}

// ---- map -----------------------------------------------------------------------------------

let map;
let markers;

function initMap() {
  map = L.map("map").setView(GVMC_CENTER, 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  markers = L.featureGroup().addTo(map);
  // Leaflet only re-measures on window resize; layout changes (panels, view tabs, narrow screens) need this too
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));
}

function renderMap(geojson, fit) {
  markers.clearLayers();
  // Draw closed reports first so open ones sit on top
  const features = [...geojson.features].sort((a, b) => CLOSED.has(b.properties.status) - CLOSED.has(a.properties.status));
  for (const f of features) {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    const closed = CLOSED.has(p.status);
    L.circleMarker([lat, lon], {
      radius: p.pwd_marker ? 9 : 6,
      color: closed ? "#8a9099" : "#1b1d24",
      weight: 1,
      fillColor: sevColor(p.severity),
      fillOpacity: closed ? 0.3 : 0.9,
    })
      .bindTooltip(`<b>${esc(p.ref)}</b><br>${esc(subLabel(p.barrier_type))}<br>${esc(humanize(p.severity))} severity · ${esc(humanize(p.status))}`)
      .bindPopup("", { minWidth: 260, maxWidth: 300, className: "report-popup", autoPanPaddingTopLeft: [20, 60] })
      .on("popupopen", (e) => {
        e.target.closeTooltip();
        // Build the content once per opening; a content function would be re-run (and the photo lost) on every popup.update()
        const el = popupContent(f);
        e.popup.setContent(el);
        loadPopupPhoto(f.id, e.popup, el);
      })
      .addTo(markers);
  }
  if (!fit) return;
  // Keep the dots clear of the info panel when it is open over the right side of the map
  const panel = $("#info-panel");
  const right = panel.hidden || panel.offsetParent === null || getComputedStyle(panel).position !== "absolute" ? 40 : panel.offsetWidth + 40;
  if (geojson.features.length) map.fitBounds(markers.getBounds(), { paddingTopLeft: [40, 40], paddingBottomRight: [right, 40], maxZoom: 15 });
  else map.setView(GVMC_CENTER, 12);
}

// Popup for a map dot: details from the GeoJSON straight away, the photo once the report has loaded.
function popupContent(f) {
  const p = f.properties;
  const el = document.createElement("div");
  el.innerHTML = `
    <div class="popup-photo"><span class="muted">Loading photo…</span></div>
    <div class="popup-body">
      <div class="popup-ref">${esc(p.ref)}</div>
      <div class="popup-issue">${esc(subLabel(p.barrier_type))} <span class="muted">· ${esc(catLabel(p.category))}</span></div>
      <div class="popup-pills">${sevPill(p.severity)} ${pill(humanize(p.status), statusColor(p.status))}${p.pwd_marker ? ` ${pill("PwD", "#1d2033")}` : ""}</div>
      <div class="muted popup-date">Reported ${esc(fmtDateTime(p.created_at))}</div>
      <button type="button" class="popup-open">Open full report</button>
    </div>`;
  el.querySelector(".popup-open").addEventListener("click", () => openReport(f.id));
  return el;
}

const reportCache = new Map();

async function loadPopupPhoto(id, popup, el) {
  const slot = el.querySelector(".popup-photo");
  try {
    if (!reportCache.has(id)) reportCache.set(id, await api(`/reports/${id}`));
    const photo = reportCache.get(id).media.find((m) => m.kind === "image");
    if (!photo) {
      slot.innerHTML = `<span class="muted">No photo attached</span>`;
      slot.classList.add("none");
      return;
    }
    const url = API_ORIGIN + photo.url;
    slot.innerHTML = `<a href="${esc(url)}" target="_blank" rel="noopener" title="Open photo in a new tab"><img src="${esc(url)}" alt="Photo attached to ${esc(reportCache.get(id).ref)}"></a>`;
    // Re-fit and re-pan once the image has its real height
    slot.querySelector("img").addEventListener("load", () => popup.update(), { once: true });
  } catch {
    slot.innerHTML = `<span class="muted">Could not load the photo</span>`;
  }
}

// ---- charts --------------------------------------------------------------------------------

function renderBars(el, rows) {
  if (!rows.length) {
    el.innerHTML = `<div class="empty">No reports</div>`;
    return;
  }
  const max = Math.max(...rows.map((r) => r.count));
  el.innerHTML = rows
    .map((r) => `
      <div class="bar-row">
        <span title="${esc(r.label)}">${esc(r.label)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(r.count / max) * 100}%;${r.color ? `background:${r.color}` : ""}"></div></div>
        <span class="bar-count">${r.count}</span>
      </div>`)
    .join("");
}

function periodLabel(period, interval) {
  const d = new Date(`${period}T00:00:00Z`);
  if (interval === "month") return d.toLocaleDateString("en-IN", { month: "short", year: "numeric", timeZone: "UTC" });
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
}

function renderTimeseries(rows, interval) {
  const el = $("#timeseries");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">No reports</div>`;
    return;
  }
  const max = Math.max(...rows.map((r) => r.count));
  el.innerHTML = rows
    .map((r) => `
      <div class="col" title="${esc(periodLabel(r.period, interval))}: ${r.count}">
        <span class="col-count">${r.count}</span>
        <div class="col-fill" style="height:${(r.count / max) * 100}%"></div>
        <span class="col-label">${esc(periodLabel(r.period, interval))}</span>
      </div>`)
    .join("");
}

function renderKpis(s) {
  const items = [
    ["Total reports", s.reports],
    ["Open", s.open],
    ["Resolved", s.resolved],
    ["High / critical", s.high_or_critical],
    ["PwD reports", s.pwd_marker],
    ["Needs review", s.needs_review],
    ["Distinct problems", s.distinct_problems],
    ["With photo", s.with_photo],
  ];
  $("#kpis").innerHTML = items
    .map(([label, value]) => `<div class="kpi"><div class="value">${value ?? 0}</div><div class="label">${label}</div></div>`)
    .join("");
}

function sumBy(rows, key, keep = () => true) {
  const totals = new Map();
  for (const r of rows) if (keep(r)) totals.set(r[key], (totals.get(r[key]) || 0) + r.count);
  return [...totals].map(([k, count]) => ({ key: k, count })).sort((a, b) => b.count - a.count);
}

// ---- table ---------------------------------------------------------------------------------

function renderTable(page) {
  $("#report-total").textContent = `(${page.total})`;
  const from = page.total ? page.offset + 1 : 0;
  const to = Math.min(page.offset + page.items.length, page.total);
  $("#page-info").textContent = `${from}–${to} of ${page.total}`;
  $("#prev").disabled = page.offset === 0;
  $("#next").disabled = page.offset + page.limit >= page.total;

  if (!page.items.length) {
    $("#rows").innerHTML = `<tr><td colspan="8" class="empty">No reports match these filters.</td></tr>`;
    return;
  }
  $("#rows").innerHTML = page.items
    .map((r) => `
      <tr data-id="${r.id}">
        <td><b>${esc(r.ref)}</b></td>
        <td>${esc(fmtDateTime(r.created_at))}</td>
        <td>${esc(subLabel(r.subcategory))} <span class="muted">· ${esc(catLabel(r.category))}</span></td>
        <td>${esc(deptLabel(r.department_id))}</td>
        <td>${sevPill(r.severity)}</td>
        <td>${pill(humanize(r.status), statusColor(r.status))}</td>
        <td>${r.pwd_marker ? "Yes" : ""}</td>
        <td class="loc" title="${esc(r.location_address || r.location_name || "")}">${esc(r.location_name || r.location_address || `${r.latitude.toFixed(4)}, ${r.longitude.toFixed(4)}`)}</td>
      </tr>`)
    .join("");
}

// ---- refresh -------------------------------------------------------------------------------

async function refresh({ fit = false } = {}) {
  reportCache.clear();
  const p = filterParams();
  const interval = $("#interval").value;
  const csv = `${API}/reports.csv?${p}`;
  $("#csv").href = csv;
  $("#csv-side").href = csv;
  $("#view-title").textContent = state.category ? catLabel(state.category) : "All reports";
  try {
    const [summary, byStatus, bySeverity, byDeptStatus, bySub, series, geojson, page] = await Promise.all([
      api("/stats/summary", p),
      api("/stats/counts", withParams(p, ["group_by", "status"])),
      api("/stats/counts", withParams(p, ["group_by", "severity"])),
      api("/stats/counts", withParams(p, ["group_by", "department_id"], ["group_by", "status"])),
      api("/stats/counts", withParams(p, ["group_by", "category"], ["group_by", "subcategory"])),
      api("/stats/timeseries", withParams(p, ["interval", interval])),
      api("/reports.geojson", withParams(p, ["limit", 5000])),
      api("/reports", withParams(p, ["limit", PAGE_SIZE], ["offset", state.offset])),
    ]);
    showError("");
    renderKpis(summary);

    const statusRows = STATUSES.map((s) => ({
      label: humanize(s),
      count: byStatus.find((r) => r.status === s)?.count || 0,
      color: statusColor(s),
    })).filter((r) => r.count);
    renderBars($("#by-status"), statusRows);
    renderBars($("#info-status"), statusRows);

    renderBars($("#by-severity"), SEVERITIES.map((s) => ({
      label: humanize(s),
      count: bySeverity.find((r) => r.severity === s)?.count || 0,
      color: sevColor(s),
    })).filter((r) => r.count));

    renderBars($("#by-department"), sumBy(byDeptStatus, "department_id").map((r) => ({ label: deptLabel(r.key), count: r.count })));
    renderBars($("#info-dept"), sumBy(byDeptStatus, "department_id", (r) => !CLOSED.has(r.status)).map((r) => ({ label: deptLabel(r.key), count: r.count })));

    renderBars($("#by-subcategory"), bySub.sort((a, b) => b.count - a.count).map((r) => ({
      label: r.subcategory === "other" ? `Other (${catLabel(r.category)})` : subLabel(r.subcategory),
      count: r.count,
    })));
    renderTimeseries(series, interval);
    renderMap(geojson, fit);
    renderTable(page);
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
  } catch (err) {
    showError(`Could not load data from ${API}: ${err.message}. Is the PI4C API running?`);
  }
}

// ---- report drawer -------------------------------------------------------------------------

async function openReport(id) {
  let r;
  try {
    r = await api(`/reports/${id}`);
  } catch (err) {
    showError(`Could not load report ${id}: ${err.message}`);
    return;
  }
  state.openReport = r;
  $("#d-title").textContent = r.ref;

  const photos = r.media.filter((m) => m.kind === "image")
    .map((m) => `<a href="${esc(API_ORIGIN + m.url)}" target="_blank" rel="noopener"><img src="${esc(API_ORIGIN + m.url)}" alt="Photo attached to ${esc(r.ref)}"></a>`)
    .join("");
  const mapsUrl = `https://www.google.com/maps?q=${r.latitude},${r.longitude}`;
  const facts = [
    ["Reported", fmtDateTime(r.created_at)],
    ["Last updated", fmtDateTime(r.updated_at)],
    ["Issue", `${subLabel(r.subcategory)} · ${catLabel(r.category)}`],
    ["Department", deptLabel(r.department_id)],
    ["Severity", humanize(r.severity)],
    ["Status", humanize(r.status)],
    ["Affected", humanize(r.affected)],
    ["PwD report", r.pwd_marker ? "Yes" : "No"],
    ["Ward", r.ward || "—"],
    ["Language", r.language === "te" ? "Telugu" : r.language === "en" ? "English" : r.language],
    ["Classified by", r.classifier ? `${r.classifier}${r.confidence != null ? ` (${Math.round(r.confidence * 100)}%)` : ""}` : "—"],
    ["Same problem as", r.cluster_id ? `Cluster #${r.cluster_id}` : "—"],
  ];

  $("#d-body").innerHTML = `
    ${photos ? `<div class="photos">${photos}</div>` : ""}
    ${r.summary_en ? `<h3>Summary</h3><p>${esc(r.summary_en)}</p>` : ""}
    <h3>Citizen's description${r.description_type !== "text" ? ` (${esc(r.description_type)})` : ""}</h3>
    <div class="quote">${esc(r.description_raw || "—")}</div>
    ${r.description_en && r.description_en !== r.description_raw ? `<h3>English translation</h3><div class="quote">${esc(r.description_en)}</div>` : ""}
    <h3>Location</h3>
    <p>${[r.location_name && esc(r.location_name), r.location_address && `<span class="muted">${esc(r.location_address)}</span>`]
      .filter(Boolean).map((line) => `${line}<br>`).join("")}<a href="${mapsUrl}" target="_blank" rel="noopener">${r.latitude.toFixed(5)}, ${r.longitude.toFixed(5)} ↗</a></p>
    <dl class="facts">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    ${r.status_note ? `<h3>Current note</h3><div class="quote">${esc(r.status_note)}</div>` : ""}`;

  const f = $("#d-form").elements;
  f.status.value = r.status;
  f.severity.value = r.severity || "";
  f.department_id.value = r.department_id || "";
  f.status_note.value = r.status_note || "";
  f.needs_review.checked = r.needs_review;
  for (const el of $("#d-form").elements) el.disabled = !state.writeAccess;
  $("#d-readonly").hidden = state.writeAccess;
  $("#d-msg").textContent = "";

  $("#d-log").innerHTML = "";
  if (state.writeAccess) loadLog(r.id);

  $("#drawer").hidden = false;
}

async function loadLog(id) {
  try {
    const log = await api(`/reports/${id}/log`);
    if (!log.length || state.openReport?.id !== id) return;
    $("#d-log").innerHTML = `<h3>Conversation log</h3><ol class="log">${log
      .map((e) => `<li><span class="muted">${esc(fmtDateTime(e.created_at))}</span> ${esc(e.direction)} · ${esc(e.stage)}</li>`)
      .join("")}</ol>`;
  } catch { /* log is optional */ }
}

async function saveReport(event) {
  event.preventDefault();
  const r = state.openReport;
  const f = $("#d-form").elements;
  const changes = {};
  if (f.status.value !== r.status) changes.status = f.status.value;
  if (f.severity.value && f.severity.value !== r.severity) changes.severity = f.severity.value;
  if (f.department_id.value && f.department_id.value !== r.department_id) changes.department_id = f.department_id.value;
  if (f.status_note.value !== (r.status_note || "")) changes.status_note = f.status_note.value;
  if (f.needs_review.checked !== r.needs_review) changes.needs_review = f.needs_review.checked;
  if (!Object.keys(changes).length) {
    $("#d-msg").textContent = "Nothing changed.";
    return;
  }
  $("#d-msg").textContent = "Saving…";
  try {
    await api(`/reports/${r.id}`, null, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
    await openReport(r.id);
    $("#d-msg").textContent = "Saved.";
    refresh();
  } catch (err) {
    $("#d-msg").textContent = err.status === 403 ? "Updating is turned off on the server (WRITE_ACCESS=false)." : `Could not save: ${err.message}`;
  }
}

// ---- views & wiring ------------------------------------------------------------------------

function showView(view) {
  state.view = view;
  for (const tab of document.querySelectorAll(".tabs button")) {
    const active = tab.dataset.view === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const section of document.querySelectorAll("section.view")) section.hidden = section.dataset.view !== view;
  if (view === "map") map.invalidateSize();
}

function selectCategory(category) {
  state.category = category;
  for (const btn of document.querySelectorAll("#indicators button")) btn.classList.toggle("active", btn.dataset.category === category);
  onFiltersChanged();
}

function onFiltersChanged() {
  state.offset = 0;
  refresh({ fit: true });
}

function resetAll() {
  $("#filters").reset();
  for (const select of $("#selects").querySelectorAll("select")) select.value = "";
  $("#area").value = "gvmc";
  selectCategory("");
}

async function main() {
  initMap();
  $("#indicators").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-category]");
    if (btn) selectCategory(btn.dataset.category);
  });
  for (const el of [$("#filters"), $("#selects"), $("#area")]) el.addEventListener("change", onFiltersChanged);
  $("#reset").addEventListener("click", resetAll);
  document.querySelector(".tabs").addEventListener("click", (e) => {
    const tab = e.target.closest("button[data-view]");
    if (tab) showView(tab.dataset.view);
  });
  $("#info-close").addEventListener("click", () => { $("#info-panel").hidden = true; $("#info-open").hidden = false; });
  $("#info-open").addEventListener("click", () => { $("#info-panel").hidden = false; $("#info-open").hidden = true; });
  $("#interval").addEventListener("change", () => refresh());
  $("#refresh").addEventListener("click", () => refresh());
  $("#prev").addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE_SIZE); refresh(); });
  $("#next").addEventListener("click", () => { state.offset += PAGE_SIZE; refresh(); });
  $("#rows").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-id]");
    if (row) openReport(Number(row.dataset.id));
  });
  $("#d-close").addEventListener("click", () => { $("#drawer").hidden = true; state.openReport = null; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#d-close").click(); });
  $("#d-form").addEventListener("submit", saveReport);

  try {
    await Promise.all([loadMeta(), probeWriteAccess()]);
  } catch (err) {
    showError(`Could not reach the PI4C API at ${API}: ${err.message}. Start it with: uv run uvicorn app.main:app --reload`);
    return;
  }
  await refresh({ fit: true });
  setInterval(() => { if (!document.hidden) refresh(); }, AUTO_REFRESH_MS);
}

main();
