import json, sys
SRC = "Source: client calls and desk research (rough estimates, illustrative); team analysis"
def T(i, role, text, **kw):
    p = {"role": role, "text": text}; p.update(kw); return p
def text(i, paras, **kw):
    e = {"type": "element", "id": i, "kind": "text", "paragraphs": paras}; e.update(kw); return e
def region(i, direction, children, gap="space.sm", pad=None, align="stretch", justify="start", **kw):
    r = {"type": "region", "id": i, "layout": {"kind": "flex", "direction": direction, "gap_role": gap, "pad_role": pad, "align": align, "justify": justify}, "children": children}
    r.update(kw); return r
def root(children, gap="space.sm"):
    r = region("root", "column", children, gap=gap)
    r["layout"]["pad_roles"] = {"left": "space.xl", "top": "space.sm", "right": "space.xl", "bottom": "space.sm"}
    del r["layout"]["pad_role"]
    return {"root": r}
def title(t): return text("title", [T("title", "type.title", t)])
def label(i, a, b): return text(i, [T(i, "type.exhibit_label", a), T(i, "type.unit_line", b)])
def source(extra=None):
    ps = [T("source", "type.source_line", SRC)]
    if extra: ps.append(T("source", "type.source_line", extra))
    return text("source", ps)
def chart(i, w=1.0): return {"type": "element", "id": i, "kind": "chart", "weight": w}
AX_LBL = {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}
slides = []

# 1 cover
slides.append({"id": "s1-cover", "layout": "Title Only",
 "chrome": {"chrome-4": {"omit": True, "why": "the reference's cover carries no page number"}},
 "title": {"register": "topic", "element": "title"},
 "spec": root([
   region("spacer-top", "column", [], weight=0.8),
   text("title", [T("title", "type.cover_title", "US cold-chain logistics"),
                  T("title", "type.h1", "Market sizing and where to play")]),
   {"type": "element", "id": "cover-rule", "kind": "rule", "size": {"width_emu": None, "height_emu": 25400}, "line_role": "color.accent3"},
   text("cover-sub", [T("cover-sub", "type.body_large", "Discussion document for the executive team"),
                      T("cover-sub", "type.body_large", "Preliminary: all figures are rough estimates from calls and desk research")]),
   region("spacer-bot", "column", [], weight=1.0),
   text("cover-date", [T("cover-date", "type.body_large", "November 2026", align="right")]),
 ])})

# 2 executive summary: navy label cells beside pale blue detail cells, as the reference's assumption tables
FIND = [
 ("Large and growing", "~$95bn in 2025 and ~$135bn by 2030: about 7% a year."),
 ("Pharma drives growth", "Pharma is 22% of the market but 35% of its growth: ~$21bn to ~$35bn, about 11% a year, on biologics and GLP-1."),
 ("Capacity is tight", "Public refrigerated warehouses run at ~82% utilisation, tightest in the Southeast and Texas; capacity grows ~4% a year."),
 ("Entry is capital-heavy", "New cold storage costs $220-260 per sq ft, about twice ambient; energy is 25-30% of operating cost."),
 ("Hypothesis to test", "Buy a regional 3PL for cold capability, then build pharma-grade sites near hubs. The numbers are rough and need bottom-up validation."),
]
rows = []
for n, (h, d) in enumerate(FIND):
    rows.append(region(f"f{n}", "row", [
        region(f"f{n}-h", "column", [text(f"f{n}-ht", [T("x", "type.body_large", h, ink_role="color.ink_inverse")])], weight=0.32, fill_role="color.accent2", pad="space.xs", justify="center"),
        region(f"f{n}-d", "column", [text(f"f{n}-dt", [T("x", "type.body_large", d)])], weight=0.68, fill_role="color.surface_alt", pad="space.xs", justify="center"),
    ], gap="space.xs" if False else None))
for r in rows: r["layout"]["gap_role"] = None
slides.append({"id": "s2-exec", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("Cold chain is an attractive, growing market; a pharma-led entry is the hypothesis to test"),
               region("findings", "column", rows, gap="space.xs", weight=1.0, justify="start")])})

