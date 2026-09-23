# Methodology — UHI Intelligence Platform (Nagpur)

This document explains **what the platform computes, why each choice was
made, and where the numbers can't be trusted**. It is the reference for the
analysis visible in the app; code locations are linked throughout. Setup
instructions live in the [README](../README.md); project scope in
[PROJECT.md](../PROJECT.md); the session-by-session record in
[PLAN.md](../PLAN.md).

---

## 1. Study design

| Parameter | Value | Why |
|---|---|---|
| Area of interest | OSM relation 10330977 — Nagpur Urban Taluka polygon, 211.4 km² (`backend/config/aoi/nagpur_city.geojson`) | City extent, not the rural district. Hard rule: every GEE query applies `.filterBounds(aoi) + .clip(aoi)` in exactly one place (`gee_common.py`) — **never a bbox**, which would pull in rural surroundings and dilute the urban signal. |
| Study period | 2019–2025 (LST), 2020–2025 cached for S2 indices | Landsat 8+9 combined revisit; all caches extend on demand when the frontend requests a year. |
| Season window | **Pre-monsoon (Mar–May)** for all published numbers | UHI intensity peaks in the pre-monsoon daytime window in central India, and cloud cover is lowest. Other seasons (monsoon/post-monsoon/winter) are supported by the code (`settings.SEASONS`) but not pre-cached. |
| Compositing rule | **Same-season median per year** — seasons are never mixed across years | A year-to-year comparison must not confound season with year. Winter wraps the calendar boundary (Dec→Feb) via the shared `gee_common.season_dates()`. |
| Compute policy | Server-side only: `reduceRegions` summaries + `getMapId` tile URLs | No raw-imagery downloads; the one exception is the small QA thumbnail used by the overlay renderer (`ward_lst_overlay.py`). |

## 2. Ward zones (the analysis units)

**Source:** the MRSAC CIS-2005 ward map PDF (`data/raw/504887890-Nagpur-WARD-Map.pdf`,
a pure-vector sheet) — OSM carries no Nagpur ward boundaries. Extraction
pipeline in `backend/etl/wards_from_pdf.py`:

1. Boundary strokes (uniform gray class) → line segments; endpoint snapping
   closes the linework; planar polygonization → faces.
2. The 107 numeric labels found on the sheet are matched 1:1 to faces
   (nearest-face assignment). **16 of the 123 ward numbers are not printed
   anywhere on the source map**; their polygons exist as unlabeled faces and
   are kept as `ward_no: null` features (13 kept after sliver filtering) so
   the city has no holes.
3. Georeferencing: the extracted city outline is fitted to the OSM AOI
   polygon by **IoU-maximizing similarity transform** (scale + rotation +
   translation; no shear/reflection), then converted UTM 44N → WGS84.
4. Result: **114 ward polygons** (`backend/config/aoi/nagpur_wards.geojson`),
   area sum 206.6 km² vs AOI 210.8 km²; fit rotation 0.5°, **IoU 0.957,
   boundary RMS ≈ 166 m**.

**⚠ The mirror incident (2026-09-24, important history):** the source PDF's
map content is authored **vertically mirrored** (inverted-y map block —
north prints where south belongs; the sheet looks fine because text stays
upright). The first extraction shipped mirrored, which the similarity fit
masked as a "10.5° rotation + 1.2 km RMS = boundary drift". Diagnosis and
root-cause fix (mirror at PDF ingest, `_to_map_space()`, segments and labels
together) are documented in the function docstring and PLAN.md sessions 6.
If this dataset is re-pulled, the fix is already in the ingest path; if a
*different* ward source is ever used, re-run the QA overlay
(`backend/etl/analysis/ward_lst_overlay.py`) — registration errors are
invisible in numeric summaries (a mirrored city averages the same) but
obvious against satellite heat.

**Caveats:**
- This is the **2005 delimitation** (123 wards / 10 zones). Nagpur's wards
  were redrawn later; ward *numbers/names* differ from today's. The zones
  are valid analysis units, not current administrative geography.
- ~170 m RMS concentrates at the rim (2005 NMC limit vs current OSM
  taluka cut). Interior ward means on 30 m pixels are unaffected; peripheral
  wards carry the uncertainty. `georef` metadata in the GeoJSON records this.

## 3. Land surface temperature (LST)

Module: `backend/etl/gee_pulls/pull_landsat_lst.py`

- **Sensors:** Landsat 8 + Landsat 9 Collection 2 **Level-2**, merged.
- **Band:** `ST_B10` — the pre-computed, atmospherically corrected surface
  temperature band. No derivation from raw thermal radiance.
- **Scaling:** DN × 0.00341802 + 149.0 → Kelvin (the C2 L2 scale factors).
- **Cloud masking:** `QA_PIXEL` bits cleared for dilated cloud (1), cloud
  (3), cloud shadow (4), snow (5) — bidirectional, per scene, before
  compositing.
- **Compositing:** per-year seasonal **median** of the masked `LST_K` images,
  clipped to the AOI. Median (not mean) rejects residual cloud/edge
  artifacts; the composite over a season draws on ~23 scenes (8-day
  combined revisit minus monsoon-adjacent losses).
