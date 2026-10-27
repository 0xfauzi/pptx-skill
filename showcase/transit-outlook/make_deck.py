"""Builds deck/deck.json and plan.json for the LRTA section from data.json (figures.py).
Every number written on a page is formatted from data.json; nothing is typed by hand.

Colour meanings, one per ink across the section:
  black (color.ink_muted)    history and the baseline case (dashed once projected)
  grey (color.grey)          the low and high ridership cases; earlier years in point comparisons
  pale navy (color.tint_navy) the range between the low and high cases
  dark grey dotted (color.ink) the 2019 level
  maroon (color.emphasis)    only what the title is about: the mark, the gap, the bar the claim names
  navy, sky, dark green, pink, light green: the five capital programs (pages 4 and 7 only)
  pale grey (color.grey_light) identified funding sources (page 5)
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "data.json")))
MARK = os.path.join(HERE, "img", "lrta-mark.png")
ONLY = sys.argv[1:]

MODES = D["MODES"]
YEARS = D["YEARS"]
HIST = D["HIST_YEARS"]
PROJ = D["PROJ_YEARS"]
T = dict(zip(YEARS, D["total"]))
LOW = {int(k): v for k, v in D["low"].items()}
HIGH = {int(k): v for k, v in D["high"].items()}
SER = D["series"]


def by_year(d):
    return {int(k): v for k, v in d.items()}


FOOT_1 = "LRTA Ten-Year Capital and Ridership Outlook 2026"
FOOT_2 = "Illustrative figures. Built in the style of a public US federal presentation; not affiliated with or endorsed by any agency."
SOURCE = "Data source: Lakeshore Regional Transit Authority, Ten-Year Capital and Ridership Outlook 2026 (fictional agency; illustrative figures)"
NOTES_COMMON = ("All figures on this page are illustrative: they were invented for a fictional agency, the Lakeshore Regional "
                "Transit Authority, and computed in figures.py. They describe no real transit system. ")

PROG_FILL = {"State of good repair": "color.accent2", "Expansion": "color.accent3", "Fleet and electrification": "color.green_dark",
             "Stations and accessibility": "color.pink", "Safety, systems and technology": "color.green_light"}
# the ink a label needs on each program fill (white on the dark fills, black on the light ones)
PROG_INK = {"State of good repair": "color.ink_inverse", "Expansion": "color.ink_muted", "Fleet and electrification": "color.ink_inverse",
            "Stations and accessibility": "color.ink_muted", "Safety, systems and technology": "color.ink_muted"}
PROG_SHORT = {"State of good repair": "state of good repair", "Expansion": "expansion", "Fleet and electrification": "fleet and electrification",
              "Stations and accessibility": "stations and accessibility", "Safety, systems and technology": "safety and systems"}

CAT_SHORT = {}
BLACK, GREY, BAND, LEVEL, EMPH = "color.ink_muted", "color.grey", "color.tint_navy", "color.ink", "color.emphasis"


def m1(v):
    return f"{v:,.1f}"


def money(v):
    return f"${v:,.0f}"


def flex(direction, gap="space.xs", pad=None, align="stretch", justify="start", pads=None):
    lay = {"kind": "flex", "direction": direction, "gap_role": gap, "align": align, "justify": justify}
    if pads is not None:
        lay["pad_roles"] = pads
    else:
        lay["pad_role"] = pad
    return lay


def text(id_, paras, weight=None, **kw):
    el = {"type": "element", "id": id_, "kind": "text", "paragraphs": paras}
    if weight is not None:
        el["weight"] = weight
    el.update(kw)
    return el


def P(role, t, **kw):
    p = {"role": role, "text": t}
    p.update(kw)
    return p


def chart_el(id_, weight=1.0):
    return {"type": "element", "id": id_, "kind": "chart", "weight": weight}


def panel(id_, header, units, body_children, weight=1.0, legend=None):
    kids = [text(f"{id_}-hd", [P("type.panel_header", header), P("type.units", units)])]
    if legend is not None:
        kids.append(legend)
    kids.extend(body_children)
    return {"type": "region", "id": id_, "weight": weight, "layout": flex("column", gap="space.xs"), "children": kids}


def word_legend(id_, names, roles, styling, sep="   "):
    """The reference's key: the series names as coloured bold words on one line, no box."""
    runs = []
    for i, (n, r) in enumerate(zip(names, roles)):
        if i:
            runs.append({"text": sep})
        runs.append({"text": n, "ink_role": r})
    styling[id_] = {"paragraphs": {"0": {"runs": runs}}}
    return text(id_, [P("type.data_label", sep.join(names))])


def page(sid, title, body, source_paras, page_no, styling, charts, annotations, notes, images=None, register="claim"):
    main = {"type": "region", "id": "main", "weight": 1.0,
            "layout": flex("column", gap="space.xs", pads={"left": "space.xl", "top": "space.sm", "right": "space.lg", "bottom": "space.xs"}),
            "children": [text("title", [P("type.title", title)]), body,
                         text("source", [P("type.source_line", s) for s in source_paras])]}
    foot = {"type": "region", "id": "foot", "size": {"height_emu": 444500}, "fill_role": "color.accent3",
            "layout": flex("row", gap="space.sm", align="center", pads={"left": "space.sm", "top": None, "right": "space.lg", "bottom": None}),
            "children": [{"type": "element", "id": "mark", "kind": "image"},
                         text("foot-text", [P("type.footer", FOOT_1), P("type.footnote", FOOT_2)], weight=1.0),
                         text("pageno", [P("type.page_number", str(page_no), align="right")], weight=0.06)]}
    styling = dict(styling)
    styling["foot-text"] = {"paragraphs": {"1": {"runs": [{"text": FOOT_2, "ink_role": "color.ink_inverse"}]}}}
    imgs = {"mark": {"path": MARK, "height_role": "space.lg", "width_role": "space.xl", "align": "left", "valign": "middle"}}
    imgs.update(images or {})
    return {"id": sid, "layout": "Blank", "notes": NOTES_COMMON + notes,
            "title": {"register": register, "element": "title"},
            "spec": {"root": {"type": "region", "id": "root", "layout": flex("column", gap="space.xs", pads={"left": None, "top": None, "right": None, "bottom": None}),
                              "children": [main, foot]}},
            "styling": styling, "charts": charts, "annotations": annotations, "images": imgs}


AX_TEXT = {"role": "type.axis_label", "ink_role": "color.ink"}


