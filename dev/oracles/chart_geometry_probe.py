#!/usr/bin/env python3
"""Measure scripts/chart_geometry.py against LibreOffice renders.

    python3 -I oracles/chart_geometry_probe.py OUT_DIR [--width 1600]

Writes one page per chart configuration through emit_pptx.write_chart (the emitter the
build uses: manual inner plot layout, explicit axis min and max, cross_between), twice:
A, the charts alone; B, the same pages with 1 px magenta marker shapes at every
position chart_geometry predicts (bar edges and value ends, point centres, gridline
values) drawn through the emitter's rect writer, the one annotations use. Both decks are rendered
with scripts/render.py. From A every drawn mark is located in the PNG by its own
colour, with sub-pixel edges from the anti-aliased coverage across the edge; from B
every marker is located the same way. The report prints, per configuration and per
measured feature, the predicted pixel, the marker's measured pixel and the mark's
measured pixel, and the worst offsets. A table page measures cell edges from the
fitted column widths and row heights the same way.

Needs no deckgen checkout. Nothing here is a unit test: it is the measurement the
annotation layer's tolerance is quoted from (PORT_AUDIT.md).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pptx import Presentation
from pptx.util import Emu

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "designing-presentations" / "skills" / "designing-presentations"
sys.path.insert(0, str(SKILL / "scripts"))
import emit_pptx as E  # noqa: E402
from chart_geometry import ChartGeometry  # noqa: E402

PAGE_W, PAGE_H = 9_144_000, 6_858_000
COLOURS = {"color.s0": "E00000", "color.s1": "00A000", "color.s2": "0000E0", "color.grid": "00B0B0", "color.axis": "808080",
           "color.ink": "000000", "color.surface": "FFFFFF", "color.marker": "FF00FF", "color.band_a": "F0C000", "color.band_b": "6040C0"}
GUIDE = {
    "color": {"roles": {k: {"hex": v} for k, v in COLOURS.items()}},
    "typography": {"families": {"major": "Arial", "minor": "Arial"},
                   "roles": {"type.axis_label": {"size_pt": 10, "family": "minor"}, "type.table_cell": {"size_pt": 10, "family": "minor"},
                             "type.table_header": {"size_pt": 10, "family": "minor"}}},
    "spacing": {"steps": {"space.xs": {"emu": 45720}}},
    "tables": {},
}
BOX = (457_200, 457_200, 8_229_600, 5_943_600)
PLOT = {"x": 0.11, "y": 0.06, "w": 0.84, "h": 0.8}
TEXT = {"role": "type.axis_label", "ink_role": "color.ink"}
CATS5 = ["Alpha", "Beta", "Gamma", "Delta", "Eps"]


def axes(cat=None, val=None, *, lo=0, hi=100, unit=20, cross="between", reverse_val=False):
    a = {"category": {"visible": True, "line_role": "color.axis", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none",
                      "labels": {"show": True, **TEXT}, **(cat or {})},
         "value": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": reverse_val, "min": lo, "max": hi, "major_unit": unit,
                   "number_format": "0", "gridlines": {"line_role": "color.grid", "line_width_pt": 0.75}, "labels": {"show": True, **TEXT}, **(val or {})}}
    if cross is not None:
        a["value"]["cross_between"] = cross
    return a


def series(n, values, *, line=False, marker=None):
    s = {"name": f"S{n}", "values": values, "labels": {"show": False}}
    if line:
        s.update({"line_role": "none", "smooth": False, "marker": marker or {"style": "square", "size": 7, "fill_role": f"color.s{n}", "line_role": "none"}})
    else:
        s.update({"fill_role": f"color.s{n}", "line_role": "none"})
    return s


CONFIGS = [
    ("column, 1 series, gap 80", {"type": "COLUMN_CLUSTERED", "categories": CATS5, "series": [series(0, [35, 62, 48, 90, 20])], "gap_width": 80, "overlap": 0, "axes": axes()}),
    ("column, 3 series, gap 50, overlap -20", {"type": "COLUMN_CLUSTERED", "categories": CATS5[:4],
     "series": [series(0, [30, 55, 70, 40]), series(1, [45, 25, 60, 85]), series(2, [65, 40, 35, 50])], "gap_width": 50, "overlap": -20, "axes": axes()}),
    ("column, 2 series, gap 120, overlap 30, axis 20..80", {"type": "COLUMN_CLUSTERED", "categories": CATS5[:4],
     "series": [series(0, [30, 55, 70, 40]), series(1, [45, 35, 60, 75])], "gap_width": 120, "overlap": 30, "axes": axes(lo=20, hi=80, unit=10)}),
    ("column, value axis reversed", {"type": "COLUMN_CLUSTERED", "categories": CATS5, "series": [series(0, [35, 62, 48, 90, 20])], "gap_width": 60, "overlap": 0,
     "axes": axes(reverse_val=True)}),
    ("stacked column, 3 series, gap 60", {"type": "COLUMN_STACKED", "categories": CATS5[:4],
     "series": [series(0, [20, 30, 15, 25]), series(1, [25, 20, 35, 30]), series(2, [30, 15, 25, 35])], "gap_width": 60, "overlap": 100, "axes": axes()}),
    ("100% stacked column, 3 series", {"type": "COLUMN_STACKED_100", "categories": CATS5[:4],
     "series": [series(0, [20, 30, 15, 25]), series(1, [25, 20, 35, 30]), series(2, [30, 15, 25, 35])], "gap_width": 60, "overlap": 100,
     "axes": axes(lo=0, hi=1, unit=0.2, val={"number_format": "0%"})}),
    ("horizontal bar, 2 series, categories reversed", {"type": "BAR_CLUSTERED", "categories": CATS5,
     "series": [series(0, [35, 62, 48, 90, 20]), series(1, [55, 40, 70, 30, 65])], "gap_width": 70, "overlap": 0,
     "axes": axes(cat={"reverse": True})}),
    ("horizontal bar, value axis deleted (visible false), categories reversed", {"type": "BAR_CLUSTERED", "categories": CATS5,
     "series": [series(0, [35, 62, 48, 90, 20])], "gap_width": 45, "overlap": 0,
     "axes": axes(cat={"reverse": True}, lo=10, hi=140, val={"visible": False})}),
    ("horizontal stacked bar, 2 series, gap 40", {"type": "BAR_STACKED", "categories": CATS5,
     "series": [series(0, [35, 22, 48, 30, 20]), series(1, [25, 40, 30, 45, 35])], "gap_width": 40, "overlap": 100, "axes": axes()}),
    ("column, legend and title drawn (inner layout ignores both)", {"type": "COLUMN_CLUSTERED", "categories": CATS5[:3],
     "series": [series(0, [35, 62, 48]), series(1, [55, 40, 70])], "gap_width": 100, "overlap": 0, "axes": axes(lo=0, hi=80, unit=20),
     "legend": {"position": "t", "role": "type.axis_label", "ink_role": "color.ink"}, "title": {"text": "A title the renderer must place", "role": "type.axis_label", "ink_role": "color.ink"}}),
    ("line, between", {"type": "LINE_MARKERS", "categories": CATS5, "series": [series(0, [35, 62, 48, 90, 20], line=True), series(1, [55, 30, 70, 60, 80], line=True)],
     "axes": axes()}),
    ("line, midpoint", {"type": "LINE_MARKERS", "categories": CATS5, "series": [series(0, [35, 62, 48, 90, 20], line=True), series(1, [55, 30, 70, 60, 80], line=True)],
     "axes": axes(cross="midpoint")}),
    ("combo: 2 clustered columns and a line on one axis", {"type": "COLUMN_CLUSTERED", "categories": CATS5[:4],
     "series": [series(0, [30, 55, 70, 40]), series(1, [45, 25, 60, 85]), {**series(2, [50, 65, 35, 75], line=True), "plot_type": "LINE_MARKERS"}],
     "gap_width": 80, "overlap": 0, "axes": axes()}),
    ("combo: line on the primary axis 0..100, columns on a secondary axis 0..40", {"type": "LINE_MARKERS", "categories": CATS5,
     "series": [{**series(0, [12, 30, 8, 36, 20]), "plot_type": "COLUMN_CLUSTERED", "axis": "secondary"}, series(1, [35, 62, 48, 90, 20], line=True)],
     "gap_width": 60, "overlap": 0,
     "axes": {**axes(), "secondary_value": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": False, "min": 0, "max": 40, "major_unit": 10,
                                             "number_format": "0", "gridlines": "none", "labels": {"show": True, **TEXT}, "cross_between": "between"}}}),
    ("XY scatter, 2 series", {"type": "XY_SCATTER", "series": [series(0, [[1.5, 20], [3.2, 65], [6.8, 40], [8.5, 85]], line=True),
                                                                series(1, [[2.4, 75], [5.0, 30], [7.4, 55]], line=True)],
     "axes": {"category": {"visible": True, "line_role": "color.axis", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "min": 0, "max": 10, "major_unit": 2,
                           "number_format": "0", "gridlines": {"line_role": "color.grid", "line_width_pt": 0.75}, "labels": {"show": True, **TEXT}},
              "value": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": False, "min": 0, "max": 100, "major_unit": 20, "number_format": "0",
                        "gridlines": {"line_role": "color.grid", "line_width_pt": 0.75}, "labels": {"show": True, **TEXT}}}}),
]


def chart_el(i: int, spec: dict) -> dict:
    return {"id": f"probe{i}", "kind": "chart", "box": list(BOX), "plot_area": PLOT, "text": TEXT, "plot_fill_role": "none", "number_format": "0", "legend": "none", "title": "none", **spec}


TABLE = {"id": "tbl", "kind": "table", "box": [914_400, 914_400, 7_315_200, 0], "header_rows": 1,
         "columns": [{"key": f"c{i}", "label": f"H{i}", "value_kind": "text"} for i in range(5)],
         "rows": [[f"r{r}c{c}" for c in range(5)] for r in range(6)],
         "column_widths_emu": [2_286_000, 1_143_000, 1_371_600, 1_600_200, 914_400], "row_heights_emu": [457_200, 320_040, 548_640, 365_760, 411_480, 320_040, 594_360],
         "header_role": "type.table_header", "cell_role": "type.table_cell", "fit_cell": {"sz": 1000, "b": False, "lnSpc_spcPts": 1200, "spcBef": 0, "spcAft": 0, "spc": 0}, "fit_header": {"sz": 1000, "b": False, "lnSpc_spcPts": 1200, "spcBef": 0, "spcAft": 0, "spc": 0}, "fit_padding_emu": 45_720,
         "header_fill_role": "none", "data_fill_role": "none", "banding_role": "none"}
TABLE["box"][3] = sum(TABLE["row_heights_emu"])


def features(geo: ChartGeometry) -> list[dict]:
    """Every predicted feature: kind, colour role it is drawn in, page EMU position, and
    the axis it is measured across."""
    out = []
    el = geo.el
    for j, s in enumerate(el["series"]):
        if geo.series_family(j) in ("bar", "bar_stacked"):
            axis = geo.series_axis(j)
            for i in range(len(el["categories"])):
                x, y, w, h = geo.bar_rect(j, i)
                where = f"S{j} {el['categories'][i]}"
                v0, v1 = geo.bar_values(j, i)
                base_is_axis = v0 == geo.crossing_value(axis)
                if geo.plot.horizontal_bars:
                    out += [{"what": f"{where} top edge", "role": s["fill_role"], "axis": "y", "emu": y, "rect": (x, y, w, h), "side": "low"},
                            {"what": f"{where} bottom edge", "role": s["fill_role"], "axis": "y", "emu": y + h, "rect": (x, y, w, h), "side": "high"}]
                    end_right = geo.value_coord(v1, axis)[1] >= geo.value_coord(v0, axis)[1]
                    out.append({"what": f"{where} value end", "role": s["fill_role"], "axis": "x", "emu": x + w if end_right else x, "rect": (x, y, w, h), "side": "high" if end_right else "low"})
                    if not base_is_axis:
                        out.append({"what": f"{where} value start", "role": s["fill_role"], "axis": "x", "emu": x if end_right else x + w, "rect": (x, y, w, h), "side": "low" if end_right else "high"})
                else:
                    out += [{"what": f"{where} left edge", "role": s["fill_role"], "axis": "x", "emu": x, "rect": (x, y, w, h), "side": "low"},
                            {"what": f"{where} right edge", "role": s["fill_role"], "axis": "x", "emu": x + w, "rect": (x, y, w, h), "side": "high"}]
                    end_top = geo.value_coord(v1, axis)[1] <= geo.value_coord(v0, axis)[1]
                    out.append({"what": f"{where} value end", "role": s["fill_role"], "axis": "y", "emu": y if end_top else y + h, "rect": (x, y, w, h), "side": "low" if end_top else "high"})
                    if not base_is_axis:
                        out.append({"what": f"{where} value start", "role": s["fill_role"], "axis": "y", "emu": y + h if end_top else y, "rect": (x, y, w, h), "side": "high" if end_top else "low"})
        else:
            n = len(s["values"]) if geo.family == "xy" else len(el["categories"])
            for i in range(n):
                px, py = geo.point(j, i)
                out.append({"what": f"S{j} point {i}", "role": s["marker"]["fill_role"], "axis": "xy", "emu": (px, py)})
    if el["axes"]["value"].get("visible") is False:
        return out
    lo, hi = geo.scale("value")
    unit = el["axes"]["value"]["major_unit"]
    v = lo
    while v <= hi + 1e-9:
        ax, c = geo.value_coord(v)
        if geo.family != "xy" and abs(v - geo.crossing_value()) < 1e-9:
            # the category axis line is drawn here, over the gridline
            out.append({"what": f"category axis line at {round(v, 6):g}", "role": "color.axis", "axis": ax, "emu": c, "gridline": True})
        else:
            out.append({"what": f"value {round(v, 6):g} gridline", "role": "color.grid", "axis": ax, "emu": c, "gridline": True})
        v += unit
    return out


def px(emu: float, width_px: int) -> float:
    return emu * width_px / PAGE_W


def _rgb(hex_: str) -> np.ndarray:
    return np.array([int(hex_[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def coverage(profile: np.ndarray, colour: np.ndarray) -> np.ndarray:
    """Share of `colour` in each pixel of a 1-D profile of RGB pixels, against the colour
    at the profile's far end from the colour (the ground the edge is drawn on)."""
    d0 = np.linalg.norm(profile[0] - colour)
    d1 = np.linalg.norm(profile[-1] - colour)
    ground = profile[0] if d0 > d1 else profile[-1]
    axis = colour - ground
    denom = float(axis @ axis)
    if denom < 400:
        return np.full(len(profile), np.nan)
    return np.clip((profile - ground) @ axis / denom, 0, 1)


