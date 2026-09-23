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

import { fetchLayers, fetchComparison, fetchWards, fetchHotspots, fetchLandcoverStats, LAYER_SPECS, yearsForLayer } from "./api.js";
import { initUI } from "./ui.js";

const DEFAULT_SEASON = "pre-monsoon";

// Per-layer ramps (tile vis params and choropleth share them per layer).
const RAMPS = {
  lst: ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
  ndvi: ["#d73027", "#fdae61", "#ffffbf", "#a6d96a", "#1a9850"],
  ndbi: ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
};

const state = {
  layer: "lst",
  year: 2024, // re-clamped to the layer's range in initMap
  season: DEFAULT_SEASON,
  showTiles: true,
  showChoropleth: true,
  showHotspots: true,
};

// per-layer year -> Map(joinKey -> {mean, p95, hotspot_pct})
const statsByLayerYear = new Map();

let map = null;
let tileLayer = null;
let wardLayer = null;
let hotspotLayer = null; // L.layerGroup of persistent-hotspot markers
let hotspotsData = null; // FeatureCollection from /api/hotspots
let selectedWard = null; // ward_no clicked in the choropleth (scenario target)
let landcoverStats = null; // {byWard: Map, colors, classes} — categorical layer

function status(message, kind = "info") {
  window.dispatchEvent(new CustomEvent("uhi:status", { detail: { message, kind } }));
}

// ---------------------------------------------------------------------------
// Color + formatting helpers
// ---------------------------------------------------------------------------
const k2c = (k) => (k == null ? null : k - 273.15);
const fmt = (v, d = 1) => (v == null ? "—" : v.toFixed(d));

// ---------------------------------------------------------------------------
// Stats join
// ---------------------------------------------------------------------------
function joinKeyOf(feature) {
  const wn = feature.properties?.ward_no;
  return wn == null ? feature.__joinKey : `w${wn}`; // __joinKey = i-th null feature
}

function statsMapFor(layer, year) {
  return statsByLayerYear.get(`${layer}:${year}`) ?? new Map();
}

async function loadComparison(layer, years) {
  const payload = await fetchComparison(years, layer, state.season);
  for (const [year, bundle] of Object.entries(payload.years)) {
    const m = new Map();
    let nullIdx = 0;
    for (const s of bundle.wards) {
      const key = s.ward_no == null ? `n${nullIdx++}` : `w${s.ward_no}`;
      m.set(key, s);
    }
    statsByLayerYear.set(`${layer}:${year}`, m);
  }
  status(`Loaded ${layer} stats for ${Object.keys(payload.years).length} years`);
}

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------
async function loadTileLayer() {
  const meta = await fetchLayers(state.year, state.layer, state.season);
  if (tileLayer) map.removeLayer(tileLayer);
  tileLayer = L.tileLayer(meta.tile_url, {
    opacity: 0.8,
    maxZoom: 19,
    attribution: `Google Earth Engine — ${meta.source}`,
  });
  if (state.showTiles) tileLayer.addTo(map);
  state.visRange = [meta.vis_params.min, meta.vis_params.max];
  return meta;
}

function wardStyle(feature) {
  const key = joinKeyOf(feature);
  let fillColor = "#888";
  if (state.layer === "landcover") {
    // Categorical: fill = dominant WorldCover class color (no percentiles).
    const wn = feature.properties?.ward_no;
    const row = wn != null ? landcoverStats?.byWard.get(wn) : null;
    if (row?.dominant) fillColor = landcoverStats.colors[String(row.dominant.value)] ?? "#888";
  } else {
    const s = key ? statsMapFor(state.layer, state.year).get(key) : undefined;
    if (s) fillColor = pctColor(s.hotspot_pct);
  }
  return {
    color: "#4a5568",
    weight: 1,
    fillColor,
    fillOpacity: state.showChoropleth ? 0.55 : 0.05,
    opacity: 0.9,
  };
}

