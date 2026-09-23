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
