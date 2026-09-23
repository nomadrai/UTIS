/**
 * UI controller — sidebar controls, stub.
 *
 * Agreed behavior (2026-09-23, see PLAN.md):
 *   - Layer toggles: LST heatmap / NDVI / NDBI / hotspot markers
 *     (Leaflet layer control wiring lands in task #8).
 *   - Year selector: multi-temporal comparison; switching years swaps the
 *     active composite tile URL (from /api/layers).
 *   - Scenario panel: sliders for hypothetical vegetation/built-up % change
 *     per zone; calls POST /api/scenario and updates BOTH the map layer and
 *     a results panel that explains the estimated impact (coefficients,
 *     r², n — the "why" behind the number).
 *
 * Implementation lands with PLAN.md task #8.
 */

import { postScenario } from "./api.js";

export function initUI() {
  // TODO(task #8): wire sliders + year selector + layer control
  throw new Error("UI wiring lands with PLAN.md task #8");
}