function wardTooltip(feature) {
  const key = joinKeyOf(feature);
  const wn = feature.properties?.ward_no;
  const name = wn == null ? "Unnumbered area" : `Ward ${wn}`;

  if (state.layer === "landcover") {
    const row = wn != null ? landcoverStats?.byWard.get(wn) : null;
    if (!row?.dominant) return `${name}<br>no data`;
    const top = Object.entries(row.shares)
      .sort((a, b) => b[1] - a[1]).slice(0, 3)
      .map(([v, p]) => `${landcoverStats.classes[v] ?? v}: ${p}%`).join("<br>");
    return `<b>${name}</b><br>Dominant: ${row.dominant.label} (${row.dominant.pct}%)<br>${top}<br><i>WorldCover 2021</i>`;
  }

  const s = key ? statsMapFor(state.layer, state.year).get(key) : undefined;
  if (!s || s.mean == null) return `${name}<br>no data`;
  const unit = LAYER_SPECS[state.layer]?.units ?? "";
  const meanLine =
    state.layer === "lst"
      ? `LST: ${fmt(s.mean)} K (${fmt(k2c(s.mean))} °C)<br>95th pct: ${fmt(s.p95)} K`
      : `${state.layer.toUpperCase()} mean: ${fmt(s.mean, 3)} ${unit}<br>95th pct: ${fmt(s.p95, 3)}`;
  return (
    `<b>${name}</b><br>` + meanLine +
    `<br>${state.layer.toUpperCase()} percentile: ${s.hotspot_pct == null ? "—" : s.hotspot_pct}`
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
  highlightSelectedWard();
}

function pctColor(pct) {
  if (pct == null) return "#888";
  const ramp = RAMPS[state.layer] ?? RAMPS.lst;
  const i = Math.min(ramp.length - 1, Math.floor((pct / 100) * ramp.length));
  return ramp[i];
}

async function loadWardLayer() {
  const fc = await fetchWards();
  wardLayer = L.geoJSON(fc, {
    style: wardStyle,
    onEachFeature: (f, l) => {
      l.on("mouseover", () => l.setStyle({ weight: 2.5, color: "#1a202c" }));
      l.on("mouseout", () => l.setStyle(wardStyle(f)));
      l.on("click", () => {
        selectedWard = f.properties?.ward_no ?? null;
        window.dispatchEvent(
          new CustomEvent("uhi:ward-selected", {
            detail: { wardNo: selectedWard },
          })
        );
      });
    },
  });
  restyleWards();
  if (state.showChoropleth) wardLayer.addTo(map);
}

function highlightSelectedWard() {
  if (!wardLayer) return;
  wardLayer.eachLayer((l) => {
    const isSel =
      selectedWard != null && l.feature?.properties?.ward_no === selectedWard;
    l.setStyle({
      ...wardStyle(l.feature),
      color: isSel ? "#ff2d00" : "#4a5568",
      weight: isSel ? 3 : 1,
      fillOpacity: isSel ? 0.7 : state.showChoropleth ? 0.55 : 0.05,
    });
  });
}

export function getSelectedWard() {
  return selectedWard;
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------
function updateLegend() {
  if (!map) return;
  const spec = LAYER_SPECS[state.layer] ?? LAYER_SPECS.lst;
  if (legendControl) legendControl.remove();
  const Legend = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create("div", "uhi-legend");
      if (state.layer === "landcover" && landcoverStats) {
        // Categorical legend: one swatch row per WorldCover class.
        div.innerHTML =
          `<b>${spec.label}</b>` +
          Object.entries(landcoverStats.classes)
            .map(([v, label]) =>
              `<div class="uhi-legend-class">` +
              `<span class="uhi-legend-swatch" style="background:${landcoverStats.colors[v]}; flex:0 0 14px; margin-right:6px"></span>${label}</div>`)
            .join("") +
          `<div class="uhi-legend-note">Ward fill = dominant class; hover for class shares</div>`;
      } else {
        const ramp = RAMPS[state.layer] ?? RAMPS.lst;
        div.innerHTML =
          `<b>${spec.label} — ${state.year}</b>` +
          `<div class="uhi-legend-row">` +
          ramp.map((c) => `<span class="uhi-legend-swatch" style="background:${c}"></span>`).join("") +
          `</div>` +
          `<div class="uhi-legend-labels"><span>${spec.legend.low}</span><span>${spec.legend.high}</span></div>` +
          `<div class="uhi-legend-note">Ward color = percentile within ${state.year}; ` +
          `satellite tint = ${state.layer.toUpperCase()} (fixed ${state.visRange?.[0]}–${state.visRange?.[1]} ${spec.units})</div>`;
      }
      return div;
    },
  });
  legendControl = new Legend({ position: "bottomright" }).addTo(map);
}

let legendControl = null;

