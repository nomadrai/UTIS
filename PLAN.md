# PLAN.md — Living Session Log

> **How to use this file:** every work session appends a new dated entry **at the
> top** of the log (below this header, above older entries). Use the template.
> The task board at the bottom is a rough sequence, not a rigid plan — reorder
> freely as reality dictates.

**Entry template (copy for each session):**

```markdown
## YYYY-MM-DD — <short title>

### Done
- ...

### Key decisions & why
- ...

### Working / Broken
- ✅ Working: ...
- ❌ Broken / blocked: ...

### Next steps (for next session)
- [ ] ...
```

---

## 2026-09-24 (session 12) — BUGFIX: scenario panel "cannot read 'ndvi'" (response_model filtering + stale-server trap)

### Done
- User hit `Cannot read properties of undefined (reading 'ndvi')` in the
  scenario panel. Root cause was TWO stacked issues:
  1. **FastAPI response_model filtering**: ScenarioResponse declared only
     zone_id/est_lst_change_c/explanation, so `baseline` and `deltas` were
     silently STRIPPED from HTTP responses — direct-call tests saw them
     (no filtering) and the smoke test only asserted surviving fields.
     Fixed: baseline/deltas declared on the model; smoke test gained a
     response-shape check so any future field drift fails loudly.
  2. **Stale-server trap**: the user's browser AND the first re-run of the
     smoke test were talking to a uvicorn from an earlier session still
     holding port 8000 (pid 241687) — the fixed code was never served.
     Killed it; smoke test now binds an EPHEMERAL port (_free_port()) so
     a stale listener can never silently serve old code again. During
     editing, `explanation` was briefly lost from the response model —
     caught by the new explanation-complete check, restored.
- UI hardened: runEstimate validates the response shape and renders a
  clear "incomplete response — restart the backend" message instead of a
  TypeError blanking the panel.
- Full suite: 35 checks ALL PASSED (shape check included).

