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
 * Scenario panel (task #6) + what-if map mode (task #10).
 */

import { fetchComparison, fetchWards, postScenario, postChat, LAYER_SPECS, yearsForLayer } from "./api.js";

/**
 * @param {object} mapApi { getState, setYear, setLayer, setTilesVisible, setChoroplethVisible,
 *   setHotspotsVisible, getSelectedWard, enableWhatIf, setWhatIfDeltas }
 */
export function initUI(mapApi) {
  const { getState, setYear, setLayer, setTilesVisible, setChoroplethVisible, setHotspotsVisible, getSelectedWard, enableWhatIf, setWhatIfDeltas } = mapApi;
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
    if (spec.categorical) {
      // Categorical layers have no comparison stats; show what they are.
      summaryEl.innerHTML =
        `<div><b>${spec.label}</b></div>` +
        `<div class="placeholder">Single-year snapshot — per-ward class shares in tooltips; city summary not applicable.</div>`;
      return;
    }
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

  // --- scenario panel (task #6) -------------------------------------------------
  const zoneSel = document.getElementById("scenario-zone");
  const vegSlider = document.getElementById("scenario-veg");
  const builtSlider = document.getElementById("scenario-built");
  const vegLabel = document.getElementById("scenario-veg-val");
  const builtLabel = document.getElementById("scenario-built-val");
  const resultEl = document.getElementById("scenario-result");
  let estimateTimer = null;

  // Zone options: city-wide + every numbered ward.
  fetchWards()
    .then((fc) => {
      const nums = [...new Set(fc.features.map((f) => f.properties.ward_no).filter((n) => n != null))].sort((a, b) => a - b);
      zoneSel.innerHTML =
        `<option value="city">City-wide (mean of wards)</option>` +
        nums.map((n) => `<option value="${n}">Ward ${n}</option>`).join("");
    })
    .catch(() => { resultEl.textContent = "Ward list unavailable"; });

  // Map click selects the ward (and syncs the dropdown).
  window.addEventListener("uhi:ward-selected", (e) => {
    const wn = e.detail?.wardNo;
    if (wn != null) {
      zoneSel.value = String(wn);
      scheduleEstimate();
    }
  });

  function sliderVals() {
    return {
      veg: Number(vegSlider.value),
      built: Number(builtSlider.value),
    };
  }

  function updateSliderLabels() {
    const { veg, built } = sliderVals();
    vegLabel.textContent = `${veg > 0 ? "+" : ""}${veg}%`;
    builtLabel.textContent = `${built > 0 ? "+" : ""}${built}%`;
  }

  function scheduleEstimate() {
    updateSliderLabels();
    clearTimeout(estimateTimer);
    estimateTimer = setTimeout(runEstimate, 250); // debounce live dragging
  }

  async function runEstimate() {
    const zone = zoneSel.value || "city";
    const { veg, built } = sliderVals();
    resultEl.innerHTML = `<span class="placeholder">Estimating…</span>`;
    try {
      const r = await postScenario(zone, veg, built);
      const ex = r.explanation ?? {};
      // Guard the response shape: a schema drift (field stripped server-side,
      // older backend, proxy mangling) should surface as a message, not a
      // TypeError that blanks the panel.
      const missing = [];
      if (!r.baseline) missing.push("baseline");
      if (!r.deltas) missing.push("deltas");
      if (typeof r.est_lst_change_c !== "number") missing.push("est_lst_change_c");
      if (!ex.equation) missing.push("explanation.equation");
      if (missing.length) {
        resultEl.innerHTML =
          `<div class="uhi-warn">Scenario response is incomplete (missing: ${missing.join(", ")}).` +
          ` Is the backend running the latest code? Restart uvicorn and retry.</div>`;
        return;
      }
      const warn = (ex.warnings || []).map((w) => `<div class="uhi-warn">⚠ ${w}</div>`).join("");
      const pNdvi = ex.p?.ndvi;
      const pNdbi = ex.p?.ndbi;
      resultEl.innerHTML =
        `<div class="uhi-scenario-big">${r.est_lst_change_c > 0 ? "+" : ""}${r.est_lst_change_c.toFixed(2)} °C</div>` +
        `<div class="placeholder">surface temperature, ${r.zone_id}</div>` +
        `<div class="uhi-equation"><code>${ex.equation}</code></div>` +
        `<div class="placeholder">fit: n=${ex.n ?? "—"} ward-year pairs, r²=${typeof ex.r2 === "number" ? ex.r2.toFixed(2) : "—"}` +
        (ex.signs_as_expected ? " — signs as expected (vegetation cools, built-up warms)" : " — ⚠ unexpected signs, interpret with care") +
        `</div>` +
        `<div class="placeholder">term significance: dNDBI p=${pNdbi?.toFixed(3) ?? "—"}, dNDVI p=${pNdvi?.toFixed(3) ?? "—"}` +
        ` (p &lt; 0.05 is conventionally significant)</div>` +
        `<div class="placeholder">baseline: NDVI ${r.baseline.ndvi.toFixed(2)}, NDBI ${r.baseline.ndbi.toFixed(2)} → applied ΔNDVI ${r.deltas.d_ndvi.toFixed(3)}, ΔNDBI ${r.deltas.d_ndbi.toFixed(3)}</div>` +
        warn;
    } catch (err) {
      resultEl.innerHTML = `<div class="uhi-warn">${err.message}</div>`;
    }
  }

  zoneSel.addEventListener("change", runEstimate);
  vegSlider.addEventListener("input", () => {
    scheduleEstimate();
    if (typeof setWhatIfDeltas === "function") setWhatIfDeltas(Number(vegSlider.value), Number(builtSlider.value));
  });
  builtSlider.addEventListener("input", () => {
    scheduleEstimate();
    if (typeof setWhatIfDeltas === "function") setWhatIfDeltas(Number(vegSlider.value), Number(builtSlider.value));
  });
  updateSliderLabels();
  // First estimate once the ward list lands (zone defaults to city-wide).
  fetchWards().then(runEstimate).catch(() => {});

  // --- what-if map mode (task #10) ----------------------------------------------
  // The SAME sliders drive both the panel estimate and the map recolor: one
  // source of truth for the scenario, two synchronized views of it.
  const whatIfChk = document.getElementById("toggle-whatif");
  if (whatIfChk) {
    whatIfChk.addEventListener("change", () => {
      if (typeof enableWhatIf === "function") {
        enableWhatIf(whatIfChk.checked).catch((err) => {
          statusEl.textContent = `What-if unavailable: ${err.message}`;
          statusEl.dataset.kind = "error";
          whatIfChk.checked = false;
        });
      }
    });
  }

  initChat();

  // --- AI chat drawer (task #11) ----------------------------------------------
  // The bot is grounded server-side (system prompt = methodology digest;
  // tools = this app's own analysis functions). Here we only render turns,
  // keep the visible history, and surface errors as chat bubbles.
  function initChat() {
    const drawer = document.getElementById("chat-drawer");
    const fab = document.getElementById("chat-fab");
    const closeBtn = document.getElementById("chat-close");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const msgs = document.getElementById("chat-messages");
    const sendBtn = form?.querySelector("button[type=submit]");
    if (!drawer || !fab || !form || !input || !msgs) return;

    const history = []; // {role, content} — assistant-visible text only

    const open = () => drawer.classList.add("open");
    const close = () => drawer.classList.remove("open");
    fab.addEventListener("click", () => {
      drawer.classList.toggle("open");
      if (drawer.classList.contains("open")) input.focus();
    });
    closeBtn?.addEventListener("click", close);

    function addBubble(role, text, sources) {
      const div = document.createElement("div");
      div.className = `chat-msg ${role}`;
      div.textContent = text;
      if (sources?.length) {
        const src = document.createElement("div");
        src.className = "chat-src";
        src.textContent = `via ${[...new Set(sources)].join(", ")}`;
        div.appendChild(src);
      }
      msgs.appendChild(div);
      msgs.scrollTop = msgs.scrollHeight;
      return div;
    }

    let busy = false;
    async function send(text) {
      const q = (text ?? input.value).trim();
      if (!q || busy) return;
      busy = true;
      if (sendBtn) sendBtn.disabled = true;
      input.value = "";
      addBubble("user", q);
      const thinking = addBubble("assistant", "Thinking… (calling the analysis tools)");
      try {
        const r = await postChat(q, history);
        thinking.querySelector(".chat-src")?.remove();
        thinking.textContent = r.reply || "(empty reply)";
        if (r.sources?.length) {
          const src = document.createElement("div");
          src.className = "chat-src";
          src.textContent = `via ${[...new Set(r.sources)].join(", ")}${r.provider ? ` · ${r.provider}` : ""}`;
          thinking.appendChild(src);
        }
        history.push({ role: "user", content: q });
        history.push({ role: "assistant", content: r.reply || "" });
        // Cap client history (server re-caps too; this keeps the drawer light).
        while (history.length > 12) history.splice(0, 2);
      } catch (err) {
        thinking.className = "chat-msg error";
        thinking.textContent = String(err.message || err);
      } finally {
        busy = false;
        if (sendBtn) sendBtn.disabled = false;
        msgs.scrollTop = msgs.scrollHeight;
      }
    }

    form.addEventListener("submit", (e) => { e.preventDefault(); send(); });
    document.querySelectorAll("#chat-suggestions button").forEach((b) => {
      b.addEventListener("click", () => send(b.dataset.q));
    });
  }
}