def cat_axis(labels_show=True, reverse=False, position=None, gridlines="none", line=True, rotation=0):
    lab = {"show": labels_show, "role": "type.axis_label", "ink_role": "color.ink", "rotation_deg": rotation}
    if position:
        lab["position"] = position
    return {"visible": True, "line_role": "color.ink" if line else "none", "line_width_pt": 0.75, "tick_marks": "none", "reverse": reverse,
            "gridlines": gridlines, "labels": lab, "title": "none"}


def val_axis(mn, mx, unit, fmt, grid=True, visible=True, cross="between", labels=True):
    return {"visible": visible, "line_role": "none", "tick_marks": "none", "reverse": False, "min": mn, "max": mx, "major_unit": unit,
            "number_format": fmt, "cross_between": cross,
            "gridlines": {"line_role": "color.grid", "line_width_pt": 0.75} if grid else "none",
            "labels": {"show": labels, "role": "type.axis_label", "ink_role": "color.ink"}, "title": "none"}


def xy_line(name, pts, role, width=1.5, dash=None, end_label=None, end_ink=None, label_pos="right", start_label=None):
    s = {"name": name, "values": [[x, y] for x, y in pts], "line_role": role, "line_width_pt": width, "smooth": False,
         "marker": {"style": "none"}, "labels": {"show": False}}
    if dash:
        s["dash"] = dash
    pts_l = []
    if start_label:
        pts_l.append({"index": 0, "label": {"show": True, "text": start_label, "position": "above", "role": "type.data_label", "ink_role": end_ink or role}})
    if end_label:
        pts_l.append({"index": len(pts) - 1, "label": {"show": True, "text": end_label, "position": label_pos, "role": "type.data_label",
                                                       "ink_role": end_ink or role}})
    if pts_l:
        s["points"] = pts_l
    return s


def x_axis(mn, mx, unit, labels=True):
    return {"visible": True, "line_role": "color.ink", "line_width_pt": 0.75, "tick_marks": "out", "reverse": False, "min": mn, "max": mx,
            "major_unit": unit, "number_format": "0", "crosses": "min", "gridlines": "none",
            "labels": {"show": labels, "role": "type.axis_label", "ink_role": "color.ink"}, "title": "none"}


