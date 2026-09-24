"""One-off tuning experiment for the what-if map (user request 2026-09-24).

Boots the API in-process, drives the real app in headless Chrome via CDP
(Node >= 22 built-in WebSocket — no `ws` package), and measures rather
than guesses:
    1. Collision check — legend (top-right) vs chat FAB/drawer
       (bottom-right) pixel boxes must not overlap.
    2. Palette sweep — for several slider settings, read the actual SVG
       fill of every ward path, invert the published diverging ramp, and
       compare the map's implied city-mean effect against the backend's
       model (agreement = client math matches the fitted coefficients).

Run:  .venv/bin/python -m scripts.tune_whatif
"""

from __future__ import annotations

import json
import socket
import statistics
import subprocess
import threading
import time
import urllib.request

import uvicorn

from backend.app.main import app

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
PROFILE = "/tmp/uhi_tune_profile"
CDP_PORT = 9223

# The diverging ramp + normalization from map.js whatIfColor() (kept in
# sync manually; this is a one-off experiment).
STOP_TS = [-1.0, -0.5, 0.0, 0.5, 1.0]
STOP_CS = [(26, 152, 80), (145, 207, 96), (255, 255, 191), (252, 141, 89), (215, 48, 39)]
SCALE_K = 1.5  # |effect| >= 1.5 K saturates
RAMP_HEX = ["#1a9850", "#91cf60", "#ffffbf", "#fc8d59", "#d73027"]


def hex2rgb(h: str) -> tuple[int, ...]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def nearest_effect_k(color: str) -> float:
    """Invert whatIfColor(): observed fill -> implied K effect.

    Mirrors the client's continuous interpolation + perceptual sqrt
    normalizer, inverted by nearest-anchor-segment search.
    """
    rgb = hex2rgb(color) if color.startswith("#") else tuple(
        int(p) for p in color.replace("rgb(", "").replace(")", "").split(",")
    )
    best_t, best_d = 0.0, 1e18
    # Search t on a fine grid within [-1, 1]; pick the t whose interpolated
    # color best matches the observation.
    for i in range(2001):
        t = -1.0 + 2.0 * i / 2000
        tt = (1 + t) / 2 * (len(STOP_TS) - 1)  # position along anchors
        seg = min(int(tt), len(STOP_TS) - 2)
        f = tt - seg
        c = tuple(
            STOP_CS[seg][j] + f * (STOP_CS[seg + 1][j] - STOP_CS[seg][j]) for j in range(3)
        )
        d = sum((a - b) ** 2 for a, b in zip(rgb, c))
        if d < best_d:
            best_t, best_d = t, d
    # Invert the perceptual normalizer: t = sign(x)*sqrt(|x|) -> x = t*|t|
    x = best_t * abs(best_t)
    return round(x * SCALE_K, 3)


def chrome_eval(expr: str, timeout: int = 30):
    """Evaluate JS in the app tab via CDP (one-shot node script per call)."""
    node_script = f"""
const http = require('http');
http.get('http://127.0.0.1:{CDP_PORT}/json/list', (res) => {{
  let raw = '';
  res.on('data', (c) => (raw += c));
  res.on('end', () => {{
    const tabs = JSON.parse(raw).filter(t => t.type === 'page');
    if (!tabs.length) {{ console.error('no page tab'); process.exit(1); }}
    const ws = new WebSocket(tabs[0].webSocketDebuggerUrl);
    ws.onopen = () => {{
      ws.send(JSON.stringify({{ id: 1, method: 'Runtime.evaluate', params: {{
        expression: {json.dumps(expr)}, returnByValue: true, awaitPromise: true }}}}));
    }};
    ws.onmessage = (ev) => {{
      const d = JSON.parse(ev.data);
      if (d.id === 1) {{
        console.log(JSON.stringify(d.result ?? {{error: d.error}}));
        ws.close(); process.exit(0);
      }}
    }};
    setTimeout(() => {{ console.error('cdp timeout'); process.exit(1); }}, {timeout * 1000});
  }});
}});
"""
    out = subprocess.run(
        ["node", "-e", node_script], capture_output=True, text=True, timeout=timeout + 10
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"cdp eval failed: {out.stderr[:300]}")
    data = json.loads(out.stdout.strip().splitlines()[-1])
    if "error" in data:
        raise RuntimeError(f"cdp error: {data['error']}")
    # CDP shapes: primitives -> {result: {result: {type, value}}}; objects
    # with returnByValue -> {result: {type: 'object', value: {...}}}.
    outer = data.get("result", {})
    val = outer.get("result", outer) if isinstance(outer, dict) else {}
    if val.get("subtype") == "error":
        raise RuntimeError(val.get("description", "page eval error"))
    if "value" not in val and val.get("type") != "undefined":
        raise RuntimeError(f"cdp: no value in response: {json.dumps(data)[:300]}")
    return val.get("value")


