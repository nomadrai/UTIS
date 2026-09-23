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
| 3 | Zonal LST stats via reduceRegion | todo | Small JSON to data/processed; feeds /api/comparison |
| 4 | NDVI / NDBI + WorldCover | todo | S2 SR 10 m; SCL mask; same polygon + season rule |
| 5 | Multi-year comparison + persistent hotspots | todo | Top-percentile-across-most-years |
| 6 | Scenario relationship fit (dLST ~ dNDVI + dNDBI) | todo | Explainable coefficients; no black box |
| 7 | API endpoints live (layers/comparison/hotspots/scenario/gee-status) | todo | Contracts stubbed in backend/app/api/ |
| 8 | Frontend wiring | todo | Locked view, layer control, year selector, sliders + explanation panel |
| 9 | Docs: methodology write-up | todo | Compositing, masking, regression fit, caveats |