def edge_px(img: np.ndarray, feat: dict, width_px: int, colour: np.ndarray) -> float | None:
    """Sub-pixel position of a filled mark's edge: the coverage profile across the edge,
    averaged over the middle half of the edge's length; the edge sits where the coverage
    integral says the colour starts (pixel i covers [i, i + 1))."""
    x, y, w, h = (px(v, width_px) for v in feat["rect"])
    c = px(feat["emu"], width_px)
    win = 7
    if feat["axis"] == "x":
        rows = range(int(y + h * 0.3), int(y + h * 0.7) + 1)
        lo, hi = int(c) - win, int(c) + win + 1
        prof = img[rows.start:rows.stop, lo:hi].mean(axis=0)
    else:
        cols = range(int(x + w * 0.3), int(x + w * 0.7) + 1)
        lo, hi = int(c) - win, int(c) + win + 1
        prof = img[lo:hi, cols.start:cols.stop].mean(axis=1)
    a = coverage(prof, colour)
    if np.isnan(a).any():
        return None
    inside_high = feat["side"] == "low"  # the mark lies after a low edge, before a high edge
    if inside_high:
        full = next((k for k in range(len(a)) if a[k] > 0.97), None)
        if full is None:
            return None
        return lo + full - float(a[:full].sum())
    full = next((k for k in range(len(a) - 1, -1, -1) if a[k] > 0.97), None)
    if full is None:
        return None
    return lo + full + 1 + float(a[full + 1:].sum())