def set_sliders(veg: int, built: int) -> None:
    chrome_eval(f"""
(() => {{
  const v = document.querySelector('#scenario-veg');
  const b = document.querySelector('#scenario-built');
  v.value = {veg}; v.dispatchEvent(new Event('input', {{ bubbles: true }}));
  b.value = {built}; b.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return 'set';
}})()
""")


def _parse_color(c: str):
    """'#rrggbb' or 'rgb(r,g,b)' -> (r, g, b); None if unparseable."""
    c = c.strip().lower()
    if c.startswith("#") and len(c) == 7:
        try:
            return hex2rgb(c)
        except ValueError:
            return None
    if c.startswith("rgb("):
        try:
            return tuple(int(p) for p in c[4:-1].split(","))
        except ValueError:
            return None
    return None


def ward_fill_hist() -> dict[str, int]:
    """Histogram of WARD fills, keyed by nearest ramp-anchor hex.

    Ward paths are the Leaflet vector pane's <path> elements carrying a
    fill-rule attribute and a stroke; hotspot pins/other overlays live in
    different panes or have fill=none. Bucket by nearest anchor — the
    client emits continuously-interpolated rgb() colors.
    """
    fills = chrome_eval("""
(() => {
  const counts = {};
  document.querySelectorAll('.leaflet-overlay-pane path').forEach(p => {
    const f = (p.getAttribute('fill') || '').trim();
    if (f && f !== 'none') counts[f] = (counts[f] || 0) + 1;
  });
  return counts;
})()
""")
    anchors = [hex2rgb(h) for h in RAMP_HEX]
    hist: dict[str, int] = {}
    for c, n in fills.items():
        rgb = _parse_color(c)
        if rgb is None:
            continue
        nearest = min(
            range(len(anchors)),
            key=lambda i: sum((a - b) ** 2 for a, b in zip(rgb, anchors[i])),
        )
        key = RAMP_HEX[nearest]
        hist[key] = hist.get(key, 0) + n
    return hist


