"""Write deck/deck.json and plan.json for the Ridgeline section from data.json (figures.py).

Usage: python3 -I scripts/build_spec.py <work dir> [page ids...]

Colour key, held on every page:
  methods: prescribed fire maroon, mechanical thinning green, mastication blue, hand thinning dark grey
  hazard classes: very high red, high yellow
  pairs: navy = what is needed (homes at risk, crew-days needed); teal = the plan (acres planned,
         hazard with the plan); light grey = today or without the plan (available now, FY2026)
"""
import json
import os
import sys

W = os.path.dirname(os.path.abspath(__file__))
ONLY = sys.argv[1:]
D = json.load(open(os.path.join(W, "data.json")))
E = 914400
FOOTER = ("Illustrative figures. Built in the style of a public US federal presentation; "
          "not affiliated with or endorsed by any agency.")
NOTE_ILL = ("All figures on this page are illustrative: they were invented for a fictional program, "
            "the Ridgeline State Forestry Program, and computed and checked in a script. "
            "They describe no real agency, county or forest.")

METHOD_ROLE = {"Prescribed fire": "color.series_maroon", "Mechanical thinning": "color.series_green",
               "Mastication": "color.series_blue", "Hand thinning": "color.ink_muted"}
NEED, PLAN, TODAY = "color.accent3", "color.accent1", "color.slice_grey"


def zone(l, t, w, h, s):
    return {"left": int(l * E), "top": int(t * E), "width": int(w * E), "height": int(h * E), "source": s}


ZONES = [zone(0, 0.07, 0.067, 7.35, "red-rule"), zone(0, 7.08, 0.75, 0.34, "page-number"),
         zone(11.55, 6.76, 1.75, 0.64, "wordmark")]


def flex(direction, gap=None, pads=(None, None, None, None), align="stretch", justify="start"):
    return {"kind": "flex", "direction": direction, "gap_role": gap,
            "pad_roles": dict(zip(("left", "top", "right", "bottom"), pads)), "align": align, "justify": justify}


def text(id_, paras, **kw):
    n = {"type": "element", "id": id_, "kind": "text",
         "paragraphs": [p if isinstance(p, dict) else {"role": p[0], "text": p[1]} for p in paras]}
    n.update(kw)
    return n


def region(id_, layout, children, **kw):
    n = {"type": "region", "id": id_, "layout": layout, "children": children}
    n.update(kw)
    return n


def el(id_, kind, **kw):
    n = {"type": "element", "id": id_, "kind": kind}
    n.update(kw)
    return n


def page(pid, layout, fig, title, body, notes):
    root = region("root", flex("column", None, ("space.margin", None, None, "space.margin")), [
        region("band", flex("row", "space.gutter", ("space.md", "space.md", "space.gutter", "space.md"), align="stretch"), [
            text("figid", [("type.kicker", fig)], weight=0.06),
            text("title", [("type.title", title)], weight=0.94, anchor="m"),
        ], size={"height_emu": int(1.05 * E)}, fill_role="color.accent3"),
        region("body", flex("column", "space.lg", ("space.gutter", "space.gutter", "space.gutter", None)), [body], weight=1.0),
        region("foot", flex("row", "space.gutter", (None, None, None, None), align="end"), [
            region("foot-l", flex("row"), [], size={"width_emu": int(0.62 * E)}),
            text("legal", [("type.footnote", FOOTER)], weight=1.0),
            region("foot-r", flex("row"), [], size={"width_emu": int(1.75 * E), "height_emu": int(0.68 * E)}),
        ]),
    ])
    return {"id": pid, "layout": layout, "title": {"register": "topic", "element": "title"},
            "notes": NOTE_ILL + " " + notes,
            "spec": {"page": {"width_emu": 12192000, "height_emu": 6858000, "reserved_zones": ZONES}, "root": root}}


def side(id_, finding, note, **kw):
    """The reference's narrow note column: small type, a bold lead word, then the note."""
    return text(id_, [("type.footnote", "Key finding: " + finding), ("type.footnote", "Note: " + note)], **kw)


def side_col(id_, finding, note, weight):
    return region(id_, flex("column", None), [
        text(id_ + "-f", [("type.footnote", "Key finding: " + finding)]),
        region(id_ + "-gap", flex("column"), [], weight=1.0),
        text(id_ + "-n", [("type.footnote", "Note: " + note)])], weight=weight)


def side_col_styling(id_, finding, note):
    return {id_ + "-f": {"paragraphs": {"0": {"runs": [{"text": "Key finding:", "emphasis": True}, {"text": " " + finding}]}}},
            id_ + "-n": {"paragraphs": {"0": {"runs": [{"text": "Note:", "emphasis": True}, {"text": " " + note}]}}}}


def side_styling(id_, finding, note):
    return {id_: {"paragraphs": {"0": {"runs": [{"text": "Key finding:", "emphasis": True}, {"text": " " + finding}]},
                                  "1": {"runs": [{"text": "Note:", "emphasis": True}, {"text": " " + note}]}}}}


def tcols(spec):
    out = []
    for c in spec:
        k, l, v = c[:3]
        col = {"key": k, "label": l, "value_kind": v}
        if len(c) > 3:
            col["width_share"] = c[3]
        out.append(col)
    return out


def table(id_, cols, rows, emphasis=None, **kw):
    t = {"columns": tcols(cols), "rows": rows, "header_rows": 1, "header_role": "type.table_header",
         "cell_role": "type.table_cell", "cell_anchor": "m"}
    if emphasis:
        t["emphasis"] = emphasis
    return el(id_, "table", table=t, **kw)


AX_TEXT = {"role": "type.axis_label", "ink_role": "color.ink"}


def cat_axis(reverse=False, show=True, title="none", line="color.ink"):
    return {"visible": True, "line_role": line, "line_width_pt": 1.0, "tick_marks": "none", "reverse": reverse,
            "gridlines": "none", "labels": {"show": show, "role": "type.axis_label", "ink_role": "color.ink"}, "title": title}


def head(id_, lead, units=None):
    paras = [("type.emphasis", lead)]
    if units:
        paras.append(("type.caption", units))
    return text(id_, paras)


def k1(x):
    return f"{x:.1f}"