def line_px(img: np.ndarray, centre: float, axis: str, span: tuple[float, float], colour: np.ndarray) -> float | None:
    """Centre of a thin line (a gridline, a marker) across `axis` near `centre`: the
    coverage-weighted mean pixel centre, sampled along `span` of the other axis."""
    win = 6
    lo, hi = int(centre) - win, int(centre) + win + 1
    a0, a1 = int(span[0]), int(span[1]) + 1
    if a1 - a0 < 1:
        return None
    prof = img[lo:hi, a0:a1].mean(axis=1) if axis == "y" else img[a0:a1, lo:hi].mean(axis=0)
    a = coverage(prof, colour)
    if np.isnan(a).any() or a.sum() < 0.2:
        return None
    return lo + float((a * (np.arange(len(a)) + 0.5)).sum() / a.sum())


def diff_px(img_a: np.ndarray, img_b: np.ndarray, centre: float, axis: str, span: tuple[float, float]) -> float | None:
    """Centre of a marker stroke: the marker is the only thing B draws that A does not,
    so the per-pixel difference B - A is the marker's coverage whatever lies under it."""
    win = 6
    lo, hi = int(centre) - win, int(centre) + win + 1
    a0, a1 = int(span[0]), int(span[1]) + 1
    if a1 - a0 < 1:
        return None
    d = np.abs(img_b - img_a).sum(axis=2)
    prof = d[lo:hi, a0:a1].mean(axis=1) if axis == "y" else d[a0:a1, lo:hi].mean(axis=0)
    if prof.sum() < 20:
        return None
    return lo + float((prof * (np.arange(len(prof)) + 0.5)).sum() / prof.sum())