- **Render range:** fixed 290–325 K, 5-color palette — identical across
  years so the map is visually comparable year to year.

## 4. Vegetation & built-up indices (NDVI / NDBI)

Module: `backend/etl/gee_pulls/pull_s2_indices.py`

- **Sensor:** Sentinel-2 `COPERNICUS/S2_SR_HARMONIZED` (Level-2A surface
  reflectance, 10 m; coverage from 2017-03-28 — earlier years are rejected).
- **Cloud masking:** the **SCL** band, masking classes 3 (shadow), 8
  (cloud medium), 9 (cloud high), 10 (cirrus), 11 (snow). QA60 is known
  unreliable on SR imagery; SCL classes are explicit and complete.
- **Reflectance scaling:** DN / 10000 → 0..1.
- **Index math happens per scene, *before* compositing** — the median is an
  *index median*, not a band median:
  - **NDVI** = (B8 − B4) / (B8 + B4), render range 0–0.6
  - **NDBI** = (B11 − B8) / (B11 + B8), render range −0.3–0.3
- **Known caveat:** NDBI also responds to open water (SWIR-absorbing), so
  water edges can read as built-up; acceptable at ward scale, documented in
  PROJECT.md.

## 5. Land cover reference (WorldCover)

Module: `backend/etl/gee_pulls/pull_worldcover.py`

- **Dataset:** ESA WorldCover v200 — a **single-year (2021) 10 m
  categorical snapshot**. It deliberately does not participate in the year
  selector (`/api/layers` pins `year=2021`; other years → 400) and does not
  appear in `/api/comparison` (a mean of class codes is meaningless).
- **Zonal statistic:** per-ward **class share** (% of ward area per class)
  via a `pixelArea`-weighted grouped `reduceRegions` — the natural summary
  for categorical data. Cached to `data/processed/worldcover_ward_stats.json`.
- **2021 snapshot result (sanity):** Built-up 57.7 %, Grassland 16.2 %,
  Tree 13.7 %, Cropland 9.2 %, Water 1.5 % of the AOI. Central wards run
  54–90 % built-up — consistent with the persistent-hotspot picture below.

## 6. Zonal statistics & hotspot percentile ranks

Module: `backend/etl/analysis/lst_stats.py`

- One server-side `reduceRegions` per (year, layer): **mean + 95th
  percentile** of the composite over every ward, shared inputs.
- **Sampling scale 100 m** (not the native 10–30 m): ward means over
  0.5–2 km² zones are statistically stable at 100 m, and the reduction is
  ~an order of magnitude cheaper; `bestEffort` lets GEE coarsen further for
  the smallest wards.
- **Hotspot percentile rank:** each ward's mean is ranked **within its own
  year** (0–100 across the 114 wards). This is the locked methodology —
  **never fixed °C cutoffs**. A seasonal composite controls for season, but
  not for year-specific weather (a heatwave year shifts every ward up
  together); within-year ranking is immune to that, which is exactly why
  2021 (the hottest year) does not saturate the hotspot list.
- Caches: `data/processed/lst_ward_stats_{layer}_{season}.json`, one file
  per layer+season, keyed by year. `/api/comparison` serves them and
  computes missing years on demand; `--refresh` recomputes.

## 7. Persistent hotspots

Module: `backend/etl/analysis/hotspots.py` → `GET /api/hotspots`

**Rule (explainable by design):** a ward is a *persistent hotspot* if its
within-year LST percentile rank is **≥ `pct` (default 90)** in at least
**`min_year_frac` (default 0.7)** of the study years with data. Defaults
mean "top-10% hottest in at least 5 of 7 years" on the current 2019–2025
cache.

- Persistence is the signal: hot in one heatwave year is weather; hot in
  5 of 7 years is the urban fabric.
- Detection runs **entirely on cached stats** — zero GEE calls, fully
  reproducible offline.
- Current result: **7 persistent wards**, led by **ward 15 — top-1%
  hottest in all 7 years** (mean 320.7 K ≈ 47.6 °C), then 30, 14, 31, 17,
  6, 13 — the dense central core.
- Sensitivity behaves monotonically (16 hotspots at pct=80 → 2 at 95/0.8
  → 0 at 99/0.99), which is what a meaningful signal should do.
- LST-only by definition; an NDVI/NDBI analogue would be a different
  product ("persistent green / persistent concrete" wards) and could be
  added the same way.

## 8. Scenario fit (dLST ~ dNDVI + dNDBI)

Module: `backend/etl/analysis/scenario.py` → `POST /api/scenario`

**Panel:** for every ward and every consecutive year pair (same season),
compute ΔLST, ΔNDVI, ΔNDBI from the cached ward means → 456 ward-year
delta rows (pre-monsoon 2019–2025).

**Fit:** ordinary least squares **ΔLST = a + b₁·ΔNDVI + b₂·ΔNDBI** with
classical standard errors, t-stats, p-values, r². Nothing fancier — the UI
prints the actual equation, which is the point ("no black box" is a locked
design decision, not a limitation we hid).