# 3 market size bridge
slides.append({"id": "s3-size", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("US cold-chain logistics grows from ~$95bn to ~$135bn by 2030, about 7% a year"),
               label("lbl", "US cold-chain logistics market, 2025 to 2030", "$ billion"),
               chart("bridge"), source("Note: pharma covers 2-8°C and frozen; non-pharma is mostly food. Growth rate is the compound annual rate, 7.3%.")]),
 "charts": {"bridge": {
   "type": "COLUMN_STACKED", "categories": ["2025", "Non-pharma growth", "Pharma growth", "2030"],
   "number_format": "0", "text": {"role": "type.axis_label", "ink_role": "color.ink"},
   "series": [
     {"name": "", "values": [0, 95, 121, 0], "fill_role": "none", "line_role": "none", "labels": {"show": False}},
     {"name": "Value", "values": [95, 26, 14, 135], "fill_role": "color.accent2", "line_role": "none",
      "labels": {"show": True, "position": "inside_end", "role": "type.data_label", "ink_role": "color.ink_inverse"},
      "points": [{"index": 0, "label": {"text": "~95"}},
                 {"index": 1, "fill_role": "color.grey", "label": {"text": "+26"}},
                 {"index": 2, "fill_role": "color.emphasis", "label": {"text": "+14"}},
                 {"index": 3, "label": {"text": "~135"}}]}],
   "axes": {"category": {"visible": True, "line_role": "color.ink", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none", "title": "none", "labels": AX_LBL},
            "value": {"visible": False, "min": 0, "max": 160, "cross_between": "between"}},
   "gap_width": 60, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
   "plot_area": {"x": 0.04, "y": 0.12, "w": 0.92, "h": 0.78},
   "bridge": {"deltas": [95, 26, 14, 135], "totals": [0, 3]}}},
 "annotations": [{"id": "growth", "host": "bridge", "kind": "bracket", "anchor": {"categories": [1, 2]}, "side": "above",
   "gap_role": "space.xs", "depth_role": "space.xs", "line_role": "color.ink", "line_width_pt": 1.0, "style": "square",
   "label": {"text": "+$40bn, about 7% a year; pharma is 35% of it", "role": "type.data_label", "ink_role": "color.ink_muted", "align": "center"}}]})

# 4 mix
slides.append({"id": "s4-mix", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("Pharma is 22% of today's market but 35% of growth to 2030"),
   region("body", "row", [
     region("left", "column", [label("lbl", "Share of the market and of its growth", "percent; $ billion in brackets"), chart("mix")], weight=1.0, gap="space.xs"),
     region("right", "column", [
        text("n1", [T("n1", "type.exhibit_label", "Pharma: the fast segment"), T("n1", "type.unit_line", "~$21bn growing to ~$35bn, about 11% a year. Biologics and GLP-1 drugs need 2-8°C and frozen handling end to end.")]),
        text("n2", [T("n2", "type.exhibit_label", "Food: the volume base"), T("n2", "type.unit_line", "~70% of volume but only ~2-3% growth a year. It fills warehouses; it does not drive growth.")]),
     ], weight=0.85, gap="space.md")], gap="space.lg", weight=1.0),
   source()]),
 "charts": {"mix": {
   "type": "COLUMN_STACKED_100", "categories": ["2025 market ($95bn)", "Growth 2025-30 ($40bn)"],
   "number_format": "0", "text": {"role": "type.axis_label", "ink_role": "color.ink"},
   "series": [
     {"name": "Non-pharma", "values": [74, 26], "fill_role": "color.accent2", "line_role": "none",
      "labels": {"show": True, "position": "center", "role": "type.data_label", "ink_role": "color.ink_inverse"},
      "points": [{"index": 0, "label": {"text": "78%"}}, {"index": 1, "label": {"text": "65%"}}]},
     {"name": "Pharma", "values": [21, 14], "fill_role": "color.emphasis", "line_role": "none",
      "labels": {"show": True, "position": "center", "role": "type.data_label", "ink_role": "color.ink_inverse"},
      "points": [{"index": 0, "label": {"text": "22%"}}, {"index": 1, "label": {"text": "35%"}}]}],
   "axes": {"category": {"visible": True, "line_role": "color.ink", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none", "title": "none", "labels": AX_LBL},
            "value": {"visible": False}},
   "gap_width": 70, "overlap": 100, "legend": {"position": "t", "role": "type.data_label", "ink_role": "color.ink_muted"},
   "plot_fill_role": "none", "title": "none"}}})

