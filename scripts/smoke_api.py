"""End-to-end API + render smoke test (single foreground process).

Starts uvicorn in a daemon thread (no shell background jobs — this sandbox
reaps those unpredictably), exercises every live endpoint against real GEE,
fetches one real tile per layer, then renders the app in headless Chrome and
greps the DOM. Prints PASS/FAIL lines; exit 1 on any failure.

Run:  .venv/bin/python scripts/smoke_api.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.request

import uvicorn

from backend.app.main import app

BASE = "http://127.0.0.1:8000"
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.load(r)


def fetch_tile(tile_url: str) -> int:
    url = tile_url.replace("{z}/{x}/{y}", "11/1353/754")
    req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read(1024)  # first KB proves the tile serves; full PNG not needed
        return r.status


def main() -> None:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(60):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(BASE + "/api/health", timeout=2)
            break
        except Exception:
            continue
    else:
        print("FAIL  server never came up")
        sys.exit(1)

    # --- health ---------------------------------------------------------------
    health = get_json("/api/health")
    check("health", health.get("status") == "ok")

    # --- layers: all three, tile fetch each -------------------------------------
    for layer in ("lst", "ndvi", "ndbi"):
        d = get_json(f"/api/layers?year=2024&layer={layer}")
        ok_host = "earthengine.googleapis.com" in d.get("tile_url", "")
        try:
            status = fetch_tile(d["tile_url"])
        except Exception as exc:
            status = f"error {exc}"
        check(
            f"layers[{layer}] tile",
            ok_host and status == 200,
            f"vis {d['vis_params']['min']}-{d['vis_params']['max']} {d['units']}",
        )

    # --- layers: year guards ------------------------------------------------------
    try:
        get_json("/api/layers?year=2016&layer=ndvi")
        check("layers ndvi 2016 rejected", False, "expected 400")
    except urllib.error.HTTPError as e:
        check("layers ndvi 2016 rejected", e.code == 400)
    try:
        get_json("/api/layers?year=2024&layer=landcover")
        check("layers unknown layer rejected", False, "expected 400")
    except urllib.error.HTTPError as e:
        check("layers unknown layer rejected", e.code == 400)

    # --- comparison: three layers --------------------------------------------------
    for layer, want_units in (("lst", "Kelvin"), ("ndvi", "index (-1..1)"), ("ndbi", "index (-1..1)")):
        d = get_json(f"/api/comparison?years=2020,2024&layer={layer}")
        wards = d["years"].get("2024", {}).get("wards", [])
        check(
            f"comparison[{layer}]",
            d.get("units") == want_units and len(wards) == 114,
            f"city {d['years']['2024']['city']}",
        )

    # --- wards -------------------------------------------------------------------
    wards_fc = get_json("/api/wards")
    check("wards", len(wards_fc.get("features", [])) == 114)

    # --- hotspots (task #5) -------------------------------------------------------
    hs = get_json("/api/hotspots")  # defaults: pct=90, frac=0.7
    det = hs.get("detection", {})
    feats = hs.get("features", [])
    check("hotspots detection meta",
          det.get("pct") == 90 and det.get("min_year_frac") == 0.7
          and len(det.get("years_used", [])) >= 5,
          f"{len(det.get('years_used', []))} years, {len(feats)} hotspots")
    check("hotspots present", 1 <= len(feats) <= 30)
    top = feats[0]["properties"] if feats else {}
    check("hotspots ranked top persistence", top.get("persistence", 0) >= 0.7)
    try:
        get_json("/api/hotspots?pct=45")
        check("hotspots pct guard", False, "expected 400")
    except urllib.error.HTTPError as e:
        check("hotspots pct guard", e.code == 400)
    hs_geo = get_json("/api/hotspots?with_geometry=true")
    g0 = hs_geo["features"][0]["geometry"] if hs_geo["features"] else None
    check("hotspots with_geometry", g0 is not None and g0.get("type") in ("Polygon", "MultiPolygon"))

    # --- scenario (task #6) --------------------------------------------------------
    def post_json(path: str, payload: dict):
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)

    sc = post_json("/api/scenario", {"zone_id": "15", "veg_delta": -20, "builtup_delta": 0})
    ex = sc.get("explanation", {})
    check("scenario ward 15 estimate", isinstance(sc.get("est_lst_change_c"), (int, float)),
          f"{sc.get('est_lst_change_c')} °C, baseline {sc.get('baseline')}")
    check("scenario explanation complete",
          all(k in ex for k in ("equation", "coef", "p", "r2", "n", "signs_as_expected")),
          f"n={ex.get('n')}, r2={round(ex.get('r2', 0), 2)}, signs_ok={ex.get('signs_as_expected')}")
    sc_city = post_json("/api/scenario", {"zone_id": "city", "veg_delta": 10, "builtup_delta": -5})
    check("scenario city fallback", isinstance(sc_city.get("est_lst_change_c"), (int, float)))
    try:
        post_json("/api/scenario", {"zone_id": "999", "veg_delta": 5, "builtup_delta": 5})
        check("scenario unknown ward rejected", False, "expected 400")
    except urllib.error.HTTPError as e:
        check("scenario unknown ward rejected", e.code == 400)
    try:
        post_json("/api/scenario", {"zone_id": "15", "veg_delta": 150, "builtup_delta": 0})
        check("scenario delta bounds", False, "expected 422")
    except urllib.error.HTTPError as e:
        check("scenario delta bounds", e.code == 422)
    check("scenario signs physical", ex.get("signs_as_expected") is True,
          f"coef {ex.get('coef')}")

    # --- landcover (task #4 completion) --------------------------------------------
    lc = get_json("/api/layers?year=2021&layer=landcover")
    check("landcover tile", "earthengine.googleapis.com" in lc.get("tile_url", ""),
          f"units {lc.get('units')}")
    try:
        get_json("/api/layers?year=2024&layer=landcover")
        check("landcover year pinned", False, "expected 400")
    except urllib.error.HTTPError as e:
        check("landcover year pinned", e.code == 400)
    try:
        get_json("/api/comparison?years=2021&layer=landcover")
        check("landcover comparison blocked", False, "expected 400")
    except urllib.error.HTTPError as e:
        check("landcover comparison blocked", e.code == 400)
    lcs = get_json("/api/landcover-stats")
    dom0 = lcs["wards"][0]["dominant"] if lcs.get("wards") else None
    check("landcover stats",
          len(lcs.get("wards", [])) == 114 and dom0 is not None
          and "class_colors" in lcs,
          f"sample dominant: {dom0}")

    # --- headless Chrome render ------------------------------------------------------
    subprocess.run(
        ["rm", "-rf", "/tmp/uhi_smoke_profile"], check=False
    )
    dom = subprocess.run(
        [
            "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-proxy-server", "--user-data-dir=/tmp/uhi_smoke_profile",
            "--enable-logging=stderr", "--window-size=1400,900",
            "--virtual-time-budget=40000", "--dump-dom", BASE + "/",
        ],
        capture_output=True, text=True, timeout=180,
    )
    dom_html = dom.stdout
    check("chrome DOM has app", "UHI Nagpur" in dom_html)
    # Terminal status is either "Ready" or the hotspot summary (whichever
    # async branch finished last) — anything else (Starting…/error) is a fail.
    status_ok = (
        'data-kind="info">Ready<' in dom_html
        or 'data-kind="info">Persistent hotspots:' in dom_html
    )
    check("chrome status reached terminal state", status_ok)
    # 3 layer options + 7 year options (2019-2025 for lst)
    check("chrome selector options", dom_html.count("<option value=") >= 10)
    check("chrome ward paths", dom_html.count("<path") >= 100,
          f"{dom_html.count('<path')} paths")
    check("chrome gee tiles requested", dom_html.count("earthengine") > 0)
    check("chrome hotspot pins", dom_html.count("uhi-hotspot-pin") >= 1)
    check("chrome scenario panel", "scenario-result" in dom_html and "°C" in dom_html,
          "panel rendered with an estimate")
    check("chrome 4 layer options", dom_html.count("<option value=") >= 13)
    # 4 layers + 7 years minimum
    check("chrome no js errors",
          "Uncaught" not in dom.stderr and "TypeError" not in dom.stderr)

    server.should_exit = True
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
