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

## 2026-09-23 — Project scaffolding

### Done
- Created the full directory skeleton (backend: FastAPI app + etl/gee_pulls +
  etl/analysis; frontend static Leaflet app; data/raw + data/processed; docs).
- Wrote PROJECT.md (problem statement, scope, stack rationale, data sources)
  and README.md (prereqs, GEE auth steps, setup, structure).
- Seeded dependency list (requirements.txt), .gitignore, and stub entry points:
  `backend/app/main.py`, `backend/etl/gee_pulls/pull_landsat_lst.py`,
  `backend/etl/analysis/lst_stats.py`, `backend/config/settings.py`,
  `frontend/index.html`. All stubs raise NotImplementedError — no logic yet.

### Key decisions & why
- **FastAPI over Flask/Django** — async-friendly for the "kick off GEE job →
  poll" pattern, Pydantic validation, auto Swagger docs; stays in the same
  Python process as the GEE/analysis code.
- **Leaflet over Mapbox GL JS as the base** — zero API-key friction, plain
  static files with no build step; Mapbox tiles remain an optional basemap.
- **LST from Landsat 8/9 only** — Sentinel-2 has no thermal band; S2 is for
  10 m NDVI/NDBI detail, not temperature.
- **No database for v1** — outputs are small JSON stats + GeoTIFF/PNG rasters
  on disk under `data/`; add PostGIS only if/when zonal queries get heavy.
- **Seasonal composites over single scenes** — Nagpur monsoon cloud cover
  makes per-date analysis unreliable; pre-monsoon (Mar–May) is the primary
  study window.
- **Scenario engine = empirical regression on Nagpur's own NDVI/NDBI↔LST
  relationship**, not a physical model — honest, cheap, and defensible;
  explicitly not forecasting (see PROJECT.md scope).

### Working / Broken
- ✅ Working: folder structure, all docs, empty stubs importable.
- ❌ Not yet attempted: GEE auth, any data pull, any LST/NDVI math, frontend
  map (index.html is a bare shell).

### Next steps (for next session)
- [ ] GEE auth end-to-end: register noncommercial Cloud project, `earthengine
      authenticate`, set GEE_PROJECT_ID in backend/.env, run the first
      successful scripted data pull.
- [ ] First data pull: Landsat 8/9 pre-monsoon composite over the Nagpur AOI
      (pin down the actual boundary polygon — GADM vs OSM).
- [ ] LST computation for one time period (single-channel + NDVI-based
      emissivity), export as GeoTIFF/PNG tiles.
- [ ] NDVI/NDBI computation for the same window (Landsat + Sentinel-2).
- [ ] Multi-year comparison logic (per-year seasonal composites, deltas).
- [ ] Scenario modeling logic (fit NDVI/NDBI↔LST regression on historical
      data, apply per-zone deltas).
- [ ] Frontend map integration: Leaflet + LST overlay + year switcher.
- [ ] UI for scenario sliders wired to the backend scenario endpoint.

---

## Task Board — rough sequence

> Status legend: `todo` → `doing` → `review` → `done`. Keep this coarse;
> details belong in session entries.

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | GEE auth + first successful data pull | todo | Blocks everything else |
| 2 | Pin down Nagpur AOI boundary polygon | todo | GADM / OSM / digitized |
| 3 | LST computation, one time period | todo | Landsat 8/9 thermal + emissivity |
| 4 | NDVI / NDBI computation | todo | L8/9 + Sentinel-2 10 m |
| 5 | Multi-year comparison (3–5+ yrs) | todo | Seasonal composites, deltas, hotspot ranking |
| 6 | Hotspot identification | todo | Percentile/rank-based thresholds |
| 7 | Scenario modeling logic | todo | Empirical NDVI/NDBI↔LST regression |
| 8 | Backend API endpoints | todo | Layers, years, zones, scenario estimate |
| 9 | Frontend map integration (Leaflet) | todo | LST overlay, year switcher, hotspots |
| 10 | UI scenario sliders | todo | Ward/zone selection + % vegetation/built-up deltas |
| 11 | Docs: methodology write-up | todo | Emissivity method, regression fit, caveats |