# 5 capacity
yrs = ["2025", "2026", "2027", "2028", "2029", "2030"]
def end_label(t): return [{"index": 5, "label": {"show": True, "text": t}}]
def lseries(name, vals, role, t):
    return {"name": name, "values": vals, "line_role": role, "line_width_pt": 2.0, "smooth": False,
            "marker": {"style": "none"}, "labels": {"show": False, "position": "right", "role": "type.data_label", "ink_role": role},
            "points": end_label(t)}
slides.append({"id": "s5-capacity", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("Revenue is set to outgrow warehouse capacity, which already runs at ~82% utilisation"),
   label("lbl", "Revenue and warehouse capacity, indexed", "2025 = 100"), chart("idx"),
   source("Note: index paths compound the stated growth rates (pharma 10.8%, total 7.3%, capacity 4% a year). Revenue includes price; capacity is cubic feet, so the gap signals tightness and pricing power, not a measured shortfall.")]),
 "charts": {"idx": {
   "type": "LINE", "categories": yrs, "number_format": "0", "text": {"role": "type.axis_label", "ink_role": "color.ink"},
   "series": [lseries("Pharma revenue", [100.0, 110.8, 122.7, 135.9, 150.5, 166.7], "color.emphasis", "Pharma revenue 167"),
              lseries("Total revenue", [100.0, 107.3, 115.1, 123.5, 132.5, 142.1], "color.accent2", "Total revenue 142"),
              lseries("Warehouse capacity", [100.0, 104.0, 108.2, 112.5, 117.0, 121.7], "color.grey", "Capacity 122")],
   "axes": {"category": {"visible": True, "line_role": "color.ink", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none", "title": "none", "labels": AX_LBL},
            "value": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": False, "title": "none", "number_format": "0",
                      "min": 80, "max": 180, "major_unit": 20, "cross_between": "midpoint", "gridlines": {"line_role": "color.gridline", "line_width_pt": 0.75}, "labels": AX_LBL}},
   "legend": "none", "plot_fill_role": "none", "title": "none",
   "plot_area": {"x": 0.06, "y": 0.04, "w": 0.70, "h": 0.84}}},
 "annotations": [{"id": "util", "host": "idx", "kind": "arrow", "anchor": {"point": {"series": 2, "category": 3}},
   "line_role": "color.ink", "line_width_pt": 0.75, "position": "below_right", "gap_role": "space.sm",
   "label": {"text": "Public refrigerated warehouses already run at ~82% average utilisation, tightest in the Southeast and Texas", "role": "type.data_label", "ink_role": "color.ink_muted", "align": "left", "max_width_share": 0.32}}]})

# 6 cost
slides.append({"id": "s6-cost", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("Cold storage costs about twice as much as ambient to build; energy is 25-30% of opex"),
   region("body", "row", [
     region("left", "column", [label("lbl", "Build cost of a new warehouse", "$ per square foot"), chart("cost")], weight=1.0, gap="space.xs"),
     region("right", "column", [
       text("n1", [T("n1", "type.exhibit_label", "Capital: a $100-140 premium per sq ft"), T("n1", "type.unit_line", "Cold storage at $220-260 against ~$120 for ambient is 1.8x to 2.2x the cost to build.")]),
       text("n2", [T("n2", "type.exhibit_label", "Operations: energy is the main lever"), T("n2", "type.unit_line", "Energy is ~25-30% of opex. Ammonia or CO2 systems, on-site solar and thermal storage cut it.")]),
     ], weight=0.85, gap="space.md")], gap="space.lg", weight=1.0),
   source()]),
 "charts": {"cost": {
   "type": "BAR_STACKED", "categories": ["New ambient warehouse", "New cold storage"], "number_format": "0",
   "text": {"role": "type.axis_label", "ink_role": "color.ink"},
   "series": [{"name": "Low end", "values": [120, 220], "fill_role": "color.accent2", "line_role": "none", "labels": {"show": False},
               "points": [{"index": 0, "fill_role": "color.grey"}]},
              {"name": "Range to high end", "values": [0, 40], "fill_role": "color.emphasis", "line_role": "none", "labels": {"show": False}}],
   "axes": {"category": {"visible": True, "line_role": "color.ink", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none", "title": "none", "labels": AX_LBL},
            "value": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": False, "title": "none", "number_format": "\"$\"0",
                      "min": 0, "max": 300, "major_unit": 100, "cross_between": "between", "gridlines": {"line_role": "color.gridline", "line_width_pt": 0.75}, "labels": AX_LBL}},
   "gap_width": 60, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
   "plot_area": {"x": 0.32, "y": 0.12, "w": 0.46, "h": 0.74}}},
 "annotations": [{"id": "vals", "host": "cost", "kind": "category_row", "anchor": {"categories": [0, 1]}, "position": "right",
   "gap_role": "space.sm", "cells": ["$120", "$220-260"], "role": "type.data_label", "ink_role": "color.ink_muted", "align": "left", "cell_width": "own"}]})