def blob_px(img: np.ndarray, centre: tuple[float, float], colour: np.ndarray, win: int = 14) -> tuple[float, float] | None:
    cx, cy = int(centre[0]), int(centre[1])
    patch = img[cy - win:cy + win + 1, cx - win:cx + win + 1]
    ground = _rgb("FFFFFF")
    axis = colour - ground
    a = np.clip((patch - ground) @ axis / float(axis @ axis), 0, 1)
    resid = np.linalg.norm(patch - (ground + a[..., None] * axis), axis=2)
    a = np.where(resid < 60, a, 0)
    if a.sum() < 1:
        return None
    ys, xs = np.mgrid[0:patch.shape[0], 0:patch.shape[1]]
    return cx - win + float((a * (xs + 0.5)).sum() / a.sum()), cy - win + float((a * (ys + 0.5)).sum() / a.sum())


def marker_shapes(feat: dict, width_px: int) -> list[dict]:
    """1 px marker strokes at a predicted position, offset from the mark so they do not
    hide the edge they mark: an edge marker runs past the mark's end, a point marker is a
    cross whose arms stop short of the point."""
    one = PAGE_W / width_px  # one pixel in EMU
    if feat["axis"] == "xy":
        x, y = feat["emu"]
        return [{"kind": "hline", "at": y, "from": x - 30 * one, "to": x - 12 * one}, {"kind": "vline", "at": x, "from": y + 12 * one, "to": y + 30 * one}]
    if feat.get("gridline"):
        # beside the plot, where nothing else is drawn
        p = PLOT
        if feat["axis"] == "y":
            right = BOX[0] + (p["x"] + p["w"]) * BOX[2]
            return [{"kind": "hline", "at": feat["emu"], "from": right + 4 * one, "to": right + 20 * one}]
        top = BOX[1] + p["y"] * BOX[3]
        return [{"kind": "vline", "at": feat["emu"], "from": top - 20 * one, "to": top - 4 * one}]
    x, y, w, h = feat["rect"]
    if feat["axis"] == "x":
        return [{"kind": "vline", "at": feat["emu"], "from": y - 18 * one, "to": y - 3 * one}] if h > 0 else []
    return [{"kind": "hline", "at": feat["emu"], "from": x + w + 3 * one, "to": x + w + 18 * one}]


