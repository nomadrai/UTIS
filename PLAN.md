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
| 4 | NDVI / NDBI + WorldCover | todo | S2 SR 10 m; SCL mask; same polygon + season rule |
| 5 | Multi-year comparison + persistent hotspots | todo | Top-percentile-across-most-years |
| 6 | Scenario relationship fit (dLST ~ dNDVI + dNDBI) | todo | Explainable coefficients; no black box |
| 7 | API endpoints live (layers/comparison/hotspots/scenario/gee-status) | doing | layers+comparison+wards live 2026-09-24; hotspots/scenario/gee-status wait on #4–6 |
| 8 | Frontend wiring | doing | map+choropleth+year selector live 2026-09-24; scenario panel waits on #6 |
| 9 | Docs: methodology write-up | todo | Compositing, masking, regression fit, caveats |