# 7 options table
slides.append({"id": "s7-options", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("The three routes trade off capability, capital and exposure to pharma growth"),
   {"type": "element", "id": "opts", "kind": "table", "weight": 1.0, "table": {
     "columns": [{"key": "route", "label": "Route", "value_kind": "text", "width_share": 0.2},
                 {"key": "buys", "label": "What it buys", "value_kind": "text", "width_share": 0.2},
                 {"key": "growth", "label": "Exposure to growth", "value_kind": "text", "width_share": 0.2},
                 {"key": "capital", "label": "Capital and risk", "value_kind": "text", "width_share": 0.2},
                 {"key": "q", "label": "Question to answer first", "value_kind": "text", "width_share": 0.2}],
     "rows": [["1. Buy a regional 3PL", "Cold sites, customers and operating skills from day one", "Mostly food: ~70% of volume, ~2-3% growth", "Acquisition premium; integration into a freight forwarder", "Are there targets with pharma-grade sites near hubs?"],
              ["2. Greenfield pharma-grade sites near hubs", "New capacity where utilisation is tightest", "Direct: pharma grows ~11% a year", "$220-260 per sq ft to build; no cold track record", "Can we win pharma customers without a track record?"],
              ["3. Tech-enabled last mile", "A position in a fragmented segment: top 5 hold ~18%", "Not sized in our notes", "Lower capital per site; many small competitors", "How large is refrigerated last mile, and who pays for it?"]],
     "header_rows": 1},
        "emphasis": [{"columns": ["route"], "fill_role": "color.accent2", "ink_role": "color.ink_inverse", "bold": False}],
    "header_fill_role": "color.accent3", "cell_anchor": "m"},
   region("spacer", "column", [], weight=1.0),
   source()])})

# 8 answer
def col(i, head, paras):
    return region(i, "column", [region(i + "-hb", "column", [text(i + "-h", [T("h", "type.exhibit_label", head, ink_role="color.ink_inverse")])], pad="space.sm", fill_role="color.accent2"),
                                region(i + "-bb", "column", [text(i + "-b", [T("b", "type.body_large", p, bullet_level=0) for p in paras])], pad="space.sm", fill_role="color.surface_alt", weight=1.0)],
                  gap=None, weight=1.0)
slides.append({"id": "s8-answer", "layout": "Title Only", "title": {"register": "claim", "element": "title"},
 "spec": root([title("Hypothesis: buy a regional 3PL for capability, then build pharma-grade sites near hubs"),
   region("cols", "row", [
     col("c1", "Is it worth it?", ["On market grounds, yes: ~$95bn growing about 7% a year, pharma about 11%", "Capacity is tight at ~82% utilisation, which supports pricing", "Against it: build cost about 2x ambient and no cold capability in-house today"]),
     col("c2", "Where to play", ["Pharma-grade cold storage near hubs: a third of market growth, and the Southeast and Texas are tightest", "Enter by acquiring a regional 3PL for sites, staff and customers, then add greenfield pharma sites", "Treat tech-enabled last mile as a later option until it is sized"]),
     col("c3", "What we must measure next", ["Size the market bottom-up by segment and region; the current figures are rough", "Screen regional 3PL targets for pharma-grade sites and price", "Model site returns: build cost, energy at 25-30% of opex, utilisation", "Size refrigerated last mile"]),
   ], gap="space.sm", weight=1.0),
   source()])})

deck = {"firm_chrome": {"chrome-2": "drop", "chrome-3": {"text": "Cold-chain logistics market sizing | Illustrative, preliminary"}}, "slides": slides}
json.dump(deck, open(sys.argv[1], "w"), indent=1)
print("wrote", len(slides), "slides")