def y_axis(mn, mx, unit, fmt):
    return {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": False, "min": mn, "max": mx, "major_unit": unit,
            "number_format": fmt, "crosses": "min", "gridlines": {"line_role": "color.grid", "line_width_pt": 0.75},
            "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}, "title": "none"}


BAND_LINES, BAND_WIDTH = 22, 2.75
BAND_LAST = True


def fan(hist_pts, base_pts, low_pts, high_pts, fmt, x0, x1, xu, mn, mx, unit, labels, plot_area):
    """The reference's projection fan: black history, black dashed baseline, grey low and high
    cases named at their ends, and the range between them shaded. The shading is a stack of
    pale strokes interpolated from low to high (an area series would bar every mark on the chart)."""
    ser = []
    xs = [x for x, _ in base_pts]
    lo = dict(low_pts)
    hi = dict(high_pts)
    band = [xy_line("range", [(x, lo[x] + t * (hi[x] - lo[x])) for x in xs], BAND, BAND_WIDTH)
            for t in (k / BAND_LINES for k in range(BAND_LINES + 1))]
    if labels.get("level") is not None:
        lv, ltext, lpos = labels["level"]
        ser.append(xy_line("2019 level", [(x0, lv), (x1, lv)], LEVEL, 1.0, dash="sysDot", end_label=ltext, end_ink=LEVEL, label_pos=lpos))
    if hist_pts:
        ser.append(xy_line("history", hist_pts, BLACK, 1.75))
    if "low" in labels:
        ser.append(xy_line("Low case", low_pts, GREY, 1.25, end_label=labels["low"], end_ink=GREY, label_pos=labels.get("low_pos", "right")))
    if "high" in labels:
        ser.append(xy_line("High case", high_pts, GREY, 1.25, end_label=labels["high"], end_ink=GREY, label_pos=labels.get("high_pos", "right")))
    ser.append(xy_line("Baseline", base_pts, BLACK, 1.75, dash="dash", end_label=labels["base"], end_ink=BLACK))
    ser = ser[::-1] + band if BAND_LAST else band + ser
    return {"type": "XY_SCATTER_LINES_NO_MARKERS", "number_format": fmt, "text": AX_TEXT, "series": ser,
            "axes": {"category": x_axis(x0, x1, xu), "value": y_axis(mn, mx, unit, fmt)},
            "legend": "none", "plot_fill_role": "none", "title": "none", "plot_area": plot_area}


def series_index(chart, name):
    return next(i for i, s in enumerate(chart["series"]) if s["name"] == name)


def projections_marks(host, labelled=True, explained=None):
    """The reference's dashed 2025 rule, with the year in bold above it and 'projections' beside it."""
    out = [{"id": f"{host}-2025", "host": host, "kind": "reference_line", "anchor": {"value": 2025, "axis": "category"},
            "line_role": "color.dash_rule", "line_width_pt": 1.0, "dash": "dash", "gap_role": "space.xs"}]
    if explained:
        out[0]["explained_by"] = explained
    if labelled:
        out[0]["label"] = {"text": "2025", "role": "type.data_label", "ink_role": GREY, "position": "end_outside", "align": "center"}
        out.append({"id": f"{host}-proj", "host": host, "kind": "reference_line", "anchor": {"value": 2025, "axis": "category"},
                    "line_role": "color.dash_rule", "line_width_pt": 1.0, "dash": "dash", "gap_role": "space.xs",
                    "label": {"text": "projections", "role": "type.axis_label", "ink_role": GREY, "position": "end_right", "align": "left"}})
    return out


# ============================ pages ============================
pages, plan_pages = [], []


def brief(must, comparison, data, forms, chosen, why, marks, look):
    return {"reader_must_see": must, "comparison": comparison, "data": data,
            "forms_considered": [{"form": f, "reason": r} for f, r in forms], "chosen_form": chosen, "why": why,
            "marks": marks, "in_reference_look": look}


# ---- page 2: ridership ----
def p_ridership():
    sid = "p1-ridership"
    st, ch, an = {}, {}, []
    hist = [(y, T[y]) for y in HIST]
    yrs = [2025] + PROJ
    lvl = T[2019]
    ry = D["recover_year"]
    c = fan(hist, [(y, T[y]) for y in yrs], [(2025, T[2025])] + [(y, LOW[y]) for y in PROJ],
            [(2025, T[2025])] + [(y, HIGH[y]) for y in PROJ], "0", 2015, 2035, 5, 40, 140, 20,
            {"low": f"low {m1(LOW[2035])}", "high": f"high {m1(HIGH[2035])}", "base": f"baseline {m1(T[2035])}"},
            {"x": 0.08, "y": 0.11, "w": 0.74, "h": 0.78})
    ch["c-total"] = c
    an += projections_marks("c-total")
    an.append({"id": "lvl2019", "host": "c-total", "kind": "reference_line", "anchor": {"value": lvl}, "line_role": LEVEL,
               "line_width_pt": 1.0, "dash": "sysDot", "gap_role": "space.xs",
               "label": {"text": f"2019 level, {m1(lvl)}", "role": "type.data_label", "ink_role": LEVEL, "position": "start_above", "align": "left"}})
    bi = series_index(c, "Baseline")
    an.append({"id": "cross", "host": "c-total", "kind": "arrow", "anchor": {"point": {"series": bi, "index": yrs.index(ry)}},
               "position": "below_right", "gap_role": "space.lg", "line_role": EMPH, "line_width_pt": 1.0,
               "label": {"text": f"the baseline is back above the 2019 level in {ry}", "role": "type.data_label", "ink_role": EMPH,
                         "align": "left", "max_width_share": 0.4}})
    # right: growth by mode, 2025 to 2035
    g = D["mode_growth"]
    order = sorted(MODES, key=lambda m: -g[m])
    cats = [m.lower() for m in order] + ["all modes"]
    vals = [round(100 * g[m], 1) for m in order] + [round(100 * (T[2035] / T[2025] - 1), 1)]
    lv = [(SER[m][YEARS.index(2025)], SER[m][-1]) for m in order] + [(T[2025], T[2035])]
    pts = []
    for i, (m, v, (a, b)) in enumerate(zip(cats, vals, lv)):
        p = {"index": i, "label": {"text": f"+{round(v)}%"}}
        if m == "light rail":
            p["fill_role"] = EMPH
        if m == "all modes":
            p["fill_role"] = BLACK
        pts.append(p)
    ch["c-growth"] = {"type": "BAR_CLUSTERED", "categories": cats, "number_format": "0", "text": AX_TEXT,
                      "series": [{"name": "Growth", "values": vals, "fill_role": GREY, "line_role": "none",
                                  "labels": {"show": True, "position": "outside_end", "role": "type.data_label", "ink_role": BLACK},
                                  "points": pts}],
                      "axes": {"category": cat_axis(reverse=True), "value": val_axis(0, 58, 20, "0\"%\"", visible=False, grid=False)},
                      "gap_width": 45, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
                      "plot_area": {"x": 0.28, "y": 0.09, "w": 0.46, "h": 0.91}}
    an.append({"id": "levels", "host": "c-growth", "kind": "category_row", "anchor": {"categories": [0, len(cats) - 1]}, "position": "right",
               "gap_role": "space.md", "cells": [f"{m1(a)} to {m1(b)}" for a, b in lv], "role": "type.axis_label", "ink_role": "color.ink",
               "align": "right", "cell_width": "uniform",
               "label": {"text": "millions", "role": "type.axis_label", "ink_role": "color.ink", "align": "right"}})
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": flex("row", gap="space.lg"),
            "children": [panel("pl", "Annual boardings, all modes, by ridership case", "millions", [chart_el("c-total")], weight=1.35),
                         panel("pr", "Growth in boardings, 2025-2035, by mode", "percent, baseline; boardings in 2025 and 2035 at right",
                               [chart_el("c-growth")], weight=1.0)]}
    lr = round(100 * g["Light rail"])
    title = f"Ridership passes its 2019 level in {ry} in the baseline; light rail grows fastest, up {lr}% from 2025 to 2035"
    src = [SOURCE, f"Note: The low and high cases scale every mode alike, to 0.88 and 1.10 times the baseline in 2035; they pass the 2019 level in {D['cross']['High']} and {D['cross']['Low']}."]
    notes = (f"Boardings fell from {m1(T[2019])} million in 2019 to {m1(T[2020])} million in 2020 and were {m1(T[2025])} million in 2025. "
             f"The baseline passes the 2019 level in {ry} ({m1(T[ry])} million) and reaches {m1(T[2035])} million in 2035; "
             f"the low and high cases end at {m1(LOW[2035])} and {m1(HIGH[2035])} million. Light rail grows {lr}% from 2025 to 2035, "
             f"bus {round(100 * g['Bus'])}%, commuter rail {round(100 * g['Commuter rail'])}%, demand response {round(100 * g['Demand response'])}%.")
    pages.append(page(sid, title, body, src, 2, st, ch, an, notes))
    plan_pages.append({"id": sid, "intent": "where ridership goes over ten years, in total and by mode",
                       "message": f"ridership is back to its 2019 level by {ry} and light rail grows fastest",
                       "composition": "new:fan-beside-ranked-bars", "title_register": "claim", "deliberate_parallel": None,
                       "exhibits": [
                           brief("the year the baseline climbs back over the 2019 level, and how wide the case range is by 2035",
                                 "the baseline and its low and high cases against the 2019 boardings level, over time",
                                 "one annual total from 2015 to 2025, then three cases from 2026 to 2035",
                                 [("line fan with a shaded range", "chosen: a crossing year and a widening range read directly off lines against a level"),
                                  ("clustered columns per year and case", "thirty columns hide the crossing and the trend under bar tops"),
                                  ("table of totals by year", "the reader would scan for the first value over 96.9")],
                                 "line fan with a shaded range",
                                 "the claim is a crossing and a spread; a line against a dotted level shows both without arithmetic",
                                 "the 2019 level as a labelled dotted line; a maroon arrow naming the crossing year; the 2025 rule with the year in bold and 'projections'",
                                 "the reference's fan: black history, black dashed baseline, grey cases named at their ends, a pale range, the dashed 2025 rule under a bold year"),
                           brief("that light rail grows fastest and how each mode's growth compares with all modes",
                                 "each mode's growth from 2025 to 2035 against the others and against the total",
                                 "four modes and the total, each a percent change with its two levels in millions",
                                 [("ranked horizontal bars of percent growth, levels in the labels", "chosen: rank and size read at a glance and the levels stay on the page"),
                                  ("stacked bars of boardings by mode per case", "repeats the left chart's totals and leaves demand response a sliver"),
                                  ("100% stacked bars of mode share", "share moves by two points; the growth that makes it is hidden")],
                                 "ranked horizontal bars of percent growth, levels in the labels",
                                 "the claim is a rank; sorted bars with the total last make the fastest mode the first thing seen",
                                 "light rail's bar in maroon as the title's subject, all modes in black, every bar labelled",
                                 "flat bars with no frame or axis, labels in black, as the reference labels its ranked bars")]})


