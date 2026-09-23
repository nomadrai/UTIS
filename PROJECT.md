# Urban Heat Island Intelligence Platform — Nagpur

**Status:** MVP complete — all analysis tasks implemented and smoke-tested (2026-09-24). See the task board in [PLAN.md](PLAN.md).
**How the analysis works:** [docs/METHODOLOGY.md](docs/METHODOLOGY.md) · **Session log:** [PLAN.md](PLAN.md) · **Setup:** [README.md](README.md)

---

## 1. Problem Statement

### What is UHI?

An **Urban Heat Island (UHI)** is the phenomenon where a city is measurably warmer
than its rural surroundings. Built-up surfaces — concrete, asphalt, rooftops —
absorb solar radiation during the day and re-emit it slowly, while the loss of
vegetation removes the cooling effect of evapotranspiration and shading. The
result is a persistent thermal anomaly over the urban core, visible from space
in thermal infrared imagery as **Land Surface Temperature (LST)**.

> Note: this platform works with **LST** (surface temperature), not air
> temperature. LST is what satellites measure directly, is the standard
> UHI-analysis input, and correlates strongly with heat exposure at street
> level — but the two are not identical.

### Why Nagpur?

Nagpur is a useful and under-studied UHI case study:

- **Rapid urbanization** — expanding built-up footprint and road networks
  converting vegetated/peripheral land, the classic UHI driver.
- **Climate context** — a hot semi-arid climate with extreme pre-monsoon
  (March–May) temperatures; the city already records some of India's highest
  summer readings, so incremental UHI amplification has real public-health
  consequences.
- **Known seasonal pattern** — research literature reports UHI intensity in
  central Indian cities peaking in the pre-monsoon daytime window, which makes
  Nagpur a good candidate for multi-temporal analysis.
- **Data availability** — Nagpur sits under consistent Landsat 8/9 and
  Sentinel-2 coverage, and its metro area fits comfortably within a single
  WRS-2 scene and a manageable Sentinel-2 tile set.

### What this platform is meant to answer

1. **Where** are the thermal hotspots in Nagpur, and how have they moved or
   grown over the last 3–5+ years?
2. **What** land-cover change (vegetation loss, built-up expansion) correlates
   with observed LST change?
3. **What if** — if vegetation were restored or built-up area changed in a
   specific area, how would surface temperature distribution plausibly shift?
   (Scenario estimation, not prediction — see scope.)

---

## 2. Scope

> **AOI policy (hard rule, agreed 2026-09-23):** every GEE query and every map
> render is scoped to the static Nagpur **city polygon** at
> `backend/config/aoi/nagpur_city.geojson` (OSM relation 10330977 = Nagpur
> Urban Taluka, i.e. the city extent — the wider rural district is excluded).
> All imagery filtering applies `.filterBounds(aoi)` + `.clip(aoi)` with this
> exact polygon via `backend/etl/gee_common.py` — **never a bounding-box
> approximation**, which would pull in surrounding rural areas and skew the
> analysis. Server-side compute only: we pull small numeric summaries
> (`reduceRegion`) or tile URLs (`getMapId`), never raw imagery.

### WILL do

- **LST mapping** from Landsat 8/9 Collection 2 Level-2 `ST_B10` — the
  pre-computed, atmospherically corrected surface-temperature band (no
  derivation from raw thermal radiance) — composited by **seasonal median**
  so no year is compared against a different season's weather.
- **Land-cover analysis** via spectral indices:
  - **NDVI** (vegetation density) from Landsat 8/9 and Sentinel-2,
  - **NDBI** (built-up index) from the same imagery,
  - cross-checked against reference land-cover products (ESA WorldCover).
- **Multi-year comparison** — per-pixel and zonal (ward/administrative unit)
  comparison across **3–5+ years**, e.g. same-season composites per year.
- **Hotspot identification** — statistically flag pixels/zones that are
  persistently hotter than the scene baseline (e.g. percentile/rank-based
  thresholds per period, not arbitrary fixed °C cutoffs).
- **Scenario estimation ("what-if")** — user adjusts a slider (e.g.
  "−20% vegetation in ward X" / "+15% built-up in ward Y") and the platform
  estimates the LST shift using an empirical statistical relationship between
  NDVI/NDBI and LST fitted on Nagpur's own historical data, rendered back onto
  the map.
- **Interactive map interface** — Leaflet-based web frontend showing LST /
  index layers, year switcher, hotspot overlays, and scenario sliders.

### WILL NOT do

