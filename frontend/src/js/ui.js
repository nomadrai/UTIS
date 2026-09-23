/**
 * UI controller — sidebar controls (task #8).
 *
 * Wires:
 *   - Year selector: swaps the composite tile URL (via /api/layers) AND the
 *     choropleth values (from the /api/comparison cache) together.
 *   - Layer toggles: LST satellite tiles + ward choropleth.
 *   - Status line: async load progress / errors surfaced to the user.
 *
 * Scenario sliders land with PLAN.md tasks #6/#8 (endpoint not live yet).
 */

import { fetchComparison } from "./api.js";

/**
 * @param {object} mapApi { getState, setYear, setTilesVisible, setChoroplethVisible }
 */
export function initUI(mapApi) {
  const { getState, setYear, setTilesVisible, setChoroplethVisible } = mapApi;
  const { years, year: currentYear } = getState();

  // --- status line -----------------------------------------------------------
  const statusEl = document.getElementById("status");
  window.addEventListener("uhi:status", (e) => {
    const { message, kind } = e.detail;
    statusEl.textContent = message;
    statusEl.dataset.kind = kind ?? "info";
  });
  statusEl.textContent = "Starting…";

  // --- year selector -----------------------------------------------------------
  const yearSel = document.getElementById("year-select");
  yearSel.innerHTML = years
    .map((y) => `<option value="${y}" ${y === currentYear ? "selected" : ""}>${y}</option>`)
    .join("");
  yearSel.addEventListener("change", () => setYear(Number(yearSel.value)));

  // --- layer toggles -----------------------------------------------------------
  const tilesChk = document.getElementById("toggle-tiles");
  const choroplethChk = document.getElementById("toggle-choropleth");
  tilesChk.addEventListener("change", () => setTilesVisible(tilesChk.checked));
  choroplethChk.addEventListener("change", () => setChoroplethVisible(choroplethChk.checked));

  // --- city summary for the selected year --------------------------------------
  const summaryEl = document.getElementById("city-summary");
  window.addEventListener("uhi:stats", (e) => {
    const c = e.detail?.city;
    if (!c) return;
    summaryEl.innerHTML =
      `<div>City mean: <b>${(c.mean - 273.15).toFixed(1)} °C</b></div>` +
      `<div>Hottest ward p95: <b>${(c.max - 273.15).toFixed(1)} °C</b></div>` +
      `<div>Wards: ${c.n_wards}</div>`;
  });

  // City summary for the current year (map.js already caches comparison
  // stats; this lightweight re-fetch keeps ui.js self-contained).
  fetchComparison([currentYear])
    .then((payload) => {
      const city = payload.years?.[String(currentYear)]?.city;
      if (city) window.dispatchEvent(new CustomEvent("uhi:stats", { detail: { city } }));
    })
    .catch(() => { /* map.js surfaces comparison errors */ });
}