def draw_markers(slide, marks: list[dict], width_px: int) -> None:
    one = PAGE_W / width_px
    for m in marks:
        if m["kind"] == "vline":
            box = (round(m["at"] - one / 2), round(m["from"]), round(one), round(m["to"] - m["from"]))
        else:
            box = (round(m["from"]), round(m["at"] - one / 2), round(m["to"] - m["from"]), round(one))
        E.write_rect(slide, {"id": "probe-marker", "fill_role": "color.marker", "line_role": None}, E.Guide(GUIDE), box)


def build(out: Path, with_markers: bool, width_px: int) -> tuple[Path, list[list[dict]]]:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(PAGE_W), Emu(PAGE_H)
    guide = E.Guide(GUIDE)
    feats_all = []
    for i, (_, spec) in enumerate(CONFIGS):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        el = chart_el(i, spec)
        E.write_chart(slide, el, guide, BOX)
        feats = features(ChartGeometry(el, BOX))
        feats_all.append(feats)
        if with_markers:
            draw_markers(slide, [m for f in feats for m in marker_shapes(f, width_px)], width_px)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    E.write_table(slide, TABLE, guide, tuple(TABLE["box"]))
    shape = slide.shapes[-1]
    for ri, row in enumerate(shape.table.rows):
        for ci in range(5):
            tc_pr = row.cells[ci]._tc.get_or_add_tcPr()
            for child in list(tc_pr):
                if child.tag in (E.qn("a:solidFill"), E.qn("a:noFill")):
                    tc_pr.remove(child)
            fill = E.etree.SubElement(tc_pr, E.qn("a:solidFill"))
            E.etree.SubElement(fill, E.qn("a:srgbClr")).set("val", COLOURS["color.band_a"] if (ri + ci) % 2 == 0 else COLOURS["color.band_b"])
    path = out / ("probe-B.pptx" if with_markers else "probe-A.pptx")
    prs.save(path)
    return path, feats_all