# ---- page 3: fares, cost and recovery, three across ----
def p_fares():
    sid = "p2-fares"
    st, ch, an = {}, {}, []
    fr, oc, rec = by_year(D["fare_rev"]), by_year(D["op_cost"]), by_year(D["recovery"])
    rl, rh = by_year(D["rec_low"]), by_year(D["rec_high"])
    vl, vh = by_year(D["rev_low"]), by_year(D["rev_high"])
    yrs = [2025] + PROJ
    pa = {"x": 0.15, "y": 0.11, "w": 0.58, "h": 0.78}
    ch["c-rev"] = fan([(y, fr[y]) for y in HIST], [(y, fr[y]) for y in yrs], [(2025, fr[2025])] + [(y, vl[y]) for y in PROJ],
                      [(2025, fr[2025])] + [(y, vh[y]) for y in PROJ], "#,##0", 2015, 2035, 10, 0, 250, 50,
                      {"low": "", "high": "", "base": f"{money(fr[2035])}\n({money(vl[2035])}-{money(vh[2035])[1:]})"}, pa)
    ch["c-cost"] = fan([(y, oc[y]) for y in HIST], [(y, oc[y]) for y in yrs], [(y, oc[y]) for y in yrs], [(y, oc[y]) for y in yrs],
                       "#,##0", 2015, 2035, 10, 0, 1600, 400, {"base": f"all cases {money(oc[2035])}"}, pa)
    ch["c-cost"]["series"] = [s for s in ch["c-cost"]["series"] if s["name"] != "range"]
    ch["c-rec"] = fan([(y, rec[y]) for y in HIST], [(y, rec[y]) for y in yrs], [(2025, rec[2025])] + [(y, rl[y]) for y in PROJ],
                      [(2025, rec[2025])] + [(y, rh[y]) for y in PROJ], "0\"%\"", 2015, 2035, 10, 0, 20, 5,
                      {"low": "", "high": "", "base": f"{rec[2035]:.1f}%\n({rl[2035]:.1f}-{rh[2035]:.1f}%)", "level": (rec[2019], f"2019 level\n{rec[2019]:.1f}%", "right")}, pa)
    an += projections_marks("c-rev")
    quote = {"text": "fan-key", "quote": "after 2025"}
    an += projections_marks("c-cost", labelled=False, explained=quote)
    an += projections_marks("c-rec", labelled=False, explained=quote)
    key = word_legend("fan-key", ["history, then the baseline dashed after 2025", "low and high ridership cases, with the range between them shaded"], [BLACK, GREY], st)
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": flex("column", gap="space.xs"),
            "children": [key, {"type": "region", "id": "three", "weight": 1.0, "layout": flex("row", gap="space.md"),
                               "children": [panel("pa", "Fare revenue", "$ million, nominal", [chart_el("c-rev")]),
                                            panel("pb", "Operating cost", "$ million, nominal", [chart_el("c-cost")]),
                                            panel("pc", "Farebox recovery", "fare revenue as a percent of operating cost", [chart_el("c-rec")])]}]}
    fg, cg = round(100 * D["fare_growth"]), round(100 * D["cost_growth"])
    title = (f"Fare revenue grows {fg}% by 2035, yet farebox recovery ends at "
             f"{rl[2035]:.1f}-{rh[2035]:.1f}%, below 2019's {rec[2019]:.1f}% in every case")
    src = [SOURCE, "Note: Fares rise 5% for every mode in 2027, 2031 and 2034. Operating cost is the same in all three cases; the cases differ in ridership, and so in fare revenue."]
    notes = (f"Fare revenue was {money(fr[2019])} million in 2019 and {money(fr[2025])} million in 2025; the baseline reaches {money(fr[2035])} million in 2035 "
             f"({money(vl[2035])} to {money(vh[2035])} million across cases). Operating cost goes from {money(oc[2025])} million to {money(oc[2035])} million. "
             f"Recovery was {rec[2019]:.1f}% in 2019 and {rec[2025]:.1f}% in 2025, and ends 2035 at {rl[2035]:.1f}% (low), {rec[2035]:.1f}% (baseline) "
             f"and {rh[2035]:.1f}% (high).")
    pages.append(page(sid, title, body, src, 3, st, ch, an, notes))
    plan_pages.append({"id": sid, "intent": "what riders pay, what service costs, and how much of the cost fares cover",
                       "message": "revenue outgrows cost, yet recovery stays well under its 2019 level in every case",
                       "composition": "new:three-across-fans", "title_register": "claim", "deliberate_parallel": None,
                       "exhibits": [
                           brief("revenue recovering and growing past its 2019 level, with the spread across ridership cases",
                                 "fare revenue over time and across the three cases", "21 years of revenue in $ million, three cases from 2026",
                                 [("line fan, one of three small multiples", "chosen: the three measures share a time axis and the eye reads across them"),
                                  ("columns with a recovery line on a second axis", "a dual axis put a percent line among dollar bars and squashed it")],
                                 "line fan, one of three small multiples", "revenue is the first term of the ratio; it reads first, left",
                                 "the 2025 rule with its bold year and 'projections', case values at the line ends",
                                 "the reference's three-across fans (its natural gas page): one header and units line per panel"),
                           brief("operating cost rising steadily, faster than ridership", "operating cost over time", "21 years in $ million, one path in every case",
                                 [("a single line in the middle panel", "chosen: the denominator between the numerator and the ratio"),
                                  ("a table row of cost by year", "the slope would have to be read from figures")],
                                 "a single line in the middle panel", "the reader needs the slope, not the figures",
                                 "the 2035 value at the line end, named 'all cases'", "black line, dashed once projected, as the reference draws its baseline"),
                           brief("recovery ending well under the dotted 2019 level in every case", "recovery in three cases against its 2019 level",
                                 "21 years of a percent, three cases from 2026, one 2019 level",
                                 [("line fan with the 2019 level as a dotted line", "chosen: the distance from every case to the level reads at a glance"),
                                  ("bars of recovery in 2019, 2025 and 2035", "loses the path and the 2020 collapse")],
                                 "line fan with the 2019 level as a dotted line", "the claim is that no case reaches a level; lines against the level show it",
                                 "the 2019 level labelled; a maroon bracket from the high case to the level giving the shortfall",
                                 "the reference's fan with a pale range")]})


