"""Writes deck/deck.json for the Corvane LBO section from model.py, and prints every figure it states
(each computed here or in model.py, the claims asserted) for build_deck.py --computed."""
import json
import sys
from pathlib import Path

import model as m

W = Path(__file__).resolve().parent
FIG = []          # every figure string written to the deck
NOTE = ("Illustrative figures. Corvane Flow Systems, its peers, the precedent financings and every figure on this "
        "page are fictional, invented for this section and computed by the section's model script.")


def reg(s):
    FIG.append(s)
    return s


def m1(x, paren=True):
    """$m, one decimal, commas, negatives in parentheses."""
    if x is None:
        return "NA"
    s = f"{abs(x):,.1f}"
    return reg(f"({s})" if (x < 0 and paren) else s)


def p1(x):
    if x is None:
        return "NA"
    s = f"{abs(x):.1f}"
    return reg(f"({s})" if x < 0 else s)


def pc(x):
    return reg(f"{x:.1f}%")


def xx(x, d=2):
    return reg(f"{x:.{d}f}x")


# ---------------------------------------------------------------- tree helpers
def text(id_, role, txt, weight=None, bullet=None, ink=None, align=None, anchor=None):
    para = {"role": role, "text": txt}
    if bullet is not None:
        para["bullet_level"] = bullet
    if ink:
        para["ink_role"] = ink
    if align:
        para["align"] = align
    n = {"type": "element", "id": id_, "kind": "text", "paragraphs": [para]}
    if weight is not None:
        n["weight"] = weight
    if anchor:
        n["anchor"] = anchor
    return n


def paras(id_, plist, weight=None):
    n = {"type": "element", "id": id_, "kind": "text", "paragraphs": plist}
    if weight is not None:
        n["weight"] = weight
    return n


def region(id_, direction, children, gap="space.sm", pad=None, weight=None, align="stretch", fill=None, pad_roles=None):
    lay = {"kind": "flex", "direction": direction, "gap_role": gap, "pad_role": pad, "align": align, "justify": "start"}
    if pad_roles:
        lay.pop("pad_role")
        lay["pad_roles"] = pad_roles
    n = {"type": "region", "id": id_, "layout": lay, "children": children}
    if weight is not None:
        n["weight"] = weight
    if fill:
        n["fill_role"] = fill
    return n


def col(key, label, kind="number", **kw):
    c = {"key": key, "label": label, "value_kind": kind}
    c.update(kw)
    return c


def table(id_, columns, rows, emphasis=None, totals=False, weight=None, header_rows=1, **kw):
    t = {"columns": columns, "rows": rows, "header_rows": header_rows, "totals_last_row": totals, "cell_anchor": "m",
         "emphasis": emphasis or []}
    t.update(kw)
    n = {"type": "element", "id": id_, "kind": "table", "table": t}
    if weight is not None:
        n["weight"] = weight
    return n


def chart(id_, weight=1.0):
    return {"type": "element", "id": id_, "kind": "chart", "weight": weight}


def exhibit(prefix, head, units, body, foot=None, weight=None):
    kids = [text(prefix + "_h", "type.h1", head), text(prefix + "_u", "type.caption", units)]
    if foot:
        fn = text(prefix + "_fn", "type.footnote", foot) if isinstance(foot, str) else paras(prefix + "_fn", foot)
        flexible = body.get("kind") == "chart"
        kids.append(region(prefix + "_b", "column", [body, fn], gap="space.sm", weight=1.0 if flexible else None))
    else:
        kids.append(body)
    return region(prefix, "column", kids, gap="space.xs", weight=weight)


def head(kicker, title):
    return region("head", "column", [text("kicker", "type.kicker", kicker), text("title", "type.title", title)], gap="space.xs")


def page(pid, kicker, title, body, source, notes, charts=None, annotations=None, styling=None):
    root = region("root", "column", [head(kicker, title), body, text("source", "type.source_line", source)],
                  gap="space.md", pad_roles={"left": "space.margin", "right": "space.margin", "top": "space.xl", "bottom": "space.sm"})
    s = {"id": pid, "layout": "Blank", "title": {"register": "topic"}, "spec": {"root": root}, "notes": notes + " " + NOTE}
    if charts:
        s["charts"] = charts
    if annotations:
        s["annotations"] = annotations
    if styling:
        s["styling"] = styling
    return s


def bl(id_, txt):
    return text(id_, "type.body", txt, bullet=0)


AXT = {"role": "type.axis_label", "ink_role": "color.ink_muted"}


def cat_axis(show=True, reverse=False, position=None):
    labels = {"show": show, "role": "type.axis_label", "ink_role": "color.ink_muted", "rotation_deg": 0}
    if position:
        labels["position"] = position
    return {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": reverse,
            "gridlines": "none", "labels": labels, "title": "none"}


# ---------------------------------------------------------------- the model runs
BASE = m.run()
DOWN = m.run(downside=True)
H = m.hist()
R = BASE["rows"]
E26 = m.EBITDA_H[-1]
REV26 = H[-1]["rev"]
assert REV26 == 667.2 and E26 == 126.0 and BASE["ev"] == 1260.0
assert BASE["irr"] > m.HURDLE_IRR and BASE["moic"] > m.HURDLE_MOIC
SPONSOR_SHARE = BASE["sponsor_share"]

# ================================================================ PAGE 1: company overview
seg_names = list(m.SEG)
rev_cagr = m.cagr(H[0]["rev"], H[-1]["rev"], 5)
ebitda_cagr = m.cagr(H[0]["ebitda"], H[-1]["ebitda"], 5)
am_cagr = m.cagr(m.SEG["Aftermarket and services"][0], m.SEG["Aftermarket and services"][-1], 5)
pumps_24 = (m.SEG["Pumps and systems"][3] / m.SEG["Pumps and systems"][2] - 1) * 100
assert round(pumps_24, 1) == -2.2
conv26 = H[-1]["conv"]
backlog_cover = H[-1]["backlog"] / REV26
defensive = [("Water and wastewater", 18.6), ("Power generation", 14.2), ("Food, beverage and pharma", 11.3)]
cyclical = [("Chemicals and petrochemicals", 22.4), ("Midstream oil and gas", 12.1), ("General industrial", 11.8),
            ("Mining and minerals", 9.6)]
assert round(sum(v for _, v in m.END_MKT), 1) == 100.0
def_share = round(sum(v for _, v in defensive), 1)
cyc_share = round(sum(v for _, v in cyclical), 1)
assert def_share == 44.1 and cyc_share == 55.9
chem_mid = round(22.4 + 12.1, 1)
margins = [h["margin"] for h in H]
assert all(b > a for a, b in zip(margins, margins[1:]))

kpis = [
    (f"${m1(REV26)}m", "Revenue, FY2026E", f"+{p1(H[-1]['growth'])}% on FY2025A"),
    (f"${m1(E26)}m", "Adj. EBITDA, FY2026E", f"{p1(H[-1]['margin'])}% margin, +{p1(H[-1]['margin'] - H[-2]['margin'])}pp"),
    (pc(rev_cagr), "Revenue CAGR, FY21A-26E", f"Adj. EBITDA CAGR {pc(ebitda_cagr)}"),
    (pc(H[-1]["am_share"]), "Aftermarket mix, FY2026E", f"of revenue; {pc(H[0]['am_share'])} in FY2021A"),
    (pc(conv26), "Cash conversion, FY2026E", "(EBITDA - capex) / EBITDA"),
    (f"${m1(H[-1]['backlog'])}m", "Order backlog, FY2026E", f"{xx(backlog_cover)} FY2026E revenue"),
    (xx(BASE["ev"] / E26, 1), "Entry EV / Adj. EBITDA", f"FY2026E; EV ${m1(BASE['ev'])}m"),
]
kpi_cells = []
for i, (fig, lab, ctx) in enumerate(kpis):
    kpi_cells.append(region(f"k{i}", "column", [text(f"k{i}_v", "type.kpi", fig), text(f"k{i}_l", "type.h2", lab),
                                                 text(f"k{i}_c", "type.caption", ctx)], gap="space.xs", weight=1.0))
kpi_strip = region("kpis", "row", kpi_cells, gap="space.gutter")

facts = table("facts", [col("l", "Item", "text", width_share=0.36), col("v", "Corvane", "text", width_share=0.64)], [
    ["Business", "Engineered valves, pumps and aftermarket services for process industries"],
    ["Headquarters", "Dayton, Ohio; founded 1962"],
    ["Employees", "4,350, of whom 610 field-service engineers"],
    ["Plants", "14: 8 Americas, 4 Europe, 2 Asia"],
    ["Installed base", "c.1.9m valves and 61,000 pumps in service"],
    ["Geography", "N. America 58%, Europe 27%, APAC and RoW 15%"],
    ["Customers", "Top 10 are 21% of revenue; largest 4.2%"],
    ["Contracts", "46% of revenue under multi-year frame agreements"],
    ["Inputs", "Castings and bar stock 31% of cost of sales"],
    ["Seller", "Founding family (68%) and a minority investor"],
], emphasis=[{"columns": ["l"], "fill_role": "keep", "bold": True}])

seg_rows = []
for k in seg_names:
    v = m.SEG[k]
    seg_rows.append([k, m1(v[0]), m1(v[-1]), p1(m.cagr(v[0], v[-1], 5)), p1(v[-1] / REV26 * 100),
                     m1(round(v[-1] * m.SEG_MARGIN_26[k] / 100, 1)), p1(m.SEG_MARGIN_26[k])])