def legend_row(id_, items, title=None, width_in=6.0, vertical=False):
    """A key drawn from layout: a filled square per series and its name, in the series' order.
    Text in a row takes a share of the row by weight, so each name is weighted by its length and a
    spacer takes the rest (0.095 in per character at 11pt, measured by capacity)."""
    def sw(i, role):
        return region(f"{id_}-sw{i}", flex("row"), [], size={"width_emu": int(0.13 * E), "height_emu": int(0.13 * E)}, fill_role=role)
    if vertical:
        rows = [region(f"{id_}-r{i}", flex("row", "space.md", align="center"), [sw(i, role), text(f"{id_}-t{i}", [{"role": "type.axis_label", "text": label, "align": "left"}], weight=1.0)])
                for i, (role, label) in enumerate(items)]
        return region(id_, flex("column", "space.xs"), rows)
    kids, used = [], 0.0
    if title:
        w = 0.095 * len(title) + 0.15
        kids.append(text(id_ + "-title", [{"role": "type.emphasis", "text": title, "align": "left"}], weight=w)); used += w
    for i, (role, label) in enumerate(items):
        w = 0.095 * len(label) + 0.12
        kids.append(sw(i, role))
        kids.append(text(f"{id_}-t{i}", [{"role": "type.axis_label", "text": label, "align": "left"}], weight=w)); used += w
    spare = width_in - used - len(items) * 0.13 - 0.08 * (2 * len(items) + (1 if title else 0))
    kids.append(region(id_ + "-spare", flex("row"), [], weight=max(spare, 0.05)))
    return region(id_, flex("row", "space.md", align="center"), kids)


def legend(pos="t"):
    return {"position": pos, "role": "type.axis_label", "ink_role": "color.ink"}


slides, plan = [], []
METHODS = ["Prescribed fire", "Mechanical thinning", "Mastication", "Hand thinning"]

# ------------------------------------------------------------------ page 1
M, years, TH = D["METHODS_HIST"], D["YEARS"], D["TOTAL_HIST"]
marker = {"Prescribed fire": "diamond", "Mechanical thinning": "square", "Mastication": "circle", "Hand thinning": "x"}
glyph = {"Prescribed fire": "◆", "Mechanical thinning": "■", "Mastication": "●", "Hand thinning": "×"}
series = [{"name": m, "values": M[m], "line_role": METHOD_ROLE[m], "line_width_pt": 2.0, "smooth": False,
           "marker": {"style": marker[m], "size": 8, "fill_role": METHOD_ROLE[m]}, "labels": {"show": False}} for m in METHODS]
c1 = {"type": "LINE_MARKERS", "categories": years, "number_format": "0", "text": AX_TEXT, "series": series,
      "axes": {"category": cat_axis(),
               "value": {"visible": True, "line_role": "color.ink", "line_width_pt": 1.0, "tick_marks": "none", "reverse": False,
                         "min": 0, "max": 25, "major_unit": 5, "number_format": "0", "gridlines": "none", "cross_between": "between",
                         "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"},
                         "title": {"text": "Thousand Acres Treated", "role": "type.emphasis", "ink_role": "color.ink", "orientation": "along"}}},
      "legend": "none", "plot_area": {"x": 0.10, "y": 0.04, "w": 0.87, "h": 0.84}, "plot_fill_role": "none", "title": "none"}
key1 = text("key1", [{"role": "type.emphasis", "text": "Method", "align": "left"}] + [{"role": "type.axis_label", "text": f"{glyph[m]}  {m}", "align": "left"} for m in METHODS])
rank_now = {"Prescribed fire": ("↑", "Rose to 1st"), "Mechanical thinning": ("↓", "Fell to 2nd"),
            "Mastication": ("→", "Held 3rd"), "Hand thinning": ("→", "Held 4th")}
pc = D["pct_change"]
rows1 = [["All methods"] + [k1(v) for v in TH] + [f"+{pc['All methods']:.0f}%", "", ""]]
rows1 += [[m] + [k1(v) for v in M[m]] + [f"+{pc[m]:.0f}%", "", rank_now[m][1]] for m in METHODS]
t1 = table("t1", [("m", "Method", "text", 0.22)] + [(y.lower(), y, "number", 0.085) for y in years] +
           [("chg", "Change", "number", 0.09), ("icon", "", "text", 0.045), ("rank", "Rank", "text", 0.22)], rows1,
           emphasis=[{"rows": [0], "fill_role": "keep", "bold": True}, {"columns": ["chg"], "fill_role": "keep", "bold": True},
                     {"columns": ["rank"], "fill_role": "keep", "bold": True}])
F1 = ("prescribed fire grew 2.5 times, from 9.4 to 23.5 thousand acres, and passed mechanical thinning in FY2025. "
      "It is 40% of FY2026 acres.")
N1 = "Fiscal years run July to June. Hand thinning includes pile burning. An acre treated twice in one year counts twice."
body1 = region("b1", flex("column", "space.lg"), [
    region("b1-top", flex("row", "space.gutter", align="stretch"), [
        region("b1-chart", flex("column", "space.sm"), [
            head("c1-head", "Acres treated by method, FY2022 to FY2026", "Thousand acres; the total is in the table"),
            el("c1", "chart", weight=1.0)], weight=0.76),
        region("b1-right", flex("column", None, (None, "space.gutter", None, None)), [
            region("b1-gap0", flex("column"), [], weight=0.3), key1, region("b1-gap", flex("column"), [], weight=0.15), side("side1", F1, N1, weight=1.0, anchor="b")], weight=0.24),
    ], weight=1.0),
    t1,
], weight=1.0)
s1 = page("p1-acres", "3_trend-graph Layout", "RSFP.1", "Acres Treated by Method: Statewide; FY2022-FY2026",
          body1, "Acres treated rose 65 percent in five years, from 35.7 to 59.0 thousand; prescribed fire drove most of the growth.")
s1["charts"] = {"c1": c1}
s1["styling"] = {"key1": {"paragraphs": {str(i + 1): {"runs": [{"text": glyph[m], "ink_role": METHOD_ROLE[m]}, {"text": f"  {m}"}]}
                                         for i, m in enumerate(METHODS)}}}
s1["styling"].update(side_styling("side1", F1, N1))
s1["annotations"] = [
    {"id": "cross", "host": "c1", "kind": "outline_box", "anchor": {"point": {"series": 0, "category": 3}},
     "shape": "ellipse", "line_role": "color.ink", "line_width_pt": 1.25, "pad_role": "space.md",
     "label": {"text": "Prescribed fire passes mechanical thinning", "role": "type.emphasis", "ink_role": "color.ink",
               "align": "right", "position": "above_left", "max_width_share": 0.24}, "gap_role": "none"}]
for i, m in enumerate(METHODS):
    s1["annotations"].append({"id": f"tr{i}", "host": "t1", "kind": "badge", "anchor": {"cell": [i + 1, 8]}, "position": "left",
                              "gap_role": "none", "pad_role": "none", "fill_role": "color.accent3",
                              "label": {"text": rank_now[m][0], "role": "type.footnote", "ink_role": "color.ink_inverse", "align": "center"}})
