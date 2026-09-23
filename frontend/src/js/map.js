/**
 * Leaflet map — task #8 wiring.
 *
 * Agreed behavior (2026-09-23, see PLAN.md):
 *   - Initial view locked/bounded to the Nagpur polygon extent (maxBounds +
 *     minZoom) — users cannot pan off into irrelevant territory.
 *   - GEE tile overlays (LST for now) come from /api/layers; every tile URL
 *     is already polygon-clipped server-side (AOI policy).
 *   - Ward choropleth from /api/wards joined to /api/comparison per-ward
 *     means; color = within-year hotspot percentile (the project's
 *     methodology — never fixed °C cutoffs).
 *   - Year selector swaps BOTH the tile layer and the choropleth values.
 */

import { fetchLayers, fetchComparison, fetchWards } from "./api.js";
import { initUI } from "./ui.js";

export const STUDY_YEARS = [2020, 2021, 2022, 2023, 2024];
const DEFAULT_SEASON = "pre-monsoon";

// Same palette as the GEE tile vis params — tiles and choropleth read as one layer.
const RAMP = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"];

const state = {
  year: STUDY_YEARS[STUDY_YEARS.length - 1],
  season: DEFAULT_SEASON,
  showTiles: true,
  showChoropleth: true,
};

let map = null;
let tileLayer = null;
let wardLayer = null;

// year -> Map(joinKey -> {mean, p95, hotspot_pct}); joinKey "n0","n1".. for null wards
const statsByYear = new Map();

function status(message, kind = "info") {
  window.dispatchEvent(new CustomEvent("uhi:status", { detail: { message, kind } }));
}

// ---------------------------------------------------------------------------
// Color + formatting helpers
// ---------------------------------------------------------------------------
function pctColor(pct) {
  if (pct == null) return "#888";
  const i = Math.min(RAMP.length - 1, Math.floor((pct / 100) * RAMP.length));
  return RAMP[i];
}

const k2c = (k) => (k == null ? null : k - 273.15);
const fmt = (v, d = 1) => (v == null ? "—" : v.toFixed(d));

// ---------------------------------------------------------------------------
// Stats join
// ---------------------------------------------------------------------------
function joinKeyOf(feature) {
  const wn = feature.properties?.ward_no;
  return wn == null ? feature.__joinKey : `w${wn}`; // __joinKey = i-th null feature
}

function statsMapFor(year) {
  return statsByYear.get(String(year)) ?? new Map();
}

async function loadComparison() {
  const payload = await fetchComparison(STUDY_YEARS, "lst", state.season);
  for (const [year, bundle] of Object.entries(payload.years)) {
    const m = new Map();
    let nullIdx = 0;
    for (const s of bundle.wards) {
      const key = s.ward_no == null ? `n${nullIdx++}` : `w${s.ward_no}`;
      m.set(key, s);
    }
    statsByYear.set(year, m);
  }
  status(`Loaded per-ward stats for ${Object.keys(payload.years).length} years`);
}

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------
async function loadTileLayer() {
  const meta = await fetchLayers(state.year, "lst", state.season);
  if (tileLayer) map.removeLayer(tileLayer);
  tileLayer = L.tileLayer(meta.tile_url, {
    opacity: 0.8,
    maxZoom: 19,
    attribution: "Google Earth Engine — Landsat 8/9 ST_B10",
  });
  if (state.showTiles) tileLayer.addTo(map);
  state.visRange = [meta.vis_params.min, meta.vis_params.max];
  return meta;
}

function wardStyle(feature) {
  const key = joinKeyOf(feature);
  const s = key ? statsMapFor(state.year).get(key) : undefined;
  return {
    color: "#4a5568",
    weight: 1,
    fillColor: s ? pctColor(s.hotspot_pct) : "#888",
    fillOpacity: state.showChoropleth ? 0.55 : 0.05,
    opacity: 0.9,
  };
}

function wardTooltip(feature) {
  const key = joinKeyOf(feature);
  const s = key ? statsMapFor(state.year).get(key) : undefined;
  const wn = feature.properties?.ward_no;
  const name = wn == null ? "Unnumbered area" : `Ward ${wn}`;
  if (!s || s.mean == null) return `${name}<br>no data`;
  return (
    `<b>${name}</b><br>` +
    `LST: ${fmt(s.mean)} K (${fmt(k2c(s.mean))} °C)<br>` +
    `95th pct: ${fmt(s.p95)} K<br>` +
    `Hotspot percentile: ${s.hotspot_pct == null ? "—" : s.hotspot_pct}`
  );
}