def render(path: Path, width_px: int) -> list[Path]:
    rdir = path.with_suffix("")
    done = subprocess.run([sys.executable, "-I", str(SKILL / "scripts" / "render.py"), str(path), "--out", str(rdir), "--width", str(width_px)],
                          capture_output=True, text=True, timeout=900, check=False)
    return [Path(p) for p in json.loads(done.stdout)["images"]]


def measure(images_a: list[Path], images_b: list[Path], feats_all: list[list[dict]], width_px: int) -> dict:
    report = {"width_px": width_px, "configs": []}
    for ci, ((name, _), feats) in enumerate(zip(CONFIGS, feats_all)):
        img_a = np.asarray(Image.open(images_a[ci]).convert("RGB"), dtype=float)
        img_b = np.asarray(Image.open(images_b[ci]).convert("RGB"), dtype=float)
        rows = []
        for f in feats:
            colour = _rgb(COLOURS[f["role"]])
            if f["axis"] == "xy":
                pred = (px(f["emu"][0], width_px), px(f["emu"][1], width_px))
                mark = blob_px(img_a, pred, colour)
                arms = marker_shapes(f, width_px)
                mx = diff_px(img_a, img_b, pred[0], "x", (px(arms[1]["from"], width_px) + 1, px(arms[1]["to"], width_px) - 1))
                my = diff_px(img_a, img_b, pred[1], "y", (px(arms[0]["from"], width_px) + 1, px(arms[0]["to"], width_px) - 1))
                for k, p_, m_, k_ in (("x", pred[0], mark[0] if mark else None, mx), ("y", pred[1], mark[1] if mark else None, my)):
                    rows.append({"what": f"{f['what']} {k}", "predicted": round(p_, 2), "mark": None if m_ is None else round(m_, 2), "marker": None if k_ is None else round(k_, 2)})
                continue
            pred = px(f["emu"], width_px)
            arms = marker_shapes(f, width_px)
            if f.get("gridline"):
                p = PLOT
                # sampled 3 to 8 px inside the plot's left (or top) edge: bars start half a
                # gap in, so no bar hides a gridline there on these configurations
                if f["axis"] == "y":
                    left = px(BOX[0] + p["x"] * BOX[2], width_px)
                    span = (left + 3, left + 8)
                else:
                    top = px(BOX[1] + p["y"] * BOX[3], width_px)
                    span = (top + 3, top + 8)
                mark = line_px(img_a, pred, f["axis"], span, colour)
            else:
                mark = edge_px(img_a, f, width_px, colour)
            marker = None
            if arms:
                a = arms[0]
                marker = diff_px(img_a, img_b, pred, "y" if a["kind"] == "hline" else "x", (px(a["from"], width_px) + 1, px(a["to"], width_px) - 1))
            rows.append({"what": f["what"], "predicted": round(pred, 2), "mark": None if mark is None else round(mark, 2), "marker": None if marker is None else round(marker, 2)})
        report["configs"].append({"name": name, "rows": rows, **summary(rows)})
    # the table: cell edges from the fitted widths and heights, located by the checkerboard
    img = np.asarray(Image.open(images_a[len(CONFIGS)]).convert("RGB"), dtype=float)
    rows = []
    x0, y0 = TABLE["box"][0], TABLE["box"][1]
    xs = np.cumsum([x0] + TABLE["column_widths_emu"])
    ys = np.cumsum([y0] + TABLE["row_heights_emu"])
    a_rgb, b_rgb = _rgb(COLOURS["color.band_a"]), _rgb(COLOURS["color.band_b"])
    for k in range(1, len(xs) - 1):
        f = {"axis": "x", "emu": xs[k], "rect": (xs[k - 1], ys[0], xs[k] - xs[k - 1], ys[1] - ys[0]), "side": "high"}
        rows.append({"what": f"column edge {k}", "predicted": round(px(xs[k], width_px), 2), "mark": _r(edge_px(img, f, width_px, a_rgb if (k - 1) % 2 == 0 else b_rgb)), "marker": None})
    for k in range(1, len(ys) - 1):
        f = {"axis": "y", "emu": ys[k], "rect": (xs[0], ys[k - 1], xs[1] - xs[0], ys[k] - ys[k - 1]), "side": "high"}
        rows.append({"what": f"row edge {k}", "predicted": round(px(ys[k], width_px), 2), "mark": _r(edge_px(img, f, width_px, a_rgb if (k - 1) % 2 == 0 else b_rgb)), "marker": None})
    report["configs"].append({"name": "table, fitted widths and heights", "rows": rows, **summary(rows)})
    return report


