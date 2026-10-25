#!/usr/bin/env python3
"""Where a chart's data lands on the page, in EMU, from the spec alone.

The one definition of chart data coordinates. The annotation layer anchors to it, the
build's label-break check sizes bars with it, and oracles/chart_geometry_probe.py
measures it against LibreOffice renders. Nothing here reads a renderer.

The chart must be written with a fixed inner plot rectangle (`plot_area`, x, y, w, h
as fractions of the chart frame, emitted as c:manualLayout with layoutTarget inner and
edge modes) and, for every axis a position is asked on, `min` and `max`; a category
position also needs the value axis's `cross_between` ("between": categories are bands,
bars and line points at band centres; "midpoint": line points on the band edges, the
first and last on the plot edges). Anything missing is refused by name, never assumed.

Formulas (OOXML layout model; measured on LibreOffice 24.2 by the probe, unmeasured in
PowerPoint):
- value v on an axis from lo to hi: t = (v - lo) / (hi - lo) from the axis origin
  (bottom for a vertical axis, left for a horizontal one), 1 - t when reversed;
- category i of n, between: band [i, i + 1] / n from the category origin (left on a
  column chart, bottom on a horizontal bar chart, the far end when reversed); midpoint:
  point at i / (n - 1);
- k clustered bars, gap g and overlap o (fractions): bar = slot / (k - (k - 1) o + g),
  the cluster centred in its slot, series j offset j * bar * (1 - o) from the cluster's
  start on the origin side; stacked: bar = slot / (1 + g), series stacked from the
  crossing value, positive and negative values on separate stacks; 100% stacked: each
  value over the category's sum of absolute values;
- bars grow from where the category axis crosses (c:crosses autoZero, which
  python-pptx writes): 0 clamped into lo..hi.
"""

from __future__ import annotations

from dataclasses import dataclass


class GeometryRefused(ValueError):
    """A position the spec does not determine; the message names what is missing."""


def chart_family(type_name: str) -> str:
    n = type_name
    if n.startswith(("COLUMN_", "BAR_")) and n != "BAR_OF_PIE":
        return "bar_stacked" if "STACKED" in n else "bar"
    if n.startswith("PIE"):
        return "pie"
    if n.startswith("DOUGHNUT"):
        return "doughnut"
    if n.startswith("LINE"):
        return "line"
    if n.startswith("AREA"):
        return "area"
    if n.startswith("XY_SCATTER"):
        return "xy"
    if n.startswith("BUBBLE"):
        return "bubble"
    if n.startswith("RADAR"):
        return "radar"
    return "other"


def bar_thickness(slot: float, type_name: str, n_series: int, gap_width: float, overlap: float) -> float:
    """A bar's thickness in a category slot of `slot` (any unit), gap_width and overlap
    in percent as the spec writes them."""
    g = gap_width / 100
    if "STACKED" in type_name:
        return slot / (1 + g)
    o = overlap / 100
    return slot / (n_series - (n_series - 1) * o + g)


#: python-pptx 1.0.2 writes no c:gapWidth for a bar chart: OOXML's absence value is 150
#: (ECMA-376 21.2.2.75); no c:overlap on a clustered chart: 0; 100 on a stacked one.
ABSENT_GAP_WIDTH = 150


