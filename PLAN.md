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
| 1 | GEE auth + first polygon-scoped data pull | todo | ee.Initialize(project=...); implement gee_common.py |
| 2 | LST computation, one time period | todo | L8/L9 ST_B10, seasonal median, clip to nagpur_city.geojson |
| 3 | Zonal LST stats via reduceRegion | todo | Small JSON to data/processed; feeds /api/comparison |
| 4 | NDVI / NDBI + WorldCover | todo | S2 SR 10 m; SCL mask; same polygon + season rule |
| 5 | Multi-year comparison + persistent hotspots | todo | Top-percentile-across-most-years |
| 6 | Scenario relationship fit (dLST ~ dNDVI + dNDBI) | todo | Explainable coefficients; no black box |
| 7 | API endpoints live (layers/comparison/hotspots/scenario/gee-status) | todo | Contracts stubbed in backend/app/api/ |
| 8 | Frontend wiring | todo | Locked view, layer control, year selector, sliders + explanation panel |
| 9 | Docs: methodology write-up | todo | Compositing, masking, regression fit, caveats |