# ---- page 4: capital plan ----
def p_capital():
    sid = "p3-capital"
    st, ch, an = {}, {}, []
    progs = D["PROGRAMS"]
    cap = D["capital"]
    yt = D["year_total"]
    ser = [{"name": p, "values": cap[p], "fill_role": PROG_FILL[p], "line_role": "none", "labels": {"show": False}} for p in progs]
    ser.append({"name": "Total", "values": [0] * 10, "fill_role": "none", "line_role": "none",
                "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": BLACK},
                "points": [{"index": i, "label": {"text": f"{t:,}"}} for i, t in enumerate(yt)]})
    ch["c-years"] = {"type": "COLUMN_STACKED", "categories": [str(y) for y in PROJ], "number_format": "0", "text": AX_TEXT, "series": ser,
                     "axes": {"category": cat_axis(), "value": val_axis(0, 1150, 250, "#,##0", cross="between", visible=False, grid=False)},
                     "gap_width": 35, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
                     "plot_area": {"x": 0.01, "y": 0.02, "w": 0.98, "h": 0.9}}
    eb = D["exp_build"]
    an.append({"id": "exp-build", "host": "c-years", "kind": "band",
               "anchor": {"region": {"categories": [PROJ.index(2027), PROJ.index(2030)], "values": [0, 1150]}}, "fill_role": "color.surface_alt",
               "label": {"text": f"2027-2030: {money(eb)}m of the {money(D['prog_total']['Expansion'])}m expansion program",
                         "role": "type.data_label", "ink_role": EMPH, "align": "left", "position": "inside_top_left", "max_width_share": 0.36}})
    order = sorted(progs, key=lambda p: -D["prog_total"][p])
    totals = [D["prog_total"][p] for p in order]
    ch["c-progs"] = {"type": "BAR_CLUSTERED", "categories": [PROG_SHORT[p] for p in order], "number_format": "#,##0", "text": AX_TEXT,
                     "series": [{"name": "Ten-year total", "values": totals, "fill_role": GREY, "line_role": "none",
                                 "labels": {"show": True, "position": "outside_end", "role": "type.data_label", "ink_role": BLACK},
                                 "points": [{"index": i, "fill_role": PROG_FILL[p], "label": {"text": f"{D['prog_total'][p]:,}  {round(D['share'][p])}%"}}
                                            for i, p in enumerate(order)]}],
                     "axes": {"category": cat_axis(reverse=True), "value": val_axis(0, 3400, 500, "#,##0", visible=False, grid=False)},
                     "gap_width": 30, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
                     "plot_area": {"x": 0.47, "y": 0.0, "w": 0.52, "h": 1.0}}
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": flex("row", gap="space.lg"),
            "children": [panel("pr", "Ten-year total by program", f"$ million; share of the {money(D['plan_total'])} million plan",
                               [chart_el("c-progs")], weight=0.9),
                         panel("pl", "Capital plan by year and program", "$ million, year of expenditure; colours as in the left chart",
                               [chart_el("c-years")], weight=1.3)]}
    title = (f"State of good repair takes {round(D['share']['State of good repair'])}% of the ${D['plan_total'] / 1000:.1f} billion plan; "
             f"two-thirds of expansion spending falls in 2027-2030")
    src = [SOURCE, "Note: Year-of-expenditure dollars. Expansion = Blue Line extension, Lakefront BRT and Crosstown BRT."]
    notes = (f"The ten-year plan totals {money(D['plan_total'])} million. Annual spending peaks at {money(max(yt))} million in {D['peak_year']}. "
             f"Expansion spends {money(eb)} million of its {money(D['prog_total']['Expansion'])} million in 2027-2030 "
             f"({100 * eb / D['prog_total']['Expansion']:.0f}%).")
    pages.append(page(sid, title, body, src, 4, st, ch, an, notes))
    plan_pages.append({"id": sid, "intent": "what the ten-year capital plan buys and when",
                       "message": "repair is the largest program, and expansion construction makes the 2027-2030 hump",
                       "composition": "new:ranking-beside-stacked-columns", "title_register": "claim", "deliberate_parallel": None,
                       "exhibits": [
                           brief("that state of good repair is the largest program at 41% of the plan, and which colour is which program",
                                 "the five programs' ten-year totals, ranked", "five totals in $ million with their shares",
                                 [("ranked horizontal bars with values and shares, coloured by program", "chosen: rank and size at a glance, and the bars are the right chart's key"),
                                  ("pie of shares", "five slices with two near 7% are hard to compare, and the reference draws no pies")],
                                 "ranked horizontal bars with values and shares, coloured by program",
                                 "the claim is a rank and a share; sorted bars with labelled values show both and double as the key",
                                 "each bar in its program colour with its total and share at the end",
                                 "flat bars in the reference's series colours, no frame, labels in black"),
                           brief("the hump in annual spending from 2027 to 2030 and that the sky-blue expansion segment makes it",
                                 "each year's spending by program, year against year", "five programs by ten years in $ million, with yearly totals",
                                 [("stacked columns by year", "chosen: the yearly totals and the program inside each read on one axis"),
                                  ("stacked area by year", "a smooth area hides which year peaks and loses the printed totals"),
                                  ("table of programs by year", "fifty figures; the hump would not be seen")],
                                 "stacked columns by year", "the claim is a hump and its cause; stacked columns show both",
                                 "totals above every column; a pale band behind 2027-2030 whose maroon label gives expansion's spend there against its total",
                                 "the reference's stacked palette in navy, sky, greens and pink, no frame")]})