def _num(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


@dataclass(frozen=True)
class Plot:
    """The inner plot rectangle in page EMU and the chart's orientation."""
    left: float
    top: float
    width: float
    height: float
    horizontal_bars: bool  # BAR_*: categories run up the page, values across


def plot_rect(el: dict, box) -> tuple[float, float, float, float] | None:
    """The inner plot rectangle in page EMU from the spec's plot_area, or None when the
    spec leaves the plot to the renderer."""
    pa = el.get("plot_area")
    if not isinstance(pa, dict) or not all(_num(pa.get(k)) for k in ("x", "y", "w", "h")):
        return None
    x, y, w, h = (float(v) for v in box)
    return x + pa["x"] * w, y + pa["y"] * h, pa["w"] * w, pa["h"] * h


class ChartGeometry:
    """Data to page EMU for one chart element (emit_pptx's chart spec plus its solved box)."""

    def __init__(self, el: dict, box: tuple[int, int, int, int] | list[int]) -> None:
        self.el = el
        self.where = el.get("id", "chart")
        self.type = str(el.get("type") or "")
        self.family = chart_family(self.type)
        if self.family not in ("bar", "bar_stacked", "line", "xy"):
            raise GeometryRefused(f"{self.where}: data positions are computed for bar, column, line and XY scatter charts; a {self.type} is not (unmeasured)")
        if self.type.startswith(("LINE_STACKED", "LINE_MARKERS_STACKED")):
            raise GeometryRefused(f"{self.where}: a stacked line's point positions are not computed here (unmeasured)")
        rect = plot_rect(el, box)
        if rect is None:
            raise GeometryRefused(f"{self.where}: needs plot_area {{x, y, w, h}}, written as the manual inner layout, so data positions are computable")
        self.box = tuple(float(v) for v in box)
        self.plot = Plot(*rect, self.type.startswith("BAR_"))
        self.axes = el.get("axes") or {}
        self.categories = el.get("categories") or []
        self.series = el.get("series") or []

    # --- axes ---------------------------------------------------------------------------

    def _axis(self, name: str) -> dict:
        ax = self.axes.get(name) or {}
        return ax

    def scale(self, name: str) -> tuple[float, float]:
        ax = self._axis(name)
        lo, hi = ax.get("min"), ax.get("max")
        if not (_num(lo) and _num(hi)) or not lo < hi:
            raise GeometryRefused(f"{self.where}: axes.{name} needs numeric min < max in the spec; an auto-scaled axis has no computable positions")
        return float(lo), float(hi)

    def cross_between(self) -> str:
        cb = self._axis("value").get("cross_between")
        if cb not in ("between", "midpoint"):
            raise GeometryRefused(f"{self.where}: axes.value.cross_between (\"between\" or \"midpoint\") is required for a category position; it decides whether points sit on band centres or band edges")
        return cb

    def _value_fraction(self, name: str, v: float) -> float:
        lo, hi = self.scale(name)
        t = (float(v) - lo) / (hi - lo)
        return 1 - t if self._axis(name).get("reverse") else t

    def value_coord(self, v: float, axis: str = "value") -> tuple[str, float]:
        """("x" | "y", page EMU) of a value on the value axis, or on the x axis
        ("category") of an XY chart."""
        if axis == "category" and self.family != "xy":
            raise GeometryRefused(f"{self.where}: a category axis has no scale; a value line sits on the value axis")
        t = self._value_fraction(axis, v)
        p = self.plot
        across = (axis == "value" and p.horizontal_bars) or axis == "category"
        if across:
            return "x", p.left + t * p.width
        return "y", p.top + (1 - t) * p.height

    def crossing_value(self) -> float:
        lo, hi = self.scale("value")
        return min(max(0.0, lo), hi)

    # --- categories ---------------------------------------------------------------------

    def _category_axis_span(self) -> tuple[str, float, float]:
        """(page axis, origin coordinate, signed extent): the category origin and the
        direction categories advance in."""
        p = self.plot
        rev = bool(self._axis("category").get("reverse"))
        if p.horizontal_bars:
            # categories run bottom-up from the origin; reversed, top-down
            return ("y", p.top, p.height) if rev else ("y", p.top + p.height, -p.height)
        return ("x", p.left + p.width, -p.width) if rev else ("x", p.left, p.width)

    def _category_index(self, category) -> int:
        n = len(self.categories)
        if isinstance(category, int) and not isinstance(category, bool):
            if not 0 <= category < n:
                raise GeometryRefused(f"{self.where}: category index {category} outside 0..{n - 1}")
            return category
        if category in self.categories:
            if self.categories.count(category) > 1:
                raise GeometryRefused(f"{self.where}: category {category!r} appears more than once; anchor by index")
            return self.categories.index(category)
        raise GeometryRefused(f"{self.where}: no category {category!r}; categories are {self.categories}")

    def category_band(self, category) -> tuple[str, float, float]:
        """(page axis, low, high) of a category's band in page EMU, low < high."""
        if self.family == "xy":
            raise GeometryRefused(f"{self.where}: an XY chart has no categories; anchor to x values")
        i = self._category_index(category)
        n = len(self.categories)
        axis, origin, extent = self._category_axis_span()
        if self.cross_between() == "between":
            a, b = origin + extent * i / n, origin + extent * (i + 1) / n
        else:
            if n < 2:
                raise GeometryRefused(f"{self.where}: one category on a midpoint axis has no band")
            step = extent / (n - 1)
            c = origin + step * i
            a, b = c - step / 2, c + step / 2
            lo_edge, hi_edge = sorted((origin, origin + extent))
            a, b = min(max(a, lo_edge), hi_edge), min(max(b, lo_edge), hi_edge)
        return axis, min(a, b), max(a, b)

    def category_centre(self, category) -> tuple[str, float]:
        i = self._category_index(category)
        n = len(self.categories)
        axis, origin, extent = self._category_axis_span()
        if self.cross_between() == "between":
            return axis, origin + extent * (i + 0.5) / n
        if n < 2:
            raise GeometryRefused(f"{self.where}: one category on a midpoint axis has no position")
        return axis, origin + extent * i / (n - 1)

    # --- marks --------------------------------------------------------------------------

    def _series_index(self, series) -> int:
        k = len(self.series)
        if isinstance(series, int) and not isinstance(series, bool):
            if not 0 <= series < k:
                raise GeometryRefused(f"{self.where}: series index {series} outside 0..{k - 1}")
            return series
        names = [s.get("name") for s in self.series]
        if names.count(series) == 1:
            return names.index(series)
        raise GeometryRefused(f"{self.where}: series {series!r} {'is not unique' if series in names else 'not found'}; series are {names}")

    def bar_rect(self, series, category) -> tuple[float, float, float, float]:
        """(left, top, width, height) in page EMU of one bar."""
        if self.family not in ("bar", "bar_stacked"):
            raise GeometryRefused(f"{self.where}: a {self.type} has no bars")
        j = self._series_index(series)
        i = self._category_index(category)
        if self.cross_between() != "between":
            raise GeometryRefused(f"{self.where}: bars need axes.value.cross_between \"between\"")
        n, k = len(self.categories), len(self.series)
        gap = float(self.el.get("gap_width", ABSENT_GAP_WIDTH))
        stacked = self.family == "bar_stacked"
        overlap = float(self.el.get("overlap", 100 if stacked else 0))
        axis, origin, extent = self._category_axis_span()
        slot = extent / n
        bar = bar_thickness(abs(slot), self.type, k, gap, overlap)
        sign = 1 if slot > 0 else -1
        slot_start = origin + slot * i
        if stacked:
            c0 = slot_start + sign * (abs(slot) - bar) / 2
        else:
            o = overlap / 100
            cluster = bar * (k - (k - 1) * o)
            c0 = slot_start + sign * ((abs(slot) - cluster) / 2 + j * bar * (1 - o))
        c1 = c0 + sign * bar
        v0, v1 = self.bar_values(j, i)
        vaxis, p0 = self.value_coord(v0)
        _, p1 = self.value_coord(v1)
        cat_lo, cat_hi = min(c0, c1), max(c0, c1)
        val_lo, val_hi = min(p0, p1), max(p0, p1)
        if axis == "x":
            return cat_lo, val_lo, cat_hi - cat_lo, val_hi - val_lo
        return val_lo, cat_lo, val_hi - val_lo, cat_hi - cat_lo

    def bar_values(self, j: int, i: int) -> tuple[float, float]:
        """The value interval one bar spans, clipped to the axis range."""
        lo, hi = self.scale("value")
        base = self.crossing_value()

        def value(s: dict) -> float:
            v = s["values"][i]
            if not _num(v):
                raise GeometryRefused(f"{self.where}: series {s.get('name')!r} category {i} has no number")
            return float(v)

        if self.family == "bar":
            a, b = base, value(self.series[j])
        else:
            vals = [value(s) for s in self.series]
            if "100" in self.type:
                total = sum(abs(v) for v in vals)
                vals = [v / total if total else 0.0 for v in vals]
            v = vals[j]
            same = [u for u in vals[:j] if (u >= 0) == (v >= 0)]
            a = sum(same)
            b = a + v
        return min(max(a, lo), hi), min(max(b, lo), hi)

    def point(self, series, index) -> tuple[float, float]:
        """(x, y) page EMU of a line point (by category) or an XY point (by index)."""
        j = self._series_index(series)
        s = self.series[j]
        if self.family == "xy":
            vals = s.get("values") or []
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(vals):
                raise GeometryRefused(f"{self.where}: series {s.get('name')!r} has no point {index!r}")
            xv, yv = vals[index][0], vals[index][1]
            return self.value_coord(xv, "category")[1], self.value_coord(yv, "value")[1]
        if self.family == "line":
            i = self._category_index(index)
            v = s["values"][i]
            if not _num(v):
                raise GeometryRefused(f"{self.where}: series {s.get('name')!r} category {i} has no number")
            _, c = self.category_centre(i)
            return c, self.value_coord(v)[1]
        # a bar's anchor point: the centre of its value end
        x, y, w, h = self.bar_rect(series, index)
        v0, v1 = self.bar_values(j, self._category_index(index))
        if self.plot.horizontal_bars:
            return (x + w if self.value_coord(v1)[1] >= self.value_coord(v0)[1] else x), y + h / 2
        return x + w / 2, (y if self.value_coord(v1)[1] <= self.value_coord(v0)[1] else y + h)

    def mark_rect(self, series, index) -> tuple[float, float, float, float]:
        """The drawn extent of one mark: a bar's rectangle, a point's marker box (its
        marker size in points, else a zero box at the point)."""
        if self.family in ("bar", "bar_stacked"):
            return self.bar_rect(series, index)
        x, y = self.point(series, index)
        s = self.series[self._series_index(series)]
        size = ((s.get("marker") or {}).get("size") or 0) * 12700
        return x - size / 2, y - size / 2, float(size), float(size)

    def value_span(self, lo_v: float, hi_v: float, axis: str = "value") -> tuple[str, float, float]:
        a_axis, a = self.value_coord(lo_v, axis)
        _, b = self.value_coord(hi_v, axis)
        return a_axis, min(a, b), max(a, b)


def table_geometry(el: dict) -> tuple[list[float], list[float]]:
    """A solved table's column left edges and row top edges in page EMU (n + 1 each),
    from the fitter's column widths and row heights as the emitter writes them."""
    x, y, _, _ = el["box"]
    widths = el.get("column_widths_emu")
    heights = el.get("row_heights_emu")
    if not widths or not heights:
        raise GeometryRefused(f"{el.get('id', 'table')}: no fitted column widths and row heights; a table's cells are located from the solver's fit")
    xs, ys = [float(x)], [float(y)]
    for w in widths:
        xs.append(xs[-1] + w)
    for h in heights:
        ys.append(ys[-1] + h)
    return xs, ys