- **No absolute future climate prediction.** The what-if module produces
  *relative scenario estimates* derived from historical correlations, not
  forecasts of future temperature. It cannot say "Nagpur will be 43°C in 2040";
  it can say "under this land-cover scenario, these zones plausibly shift
  ~+1.2°C relative to today's distribution."
- **No air-temperature / weather modeling**, no CFD or microclimate simulation.
- **No operational/real-time monitoring** — analysis runs on requested time
  windows, not a live feed.
- **No ground-truth campaign** — validation relies on published relationships
  and cross-dataset consistency, not in-situ sensors (a possible future
  extension).
- **No mobile app** — responsive web only.

---

## 3. Tech Stack & Why

| Layer | Choice | Why |
|---|---|---|
| Data + compute | **Google Earth Engine (Python API)** | Decades of Landsat/Sentinel archives, cloud-side processing — no local imagery downloads, no raster GPU math on this machine. GEE composites, cloud-masking, and index math run server-side; we pull only small numeric summaries (reduceRegion) and map tile URLs (getMapId). |
| Backend | **Python + FastAPI** | Same language as the GEE/analysis stack (no context switching between services); async endpoints fit the "fire GEE job → poll → serve result" pattern well; Pydantic gives request/response validation for free. FastAPI also auto-documents the API (Swagger UI), which keeps frontend/backend contract honest. |
| Frontend map | **Leaflet** | Lean, dependency-free, ubiquitous, excellent raster-overlay support for GEE-hosted tiles. Initial view locked/bounded to the Nagpur polygon extent (maxBounds); GEE tile overlays + year selector + scenario sliders. |
| Map basemap tiles | **OpenStreetMap** default (optional Mapbox token) | OSM costs nothing and works offline of any API key. Mapbox GL vector basemaps remain an optional upgrade — Leaflet consumes both. Keeping Leaflet (rather than Mapbox GL JS) as the base avoids vendor lock-in for a research tool. |
| Land-cover reference | **ESA WorldCover** (via GEE catalog) | 10 m global land cover, available in the GEE public catalog, no extra pipeline. Bhuvan (ISRO) LULC products kept as an India-specific cross-check/alternative. |
| Charts | **Chart.js** (if/when needed) | Small, no build step, enough for time-series comparisons. |

Deliberately **not** used (for now): PostGIS/database (results are small JSON +
GeoTIFF/PNG outputs on disk), Celery/queues (GEE handles the heavy compute),
React/Vue build tooling (a static Leaflet app keeps the project navigable).

---

## 4. Data Sources

| Dataset | GEE ID | Use |
|---|---|---|
| Landsat 8 OLI/TIRS | `LANDSAT/LC08/C02/T1_L2` | Primary LST source via `ST_B10` (pre-computed surface temperature), 30 m optical / 100 m thermal, 2013–present. Collection 2 Level-2. |
| Landsat 9 OLI-2/TIRS-2 | `LANDSAT/LC09/C02/T1_L2` | Extends LST continuity from 2021 onward; merged with L8 for denser time series. |
| Sentinel-2 MSI | `COPERNICUS/S2_SR_HARMONIZED` | 10 m NDVI/NDBI at higher spatial detail; **no thermal band**, so LST comes from Landsat only, S2 supplements land-cover mapping. |
| ESA WorldCover 10 m | `ESA/WorldCover/v200` (2021) | Land-cover reference/validation for built-up vs vegetation classes. |
| Bhuvan LULC (ISRO) | manual download (not in GEE) | Optional India-specific land-cover cross-check. |
| AOI boundary | OSM relation 10330977 (Nagpur Urban Taluka) | City-extent polygon stored at `backend/config/aoi/nagpur_city.geojson` (384-vertex MultiPolygon, ODbL licensed). OSM gave cleaner city geometry than GADM admin levels; static reference — re-fetch only with a dated PLAN.md entry. |

**Primary constraints we design around:**

- Landsat revisit is 16 days per satellite (~8 days combined L8+L9) and monsoon
  cloud cover in Nagpur (Jun–Sep) seriously thins usable scenes — analysis
  windows use seasonal composites rather than single dates.
- `ST_B10` is already atmospherically corrected (emissivity correction
  included) — no custom single-channel retrieval needed; convert DN to
  Kelvin with the C2 L2 factor (DN × 0.00341802 + 149.0).
- GEE free (noncommercial) tier has concurrency/limits — batch jobs rather
  than on-the-fly heavy computation where possible.
