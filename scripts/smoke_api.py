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
    check("chrome status Ready", 'data-kind="info">Ready<' in dom_html)
    # 3 layer options + 7 year options (2019-2025 for lst)
    check("chrome selector options", dom_html.count("<option value=") >= 10)
    check("chrome ward paths", dom_html.count("<path") >= 100,
          f"{dom_html.count('<path')} paths")
    check("chrome gee tiles requested", dom_html.count("earthengine") > 0)
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
