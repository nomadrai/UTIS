/**
 * API client — the ONLY module that talks to the backend.
 *
 * Endpoints (see backend/app/api/): layers, comparison, hotspots, scenario,
 * gee-status. Fetch wrappers land with PLAN.md task #8; stubs now.
 */

const API_BASE = "http://localhost:8000";

export async function fetchLayers(year, layer) {
  // GET /api/layers?year=..&layer=lst|ndvi|ndbi|landcover
  // -> { tile_url, vis_params, valid_min, valid_max }
  throw new Error("Wired in PLAN.md task #8");
}

export async function fetchComparison(years, layer = "lst") {
  // GET /api/comparison?years=2020,2022,2024&layer=lst
  // -> { layer: { year: stats } }
  throw new Error("Wired in PLAN.md task #8");
}

export async function fetchHotspots(pct = 90, minYearFrac = 0.7) {
  // GET /api/hotspots?pct=..&min_year_frac=..
  // -> GeoJSON of persistent hotspot zones (Nagpur polygon only)
  throw new Error("Wired in PLAN.md task #8");
}

export async function postScenario(zoneId, vegDelta, builtupDelta) {
  // POST /api/scenario { zone_id, veg_delta, builtup_delta }
  // -> { est_lst_change_c, explanation: { coefficients, r2, n } }
  throw new Error("Wired in PLAN.md task #8");
}