### Key decisions & why
- **Ephemeral-port smoke test** is the systemic lesson: hardcoded ports
  turn "stale process" into "tests silently pass against old code" —
  the worst failure mode. Same class of bug bit twice today (ss + bind
  error in session 7's stale server; invisible pass-through here).
- The UI now distrusts its own API responses (shape guard) — schema drift
  should surface as a readable message at the point of use.

### Next steps (for next session)
- [ ] User: restart uvicorn to serve the fixed code (kill any old process).
- [ ] Commit everything (scenario fix included).

## 2026-09-24 (session 11) — Task #9: methodology write-up (docs/METHODOLOGY.md) — BOARD 9/9

### Done
- `docs/METHODOLOGY.md` (new, ~10 sections): study design (AOI rule,
  season rule, server-side policy), ward-zone provenance incl. the PDF
  mirror incident as documented history, LST compositing + QA_PIXEL
  masking, S2 SCL masking + index-before-median rule, WorldCover
  snapshot/class-share rationale, zonal stats + within-year percentile
  methodology, persistent-hotspot rule with current results, the scenario
  fit with the actual fitted equation + honest p-values, consolidated
  caveats (8 numbered), and reproducibility commands for every published
  number.
- README: methodology link, `docs/` in the structure tree, run
  instructions corrected to reality (server serves the frontend;
  127.0.0.1-not-localhost note; cache-pull commands; smoke test).
- PROJECT.md: stale "no logic implemented yet" status line replaced with
  the MVP-complete status + methodology link.

### Key decisions & why
- **One methodology file, code-linked, caveat-forward**: the audience is
  a future maintainer (or reviewer) asking "can I trust this number?" —
  every section ends in the caveat that applies, and §9 consolidates
  them; reproducibility commands live in one place.
- **The mirror incident stays in the docs**: it is the strongest argument
  for the QA-overlay step in the reproducibility list.

### Working / Broken
- ✅ Working: docs complete and cross-linked; app + 34-check suite green.
- ❌ Broken / blocked: nothing.

### Next steps (for next session)
- [ ] Commit everything (scenario + WorldCover + docs are uncommitted).
- [ ] Optional: gee-status polish; zone-name extraction from the prabhag
      panel; additional seasons cached; offline unit tests for
      fit/detection/join logic.

## 2026-09-24 (session 10) — WorldCover landcover layer (task #4 completion) — BOARD FULLY DONE

### Done
- `backend/etl/gee_pulls/pull_worldcover.py` (new): ESA WorldCover v200 —
  a SINGLE-YEAR (2021) 10 m categorical snapshot, deliberately outside the
  year-selector model. Full 10-class table with legend colors; tile vis
  params; sanity check (AOI top classes: Built-up 57.7%, Grassland 16.2%,
  Tree 13.7%, Cropland 9.2%, Water 1.5% — plausible for Nagpur); per-ward
  CLASS-SHARE stats via pixelArea-weighted grouped reduceRegions (a mean
  of class codes is meaningless — shares are the right categorical
  summary); cached to data/processed/worldcover_ward_stats.json.
- Registry: "landcover" entry with min_year=max_year=2021 + `categorical:
  true` flag; max_year filled for all layers so validation uses one code
  path; layer-agnostic coverage error message. /api/comparison now
  explicitly rejects categorical layers (400).
- `GET /api/landcover-stats` (new): cached per-ward shares + dominant
  class + class colors; 404 until the CLI has been run.
- Frontend: landcover layer in the selector — ward fill = DOMINANT class
  color (not percentile), class-share tooltips (top-3), categorical legend
  (one swatch per class), year selector pins to 2021, city summary
  replaced by an explanatory note for the snapshot layer.
- Central wards 54–90% Built-up (ward 4 is 90% built) — consistent with
  the persistent-hotspot picture.
- Smoke suite extended to 34 checks (tile, year-pin guard, comparison
  block, stats payload, 4 layer options in headless DOM) → ALL PASSED.

### Key decisions & why
- **Categorical ≠ continuous**: WorldCover gets a different stats endpoint
  and a different choropleth semantic (dominant class, not percentile) —
  forcing it through /api/comparison would have produced nonsense means.
- **Year pinned to 2021**: the snapshot is what it is; the UI disables
  year choice rather than silently compositing wrong years.

### Working / Broken
- ✅ Working: FOUR layers (lst/ndvi/ndbi/landcover), all endpoints, 34-check
  smoke suite green. Task board: every row done.
- ❌ Broken / blocked: nothing.

### Next steps (for next session)
- [ ] Commit the scenario + landcover work (last uncommitted changes).
- [ ] Optional: README quickstart; gee-status polish; zone-name extraction
      from the prabhag panel; more seasons cached.

## 2026-09-24 (session 9) — Task #6: scenario fit dLST ~ dNDVI + dNDBI + /api/scenario + sliders — TASK BOARD COMPLETE

### Done
- `backend/etl/analysis/scenario.py` (new): ward×year delta panel from the
  three per-layer caches (456 ward-year pairs for pre-monsoon 2019–2025),
  plain OLS dLST ~ 1 + dNDVI + dNDBI with classical se/t/p, r², residual
  std, memoized per season. Prediction: slider %s applied to the zone's
  baseline mean NDVI/NDBI → plugged into the fitted equation; estimates
  beyond ±5 °C or far outside the observed dLST range carry explicit
  extrapolation warnings.
- **The fitted model**: dLST = −0.49 − 1.19·dNDVI + 110.5·dNDBI (K),
  n=456, r²=0.31. Signs physically correct (vegetation cools, built-up
  warms); dNDBI highly significant (p<0.0001), dNDVI not (p=0.90 —
  year-to-year NDVI deltas are small/noisy; surfaced honestly in the UI,
  not hidden).
- `POST /api/scenario` (stub replaced): pydantic bounds ±100%, zone_id =
  ward number or "city" (mean-of-ward-baselines fallback); 400 unknown
  zone, 404 missing caches, 503 un-fittable panel. Sample: ward 15
  −20% vegetation → −0.43 °C; +10% built-up → +0.80 °C.
- Frontend: scenario zone dropdown (city + 107 numbered wards, synced
  two-way with map clicks — choropleth wards now select + highlight red),
  vegetation/built-up sliders (−50..+50%), live debounced estimates, and
  the explanation panel: big ±°C number, the fitted equation, n/r²/sign
  note, per-term p-values, applied deltas, warnings.
- `scripts/smoke_api.py` extended to 29 checks (scenario estimate,
  explanation completeness, city fallback, unknown-ward 400, bounds 422,
  physical signs, panel renders in headless Chrome) → ALL PASSED.

### Key decisions & why
- **Explainable OLS only** (locked design): the UI prints the actual
  fitted equation + diagnostics; no ML. The scenario number is only ever
  as good as the panel — warnings flag extrapolation instead of
  pretending precision.
- **Deltas applied to baseline indices**: % vegetation maps through the
  ward's own NDVI baseline (ΔNDVI = pct/100 · NDVI_base) so the same
  slider means different things in green vs concrete wards.
- **Map-click ↔ dropdown sync**: selecting a ward is one gesture; the
  scenario panel follows the map.

### Working / Broken
- ✅ Working: FULL pipeline — 3 satellite layers, ward choropleth,
  persistent hotspots, scenario what-ifs; all endpoints live; 29-check
  smoke suite green.
- ❌ Broken / blocked: nothing blocking. Optional leftovers: WorldCover
  landcover layer, gee-status gee_authenticated polish, zone metadata
  (10-zone rollup).

### Next steps (for next session)
- [ ] Optional: WorldCover landcover layer in the LAYERS registry.
- [ ] Optional: zone-level (10-zone) rollup alongside wards.
- [ ] Consider: commit the whole MVP; write a short demo script/README
      section for first-run.

## 2026-09-24 (session 8) — Task #5: persistent hotspot detection + /api/hotspots

### Done
- `backend/etl/analysis/hotspots.py` (new): persistence rule — a ward is a
  hotspot if its within-year LST percentile rank is ≥ pct (default 90) in
  ≥ min_year_frac (default 0.7) of study years with data. Reads ONLY the
  cached per-year ward summaries (no GEE calls); stable null-ward join
  (i-th null ward ↔ i-th null stat, both ordered lists).
- `/api/hotspots` implemented (was stubbed): pct 50..99 + min_year_frac
  (0,1] validation (400s), 404 when the season's cache is missing,
  GeoJSON FeatureCollection with per-ward stats (years_hot, persistence,
  mean_percentile, mean_lst_k, yearly detail); `with_geometry=true`
  embeds ward polygons for standalone use, default geometry=null (client
  joins ward_no to /api/wards).
- Frontend: hotspot toggle + red numbered pins at persistent-ward
  centroids (joined client-side to ward polygons), tooltips with
  persistence detail, status-line summary; fetchHotspots in api.js.
- Detection results (pre-monsoon, pct=90/frac=0.7): **7 persistent
  hotspot wards** — ward 15 top-1% hottest in ALL 7 years (320.7 K mean),
  then 30, 14, 31, 17, 6, 13. Sensitivity sweep monotonic: 16 hotspots
  at pct=80 → 0 at pct=99/frac=0.99. Cache now holds 7 years (2019–2025;
  2019+2025 were computed on-demand by earlier frontend fetches) — more
  years, stronger persistence signal.
- `scripts/smoke_api.py` extended: detection meta, presence, ranking,
  param guard, with_geometry, hotspot pins in the headless DOM →
  ALL 22 CHECKS PASSED (status check fixed to accept the terminal
  hotspot-summary line, which now fires after "Ready").

### Key decisions & why
- **Ward-level persistence, not pixel-level**: zones are the project's
  analysis unit (and what the UI shows); pixel blobs would need a second
  polygonization layer. The ward rule is fully explainable ("top-10% in ≥4
  of 7 years") and reuses existing caches — zero GEE cost.
- **LST-only methodology** (SUPPORTED_LAYERS = ("lst",)): the contract
  defines hotspots via temperature percentile; an NDVI/NDBI analogue
  would be a different product (can be added later if wanted).
- **Client-side pin join**: /api/hotspots stays tiny (no geometry by
  default); the map already owns ward geometry.

### Working / Broken
- ✅ Working: persistent hotspot overlay end-to-end; all three satellite
  layers; 22-check smoke suite green.
- ❌ Broken / blocked: /api/scenario still stubbed (task #6 — the last
  unimplemented endpoint besides gee-status cosmetics).

### Next steps (for next session)
- [ ] Task #6: scenario fit dLST ~ dNDVI + dNDBI (explainable OLS per
      ward-deltas across years) → /api/scenario + frontend sliders +
      explanation panel (coefficients, r², n).
- [ ] Optional: gee-status endpoint polish (fill gee_authenticated).

## 2026-09-24 (session 7) — Task #4: Sentinel-2 NDVI/NDBI composites + multi-layer app

### Done
- `backend/etl/gee_pulls/pull_s2_indices.py` (new): S2_SR_HARMONIZED,
  SCL masking (classes 3/8/9/10/11), per-scene reflectance scaling +
  normalizedDifference indices (NDVI (B8-B4)/(B8+B4), NDBI (B11-B8)/
  (B11+B8)) BEFORE median compositing (index median, not band median),
  fixed vis params, sanity check, CLI (--sanity-check/--zonal-stats/
  --refresh). Sanity vs live GEE: 55 S2 scenes pre-monsoon 2024;
  city means NDVI 0.27 / NDBI 0.05 — plausible for dry-season Nagpur.
- `gee_common.season_dates()` shared helper: single source of season
  windows for both pulls (winter wrap handled once).
- `lst_stats.py` generalized to layers: per-layer cache files
  (`lst_ward_stats_{layer}_{season}.json`), injectable composite builder,
  per-layer units/source metadata; LST cache migrated to new name.
- `/api/layers` + `/api/comparison` refactored to a LAYERS registry
  (composite/vis/min_year/source per layer); S2 layers reject pre-2017
  (no coverage); landcover explicitly not available yet.
- Per-ward NDVI/NDBI stats cached for 2020–2024 (10 layer-years).
- Frontend: layer selector (LST/NDVI/NDBI) from a client LAYER_SPECS
  mirror, per-layer year repopulation (S2 starts 2017), per-layer ramps +
  legend labels, layer-aware tooltips + city summary, `setLayer` API;
  stats cached per layer:year client-side so revisits are instant.
- `scripts/smoke_api.py` (new): single-process smoke test — boots uvicorn
  in a thread (sandbox reaps shell background jobs), checks all endpoints
  + one real tile per layer (ranged GET; GEE tiles reject HEAD) + year
  guards + headless-Chrome DOM (status Ready, 117 ward paths, GEE tile
  requests, 0 JS errors). ALL 16 CHECKS PASSED.

### Key decisions & why
- **SCL over QA60** for S2 cloud masking: QA60 is known-unreliable on SR
  imagery; SCL classes are explicit and bidirectional masking is simple.
- **Index-then-median** (not band-median-then-index): medians of ratios
  behave correctly across heterogeneous scenes.
- **LAYERS registry** (backend) + **LAYER_SPECS mirror** (frontend): one
  place each to add a layer; year limits/units/legends stay in sync.
- **Ranged GET for tile checks**: GEE tile endpoint 404s on HEAD; a
  1 KB ranged GET proves a tile serves without downloading it all.

### Working / Broken
- ✅ Working: three live layers (tiles + ward choropleth + year selector);
  per-layer zonal caches; smoke test green.
- ❌ Broken / blocked: /api/hotspots + /api/scenario still stubbed
  (tasks #5–#6); landcover layer not implemented.

### Next steps (for next session)
- [ ] Task #5: persistent hotspots (top-percentile across most years) →
      /api/hotspots.
- [ ] Task #6: scenario fit dLST ~ dNDVI + dNDBI → /api/scenario + sliders.
- [ ] Optional: WorldCover landcover layer for the LAYERS registry.

## 2026-09-24 (session 6) — BUGFIX: ward layer was N-S mirrored (root cause found + fixed)

### Done
- User reported ward choropleth vs LST tiles vertically mirrored. Full
  diagnosis per user checklist: same CRS (both EPSG:4326, no reprojection
  needed); no local raster affine to be wrong (tiles are GEE XYZ, north-up);
  GeoJSON lon/lat order correct; extraction code faithful (linework matches
  the PDF's own raster rendering 99.2% as-is, 7.4% flipped); page.rotation=0.
- **Root cause: the source PDF's map content is vertically mirrored** —
  the 2005 authoring wrote the map block with an inverted y-axis (zone
  labels: Laxmi Nagar/N at panel bottom, Aasi Nagar/S at top, E-W correct
  → vertical mirror, not rotation). Proved numerically: det=−1 fit of the
  outline to the AOI scores IoU 0.927 at 0° vs 0.847 for the best det=+1
  rotation fit. The session-4 "2005 boundary drift" explanation for the
  1.2 km RMS was WRONG — it was the mirror.
- Fix at the root, per user directive: `_to_map_space()` in
  wards_from_pdf.py mirrors segments AND label anchors at ingest (frame
  midline), keeping label→face assignment consistent. No downstream flip.
- Re-extracted: rot 10.5°→**0.5°**, IoU 0.723→**0.957**, RMS 1122 m→
  **166 m**, wards outside AOI 16.4%→**2.2%**. 114 wards, 107 numbered
  (labels+geometry flipped together, 1:1 preserved), 13 null.
- Zonal stats recomputed for 2020–2024 (--refresh): city means ~unchanged
  (mirror-invariant), per-ward values/hotspot ranks moved to true locations.
- New QA tool `backend/etl/analysis/ward_lst_overlay.py` (`python -m ...`):
  ward boundaries drawn over the GEE LST composite thumbnail →
  data/processed/ward_lst_overlay.png. Numeric confirmation: LST sampled
  under each corrected polygon vs assigned ward mean r=**0.840** (median
  offset 0.1 K); hottest sets agree {15,17,14,16,2} vs {15,14,17,16,31}.
- App re-verified headless: Ready, 117 paths, 0 JS errors, mean 40.6 °C.

### Key decisions & why
- **Fix at ingest, never downstream** (user directive): a flip in map.js
  or the stats would break on the next data pull; the mirror is a property
  of THIS source PDF, so it is corrected where that PDF is read, with the
  full evidence chain in the docstring.
- **Overlay PNG is now a standing QA gate**: run it after ANY future change
  to ward extraction, AOI, or compositing — registration bugs are invisible
  in numeric summaries (a mirrored city averages the same) but obvious
  against satellite heat.

### Working / Broken
- ✅ Working: correctly-registered ward layer + LST tiles + choropleth;
  stats cache refreshed; overlay QA reproducible.
- ❌ Broken / blocked: nothing new; scenario/hotspots endpoints still await
  tasks #4–6.

### Next steps (for next session)
- [ ] Task #4: S2 NDVI/NDBI composites (unlock remaining toggles).
- [ ] Tasks #5–#6: persistent hotspots + scenario fit + sliders UI.

## 2026-09-24 (session 5) — Task #8: frontend map wired (tiles + choropleth + year selector)

### Done
- `backend/app/api/wards.py` (new): GET /api/wards serves the 114-ward
  FeatureCollection for the choropleth; registered in main.py.
- `main.py`: CORS for localhost/file:// origins + StaticFiles mount of
  frontend/ (html=True) — one origin serves both app and API. Mount MUST
  come after all API routes: placed mid-file it shadowed /api/health.
- `api.js` implemented: fetchLayers/fetchComparison/fetchWards with error
  propagation; API_BASE is same-origin (""), falls back to localhost:8000
  under file://.
- `map.js` implemented: locked view (maxBounds viscosity 1.0, minZoom 11,
  fitBounds from /api/layers bbox), OSM basemap, GEE LST tile overlay
  (0.8 opacity), ward choropleth colored by within-year hotspot
  percentile, hover tooltips (K + °C + p95 + percentile), legend control,
  year setter, layer-visibility setters, graceful "backend unreachable"
  panel.
- `ui.js` implemented: year selector, two layer toggles, status line
  (uhi:status events), city summary panel (mean °C / hottest p95 / wards).
- `index.html`: real controls replace placeholders + legend/error/status
  styling.
- Verified in headless Chrome: status "Ready", 117 ward paths rendered,
  20 GEE tile requests, legend + city summary populated (2024 city mean
  40.6 °C), zero JS console errors.

### Key decisions & why
- **Same-origin serving** (API mounts the frontend): no CORS in the normal
  case, one command to run; CORS retained for file:// / separate dev server.
- **Choropleth color = hotspot percentile, not raw K**: matches the locked
  methodology (percentile ranks, never fixed cutoffs); raw K lives in the
  tooltip + satellite tint.
- **null ward_no join**: GEE sentinel −1 → JSON null → client joins the
  i-th null feature to the i-th null stat (stable order, both sides sorted).

### Working / Broken
- ✅ Working: full visual loop — year select → /api/layers tile swap +
  /api/comparison choropleth restyle; toggles; legend; tooltips.
- ❌ Broken / blocked: scenario sliders (needs task #6); NDVI/NDBI toggles
  (needs task #4); headless-Chrome checks are flaky across separate shell
  invocations (background procs reaped) — verified same-command.

### Next steps (for next session)
- [ ] Task #4: S2 NDVI/NDBI composites → unlock layers + toggles.
- [ ] Tasks #5–#6: hotspots + scenario fit → /api/hotspots, /api/scenario,
      scenario sliders UI.
- [ ] Optional: fetch /api/wards + comparison once, join server-side in a
      single payload to cut a round trip.

## 2026-09-24 (session 4) — Ward polygons from PDF + zonal stats + live comparison/layers API

### Done
- Ward boundaries: user supplied the MRSAC CIS-2005 ward-map PDF (pure
  vector, 40k line segments). Built `backend/etl/wards_from_pdf.py`:
  boundary-stroke extraction → endpoint snapping → planar face
  polygonization → label→face assignment → IoU-maximizing similarity fit
  against the OSM city polygon → UTM→WGS84 →
  `backend/config/aoi/nagpur_wards.geojson`.
- 114 ward features: 107 numbered + 13 `ward_no=null` (their numbers are
  not printed anywhere on the source map). Area sum 206.6 km² vs AOI
  210.8 km² (98%); georef scale 94.69 m/pt, rot 10.5°, IoU 0.72,
  boundary RMS ≈ 1.1 km concentrated at the rim.
- `lst_stats.py` implemented: ward FeatureCollection, single server-side
  `reduceRegions` (mean + p95, shared inputs, 100 m sampling) per
  (year, season), within-year percentile hotspot ranks, city summaries,
  JSON cache at `data/processed/lst_ward_stats_{season}.json`.
- `pull_landsat_lst.py`: added `--zonal-stats` / `--refresh` CLI; ran for
  2020–2024 pre-monsoon → all five years cached (city means 313.8–319.1 K,
  2021 hottest — consistent with the city-wide pulls).
- `/api/comparison` live: per-ward stats from cache, computes missing
  years on demand, strict validation (years/layer/season), 503 on GEE
  failure. `/api/layers` live: real getMapId tile URL + fixed vis params
  + AOI bbox. Verified end-to-end incl. 400/503 paths.

### Key decisions & why
- **Georef residual accepted + documented** (user decision): the ~1.2 km
  RMS is a 2005-NMC vs current-OSM boundary mismatch, not a fit bug —
  every pipeline check passed (closed linework, area match, single-part
  AOI, IoU-optimal placement). Interior wards are solid; peripheral wards
  carry ~100–300 m uncertainty. Embedded a `georef` block in the GeoJSON;
  fine for ward-mean LST on 30 m pixels.
- **Unlabeled wards included as `ward_no=null`** (user decision): full
  city coverage beats 22 holes; ee side uses sentinel −1, API maps back
  to null.
- **Hotspot = within-year percentile rank** of ward means, never fixed °C
  cutoffs (seasonal composites control season, not year-specific weather).
- **100 m zonal sampling**: ST_B10 is 30 m but ward means (0.5–2 km²
  zones) are stable at 100 m; ~10x cheaper reductions, bestEffort for
  tiny wards.

### Working / Broken
- ✅ Working: GEE auth end-to-end; ward extraction + georef; zonal stats
  2020–2024 cached; /api/comparison + /api/layers return real data;
  validation paths return 400s.
- ❌ Broken / blocked: starlette TestClient needs `httpx` (not installed)
  — endpoints verified by direct call instead; hotspots/scenario/gee-status
  endpoints still stubbed (need tasks #4–6).

### Next steps (for next session)
- [ ] Task #4: S2 NDVI/NDBI composites (same years/season/polygon rule).
- [ ] Tasks #5–#6: persistent hotspots + scenario fit → unstub
      /api/hotspots + /api/scenario.
- [ ] Task #8: frontend wiring — locked view, year selector, ward choropleth
      from /api/comparison, GEE tiles from /api/layers.

## 2026-09-23 (session 3) — Task #1 code: GEE init + Landsat LST pull implemented

### Done
- venv created + requirements installed; `backend/.env` holds GEE_PROJECT_ID
  (user-provided); added `backend/.env.example` (README referenced it but it
  didn't exist).
- `settings.py`: added `GEE_PROJECT_ID` (from env, stripped).
- `gee_common.py` fully implemented: `get_ee()` (init bound to project,
  cached once per process), `aoi_geometry`/`aoi_feature`,
  `scope_to_nagpur` (filterBounds+clip in ONE place — AOI policy intact),
  `clip_to_nagpur`, `reduce_over_zones` (mean reduceRegion), `to_tile_url`
  (getMapId), plus small AOI/JSON helpers.
- `pull_landsat_lst.py` fully implemented: merged L8/L9 collection, per-year
  season windows (winter wraps the calendar year: Dec→Feb), QA_PIXEL cloud
  mask (dilated cloud/cloud/shadow/snow bits), ST_B10 DN→Kelvin scaling,
  per-year seasonal median composite, reduceRegion stats, CLI with
  `--years/--season/--sanity-check/--print-composites`.
- Verified: imports, season-date windows, scale math, CLI help. The
  sanity-check fails fast with the exact "earthengine authenticate" hint
  until credentials exist — correct behavior, confirmed.

### Key decisions & why
- `get_ee()` defers `import ee` and caches init — non-GEE code paths don't
  pay the import, exactly one Initialize per process.
- Fixed LST vis range 290–325 K (palette blue→red) so year-to-year renders
  are visually comparable — per-year auto-scaling would lie.
- Sanity check = 3 cheap server-side probes: constant echo through GEE
  compute, AOI area plausibility (Nagpur city ≈ 50–1000 km² band), 2024
  pre-monsoon L8/L9 scene count over the polygon.

- GEE auth completed by user (`earthengine authenticate`); sanity check
  passed: echo OK, AOI area 211.36 km² (plausible for Urban Taluka), 23
  L8/L9 scenes over the polygon in pre-monsoon 2024.
- **First real LST pull (task #2)**: pre-monsoon median composites,
  city-wide mean LST: 2020: 317.5 K (44.4 °C), 2021: 319.7 K (46.5 °C),
  2022: 315.4 K (42.2 °C), 2023: 314.3 K (41.2 °C), 2024: 314.4 K (41.3 °C)
  — plausible pre-monsoon daytime surface temps for Nagpur.

### Working / Broken
- ✅ Working: GEE auth end-to-end, polygon-scoped queries, cloud-masked
  composites, ST_B10 scaling, reduceRegion stats, CLI.
- ❌ Not yet: per-ward zonal stats (#3), S2 indices (#4), hotspots (#5),
  scenario fit (#6), live API (#7), frontend (#8).

### Next steps (for next session)
- [ ] Tasks #3/#7: zonal stats (per-ward) + wire API endpoints to real data.
- [ ] Task #4: S2 NDVI/NDBI composites, same years/season.
- [ ] Then #5–#6, #8, and cache composites for the /api/layers tile URLs.

---

## 2026-09-23 (session 2) — Architecture locked: AOI polygon + server-side-only GEE

### Done
- **AOI pinned to a real city polygon.** Rejected bounding boxes for good:
  fetched the **Nagpur Urban Taluka** boundary (OSM relation **10330977**,
  admin_level 6 — city extent; the wider rural district is a separate
  relation and is excluded) and stored it as a static reference at
  `backend/config/aoi/nagpur_city.geojson` (384-vertex closed MultiPolygon,
  bbox 78.995–79.179 E / 21.053–21.231 N, ODbL provenance in file props).
  Checked GADM vs OSM; OSM gave cleaner, more current city geometry.
- Restructured `backend/config/settings.py` around the polygon: AOI loader +
  a derived bbox that is **explicitly for coarse map-fitting only**, never
  filtering. Removed the old hand-typed `NAGPUR_BBOX`.
- Added `backend/etl/gee_common.py` — the single choke point where every GEE
  query will get `.filterBounds(aoi)` + `.clip(aoi)` (stubs now).
- Rewrote/added ETL stubs to the agreed design: `pull_landsat_lst.py`
  (merged L8/L9, **ST_B10**, DN→K scale, seasonal median composite),
  `pull_s2_indices.py` (S2 SR 10 m; NDVI = (B8−B4)/(B8+B4), NDBI =
  (B11−B8)/(B11+B8), SCL cloud mask; WorldCover v200 clipped).
- Analysis stubs: `hotspots.py` (top-percentile-across-most-years), 
  `scenario.py` (fitted dLST ~ dNDVI + dNDBI regression with explainable
  coefficients — explicitly **no black-box model**), `lst_stats.py`
  (per-year/zonal summaries via reduceRegion, cached to data/processed).
- Stubbed all API endpoints: `/api/layers`, `/api/comparison`,
  `/api/hotspots`, `/api/scenario` (Pydantic contract with explanation
  payload), `/api/gee-status`; wired into `main.py`.
- Frontend stubs: `src/js/api.js` (only module allowed to call the backend),
  `map.js` (maxBounds-locked Leaflet + GEE overlays), `ui.js` (layer
  toggles, year selector, scenario sliders + explanation panel);
  `index.html` sidebar placeholders updated to match.
- Updated PROJECT.md: AOI policy callout, ST_B10 approach, server-side-only
  rule, Leaflet locked-view note, AOI provenance row in data sources.

### Key decisions & why
- **OSM Urban Taluka polygon over GADM/bbox** — it is the actual city extent;
  a rectangle spills into surrounding rural areas and would skew every LST
  statistic. Geometry is static + version-controlled so all sessions and
  endpoints scope identically; re-fetching requires a dated PLAN.md entry.
- **ST_B10 instead of deriving LST from radiance** — Collection 2 Level-2
  ships atmospherically corrected surface temperature (emissivity handled);
  one scale/offset (DN × 0.00341802 + 149.0) to Kelvin. Less code, fewer
  methodology traps.
- **Seasonal median composites per year** (same season window every year) —
  protects against comparing a cloudy monsoon date against a clear winter
  date; pre-monsoon (Mar–May) is the primary window.
- **Server-side-only GEE policy** — reduceRegion for numbers, getMapId for
  tiles; no raw-imagery downloads, keeps us inside noncommercial-tier norms
  and the project lean.
- **Scenario model = fitted linear relationship with published coefficients**
  (dLST ~ a·dNDVI + b·dNDBI + c within the polygon) — the platform must
  explain WHY it estimates what it estimates; black-box models are banned by
  design.
- **Leaflet view locked to polygon extent** (maxBounds/minZoom from the AOI
  bbox) — users can't pan into irrelevant territory; reinforces the AOI
  discipline end-to-end.

### Working / Broken
- ✅ Working: full skeleton per the agreed architecture; all Python stubs
  compile; AOI geojson validated (closed rings, sane bbox); import graph
  consistent (routers wired, settings loads polygon).
- ❌ Not yet attempted: GEE auth/first pull, any real GEE query, composites,
  hotspot/scenario math, live endpoints, map rendering.

### Next steps (for next session)
- [ ] Task #1 — GEE auth end-to-end (noncommercial Cloud project,
      `earthengine authenticate`, `GEE_PROJECT_ID` in backend/.env), then
      implement `gee_common.py` and run the first polygon-scoped query.
- [ ] Task #2 — first LST pull: L8/L9 pre-monsoon composite for one recent
      year via ST_B10; sanity-check reduceRegion stats inside the polygon.
- [ ] Task #4 — S2 NDVI/NDBI composites for the same year/season.
- [ ] Tasks #5–#7 — multi-year stats, hotspots, scenario fit, then API
      endpoints; frontend wiring last (task #8).

---

## 2026-09-23 (session 1) — Project scaffolding

### Done
- Created the directory skeleton (backend: FastAPI app + etl/gee_pulls +
  etl/analysis; frontend static Leaflet app; data/raw + data/processed; docs).
- Wrote PROJECT.md (problem statement, scope, stack rationale, data sources)
  and README.md (prereqs, GEE auth steps, setup, structure).
- Seeded dependency list (requirements.txt), .gitignore, and stub entry points.
  All stubs raise NotImplementedError — no logic by design.

### Key decisions & why
- **FastAPI over Flask/Django** — async-friendly for the "kick off GEE job →
  poll" pattern, Pydantic validation, auto Swagger docs; same Python process
  as the GEE/analysis code.
- **Leaflet over Mapbox GL JS as the base** — zero API-key friction, plain
  static files with no build step; Mapbox tiles remain an optional basemap.
- **LST from Landsat 8/9 only** — Sentinel-2 has no thermal band; S2 is for
  10 m NDVI/NDBI detail, not temperature.
- **No database for v1** — outputs are small JSON stats + rasters on disk
  under `data/`; add PostGIS only if/when zonal queries get heavy.
- **Seasonal composites over single scenes** — Nagpur monsoon cloud cover
  makes per-date analysis unreliable; pre-monsoon (Mar–May) is the primary
  study window.
- **Scenario engine = empirical regression on Nagpur's own NDVI/NDBI↔LST
  relationship**, not a physical model — honest, cheap, defensible; explicitly
  not forecasting.

### Working / Broken
- ✅ Working: folder structure, all docs, empty stubs importable.
- ❌ Not yet attempted: GEE auth, any data pull, any LST/NDVI math, frontend
  map (index.html is a bare shell).

---

## Task Board — rough sequence

> Status legend: `todo` → `doing` → `review` → `done`. Keep this coarse;
> details belong in session entries.

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | GEE auth + first polygon-scoped data pull | done | sanity check passed 2026-09-23: echo OK, AOI 211 km², 23 scenes |
| 2 | LST computation, one time period | done | pre-monsoon 2020–2024 composites pulled; means 314–320 K, plausible |
| 3 | Zonal LST stats via reduceRegion | done | 114 wards, mean+p95, 2020–2024 cached; hotspot pct ranks |
| 4 | NDVI / NDBI + WorldCover | done | NDVI+NDBI live (session 7); WorldCover 2021 snapshot + class-share stats live (session 10) |
| 5 | Multi-year comparison + persistent hotspots | done | 7 persistent wards found (pct90/frac0.7, 7 years); /api/hotspots live |
| 6 | Scenario relationship fit (dLST ~ dNDVI + dNDBI) | done | fitted (n=456, r²=0.31, signs physical); /api/scenario + sliders live |
| 7 | API endpoints live (layers/comparison/hotspots/scenario/gee-status) | done | all five + /api/wards live 2026-09-24; 29-check smoke suite |
| 8 | Frontend wiring | done | map, choropleth, hotspot pins, layer/year selectors, scenario panel live |
| 9 | Docs: methodology write-up | done | docs/METHODOLOGY.md: 10 sections + caveats + repro commands; README/PROJECT cross-linked |