// ---------------------------------------------------------------------------
// Persistent hotspot overlay (task #5)
// ---------------------------------------------------------------------------
async function loadHotspots() {
  hotspotsData = await fetchHotspots(90, 0.7, state.season);
  renderHotspots();
  const n = hotspotsData.features.length;
  status(`Persistent hotspots: ${n} ward${n === 1 ? "" : "s"} (top-10% in ≥70% of years)`);
}

function renderHotspots() {
  if (hotspotLayer) map.removeLayer(hotspotLayer);
  hotspotLayer = L.layerGroup();
  if (!hotspotsData) return;
  for (const f of hotspotsData.features) {
    const wn = f.properties.ward_no;
    // Join to the ward polygons already on the map; null wards have no
    // labeled polygon to pin — skip them (they stay in the choropleth).
    const target = wardLayer && wn != null
      ? wardLayer.getLayers().find((l) => l.feature?.properties?.ward_no === wn)
      : null;
    const ll = target ? target.getBounds().getCenter() : null;
    if (!ll) continue;
    const p = f.properties;
    hotspotLayer.addLayer(
      L.marker(ll, {
        icon: L.divIcon({
          className: "uhi-hotspot-pin",
          html: `<span>${wn}</span>`,
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        }),
        title: `Ward ${wn} — persistent hotspot`,
      }).bindTooltip(
        `<b>Ward ${wn} — persistent hotspot</b><br>` +
        `Hot (top-10% LST) in ${p.years_hot.length}/${p.n_years} years<br>` +
        `Mean percentile: ${p.mean_percentile}<br>` +
        `Mean LST: ${fmt(p.mean_lst_k)} K (${fmt(k2c(p.mean_lst_k))} °C)`,
        { sticky: true }
      )
    );
  }
  if (state.showHotspots) hotspotLayer.addTo(map);
}

export function setHotspotsVisible(v) {
  state.showHotspots = Boolean(v);
  if (!map) return;
  if (state.showHotspots) hotspotLayer?.addTo(map);
  else if (hotspotLayer) map.removeLayer(hotspotLayer);
}

// ---------------------------------------------------------------------------
// Public API (used by ui.js)
// ---------------------------------------------------------------------------
async function ensureLandcoverStats() {
  if (landcoverStats) return;
  const payload = await fetchLandcoverStats();
  const byWard = new Map();
  for (const row of payload.wards) byWard.set(row.ward_no, row);
  landcoverStats = { byWard, colors: payload.class_colors, classes: payload.classes };
}

export async function setLayer(layer) {
  if (!LAYER_SPECS[layer]) return;
  if (layer === state.layer) return;
  state.layer = layer;
  const years = yearsForLayer(layer);
  if (!years.includes(state.year)) state.year = years[years.length - 1];
  status(`Switching to ${LAYER_SPECS[layer].label}…`);
  // Categorical layers have no /api/comparison — load their stats instead.
  const loads = LAYER_SPECS[layer].categorical
    ? [loadTileLayer(), ensureLandcoverStats()]
    : [loadTileLayer(), loadComparison(layer, years)];
  await Promise.allSettled(loads);
  restyleWards();
  updateLegend();
  status(`${LAYER_SPECS[layer].label}, ${state.year} — updated`);
}

export async function setYear(year) {
  const years = yearsForLayer(state.layer);
  if (!years.includes(Number(year))) return;
  state.year = Number(year);
  status(`Switching to ${state.year}…`);
  if (!statsMapFor(state.layer, state.year).size) {
    await loadComparison(state.layer, years); // first view of this year for this layer
  }
  await loadTileLayer(); // tile URL is year-specific
  restyleWards();
  updateLegend();
  status(`${LAYER_SPECS[state.layer].label}, ${state.year} ${state.season} — updated`);
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
  return { ...state, years: yearsForLayer(state.layer) };
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

  // Tiles + ward geometry + per-ward stats, in parallel; one failure must
  // not kill the others. Hotspots (LST-only methodology) load after wards
  // so pins can join to ward polygons.
  await Promise.allSettled([
    loadTileLayer(),
    loadWardLayer(),
    loadComparison(state.layer, yearsForLayer(state.layer)),
  ]);
  restyleWards();
  updateLegend();
  loadHotspots().catch(() => status("Hotspot overlay unavailable", "error"));

  initUI({
    getState,
    setYear,
    setLayer,
    setTilesVisible,
    setChoroplethVisible,
    setHotspotsVisible,
    getSelectedWard,
  });

  status("Ready");
}

initMap();