slides.append(s1)
plan.append({"id": "p1-acres", "intent": "show how much the program treats each year and with which methods",
             "message": "treatment rose 65% in five years and prescribed fire became the largest method in FY2025",
             "composition": "arch-3", "title_register": "topic", "deliberate_parallel": None,
             "exhibits": [{"reader_must_see": "the prescribed fire line climbing past mechanical thinning while the other two methods grow slowly",
                           "comparison": "each method's acres year by year against the other methods",
                           "data": "five fiscal years of acres for four methods, in thousand acres; the total is four times larger",
                           "forms_considered": [
                               {"form": "line chart of the four methods on a 0 to 25 axis, total in the table", "reason": "chosen: the crossing is in the open part of the scale"},
                               {"form": "line chart with the total as a fifth line", "reason": "the total sets a 0 to 70 scale and squeezes the crossing into the bottom third"},
                               {"form": "stacked columns by year", "reason": "the total reads but the crossing of two inner segments cannot be seen"}],
                           "chosen_form": "line chart of the four methods on a 0 to 25 axis, total in the table",
                           "why": "the claim is a change in rank over time, which crossing lines show and stacked segments hide",
                           "marks": "a ring at the FY2025 crossing labelled with what it marks; a titled key in the method colours",
                           "in_reference_look": "coloured method lines with markers, a key with a title as the reference's 'Age Group' legend, no gridlines"},
                          {"reader_must_see": "the exact acres behind every point, the total and each method's change in rank",
                           "comparison": "each method's acres by year, its five-year change and its rank now against FY2022",
                           "data": "five yearly values for four methods and their total, a percent change and a rank movement",
                           "forms_considered": [
                               {"form": "table of the plotted values with a change column and an icon column", "reason": "chosen: the reference prints its estimates under every trend chart with a trend icon column"},
                               {"form": "data labels on every line point", "reason": "twenty labels crowd the lines where they cross"}],
                           "chosen_form": "table of the plotted values with a change column and an icon column",
                           "why": "readers look values up, and the icon column states what the reference's trend column states",
                           "marks": "total row, change column and rank column bold; an arrow icon per method",
                           "in_reference_look": "grey header with white bold labels, round icons beside a bold word, as its trend column"}]})