**Current fitted model (pre-monsoon panel):**

```
ΔLST = −0.49 − 1.19·ΔNDVI + 110.5·ΔNDBI   (Kelvin)
n = 456, r² = 0.31, residual std = 2.20 K
b_NDBI: p < 0.0001   (highly significant)
b_NDVI: p = 0.90     (NOT significant on this panel)
```

- Signs are physically correct: vegetation gain cools, built-up gain warms.
- **The NDVI term is weak on the current panel.** Year-to-year NDVI deltas
  in a pre-monsoon composite are small and noisy relative to sensor noise.
  The UI surfaces the p-values rather than hiding this. Adding more years
  and/or a second season to the panel is the honest way to tighten it —
  not a more flexible model.
- **Prediction:** a slider % is applied to the *zone's own baseline* mean
  index (ΔNDVI = pct/100 × NDVI_base) so "+20% vegetation" means different
  absolute deltas in green vs concrete wards, then plugged into the fitted
  equation. `zone_id="city"` uses the mean of ward baselines.
- **Extrapolation warnings:** estimates beyond ±5 °C, or farther than half
  the observed ΔLST range (−5.8..+4.2 K), carry explicit warnings in
  `explanation.warnings`. The model interpolates; it does not predict
  unprecedented interventions.

## 9. Caveats & limitations (consolidated)

1. **LST ≠ air temperature.** Satellites measure surface skin temperature;
   street-level heat exposure correlates strongly but is not identical
   (PROJECT.md §1).
2. **Season ≠ weather.** Same-season medians remove seasonal confounding;
   within-year weather (heatwaves, pre-monsoon rainfall timing) remains.
   The within-year percentile methodology is the mitigation.
3. **Ward geometry** is the 2005 delimitation, georeferenced to ~170 m RMS
   (§2). Peripheral wards inherit most of that uncertainty.
4. **NDVI term in the scenario fit is not significant** on the current
   panel (§8) — vegetation what-ifs are directionally informed but
   statistically weak; built-up what-ifs are the strong arm.
5. **NDBI/water confusion** near waterbodies (§4).
6. **GEE tile URLs expire** and the server holds credentials — this is a
   local/demo deployment; hosting needs a service account story.
7. **Ward-level stats, not pixel maps**, for hotspots: persistence is
   computed on zones (the project's analysis unit), not pixel blobs.
8. **One-off environmental caveats** are logged in PLAN.md sessions rather
   than silently patched — e.g. the mirrored source PDF (§2).

## 10. Phase-2 features and how they inherit these rules

Planned extensions (task board #10–#18 in PLAN.md) are bound by the same
methodology — this section is the contract they must honor:

- **AI chat assistant (#11):** answers ONLY from the platform's computed
  data — it calls the same endpoints this document describes (comparison,
  hotspots, scenario, landcover-stats) as tools, and must route any
  what-if arithmetic through `POST /api/scenario`. It may not compute
  numbers itself, and its system prompt includes §9's caveats verbatim so
  it inherits the honesty constraints (LST ≠ air temperature, NDVI-term
  weakness, 2005 ward delimitation). Free-tier providers process prompts
  externally — acceptable for public satellite data, noted for users.
- **What-if map (#10):** client-side prediction must use the coefficients
  and baselines published by the backend (single source of truth), with
  the same extrapolation warnings as `/api/scenario`.
- **Exposure weighting (#13):** population rasters are model estimates —
  source + year must be cited wherever a people-exposed figure appears.
- **ERA5-Land cross-check (#15):** outputs are labeled air temperature
  (2 m), never mixed with LST numbers.

## 11. Reproducibility

Every published number regenerates from these commands (auth + `.env`
required; see README):

```bash
# sanity: auth, AOI, scene counts
python -m backend.etl.gee_pulls.pull_landsat_lst --sanity-check
python -m backend.etl.gee_pulls.pull_s2_indices --sanity-check
python -m backend.etl.gee_pulls.pull_worldcover --sanity-check

# ward polygons from the source PDF (mirror fix included; ~170 m RMS expected)
python -m backend.etl.wards_from_pdf

# per-ward caches (add --refresh to recompute existing years)
python -m backend.etl.gee_pulls.pull_landsat_lst --zonal-stats --years 2019 2020 2021 2022 2023 2024 2025 --season pre-monsoon
python -m backend.etl.gee_pulls.pull_s2_indices   --zonal-stats --years 2020 2021 2022 2023 2024 2025 --season pre-monsoon
python -m backend.etl.gee_pulls.pull_worldcover   --zonal-stats

# QA overlay: ward boundaries drawn over the LST composite
python -m backend.etl.analysis.ward_lst_overlay

# full end-to-end verification (34 checks incl. headless-browser render)
python -m scripts.smoke_api
```

After **any** change to ward extraction, the AOI, or compositing: re-run
the ward extraction, then every `--zonal-stats` pull with `--refresh`, then
the overlay. The hotspot and scenario modules read only the caches, so they
update automatically.
