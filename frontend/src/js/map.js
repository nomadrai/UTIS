/**
 * Leaflet map setup — stub.
 *
 * Agreed behavior (2026-09-23, see PLAN.md):
 *   - Initial view locked/bounded to the Nagpur polygon extent (from
 *     /api or the AOI file's bbox — set via initMap options); users cannot
 *     pan off into irrelevant territory (maxBounds + minZoom).
 *   - GEE tile overlays: LST heatmap, NDVI, NDBI, hotspot markers —
 *     toggled via a layer control; every tile URL returned by the backend
 *     is already polygon-clipped server-side.
 *   - Year selector drives which composite tile URL is loaded.
 *
 * Implementation lands with PLAN.md task #8.
 */

import { fetchLayers, fetchHotspots } from "./api.js";

export function initMap() {
  // TODO(task #8): L.map("map", { maxBounds: nagpurBounds, ... })
  throw new Error("Map init lands with PLAN.md task #8");
}
