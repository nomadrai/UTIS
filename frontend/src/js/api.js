/**
 * API client — the ONLY module that talks to the backend.
 *
 * Endpoints (see backend/app/api/): layers, comparison, wards, hotspots,
 * scenario, gee-status. hotspots/scenario land with PLAN.md tasks #5–#6.
 */

// Same-origin when the API serves this frontend (mounted in main.py) — the
// normal case. If index.html is opened via file:// (origin "null"), fall
// back to the dev API origin; CORS is configured to allow it.
const API_BASE =
  window.location.protocol === "file:" ? "http://localhost:8000" : "";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* keep statusText */ }
    throw new Error(`${path} → ${res.status}: ${detail}`);
  }
  return res.json();
}

/**
 * GET /api/layers?year=..&layer=lst&season=..
 * -> { tile_url, vis_params, bbox_wsen, units, ... }
 */
export async function fetchLayers(year, layer = "lst", season = "pre-monsoon") {
  return getJSON(
    `/api/layers?year=${encodeURIComponent(year)}&layer=${encodeURIComponent(layer)}&season=${encodeURIComponent(season)}`
  );
}

/**
 * GET /api/comparison?years=2020,2022,2024&layer=lst
 * -> { layer, season, units, years: { "<year>": { wards: [...], city: {...} } } }
 */
export async function fetchComparison(years, layer = "lst", season = "pre-monsoon") {
  const y = Array.isArray(years) ? years.join(",") : years;
  return getJSON(
    `/api/comparison?years=${encodeURIComponent(y)}&layer=${encodeURIComponent(layer)}&season=${encodeURIComponent(season)}`
  );
}

/**
 * GET /api/wards
 * -> FeatureCollection of the 114 georeferenced wards (ward_no may be null)
 */
export async function fetchWards() {
  return getJSON("/api/wards");
}

/**
 * GET /api/landcover-stats
 * -> { year, classes: {value: label}, class_colors: {value: hex},
 *      wards: [{ward_no, shares, dominant}] } — categorical layer stats.
 */
export async function fetchLandcoverStats() {
  return getJSON("/api/landcover-stats");
}

/**
 * GET /api/scenario-model
 * -> { coef, effect_semantics, thresholds, ward_baselines: {ndvi, ndbi},
 *      equation, r2, n, ... } — inputs for the what-if map (task #10).
 *      The client computes per-ward effect = b_ndvi*dNDVI + b_ndbi*dNDBI
 *      (intercept excluded — semantics published by the backend).
 */
export async function fetchScenarioModel() {
  return getJSON("/api/scenario-model");
}

/**
 * GET /api/hotspots?pct=..&min_year_frac=..
 * -> FeatureCollection of persistent hotspot wards (LST), geometry null —
 *    joined client-side to the already-loaded ward polygons by ward_no.
 */
export async function fetchHotspots(pct = 90, minYearFrac = 0.7, season = "pre-monsoon") {
  return getJSON(
    `/api/hotspots?pct=${pct}&min_year_frac=${minYearFrac}&season=${encodeURIComponent(season)}`
  );
}

/**
 * POST /api/scenario { zone_id, veg_delta, builtup_delta }
 * -> { zone_id, est_lst_change_c, explanation: { equation, coef, se, t, p,
 *      r2, n, signs_as_expected, warnings } }
 */
export async function postScenario(zoneId, vegDelta, builtupDelta) {
  const res = await fetch(`${API_BASE}/api/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      zone_id: String(zoneId),
      veg_delta: vegDelta,
      builtup_delta: builtupDelta,
    }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* keep */ }
    throw new Error(`scenario → ${res.status}: ${detail}`);
  }
  return res.json();
}

/**
 * POST /api/chat { message, history }
 * -> { reply, sources: [tool names], provider } — the AI assistant
 *    (task #11). 503 when no provider key is configured or all fail.
 */
export async function postChat(message, history = []) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* keep */ }
    throw new Error(`chat → ${res.status}: ${detail}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Layer registry (client mirror of backend/app/api/layers.py LAYERS — the
// backend remains authoritative; this drives UI labels + year ranges).
// ---------------------------------------------------------------------------
export const LAYER_SPECS = {
  lst: {
    label: "Land surface temperature",
    min_year: 2013,
    max_year: 2026,
    units: "Kelvin",
    legend: { low: "coolest wards", high: "hottest wards" },
  },
  ndvi: {
    label: "Vegetation (NDVI)",
    min_year: 2017, // Sentinel-2 SR coverage starts 2017-03-28
    max_year: 2026,
    units: "index (-1..1)",
    legend: { low: "least vegetation", high: "most vegetation" },
  },
  ndbi: {
    label: "Built-up (NDBI)",
    min_year: 2017,
    max_year: 2026,
    units: "index (-1..1)",
    legend: { low: "least built-up", high: "most built-up" },
  },
  landcover: {
    label: "Land cover (WorldCover 2021)",
    min_year: 2021, // single-year snapshot — year selector will pin to 2021
    max_year: 2021,
    units: "class",
    categorical: true, // ward fill = dominant class, not percentile
    legend: { low: "less of class", high: "more of class" }, // unused when categorical
  },
};

export const LANDCOVER_COLORS = null; // filled at runtime from /api/landcover-stats class_colors

/** Valid study years for a layer: last N full years with sensor coverage. */
export function yearsForLayer(layer) {
  const spec = LAYER_SPECS[layer] ?? LAYER_SPECS.lst;
  const last = Math.min(spec.max_year, 2025); // 2026 not complete yet
  const first = Math.max(spec.min_year, last - 6); // keep the selector sane
  const years = [];
  for (let y = first; y <= last; y++) years.push(y);
  return years;
}