# ------------------------------------------------------------------ page 2
C = D["COUNTIES"]
names = [c[0] for c in C]
HS, AS, GS = D["HOME_SHARE"], D["ACRE_SHARE"], D["GROUP_SHARES"]
plan_total = sum(c[4] for c in C)
c2 = {"type": "BAR_STACKED", "categories": names, "number_format": "0", "text": AX_TEXT,
      "series": [
          {"name": "Very high hazard", "values": [c[1] for c in C], "fill_role": "color.series_red", "line_role": "none",
           "labels": {"show": True, "position": "center", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink_inverse"}},
          {"name": "High hazard", "values": [c[2] for c in C], "fill_role": "color.series_yellow", "line_role": "none",
           "labels": {"show": True, "position": "center", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink"}}],
      "axes": {"category": cat_axis(reverse=True),
               "value": {"visible": False, "min": 0, "max": 60, "cross_between": "between"}},
      "gap_width": 45, "overlap": 100, "legend": "none",
      "plot_area": {"x": 0.20, "y": 0.06, "w": 0.66, "h": 0.93}, "plot_fill_role": "none", "title": "none"}
ann2 = [{"id": "tot2", "host": "c2", "kind": "category_row", "anchor": {"categories": [0, len(C) - 1]}, "position": "right",
         "gap_role": "space.md", "cell_width": "uniform", "align": "right",
         "cells": [{"text": f"{c[1] + c[2]}%", "role": "type.emphasis", "ink_role": "color.ink"} for c in C],
         "label": {"text": "Both", "role": "type.emphasis", "ink_role": "color.ink", "align": "right", "max_width_share": 0.1}}]
bold2 = [names.index("Dunmore"), names.index("Basin")]
rows2 = [[c[0], k1(c[3]), f"{HS[c[0]]:.0f}%", k1(c[4]), f"{AS[c[0]]:.0f}%"] for c in C]
rows2.append(["All counties", k1(sum(c[3] for c in C)), "100%", k1(plan_total), "100%"])
t2 = table("t2", [("county", "County", "text", 0.26), ("homes", "WUI Homes", "number", 0.19), ("hs", "Home Share", "number", 0.18),
                  ("acres", "Planned Acres", "number", 0.20), ("as", "Acre Share", "number", 0.17)], rows2,
           emphasis=[{"rows": [len(rows2) - 1], "fill_role": "keep", "bold": True}, {"rows": bold2, "fill_role": "keep", "bold": True}])
groups = list(GS)
gname = {"Elk Ridge and Cedar Fork": "Elk Ridge, Cedar Fork", "Basin and Dunmore": "Basin, Dunmore", "Other six counties": "Other six"}
c2b = {"type": "BAR_CLUSTERED", "categories": [gname[g] for g in groups], "number_format": "0", "text": AX_TEXT,
       "series": [
           {"name": "Share of WUI homes", "values": [round(GS[g][0], 1) for g in groups], "fill_role": NEED, "line_role": "none",
            "labels": {"show": True, "position": "outside_end", "number_format": "0\"%\"", "role": "type.data_label", "ink_role": "color.ink"}},
           {"name": "Share of planned acres", "values": [round(GS[g][1], 1) for g in groups], "fill_role": PLAN, "line_role": "none",
            "labels": {"show": True, "position": "outside_end", "number_format": "0\"%\"", "role": "type.data_label", "ink_role": "color.ink"}}],
       "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 60, "cross_between": "between"}},
       "gap_width": 30, "overlap": 0, "legend": "none",
       "plot_area": {"x": 0.43, "y": 0.0, "w": 0.50, "h": 1.0}, "plot_fill_role": "none", "title": "none"}
F2 = ("Basin and Dunmore hold 37% of the homes in the WUI but receive 12% of planned acres; "
      "near homes the plan thins by hand, at 4.8 times the cost per acre of prescribed fire.")
N2 = "Hazard classes are from the program's 2026 fuels model. Bold rows: the two counties with the most WUI homes."
body2 = region("b2", flex("row", "space.gutter", align="stretch"), [
    region("b2-chart", flex("column", "space.sm"), [
        head("c2-head", "Share of county land in wildfire hazard, by hazard class", "Percent of county land; counties ranked by the two classes together"),
        legend_row("key2", [("color.series_red", "Very high"), ("color.series_yellow", "High")], title="Hazard class", width_in=5.8),
        el("c2", "chart", weight=1.0)], weight=0.47),
    region("b2-right", flex("column", "space.md"), [
        head("t2-head", "Homes in the wildland-urban interface (WUI) and acres planned", "Thousands, FY2027-FY2029; shares of the ten-county total"),
        t2,
        region("b2-low", flex("row", "space.gutter", align="stretch"), [
            region("b2-c2b", flex("column", "space.sm"), [
                legend_row("key2b", [(NEED, "Share of WUI homes"), (PLAN, "Share of planned acres")], vertical=True),
                el("c2b", "chart", weight=1.0)], weight=0.64),
            side("side2", F2, N2, weight=0.36, anchor="t")], weight=1.0),
    ], weight=0.53),
], weight=1.0)
s2 = page("p2-county", "1_figure-standard", "RSFP.2", "Hazard and Planned Acres by County; FY2027-FY2029",
          body2, "Planned acres follow the hazard rank; the counties with the most homes get few acres because work near homes is done by hand.")
s2["charts"] = {"c2": c2, "c2b": c2b}
s2["annotations"] = ann2
s2["styling"] = side_styling("side2", F2, N2)
slides.append(s2)
plan.append({"id": "p2-county", "intent": "show where the hazard is, that the plan's acres follow it, and where homes are left with few acres",
             "message": "the plan puts 38% of its acres in the two highest-hazard counties, while Basin and Dunmore, with 37% of WUI homes, get 12%",
             "composition": "new:chart-beside-table", "title_register": "topic", "deliberate_parallel": None,
             "exhibits": [{"reader_must_see": "the counties ranked by hazard share, with Elk Ridge and Cedar Fork far above the rest",
                           "comparison": "each county's very high and high hazard share against the other counties",
                           "data": "two percentages for each of ten counties that add to a combined share",
                           "forms_considered": [
                               {"form": "stacked horizontal bars sorted by combined share, the combined share in a column at right", "reason": "chosen: rank and the split between the two classes read together"},
                               {"form": "choropleth map of the counties", "reason": "the emitter draws no map, and a map hides the rank the plan follows"}],
                           "chosen_form": "stacked horizontal bars sorted by combined share, the combined share in a column at right",
                           "why": "the claim is a rank, and sorted bars with the combined figure in one column show it",
                           "marks": "combined share bold in its own titled column; hazard classes in a legend",
                           "in_reference_look": "bars with values on them and a legend above, as on its substance-use bar pages"},
                          {"reader_must_see": "how many homes and planned acres each county carries, and their shares",
                           "comparison": "each county's share of WUI homes against its share of planned acres",
                           "data": "homes and planned acres for ten counties with shares and a total row",
                           "forms_considered": [
                               {"form": "compact table beside the bars, rows in the bars' order", "reason": "chosen: exact values to look up"},
                               {"form": "second bar series for planned acres", "reason": "mixes percent and acres on one axis"}],
                           "chosen_form": "compact table beside the bars, rows in the bars' order",
                           "why": "lookup values belong in a table and the rows line up with the bars' order",
                           "marks": "total row bold; Basin and Dunmore bold, the bold explained in the note",
                           "in_reference_look": "grey header with white bold labels, no interior rules, centred numbers at one decimal"},
                          {"reader_must_see": "Basin and Dunmore's share of homes far above their share of acres",
                           "comparison": "share of homes against share of planned acres for three county groups",
                           "data": "two shares for each of three groups that each add to 100%",
                           "forms_considered": [
                               {"form": "paired horizontal bars for three groups", "reason": "chosen: the mismatch reads as two bar lengths"},
                               {"form": "two more columns in the table", "reason": "the gap has to be worked out row by row"}],
                           "chosen_form": "paired horizontal bars for three groups",
                           "why": "the finding is a mismatch, which a pair of bars shows at once",
                           "marks": "values at bar ends; navy for homes (the need), teal for acres (the plan)",
                           "in_reference_look": "bars with values at bar ends and a legend above"}]})

# ------------------------------------------------------------------ page 3
COST = D["COST"]
order3 = sorted(METHODS, key=lambda m: -D["COST_TOTAL"][m])
comp_names = ["Labor", "Equipment", "Materials", "Planning"]
c3 = {"type": "BAR_CLUSTERED", "categories": order3, "number_format": "0", "text": AX_TEXT,
      "series": [{"name": "Cost per acre", "values": [D["COST_TOTAL"][m] for m in order3], "fill_role": "color.ink_muted", "line_role": "none",
                  "labels": {"show": True, "position": "outside_end", "number_format": "\\$#,##0", "role": "type.emphasis", "ink_role": "color.ink"},
                  "points": [{"index": i, "fill_role": METHOD_ROLE[m]} for i, m in enumerate(order3)]}],
      "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 2000, "cross_between": "between"}},
      "gap_width": 40, "overlap": 0, "legend": "none",
      "plot_area": {"x": 0.20, "y": 0.11, "w": 0.38, "h": 0.89}, "plot_fill_role": "none", "title": "none"}
ann3 = []
for j, nm in enumerate(comp_names):
    cells = []
    for m in order3:
        v = COST[m][j]
        cell = {"text": f"${v:,}", "role": "type.axis_label", "ink_role": "color.ink"}
        if (m == "Mechanical thinning" and nm == "Equipment") or (m == "Hand thinning" and nm == "Labor"):
            cell = {"text": f"${v:,}", "role": "type.emphasis", "ink_role": "color.ink", "emphasis": True}
        cells.append(cell)
    a = {"id": f"comp{j}", "host": "c3", "kind": "category_row", "anchor": {"categories": [0, 3]}, "position": "right",
         "gap_role": "space.gutter", "cell_width": "uniform", "align": "right", "cells": cells,
         "label": {"text": nm, "role": "type.emphasis", "ink_role": "color.ink", "align": "right", "max_width_share": 0.085}}
    if j:
        a["after"] = f"comp{j - 1}"
        a["gap_role"] = "type.axis_label"
        a["gap_lines"] = 3
    ann3.append(a)
P, CM, TC = D["PLAN_BY_METHOD"], D["COST_M"], D["TOTAL_COST_M"]
rows3 = [[m, k1(P[m]), f"{D['COST_TOTAL'][m]:,}", k1(CM[m]), f"{P[m] / 160 * 100:.0f}%", f"{CM[m] / TC * 100:.0f}%"] for m in order3]
rows3.append(["All methods", k1(sum(P.values())), f"{D['avg_cost']:,.0f}", k1(TC), "100%", "100%"])
ipf, imt = order3.index("Prescribed fire"), order3.index("Mechanical thinning")
t3 = table("t3", [("m", "Method", "text", 0.24), ("acres", "Planned Acres", "number", 0.15), ("cpa", "Unit Cost", "number", 0.15),
                  ("cost", "Plan Cost", "number", 0.15), ("sa", "Acre Share", "number", 0.155), ("sc", "Cost Share", "number", 0.155)], rows3,
           emphasis=[{"rows": [4], "fill_role": "keep", "bold": True}, {"rows": [ipf, imt], "columns": ["sa", "sc"], "fill_role": "keep", "bold": True}])
F3 = ("prescribed fire is 40% of planned acres but 11% of cost; mechanical thinning is 28% of acres and 55% of cost, "
      "at 7.3 times the cost per acre, most of it equipment.")
N3 = ("Plan cost is planned acres FY2027-FY2029 times FY2026 cost per acre. Bold component: the largest part of the two "
      "dearest methods. Hand thinning includes pile burning.")
body3 = region("b3", flex("column", "space.lg"), [
    region("b3-top", flex("row", "space.gutter", align="stretch"), [
        region("b3-chart", flex("column", "space.sm"), [
            head("c3-head", "Cost per acre treated, by method and by cost component", "FY2026 dollars per acre; bar colours as the methods on page 1"),
            el("c3", "chart", weight=1.0)], weight=0.79),
        side_col("side3", F3, N3, weight=0.21),
    ], weight=1.0),
    region("b3-t", flex("column", "space.sm"), [
        head("t3-head", "The plan's cost by method, FY2027-FY2029", "Thousand acres; dollars per acre; $ million; percent of the plan"),
        t3]),
], weight=1.0)
s3 = page("p3-cost", "1_figure-standard", "RSFP.3", "Cost per Acre by Treatment Method: Statewide; FY2026",
          body3, "The plan's $129.7 million buys 160 thousand acres at an average of $811 an acre.")
s3["charts"] = {"c3": c3}
s3["annotations"] = ann3
s3["styling"] = side_col_styling("side3", F3, N3)
slides.append(s3)
plan.append({"id": "p3-cost", "intent": "show what each method costs per acre, why, and what the plan's mix costs",
             "message": "prescribed fire is 40% of the plan's acres for 11% of its cost",
             "composition": "new:ranked-bars-with-figure-columns-over-table", "title_register": "topic", "deliberate_parallel": None,
             "exhibits": [{"reader_must_see": "mechanical thinning costing 7.3 times prescribed fire per acre, and that equipment is most of it",
                           "comparison": "total cost per acre across four methods, and the four parts that make each",
                           "data": "four cost components for each of four methods in dollars per acre, from $25 to $820",
                           "forms_considered": [
                               {"form": "ranked bars of the total with the four components as aligned figure columns", "reason": "chosen: the rank reads from the bars and every component is legible, however small"},
                               {"form": "stacked columns of cost components", "reason": "prescribed fire's $220 splits into slivers no label fits, as the last build showed"}],
                           "chosen_form": "ranked bars of the total with the four components as aligned figure columns",
                           "why": "the reader needs the gap in totals and its cause, and the small components must stay readable",
                           "marks": "totals bold at bar ends; the largest component of the two dearest methods bold, explained in the note",
                           "in_reference_look": "its horizontal ranked bars with values at the ends, no value axis, method colours from its line pages"},
                          {"reader_must_see": "the plan's acres and cost by method with each method's share",
                           "comparison": "share of acres against share of cost for each method",
                           "data": "planned acres, cost per acre, cost and two shares for four methods and a total",
                           "forms_considered": [
                               {"form": "table under the chart, in the bars' order", "reason": "chosen: exact plan figures"},
                               {"form": "paired bars of acre share and cost share", "reason": "a second chart on one page, and the figures still need stating"}],
                           "chosen_form": "table under the chart, in the bars' order",
                           "why": "the shares are looked up and compared in two columns side by side",
                           "marks": "total row bold; the prescribed fire and mechanical thinning shares bold",
                           "in_reference_look": "grey header table below the chart, as on its trend pages"}]})

# ------------------------------------------------------------------ page 4
R = D["RESOURCES"]
rows4 = [[r, str(h), str(n), f"+{n - h}", f"+{(n / h - 1) * 100:.0f}%"] for r, h, n in R]
ibb = [r for r, _, _ in R].index("Qualified burn bosses")
t4 = table("t4", [("r", "Resource", "text", 0.30), ("now", "In Service FY2026", "number", 0.215), ("need", "Peak Need FY2028", "number", 0.215),
                  ("gap", "Gap", "number", 0.12), ("pct", "Increase", "number", 0.15)], rows4,
           emphasis=[{"rows": [ibb], "fill_role": "keep", "bold": True}])
CD = D["CREW_DAYS"]
X4, Y4, W4, H4, GW = 0.02, 0.14, 0.90, 0.74, 1.30
fy = list(CD)
c4 = {"type": "COLUMN_CLUSTERED", "categories": fy, "number_format": "#,##0", "text": AX_TEXT,
      "series": [
          {"name": "Crew-days needed", "values": [CD[y][0] for y in fy], "fill_role": NEED, "line_role": "none",
           "labels": {"show": True, "position": "outside_end", "number_format": "#,##0", "role": "type.data_label", "ink_role": "color.ink"}},
          {"name": "Crew-days available", "values": [CD[y][1] for y in fy], "fill_role": TODAY, "line_role": "none",
           "labels": {"show": True, "position": "outside_end", "number_format": "#,##0", "role": "type.data_label", "ink_role": "color.ink"}}],
      "axes": {"category": cat_axis(), "value": {"visible": False, "min": 0, "max": 10000, "cross_between": "between"}},
      "gap_width": 130, "overlap": 0, "legend": legend("t"),  # GW
      "plot_area": {"x": X4, "y": Y4, "w": W4, "h": H4}, "plot_fill_role": "none", "title": "none"}
ann4 = []
# the shortfall bracket sits in the gap right of each pair; geometry from plot_area and gap_width
band = W4 / 3
bar = band / (2 + GW)
for i, y in enumerate(fy[:2]):
    n, a = CD[y]
    right = X4 + band * i + bar * GW / 2 + 2 * bar
    yv = lambda v: Y4 + H4 * (1 - v / 10000)
    ann4.append({"id": f"short{i}", "host": "c4", "kind": "mark", "prst": "rightBracket", "line_role": "color.ink", "line_width_pt": 1.25,
                 "anchor": {"box": [right + 0.006, yv(n), right + 0.02, yv(a)]},
                 "label": {"text": f"{n - a:,} short", "role": "type.emphasis", "ink_role": "color.ink", "align": "left",
                           "position": "right", "max_width_share": 0.07}, "gap_role": "space.sm"})
LS = D["LEAD_SORTED"]
c4b = {"type": "BAR_CLUSTERED", "categories": [r for r, _ in LS], "number_format": "0", "text": AX_TEXT,
       "series": [{"name": "Lead time (months)", "values": [v for _, v in LS], "fill_role": TODAY, "line_role": "none",
                   "labels": {"show": True, "position": "outside_end", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink"},
                   "points": [{"index": 0, "fill_role": NEED, "label": {"role": "type.emphasis"}}]}],
       "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 20, "cross_between": "between"}},
       "gap_width": 40, "overlap": 0, "legend": "none",
       "plot_area": {"x": 0.40, "y": 0.0, "w": 0.56, "h": 1.0}, "plot_fill_role": "none", "title": "none"}
F4 = ("capacity is 900 crew-days short in FY2027 and 1,500 at the FY2028 peak. Burn bosses are the tightest constraint: "
      "the plan needs 16, up 78% from 9, and each takes 18 months to qualify.")
N4 = "A crew-day is one crew working one day on treatment; engine crews count only days not held for fire response."
body4 = region("b4", flex("row", "space.gutter", align="stretch"), [
    region("b4-left", flex("column", "space.gutter"), [
        region("b4-t", flex("column", "space.sm"), [
            head("t4-head", "Crews and heavy equipment in service and needed", "Count of crews or machines"), t4]),
        region("b4-c", flex("column", "space.sm"), [
            head("c4-head", "Crew-days needed and available, by fiscal year", "Crew-days; navy is the plan's need, grey what crews can supply"),
            el("c4", "chart", weight=1.0)], weight=1.0)], weight=0.56),
    region("b4-right", flex("column", "space.lg"), [
        region("b4-lead", flex("column", "space.sm"), [
            head("c4b-head", "Lead time to add one unit", "Months, longest first"),
            el("c4b", "chart", weight=1.0)], weight=1.0),
        side("side4", F4, N4)], weight=0.44),
], weight=1.0)
s4 = page("p4-crews", "1_figure-standard", "RSFP.4", "Crews and Equipment: Statewide; FY2027-FY2029",
          body4, "Capacity falls 900 crew-days short in FY2027 and 1,500 in FY2028, and covers the need by FY2029 after hiring.")
s4["charts"] = {"c4": c4, "c4b": c4b}
s4["annotations"] = ann4
s4["styling"] = side_styling("side4", F4, N4)
slides.append(s4)
plan.append({"id": "p4-crews", "intent": "show the people and machines the plan needs and when capacity falls short",
             "message": "capacity is 1,500 crew-days short at the FY2028 peak and burn bosses, at 18 months to qualify, are the tightest constraint",
             "composition": "new:table-and-bars-over-columns", "title_register": "topic", "deliberate_parallel": None,
             "exhibits": [{"reader_must_see": "which resources have the largest gap between what is in service and what is needed",
                           "comparison": "in service against needed for six crew and equipment types",
                           "data": "two counts for each of six resources with the gap and percent increase",
                           "forms_considered": [
                               {"form": "table of counts with gap and increase columns", "reason": "chosen: small integers read exactly, gaps in their own column"},
                               {"form": "dumbbell chart of now and needed", "reason": "counts from 6 to 30 on one scale squash the small gaps that matter"}],
                           "chosen_form": "table of counts with gap and increase columns",
                           "why": "the reader plans hiring from exact counts",
                           "marks": "the burn boss row bold, the same resource that is highlighted in the lead-time bars",
                           "in_reference_look": "grey header table with a bold row for emphasis"},
                          {"reader_must_see": "burn bosses taking twice as long to add as any other resource",
                           "comparison": "months of lead time across the six resources, longest first",
                           "data": "one lead time in months for each of six resources",
                           "forms_considered": [
                               {"form": "horizontal bars sorted longest first", "reason": "chosen: one long bar at the top stands out"},
                               {"form": "a lead-time column in the table", "reason": "a sixth column hides the one outlier among small integers"}],
                           "chosen_form": "horizontal bars sorted longest first",
                           "why": "the claim is one outlier, which a bar length shows at once",
                           "marks": "the burn boss bar in navy with its value bold; the rest grey",
                           "in_reference_look": "its ranked horizontal bars with values at bar ends, no value axis, no gridlines"},
                          {"reader_must_see": "needed crew-days above available in FY2027 and FY2028, by 900 and 1,500",
                           "comparison": "needed against available crew-days in each plan year",
                           "data": "two values for each of three fiscal years in crew-days",
                           "forms_considered": [
                               {"form": "clustered columns with the shortfall bracketed", "reason": "chosen: the gap in each year reads as a height difference and the bracket says its size"},
                               {"form": "line of the shortfall alone", "reason": "hides the scale of the need behind the gap"}],
                           "chosen_form": "clustered columns with the shortfall bracketed",
                           "why": "the reader sees both size and shortfall per year",
                           "marks": "values on every column; brackets labelled 900 short and 1,500 short",
                           "in_reference_look": "columns with values and a legend above, no gridlines"}]})

# ------------------------------------------------------------------ page 5
S = D["SCHEDULE"]
stream_role = [TODAY, TODAY, METHOD_ROLE["Hand thinning"], METHOD_ROLE["Mechanical thinning"], METHOD_ROLE["Mastication"],
               METHOD_ROLE["Prescribed fire"], NEED, TODAY]
PX, PY, PW, PH = 0.36, 0.16, 0.63, 0.84
c5 = {"type": "BAR_STACKED", "categories": [s[0] for s in S], "number_format": "0", "text": AX_TEXT,
      "series": [
          {"name": "", "values": [s[1] for s in S], "fill_role": "none", "line_role": "none", "labels": {"show": False}},
          {"name": "Scheduled", "values": [s[2] for s in S], "fill_role": "color.accent1", "line_role": "none", "labels": {"show": False},
           "points": [{"index": i, "fill_role": r} for i, r in enumerate(stream_role)]}],
      "axes": {"category": cat_axis(reverse=True),
               "value": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": False, "min": 0, "max": 12, "major_unit": 1,
                         "number_format": "0", "cross_between": "between",
                         "gridlines": {"line_role": "color.slice_grey", "line_width_pt": 0.5},
                         "labels": {"show": False, "role": "type.axis_label", "ink_role": "color.ink"}, "title": "none"}},
      "gap_width": 45, "overlap": 100, "legend": "none",
      "plot_area": {"x": PX, "y": PY, "w": PW, "h": PH}, "plot_fill_role": "none", "title": "none"}
ann5 = []
yh = PY / 2
for y in range(3):
    x0 = PX + PW * (4 * y) / 12
    ann5.append({"id": f"yr{y}", "host": "c5", "kind": "mark", "prst": "rect", "fill_role": "color.accent2",
                 "line_role": "color.surface", "line_width_pt": 1.0,
                 "anchor": {"box": [x0, 0.0, x0 + PW * 4 / 12, yh - 0.005]},
                 "label": {"text": f"FY{2027 + y}", "role": "type.emphasis", "ink_role": "color.ink", "align": "center", "position": "inside"}})
for q in range(12):
    x0 = PX + PW * q / 12
    ann5.append({"id": f"q{q}", "host": "c5", "kind": "mark", "prst": "rect", "fill_role": "color.surface",
                 "anchor": {"box": [x0 + 0.003, yh, x0 + PW / 12 - 0.003, PY - 0.01]},
                 "label": {"text": f"Q{q % 4 + 1}", "role": "type.axis_label", "ink_role": "color.ink", "align": "center", "position": "inside"}})
PYR, YT = D["PLAN_YEARLY"], D["YEAR_TOTALS"]
rows5 = [[m] + [k1(x) for x in PYR[m]] + [k1(sum(PYR[m]))] for m in METHODS]
rows5.append(["All methods"] + [k1(x) for x in YT] + [k1(sum(YT))])
t5 = table("t5", [("m", "Method", "text", 0.36), ("y27", "FY2027", "number", 0.16), ("y28", "FY2028", "number", 0.16),
                  ("y29", "FY2029", "number", 0.16), ("tot", "Total", "number", 0.16)], rows5,
           emphasis=[{"rows": [4], "fill_role": "keep", "bold": True}])
F5 = ("mechanical thinning in Elk Ridge and Cedar Fork runs nine of the twelve quarters, Q3 of FY2027 to Q3 of FY2029. "
      "FY2027 treats 42.0 thousand acres while permits clear, then 59.0 a year, the FY2026 pace.")
N5 = ("Quarter 1 is July to September. Bar colours: the method colours of page 1; grey, preparation and monitoring; "
      "navy, the four smaller counties, which use all four methods.")
body5 = region("b5", flex("column", "space.lg"), [
    head("c5-head", "Work schedule by fiscal quarter, FY2027 to FY2029", "July 2026 to June 2029; each bar runs from the first to the last quarter of work"),
    el("c5", "chart", weight=1.0),
    region("b5-low", flex("row", "space.gutter", align="stretch"), [
        region("b5-t", flex("column", "space.sm"), [head("t5-head", "Planned acres by year", "Thousand acres"), t5], weight=0.62),
        side("side5", F5, N5, weight=0.38, anchor="b")]),
], weight=1.0)
s5 = page("p5-schedule", "1_figure-standard", "RSFP.5", "Treatment Schedule by Work Stream: FY2027-FY2029",
          body5, "The schedule front-loads permits and hiring; FY2028 and FY2029 each treat 59 thousand acres.")
s5["charts"] = {"c5": c5}
s5["annotations"] = ann5
s5["styling"] = side_styling("side5", F5, N5)
slides.append(s5)
plan.append({"id": "p5-schedule", "intent": "show when each work stream runs over the three plan years and how many acres each year treats",
             "message": "permits and hiring take the first year, so FY2027 treats 42.0 thousand acres and later years 59.0",
             "composition": "new:full-width-chart-over-table", "title_register": "topic", "deliberate_parallel": None,
             "exhibits": [{"reader_must_see": "the order of the work streams, which overlap in each quarter, and that mechanical thinning spans nine quarters",
                           "comparison": "start and length of eight work streams against the twelve quarters",
                           "data": "a start quarter and a length in quarters for each of eight tasks",
                           "forms_considered": [
                               {"form": "Gantt bars on a quarter grid with a year and quarter header", "reason": "chosen: start, length and overlap read along one time axis and quarters can be counted"},
                               {"form": "table of start and end quarters", "reason": "overlap between tasks has to be worked out"}],
                           "chosen_form": "Gantt bars on a quarter grid with a year and quarter header",
                           "why": "a schedule is read as bars along time, and the finding counts quarters",
                           "marks": "a two-row header of fiscal years and quarters; dashed lines at the year boundaries; bars coloured by method or phase",
                           "in_reference_look": "bars with labels at left, no value axis line, light rules only where they carry the count"},
                          {"reader_must_see": "planned acres by method in each plan year and the total",
                           "comparison": "acres per year and method against the three-year total",
                           "data": "four methods by three years with row and column totals",
                           "forms_considered": [
                               {"form": "table of acres by method and year", "reason": "chosen: exact plan figures to look up under the schedule"},
                               {"form": "stacked columns of acres by year", "reason": "a second chart competes with the schedule for height"}],
                           "chosen_form": "table of acres by method and year",
                           "why": "the figures are a lookup that ties to the plan total",
                           "marks": "total row bold",
                           "in_reference_look": "grey header, centred numbers at one decimal, bold total row"}]})

# ------------------------------------------------------------------ page 6
WP, WO, HY = D["WITH_PLAN"], D["WITHOUT"], D["HZ_YEARS"]
c6a = {"type": "LINE_MARKERS", "categories": HY, "number_format": "#,##0", "text": AX_TEXT,
       "series": [
           {"name": "Without the plan", "values": WO, "line_role": "color.ink_muted", "line_width_pt": 2.0, "dash": "dash", "smooth": False,
            "marker": {"style": "square", "size": 7, "fill_role": "color.ink_muted"},
            "labels": {"show": False}, "points": [{"index": 4, "label": {"show": True, "text": f"{WO[-1]:,}", "position": "above", "role": "type.emphasis", "ink_role": "color.ink"}}]},
           {"name": "With the plan", "values": WP, "line_role": PLAN, "line_width_pt": 2.5, "smooth": False,
            "marker": {"style": "circle", "size": 8, "fill_role": PLAN},
            "labels": {"show": False}, "points": [{"index": 4, "label": {"show": True, "text": f"{WP[-1]:,}", "position": "below", "role": "type.emphasis", "ink_role": "color.ink"}}]}],
       "axes": {"category": cat_axis(),
                "value": {"visible": True, "line_role": "color.ink", "line_width_pt": 1.0, "tick_marks": "none", "reverse": False,
                          "min": 0, "max": 1400, "major_unit": 200, "number_format": "#,##0", "gridlines": "none", "cross_between": "between",
                          "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"},
                          "title": {"text": "Thousand Acres", "role": "type.emphasis", "ink_role": "color.ink", "orientation": "along"}}},
       "legend": legend("t"),
       "plot_area": {"x": 0.13, "y": 0.17, "w": 0.64, "h": 0.73}, "plot_fill_role": "none", "title": "none"}
ann6 = [{"id": "gap", "host": "c6a", "kind": "bracket", "anchor": {"categories": [4, 4]}, "side": "right", "style": "square",
         "gap_role": "space.lg", "depth_role": "space.lg", "line_role": "color.ink", "line_width_pt": 1.0,
         "label": {"text": "229 thousand acres avoided", "role": "type.emphasis", "ink_role": "color.ink", "align": "left", "max_width_share": 0.21}}]
AV = D["AVOIDED"]
t6 = table("t6", [("p", "Path", "text", 0.28)] + [(y.lower(), y, "number", 0.144) for y in HY],
           [["Without the plan"] + [f"{v:,}" for v in WO], ["With the plan"] + [f"{v:,}" for v in WP],
            ["Acres avoided"] + [f"{v:,}" for v in AV]],
           emphasis=[{"rows": [2], "fill_role": "keep", "bold": True}])
S30 = D["share_2030"]
c6b = {"type": "BAR_CLUSTERED", "categories": names, "number_format": "0", "text": AX_TEXT,
       "series": [
           {"name": "FY2026", "values": [c[1] + c[2] for c in C], "fill_role": TODAY, "line_role": "none",
            "labels": {"show": True, "position": "outside_end", "number_format": "0\"%\"", "role": "type.data_label", "ink_role": "color.ink"}},
           {"name": "FY2030 with the plan", "values": [S30[n] for n in names], "fill_role": PLAN, "line_role": "none",
            "labels": {"show": True, "position": "outside_end", "number_format": "0\"%\"", "role": "type.data_label", "ink_role": "color.ink"}}],
       "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 70, "cross_between": "between"}},
       "gap_width": 40, "overlap": 0, "legend": "none",
       "plot_area": {"x": 0.22, "y": 0.0, "w": 0.74, "h": 1.0}, "plot_fill_role": "none", "title": "none"}
F6 = ("by FY2030 the plan holds high-hazard land to 1,098 thousand acres, 229 thousand (17.3%) below the path without treatment "
      "and 11.5% below today. Every county falls, by 3 to 21 points; none stays above 37%.")
body6 = region("b6", flex("column", "space.lg"), [
    region("b6-row", flex("row", "space.gutter"), [
        region("b6-l", flex("column", "space.sm"), [
            head("c6a-head", "Statewide land in high or very high hazard", "Thousand acres; without the plan, fuels keep growing about 1.7% a year"),
            el("c6a", "chart", weight=1.0), t6], weight=0.5),
        region("b6-r", flex("column", "space.sm"), [
            head("c6b-head", "Share of county land in high or very high hazard", "Percent of county land; counties in the order of page 2"),
            legend_row("key6b", [(TODAY, "FY2026"), (PLAN, "FY2030 with the plan")], width_in=6.18),
            el("c6b", "chart", weight=1.0)], weight=0.5),
    ], weight=1.0),
    text("finding6", [{"role": "type.footnote", "text": "Key finding: " + F6}]),
], weight=1.0)
s6 = page("p6-risk", "1_figure-standard", "RSFP.6", "Hazard Reduction Expected: Statewide; FY2026-FY2030",
          body6, "Without treatment, fuel growth adds about 1.7 percent a year to high-hazard land; the plan reverses it.")
s6["charts"] = {"c6a": c6a, "c6b": c6b}
s6["annotations"] = ann6
s6["styling"] = {"finding6": {"paragraphs": {"0": {"runs": [{"text": "Key finding:", "emphasis": True}, {"text": " " + F6}]}}}}
slides.append(s6)
plan.append({"id": "p6-risk", "intent": "show what the plan buys in hazard reduction, statewide and by county",
             "message": "by FY2030 high-hazard land is 229 thousand acres (17.3%) below the no-treatment path",
             "composition": "new:two-charts-side-by-side", "title_register": "topic", "deliberate_parallel": None,
             "exhibits": [{"reader_must_see": "the two paths parting after FY2026 and the 229 thousand acre gap at FY2030, on an axis from zero",
                           "comparison": "high-hazard acres with the plan against without it, year by year",
                           "data": "two series of five yearly values in thousand acres from one shared start",
                           "forms_considered": [
                               {"form": "two lines from a shared start on a zero-based axis, the end gap bracketed", "reason": "chosen: the gap is shown at its true size against the whole"},
                               {"form": "the same lines on an axis from 900", "reason": "exaggerates the divergence about fourfold, as the critic marked"},
                               {"form": "columns of the avoided acres per year", "reason": "drops the levels the reader compares with today"}],
                           "chosen_form": "two lines from a shared start on a zero-based axis, the end gap bracketed",
                           "why": "the claim is a difference between two paths, and its size must not be inflated",
                           "marks": "bracket at FY2030 labelled 229 thousand acres avoided; end values labelled; no-plan path dashed grey",
                           "in_reference_look": "lines with markers, value axis titled along the left, a legend above, no gridlines"},
                          {"reader_must_see": "the exact acres on each path and the acres avoided in each year",
                           "comparison": "the two paths year by year and their difference",
                           "data": "two paths and their difference for five years, thousand acres",
                           "forms_considered": [
                               {"form": "three-row table under the chart", "reason": "chosen: the zero-based chart shows the size, the table the values; the reference prints its plotted values under its trend charts"},
                               {"form": "data labels on every point", "reason": "the two lines run close at the start and ten labels would collide"}],
                           "chosen_form": "three-row table under the chart",
                           "why": "readers look up yearly values and the avoided row states the gap the bracket marks",
                           "marks": "the acres-avoided row bold",
                           "in_reference_look": "grey header table under the trend chart, as on its trend pages"},
                          {"reader_must_see": "every county's hazard share falling, most in Elk Ridge and Cedar Fork",
                           "comparison": "each county's share now against its share in FY2030",
                           "data": "two percentages for each of ten counties",
                           "forms_considered": [
                               {"form": "paired horizontal bars by county", "reason": "chosen: before and after sit side by side in the hazard rank of page 2"},
                               {"form": "table of reductions in points", "reason": "the size of the drop does not read without bars"}],
                           "chosen_form": "paired horizontal bars by county",
                           "why": "the claim is a drop in every county, read as two bar lengths",
                           "marks": "values at every bar end; county order kept from page 2; grey for today, teal for the plan as on every page",
                           "in_reference_look": "bars with values at bar ends and a legend above"}]})

if ONLY:
    slides = [s for s in slides if s["id"] in ONLY]
os.makedirs(os.path.join(W, "deck"), exist_ok=True)
deck = {"firm_chrome": {"chrome-1": {"image_path": os.path.join(W, "img", "ridgeline_bg.jpeg")}}, "slides": slides}
json.dump(deck, open(os.path.join(W, "deck", "deck.json"), "w"), indent=1)
guide = json.load(open(os.path.join(W, "ref", "guide.json")))
sha = guide["reference"].get("sha256")
json.dump({"schema": "pptx-skill section plan v2", "reference_sha256": sha, "pages": plan}, open(os.path.join(W, "plan.json"), "w"), indent=1)
print("slides", [s["id"] for s in slides], "sha", sha)
