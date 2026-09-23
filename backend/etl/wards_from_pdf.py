"""One-off: extract Nagpur ward polygons from the MRSAC CIS-2005 ward-map PDF.

Pipeline (ward panel of 504887890-Nagpur-WARD-Map.pdf):
    0. Mirror ingest to map space: the source PDF's map content is
       vertically mirrored (inverted-y authoring) — segments and labels
       are reflected at extraction, see _to_map_space (found 2026-09-24
       after the ward layer rendered N-S flipped against GEE LST tiles).
    1. Pull the gray boundary strokes (color ~0.431, width 0.48) — the ward
       boundary class — as line segments in PDF points.
    2. Snap endpoints into a planar graph, polygonize with shapely -> faces.
    3. Union of faces = 2005 city outline; individual faces = wards.
    4. Assign ward numbers: 123 PDF numeric labels -> nearest face (greedy,
       one label per face); verify 1:1.
    5. Georeference: similarity fit (scale/rotation/translation, Umeyama +
       ICP refinement) of the PDF outline onto nagpur_city.geojson in
       EPSG:32644 meters; report RMS residual.
    6. Zone names: same extraction on the prabhag panel (10 zones labeled),
       fit prabhag outline -> ward outline in PDF space, spatial-join
       ward -> prabhag -> zone. Best effort; zone=null on failure.

Output:
    backend/config/aoi/nagpur_wards.geojson (EPSG:4326, one feature/ward,
    properties: ward_no, zone, source) + validation report on stdout.

Run:  .venv/bin/python -m backend.etl.wards_from_pdf
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pymupdf
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import MultiLineString, MultiPolygon, Point, Polygon, mapping
from shapely.ops import transform as shp_transform, polygonize, unary_union
from shapely.validation import make_valid

from backend.config.settings import load_nagpur_aoi

PDF_PATH = Path(
    __file__).resolve().parents[2] / "data" / "raw" / "504887890-Nagpur-WARD-Map.pdf"
if not PDF_PATH.exists():  # fallback: original download location
    PDF_PATH = Path.home() / "Downloads" / "504887890-Nagpur-WARD-Map.pdf"
OUT_PATH = Path(__file__).resolve().parents[1] / "config" / "aoi" / "nagpur_wards.geojson"

# Panel frames (black 0.96 strokes found by inspection):
WARD_FRAME = pymupdf.Rect(463.0, 290.4, 800.5, 517.2)     # wards, 123 labels
PRABHAG_FRAME = pymupdf.Rect(466.1, 67.4, 803.1, 283.9)   # prabhags, 45 labels
BOUNDARY_COLOR = 0.431
BOUNDARY_WIDTH = 0.48
SNAP_TOL = 0.35          # PDF points
UTM = "EPSG:32644"       # UTM 44N — Nagpur


# --------------------------------------------------------------------------
# 1. Extraction
# --------------------------------------------------------------------------
def _to_map_space(frame: pymupdf.Rect, y: float) -> float:
    """PDF y (down) -> map-space y (up), reflected across the frame midline.

    ROOT-CAUSE FIX (2026-09-24): the source PDF's map content is authored
    VERTICALLY MIRRORED — the map block was drawn with an inverted y-axis,
    so north prints where south belongs (zone-label compass check:
    Laxmi Nagar/N sits at the panel bottom, Aasi Nagar/S at the top, while
    E-W stays correct → vertical mirror, not a rotation). Verified three
    ways: extracted linework matches the PDF's own raster rendering 99.2%
    as-is (so pymupdf reports author space faithfully), page.rotation == 0,
    and a det=-1 fit of the outline to the AOI scores IoU 0.927 at 0° vs
    0.847 for the best rotation-only fit. Mirroring at ingest — segments
    AND labels, same frame midline — keeps them mutually consistent and
    fixes every downstream use; no downstream flip would survive a new pull.
    """
    return frame.y0 + frame.y1 - y


def extract_segments(frame: pymupdf.Rect) -> list[tuple[float, float, float, float]]:
    """Gray boundary strokes inside `frame` -> (x1, y1, x2, y2) segments.

    Returned in MAP SPACE (y-up) — see _to_map_space for why the mirror is
    applied here and not downstream.
    """
    doc = pymupdf.open(PDF_PATH)
    page = doc[0]
    segs: list[tuple[float, float, float, float]] = []
    for d in page.get_drawings():
        col, wid = d.get("color"), d.get("width")
        if col is None or wid is None:
            continue
        if abs(col[0] - BOUNDARY_COLOR) > 0.02 or col[0] != col[1] or col[1] != col[2]:
            continue
        if abs(wid - BOUNDARY_WIDTH) > 0.01:
            continue
        if not frame.contains(d["rect"]):
            continue
        for item in d["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                segs.append((p1.x, _to_map_space(frame, p1.y),
                             p2.x, _to_map_space(frame, p2.y)))
    return segs


def extract_numeric_labels(frame: pymupdf.Rect,
                           margin: float = 8.0) -> dict[int, tuple[float, float]]:
    """Numeric text labels near `frame` -> {number: (x, y) anchor}.

    A small margin catches edge labels whose bbox sits just outside the
    boundary frame (ward numbers hug the border on the original map).

    Anchors are returned in MAP SPACE (y-up), matching extract_segments —
    the mirror must hit text and geometry alike or label→face assignment
    would pair each number with its mirrored twin's polygon."""
    doc = pymupdf.open(PDF_PATH)
    page = doc[0]
    labels: dict[int, tuple[float, float]] = {}
    for w in page.get_text("words"):
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (frame.x0 - margin <= cx <= frame.x1 + margin
                and frame.y0 - margin <= cy <= frame.y1 + margin):
            continue
        if text.isdigit():
            labels.setdefault(int(text), (cx, _to_map_space(frame, cy)))
    return labels