def _r(v):
    return None if v is None else round(v, 2)


def summary(rows: list[dict]) -> dict:
    mk = [abs(r["mark"] - r["predicted"]) for r in rows if r["mark"] is not None]
    mm = [abs(r["marker"] - r["predicted"]) for r in rows if r["marker"] is not None]
    off = [abs(r["mark"] - r["marker"]) for r in rows if r["mark"] is not None and r["marker"] is not None]
    unread = [r["what"] for r in rows if r["mark"] is None]
    return {"n": len(rows), "max_mark_vs_predicted_px": round(max(mk), 2) if mk else None, "max_marker_vs_predicted_px": round(max(mm), 2) if mm else None,
            "max_mark_vs_marker_px": round(max(off), 2) if off else None, "mean_mark_vs_predicted_px": round(sum(mk) / len(mk), 3) if mk else None, "unread": unread}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--rows", action="store_true", help="print every row, not only the summaries")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    a, feats = build(out, False, args.width)
    b, _ = build(out, True, args.width)
    report = measure(render(a, args.width), render(b, args.width), feats, args.width)
    (out / "probe.json").write_text(json.dumps(report, indent=1))
    for c in report["configs"]:
        print(f"{c['name']:<52} n={c['n']:<3} mark-pred max {c['max_mark_vs_predicted_px']} mean {c['mean_mark_vs_predicted_px']}  "
              f"marker-pred max {c['max_marker_vs_predicted_px']}  mark-marker max {c['max_mark_vs_marker_px']}  unread {len(c['unread'])}")
        if args.rows:
            for r in c["rows"]:
                print(f"    {r['what']:<34} pred {r['predicted']:>8}  mark {r['mark']}  marker {r['marker']}")
    allm = [abs(r["mark"] - r["predicted"]) for c in report["configs"] for r in c["rows"] if r["mark"] is not None]
    unread = [f"{c['name']}: {w}" for c in report["configs"] for w in c["unread"]]
    print(f"ALL: {len(allm)} features read, max |mark - predicted| {max(allm):.2f} px, mean {sum(allm) / len(allm):.3f} px at {args.width} px wide; "
          f"{len(unread)} not found within 7 px of the prediction (occluded by a later series, or misplaced)")
    for u in unread:
        print(f"    not found: {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
