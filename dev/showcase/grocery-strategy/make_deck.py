"""Write deck/deck.json for the Brindle Markets store format section from data.json."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "data.json")))
F = D["formats"]
T = D["total"]
A = D["actions"]
L = D["levers"]

SOURCE = "Source: Brindle store P&L, capital register and loyalty-card data, 2025; regional grocery market model; team analysis. All figures illustrative."
NOTE = "All figures on this page are illustrative: Brindle Markets is a fictional grocer and every number was invented for this section and computed in figures.py."


def fmt1(v):
    return f"{v:,.1f}"


def fmt0(v):
    return f"{v:,.0f}"


def pct1(v):
    return f"{v:.1f}"


def neg(v, f=fmt1):
    return f"({f(-v)})" if v < 0 else f(v)


def txt(id_, paras, **kw):
    el = {"type": "element", "id": id_, "kind": "text", "paragraphs": paras}
    el.update(kw)
    return el


def P(role, text, **kw):
    p = {"role": role, "text": text}
    p.update(kw)
    return p


def col(id_, children, gap="space.xs", pad=None, **kw):
    r = {"type": "region", "id": id_, "layout": {"kind": "flex", "direction": "column", "gap_role": gap, "pad_role": pad, "align": "stretch", "justify": "start"}, "children": children}
    r.update(kw)
    return r


def row(id_, children, gap="space.gutter", pad=None, align="stretch", **kw):
    r = {"type": "region", "id": id_, "layout": {"kind": "flex", "direction": "row", "gap_role": gap, "pad_role": pad, "align": align, "justify": "start"}, "children": children}
    r.update(kw)
    return r


def chart(id_, weight=1.0):
    return {"type": "element", "id": id_, "kind": "chart", "weight": weight}


def table(id_, columns, rows, totals=False, weight=None, **kw):
    t = {"columns": columns, "rows": rows, "header_rows": 1, "totals_last_row": totals}
    t.update(kw)
    el = {"type": "element", "id": id_, "kind": "table", "table": t}
    if weight is not None:
        el["weight"] = weight
    return el


def C(key, label, kind="number", **kw):
    c = {"key": key, "label": label, "value_kind": kind}
    c.update(kw)
    return c


def page(id_, kicker, title, body):
    root = col("root", [
        col("head", [txt("kicker", [P("type.kicker", kicker)]), txt("title", [P("type.title", title.replace("'", "\u2019"))])], gap="space.xs"),
        body,
        txt("source", [P("type.source_line", SOURCE)]),
    ], gap="space.md", pad="space.margin")
    return {"id": id_, "layout": "Blank", "title": {"register": "claim"}, "spec": {"root": root}, "notes": NOTE}


def ticket(id_, figure, line):
    return col(id_, [txt(id_ + "-f", [P("type.figure", figure)]), txt(id_ + "-t", [P("type.body", line)])], gap="space.xs")


AX_TEXT = {"role": "type.axis_label", "ink_role": "color.ink_muted"}
DL = {"role": "type.data_label", "ink_role": "color.ink"}


def cat_axis(**kw):
    a = {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none",
         "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink_muted"}, "title": "none"}
    a.update(kw)
    return a


slides = []

# ---------------------------------------------------------------- p1 market
sh = D["share"]
names = ["Large stores", "Discounters", "Convenience", "Online", "Specialist"]
series = []
for i, ch in enumerate(D["channels"]):
    vals = [sh["2019"][i], sh["2025"][i], sh["2028F"][i]]
    lead = i == 0
    role = "color.accent2" if lead else "color.accent3"
    end_text = f"{vals[2]}%  {names[i]}" + (f", {D['large_pts']} pts" if lead else "")
    pts = [{"index": 2, "label": {"show": True, "text": end_text, "position": "right", "ink_role": "color.accent2" if lead else "color.ink"}}]
    pts.append({"index": 0, "label": {"show": True, "text": f"{vals[0]}%", "position": "left", "ink_role": "color.accent2" if lead else "color.ink"}})
    series.append({"name": ch, "values": vals, "line_role": role, "line_width_pt": 2.25 if lead else 1.25, "smooth": False,
                   "marker": {"style": "circle", "size": 5, "fill_role": role, "line_role": role},
                   "labels": {"show": False, "position": "right", "role": "type.data_label", "ink_role": "color.ink"}, "points": pts})
slope = {"type": "LINE_MARKERS", "categories": ["2019", "2025", "2028F"], "number_format": "0", "text": AX_TEXT, "series": series,
         "axes": {"category": cat_axis(), "value": {"visible": False, "min": 0, "max": 50, "cross_between": "midpoint"}},
         "legend": "none", "plot_fill_role": "none", "title": "none", "plot_area": {"x": 0.07, "y": 0.04, "w": 0.55, "h": 0.86}}

tr = D["trips"]
missions = D["missions"]
bars = {"type": "BAR_CLUSTERED", "categories": missions, "number_format": "0.0", "text": AX_TEXT,
        "series": [
            {"name": "2019", "values": tr["2019"], "fill_role": "color.accent3", "line_role": "none",
             "labels": {"show": True, "position": "outside_end", "number_format": "0.0", **DL}},
            {"name": "2025", "values": tr["2025"], "fill_role": "color.accent1", "line_role": "none",
             "labels": {"show": True, "position": "outside_end", "number_format": "0.0", **DL},
             "points": [{"index": 0, "fill_role": "color.accent2", "label": {"text": f"{tr['2025'][0]:.1f}  ({round(D['main_change'])}%)", "ink_role": "color.accent2"}},
                        {"index": 1, "label": {"text": f"{tr['2025'][1]:.1f}  (+{D['topup_change']}%)"}}]}],
        "axes": {"category": cat_axis(reverse=True), "value": {"visible": False, "min": 0, "max": 3.4, "cross_between": "between"}},
        "gap_width": 45, "overlap": 0, "legend": "none",
        "plot_fill_role": "none", "title": "none", "plot_area": {"x": 0.25, "y": 0.01, "w": 0.62, "h": 0.98}}

small_share = round((F["Neighbourhood"]["sales"] + F["Express"]["sales"]) / T["sales"] * 100)
assert small_share == 8
large_gain = round(D["large_spend"]["2028F"] - D["large_spend"]["2019"], 1)
assert large_gain == 0.4
panel1 = col("panel", [
    txt("panel-h", [P("type.h1", "What it means for Brindle")]),
    ticket("t1", f"{D['super_share']}%", f"of Brindle's store sales come from its 58 superstores, against a {sh['2025'][0]}% large-store share of the market"),
    ticket("t2", f"£{D['basket']['2025'][0]}", f"average main-shop basket in 2025, up from £{D['basket']['2019'][0]} in 2019: fewer big shops, each larger, and more small ones between them"),
    ticket("t3", f"{D['small_online_2028']}%", f"of 2028 spend goes to discounters, convenience and online; Brindle's neighbourhood and express stores carry {small_share}% of its sales"),
    ticket("t4", f"£{large_gain}bn", f"of the £{D['market_add']}bn the market adds from 2019 to 2028 reaches large stores, whose spend moves from £{D['large_spend']['2019']}bn to £{D['large_spend']['2028F']}bn"),
], gap="space.md", pad="space.md", fill_role="color.surface_alt", weight=0.78)

body1 = row("body", [
    col("exA", [txt("exA-h", [P("type.h1", "Share of regional grocery spend by channel")]),
                txt("exA-u", [P("type.caption", f"% of spend; market £{D['market']['2019']}bn in 2019, £{D['market']['2025']}bn in 2025, £{D['market']['2028F']}bn forecast for 2028")]),
                chart("slope")], weight=1.25),
    col("exB", [txt("exB-h", [P("type.h1", "Shopping trips by mission")]),
                txt("exB-u", [P("type.caption", f"Trips per household per week, all missions {D['tot_trips']['2019']} in 2019 and {D['tot_trips']['2025']} in 2025; upper bar 2019 (grey-blue), lower bar 2025")]),
                chart("bars")], weight=1.0),
    panel1], weight=1.0)
s1 = page("p1-market", "01  Market shift",
          f"Grocery spend grows £{D['market_add']}bn by 2028, yet large stores' share falls from {sh['2019'][0]}% to {sh['2028F'][0]}% as shoppers trade the weekly shop for top-ups",
          body1)
s1["charts"] = {"slope": slope, "bars": bars}
slides.append(s1)

# ---------------------------------------------------------------- p2 formats
fk = ["Superstore", "Supermarket", "Neighbourhood", "Express"]
area_tot = sum(F[k]["stores"] * F[k]["area"] for k in fk)
dens_tot = round(T["sales"] * 1e6 / (area_tot * 1000 * 52), 2)
lfl_tot = round(sum(F[k]["lfl"] * F[k]["sales"] for k in fk) / T["sales"], 1)
gm_tot = round(sum(F[k]["gm"] * F[k]["sales"] for k in fk) / T["sales"], 1)
below_tot = sum(F[k]["below"] for k in fk)
assert below_tot == D["below_total"]


def frow(label, f, tot):
    return [label] + [f(F[k]) for k in fk] + [tot]


REFIT = {"Superstore": 9.6, "Supermarket": 7.2, "Neighbourhood": 3.1, "Express": 2.4}  # illustrative input
for k in fk:
    F[k]["name"] = k
refit_tot = round(sum(REFIT[k] * F[k]["stores"] for k in fk) / 214, 1)
assert round(F["Superstore"]["capital"] / T["capital"] * 100) == D["super_cap_share"]
assert round(F["Superstore"]["ebitda"] / T["ebitda"] * 100) == D["super_eb_share"]
ftab_rows = [
    ["Scale", "", "", "", "", ""],
    frow("Stores", lambda r: str(r["stores"]), "214"),
    frow("Average sales area (k sq ft)", lambda r: f"{r['area']:g}", f"{area_tot / 214:.1f}"),
    frow("Sales (£m)", lambda r: fmt0(r["sales"]), fmt0(T["sales"])),
    frow("Sales per store (£m)", lambda r: fmt1(r["sales_per_store"]), fmt1(T["sales"] / 214)),
    frow("Sales density (£ per sq ft per week)", lambda r: f"{r['density']:.2f}", f"{dens_tot:.2f}"),
    frow("Share of store sales (%)", lambda r: str(round(r["sales"] / T["sales"] * 100)), "100"),
    frow("Average years since last refit", lambda r: f"{REFIT[r['name']]:.1f}", f"{refit_tot:.1f}"),
    ["Trading and profit", "", "", "", "", ""],
    frow("Like-for-like sales growth, 2025 (%)", lambda r: neg(r["lfl"]), neg(lfl_tot)),
    frow("Gross margin (%)", lambda r: fmt1(r["gm"]), fmt1(gm_tot)),
    frow("Store EBITDA (£m)", lambda r: fmt1(r["ebitda"]), fmt1(T["ebitda"])),
    frow("Store EBITDA margin (%)", lambda r: fmt1(r["margin"]), fmt1(T["margin"])),
    frow("Share of store EBITDA (%)", lambda r: str(round(r["ebitda"] / T["ebitda"] * 100)), "100"),
    ["Capital", "", "", "", "", ""],
    frow("Invested capital (£m)", lambda r: fmt0(r["capital"]), fmt0(T["capital"])),
    frow("Share of invested capital (%)", lambda r: str(round(r["capital"] / T["capital"] * 100)), "100"),
    frow("Cash return on capital (%)", lambda r: fmt1(r["ret"]), fmt1(T["ret"])),
    frow("Stores under the 12% hurdle", lambda r: str(r["below"]), str(below_tot)),
]
ri = [r[0] for r in ftab_rows].index
ftab = table("ftab", [C("m", "", "text"), C("superstore", "Superstore"), C("supermarket", "Supermarket"), C("neighbourhood", "Neighbourhood"),
                      C("express", "Express"), C("estate", "Estate")], ftab_rows, totals=False,
             cell_anchor="m",
             emphasis=[{"rows": [ri("Scale"), ri("Trading and profit"), ri("Capital")], "fill_role": "color.surface_alt", "bold": True},
                       {"rows": [ri("Cash return on capital (%)")], "fill_role": "keep", "bold": True},
                       {"rows": [ri("Cash return on capital (%)"), ri("Share of invested capital (%)")], "columns": ["superstore"], "fill_role": "keep", "ink_role": "color.accent2", "bold": True},
                       {"columns": ["estate"], "fill_role": "keep", "include_header": True, "bold": True}])

fmt_names = fk + ["Estate"]
rets = [F[k]["ret"] for k in fk] + [T["ret"]]
retchart = {"type": "COLUMN_CLUSTERED", "categories": fmt_names, "number_format": "0.0", "text": AX_TEXT,
            "series": [{"name": "Cash return on capital (%)", "values": rets, "fill_role": "color.accent1", "line_role": "none",
                        "labels": {"show": True, "position": "outside_end", "number_format": "0.0\"%\"", **DL},
                        "points": [{"index": 0, "fill_role": "color.accent2", "label": {"ink_role": "color.accent2"}}, {"index": 4, "fill_role": "color.accent3"}]}],
            "axes": {"category": cat_axis(), "value": {"visible": False, "min": 0, "max": 24, "cross_between": "between"}},
            "gap_width": 55, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
            "plot_area": {"x": 0.01, "y": 0.06, "w": 0.98, "h": 0.84}}
ann2 = [{"id": "hurdle", "host": "retchart", "kind": "reference_line", "anchor": {"value": D["hurdle"]}, "line_role": "color.ink", "line_width_pt": 1.0, "dash": "dash",
         "label": {"text": "Hurdle 12%", "role": "type.data_label", "ink_role": "color.ink", "position": "start_above", "align": "left"}}]

sup, nb = F["Superstore"], F["Neighbourhood"]
band2 = row("band", [
    txt("band-h", [P("type.h1", "What it means for Brindle")], weight=0.55),
    ticket("t1", f"{D['super_cap_share']}%", f"of invested capital sits in superstores, which earn {D['super_eb_share']}% of store EBITDA at a {sup['margin']}% margin"),
    ticket("t2", f"{D['large_below']} of 154", f"superstores and supermarkets return under 12%; {sup['below']} of the 58 superstores do"),
    ticket("t3", f"{nb['ret']}%", f"return in the 42 neighbourhood stores, which carry only {D['nb_sales_share']}% of sales and £{nb['capital']}m of capital"),
], gap="space.lg", pad="space.md", fill_role="color.surface_alt")

body2 = col("body", [
    row("exs", [
        col("exA", [txt("exA-h", [P("type.h1", "Store P&L by format, 2025")]),
                    txt("exA-u", [P("type.caption", "£m unless stated; store EBITDA before central costs; cash return is store EBITDA over invested capital")]),
                    ftab], weight=1.6),
        col("exB", [txt("exB-h", [P("type.h1", "Cash return on invested capital")]),
                    txt("exB-u", [P("type.caption", "%, 2025; hurdle is Brindle's 12% pre-tax cost of store capital")]),
                    chart("retchart")], weight=1.0)], weight=1.0),
    band2], gap="space.md", weight=1.0)
s2 = page("p2-formats", "02  Format economics",
          f"Superstores take {D['super_cap_share']}% of Brindle's capital but return {sup['ret']}%, under half the 12% hurdle; neighbourhood stores return {nb['ret']}%",
          body2)
s2["charts"] = {"retchart": retchart}
s2["annotations"] = ann2
slides.append(s2)

# ---------------------------------------------------------------- p3 segments
segs = D["segments"]
bsales = [round(b * 1000) for b in D["brindle_seg"]]
assert sum(bsales) == T["sales"], (sum(bsales), T["sales"])
assert sum(D["seg_hh"]) == 4780
seg_rows = [[segs[i], fmt0(D["seg_hh"][i]), fmt1(D["seg_spend"][i]), neg(D["seg_growth"][i]), fmt1(D["seg_sow"][i]), fmt0(bsales[i]),
             D["seg_mission"][i], D["seg_format"][i]] for i in range(5)]
seg_rows.append(["Market", fmt0(sum(D["seg_hh"])), fmt1(D["market"]["2025"]), fmt1(D["mkt_growth"]), fmt1(D["brindle_sow"]), fmt0(T["sales"]), "", ""])
fast = [1, 2, 4]
stab = table("stab", [C("seg", "Segment", "text"), C("hh", "Households (k)"), C("spend", "Market spend (£bn)"),
                      C("g", "Spend growth, 2022-25 (% a year)", total="none"), C("sow", "Brindle share of wallet (%)", total="none"),
                      C("bs", "Brindle sales (£m)"), C("mission", "Main mission", "text", width_share=0.15), C("format", "Format they choose", "text")],
             seg_rows, totals=True, cell_anchor="m",
             emphasis=[{"rows": fast, "columns": ["sow", "g"], "fill_role": "keep", "ink_role": "color.accent2", "bold": True}])

core = [0, 3]
lab_pos = {0: "right", 3: "right", 1: "right", 2: "left", 4: "left"}


def seg_series(name, idx, role):
    return {"name": name, "values": [[D["seg_growth"][i], D["seg_sow"][i]] for i in idx], "line_role": "none", "smooth": False,
            "marker": {"style": "circle", "size": 9, "fill_role": role, "line_role": role},
            "labels": {"show": True, "position": "right", "number_format": "0.0", "role": "type.data_label", "ink_role": "color.ink"},
            "points": [{"index": j, "label": {"text": f"{segs[i]}, £{D['seg_spend'][i]}bn", "position": lab_pos[i]}} for j, i in enumerate(idx)]}


scat = {"type": "XY_SCATTER", "number_format": "0.0", "text": AX_TEXT,
        "series": [seg_series("Core segments", core, "color.accent1"), seg_series("Growth segments", fast, "color.accent2")],
        "axes": {"category": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "out", "reverse": False,
                              "min": -2, "max": 10, "major_unit": 2, "number_format": "0\"%\"", "gridlines": "none",
                              "labels": {"show": True, "position": "low", "role": "type.axis_label", "ink_role": "color.ink_muted"},
                              "title": {"text": "Segment spend growth, 2022-25 (% a year)", "role": "type.axis_label", "ink_role": "color.ink_muted", "orientation": "horizontal"}},
                 "value": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "out", "reverse": False,
                           "min": 0, "max": 16, "major_unit": 4, "number_format": "0\"%\"", "gridlines": "none",
                           "labels": {"show": True, "position": "low", "role": "type.axis_label", "ink_role": "color.ink_muted"},
                           "title": {"text": "Brindle share of wallet (%)", "role": "type.axis_label", "ink_role": "color.ink_muted", "orientation": "along"}}},
        "legend": "none", "plot_fill_role": "none", "title": "none", "plot_area": {"x": 0.09, "y": 0.04, "w": 0.86, "h": 0.78}}
ann3 = [
    {"id": "avg-share", "host": "scat", "kind": "reference_line", "anchor": {"value": D["brindle_sow"]}, "line_role": "color.ink_muted", "line_width_pt": 0.75, "dash": "dash",
     "label": {"text": f"Brindle average {D['brindle_sow']}%", "role": "type.data_label", "ink_role": "color.ink_muted", "position": "end_above", "align": "right"}},
    {"id": "mkt-growth", "host": "scat", "kind": "reference_line", "anchor": {"value": D["mkt_growth"], "axis": "category"}, "line_role": "color.ink_muted", "line_width_pt": 0.75, "dash": "dash", "gap_role": "space.xs",
     "label": {"text": f"Market growth {D['mkt_growth']}%", "role": "type.data_label", "ink_role": "color.ink_muted", "position": "end_right", "align": "left"}},
]
half_gap = round((D["slow_sow"] - D["fast_sow"]) / 2 / 100 * D["fast_spend"], 1)
half_gap_pct = round(half_gap * 1000 / T["sales"] * 100)
assert (half_gap, half_gap_pct) == (1.1, 28), (half_gap, half_gap_pct)
side3 = col("side", [
    txt("side-h", [P("type.h1", "What it means for Brindle")]),
    txt("side-t", [
        P("type.h2", "The base is shrinking in real terms"),
        P("type.body", f"{D['slow_of_brindle']}% of Brindle's sales come from established families and older traditional shoppers, whose spend grows 1.4% and falls 0.6% a year."),
        P("type.h2", "Growth is where Brindle is weakest"),
        P("type.body", f"The three growth segments hold {D['fast_share_mkt']}% of spend, £{D['fast_spend']}bn, and give Brindle {D['fast_sow']}% of it against {D['slow_sow']}% in the core."),
        P("type.h2", "Each point of share is worth £266m"),
        P("type.body", f"One point of wallet in the growth segments is £{D['pt_fast']}m of sales; they shop top-up, food-for-now and online, the missions small formats serve."),
        P("type.h2", f"Half the gap is £{half_gap}bn of sales"),
        P("type.body", f"Lifting growth-segment share halfway to the core's {D['slow_sow']}% would add £{half_gap}bn, {half_gap_pct}% of today's store sales."),
        P("type.h2", "Young urban is the extreme case"),
        P("type.body", f"Its spend grows fastest, {D['seg_growth'][4]}% a year, and Brindle's share is lowest, {D['seg_sow'][4]}%: £{bsales[4]}m of sales, from express and online."),
    ]),
], gap="space.sm", pad="space.md", fill_role="color.surface_alt", weight=0.85)
body3 = col("body", [
    col("exA", [txt("exA-h", [P("type.h1", "Customer segments in Brindle's catchments, 2025")]),
                txt("exA-u", [P("type.caption", "Share of wallet is Brindle's sales over the segment's market spend; growth is nominal")]),
                stab]),
    row("lower", [
        col("exB", [txt("exB-h", [P("type.h1", "Where spend grows against where Brindle is strong")]), chart("scat")], weight=1.5),
        side3], weight=1.0)], gap="space.md", weight=1.0)
assert D["pt_fast"] == 266
s3 = page("p3-segments", "03  Customer segments",
          f"Brindle's share of wallet is {D['slow_sow']}% where spend is flat and {D['fast_sow']}% where it grows: the three growth segments hold {D['fast_share_mkt']}% of spend",
          body3)
s3["charts"] = {"scat": scat}
s3["annotations"] = ann3
slides.append(s3)

# ---------------------------------------------------------------- p4 network
pts = D["points"]
groups = [("Clears the hurdle: invest or keep", ("Invest", "Keep"), "color.accent3", 5),
          ("Under the hurdle: reformat or right-size", ("Reformat", "Right-size"), "color.accent2", 5),
          ("Exit", ("Exit",), "color.ink", 6)]
nser = []
for name, acts, role, size in groups:
    nser.append({"name": name, "values": [[p[0], p[1]] for p in pts if p[2] in acts], "line_role": "none", "smooth": False,
                 "marker": {"style": "circle", "size": size, "fill_role": role, "line_role": role}, "labels": {"show": False}})
assert sum(len(s["values"]) for s in nser) == 214
netscat = {"type": "XY_SCATTER", "number_format": "0.0", "text": AX_TEXT, "series": nser,
           "axes": {"category": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "out", "reverse": False,
                                 "min": -8, "max": 10, "major_unit": 2, "number_format": "0\"%\"", "gridlines": "none",
                                 "labels": {"show": True, "position": "low", "role": "type.axis_label", "ink_role": "color.ink_muted"},
                                 "title": {"text": "Catchment grocery spend growth, 2022-25 (% a year)", "role": "type.axis_label", "ink_role": "color.ink_muted", "orientation": "horizontal"}},
                    "value": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "out", "reverse": False,
                              "min": -8, "max": 32, "major_unit": 4, "number_format": "0\"%\"", "gridlines": "none",
                              "labels": {"show": True, "position": "low", "role": "type.axis_label", "ink_role": "color.ink_muted"},
                              "title": {"text": "Store cash return on capital, 2025 (%)", "role": "type.axis_label", "ink_role": "color.ink_muted", "orientation": "along"}}},
           "legend": "none", "plot_fill_role": "none", "title": "none", "plot_area": {"x": 0.08, "y": 0.03, "w": 0.80, "h": 0.84}}
XMIN, XMAX = -8, 10


def qlabel(id_, text, x, y, ink, align):
    return {"id": id_, "host": "netscat", "kind": "mark", "prst": "rect", "anchor": {"region": {"x": x, "y": y}}, "fill_role": "color.surface",
            "label": {"text": text, "role": "type.h2", "ink_role": ink, "align": align, "position": "inside"}}


ann4 = [
    {"id": "hurdle", "host": "netscat", "kind": "reference_line", "anchor": {"value": D["hurdle"]}, "line_role": "color.ink", "line_width_pt": 1.0, "dash": "dash",
     "label": {"text": "Hurdle 12%", "role": "type.data_label", "ink_role": "color.ink", "position": "end_outside", "align": "left"}},
    {"id": "growth-cut", "host": "netscat", "kind": "reference_line", "anchor": {"value": D["growth_cut"], "axis": "category"}, "line_role": "color.ink", "line_width_pt": 1.0, "dash": "dash", "gap_role": "space.xs",
     "label": {"text": "Catchment growth 1.5%", "role": "type.data_label", "ink_role": "color.ink", "position": "end_right", "align": "left"}},
    {"id": "exit-zone", "host": "netscat", "kind": "band", "anchor": {"region": {"x": [XMIN, D["growth_cut"]], "y": [-8, D["exit_cut"]]}},
     "fill_role": "color.surface_alt", "pad_role": "none",
     "label": {"text": f"Exit: {A['Exit']['stores']}, under 3%", "role": "type.h2", "ink_role": "color.ink", "position": "inside_bottom_left", "align": "left"}},
    qlabel("q-invest", f"Invest: {A['Invest']['stores']}", [7.3, 10], [29, 31.5], "color.accent1", "right"),
    qlabel("q-keep", f"Keep: {A['Keep']['stores']}", [-8, -4.6], [29, 31.5], "color.accent1", "left"),
    qlabel("q-reformat", f"Reformat: {A['Reformat']['stores']}", [6.6, 10], [4.5, 7.0], "color.accent2", "right"),
    qlabel("q-rightsize", f"Right-size: {A['Right-size']['stores']}", [-8, -4.5], [8.5, 11.0], "color.accent2", "left"),
]
rules = {"Invest": "\u226512%, growing", "Keep": "\u226512%, flat", "Reformat": "<12%, growing", "Right-size": "<12%, flat", "Exit": "<3%, flat"}
up = {"Reformat": L["Reformat"], "Right-size": L["Right-size"], "Exit": L["Exit"]}
arows = []
for a in ["Invest", "Keep", "Reformat", "Right-size", "Exit"]:
    r = A[a]
    arows.append([a, rules[a], str(r["stores"]), str(r["large"]), fmt0(r["sales"]), fmt1(r["ebitda"]), fmt1(r["ret"]),
                  fmt1(up[a]["capex"]) if a in up else "NA", fmt1(up[a]["uplift"]) if a in up else "NA"])
cap_est = sum(up[a]["capex"] for a in up)
up_est = sum(up[a]["uplift"] for a in up)
arows.append(["Estate", "", "214", str(sum(A[a]["large"] for a in A)), fmt0(T["sales"]), fmt1(T["ebitda"]), fmt1(T["ret"]), fmt1(cap_est), fmt1(up_est)])
atab = table("atab", [C("a", "Action", "text"), C("rule", "Return, catchment", "text", width_share=0.18), C("n", "Stores"), C("large", "Large"), C("sales", "Sales (£m)"),
                      C("eb", "EBITDA (£m)"), C("ret", "Return (%)", total="none"), C("capex", "Capex (£m)"), C("up", "2028 uplift (£m)")],
             arows, totals=True, cell_anchor="m",
             emphasis=[{"rows": [2, 3], "columns": ["a"], "fill_role": "keep", "ink_role": "color.accent2", "bold": True},
                       {"rows": [4], "columns": ["a"], "fill_role": "keep", "ink_role": "color.ink", "bold": True}])
rf, rs, ex = A["Reformat"], A["Right-size"], A["Exit"]
large_under = sum(A[a]["large"] for a in ("Reformat", "Right-size", "Exit"))
assert large_under == 124 and sum(A[a]["stores"] for a in ("Reformat", "Right-size", "Exit")) == D["below_total"]
side4 = col("side", [
    txt("side-t", [
        P("type.h2", "Reformat where demand is growing"),
        P("type.body", f"{rf['stores']} stores, {rf['super']} of them superstores, give space back to fresh, food-to-go and click-and-collect and sublet the rest; capex £{L['Reformat']['capex']:.0f}m lifts them to a 10% return."),
        P("type.h2", "Right-size where it is not"),
        P("type.body", f"{rs['stores']} stores cut space and move to the leaner labour model; £{L['Right-size']['capex']:.1f}m of capex adds £{L['Right-size']['uplift']}m."),
        P("type.h2", "Exit releases capital, not EBITDA"),
        P("type.body", f"The {ex['stores']} exits earn £{ex['ebitda']}m on £{D['exit_capital']}m of capital; {round(D['transfer'] * 100)}% of their sales move to nearby stores, worth £{L['Exit']['transfer']}m."),
        P("type.h2", "Invest where return and demand meet"),
        P("type.body", f"{A['Invest']['stores']} stores clear both lines, {A['Invest']['stores'] - A['Invest']['large']} of them neighbourhood or express: the model for the 30 new stores."),
        P("type.h2", "The problem is the large stores"),
        P("type.body", f"{large_under} of the {D['below_total']} stores under the hurdle are superstores or supermarkets; {D['below_total'] - large_under} are small formats."),
    ]),
], gap="space.sm", pad="space.md", fill_role="color.surface_alt", weight=1.0)
body4 = row("body", [
    col("exA", [txt("exA-h", [P("type.h1", "214 stores by return and catchment growth")]),
                txt("exA-u", [P("type.caption", "One point per store; thresholds are the 12% hurdle and 1.5% a year catchment growth")]),
                chart("netscat")], weight=1.15),
    col("right", [
        col("exB", [txt("exB-h", [P("type.h1", "The five actions")]),
                    txt("exB-u", [P("type.caption", "2025 sales, store EBITDA and return; capex and EBITDA uplift to 2028; large means superstore or supermarket")]),
                    atab]),
        side4], gap="space.md", weight=1.0)], weight=1.0)
s4 = page("p4-network", "04  Network rationalisation",
          f"{D['below_total']} of 214 stores miss the 12% hurdle: reformat {rf['stores']} where catchments grow, right-size {rs['stores']} and exit {ex['stores']} where they do not",
          body4)
s4["charts"] = {"netscat": netscat}
s4["annotations"] = ann4
slides.append(s4)

# ---------------------------------------------------------------- p5 plan
labels = ["2025 store EBITDA", "Reformat", "Right-size", "Exits, net of transfer", "New neighbourhood", "Unchanged large stores", "2028 store EBITDA"]
deltas = [D["eb2025"]] + D["steps"] + [D["eb2028"]]
base, run = [], 0.0
for i, d in enumerate(deltas):
    if i == 0 or i == len(deltas) - 1:
        base.append(0.0)
        run = d if i == 0 else run
    else:
        base.append(round(min(run, run + d), 1))
        run = round(run + d, 1)
assert abs(run - D["eb2028"]) < 0.05
heights = [round(abs(d), 1) for d in deltas]
step_pts = [{"index": 0, "fill_role": "color.accent1"}, {"index": 1, "fill_role": "color.accent2"}, {"index": 2, "fill_role": "color.positive"},
            {"index": 3, "fill_role": "color.positive"}, {"index": 4, "fill_role": "color.positive"}, {"index": 5, "fill_role": "color.negative"},
            {"index": 6, "fill_role": "color.accent1"}]
lab_text = [f"£{deltas[0]:.1f}m"] + [f"+{d:.1f}" if d >= 0 else f"({-d:.1f})" for d in deltas[1:-1]] + [f"£{deltas[-1]:.1f}m"]
bridge = {"type": "COLUMN_STACKED", "categories": labels, "number_format": "0.0", "text": AX_TEXT,
          "series": [
              {"name": "Base", "values": base, "fill_role": "none", "line_role": "none", "labels": {"show": False}},
              {"name": "Step", "values": heights, "fill_role": "color.accent1", "line_role": "none", "labels": {"show": False}, "points": step_pts},
              {"name": "Label", "values": [0] * 7, "fill_role": "none", "line_role": "none",
               "labels": {"show": True, "position": "inside_base", "number_format": "0.0", **DL},
               "points": [{"index": i, "label": {"text": t, "ink_role": "color.accent2" if i == 1 else "color.ink"}} for i, t in enumerate(lab_text)]}],
          "axes": {"category": cat_axis(labels={"show": True, "role": "type.axis_label", "ink_role": "color.ink_muted", "rotation_deg": 0}),
                   "value": {"visible": False, "min": 0, "max": 345, "cross_between": "between"}},
          "gap_width": 35, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
          "plot_area": {"x": 0.01, "y": 0.02, "w": 0.98, "h": 0.89},
          "bridge": {"deltas": deltas, "totals": [0, 6]}}
# bases on stacked: the label series sits on top of base+step
for i in range(7):
    assert base[i] + heights[i] <= 345

ph = D["phase"]
gates = {"Reformat": "Pilot 4 stores by Q2 2026; roll out only above a 10% return",
         "Right-size": "Landlord talks on sublets; labour model agreed with unions",
         "Exit": "Lease breaks and disposals; staff offered nearby roles",
         "Open": "30 sites in the growth catchments; 70% of mature EBITDA by 2028",
         "Drift": "Price and range reset in the 34 unchanged large stores"}
unchanged_large = sum(A[a]["large"] for a in ("Invest", "Keep"))
assert unchanged_large == 30
gates["Drift"] = f"Price and range reset in the {unchanged_large} unchanged large stores"
wname = {"Reformat": "Reformat superstores and supermarkets", "Right-size": "Right-size flat-catchment stores", "Exit": "Exit loss-making stores",
         "Open": "Open neighbourhood stores", "Drift": "Unchanged large stores"}
rrows = []
for k in ["Reformat", "Right-size", "Exit", "Open"]:
    n = 30 if k == "Open" else A[k]["stores"]
    rrows.append([wname[k], gates[k], str(ph[k][0]), str(ph[k][1]), str(ph[k][2]), str(n), fmt1(L[k]["capex"]), neg(L[k]["uplift"])])
rrows.append([wname["Drift"], gates["Drift"], "", "", "", str(unchanged_large), "0.0", neg(L["Drift"]["uplift"])])
rrows.append(["Programme", "", "", "", "", "", fmt1(D["capex_total"]), fmt1(D["uplift_total"])])
assert abs(sum(L[k]["capex"] for k in L) - D["capex_total"]) < 0.05
assert abs(sum(L[k]["uplift"] for k in L) - D["uplift_total"]) < 0.05
rtab = table("rtab", [C("w", "Workstream", "text"), C("gate", "Gate to pass", "text", width_share=0.33), C("y26", "2026", total="none"), C("y27", "2027", total="none"),
                      C("y28", "2028", total="none"), C("n", "Stores", total="none"), C("capex", "Capex (£m)"), C("up", "EBITDA uplift 2028 (£m)")],
             rrows, totals=True, cell_anchor="m",
             emphasis=[{"rows": [0], "columns": ["w", "up"], "fill_role": "keep", "ink_role": "color.accent2", "bold": True}])
grow_capex_share = round((L["Reformat"]["capex"] + L["Open"]["capex"]) / D["capex_total"] * 100)
assert grow_capex_share == 81
panel5 = col("panel", [
    txt("panel-h", [P("type.h1", "What the board is asked to fund")]),
    ticket("t1", f"£{D['capex_total']:.0f}m", f"capex over three years, {grow_capex_share}% of it reformats and new stores"),
    ticket("t2", f"{D['payback']:.1f} years", f"payback on the 2028 EBITDA uplift of £{D['uplift_total']}m"),
    ticket("t3", f"{D['ret2028']}%", f"estate cash return in 2028, from {T['ret']}% today, on {D['stores_2028']} stores"),
    ticket("t4", f"£{D['exit_capital']}m", f"of capital released by the {A['Exit']['stores']} exits, which earn £{A['Exit']['ebitda']}m today"),
], gap="space.md", pad="space.md", fill_role="color.surface_alt", weight=0.5)
assert D["uplift_total"] == 95.9
body5 = col("body", [
    row("upper", [
        col("exA", [txt("exA-h", [P("type.h1", "Store EBITDA, 2025 to 2028")]),
                    txt("exA-u", [P("type.caption", f"£m; exits net of the {round(D['transfer'] * 100)}% of their sales recaptured nearby; new stores at 70% of mature EBITDA")]),
                    chart("bridge")], weight=1.5),
        panel5], weight=1.0),
    col("exB", [txt("exB-h", [P("type.h1", "Phasing, money and gates")]),
                txt("exB-u", [P("type.caption", "Stores started each year; capex and 2028 EBITDA uplift in £m")]),
                rtab])], gap="space.md", weight=1.0)
s5 = page("p5-plan", "05  Three-year plan",
          f"The plan lifts store EBITDA {D['eb_growth_pct']}% to £{D['eb2028']:.0f}m by 2028 on £{D['capex_total']:.0f}m of capex; reformats carry {D['reformat_share_gain']}% of the gain",
          body5)
s5["charts"] = {"bridge": bridge}
slides.append(s5)

os.makedirs(os.path.join(HERE, "deck"), exist_ok=True)
json.dump({"slides": slides}, open(os.path.join(HERE, "deck", "deck.json"), "w"), indent=1)
for s in slides:
    print(s["id"], s["spec"]["root"]["children"][0]["children"][1]["paragraphs"][0]["text"])
