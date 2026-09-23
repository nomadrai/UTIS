/**
 * UI controller — sidebar controls (task #8/#4).
 *
 * Wires:
 *   - Layer selector: LST / NDVI / NDBI (registry-driven, api.js LAYER_SPECS).
 *   - Year selector: swaps the composite tile URL (via /api/layers) AND the
 *     choropleth values (from /api/comparison) together; repopulated per
 *     layer (S2 layers start at 2017).
 *   - Layer toggles: satellite tiles + ward choropleth.
 *   - Status line: async load progress / errors surfaced to the user.
 *
 * Scenario panel lands with PLAN.md tasks #6/#8 (endpoint not live yet).
 */

import { fetchComparison, LAYER_SPECS, yearsForLayer } from "./api.js";

/**
 * @param {object} mapApi { getState, setYear, setLayer, setTilesVisible, setChoroplethVisible, setHotspotsVisible }
 */
export function initUI(mapApi) {
  const { getState, setYear, setLayer, setTilesVisible, setChoroplethVisible, setHotspotsVisible } = mapApi;
  const { layer, years, year: currentYear } = getState();

  // --- status line -----------------------------------------------------------
  const statusEl = document.getElementById("status");
  window.addEventListener("uhi:status", (e) => {
    const { message, kind } = e.detail;
    statusEl.textContent = message;
    statusEl.dataset.kind = kind ?? "info";
  });
  statusEl.textContent = "Starting…";

  // --- layer selector ----------------------------------------------------------
  const layerSel = document.getElementById("layer-select");
  layerSel.innerHTML = Object.entries(LAYER_SPECS)
    .map(([key, spec]) => `<option value="${key}" ${key === layer ? "selected" : ""}>${spec.label}</option>`)
    .join("");
  layerSel.addEventListener("change", () => {
    setLayer(layerSel.value);
    repopulateYears();
  });

  // --- year selector (per-layer year range) -------------------------------------
  const yearSel = document.getElementById("year-select");
  function repopulateYears() {
    const { years: ys, year: cy } = getState();
    yearSel.innerHTML = ys
      .map((y) => `<option value="${y}" ${y === cy ? "selected" : ""}>${y}</option>`)
      .join("");
  }
  repopulateYears();
  yearSel.addEventListener("change", () => setYear(Number(yearSel.value)));

  // --- layer toggles -----------------------------------------------------------
  const tilesChk = document.getElementById("toggle-tiles");
  const choroplethChk = document.getElementById("toggle-choropleth");
  const hotspotsChk = document.getElementById("toggle-hotspots");
  tilesChk.addEventListener("change", () => setTilesVisible(tilesChk.checked));
  choroplethChk.addEventListener("change", () => setChoroplethVisible(choroplethChk.checked));
  hotspotsChk.addEventListener("change", () => setHotspotsVisible(hotspotsChk.checked));

  // --- city summary for the selected layer+year ----------------------------------
  const summaryEl = document.getElementById("city-summary");
  function refreshSummary() {
    const { layer: ly, year: cy2 } = getState();
    const spec = LAYER_SPECS[ly];
    summaryEl.classList.remove("placeholder");
    fetchComparison([cy2], ly)
      .then((payload) => {
        const city = payload.years?.[String(cy2)]?.city;
        if (!city) return;
        const mean = ly === "lst" ? `${(city.mean - 273.15).toFixed(1)} °C` : city.mean.toFixed(3);
        const max = ly === "lst" ? `${(city.max - 273.15).toFixed(1)} °C` : city.max.toFixed(3);
        summaryEl.innerHTML =
          `<div>City mean ${spec.label.toLowerCase()}: <b>${mean}</b></div>` +
          `<div>Hottest ward (${spec.legend.high}): <b>${max}</b></div>` +
          `<div>Wards: ${city.n_wards}</div>`;
      })
      .catch(() => { /* map.js surfaces comparison errors */ });
  }
  refreshSummary();
  // Re-run when the user changes layer/year (setLayer/setYear update state first).
  layerSel.addEventListener("change", refreshSummary);
  yearSel.addEventListener("change", refreshSummary);
}