function restyleWards() {
  if (!wardLayer) return;
  // Precompute join keys once; counters reset per pass.
  let nullIdx = 0;
  wardLayer.eachLayer((l) => {
    const f = l.feature;
    if (f.properties?.ward_no == null) f.__joinKey = `n${nullIdx++}`;
    else f.__joinKey = `w${f.properties.ward_no}`;
    l.setStyle(wardStyle(f));
    l.bindTooltip(wardTooltip(f), { sticky: true });
  });
}

async function loadWardLayer() {
  const fc = await fetchWards();
  wardLayer = L.geoJSON(fc, {
    style: wardStyle,
    onEachFeature: (f, l) => {
      l.on("mouseover", () => l.setStyle({ weight: 2.5, color: "#1a202c" }));
      l.on("mouseout", () => l.setStyle(wardStyle(f)));
    },
  });
  restyleWards();
  if (state.showChoropleth) wardLayer.addTo(map);
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------
function addLegend() {
  const Legend = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create("div", "uhi-legend");
      div.innerHTML =
        `<div class="uhi-legend-row">` +
        `<span class="uhi-legend-swatch" style="background:${RAMP[0]}"></span>` +
        `<span class="uhi-legend-swatch" style="background:${RAMP[1]}"></span>` +
        `<span class="uhi-legend-swatch" style="background:${RAMP[2]}"></span>` +
        `<span class="uhi-legend-swatch" style="background:${RAMP[3]}"></span>` +
        `<span class="uhi-legend-swatch" style="background:${RAMP[4]}"></span>` +
        `</div>` +
        `<div class="uhi-legend-labels"><span>coolest wards</span><span>hottest wards</span></div>` +
        `<div class="uhi-legend-note">Ward color = hotspot percentile within ${state.year}; ` +
        `satellite tint = LST (fixed ${state.visRange?.[0] ?? 290}–${state.visRange?.[1] ?? 325} K scale)</div>`;
      return div;
    },
  });
  new Legend({ position: "bottomright" }).addTo(map);
}

// ---------------------------------------------------------------------------
// Public API (used by ui.js)
// ---------------------------------------------------------------------------
export async function setYear(year) {
  if (!STUDY_YEARS.includes(Number(year))) return;
  state.year = Number(year);
  status(`Switching to ${state.year}…`);
  await loadTileLayer(); // tile URL is year-specific
  restyleWards();
  status(`${state.year} ${state.season} — ward means + composite updated`);
}

export function setTilesVisible(v) {
  state.showTiles = Boolean(v);
  if (!map) return;
  if (state.showTiles) tileLayer?.addTo(map);
  else if (tileLayer) map.removeLayer(tileLayer);
}

export function setChoroplethVisible(v) {
  state.showChoropleth = Boolean(v);
  if (!map) return;
  if (state.showChoropleth) wardLayer?.addTo(map);
  else if (wardLayer) map.removeLayer(wardLayer);
}

export function getState() {
  return { ...state, years: [...STUDY_YEARS] };
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
export async function initMap() {
  const el = document.getElementById("map");
  status("Contacting backend…");

  let meta;
  try {
    meta = await fetchLayers(state.year, "lst", state.season);
  } catch (err) {
    el.innerHTML =
      `<div class="uhi-error"><h2>Backend unreachable</h2><p>${err.message}</p>` +
      `<p>Start it with:<br><code>.venv/bin/uvicorn backend.app.main:app --reload</code></p></div>`;
    status("Backend unreachable", "error");
    return;
  }

  const [w, s, e, n] = meta.bbox_wsen;
  const bounds = L.latLngBounds([s, w], [n, e]);
  const padded = bounds.pad(0.12);

  map = L.map("map", {
    maxBounds: padded,
    maxBoundsViscosity: 1.0, // hard lock — agreed behavior
    minZoom: 11,
    maxZoom: 19,
  });
  map.fitBounds(padded);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

  state.visRange = [meta.vis_params.min, meta.vis_params.max];

  // Tiles + choropleth load in parallel; one failure should not kill the other.
  await Promise.allSettled([loadTileLayer(), loadWardLayer()]);
  addLegend();

  initUI({
    getState,
    setYear,
    setTilesVisible,
    setChoroplethVisible,
  });

  status("Ready");
}

initMap();