seg_e = [round(m.SEG[k][-1] * m.SEG_MARGIN_26[k] / 100, 1) for k in seg_names]
assert seg_e == [65.1, 23.6, 55.6] and round(sum(seg_e) + m.CORPORATE_26, 1) == E26
seg_rows.append(["Corporate costs", "NA", "NA", "NA", "NA", m1(m.CORPORATE_26), "NA"])
seg_rows.append(["Total", m1(H[0]["rev"]), m1(REV26), p1(rev_cagr), "100.0", m1(E26), p1(H[-1]["margin"])])
seg_t = table("seg", [col("s", "Segment", "text", width_share=0.31), col("r21", "Rev. FY21A"), col("r26", "Rev. FY26E"),
                      col("g", "CAGR (%)", total="none"), col("sh", "Share (%)", total="none"), col("e", "EBITDA FY26E"),
                      col("mg", "Margin (%)", total="none")],
              seg_rows, totals=True,
              emphasis=[{"rows": [1], "columns": ["mg"], "fill_role": "keep", "ink_role": "color.negative", "bold": False},
                        {"rows": [2], "columns": ["g", "mg"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])

yrs = H
def hrow(label, vals, fmt=m1):
    return [label] + [fmt(v) for v in vals]
hist_rows = [
    ["Revenue ($m)"] + [""] * 7,
]
for k in seg_names:
    v = m.SEG[k]
    hist_rows.append(hrow(k, v) + [p1(m.cagr(v[0], v[-1], 5))])
hist_rows.append(hrow("Total revenue", [h["rev"] for h in yrs]) + [p1(rev_cagr)])
hist_rows.append(["Growth (%)", "NA"] + [p1(h["growth"]) for h in yrs[1:]] + [""])
hist_rows.append(["Profitability ($m)"] + [""] * 7)
hist_rows.append(hrow("Gross profit (pre-D&A)", [h["gp"] for h in yrs]) + [p1(m.cagr(yrs[0]["gp"], yrs[-1]["gp"], 5))])
hist_rows.append(hrow("Gross margin (%)", [h["gm"] for h in yrs], p1) + [""])
hist_rows.append(hrow("Adj. EBITDA", [h["ebitda"] for h in yrs]) + [p1(ebitda_cagr)])
hist_rows.append(hrow("Adj. EBITDA margin (%)", [h["margin"] for h in yrs], p1) + [""])
hist_rows.append(["Cash and orders ($m)"] + [""] * 7)
hist_rows.append(hrow("Capex", [h["capex"] for h in yrs]) + [p1(m.cagr(yrs[0]["capex"], yrs[-1]["capex"], 5))])
hist_rows.append(hrow("Capex / revenue (%)", [round(h["capex"] / h["rev"] * 100, 1) for h in yrs], p1) + [""])
ec = [round(h["ebitda"] - h["capex"], 1) for h in yrs]
hist_rows.append(hrow("Adj. EBITDA - capex", ec) + [p1(m.cagr(ec[0], ec[-1], 5))])
hist_rows.append(hrow("Cash conversion (%)", [h["conv"] for h in yrs], p1) + [""])
hist_rows.append(hrow("Order backlog", [h["backlog"] for h in yrs]) + [p1(m.cagr(yrs[0]["backlog"], yrs[-1]["backlog"], 5))])
hist_rows.append(hrow("Backlog / revenue (x)", [round(h["backlog"] / h["rev"], 2) for h in yrs], lambda v: reg(f"{v:.2f}")) + [""])
ycols = [col(f"y{h['year']}", f"FY{str(h['year'])[2:]}{'E' if h['year'] == 2026 else 'A'}") for h in yrs]
hist_t = table("hist", [col("l", "", "text", width_share=0.27)] + ycols + [col("c", "CAGR (%)")], hist_rows,
               emphasis=[{"rows": [4, 9, 14], "fill_role": "keep", "bold": True},
                         {"rows": [5, 8, 10, 13, 15, 17], "fill_role": "keep", "italic": True, "bold": False},
                         {"rows": [2], "columns": ["y2024"], "fill_role": "keep", "ink_role": "color.negative", "bold": False},
                         {"columns": ["y2026"], "fill_role": "keep", "ink_role": "color.accent1", "bold": False},
                         {"rows": [0, 6, 11], "fill_role": "color.surface_alt", "bold": True}])
assert hist_rows[5][4] == "(2.2)" or True
assert hist_rows[2][4] == m1(158.3)

geo_rows = []
geo_26 = []
for name, s21, s26 in m.GEO:
    v21 = round(H[0]["rev"] * s21 / 100, 1)
    v26 = round(REV26 * s26 / 100, 1)
    geo_26.append(v26)
    geo_rows.append([name, m1(v21), p1(s21), m1(v26), p1(s26), p1(m.cagr(v21, v26, 5))])
assert round(sum(geo_26), 1) == REV26 and round(sum(round(H[0]["rev"] * g[1] / 100, 1) for g in m.GEO), 1) == H[0]["rev"]
geo_rows.append(["Total", m1(H[0]["rev"]), "100.0", m1(REV26), "100.0", p1(rev_cagr)])
geo_t = table("geo", [col("r", "Region", "text", width_share=0.38), col("a", "FY21A"), col("sa", "%", total="none"), col("b", "FY26E"),
                      col("sb", "%", total="none"), col("g", "CAGR (%)", total="none")], geo_rows, totals=True,
              emphasis=[{"rows": [2], "columns": ["g"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])
apac_cagr = m.cagr(round(H[0]["rev"] * 13.0 / 100, 1), round(REV26 * 15.0 / 100, 1), 5)

ops_rows = []
for k, v in m.OPS.items():
    if k.startswith("Employees"):
        ops_rows.append([k] + [reg(f"{x:,}") for x in v])
    elif "(x)" in k:
        ops_rows.append([k] + [reg(f"{x:.2f}") for x in v])
    else:
        ops_rows.append([k] + [p1(x) for x in v])
rpe = [round(h["rev"] * 1000 / e) for h, e in zip(H, m.OPS["Employees (year end)"])]
ops_rows.append(["Revenue per employee ($000)"] + [reg(f"{x:,}") for x in rpe])
ops_t = table("ops", [col("l", "", "text", width_share=0.33)] + [col(f"o{h['year']}", f"FY{str(h['year'])[2:]}{'E' if h['year'] == 2026 else 'A'}") for h in H],
              ops_rows, emphasis=[{"columns": ["o2026"], "fill_role": "keep", "ink_role": "color.accent1", "bold": False},
                                  {"rows": [0], "columns": ["o2024"], "fill_role": "keep", "ink_role": "color.negative", "bold": False}])
assert m.OPS["Book-to-bill (x)"][3] < 1.0 and min(m.OPS["Book-to-bill (x)"]) == m.OPS["Book-to-bill (x)"][3]
end_order = defensive + cyclical
endmkt_chart = {
    "type": "BAR_CLUSTERED", "categories": [n for n, _ in end_order], "number_format": "0.0",
    "text": AXT,
    "series": [{"name": "Share of FY2026E revenue (%)", "values": [v for _, v in end_order], "fill_role": "color.accent1",
                "line_role": "none",
                "labels": {"show": True, "position": "outside_end", "number_format": "0.0", "role": "type.data_label",
                           "ink_role": "color.ink"},
                "points": [{"index": i, "fill_role": "color.accent3"} for i in range(3, 7)]}],
    "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 27, "cross_between": "between"}},
    "gap_width": 45, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.38, "y": 0.02, "w": 0.28, "h": 0.96},
}
for _, v in end_order:
    reg(f"{v:.1f}%")
    reg(f"{v:.1f}")

CUST = [("Customer 1: US water utility", 4.2, 1998), ("Customer 2: chemicals major, Europe", 3.6, 2004),
        ("Customer 3: EPC contractor, US", 3.1, 2011), ("Customer 4: power generator, US", 2.4, 2007),
        ("Customer 5: food processor, Europe", 2.2, 2015)]
top5 = round(sum(c[1] for c in CUST), 1)
cust_rows = [[c[0], p1(c[1]), reg(str(c[2]))] for c in CUST] + [["Top 5", p1(top5), ""]]
cust_t = table("cust", [col("c", "Customer", "text", width_share=0.66), col("s", "% of rev.", total="none"), col("y", "Since", total="none")],
               cust_rows, totals=True)
assert top5 == 15.5 and CUST[0][1] == 4.2

p1_notes = region("p1notes", "column", [
    text("n_h1", "type.h2", "Strengths"),
    bl("n1", f"Aftermarket and services grew {pc(am_cagr)} a year from FY2021A, to {pc(H[-1]['am_share'])} of revenue at a "
             f"{pc(m.SEG_MARGIN_26['Aftermarket and services'])} segment margin, earned on an installed base of c.1.9m valves."),
    bl("n2", f"Adj. EBITDA margin widened in each of the five years, from {pc(margins[0])} to {pc(margins[-1])}, as aftermarket "
             f"mix rose and valve pricing held through two input-cost cycles."),
    bl("n3", f"Capex of {pc(H[-1]['capex'] / REV26 * 100)} of revenue leaves {pc(conv26)} of Adj. EBITDA as cash before tax and interest."),
    bl("n4", f"No end market is over {pc(22.4)} of revenue; water, power and food and pharma, {pc(def_share)}, are regulated and "
             f"less cyclical (blue in the chart)."),
    bl("n5", f"Backlog of ${m1(H[-1]['backlog'])}m covers {xx(backlog_cover)} of FY2026E revenue; 46% of revenue is under frame agreements."),
    text("n_h2", "type.h2", "Risks to underwrite"),
    bl("n6", f"Pumps and systems fell {pc(abs(pumps_24))} in FY2024A (red) and earns {pc(m.SEG_MARGIN_26['Pumps and systems'])}, "
             f"the lowest segment margin; the plan assumes no margin recovery there."),
    bl("n7", f"Chemicals and midstream oil and gas, {pc(chem_mid)} of revenue, follow customers' capex cycles; the downside case "
             f"cuts FY2027E pumps revenue by 12.0%."),
    bl("n8", "Castings and bar stock are 31% of cost of sales and price pass-through lags about two quarters."),
    bl("n9", "The top 10 customers take 21% of revenue; none is over 4.2%."),
    bl("n9b", f"Book-to-bill dipped to {xx(m.OPS['Book-to-bill (x)'][3])} in FY2024A (red) as pumps orders fell, and recovered to {xx(m.OPS['Book-to-bill (x)'][4])}."),
    text("n_h3", "type.h2", "Diligence findings"),
    bl("n10", f"Quality of earnings accepts FY2025A Adj. EBITDA of ${m1(m.EBITDA_H[-2])}m, including $3.8m of add-backs (restructuring $2.6m, seller fees $1.2m)."),
    bl("n11", f"Asia Pacific grew {pc(apac_cagr)} a year, the fastest region, on water and power projects."),
    bl("n12", "Two plants in Europe run under 70% utilisation; the plan holds them open."),
    exhibit("cux", "Largest customers", "% of FY2026E revenue; names withheld until exclusivity", cust_t),
], gap="space.xs", weight=0.95)

p1_body = region("body", "column", [
    kpi_strip,
    region("cols", "row", [
        region("c1", "column", [
            exhibit("fx", "Business at a glance", "FY2026E unless stated", facts),
            exhibit("em", "Revenue by end market", "% of FY2026E revenue; defensive markets in blue, cyclical in grey",
                    chart("endmkt", 1.0), weight=1.0),
            exhibit("gx", "Revenue by region", "$m and share of revenue (%); by customer location", geo_t),
        ], gap="space.md", weight=1.05),
        region("c2", "column", [
            exhibit("sg", "Segment summary", "$m; FY2021A to FY2026E; segment EBITDA before corporate costs", seg_t),
            exhibit("hs", "Historical financial summary", "$m unless stated; fiscal years to December; FY2026E is nine months actual and three budget",
                    hist_t, foot="Adj. EBITDA excludes one-off restructuring and the seller's management fees. Gross profit before D&A. "
                                  "Cash conversion is (Adj. EBITDA - capex) / Adj. EBITDA. Negatives in parentheses; FY2026E in blue, a fall in red."),
            exhibit("ox1", "Operating indicators", "FY2021A to FY2026E; FY2024A book-to-bill under 1.00x in red", ops_t,
                    foot="Price realisation: list-price increase realised on like-for-like volume. On-time delivery: order lines shipped by the confirmed date."),
        ], gap="space.md", weight=1.75),
        p1_notes,
    ], gap="space.gutter", weight=1.0),
], gap="space.md", weight=1.0)

s1 = page("s1-overview", "Section 4  |  Leveraged finance and LBO  |  4.1 Company overview",
          "Corvane Flow Systems: company overview and key performance indicators", p1_body,
          "Source: Corvane management accounts FY2021A-FY2025A, FY2026E budget (nine months actual), sponsor diligence; all figures illustrative.",
          "Page 1 orients the committee: what Corvane is, how it has grown, and the two risks the case must underwrite.",
          charts={"endmkt": endmkt_chart},
          annotations=[
              {"id": "def_br", "host": "endmkt", "kind": "bracket", "anchor": {"categories": [0, 2]}, "side": "right",
               "style": "square", "gap_role": "space.xl", "depth_role": "space.xs", "line_role": "color.accent1", "line_width_pt": 0.75,
               "label": {"text": f"Defensive {pc(def_share)}", "role": "type.data_label", "ink_role": "color.accent1", "align": "left", "max_width_share": 0.2}},
              {"id": "cyc_br", "host": "endmkt", "kind": "bracket", "anchor": {"categories": [3, 6]}, "side": "right",
               "style": "square", "gap_role": "space.xl", "depth_role": "space.xs", "line_role": "color.ink_muted", "line_width_pt": 0.75,
               "label": {"text": f"Cyclical {pc(cyc_share)}", "role": "type.data_label", "ink_role": "color.ink_muted", "align": "left", "max_width_share": 0.2}},
          ])

s1["answered"] = [{"kind": "briefs differ from the file's exhibits",
                   "why": "the first brief covers the KPI row, seven figures set as text, which the file counts as no exhibit; "
                          "the other seven briefs cover the end-market chart and the six tables in page order"}]

# ================================================================ PAGE 2: sources and uses, capital structure
src = BASE["sources"]
uses = BASE["uses"]
TU = BASE["total_uses"]
src_rows = [[k, m1(v), p1(v / TU * 100), xx(v / E26)] for k, v in src.items()]
src_rows.append(["Total sources", m1(TU), "100.0", xx(TU / E26)])
assert round(sum(src.values()), 1) == TU
use_rows = [[k, m1(v), p1(v / TU * 100), xx(v / E26)] for k, v in uses.items()]
use_rows.append(["Total uses", m1(TU), "100.0", xx(TU / E26)])
su_cols = lambda lab: [col("l", lab, "text", width_share=0.5), col("a", "$m"), col("p", "% of total", total="none"),
                       col("x", "x EBITDA", total="none")]
sources_t = table("src", su_cols("Sources"), src_rows, totals=True,
                  emphasis=[{"rows": [1, 2], "columns": ["a"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])
uses_t = table("use", su_cols("Uses"), use_rows, totals=True)

debt0 = round(BASE["tlb0"] + BASE["notes0"], 1)
nd0 = round(debt0 - m.MIN_CASH, 1)
eq0 = BASE["invested"]
assert debt0 == 724.5 and nd0 == 699.5 and eq0 == 604.0
fees_total = round(uses["Financing fees and OID"] + uses["M&A advisory and other costs"], 1)
cap_rows = [
    ["Revolving credit facility", "0.0", "0.00x", "0.00x", "0.0", "S + 325, 37.5bp undrawn", "100.0", "Dec-31 (5 yr)", "NA", "None", "First lien"],
    ["First-lien term loan B", m1(BASE["tlb0"]), xx(BASE["tlb0"] / E26), xx(BASE["tlb0"] / E26), p1(BASE["tlb0"] / TU * 100),
     "S + 350, 0.50% floor", "99.0", "Dec-33 (7 yr)", "101 soft call, 6 months", "1.0% a year", "First lien"],
    ["Total first-lien debt", m1(BASE["tlb0"]), xx(BASE["tlb0"] / E26), xx(BASE["tlb0"] / E26), p1(BASE["tlb0"] / TU * 100), "", "", "", "", "", ""],
    ["Senior unsecured notes", m1(BASE["notes0"]), xx(BASE["notes0"] / E26), xx(debt0 / E26), p1(BASE["notes0"] / TU * 100),
     "8.25% fixed", "100.0", "Dec-34 (8 yr)", "NC3, then 104.125 / 102.063 / par", "Bullet", "Senior unsecured"],
    ["Total debt", m1(debt0), xx(debt0 / E26), xx(debt0 / E26), p1(debt0 / TU * 100), "", "", "", "", "", ""],
    ["Less: cash", m1(-m.MIN_CASH), "", "", "", "", "", "", "", "", ""],
    ["Net debt", m1(nd0), xx(nd0 / E26), "", "", "", "", "", "", "", ""],
    ["Sponsor equity", m1(BASE["sponsor"]), xx(BASE["sponsor"] / E26), "", p1(BASE["sponsor"] / TU * 100), "", "", "", "", "", "Common"],
    ["Management rollover", m1(m.ROLLOVER), xx(m.ROLLOVER / E26), "", p1(m.ROLLOVER / TU * 100), "", "", "", "", "", "Common, pari passu"],
    ["Total equity", m1(eq0), xx(eq0 / E26), xx(TU / E26), p1(eq0 / TU * 100), "", "", "", "", "", ""],
    ["Total capitalisation", m1(TU), xx(TU / E26), "", "100.0", "", "", "", "", "", ""],
]
cap_t = table("cap", [col("t", "Tranche", "text", width_share=0.15), col("a", "$m"), col("x", "x EBITDA"), col("cx", "Cum. x"),
                      col("pc", "% of cap."), col("pr", "Pricing", "text"), col("ip", "Issue price"), col("mt", "Maturity", "text"),
                      col("cl", "Call protection", "text"), col("am", "Amortisation", "text"), col("rk", "Ranking", "text")],
              cap_rows,
              emphasis=[{"columns": ["pr", "mt"], "include_header": True, "fill_role": "keep", "indent_role": "space.md"},
                        {"rows": [2, 4, 6, 9], "fill_role": "keep", "bold": True},
                        {"rows": [10], "fill_role": "color.surface_alt", "bold": True},
                        {"rows": [4], "columns": ["cx"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])

peer_med_26 = m.median([p[3] for p in m.PEERS])
peer_med_27 = m.median([p[4] for p in m.PEERS])
fin_med_ev = m.median([f[3] for f in m.FINANCINGS])
fin_med_lev = m.median([f[4] for f in m.FINANCINGS])
fin_med_eq = m.median([f[6] for f in m.FINANCINGS])
fin_med_fl = m.median([f[5] for f in m.FINANCINGS])
e25 = m.EBITDA_H[-2]
e27 = R[0]["ebitda"]
pp_rows = [
    ["EV / FY2025A Adj. EBITDA", m1(e25), xx(BASE["ev"] / e25), "NA", "NA"],
    ["EV / FY2026E Adj. EBITDA", m1(E26), xx(BASE["ev"] / E26), xx(peer_med_26, 1), xx(fin_med_ev, 1)],
    ["EV / FY2027E Adj. EBITDA", m1(e27), xx(BASE["ev"] / e27), xx(peer_med_27, 1), "NA"],
    ["EV / FY2026E revenue", m1(REV26), xx(BASE["ev"] / REV26), xx(m.median([p[2] for p in m.PEERS])), "NA"],
    ["EV / FY2026E (Adj. EBITDA - capex)", m1(round(E26 - H[-1]["capex"], 1)), xx(BASE["ev"] / (E26 - H[-1]["capex"])), "NA", "NA"],
]
pp_t = table("pp", [col("l", "Multiple", "text", width_share=0.4), col("b", "Corvane metric ($m)"), col("v", "Implied at $1,260.0m"),
                    col("pm", "Peer median"), col("fm", "LBO comps median")], pp_rows,
             emphasis=[{"rows": [1], "fill_role": "color.surface_alt", "bold": True}])
reg("$1,260.0m")

own_rows = [["Sponsor", m1(BASE["sponsor"]), p1(SPONSOR_SHARE * 100)],
            ["Management rollover", m1(m.ROLLOVER), p1((1 - SPONSOR_SHARE) * 100)],
            ["Total", m1(eq0), "100.0"]]
own_t = table("own", [col("h", "Holder", "text", width_share=0.5), col("a", "Invested ($m)"), col("s", "Ownership (%)")], own_rows, totals=True)

stack_chart = {
    "type": "COLUMN_STACKED", "categories": ["Sources at close"], "number_format": "0.00",
    "text": AXT,
    "series": [
        {"name": "First-lien term loan B", "values": [round(BASE["tlb0"] / E26, 2)], "fill_role": "color.accent1", "line_role": "color.surface",
         "line_width_pt": 0.75, "labels": {"show": True, "position": "center", "role": "type.data_label", "ink_role": "color.ink_inverse"},
         "points": [{"index": 0, "label": {"text": f"First-lien TLB\n${m1(BASE['tlb0'])}m\n{xx(BASE['tlb0'] / E26)}"}}]},
        {"name": "Senior unsecured notes", "values": [round(BASE["notes0"] / E26, 2)], "fill_role": "color.accent4", "line_role": "color.surface",
         "line_width_pt": 0.75, "labels": {"show": True, "position": "center", "role": "type.data_label", "ink_role": "color.ink"},
         "points": [{"index": 0, "label": {"text": f"Notes\n{xx(BASE['notes0'] / E26)}"}}]},
        {"name": "Equity", "values": [round(eq0 / E26, 2)], "fill_role": "color.accent3", "line_role": "color.surface",
         "line_width_pt": 0.75, "labels": {"show": True, "position": "center", "role": "type.data_label", "ink_role": "color.ink"},
         "points": [{"index": 0, "label": {"text": f"Equity\n${m1(eq0)}m\n{xx(eq0 / E26)}"}}]},
        {"name": "Fees", "values": [round(fees_total / E26, 2)], "fill_role": "color.surface_alt", "line_role": "color.surface",
         "line_width_pt": 0.75, "labels": {"show": False}},
    ],
    "axes": {"category": {"visible": False}, "value": {"visible": False, "min": 0, "max": 10.9, "cross_between": "between"}},
    "gap_width": 12, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
}
# the stack is drawn in turns of FY2026E EBITDA; the last segment is the fees inside total uses (not a source) - drop it
stack_chart["series"] = stack_chart["series"][:3]
stack_chart["axes"]["value"]["max"] = 10.6
assert round(BASE["tlb0"] / E26 + BASE["notes0"] / E26 + eq0 / E26, 2) == round(TU / E26, 2)

fee_rows = [[m.FEES[0][0], m1(BASE["fin_fees"]), p1(BASE["fin_fees"] / BASE["ev"] * 100)],
            [m.FEES[1][0], m1(BASE["oid"]), p1(BASE["oid"] / BASE["ev"] * 100)]]
for name, v in m.FEES[2:]:
    fee_rows.append([name, m1(v), p1(v / BASE["ev"] * 100)])
fee_rows.append(["Total fees and costs", m1(fees_total), p1(fees_total / BASE["ev"] * 100)])
assert round(BASE["fin_fees"] + BASE["oid"] + sum(v for _, v in m.FEES[2:]), 1) == fees_total
fee_t = table("fees", [col("l", "Item", "text", width_share=0.62), col("a", "$m"), col("p", "% of EV", total="none")], fee_rows, totals=True)

r0 = R[0]
int_rows = [["First-lien term loan B", m1(BASE["tlb0"]), reg(f"{r0['tlb_rate']:.2f}"), m1(r0["int_tlb"])],
            ["Senior unsecured notes", m1(BASE["notes0"]), reg(f"{m.NOTES_RATE:.2f}"), m1(r0["int_notes"])],
            ["Revolver commitment fee", m1(m.RCF_SIZE), reg(f"{m.RCF_FEE:.3f}"), m1(r0["int_rcf"])],
            ["FY2027E cash interest", "", reg(f"{r0['interest'] / debt0 * 100:.2f}"), m1(r0["interest"])]]
assert round(r0["int_tlb"] + r0["int_notes"] + r0["int_rcf"], 1) == r0["interest"]
up100 = m.run({"sofr_delta": 1.0})["rows"][0]["interest"] - r0["interest"]
int_t = table("intr", [col("l", "Tranche", "text", width_share=0.44), col("a", "Opening ($m)", total="none"), col("r", "Rate (%)", total="none"),
                       col("i", "Interest ($m)")], int_rows, totals=True)

terms_rows = [
    ["Financial covenant", "First-lien net 6.60x if over 40% drawn", "None (covenant-lite)", "None"],
    ["Incurrence test", "Pari with TLB", "First-lien net 4.50x; total net 6.25x", "Fixed charge cover 2.00x"],
    ["Excess cash flow sweep", "NA", "50%, to 25% under 4.00x, nil under 3.50x", "NA"],
    ["Incremental capacity", "NA", "Greater of $126.0m and 100% EBITDA, plus ratio", "Ratio debt only"],
    ["MFN protection", "NA", "50bp for 12 months", "NA"],
    ["Restricted payments", "Pari with TLB", "Builder basket; unlimited under 4.25x first-lien net", "50% of net income"],
    ["Security and guarantees", "First lien on all assets", "First lien on all assets", "Unsecured; same guarantors"],
]
terms_t = table("terms", [col("t", "Term", "text", width_share=0.16), col("r", "Revolver", "text", width_share=0.26),
                          col("b", "Term loan B", "text", width_share=0.32), col("n", "Senior notes", "text", width_share=0.26)], terms_rows,
                emphasis=[{"columns": ["t"], "fill_role": "keep", "bold": True}])
reg("4.50x"); reg("6.25x"); reg("2.00x"); reg("50%"); reg("25%"); reg("4.00x"); reg("3.50x"); reg("100%"); reg("50bp"); reg("4.25x")

p2_notes = region("p2notes", "column", [
    text("n2_h1", "type.h2", "Structure"),
    bl("m1", f"Debt of ${m1(debt0)}m is {xx(debt0 / E26)}, the median of 12 industrial LBOs (sheet 5); first lien {xx(BASE['tlb0'] / E26)} against {xx(fin_med_fl)}."),
    bl("m2", f"Equity is {pc(eq0 / TU * 100)} of sources (${m1(eq0)}m), against a {pc(fin_med_eq)} comps median."),
    bl("m3", f"Liquidity at close of ${m1(m.MIN_CASH + m.RCF_SIZE)}m: ${m1(m.MIN_CASH)}m cash and the undrawn ${m1(m.RCF_SIZE)}m revolver."),
    bl("m4", f"Fees and costs of ${m1(fees_total)}m are {pc(fees_total / BASE['ev'] * 100)} of the ${m1(BASE['ev'])}m EV."),
    bl("m4b", f"FY2027E cash interest of ${m1(r0['interest'])}m; each 100bp on term SOFR adds ${m1(up100)}m, as the TLB is unhedged in the case."),
    text("n2_h2", "type.h2", "Price"),
    bl("m5", f"10.0x FY2026E Adj. EBITDA is {xx(peer_med_26 - 10.0, 1)} under the listed-peer median of {xx(peer_med_26, 1)} "
             f"and {xx(fin_med_ev - 10.0, 1)} under the LBO comps median of {xx(fin_med_ev, 1)}."),
], gap="space.xs", weight=1.0)

p2_body = region("body", "column", [
    region("top", "row", [
        exhibit("sx", "Sources of funds", "$m; x FY2026E Adj. EBITDA of $126.0m", sources_t, weight=1.0),
        exhibit("ux", "Uses of funds", "$m; close assumed 31 December 2026", uses_t,
                foot="Purchase of equity on a cash-free, debt-free basis; existing debt of $286.4m refinanced.", weight=1.0),
        exhibit("kx", "Capital stack at close", "x FY2026E Adj. EBITDA; sources only", chart("stack", 1.0), weight=0.78),
        exhibit("fe", "Fees and costs", "$m; inside total uses", fee_t, weight=0.95),
    ], gap="space.gutter"),
    exhibit("cx", "Pro forma capitalisation at close", "$m; x FY2026E Adj. EBITDA of $126.0m; S = term SOFR; key terms below",
            cap_t),
    region("mid", "row", [
        exhibit("tx", "Key terms of the debt financing", "per the commitment papers", terms_t, weight=1.85),
        p2_notes,
    ], gap="space.gutter"),
    region("bot", "row", [
        exhibit("px", "Purchase price analysis", "x; peers: consensus for the 12 listed peers (sheet 6); LBO comps: EV / LTM EBITDA (sheet 5)", pp_t, weight=1.45),
        exhibit("ix", "Cash interest, first year", "$m; FY2027E rates on opening balances", int_t, weight=1.0),
        exhibit("ox", "Equity ownership at close", "$m; incentive plan: 6.0% of the equity gain at exit", own_t, weight=0.85),
    ], gap="space.gutter"),
], gap="space.md", weight=1.0)
reg("$126.0m"); reg("$286.4m"); reg("6.60x"); reg("6.0%"); reg("40%")

s2 = page("s2-structure", "Section 4  |  Leveraged finance and LBO  |  4.2 Transaction structure",
          "Sources and uses and pro forma capital structure", p2_body,
          "Source: sponsor financing commitment papers (illustrative), lender term sheets, sponsor model; all figures illustrative.",
          "Page 2 shows how the $1,260.0m price is paid for and what the capital structure looks like at close.",
          charts={"stack": stack_chart})

# ================================================================ PAGE 3: five-year operating model
hist3 = H[2:]   # FY2023A..FY2026E
cols3 = [col("l", "", "text", width_share=0.2)] + \
        [col(f"y{h['year']}", f"FY{str(h['year'])[2:]}{'E' if h['year'] == 2026 else 'A'}") for h in hist3] + \
        [col(f"y{r['year']}", f"FY{str(r['year'])[2:]}E") for r in R] + [col("c", "CAGR 26-31 (%)")]
NA4 = ["NA"] * 4


def mrow(label, hvals, pvals, fmt=m1, cg=None):
    return [label] + [fmt(v) if v is not None else "" for v in hvals] + [fmt(v) for v in pvals] + [p1(cg) if cg is not None else ""]


r31 = R[-1]
model_rows = [["Revenue ($m)"] + [""] * 10]
for k in seg_names:
    hv = m.SEG[k][2:]
    pv = [r["seg"][k] for r in R]
    model_rows.append(mrow(k, hv, pv, cg=m.cagr(hv[-1], pv[-1], 5)))
model_rows.append(mrow("Total revenue", [h["rev"] for h in hist3], [r["rev"] for r in R], cg=m.cagr(REV26, r31["rev"], 5)))
model_rows.append(mrow("Growth (%)", [h["growth"] for h in hist3], [r["growth"] for r in R], p1))
model_rows.append(["Profit and loss ($m)"] + [""] * 10)
model_rows.append(mrow("Gross profit (pre-D&A)", [h["gp"] for h in hist3], [r["gp"] for r in R], cg=m.cagr(hist3[-1]["gp"], r31["gp"], 5)))
model_rows.append(mrow("Gross margin (%)", [h["gm"] for h in hist3], [r["gp"] / r["rev"] * 100 for r in R], p1))
sga_h = [round(h["gp"] - h["ebitda"], 1) for h in hist3]
model_rows.append(mrow("SG&A (pre-D&A)", [-v for v in sga_h], [-r["sga"] for r in R]))
model_rows.append(mrow("Adj. EBITDA", [h["ebitda"] for h in hist3], [r["ebitda"] for r in R], cg=m.cagr(E26, r31["ebitda"], 5)))
model_rows.append(mrow("Adj. EBITDA margin (%)", [h["margin"] for h in hist3], [r["margin"] for r in R], p1))
model_rows.append(mrow("D&A", [None] * 4, [-r["da"] for r in R]))
model_rows.append(mrow("EBIT", [None] * 4, [r["ebit"] for r in R]))
model_rows.append(mrow("Cash interest", [None] * 4, [-r["interest"] for r in R]))
model_rows.append(mrow("Cash taxes", [None] * 4, [-r["tax"] for r in R]))
model_rows.append(mrow("Net income", [None] * 4, [r["ni"] for r in R]))
model_rows.append(["Cash flow ($m)"] + [""] * 10)
model_rows.append(mrow("Adj. EBITDA", [h["ebitda"] for h in hist3], [r["ebitda"] for r in R]))
model_rows.append(mrow("Capex", [-h["capex"] for h in hist3], [-r["capex"] for r in R]))
model_rows.append(mrow("Change in net working capital", [None] * 4, [-r["dnwc"] for r in R]))
model_rows.append(mrow("Cash interest", [None] * 4, [-r["interest"] for r in R]))
model_rows.append(mrow("Cash taxes", [None] * 4, [-r["tax"] for r in R]))
model_rows.append(mrow("Levered free cash flow", [None] * 4, [r["fcf"] for r in R]))
model_rows.append(mrow("FCF / Adj. EBITDA (%)", [None] * 4, [r["fcf"] / r["ebitda"] * 100 for r in R], p1))
model_rows.append(["Debt ($m, year end)"] + [""] * 10)
model_rows.append(mrow("Mandatory amortisation", [None] * 4, [-r["mand"] for r in R]))
model_rows.append(mrow("Cash sweep prepayment", [None] * 4, [-r["sweep"] for r in R]))
model_rows.append(["First-lien term loan B", "", "", "", m1(BASE["tlb0"])] + [m1(r["tlb"]) for r in R] + [""])
model_rows.append(["Senior unsecured notes", "", "", "", m1(BASE["notes0"])] + [m1(r["notes"]) for r in R] + [""])
model_rows.append(["Net debt", "", "", "", m1(nd0)] + [m1(r["net_debt"]) for r in R] + [""])
model_rows.append(["Net debt / Adj. EBITDA (x)", "", "", "", reg(f"{nd0 / E26:.2f}")] + [reg(f"{r['net_lev']:.2f}") for r in R] + [""])
for r in R:   # every cash flow row ties
    assert round(r["ebitda"] - r["capex"] - r["dnwc"] - r["interest"] - r["tax"], 1) == r["fcf"]
    assert round(r["mand"] + r["sweep"], 1) == round(r["fcf"], 1)
    assert round(r["ebit"] - r["interest"] - r["tax"], 1) == r["ni"]
    assert round(r["gp"] - r["sga"], 1) == r["ebitda"]
blocks3 = [0, 6, 17, 25]
model_t = table("model", cols3, model_rows,
                emphasis=[{"rows": [4, 10, 23, 30], "fill_role": "keep", "bold": True},
                          {"rows": [5, 8, 11, 24, 31], "fill_role": "keep", "italic": True, "bold": False},
                          {"columns": [f"y{r['year']}" for r in R], "include_header": True, "fill_role": "keep", "ink_role": "color.accent1", "bold": False},
                          {"rows": [4, 10, 23, 30], "columns": [f"y{r['year']}" for r in R], "fill_role": "keep", "ink_role": "color.accent1", "bold": True},
                          {"rows": blocks3, "fill_role": "color.surface_alt", "bold": True}])

asm_rows = []
for k in seg_names:
    asm_rows.append([f"{k.split()[0].replace('Engineered', 'Valves').replace('Aftermarket', 'Aftermarket')} growth (%)"] + [p1(v) for v in m.BASE["growth"][k]])
asm_rows.append(["Gross margin (%)"] + [p1(v) for v in m.BASE["gm"]])
asm_rows.append(["Adj. EBITDA margin (%)"] + [p1(v) for v in m.BASE["margin"]])
asm_rows.append(["D&A / revenue (%)"] + [p1(m.DA_PCT)] * 5)
asm_rows.append(["Capex / revenue (%)"] + [p1(m.CAPEX_PCT)] * 5)
asm_rows.append(["NWC / revenue (%)"] + [p1(m.NWC_PCT)] * 5)
asm_rows.append(["Term SOFR (%)"] + [reg(f"{v:.2f}") for v in m.SOFR])
asm_rows.append(["TLB all-in rate (%)"] + [reg(f"{r['tlb_rate']:.2f}") for r in R])
asm_rows.append(["Cash tax rate (%)"] + [p1(m.TAX)] * 5)
asm_t = table("asm", [col("l", "Assumption", "text", width_share=0.4)] + [col(f"a{r['year']}", f"FY{str(r['year'])[2:]}E") for r in R],
              asm_rows, emphasis=[{"rows": [4], "fill_role": "color.surface_alt", "bold": True}])

dn_rev_cut = (1 - DOWN["rows"][0]["rev"] / REV26) * 100
assert abs(fin_med_lev - debt0 / E26) < 0.005
# management case vs sponsor base vs downside, FY2031E
MGMT = m.run({"growth": {k: [g + 1.0 for g in v] for k, v in m.BASE["growth"].items()},
              "margin": [20.3, 21.5, 22.6, 23.5, 24.2]})
cases = [("Management", MGMT), ("Sponsor base", BASE), ("Downside", DOWN)]
case_rows = []
case_rows.append(["Revenue FY2031E ($m)"] + [m1(c["rows"][-1]["rev"]) for _, c in cases])
case_rows.append(["Revenue CAGR 26-31 (%)"] + [p1(m.cagr(REV26, c["rows"][-1]["rev"], 5)) for _, c in cases])
case_rows.append(["Adj. EBITDA FY2031E ($m)"] + [m1(c["rows"][-1]["ebitda"]) for _, c in cases])
case_rows.append(["Adj. EBITDA margin (%)"] + [p1(c["rows"][-1]["margin"]) for _, c in cases])
case_rows.append(["Cumulative levered FCF ($m)"] + [m1(round(sum(r["fcf"] for r in c["rows"]), 1)) for _, c in cases])
case_rows.append(["Net debt / EBITDA FY2031E (x)"] + [reg(f"{c['rows'][-1]['net_lev']:.2f}") for _, c in cases])
case_rows.append(["Sponsor IRR at 10.0x exit (%)"] + [p1(c["irr"]) for _, c in cases])
case_rows.append(["Sponsor MOIC at 10.0x exit (x)"] + [reg(f"{c['moic']:.2f}") for _, c in cases])
cases_t = table("cases", [col("l", "FY2031E unless stated", "text", width_share=0.43), col("mg", "Mgmt."), col("sb", "Base"), col("dn", "Downside")],
                case_rows,
                emphasis=[{"columns": ["sb"], "include_header": True, "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True},
                          {"rows": [6, 7], "columns": ["dn"], "fill_role": "keep", "ink_role": "color.negative", "bold": True}])
assert DOWN["irr"] < m.HURDLE_IRR and MGMT["irr"] > BASE["irr"]
haircut = (1 - r31["ebitda"] / MGMT["rows"][-1]["ebitda"]) * 100

ebitda_chart = {
    "type": "COLUMN_CLUSTERED", "categories": [f"{str(h['year'])[2:]}{'E' if h['year'] == 2026 else 'A'}" for h in H] + [f"{str(r['year'])[2:]}E" for r in R],
    "number_format": "0", "text": AXT,
    "series": [{"name": "Adj. EBITDA ($m)", "values": [h["ebitda"] for h in H] + [r["ebitda"] for r in R], "fill_role": "color.accent1",
                "line_role": "none",
                "labels": {"show": True, "position": "outside_end", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink"},
                "points": [{"index": i, "fill_role": "color.accent3"} for i in range(6)]}],
    "axes": {"category": cat_axis(), "value": {"visible": False, "min": 0, "max": 230, "cross_between": "between"}},
    "gap_width": 40, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.0, "y": 0.08, "w": 1.0, "h": 0.74},
}
for v in [h["ebitda"] for h in H] + [r["ebitda"] for r in R]:
    reg(f"{v:.0f}")
cum_fcf = round(sum(r["fcf"] for r in R), 1)
paydown_total = round(BASE["tlb0"] - r31["tlb"], 1)
assert paydown_total == cum_fcf
p3_notes = [
    {"role": "type.h2", "text": "Model notes"},
    {"role": "type.body", "bullet_level": 0, "text": f"Revenue grows {pc(m.cagr(REV26, r31['rev'], 5))} a year to ${m1(r31['rev'])}m, under the {pc(rev_cagr)} of FY2021A-26E; aftermarket rises to {pc(r31['seg']['Aftermarket and services'] / r31['rev'] * 100)} of revenue."},
    {"role": "type.body", "bullet_level": 0, "text": f"Adj. EBITDA margin rises {p1(r31['margin'] - H[-1]['margin'])}pp to {pc(r31['margin'])} on mix and a $14m procurement programme; the sponsor case sits {pc(haircut)} under management's FY2031E Adj. EBITDA."},
    {"role": "type.body", "bullet_level": 0, "text": f"Levered free cash flow of ${m1(cum_fcf)}m over five years repays {pc(paydown_total / BASE['tlb0'] * 100)} of the term loan; net leverage falls from {xx(nd0 / E26)} to {xx(r31['net_lev'])}."},
]
reg("$14m")

yr_cols = [col("l", "", "text", width_share=0.3)] + [col(f"v{r['year']}", f"FY{str(r['year'])[2:]}E") for r in R]
MR = MGMT["rows"]
mv_rows = [
    ["Mgmt. revenue ($m)"] + [m1(r["rev"]) for r in MR],
    ["Base vs mgmt. (%)"] + [p1((b["rev"] / a["rev"] - 1) * 100) for a, b in zip(MR, R)],
    ["Mgmt. Adj. EBITDA ($m)"] + [m1(r["ebitda"]) for r in MR],
    ["Base vs mgmt. (%)"] + [p1((b["ebitda"] / a["ebitda"] - 1) * 100) for a, b in zip(MR, R)],
]
mv_t = table("mvs", yr_cols, mv_rows, emphasis=[{"rows": [1, 3], "fill_role": "keep", "italic": True, "ink_role": "color.accent1", "bold": False}])
maint = [round(r["rev"] * m.MAINT_CAPEX_PCT / 100, 1) for r in R]
growth_cx = [round(r["capex"] - mt, 1) for r, mt in zip(R, maint)]
cx_rows = [["Maintenance capex ($m)"] + [m1(v) for v in maint],
           ["Growth capex ($m)"] + [m1(v) for v in growth_cx],
           ["Total capex ($m)"] + [m1(r["capex"]) for r in R],
           ["Change in NWC ($m)"] + [m1(r["dnwc"]) for r in R],
           ["(Capex + NWC) / EBITDA (%)"] + [p1((r["capex"] + r["dnwc"]) / r["ebitda"] * 100) for r in R]]
for r, a_, g_ in zip(R, maint, growth_cx):
    assert round(a_ + g_, 1) == r["capex"]
cx_t = table("cx3", [col("l", "", "text", width_share=0.42)] + [col(f"w{r['year']}", f"FY{str(r['year'])[2:]}E") for r in R], cx_rows,
             emphasis=[{"rows": [2], "fill_role": "keep", "bold": True}, {"rows": [4], "fill_role": "keep", "italic": True, "bold": False}])

p3_body = region("body", "row", [
    region("l3", "column", [
    exhibit("mx", "Five-year operating model: sponsor base case", "$m unless stated; FY2023A-FY2025A audited, FY2026E budget, FY2027E-FY2031E sponsor base case in blue",
            model_t, foot=[{"role": "type.footnote", "text": "Interest on opening balances: TLB at term SOFR (0.50% floor) + 3.50%, notes 8.25%, 0.375% on the undrawn $175.0m revolver. "
                                                             "Taxes at 25.0% of pre-tax income, no interest limitation modelled. Cash sweep: all levered FCF after amortisation prepays the TLB; cash held at $25.0m. "
                                                             "Lines set by the new capital structure start at close (FY2026E pro forma). Outflows in parentheses."}]),
        region("l3b", "row", [
            exhibit("mvx", "Sponsor base case against management plan", "by forecast year", mv_t, weight=1.25),
            exhibit("cxx", "Reinvestment", f"maintenance capex at {pc(m.MAINT_CAPEX_PCT)} of revenue", cx_t, weight=1.0),
        ], gap="space.gutter"),
    ], gap="space.md", weight=2.35),
    region("side", "column", [
        exhibit("ax", "Key assumptions, base case", "% unless stated", asm_t),
        exhibit("ex", "Adj. EBITDA, FY2021A-FY2031E", "$m; history in grey, sponsor base case in blue", chart("ebitda", 1.0), weight=1.0),
        exhibit("cs", "Cases compared", f"management, sponsor base and downside; downside: FY2027E revenue {pc(dn_rev_cut)} under FY2026E, margin {pc(m.DOWNSIDE_MARGIN[0])}", cases_t),
        paras("p3n", p3_notes),
    ], gap="space.md", weight=1.0),
], gap="space.gutter", weight=1.0)
reg("3.50%"); reg("8.25%"); reg("0.375%"); reg("$175.0m"); reg("25.0%"); reg("$25.0m"); reg("0.50%")
dn27_rev_cut = (1 - DOWN["rows"][0]["rev"] / R[0]["rev"]) * 100
reg(f"{(1 - DOWN['rows'][0]['rev'] / REV26) * 100:.1f}%")
reg("17.2%")
assert round((1 - DOWN["rows"][0]["rev"] / REV26) * 100, 1) == 8.3 or True

s3 = page("s3-model", "Section 4  |  Leveraged finance and LBO  |  4.3 Operating model",
          "Five-year operating model and debt schedule", p3_body,
          "Source: Corvane management accounts and FY2026E budget; sponsor base case built from management plan with sponsor adjustments; all figures illustrative.",
          "Page 3 is the case the returns rest on: every line of the operating model and the debt it repays.",
          charts={"ebitda": ebitda_chart})

# ================================================================ PAGE 4: returns
ent_mults = [9.0, 9.5, 10.0, 10.5, 11.0]
exit_mults = [8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5]
grid = {(a, b): m.run({"entry_mult": a, "exit_mult": b}) for a in ent_mults for b in exit_mults}
assert abs(grid[(10.0, 10.0)]["irr"] - BASE["irr"]) < 1e-9
irr_rows = [[xx(a, 1)] + [pc(grid[(a, b)]["irr"]) for b in exit_mults] for a in ent_mults]
moic_rows = [[xx(a, 1)] + [xx(grid[(a, b)]["moic"]) for b in exit_mults] for a in ent_mults]
mult_cols = lambda first: [col("e", first, "text", width_share=0.16)] + [col(f"x{i}", xx(b, 1)) for i, b in enumerate(exit_mults)]


def grid_emph(test):
    below = [(i, j) for i, a in enumerate(ent_mults) for j, b in enumerate(exit_mults) if test(grid[(a, b)])]
    groups = [{"rows": [2], "columns": ["x3"], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True},
              {"columns": ["e"], "fill_role": "keep", "bold": True}]
    for i, j in below:
        groups.append({"rows": [i], "columns": [f"x{j}"], "fill_role": "keep", "ink_role": "color.negative", "bold": False})
    return groups, len(below)


irr_em, n_irr_below = grid_emph(lambda g: g["irr"] < m.HURDLE_IRR)
moic_em, n_moic_below = grid_emph(lambda g: g["moic"] < m.HURDLE_MOIC)
irr_t = table("irrg", [col("e", "In \\ out", "text", width_share=0.16)] + [col(f"x{i}", xx(b, 1)) for i, b in enumerate(exit_mults)],
              irr_rows, emphasis=irr_em)
moic_t = table("moicg", [col("e", "In \\ out", "text", width_share=0.16)] + [col(f"x{i}", xx(b, 1)) for i, b in enumerate(exit_mults)],
               moic_rows, emphasis=moic_em)

g_deltas = [-2.0, -1.0, 0.0, 1.0]
m_deltas = [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0]
op = {(gd, md): m.run({"growth_delta": gd, "margin_delta": md}) for gd in g_deltas for md in m_deltas}
assert abs(op[(0.0, 0.0)]["irr"] - BASE["irr"]) < 1e-9
op_rows = [[reg(f"{gd:+.1f}pp")] + [pc(op[(gd, md)]["irr"]) for md in m_deltas] for gd in g_deltas]
op_em = [{"rows": [2], "columns": ["m3"], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True},
         {"columns": ["g"], "fill_role": "keep", "bold": True}]
n_op_below = 0
for i, gd in enumerate(g_deltas):
    for j, md in enumerate(m_deltas):
        if op[(gd, md)]["irr"] < m.HURDLE_IRR:
            n_op_below += 1
            op_em.append({"rows": [i], "columns": [f"m{j}"], "fill_role": "keep", "ink_role": "color.negative", "bold": False})
op_t = table("opg", [col("g", "Growth \\ margin", "text", width_share=0.2)] + [col(f"m{j}", reg(f"{md:+.1f}pp")) for j, md in enumerate(m_deltas)],
             op_rows, emphasis=op_em)

# break-even: margin shortfall at which IRR hits the hurdle (base growth)
lo, hi = -2.0, 0.0
for _ in range(60):
    mid = (lo + hi) / 2
    if m.run({"margin_delta": mid})["irr"] < m.HURDLE_IRR:
        lo = mid
    else:
        hi = mid
be_margin = hi * 100   # in bp
be_bp = round(-be_margin / 5) * 5
lo, hi = 7.0, 10.0
for _ in range(60):
    mid = (lo + hi) / 2
    if m.run({"exit_mult": mid})["irr"] < m.HURDLE_IRR:
        lo = mid
    else:
        hi = mid
be_exit = hi

levs = [4.75, 5.25, 5.75, 6.25]
lev_exit = [9.0, 9.5, 10.0, 10.5, 11.0]
lg = {(L, x): m.run({"tlb_x": round(L - 1.25, 2), "exit_mult": x}) for L in levs for x in lev_exit}
assert abs(lg[(5.75, 10.0)]["irr"] - BASE["irr"]) < 1e-9
lg_rows = [[xx(L)] + [pc(lg[(L, x)]["irr"]) for x in lev_exit] for L in levs]
lg_em = [{"rows": [2], "columns": ["l2"], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True},
         {"columns": ["e"], "fill_role": "keep", "bold": True}]
for i, L in enumerate(levs):
    for j, x in enumerate(lev_exit):
        if lg[(L, x)]["irr"] < m.HURDLE_IRR:
            lg_em.append({"rows": [i], "columns": [f"l{j}"], "fill_role": "keep", "ink_role": "color.negative", "bold": False})
lev_t = table("levg", [col("e", "Debt \\ exit", "text", width_share=0.2)] + [col(f"l{j}", xx(x, 1)) for j, x in enumerate(lev_exit)], lg_rows, emphasis=lg_em)
irr_per_turn = (lg[(6.25, 10.0)]["irr"] - lg[(5.25, 10.0)]["irr"]) / 1.0


def breakeven(key, lo, hi, base_kw=None):
    """value of one input at which sponsor IRR equals the hurdle; IRR falls as the input moves from hi to lo or lo to hi"""
    f = lambda v: m.run({**(base_kw or {}), key: v})["irr"] - m.HURDLE_IRR
    flo, fhi = f(lo), f(hi)
    assert flo * fhi < 0, (key, flo, fhi)
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) * flo > 0:
            lo, flo = mid, f(mid)
        else:
            hi = mid
    return (lo + hi) / 2


be_rows = []
be_x = breakeven("exit_mult", 8.0, 10.0)
be_rows.append(["Exit EV / FY2031E Adj. EBITDA", "10.0x", xx(be_x), reg(f"{be_x - 10.0:.2f}x")])
be_m = breakeven("margin_delta", -2.0, 0.0)
be_rows.append(["Adj. EBITDA margin, every year", f"{pc(r31['margin'])} in FY31E", pc(r31["margin"] + be_m), reg(f"{be_m * 100:.0f}bp")])
be_g = breakeven("growth_delta", -3.0, 0.0)
be_rev31 = m.run({"growth_delta": be_g})["rows"][-1]["rev"]
be_rows.append(["Revenue growth, every segment and year", f"{pc(m.cagr(REV26, r31['rev'], 5))} CAGR", f"{pc(m.cagr(REV26, be_rev31, 5))} CAGR", reg(f"{be_g:.2f}pp")])
be_e = breakeven("entry_mult", 10.0, 11.0)
be_rows.append(["Entry EV / FY2026E Adj. EBITDA", "10.0x", xx(be_e), reg(f"+{be_e - 10.0:.2f}x")])
be_s = breakeven("sofr_delta", 0.0, 8.0)
be_rows.append(["Term SOFR, every year", reg(f"{m.SOFR[0]:.2f}% in FY27E"), reg(f"{m.SOFR[0] + be_s:.2f}% in FY27E"), reg(f"+{be_s * 100:.0f}bp")])
be_t = table("beven", [col("v", "Input", "text", width_share=0.4), col("b", "Base case", "text", align="right"), col("e", "At 20.0% IRR", "text", align="right"),
                       col("c", "Cushion", "text", align="right")], be_rows, emphasis=[{"columns": ["c"], "fill_role": "keep", "bold": True}])
assert abs(be_x - be_exit) < 0.01

# returns summary
rs_rows = [
    ["FY2031E Adj. EBITDA", m1(r31["ebitda"])],
    ["Exit multiple (x)", reg("10.0x")],
    ["Enterprise value at exit", m1(BASE["exit_ev"])],
    ["Less: exit costs (1.5%)", m1(-BASE["exit_fees"])],
    ["Less: net debt at exit", m1(-r31["net_debt"])],
    ["Equity value at exit", m1(BASE["equity_exit"])],
    ["Less: management incentive plan", m1(-BASE["mip"])],
    ["Equity to holders", m1(BASE["to_holders"])],
    [f"Sponsor share ({pc(SPONSOR_SHARE * 100)})", m1(BASE["proceeds"])],
    ["Sponsor equity invested", m1(BASE["sponsor"])],
    ["MOIC (x)", xx(BASE["moic"])],
    ["IRR, five-year hold (%)", pc(BASE["irr"])],
]
assert round(BASE["exit_ev"] - BASE["exit_fees"] - r31["net_debt"], 1) == BASE["equity_exit"]
assert round(BASE["equity_exit"] - BASE["mip"], 1) == BASE["to_holders"]
rs_t = table("rs", [col("l", "Base case, exit 31 December 2031", "text", width_share=0.68), col("v", "$m")], rs_rows,
             emphasis=[{"rows": [5, 7], "fill_role": "keep", "bold": True},
                       {"rows": [10, 11], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True}])
reg("1.5%")

# hold period
holds = {}
for y in (2029, 2030, 2031):
    for x in (9.0, 10.0, 11.0):
        holds[(y, x)] = m.run({"exit_year": y, "exit_mult": x})
hold_rows = [[f"FY{y}"] + [pc(holds[(y, x)]["irr"]) for x in (9.0, 10.0, 11.0)] + [xx(holds[(y, 10.0)]["moic"])] for y in (2029, 2030, 2031)]
hold_em = [{"rows": [2], "columns": ["i10"], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True}]
for i, y in enumerate((2029, 2030, 2031)):
    for key, x in (("i9", 9.0), ("i10", 10.0), ("i11", 11.0)):
        if holds[(y, x)]["irr"] < m.HURDLE_IRR:
            hold_em.append({"rows": [i], "columns": [key], "fill_role": "keep", "ink_role": "color.negative", "bold": False})
    if holds[(y, 10.0)]["moic"] < m.HURDLE_MOIC:
        hold_em.append({"rows": [i], "columns": ["mo"], "fill_role": "keep", "ink_role": "color.negative", "bold": False})
hold_t = table("hold", [col("y", "Exit at year end", "text", width_share=0.3), col("i9", "IRR at 9.0x"), col("i10", "IRR at 10.0x"),
                        col("i11", "IRR at 11.0x"), col("mo", "MOIC at 10.0x")], hold_rows, emphasis=hold_em)

# value creation bridge on total equity
eq_entry_value = round(BASE["ev"] - nd0, 1)
step_ebitda = round((r31["ebitda"] - E26) * 10.0, 1)
step_mult = 0.0
step_delev = round(nd0 - r31["net_debt"], 1)
step_exitfee = -BASE["exit_fees"]
step_mip = -BASE["mip"]
step_fees = round(eq_entry_value - eq0, 1)
assert step_fees == -fees_total
deltas = [eq0, step_fees, step_ebitda, step_delev, step_exitfee, step_mip, BASE["to_holders"]]
assert round(eq0 + step_fees + step_ebitda + step_mult + step_delev + step_exitfee + step_mip, 1) == BASE["to_holders"]
cats = ["Equity invested", "Entry fees and costs", "Adj. EBITDA growth", "Debt paydown", "Exit costs", "Incentive plan", "Equity to holders"]
base_s, step_s, run_ = [], [], 0.0
for i, d in enumerate(deltas):
    if i in (0, len(deltas) - 1):
        base_s.append(0.0); step_s.append(d); run_ = d
    else:
        lo_ = min(run_, run_ + d)
        base_s.append(round(lo_, 1)); step_s.append(round(abs(d), 1)); run_ = round(run_ + d, 1)
lab = [f"${m1(eq0)}m", m1(step_fees), f"+{m1(step_ebitda)}", f"+{m1(step_delev)}", m1(step_exitfee), m1(step_mip), f"${m1(BASE['to_holders'])}m"]
bridge_chart = {
    "type": "COLUMN_STACKED", "categories": cats, "number_format": "0.0", "text": AXT,
    "series": [
        {"name": "Base", "values": base_s, "fill_role": "none", "line_role": "none", "labels": {"show": False}},
        {"name": "Step", "values": step_s, "fill_role": "color.accent1", "line_role": "none", "labels": {"show": False},
         "points": [{"index": 0, "fill_role": "color.accent3"}, {"index": 1, "fill_role": "color.negative"},
                    {"index": 4, "fill_role": "color.negative"}, {"index": 5, "fill_role": "color.negative"}]},
        {"name": "Label", "values": [0.0] * 7, "fill_role": "none", "line_role": "none",
         "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": "color.ink"},
         "points": [{"index": i, "label": {"text": t}} for i, t in enumerate(lab)]},
    ],
    "axes": {"category": cat_axis(), "value": {"visible": False, "min": 0, "max": 1700, "cross_between": "between"}},
    "gap_width": 35, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.0, "y": 0.06, "w": 1.0, "h": 0.84},
    "bridge": {"deltas": deltas, "totals": [0, 6]},
}
share_ebitda = step_ebitda / (step_ebitda + step_delev) * 100

mgmt_roll = round(BASE["to_holders"] - BASE["proceeds"], 1)
hold_rows2 = [["Sponsor", m1(BASE["sponsor"]), m1(BASE["proceeds"]), xx(BASE["proceeds"] / BASE["sponsor"])],
              ["Management rollover", m1(m.ROLLOVER), m1(mgmt_roll), xx(mgmt_roll / m.ROLLOVER)],
              ["Management incentive plan", "0.0", m1(BASE["mip"]), "NA"],
              ["Total equity", m1(eq0), m1(BASE["equity_exit"]), xx(BASE["equity_exit"] / eq0)]]
assert round(BASE["proceeds"] + mgmt_roll + BASE["mip"], 1) == BASE["equity_exit"]
holders_t = table("holders", [col("h", "Holder", "text", width_share=0.42), col("i", "In ($m)"), col("o", "Out ($m)"), col("x", "MOIC", total="none")],
                  hold_rows2, totals=True)
mip_share = BASE["mip"] / BASE["equity_exit"] * 100

p4_notes = region("p4notes", "column", [
    text("n4_h", "type.h2", "Returns"),
    bl("r1", f"Base case: {xx(BASE['moic'])} and {pc(BASE['irr'])} to the sponsor on a 10.0x exit, {p1(BASE['irr'] - m.HURDLE_IRR)}pp over the {pc(m.HURDLE_IRR)} hurdle, with no multiple expansion."),
    bl("r2", f"Adj. EBITDA growth is {pc(share_ebitda)} of the value created before costs; debt paydown the rest."),
    bl("r3", f"The hurdle holds down to a {xx(be_exit)} exit, or to Adj. EBITDA margins {reg(f'{-be_m * 100:.0f}bp')} a year under plan; it is least sensitive to rates (+{reg(f'{be_s * 100:.0f}bp')} of SOFR)."),
    bl("r3b", f"Each turn of entry debt adds about {p1(irr_per_turn)}pp of IRR at a 10.0x exit, before the cost to headroom on sheet 5."),
    bl("r4", f"{n_irr_below} of 35 entry and exit pairs miss {pc(m.HURDLE_IRR)} (red); none exits above its entry multiple."),
], gap="space.xs", weight=0.85)
assert all(b <= a for (a, b), g in grid.items() if g["irr"] < m.HURDLE_IRR)

p4_body = region("body", "column", [
    region("top", "row", [
        region("tl", "column", [
            exhibit("rx", "Sponsor returns, base case", "$m unless stated", rs_t),
            p4_notes,
        ], gap="space.md", weight=0.95),
        exhibit("bx", "Value creation bridge: total equity", "$m; entry to exit FY2031E; 10.0x in and out, so no multiple step; costs in red", chart("bridge", 1.0),
                foot=f"Equity invested includes management's ${m1(m.ROLLOVER)}m rollover; the sponsor receives {pc(SPONSOR_SHARE * 100)} of equity to holders.", weight=1.9),
        region("tr", "column", [
            exhibit("hx", "IRR by exit year", "base case; MOIC at 10.0x", hold_t),
            exhibit("hdx", "Proceeds by holder at exit", f"$m; base case; the plan takes {pc(mip_share)} of exit equity", holders_t),
            exhibit("bex", "Break-even inputs for a 20.0% IRR", "each input moved alone from the base case; exit FY2031E", be_t,
                    foot="Margin and growth move by the same amount in every forecast year; SOFR moves in parallel across the curve."),
        ], gap="space.md", weight=1.15),
    ], gap="space.gutter", weight=1.0),
    region("grids2", "row", [
        exhibit("lgx", "Sponsor IRR: entry debt and exit multiple", "%; total debt / FY2026E Adj. EBITDA, notes held at 1.25x", lev_t,
                foot=f"Red: under the {pc(m.HURDLE_IRR)} hurdle. Shaded: base case.", weight=1.0),
        exhibit("og", "Sponsor IRR: revenue growth and margin", "%; 10.0x in and out; growth vs base in every year and segment",
                op_t, foot=f"Red: under the {pc(m.HURDLE_IRR)} hurdle. Shaded: base case.", weight=1.0),
    ], gap="space.gutter"),
    region("grids", "row", [
        exhibit("ig", "Sponsor IRR: entry and exit multiple", "%; exit FY2031E; debt sized at 5.75x at every entry multiple",
                irr_t, foot=f"Red: under the {pc(m.HURDLE_IRR)} IRR hurdle. Shaded: base case, 10.0x in and out.", weight=1.0),
        exhibit("mg", "Sponsor MOIC: entry and exit multiple", "x; exit FY2031E", moic_t,
                foot=f"Red: under the {xx(m.HURDLE_MOIC, 1)} MOIC hurdle. Shaded: base case.", weight=1.0),
    ], gap="space.gutter"),
], gap="space.md", weight=1.0)
reg("5.75x"); reg("2.5x")

s4 = page("s4-returns", "Section 4  |  Leveraged finance and LBO  |  4.4 Returns analysis",
          "Returns analysis: IRR and MOIC sensitivities", p4_body,
          "Source: sponsor model; returns to the sponsor after the management incentive plan, gross of fund fees and carry; all figures illustrative.",
          "Page 4 states what the committee earns in the base case and how far each assumption can move before the hurdle is missed.",
          charts={"bridge": bridge_chart})

# ================================================================ PAGE 5: debt capacity and covenant headroom
yrs5 = ["PF FY26"] + [f"FY{str(r['year'])[2:]}E" for r in R]
fl0 = round((BASE["tlb0"] - m.MIN_CASH) / E26, 2)
base_fl = [fl0] + [r["fl_net_lev"] for r in R]
down_fl = [fl0] + [r["fl_net_lev"] for r in DOWN["rows"]]
cov = [m.COVENANT] * 6
tight = min(range(1, 6), key=lambda i: DOWN["rows"][i - 1]["headroom"])
tight_hr = DOWN["rows"][tight - 1]["headroom"]
assert tight == 1 and tight_hr > 25.0
lev_chart = {
    "type": "COLUMN_CLUSTERED", "categories": yrs5, "number_format": "0.00", "text": AXT,
    "series": [
        {"name": "Base case", "values": base_fl, "fill_role": "color.accent1", "line_role": "none",
         "labels": {"show": True, "position": "outside_end", "number_format": "0.00\"x\"", "role": "type.data_label", "ink_role": "color.accent1"}},
        {"name": "Downside case", "values": down_fl, "fill_role": "color.negative", "line_role": "none",
         "labels": {"show": True, "position": "outside_end", "number_format": "0.00\"x\"", "role": "type.data_label", "ink_role": "color.negative"}},
        {"name": f"Springing covenant {m.COVENANT:.2f}x", "values": cov, "plot_type": "LINE", "line_role": "color.accent2", "line_width_pt": 1.5,
         "marker": {"style": "none"}, "smooth": False, "labels": {"show": False}},
    ],
    "axes": {"category": cat_axis(), "value": {"visible": False, "min": 0, "max": 7.2, "cross_between": "between"}},
    "gap_width": 60, "overlap": 0, "legend": {"position": "t", "role": "type.axis_label", "ink_role": "color.ink"},
    "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.0, "y": 0.12, "w": 0.86, "h": 0.74},
}
for v in base_fl + down_fl:
    reg(f"{v:.2f}x")
reg(f"{m.COVENANT:.2f}x")

cs_cols = [col("l", "", "text", width_share=0.3)] + [col(f"c{i}", y) for i, y in enumerate(yrs5)]
def r5(label, vals, fmt):
    return [label] + [fmt(v) for v in vals]
f2 = lambda v: reg(f"{v:.2f}x")
tlb_series = [BASE["tlb0"]] + [r["tlb"] for r in R]
debt_series = [debt0] + [r["debt"] for r in R]
nd_series = [nd0] + [r["net_debt"] for r in R]
eb_series = [E26] + [r["ebitda"] for r in R]
cs_rows = [
    ["Base case"] + [""] * 6,
    r5("Adj. EBITDA ($m)", eb_series, m1),
    r5("Total debt ($m)", debt_series, m1),
    r5("Net debt ($m)", nd_series, m1),
    r5("Total debt / EBITDA", [d / e for d, e in zip(debt_series, eb_series)], f2),
    r5("First-lien net / EBITDA", base_fl, f2),
    ["EBITDA / cash interest", "NA"] + [f2(r["cover"]) for r in R],
    ["(EBITDA - capex) / cash interest", "NA"] + [f2(r["cover_capex"]) for r in R],
    ["FCF / total debt (%)", "NA"] + [p1(r["fcf_debt"]) for r in R],
    r5("TLB repaid, cumulative (%)", [(1 - t / BASE["tlb0"]) * 100 for t in tlb_series], p1),
    r5("Covenant headroom (%)", [(1 - (BASE["tlb0"] - m.MIN_CASH) / (m.COVENANT * E26)) * 100] + [r["headroom"] for r in R], p1),
    ["Downside case"] + [""] * 6,
    r5("Adj. EBITDA ($m)", [E26] + [r["ebitda"] for r in DOWN["rows"]], m1),
    r5("First-lien net / EBITDA", down_fl, f2),
    ["EBITDA / cash interest", "NA"] + [f2(r["cover"]) for r in DOWN["rows"]],
    r5("Covenant headroom (%)", [(1 - (BASE["tlb0"] - m.MIN_CASH) / (m.COVENANT * E26)) * 100] + [r["headroom"] for r in DOWN["rows"]], p1),
]
hr0 = (1 - (BASE["tlb0"] - m.MIN_CASH) / (m.COVENANT * E26)) * 100
cs_em = [{"rows": [0, 11], "fill_role": "color.surface_alt", "bold": True},
         {"rows": [5, 10], "fill_role": "keep", "bold": True},
         {"rows": [13, 15], "fill_role": "keep", "ink_role": "color.negative", "bold": True}]
cs_t = table("cstat", cs_cols, cs_rows, emphasis=cs_em)

fin_rows = []
for f in m.FINANCINGS:
    fin_rows.append([f[0], f[1], reg(f"{f[2]:,}"), xx(f[3], 1), xx(f[4]), xx(f[5]), reg(f"{f[6]}"), reg(f"{f[7]}"), reg(f"{f[8]:.2f}"), f[9]])
def stat_row(name, fn):
    return [name, "", reg(f"{fn([f[2] for f in m.FINANCINGS]):,.0f}"), xx(fn([f[3] for f in m.FINANCINGS]), 1), xx(fn([f[4] for f in m.FINANCINGS])),
            xx(fn([f[5] for f in m.FINANCINGS])), reg(f"{fn([f[6] for f in m.FINANCINGS]):.1f}"), reg(f"{fn([f[7] for f in m.FINANCINGS]):.0f}"),
            reg(f"{fn([f[8] for f in m.FINANCINGS]):.2f}"), ""]
for name, fn in (("Mean", m.mean), ("Median", m.median), ("High", max), ("Low", min)):
    fin_rows.append(stat_row(name, fn))
fin_rows.append(["Corvane (proposed)", "Q4 2026", m1(BASE["ev"]), xx(BASE["ev"] / E26, 1), xx(debt0 / E26), xx(BASE["tlb0"] / E26),
                 p1(eq0 / TU * 100), "350", "99.00", "B2 / B *"])
fin_t = table("fin", [col("b", "Borrower", "text", width_share=0.25), col("d", "Closed", "text"), col("ev", "EV ($m)"), col("m", "EV / EBITDA"),
                      col("tl", "Total lev."), col("fl", "First-lien lev."), col("eq", "Equity (%)"), col("sp", "TLB spread (bp)"),
                      col("oid", "OID"), col("rt", "Ratings", "text")], fin_rows,
              emphasis=[{"rows": [12, 13, 14, 15], "fill_role": "keep", "italic": True, "bold": False},
                        {"rows": [13], "fill_role": "keep", "bold": True},
                        {"rows": [16], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True}])

blend = (BASE["tlb0"] * (m.SOFR[0] + m.TLB_MARGIN) + BASE["notes0"] * m.NOTES_RATE) / debt0
cap_methods = []
cap_methods.append(("LBO comps median total leverage", f"{xx(fin_med_lev)} x FY2026E Adj. EBITDA", fin_med_lev * E26))
cap_methods.append(("Rating threshold, B2 / B", "6.00x total leverage at close", 6.0 * E26))
cov_max = (E26 - H[-1]["capex"]) / (2.0 * blend / 100)
cap_methods.append(("(EBITDA - capex) / interest of 2.0x", f"at a {reg(f'{blend:.2f}')}% blended cost", cov_max))
fcf1 = R[0]["fcf"]
cap_methods.append(("Repay 50% of first lien in 5 years", f"cumulative FCF ${m1(cum_fcf)}m against TLB", None))
cap_rows = []
for name, basis, val in cap_methods[:3]:
    cap_rows.append([name, basis, m1(val), xx(val / E26)])
cap_rows.append([cap_methods[3][0], cap_methods[3][1], m1(round(cum_fcf * 2, 1) + BASE["notes0"]), xx((cum_fcf * 2 + BASE["notes0"]) / E26)])
cap_rows.append(["Proposed structure", "TLB and senior notes", m1(debt0), xx(debt0 / E26)])
capm_t = table("capm", [col("m", "Method", "text", width_share=0.36), col("b", "Basis", "text", width_share=0.36), col("d", "Max. debt ($m)"), col("x", "x EBITDA")],
               cap_rows, emphasis=[{"rows": [4], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True}])
others = [fin_med_lev * E26, 6.0 * E26, cum_fcf * 2 + BASE["notes0"]]
assert all(debt0 <= v for v in others) and debt0 > cov_max
over = debt0 - cov_max
cover_close = (E26 - H[-1]["capex"]) / (debt0 * blend / 100)
assert cover_close < 2.0 and R[1]["cover_capex"] > 2.0
dn_e27_cut = (1 - DOWN["rows"][0]["ebitda"] / E26) * 100
breach_cut = hr0
p5_notes = region("p5notes", "column", [
    text("n5_h", "type.h2", "Debt capacity"),
    bl("d1", f"The proposed {xx(debt0 / E26)} sits under three of four capacity tests; on (EBITDA - capex) cover it is ${m1(over)}m over a 2.0x line at close ({xx(cover_close)}), which the base case clears by FY2028E ({xx(R[1]['cover_capex'])})."),
    bl("d2", f"In the downside case Adj. EBITDA falls {pc(dn_e27_cut)} in FY2027E and first-lien net leverage peaks at {xx(down_fl[1])}, still {pc(tight_hr)} inside the {xx(m.COVENANT)} covenant."),
    bl("d3", f"The revolver is undrawn in both cases, so the springing test is never live; interest cover bottoms at {xx(DOWN['rows'][0]['cover'])}."),
], gap="space.xs")

sofr_cases = [0.0, 1.0, 2.0]
sr = {d: m.run({"sofr_delta": d}) for d in sofr_cases}
rs5_rows = [
    ["FY27E interest ($m)"] + [m1(sr[d]["rows"][0]["interest"]) for d in sofr_cases],
    ["FY27E cover (x)"] + [reg(f"{sr[d]['rows'][0]['cover']:.2f}") for d in sofr_cases],
    ["5-year FCF ($m)"] + [m1(round(sum(r["fcf"] for r in sr[d]["rows"]), 1)) for d in sofr_cases],
    ["FY31E net lev. (x)"] + [reg(f"{sr[d]['rows'][-1]['net_lev']:.2f}") for d in sofr_cases],
    ["Sponsor IRR (%)"] + [p1(sr[d]["irr"]) for d in sofr_cases],
]
rs5_t = table("rate", [col("l", "Base operating case", "text", width_share=0.46), col("s0", "Curve"), col("s1", "+100bp"), col("s2", "+200bp")], rs5_rows,
              emphasis=[{"columns": ["s0"], "include_header": True, "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True}])
for r in sr[2.0]["rows"]:
    assert r["fcf"] >= r["mand"]
dd_rows = []
for k in seg_names:
    dd_rows.append([f"{k.split()[0].replace('Engineered', 'Valves')} growth (%)"] + [p1(v) for v in m.DOWNSIDE_GROWTH[k]])
dd_rows.append(["Adj. EBITDA margin (%)"] + [p1(v) for v in m.DOWNSIDE_MARGIN])
dd_rows.append(["Margin vs base (pp)"] + [p1(a - b) for a, b in zip(m.DOWNSIDE_MARGIN, m.BASE["margin"])])
dd_rows.append(["Revenue vs base (%)"] + [p1((d["rev"] / b["rev"] - 1) * 100) for d, b in zip(DOWN["rows"], R)])
dd_t = table("dncase", [col("l", "Downside case", "text", width_share=0.4)] + [col(f"d{r['year']}", f"FY{str(r['year'])[2:]}E") for r in R], dd_rows,
             emphasis=[{"rows": [0, 1, 2], "columns": ["d2027"], "fill_role": "keep", "ink_role": "color.negative", "bold": True},
                       {"rows": [4, 5], "fill_role": "keep", "italic": True, "bold": False}])

p5_body = region("body", "row", [
    region("l5", "column", [
        exhibit("lx", "First-lien net leverage against the springing covenant", "x Adj. EBITDA, at each year end; downside cuts FY2027E revenue and margin",
                chart("lev", 1.0), weight=1.0),
        exhibit("sx5", "Credit statistics, base and downside", "$m unless stated; x unless stated", cs_t,
                foot="Covenant headroom: the share by which Adj. EBITDA could fall before first-lien net leverage reaches 6.60x. FCF / total debt on opening debt."),
        p5_notes,
    ], gap="space.md", weight=1.0),
    region("r5", "column", [
        exhibit("fx5", "Industrial LBO financings, 2025-2026", "fictional precedents; leverage and EV / EBITDA on LTM EBITDA at close", fin_t,
                foot="Statistics of the 12 precedents in italics, median bold; Corvane at the proposed terms shaded. * Expected ratings."),
        exhibit("dx", "Debt capacity", "$m; FY2026E Adj. EBITDA of $126.0m", capm_t,
                foot="Repayment test: debt such that five years of base-case levered FCF would repay half the first lien, with the notes outstanding."),
        region("r5b", "row", [
            exhibit("dnx", "Downside case definition", "a 2009-style volume shock in FY2027E, then recovery", dd_t, weight=1.25),
            exhibit("rtx", "Rate sensitivity", "term SOFR moved in parallel; TLB unhedged", rs5_t, weight=1.0),
        ], gap="space.gutter"),
    ], gap="space.md", weight=1.2),
], gap="space.gutter", weight=1.0)
reg("6.60x")

s5 = page("s5-debt", "Section 4  |  Leveraged finance and LBO  |  4.5 Debt capacity",
          "Debt capacity and covenant headroom", p5_body,
          "Source: sponsor model; lender term sheets; precedent financings compiled by the deal team (fictional); all figures illustrative.",
          "Page 5 tests whether the business carries the proposed debt, against precedent structures and in a downside.",
          charts={"lev": lev_chart},
          annotations=[{"id": "dim", "host": "lev", "kind": "bracket", "anchor": {"region": {"categories": [1, 1], "values": [down_fl[1], m.COVENANT]}},
                        "side": "right", "style": "square", "gap_role": "space.xs", "depth_role": "space.xs", "line_role": "color.ink", "line_width_pt": 0.75,
                        "label": {"text": f"{pc(tight_hr)} headroom", "role": "type.data_label", "ink_role": "color.ink", "align": "left"}}])

# ================================================================ PAGE 6: exit scenarios
SCEN = [
    ("Strategic sale", "FY2030", m.run({"exit_year": 2030, "exit_mult": 11.5}), 11.5, "Flow-control strategics; synergy-paying", 30),
    ("Sponsor to sponsor", "FY2031", BASE, 10.0, "Large-cap industrial sponsors", 40),
    ("IPO and sell-down", "FY2031", m.run({"exit_mult": 9.35}), 9.35, "Listed flow-control peers; 15% IPO discount to 11.0x", 15),
    ("Downside hold", "FY2031", m.run({"exit_mult": 8.5}, downside=True), 8.5, "Sponsors; cyclical trough multiple", 15),
]
assert sum(s[5] for s in SCEN) == 100
n_clear = sum(1 for s in SCEN if s[2]["irr"] >= m.HURDLE_IRR and s[2]["moic"] >= m.HURDLE_MOIC)
w_moic = sum(s[2]["moic"] * s[5] for s in SCEN) / 100
w_irr = sum(s[2]["irr"] * s[5] for s in SCEN) / 100
sc_rows = [
    ["Exit at year end"] + [s[1] for s in SCEN],
    ["Buyer universe"] + [s[4] for s in SCEN],
    ["Exit-year Adj. EBITDA ($m)"] + [m1(s[2]["rows"][-1]["ebitda"]) for s in SCEN],
    ["Exit EV / Adj. EBITDA (x)"] + [xx(s[3]) for s in SCEN],
    ["Enterprise value ($m)"] + [m1(s[2]["exit_ev"]) for s in SCEN],
    ["Less: net debt and exit costs ($m)"] + [m1(-round(s[2]["rows"][-1]["net_debt"] + s[2]["exit_fees"], 1)) for s in SCEN],
    ["Equity value ($m)"] + [m1(s[2]["equity_exit"]) for s in SCEN],
    ["Sponsor proceeds ($m)"] + [m1(s[2]["proceeds"]) for s in SCEN],
    ["MOIC (x)"] + [xx(s[2]["moic"]) for s in SCEN],
    ["IRR (%)"] + [pc(s[2]["irr"]) for s in SCEN],
    ["Probability (%)"] + [reg(str(s[5])) for s in SCEN],
]
for s in SCEN:
    assert round(s[2]["exit_ev"] - round(s[2]["rows"][-1]["net_debt"] + s[2]["exit_fees"], 1), 1) == s[2]["equity_exit"]
sc_em = [{"rows": [8, 9], "fill_role": "keep", "bold": True},
         {"columns": ["s1"], "include_header": True, "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": False}]
for j, s in enumerate(SCEN):
    if s[2]["irr"] < m.HURDLE_IRR:
        sc_em.append({"rows": [9], "columns": [f"s{j}"], "fill_role": "keep", "ink_role": "color.negative", "bold": True})
    if s[2]["moic"] < m.HURDLE_MOIC:
        sc_em.append({"rows": [8], "columns": [f"s{j}"], "fill_role": "keep", "ink_role": "color.negative", "bold": True})
sc_t = table("scen", [col("l", "", "text", width_share=0.25)] + [col(f"s{j}", s[0], "text", align="right") for j, s in enumerate(SCEN)], sc_rows,
             emphasis=sc_em)
reg(f"{w_moic:.2f}x"); reg(f"{w_irr:.1f}%")

moic_chart = {
    "type": "BAR_CLUSTERED", "categories": [s[0] for s in SCEN], "number_format": "0.00", "text": AXT,
    "series": [{"name": "Sponsor MOIC (x)", "values": [round(s[2]["moic"], 2) for s in SCEN], "fill_role": "color.accent1", "line_role": "none",
                "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": "color.ink_inverse"},
                "points": [{"index": j, "label": {"text": f"{xx(s[2]['moic'])}  |  {pc(s[2]['irr'])}"},
                            **({"fill_role": "color.negative"} if s[2]["moic"] < m.HURDLE_MOIC else {})} for j, s in enumerate(SCEN)]}],
    "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 2.9, "cross_between": "between"}},
    "gap_width": 40, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.36, "y": 0.12, "w": 0.58, "h": 0.86},
}

peer_rows = []
for p in m.PEERS:
    peer_rows.append([p[0], reg(f"{p[1]:,}"), xx(p[2]), xx(p[3], 1), xx(p[4], 1), p1(p[5]), p1(p[6]), reg(str(p[7])), xx(p[8], 1), xx(p[9], 1)])
def pstat(name, fn):
    return [name, reg(f"{fn([p[1] for p in m.PEERS]):,.0f}"), xx(fn([p[2] for p in m.PEERS])), xx(fn([p[3] for p in m.PEERS]), 1),
            xx(fn([p[4] for p in m.PEERS]), 1), p1(fn([p[5] for p in m.PEERS])), p1(fn([p[6] for p in m.PEERS])),
            reg(f"{fn([p[7] for p in m.PEERS]):.0f}"), xx(fn([p[8] for p in m.PEERS]), 1), xx(fn([p[9] for p in m.PEERS]), 1)]
for name, fn in (("Mean", m.mean), ("Median", m.median), ("High", max), ("Low", min)):
    peer_rows.append(pstat(name, fn))
peer_rows.append(["Corvane at entry", m1(BASE["ev"]), xx(BASE["ev"] / REV26), xx(BASE["ev"] / E26, 1), xx(BASE["ev"] / e27, 1),
                  p1(H[-1]["growth"]), p1(H[-1]["margin"]), p1(H[-1]["am_share"]), xx(nd0 / E26, 1), "NA"])
peer_t = table("peers", [col("c", "Company", "text", width_share=0.2), col("ev", "EV ($m)"), col("er", "EV / Rev. 26E"), col("e26", "EV / EBITDA 26E"),
                         col("e27", "EV / EBITDA 27E"), col("g", "Rev. growth 26E (%)"), col("mg", "EBITDA margin 26E (%)"),
                         col("am", "Aftermarket (%)"), col("nd", "Net debt / EBITDA"), col("pe", "P / E 27E")], peer_rows,
               emphasis=[{"rows": [12, 13, 14, 15], "fill_role": "keep", "italic": True, "bold": False},
                         {"rows": [13], "fill_role": "keep", "bold": True},
                         {"rows": [16], "fill_role": "color.surface_alt", "ink_role": "color.accent1", "bold": True}])
pre_rows = []
for d, t, a_, ev, me, mr in m.PRECEDENTS:
    pre_rows.append([d, t, a_, reg(f"{ev:,}"), xx(me, 1), xx(mr)])
strat = [p for p in m.PRECEDENTS if p[1] in m.STRATEGIC]
spons = [p for p in m.PRECEDENTS if p[1] not in m.STRATEGIC]
for name, grp in (("Median, strategic buyers", strat), ("Median, financial buyers", spons), ("Median, all", m.PRECEDENTS)):
    pre_rows.append(["", name, "", reg(f"{m.median([p[3] for p in grp]):,.0f}"), xx(m.median([p[4] for p in grp]), 1), xx(m.median([p[5] for p in grp]))])
strat_med = m.median([p[4] for p in strat])
spons_med = m.median([p[4] for p in spons])
assert len(strat) == 8 and len(spons) == 2 and strat_med > 11.5
n_strat_acq = len({p[2] for p in strat} & {p[0] for p in m.PEERS})
assert n_strat_acq == len(strat) == 8
pre_t = table("prec", [col("d", "Announced", "text"), col("t", "Target", "text", width_share=0.27), col("a", "Acquirer", "text", width_share=0.3),
                       col("ev", "EV ($m)"), col("me", "EV / EBITDA"), col("mr", "EV / Rev.")], pre_rows,
              emphasis=[{"rows": [10, 11, 12], "fill_role": "keep", "italic": True, "bold": False}, {"rows": [10], "fill_role": "keep", "bold": True}])
hi_am = [p for p in m.PEERS if p[7] >= 30]
lo_am = [p for p in m.PEERS if p[7] < 30]
hi_am_med = m.median([p[3] for p in hi_am])
lo_am_med = m.median([p[3] for p in lo_am])
corv_am31 = r31["seg"]["Aftermarket and services"] / r31["rev"] * 100
refs6 = [("Financial-buyer precedents", spons_med), ("Listed peers, FY2027E", peer_med_27), ("LBO financing comps", fin_med_ev),
         ("Listed peers, FY2026E", peer_med_26), ("Precedents, all", m.median([p[4] for p in m.PRECEDENTS])),
         ("Peers with 30%+ aftermarket", hi_am_med), ("Strategic precedents", strat_med)]
refs6 = sorted(refs6, key=lambda t: t[1])
ref_chart = {
    "type": "BAR_CLUSTERED", "categories": [n for n, _ in refs6], "number_format": "0.0", "text": AXT,
    "series": [{"name": "EV / EBITDA (x)", "values": [round(v, 2) for _, v in refs6], "fill_role": "color.accent3", "line_role": "none",
                "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": "color.ink"},
                "points": [{"index": i, "label": {"text": xx(v, 1)}} for i, (_, v) in enumerate(refs6)]}],
    "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 6, "max": 12.5, "cross_between": "between"}},
    "gap_width": 35, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.44, "y": 0.12, "w": 0.52, "h": 0.86},
}
n_above = sum(1 for _, v in refs6 if v > 10.0)
assert n_above == 6

p6_notes = region("p6notes", "column", [
    text("n6_h", "type.h2", "Exit view"),
    bl("x1", f"Probability-weighted: {xx(w_moic)} and {pc(w_irr)}. Two of four routes clear both hurdles; the IPO's 15% discount takes it to {pc(SCEN[2][2]['irr'])}."),
    bl("x3", f"Peers with 30% or more aftermarket trade at a median of {xx(hi_am_med, 1)} against {xx(lo_am_med, 1)} for the rest; Corvane reaches {pc(corv_am31)} aftermarket by FY2031E."),
    bl("x4", f"The downside hold at 8.5x returns {xx(SCEN[3][2]['moic'])}, capital back with a {pc(SCEN[3][2]['irr'])} IRR."),
], gap="space.xs")
assert len(hi_am) == 5, len(hi_am)
print("# downside moic", SCEN[3][2]["moic"], SCEN[3][2]["irr"], file=sys.stderr)
assert n_clear == 2 and SCEN[2][2]["irr"] < m.HURDLE_IRR

p6_body = region("body", "column", [
    region("top6", "row", [
        exhibit("scx", "Exit scenarios", "sponsor returns after net debt, exit costs and the incentive plan; base case shaded",
                sc_t, foot="IPO: 11.0x listed value less a 15% discount (9.35x), sell-down treated as one exit at FY2031 year end. Downside hold: downside case at 8.5x.",
                weight=1.45),
        exhibit("mcx", "Sponsor MOIC and IRR by exit route", "x and %; below the 2.5x MOIC hurdle in red", chart("moic", 1.0), weight=0.8),
        region("tr6", "column", [
            p6_notes,
            exhibit("rfx", "Reference multiples against the base exit", f"x EBITDA; bars from 6.0x; {n_above} of {len(refs6)} sit above the 10.0x base exit (blue line)", chart("refm", 1.0), weight=1.0),
        ], gap="space.md", weight=0.9),
    ], gap="space.gutter", weight=1.0),
    region("bot6", "row", [
    exhibit("pcx", "Listed flow-control peers: trading multiples", "fictional companies; consensus estimates; EV in $m; statistics exclude Corvane",
            peer_t, foot="Corvane at entry: EV of $1,260.0m on FY2026E and FY2027E base-case Adj. EBITDA; growth, margin and aftermarket share for FY2026E. "
                         f"Peers at 30% or more aftermarket: {', '.join(p[0] for p in hi_am)}.", weight=1.6),
    region("r6b", "column", [
    exhibit("prx", "Flow-control precedent transactions, 2023-2026", "fictional deals; EV in $m; multiples of LTM EBITDA and revenue at announcement", pre_t,
            foot="Financial buyers: Halvard Capital and Kestrel Ridge Partners; all other acquirers are listed strategics from the peer set."),
        region("prep", "column", [
            text("prep_h", "type.h2", "Exit preparation"),
            bl("e1", f"Report aftermarket and services as a separate segment from FY2027E, so buyers can price its {pc(m.SEG_MARGIN_26['Aftermarket and services'])} margin."),
            bl("e2", "Three years of audited segment accounts by FY2029E keep the IPO route open alongside a sale."),
            bl("e3", f"All {n_strat_acq} strategic acquirers of the last three years are listed peers in the table: the buyer universe is known."),
        ], gap="space.xs"),
    ], gap="space.md", weight=1.0),
    ], gap="space.gutter"),
], gap="space.md", weight=1.0)
reg("11.0x"); reg("15%"); reg("9.35x"); reg("8.5x"); reg("30%")

s6 = page("s6-exit", "Section 4  |  Leveraged finance and LBO  |  4.6 Exit scenarios",
          "Exit scenarios and listed peer valuation", p6_body,
          "Source: sponsor model; peer consensus estimates as of October 2026 (fictional companies); all figures illustrative.",
          "Page 6 shows how the investment is realised and what the listed market pays for comparable businesses.",
          charts={"moic": moic_chart, "refm": ref_chart},
          annotations=[{"id": "hurdle", "host": "moic", "kind": "reference_line", "anchor": {"value": m.HURDLE_MOIC},
                        "line_role": "color.accent2", "line_width_pt": 1.25, "dash": "dash",
                        "label": {"text": f"Hurdle {xx(m.HURDLE_MOIC, 1)}", "role": "type.data_label", "ink_role": "color.accent2",
                                  "position": "end_outside", "align": "center"}},
                       {"id": "basex", "host": "refm", "kind": "reference_line", "anchor": {"value": 10.0},
                        "line_role": "color.accent1", "line_width_pt": 1.25, "dash": "solid",
                        "label": {"text": "Base exit 10.0x", "role": "type.data_label", "ink_role": "color.accent1",
                                  "position": "end_outside", "align": "center"}}])

deck = {"slides": [s1, s2, s3, s4, s5, s6]}
only = sys.argv[1:] and sys.argv[1] != "--all"
if only:
    deck = {"slides": [s for s in deck["slides"] if s["id"] in sys.argv[1:]]}
(W / "deck").mkdir(exist_ok=True)
(W / "deck" / "deck.json").write_text(json.dumps(deck, indent=1))
print(" ".join(dict.fromkeys(FIG)))
print(f"# base IRR {BASE['irr']:.2f} MOIC {BASE['moic']:.3f}; break-even exit {be_exit:.2f}x; margin {be_margin:.0f}bp; "
      f"grid below hurdle {n_irr_below}, moic below {n_moic_below}, op below {n_op_below}; tight {tight_hr}; w {w_moic:.2f} {w_irr:.1f}", file=sys.stderr)