# --------------------------------------------------------------------------
# 2. Snap + polygonize
# --------------------------------------------------------------------------
def snap_segments(segs, tol: float = SNAP_TOL) -> list[tuple[float, float, float, float]]:
    """Cluster coincident endpoints (union-find over a spatial hash) and
    replace each endpoint with its cluster mean -> closed linework."""
    pts: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in segs:
        pts.append((x1, y1))
        pts.append((x2, y2))

    parent = list(range(len(pts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    cell = tol
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (x, y) in enumerate(pts):
        grid[(int(x // cell), int(y // cell))].append(idx)
    for idx, (x, y) in enumerate(pts):
        cx, cy = int(x // cell), int(y // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((cx + dx, cy + dy), ()):
                    if other > idx:
                        ox, oy = pts[other]
                        if math.hypot(x - ox, y - oy) <= SNAP_TOL:
                            union(idx, other)

    groups: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(pts)):
        groups[find(idx)].append(idx)
    rep = {root: (float(np.mean([pts[i][0] for i in m])),
                  float(np.mean([pts[i][1] for i in m])))
           for root, m in groups.items()}

    out = []
    for k, (x1, y1, x2, y2) in enumerate(segs):
        n1 = rep[find(2 * k)]
        n2 = rep[find(2 * k + 1)]
        if n1 != n2:  # drop degenerate self-loops
            out.append((n1[0], n1[1], n2[0], n2[1]))
    return out


def polygonize_faces(segs) -> tuple[list[Polygon], MultiLineString]:
    """Faces from snapped segments. unary_union FIRST: it nodes the linework
    (splits segments wherever they cross/touch) — polygonize cannot form
    rings from unnoded lines."""
    raw = MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in segs])
    noded = unary_union(raw)
    faces = [make_valid(g) for g in polygonize(noded)]
    faces = [p for p in faces if isinstance(p, Polygon) and p.area > 1.0]
    return faces, noded


# --------------------------------------------------------------------------
# 3. Label -> face assignment (greedy 1:1)
# --------------------------------------------------------------------------
def assign_labels(faces: list[Polygon], labels: dict[int, tuple[float, float]]):
    pairs = []
    for no, (lx, ly) in labels.items():
        pt = Point(lx, ly)
        for fi, face in enumerate(faces):
            d = face.distance(pt)
            pairs.append((d, no, fi))
    pairs.sort()
    ward_of_face: dict[int, int] = {}
    face_of_ward: dict[int, int] = {}
    for d, no, fi in pairs:
        if no in face_of_ward or fi in ward_of_face:
            continue
        face_of_ward[no] = fi
        ward_of_face[fi] = no
    return face_of_ward, ward_of_face


# --------------------------------------------------------------------------
# 4. Similarity fit (Umeyama) + ICP refinement
# --------------------------------------------------------------------------
def umeyama(src: np.ndarray, dst: np.ndarray):
    """Least-squares similarity (s, R, t): dst ~ s * R @ src + t."""
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    sc, dc = src - mu_s, dst - mu_d
    cov = dc.T @ sc / len(src)
    U, S, Vt = np.linalg.svd(cov)
    R = U @ Vt
    if np.linalg.det(R) < 0:  # avoid reflection
        U[:, -1] *= -1
        R = U @ Vt
    var_s = (sc ** 2).sum() / len(src)
    s = float(S.sum()) / var_s if var_s > 0 else 1.0  # trace(diag(S)) == S.sum()
    t = mu_d - s * R @ mu_s
    return s, R, t


def apply_sim(pts: np.ndarray, s, R, t) -> np.ndarray:
    return (s * (R @ pts.T).T + t)


def fit_by_iou(src_poly: Polygon, dst_poly: Polygon):
    """Fit similarity (s, R, t) maximizing polygon overlap (IoU).

    Robust to outline differences between the 2005 NMC limit and the OSM
    polygon: scale from the area ratio, centroid alignment, then a rotation
    grid search. Returns (params, iou) — placement is optimal even when the
    two outlines genuinely differ.
    """
    src_c = np.asarray(src_poly.centroid.coords[0])
    dst_c = np.asarray(dst_poly.centroid.coords[0])
    s0 = math.sqrt(dst_poly.area / src_poly.area)
    coords = np.asarray(src_poly.exterior.coords)

    def iou_at(rot_deg: float, s: float) -> float:
        a = math.radians(rot_deg)
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        t = dst_c - s * R @ src_c
        moved = shp_transform(lambda x, y, z=None: tuple(apply_sim(
            np.column_stack([np.atleast_1d(x), np.atleast_1d(y)]), s, R, t).T),
            src_poly)
        return moved.intersection(dst_poly).area / moved.union(dst_poly).area

    best_rot, best_iou = 0.0, iou_at(0.0, s0)
    for rot in np.arange(-10, 10.01, 0.5):  # coarse sweep
        v = iou_at(float(rot), s0)
        if v > best_iou:
            best_rot, best_iou = float(rot), v
    for rot in np.arange(best_rot - 0.5, best_rot + 0.51, 0.1):  # refine
        v = iou_at(float(rot), s0)
        if v > best_iou:
            best_rot, best_iou = float(rot), v

    # small scale refinement around the area-ratio estimate
    best_s = s0
    for s in s0 * np.array([0.97, 0.985, 1.0, 1.015, 1.03]):
        v = iou_at(best_rot, float(s))
        if v > best_iou:
            best_s, best_iou = float(s), v

    a = math.radians(best_rot)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    t = dst_c - best_s * R @ src_c
    return (best_s, R, t), best_iou


def densify(coords, step: float) -> np.ndarray:
    """Densely sample along a closed ring (step in the same units)."""
    pts = []
    for i in range(len(coords) - 1):
        (x1, y1), (x2, y2) = coords[i], coords[i + 1]
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
        for t in np.linspace(0, 1, n, endpoint=False):
            pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    return np.asarray(pts)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    # --- wards panel -------------------------------------------------------
    faces: list[Polygon] = []
    segs: list = []
    for tol in (0.35, 0.7, 1.2):  # ladder: stop as soon as linework closes
        segs = snap_segments(extract_segments(WARD_FRAME), tol)
        faces, _ = polygonize_faces(segs)
        print(f"ward panel: tol={tol}pt -> {len(segs)} segments, {len(faces)} faces")
        if len(faces) >= 100:
            break

    labels = extract_numeric_labels(WARD_FRAME)
    print(f"ward panel: {len(labels)} numeric labels")
    face_of_ward, ward_of_face = assign_labels(faces, labels)
    matched = len(face_of_ward)
    print(f"label->face assignment: {matched} 1:1 matches "
          f"({len(labels) - matched} labels unmatched, "
          f"{len(faces) - len(ward_of_face)} faces unlabeled)")

    # city outline = union of ALL faces — the numberless peripheral wards
    # are part of the 2005 city; fitting labeled-only shrank the fit target
    # and inflated RMS (~2 km). Slivers still excluded by area filter.
    outline_pdf = unary_union(faces)
    outline_pts_pdf = densify(
        list(outline_pdf.exterior.coords) if isinstance(outline_pdf, Polygon)
        else [c for g in outline_pdf.geoms for c in g.exterior.coords], 2.0)

    # --- AOI in UTM ---------------------------------------------------------
    to_utm = Transformer.from_crs("EPSG:4326", UTM, always_xy=True).transform
    aoi = make_valid(shp_transform(to_utm, shape(load_nagpur_aoi()["geometry"])))
    aoi_pts = densify(list(aoi.exterior.coords)
                      if isinstance(aoi, Polygon)
                      else [c for g in aoi.geoms for c in g.exterior.coords], 50.0)

    (s, R, t), fit_iou = fit_by_iou(outline_pdf, aoi)
    moved_outline = shp_transform(
        lambda x, y, z=None: tuple(apply_sim(
            np.column_stack([np.atleast_1d(x), np.atleast_1d(y)]), s, R, t).T),
        outline_pdf)
    tree = cKDTree(aoi_pts)
    d, _ = tree.query(densify(list(moved_outline.exterior.coords)
                              if isinstance(moved_outline, Polygon)
                              else [c for g in moved_outline.geoms
                                    for c in g.exterior.coords], 50.0))
    rms = float(np.sqrt((d ** 2).mean()))
    print(f"georef: scale={s:.4f} rot={math.degrees(math.atan2(R[1, 0], R[0, 0])):.2f}deg "
          f"IoU={fit_iou:.3f} boundary-RMS={rms:.0f} m")

    to_pdf2utm = lambda xs, ys: apply_sim(np.column_stack([xs, ys]), s, R, t).T

    # --- build ward features -------------------------------------------------
    MIN_FACE_PT2 = 25.0  # ~0.3 km2 at map scale; drops polygonization slivers

    def georef_face(fi: int):
        geom = make_valid(shp_transform(
            lambda x, y, z=None: to_pdf2utm(x, y), faces[fi]))
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)  # drop slivers
        return geom

    wards = []
    for no, fi in face_of_ward.items():
        if faces[fi].area >= MIN_FACE_PT2:
            wards.append((no, georef_face(fi)))
    # 22 ward numbers are not printed anywhere on the source map; their
    # polygons exist as unlabeled faces, so keep them (ward_no=null) for
    # full city coverage instead of punching holes in the layer.
    n_unlabeled = 0
    for fi in range(len(faces)):
        if fi not in ward_of_face and faces[fi].area >= MIN_FACE_PT2:
            wards.append((None, georef_face(fi)))
            n_unlabeled += 1
    print(f"wards georeferenced: {len(wards)} = {matched} numbered "
          f"+ {n_unlabeled} with ward_no=null (numbers never printed on map)")

    # --- zones (prabhag panel): DEFERRED — best-effort metadata, planned
    # as a follow-up; ward_no is sufficient for the zonal analysis.
    zone_of_ward: dict[int, str | None] = {no: None for no, _ in wards}

    # --- validation -----------------------------------------------------------
    union_wards = unary_union([g for _, g in wards])
    inter = union_wards.intersection(aoi)
    print(f"ward-union vs AOI: overlap {inter.area / aoi.area * 100:.1f}% of AOI, "
          f"wards outside AOI {max(0.0, 1 - inter.area / union_wards.area) * 100:.1f}%")
    areas = [g.area for _, g in wards]
    print(f"ward areas: min={min(areas)/1e6:.2f} med={sorted(areas)[len(areas)//2]/1e6:.2f} "
          f"max={max(areas)/1e6:.2f} km2, sum={sum(areas)/1e6:.1f} km2 "
          f"(AOI {aoi.area/1e6:.1f} km2)")

    # --- write GeoJSON ---------------------------------------------------------
    to_wgs = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True).transform
    feats = []
    for no, geom in sorted(wards, key=lambda w: (w[0] is None, w[0] or 0)):
        wgs = shp_transform(to_wgs, geom)
        feats.append({
            "type": "Feature",
            "properties": {
                "ward_no": no,
                "zone": zone_of_ward.get(no),
                "source": "MRSAC CIS-2005 ward map (vector PDF), "
                          "georeferenced to OSM city polygon",
            },
            "geometry": mapping(wgs),
        })
    fc = {"type": "FeatureCollection",
          "name": "nagpur_wards_cis2005",
          "georef": {
              "fit_target": "OSM Nagpur Urban Taluka polygon (current limit)",
              "source_limit": "2005 NMC city limit (MRSAC CIS-2005 sheet)",
              "rms_m": round(rms),
              "iou": round(fit_iou, 3),
              "note": "Residual RMS (~170 m) reflects 2005 NMC vs current "
                      "OSM boundary drift; fine for ward-mean LST on 30 m "
                      "pixels. Source was mirrored at ingest (see "
                      "_to_map_space); fixed 2026-09-24 (see PLAN.md).",
          },
          "features": feats}
    OUT_PATH.write_text(json.dumps(fc))
    print(f"wrote {OUT_PATH} ({len(feats)} features)")


def shape(geojson_geom: dict):
    from shapely.geometry import shape as _shape
    return _shape(geojson_geom)


if __name__ == "__main__":
    main()