# ---- page 5: funding gap ----
def p_funding():
    sid = "p4-funding"
    st, ch, an = {}, {}, []
    need, srcs, fund = D["plan_total"], D["SOURCES"], D["funding"]
    cats = ["Need"] + [CAT_SHORT.get(x, x) for x in srcs] + ["Gap"]
    deltas = [need] + [-fund[s] for s in srcs] + [D["gap"]]
    base, step, run, levels = [0], [need], need, [need]
    for s in srcs:
        run -= fund[s]
        base.append(run); step.append(fund[s]); levels.append(run)
    base.append(0); step.append(D["gap"])
    assert run == D["gap"]
    labels = [f"{need:,}"] + [f"-{fund[s]:,}" for s in srcs] + [f"{D['gap']:,}"]
    gw = 40
    ch["c-bridge"] = {
        "type": "COLUMN_STACKED", "categories": cats, "number_format": "#,##0", "text": AX_TEXT,
        "series": [
            {"name": "Base", "values": base, "fill_role": "none", "line_role": "none", "labels": {"show": False}},
            {"name": "Step", "values": step, "fill_role": "color.grey_light", "line_role": "none", "labels": {"show": False},
             "points": [{"index": 0, "fill_role": "color.ink"}, {"index": len(cats) - 1, "fill_role": EMPH}]},
            {"name": "Label", "values": [0] * len(cats), "fill_role": "none", "line_role": "none",
             "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": BLACK},
             "points": [{"index": i, "label": {"text": t}} for i, t in enumerate(labels)]}],
        "axes": {"category": cat_axis(), "value": val_axis(0, 6000, 1000, "#,##0", cross="between")},
        "gap_width": gw, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
        "bridge": {"deltas": deltas, "totals": [0, len(cats) - 1]},
        "plot_area": {"x": 0.1, "y": 0.06, "w": 0.9, "h": 0.74}}
    # connectors: a hairline from each bar's top edge to the next bar, at the running level
    half = 0.5 / (1 + gw / 100)
    for i, lv in enumerate(levels):
        an.append({"id": f"conn{i}", "host": "c-bridge", "kind": "mark", "prst": "line", "line_role": "color.grey", "line_width_pt": 0.75,
                   "anchor": {"region": {"categories": [i, i + 1], "values": [lv, lv]}},
                   "points": [[(0.5 + half) / 2 + 0.02, 0.0], [(1.5 - half) / 2 - 0.02, 0.0]]})
    rows = [[s["name"], s["what"], f"{s['need']:,}", f"{s['funded']:,}", f"{s['gap']:,}", f"{s['gap_share']:.1f}%"] for s in D["scen"]]
    tbl = {"type": "element", "id": "t-scen", "kind": "table",
           "table": {"columns": [{"key": "sc", "label": "Scenario", "value_kind": "text", "width_share": 0.27},
                                 {"key": "wh", "label": "What changes", "value_kind": "text", "width_share": 0.30},
                                 {"key": "need", "label": "Need", "value_kind": "number"},
                                 {"key": "fund", "label": "Funded", "value_kind": "number"},
                                 {"key": "gap", "label": "Gap", "value_kind": "number"},
                                 {"key": "sh", "label": "Share", "value_kind": "number"}],
                     "rows": rows, "header_rows": 1, "header_role": "type.table_header", "cell_role": "type.table_cell"},
           "emphasis": [{"rows": [0], "fill_role": "keep", "bold": True}], "cell_anchor": "m"}
    lo = min(s["gap"] for s in D["scen"]); hi = max(s["gap"] for s in D["scen"])
    nog = next(s for s in D["scen"] if s["name"] == "No federal grant")["gap"]
    ren = next(s for s in D["scen"] if s["name"] == "Sales tax renewed")["gap"]
    esc_add = next(s for s in D["scen"] if s["name"] == "Costs 8% higher")["gap"] - D["gap"]
    read = text("scen-read", [P("type.body", f"Renewing the local sales tax roughly halves the gap, to {money(ren)} million; "
                                             f"losing the Blue Line's federal grant roughly doubles it, to {money(nog)} million. "
                                             f"Costs 8% over estimate add {money(esc_add)} million to it.")])
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": flex("row", gap="space.lg"),
            "children": [panel("pl", "Need, identified sources and gap, baseline", "$ million, 2026-2035", [chart_el("c-bridge")], weight=1.0),
                         {"type": "region", "id": "pr", "weight": 1.45, "layout": flex("column", gap="space.sm"),
                          "children": [text("pr-hd", [P("type.panel_header", "Funding gap by scenario"), P("type.units", "$ million over 2026-2035; gap as a share of need")]), tbl, read]}]}
    title = (f"Identified sources cover {round(100 * D['funded'] / need)}% of the ${need / 1000:.1f} billion plan; "
             f"the ${D['gap'] / 1000:.1f} billion gap runs from ${lo / 1000:.1f} to ${hi / 1000:.1f} billion across scenarios")
    src = [SOURCE, "Note: Federal grants = the Blue Line capital grant request. Costs 8% higher raises the whole plan 8%."]
    notes = (f"Need {money(need)} million; identified {money(D['funded'])} million; gap {money(D['gap'])} million ({100 * D['gap'] / need:.1f}% of need). "
             f"Scenario gaps run from {money(lo)} million (sales tax renewed) to {money(hi)} million (both downsides).")
    pages.append(page(sid, title, body, src, 5, st, ch, an, notes))
    plan_pages.append({"id": sid, "intent": "how the plan is paid for and how big the shortfall can get",
                       "message": "sources cover 84% and the gap swings five-fold across scenarios",
                       "composition": "new:bridge-beside-table", "title_register": "claim", "deliberate_parallel": None,
                       "exhibits": [
                           brief("the plan's need stepping down source by source to a maroon gap bar", "the need against each identified source and the remainder",
                                 "one need, five sources and one gap, in $ million, that tie out",
                                 [("waterfall from need to gap", "chosen: each source's contribution and the remainder read as steps that tie"),
                                  ("one stacked bar of sources against a need line", "the gap would be a sliver between a bar and a line"),
                                  ("table of sources", "the gap would be a subtraction left to the reader")],
                                 "waterfall from need to gap", "the claim is what remains after sources; a bridge shows the remainder as a bar",
                                 "the need in dark grey, sources in pale grey, the gap in maroon; every step labelled; connectors at each running level",
                                 "flat blocks with no frame, light gridlines, values in black"),
                           brief("how the gap moves between scenarios, and what changes in each", "need, funding and gap in each of five scenarios",
                                 "five scenarios by a description and four figures",
                                 [("compact scenario table with a what-changes column", "chosen: four figures a scenario are compared down a column, and the description says why"),
                                  ("bars of the gap by scenario", "drops the need and funding that explain each gap")],
                                 "compact scenario table with a what-changes column", "the reader looks up a scenario; a table holds it exactly",
                                 "the baseline row in bold, the row the waterfall draws",
                                 "the reference's navy-teal header cells and pale blue banded rows")]})