def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
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
        raise SystemExit(1)

    subprocess.run(["rm", "-rf", PROFILE], check=False)
    chrome = subprocess.Popen(
        [
            "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-proxy-server", f"--user-data-dir={PROFILE}",
            f"--remote-debugging-port={CDP_PORT}", "--window-size=1400,900",
            BASE + "/",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2)
                break
            except Exception:
                continue
        time.sleep(14)  # app boot: GEE fetches + ward render

        # --- 1. collision check: legend vs chat FAB/drawer --------------------
        def boxes() -> dict:
            return chrome_eval("""
(() => {
  const q = (sel) => { const el = document.querySelector(sel); if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height }; };
  return { legend: q('.uhi-legend'), fab: q('#chat-fab'),
           drawer: q('#chat-drawer'),
           open: document.querySelector('#chat-drawer')?.classList.contains('open') };
})()
""")

        bx = boxes()
        legend, fab = bx.get("legend"), bx.get("fab")
        check("legend rendered", legend is not None and legend["w"] > 20)
        check("fab rendered", fab is not None)

        def overlap(a, b):
            if not a or not b:
                return 0
            ox = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
            oy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
            return ox * oy

        check("legend does not cover chat FAB", overlap(legend, fab) == 0,
              f"legend y={legend and round(legend['y'])}, fab y={fab and round(fab['y'])}")

        chrome_eval("document.querySelector('#chat-fab').click(); 'ok'")
        time.sleep(0.5)
        bx2 = boxes()
        check("drawer opens", bx2.get("open") is True)
        check("legend does not cover open drawer",
              overlap(bx2.get("legend"), bx2.get("drawer")) == 0)
        chrome_eval("document.querySelector('#chat-close').click(); 'ok'")

        # --- 2. what-if sweep ---------------------------------------------------
        from backend.etl.analysis import scenario as scenario_mod

        model = json.loads(urllib.request.urlopen(BASE + "/api/scenario-model").read())
        intercept = model["coef"]["intercept"]

        def city_ref(veg: int, built: int) -> float:
            # predict() includes the intercept; the map excludes it.
            r = scenario_mod.predict("city", veg, built, scenario_mod.DEFAULT_SEASON)
            return r["est_lst_change_c"] - intercept

        # Enable what-if mode via the real checkbox (exercises actual wiring).
        chrome_eval("""
(() => {
  const chk = document.querySelector('#toggle-whatif');
  chk.checked = true;
  chk.dispatchEvent(new Event('change', { bubbles: true }));
  return 'enabled';
})()
""")
        time.sleep(2.5)  # model fetch + recolor

        sweep = [(0, 0), (20, 0), (0, 30), (-30, -30), (40, 40)]
        results: dict[str, dict] = {}
        for veg, built in sweep:
            set_sliders(veg, built)
            time.sleep(1.2)  # recolor
            hist = ward_fill_hist()
            n = sum(hist.values())
            implied = (
                sum(nearest_effect_k(c) * cnt for c, cnt in hist.items()) / n if n else None
            )
            results[f"{veg}/{built}"] = {
                "n": n, "hist": hist, "implied": implied, "ref": round(city_ref(veg, built), 3),
            }

        print("\npalette sweep (veg/built % -> ward-fill histogram, implied vs reference K):")
        for k, v in results.items():
            hist = " ".join(f"{c[1:]}:{n}" for c, n in sorted(v["hist"].items()))
            imp = f"{v['implied']:+.3f}" if v["implied"] is not None else "n/a"
            print(f"  {k:>8}  n={v['n']:>3}  implied={imp}  ref={v['ref']:+.3f}  [{hist}]")

        # Assertions — encoding what the map actually owes the user:
        # visibility of small effects, correct direction, spatial pattern,
        # and a monotone (near-linear) relationship to the fitted model.
        z = results["0/0"]
        check("zero sliders -> all wards neutral (yellow)",
              z["hist"].get("#ffffbf", 0) == z["n"] and z["n"] >= 100, f"{z['hist']}")

        v20 = results["20/0"]
        n_nonneutral = sum(n for c, n in v20["hist"].items() if c != "#ffffbf")
        check("veg +20 visibly cools (tint appears, direction negative)",
              n_nonneutral >= 1 and (v20["implied"] or 0) <= 0,
              f"implied={v20['implied']:+.3f} (ref {v20['ref']:+.3f}), non-neutral wards={n_nonneutral}")

        check("built-up +30 strongly warms", results["0/30"]["implied"] >= 1.0,
              f"{results['0/30']['implied']:+.3f} (ref {results['0/30']['ref']:+.3f})")

        f40 = results["40/40"]
        check("40/40 shows strong warming with spatial pattern",
              (f40["implied"] or 0) >= 0.9 and len(f40["hist"]) >= 2,
              f"implied={f40['implied']:+.3f}, colors={len(f40['hist'])} "
              "(both 0/30 and 40/40 saturate the ramp past ±1.5 K by design; "
              "ordering between saturated maps is not a requirement)")

        # Map coloring must be a monotone, near-linear function of the model:
        # high Pearson r; slope may compress (perceptual sqrt + saturation,
        # disclosed in the legend) but not invert.
        pairs = [(v["implied"], v["ref"]) for v in results.values() if v["implied"] is not None]
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        sxy = sum((x - mx) * (y - my) for x, y in pairs)
        r = sxy / ((sxx * syy) ** 0.5) if sxx and syy else 0.0
        slope = sxy / sxx if sxx else 0.0
        check("map coloring tracks the fitted model (r>=0.95, slope 0.6-1.9)",
              r >= 0.95 and 0.6 <= slope <= 1.9,
              f"r={r:.4f}, slope={slope:.3f} (compression from perceptual scale is by design)")

    finally:
        chrome.terminate()
        server.should_exit = True

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURES: {FAILURES}")
        raise SystemExit(1)
    print("\nALL TUNING CHECKS PASSED")


if __name__ == "__main__":
    main()