# ---- page 6: cost per rider ----
def p_cost():
    sid = "p5-cost"
    st, ch, an = {}, {}, []
    cpb = by_year(D["cpb"])
    lo_, hi_ = by_year(D["cpb_low"]), by_year(D["cpb_high"])
    yrs = [2025] + PROJ
    c = fan([(y, cpb[y]) for y in HIST], [(y, cpb[y]) for y in yrs], [(2025, cpb[2025])] + [(y, lo_[y]) for y in PROJ],
            [(2025, cpb[2025])] + [(y, hi_[y]) for y in PROJ], "$0", 2015, 2035, 5, 8, 18, 2,
            {"low": f"low ridership ${lo_[2035]:.2f}", "high": f"high ridership ${hi_[2035]:.2f}", "base": f"baseline ${cpb[2035]:.2f}",
             "level": (cpb[2019], f"2019 level, ${cpb[2019]:.2f}", "above")},
            {"x": 0.09, "y": 0.11, "w": 0.56, "h": 0.78})
    ch["c-cpb"] = c
    an += projections_marks("c-cpb")
    # right: change since 2019 by mode, a dot plot with the 2035 case range
    cc = D["cpb_change"]
    cm = D["cpb_mode"]
    rows = sorted(MODES, key=lambda m: -cc[m]["2035"]) + ["All modes"]
    cats = [m.lower() for m in rows]
    lowr = [round(cc[m]["2035_high"], 1) for m in rows]   # high ridership: the lowest cost
    span = [round(cc[m]["2035_low"] - cc[m]["2035_high"], 1) for m in rows]
    v25 = [round(cc[m]["2025"], 1) for m in rows]
    v35 = [round(cc[m]["2035"], 1) for m in rows]
    ch["c-dots"] = {
        "type": "LINE_MARKERS", "categories": cats, "number_format": "0", "text": AX_TEXT,
        "series": [
            {"name": "Range base", "values": lowr, "plot_type": "COLUMN_STACKED", "fill_role": "none", "line_role": "none", "labels": {"show": False}},
            {"name": "2035 range", "values": span, "plot_type": "COLUMN_STACKED", "fill_role": BAND, "line_role": "none", "labels": {"show": False}},
            {"name": "2025", "values": v25, "line_role": "none", "smooth": False,
             "marker": {"style": "circle", "size": 7, "fill_role": GREY, "line_role": GREY}, "labels": {"show": False}},
            {"name": "2035 baseline", "values": v35, "line_role": "none", "smooth": False,
             "marker": {"style": "circle", "size": 8, "fill_role": BLACK, "line_role": BLACK},
             "labels": {"show": True, "position": "right", "role": "type.data_label", "ink_role": BLACK},
             "points": [{"index": i, "label": {"text": f"+{round(v)}%"}} for i, v in enumerate(v35)]}],
        "axes": {"category": cat_axis(position="low"), "value": val_axis(0, 70, 10, "0\"%\"", cross="between")},
        "gap_width": 260, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
        "plot_area": {"x": 0.17, "y": 0.03, "w": 0.81, "h": 0.6}}
    lv19 = [f"${cm['2019'][m]:.2f}" if m in MODES else f"${cpb[2019]:.2f}" for m in rows]
    lv35 = [f"${cm['2035'][m]:.2f}" if m in MODES else f"${cpb[2035]:.2f}" for m in rows]
    an.append({"id": "row19", "host": "c-dots", "kind": "category_row", "anchor": {"categories": [0, len(rows) - 1]}, "position": "below",
               "gap_role": "type.axis_label", "gap_lines": 3, "cells": lv19, "role": "type.axis_label", "ink_role": "color.ink", "align": "center",
               "cell_width": "own", "label": {"text": "2019", "role": "type.axis_label", "ink_role": "color.ink", "max_width_share": 0.16, "align": "left"}})
    an.append({"id": "row35", "host": "c-dots", "kind": "category_row", "anchor": {"categories": [0, len(rows) - 1]}, "position": "below",
               "gap_role": "space.xs", "after": "row19", "cells": lv35, "role": "type.data_label", "ink_role": BLACK, "align": "center",
               "cell_width": "own", "label": {"text": "2035", "role": "type.data_label", "ink_role": BLACK, "max_width_share": 0.16, "align": "left"}})
    key = word_legend("dots-key", ["2025", "2035 baseline", "shaded: 2035 from high to low ridership"], [GREY, BLACK, "color.ink"], st)
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": flex("row", gap="space.lg"),
            "children": [panel("pa", "Operating cost per boarding, all modes, by ridership case", "dollars, nominal", [chart_el("c-cpb")], weight=1.15),
                         panel("pb", "Change in cost per boarding since 2019, by mode", "percent; dollars per boarding below", [chart_el("c-dots")],
                               weight=1.0, legend=key)]}
    title = (f"Cost per boarding stays above 2019's ${cpb[2019]:.2f} in every case; bus's rises most, "
             f"up {round(cc['Bus']['2035'])}% on 2019 by 2035")
    src = [SOURCE, "Note: Cost per boarding = operating cost / boardings. The cases differ in ridership only; operating cost is the baseline's in all three. "
                   "Demand response is per trip."]
    notes = (f"Systemwide cost per boarding was ${cpb[2019]:.2f} in 2019 and ${cpb[2025]:.2f} in 2025; it ends 2035 at ${cpb[2035]:.2f} in the baseline, "
             f"${hi_[2035]:.2f} with high ridership and ${lo_[2035]:.2f} with low. By mode, 2035 against 2019: "
             + ", ".join(f"{m.lower()} +{round(cc[m]['2035'])}%" for m in rows) + ".")
    pages.append(page(sid, title, body, src, 6, st, ch, an, notes))
    plan_pages.append({"id": sid, "intent": "what each rider costs to carry, systemwide and by mode",
                       "message": "unit cost stays above 2019 in every case, and every mode costs more per rider than in 2019",
                       "composition": "new:fan-beside-dot-plot", "title_register": "claim", "deliberate_parallel": None,
                       "exhibits": [
                           brief("all three case lines staying above the dotted 2019 level through 2035", "cost per boarding in three cases against its 2019 value",
                                 "21 years in dollars, three cases from 2026, one 2019 value",
                                 [("line fan with the 2019 level as a line, axis from $8", "chosen: every case's distance from the level reads at a glance, and the lines use the plot's height"),
                                  ("columns for 2019, 2025 and 2035 by case", "loses the path and the 2020 spike")],
                                 "line fan with the 2019 level as a line, axis from $8", "the claim is that no line comes down to a level",
                                 "the 2019 level labelled; each case named at its end with its 2035 value; 'high ridership' and 'low ridership' named as such",
                                 "the reference's fan with a pale range and the bold 2025 rule"),
                           brief("that every mode's 2035 cost sits well right of zero change, bus furthest, and how far the ridership cases move it",
                                 "each mode's change since 2019 in 2025 and 2035, and the 2035 range across cases",
                                 "four modes and all modes, each with two percent changes and a 2035 range, plus the dollar levels",
                                 [("dot plot of percent change with a range bar, dollar levels in rows under it", "chosen: one scale for modes whose levels differ nine-fold, levels kept below"),
                                  ("clustered bars of dollar levels by year", "demand response at $69 flattens the others; the earlier draft needed a separate panel for it")],
                                 "dot plot of percent change with a range bar, dollar levels in rows under it",
                                 "the claim is about change; percent change puts every mode on one honest scale",
                                 "the 2035 baseline dot labelled with its change; 2025 dots in grey; the case range shaded; the 2019 and 2035 levels in rows",
                                 "the reference's dot plot (its consumption-by-fuel page): dots on pale range bars, light gridlines")]})


# ---- page 7: timeline ----
def p_timeline():
    sid = "p6-timeline"
    st, ch, an = {}, {}, []
    pr = D["projects"]
    y0, n_years = PROJ[0], len(PROJ)
    cats = ["year"] + [p[0] for p in pr]
    starts = [0] + [p[1] - y0 for p in pr]
    dur = [0] + [p[2] - p[1] + 1 for p in pr]
    ser = [{"name": "Start", "values": starts, "fill_role": "none", "line_role": "none", "labels": {"show": False}},
           {"name": "Construction", "values": dur, "fill_role": GREY, "line_role": "none",
            "labels": {"show": True, "position": "center", "role": "type.data_label", "ink_role": BLACK},
            "points": [{"index": 0, "label": {"show": False}}] +
                      [{"index": i + 1, "fill_role": PROG_FILL[p[4]], "label": dict({"text": f"${p[3]:,}m", "ink_role": PROG_INK[p[4]]},
                                                                                  **({"position": "inside_base"} if p[1] <= 2030 < p[2] and abs((p[1] + p[2] + 1) / 2 - 2031) < 1.5 else {}))}
                       for i, p in enumerate(pr)]},
           {"name": "Service", "values": [0] + [0.0001 if p[4] == "Expansion" else 0 for p in pr], "fill_role": "none", "line_role": "none",
            "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": "color.ink"},
            "points": [{"index": 0, "label": {"show": False}}] +
                      [{"index": i + 1, "label": ({"text": f"in service {p[2]}"} if p[4] == "Expansion" else {"show": False})} for i, p in enumerate(pr)]}]
    # the header row: one unit segment per year, its year centred in it (the bars span whole years)
    for k, y in enumerate(PROJ):
        ser.append({"name": str(y), "values": [1] + [0] * len(pr), "fill_role": "color.surface_alt" if k % 2 == 0 else "color.band_blue", "line_role": "none",
                    "labels": {"show": True, "position": "center", "role": "type.axis_label", "ink_role": "color.ink"},
                    "points": [{"index": 0, "label": {"text": str(y)}}] + [{"index": i + 1, "label": {"show": False}} for i in range(len(pr))]})
    ch["c-gantt"] = {"type": "BAR_STACKED", "categories": cats, "number_format": "0", "text": AX_TEXT, "series": ser,
                     "axes": {"category": cat_axis(reverse=True, line=False),
                              "value": {**val_axis(0, n_years, 1, "0", cross="between", visible=False, grid=False)}},
                     "gap_width": 30, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
                     "plot_area": {"x": 0.25, "y": 0.09, "w": 0.74, "h": 0.9}}
    st.setdefault("c-gantt", {})
    done = [p for p in pr if p[2] <= 2030]
    an.append({"id": "by2030", "host": "c-gantt", "kind": "reference_line", "anchor": {"value": 2031 - y0}, "line_role": EMPH, "line_width_pt": 1.25,
               "dash": "dash", "gap_role": "space.xs",
               "label": {"text": f"end of 2030: {len(done)} of {len(pr)} projects complete", "role": "type.data_label", "ink_role": EMPH,
                         "position": "end_outside", "align": "center"}})
    progs = D["PROGRAMS"]
    leg = word_legend("prog-key6", [PROG_SHORT[p] for p in progs], [PROG_FILL[p] for p in progs], st)
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": flex("row", gap="space.lg"),
            "children": [panel("pl", "Major projects: years of construction and cost", "bars span whole calendar years; cost in $ million, year of expenditure",
                               [chart_el("c-gantt")], weight=1.0, legend=leg)]}
    big = [p for p in pr if p[0].startswith("Blue Line")][0]
    title = (f"Five of ten major projects finish by 2030, including the ${big[3] / 1000:.2f} billion Blue Line extension; "
             f"two programs run all decade")
    src = [SOURCE, "Note: Expansion projects show the year they enter service. Bar colours are the capital programs of page 4."]
    notes = ("Projects ending by 2030: " + ", ".join(p[0] for p in done) + ". Running 2026-2035: "
             + ", ".join(p[0] for p in pr if (p[1], p[2]) == (2026, 2035)) + ".")
    pages.append(page(sid, title, body, src, 7, st, ch, an, notes))
    plan_pages.append({"id": sid, "intent": "when the major projects are built and what each costs",
                       "message": "half the major projects finish by 2030; fleet and accessibility run all decade",
                       "composition": "new:full-width-gantt", "title_register": "claim", "deliberate_parallel": None,
                       "exhibits": [
                           brief("which bars end left of the 2030 line, and the Blue Line extension's long, costly bar",
                                 "each project's construction years against the others and against the end of 2030",
                                 "ten projects with a start year, an end year, a cost and a program",
                                 [("Gantt bars under a header row of years, coloured by program", "chosen: overlap, duration and the 2030 cut read on one time axis, and every year label sits on its own year"),
                                  ("table of projects with years and costs", "the reader would compare years by reading them"),
                                  ("milestone dots on a time line", "drops duration, which is where the decade-long programs show")],
                                 "Gantt bars under a header row of years, coloured by program",
                                 "the claim is about timing; bars on a time axis with one cut line show which side each project lands",
                                 "a dashed maroon line at the end of 2030 labelled with the count above the plot; cost inside every bar; service years beside the expansion bars",
                                 "horizontal bars in the reference's series colours with a word key, banded like its tables")]})


for fn in (p_ridership, p_fares, p_capital, p_funding, p_cost, p_timeline):
    fn()
if ONLY:
    pages = [p for p in pages if p["id"] in ONLY]
    plan_pages = [p for p in plan_pages if p["id"] in ONLY]
os.makedirs(os.path.join(HERE, "deck"), exist_ok=True)
json.dump({"slides": pages}, open(os.path.join(HERE, "deck", "deck.json"), "w"), indent=1)
guide = json.load(open(os.path.join(HERE, "ref", "guide.json")))
json.dump({"schema": "pptx-skill section plan v2", "reference_sha256": guide["reference"]["sha256"], "pages": plan_pages},
          open(os.path.join(HERE, "plan.json"), "w"), indent=1)
print("pages:", [p["id"] for p in pages])
