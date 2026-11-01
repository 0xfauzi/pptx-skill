"""Write deck/deck.json for the Project Falcon valuation section from the computed figures."""
import contextlib, io, json, runpy, statistics as st
from pathlib import Path

W = Path("/home/user/pptx-skill/falcon")
with contextlib.redirect_stdout(io.StringIO()):
    G = runpy.run_path(str(W / "figures.py"))
comps, stats, prec, pstats, ff, F, falc = G["comps"], G["stats"], G["prec"], G["pstats"], G["ff"], G["F_metric"], G["falc"]
SPONSORS = ("KKR-backed Arcis", "Blackstone", "Carlyle")

def x1(v): return f"{v:.1f}x"
def x2(v): return f"{v:.2f}x"
def n0(v): return f"{v:,.0f}"
def d1(v): return f"{v:.1f}"
def m(v): return f"${v:,.0f}m"

FOOT = "Project Falcon  |  Valuation  |  Strictly confidential  |  Draft for discussion"
SOURCE_TAIL = "Share prices and consensus estimates as of [pricing date to be confirmed]."

def text(id_, paras, **kw):
    return {"type": "element", "id": id_, "kind": "text", "paragraphs": paras, **kw}
def P(role, t, **kw):
    d = {"role": role, "text": t}; d.update(kw); return d
def col(id_, children, gap="space.xs", **kw):
    return {"type": "region", "id": id_, "layout": {"kind": "flex", "direction": "column", "gap_role": gap, "pad_role": None,
            "align": "stretch", "justify": "start"}, "children": children, **kw}
def row(id_, children, gap="space.lg", **kw):
    return {"type": "region", "id": id_, "layout": {"kind": "flex", "direction": "row", "gap_role": gap, "pad_role": None,
            "align": "stretch", "justify": "start"}, "children": children, **kw}
TLOOK = {"data_fill_role": "none", "edge_rules": {"header_bottom": {"color_role": "color.ink", "width_pt": 1.0}}}
def head(section, title):
    return text("title", [P("type.section_label", f"Project Falcon  |  Valuation  |  {section}"), P("type.title", title)])
def exhibit_head(id_, h, cap):
    return text(id_, [P("type.h1", h), P("type.caption", cap)])
def bullets(id_, heading, items, **kw):
    return text(id_, [P("type.h2", heading)] + [P("type.bullet", t, bullet_level=0) for t in items], **kw)
def footer(sheet, source):
    return col("foot", [
        text("source", [P("type.source_line", source)]),
        row("footrow", [text("footer", [P("type.footnote", FOOT)], weight=1),
                        text("sheet", [P("type.footnote", f"Sheet {sheet}", align="right")], weight=0.15)], gap="space.md")])
def root(children):
    EMU = 914400
    zone = {"left": 0, "top": int(round(8.085 * EMU)), "width": int(11 * EMU), "height": int(round(0.415 * EMU)), "source": "chrome-5:rule (bottom rule at 8.105 in; the empty layout date, footer and number placeholders at 6.95 in draw nothing on the reference pages)"}
    return {"page": {"reserved_zones": [zone]}, "root": {"type": "region", "id": "root",
                     "layout": {"kind": "flex", "direction": "column", "gap_role": "space.md",
                                "pad_roles": {"left": "space.margin", "top": "space.lg", "right": "space.margin", "bottom": "space.sm"},
                                "align": "stretch", "justify": "start"},
                     "children": children}}
AX = {"role": "type.axis_label", "ink_role": "color.ink"}

# ---------------- Page 1: trading comparables ----------------
cs = sorted(comps, key=lambda c: -c["ev"])
crow = [[c["name"], c["ticker"], c["px"], n0(c["eq"]), n0(c["ev"]), x2(c["ev_rev_ltm"]), x2(c["ev_rev_ntm"]),
         x1(c["ev_ebitda_ltm"]), x1(c["ev_ebitda_ntm"]), d1(c["growth"]), d1(c["margin"])] for c in cs]
def statrow(label, k):
    return [label, "", "", "", "", x2(stats["ev_rev_ltm"][k]), x2(stats["ev_rev_ntm"][k]), x1(stats["ev_ebitda_ltm"][k]),
            x1(stats["ev_ebitda_ntm"][k]), d1(stats["growth"][k]), d1(stats["margin"][k])]
crow += [statrow("Mean", "mean"), statrow("Median", "median"), statrow("High", "hi"), statrow("Low", "lo"),
         ["Falcon (private)", "", "NA", "NA", "NA", "NA", "NA", "NA", "NA", falc["Revenue growth NTM (%)"], falc["EBITDA margin LTM (%)"]]]
comps_tbl = {"columns": [
    {"key": "co", "label": ["", "Company"], "width_share": 0.15, "value_kind": "text"},
    {"key": "tk", "label": ["", "Ticker"], "width_share": 0.05, "value_kind": "text"},
    {"key": "px", "label": ["", "Share price ($)"], "width_share": 0.08, "value_kind": "number"},
    {"key": "eq", "label": ["", "Equity value ($m)"], "width_share": 0.09, "value_kind": "number"},
    {"key": "ev", "label": ["", "EV ($m)"], "width_share": 0.08, "value_kind": "number"},
    {"key": "rl", "label": ["EV / revenue", "LTM"], "width_share": 0.075, "value_kind": "number"},
    {"key": "rn", "label": ["EV / revenue", "NTM"], "width_share": 0.075, "value_kind": "number"},
    {"key": "el", "label": ["EV / EBITDA", "LTM"], "width_share": 0.075, "value_kind": "number"},
    {"key": "en", "label": ["EV / EBITDA", "NTM"], "width_share": 0.075, "value_kind": "number"},
    {"key": "g", "label": ["", "Revenue growth NTM (%)"], "width_share": 0.125, "value_kind": "number"},
    {"key": "mg", "label": ["", "EBITDA margin LTM (%)"], "width_share": 0.125, "value_kind": "number"}],
    "rows": crow, "header_rows": 2}
NP = len(cs)

# Falcon against the peer distribution
rev_ltm = [float(r) for r in []]
peer_rev = [c["ev"] / c["ev_rev_ltm"] for c in comps]
peer_ebitda = [c["ev"] / c["ev_ebitda_ltm"] for c in comps]
def rank(v, xs): return 1 + sum(x > v for x in xs)
def tie(v, xs): return any(abs(x - v) < 1e-9 for x in xs)
pct = G["pct"]
pos_rows = []
for label, fv, xs, fmt in [("EBITDA margin LTM (%)", float(falc["EBITDA margin LTM (%)"]), [c["margin"] for c in comps], d1),
                           ("Revenue growth NTM (%)", float(falc["Revenue growth NTM (%)"]), [c["growth"] for c in comps], d1),
                           ("Revenue LTM ($m)", F["rev_ltm"], peer_rev, n0),
                           ("EBITDA LTM ($m)", F["ebitda_ltm"], peer_ebitda, n0)]:
    r = rank(fv, xs)
    pos_rows.append([label, fmt(fv), fmt(pct(xs, .25)), fmt(st.median(xs)), fmt(pct(xs, .75)),
                     f"{r} of 9" + (" (tied)" if tie(fv, xs) else "")])
pos_tbl = {"columns": [{"key": "k", "label": "Metric", "value_kind": "text", "width_share": 0.31},
                       {"key": "f", "label": "Falcon", "value_kind": "number", "width_share": 0.12},
                       {"key": "q1", "label": "25th pct", "value_kind": "number", "width_share": 0.13},
                       {"key": "md", "label": "Median", "value_kind": "number", "width_share": 0.13},
                       {"key": "q3", "label": "75th pct", "value_kind": "number", "width_share": 0.13},
                       {"key": "rk", "label": "Rank", "value_kind": "text", "width_share": 0.18}],
           "rows": pos_rows, "header_rows": 1}

# least-squares fit of EV / NTM revenue on LTM margin
xs = [c["margin"] for c in comps]; ys = [c["ev_rev_ntm"] for c in comps]
fit = st.linear_regression(xs, ys)
fm = float(falc["EBITDA margin LTM (%)"])
fit_mult = fit.slope * fm + fit.intercept
fit_ev = fit_mult * F["rev_ntm"]
r_corr = st.correlation(xs, ys)
assert r_corr > 0.98
scatter = {"type": "XY_SCATTER", "number_format": "0.0",
    "text": AX,
    "series": [
        {"name": "Listed peers", "values": [[c["margin"], round(c["ev_rev_ntm"], 3)] for c in comps], "line_role": "none",
         "marker": {"style": "circle", "size": 6, "fill_role": "color.ink_muted", "line_role": "color.ink_muted"},
         "labels": {"show": True, "position": "right", "role": "type.data_label", "ink_role": "color.ink"},
         "points": [{"index": i, "label": ({"text": c["ticker"], "position": "left"} if c["ticker"] == "VDP" else {"text": c["ticker"]})} for i, c in enumerate(comps)]},
        {"name": "Least-squares fit", "values": [[12.5, round(fit.slope * 12.5 + fit.intercept, 3)], [23.0, round(fit.slope * 23.0 + fit.intercept, 3)]],
         "line_role": "color.accent1", "line_width_pt": 1.0, "dash": "dash", "smooth": False,
         "marker": {"style": "none"}, "labels": {"show": False}}],
    "axes": {"category": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "out", "min": 12, "max": 24, "major_unit": 2,
                          "number_format": "0\"%\"", "gridlines": "none", "crosses": "min",
                          "title": {"text": "EBITDA margin, LTM", "role": "type.axis_label", "ink_role": "color.ink", "orientation": "horizontal"},
                          "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
             "value": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "out", "min": 1.4, "max": 3.0, "major_unit": 0.4,
                       "number_format": "0.0\"x\"", "gridlines": "none", "crosses": "min",
                       "title": {"text": "EV / NTM revenue", "role": "type.axis_label", "ink_role": "color.ink", "orientation": "along"},
                       "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}}},
    "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.13, "y": 0.10, "w": 0.80, "h": 0.70}}

pr1 = sorted(comps, key=lambda c: -c["ev_ebitda_ntm"])
mult = {"type": "BAR_CLUSTERED", "categories": [c["name"] for c in pr1], "number_format": "0.0\"x\"", "text": AX,
        "series": [{"name": "EV / NTM EBITDA", "values": [round(c["ev_ebitda_ntm"], 2) for c in pr1], "fill_role": "color.accent1", "line_role": "none",
                    "labels": {"show": True, "position": "inside_base", "number_format": "0.0\"x\"", "role": "type.emphasis", "ink_role": "color.ink"}}],
        "axes": {"category": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "none", "reverse": True, "gridlines": "none",
                              "title": "none", "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
                 "value": {"visible": False, "min": 0, "max": 14, "cross_between": "between", "reverse": False}},
        "gap_width": 60, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
        "plot_area": {"x": 0.36, "y": 0.13, "w": 0.60, "h": 0.85}}
g_rank = rank(float(falc["Revenue growth NTM (%)"]), [c["growth"] for c in comps])
m_rank = rank(fm, [c["margin"] for c in comps])
hi_m = max(comps, key=lambda c: c["margin"]); lo_m = min(comps, key=lambda c: c["margin"])
size_corr = st.correlation([c['ev'] for c in comps], [c['ev_ebitda_ntm'] for c in comps])
assert 0.4 < size_corr < 0.5
p1_bul = [
    f"Peers trade at {x1(stats['ev_ebitda_ntm']['lo'])} to {x1(stats['ev_ebitda_ntm']['hi'])} NTM EBITDA (median {x1(stats['ev_ebitda_ntm']['median'])}) and {x1(stats['ev_ebitda_ltm']['lo'])} to {x1(stats['ev_ebitda_ltm']['hi'])} LTM (median {x1(stats['ev_ebitda_ltm']['median'])}): a 0.9x and 1.2x spread across eight companies.",
    f"EV / NTM revenue runs from {x2(stats['ev_rev_ntm']['lo'])} ({lo_m['name'].split()[0]}, {d1(lo_m['margin'])}% margin) to {x2(stats['ev_rev_ntm']['hi'])} ({hi_m['name'].split()[0]}, {d1(hi_m['margin'])}%) and tracks margin with a correlation of {r_corr:.2f}: revenue multiples restate the EBITDA multiple, not a separate view.",
    f"Falcon's {d1(fm)}% LTM margin ranks {m_rank} of 9 and its {falc['Revenue growth NTM (%)']}% NTM growth {g_rank} of 9 (level with Varden), both within 0.3pp of the peer median, which supports applying the median multiple without a profile adjustment.",
    f"On the fitted line Falcon's margin implies {x2(fit_mult)} NTM revenue, {m(fit_ev)} of EV, against {m([r for r in ff if r['method']=='Trading comps, EV / NTM EBITDA'][0]['ev_med'])} at the median NTM EBITDA multiple.",
    f"Falcon is smaller than six of eight peers: LTM revenue of {m(F['rev_ltm'])} against a peer median of {m(st.median(peer_rev))}. Larger peers trade somewhat higher (correlation {size_corr:.2f} between EV and NTM EBITDA multiple), too few points to size a discount: no discount is applied, and this needs a view from the deal team.",
]
assert stats['ev_ebitda_ntm']['hi'] - stats['ev_ebitda_ntm']['lo'] < 0.95 and abs(stats['ev_ebitda_ltm']['hi'] - stats['ev_ebitda_ltm']['lo'] - 1.2) < 0.06
assert abs(fm - stats['margin']['median']) <= 0.3 and abs(float(falc['Revenue growth NTM (%)']) - stats['growth']['median']) <= 0.3
assert sum(F['rev_ltm'] < x for x in peer_rev) == 6
pass  # size_corr computed above
#([c["ev"] for c in comps], [c["ev_ebitda_ntm"] for c in comps])

s1 = {"id": "p1-comps", "layout": "Blank", "title": {"register": "topic", "element": "title"},
  "spec": root([
    head("1 Trading comparables", "Listed peer trading multiples"),
    col("comps-block", [exhibit_head("comps-h", "Listed peers: trading multiples", "EV and equity value in $m; LTM and NTM consensus; statistics exclude Falcon; sorted by EV"),
                        {"type": "element", "id": "comps", "kind": "table", "table": comps_tbl}]),
    row("lower", [
        col("fit-block", [exhibit_head("fit-h", "Revenue multiple against margin", f"x and %; eight listed peers; dashed line: least-squares fit, r = {r_corr:.2f}"),
                          {"type": "element", "id": "fit", "kind": "chart", "weight": 1}], weight=1.0),
        col("pos-block", [exhibit_head("pos-h", "Falcon against the peer set", "Falcon against peer 25th percentile, median and 75th percentile; rank 1 is the highest of nine, Falcon included"),
                          {"type": "element", "id": "pos", "kind": "table", "table": pos_tbl},
                          text("pos-note", [P("type.footnote", "Falcon LTM revenue $1,460m, NTM $1,545m; LTM EBITDA $276m, NTM $301m.")]),
                          exhibit_head("mult-h", "EV / NTM EBITDA by peer", f"x; axis from zero; all eight within {stats['ev_ebitda_ntm']['hi']-stats['ev_ebitda_ntm']['lo']:.1f}x of each other"),
                          {"type": "element", "id": "mult", "kind": "chart", "weight": 1}], weight=1.0),
        bullets("view", "Trading view", p1_bul, weight=1.15)], weight=1),
    footer(1, "Source: falcon_comps.csv (peer market data and consensus; Falcon management figures). " + SOURCE_TAIL)]),
  "styling": {"comps": {"emphasis": [
        {"rows": [NP + 1], "fill_role": "keep", "bold": True},
        {"rows": [NP, NP + 2, NP + 3], "fill_role": "keep", "italic": True},
        {"rows": [NP + 4], "fill_role": "color.surface_alt", "ink_role": "color.ink_muted", "bold": True}],
        "cell_anchor": "b", "spanner_align": "center", **TLOOK},
              "pos": {"emphasis": [{"columns": ["f"], "fill_role": "color.surface_alt", "ink_role": "color.ink_muted", "bold": True, "include_header": True}], "cell_anchor": "b", **TLOOK}},
  "charts": {"fit": scatter, "mult": mult},
  "annotations": [
    {"id": "falcon-m", "host": "fit", "kind": "reference_line", "anchor": {"value": fm, "axis": "category"},
     "line_role": "color.emphasis", "line_width_pt": 1.0, "dash": "dash",
     "label": {"text": f"Falcon {d1(fm)}%: {x2(fit_mult)} on the fit", "role": "type.data_label", "ink_role": "color.emphasis", "position": "end_outside", "align": "left"}},
    {"id": "mult-med", "host": "mult", "kind": "reference_line", "anchor": {"value": round(stats["ev_ebitda_ntm"]["median"], 2)},
     "line_role": "color.ink_muted", "line_width_pt": 1.0,
     "label": {"text": f"Median {x1(stats['ev_ebitda_ntm']['median'])}", "role": "type.data_label", "ink_role": "color.ink_muted", "position": "end_outside", "align": "center"}}]}

# ---------------- Page 2: precedent transactions ----------------
def btype(a): return "Sponsor" if a in SPONSORS else "Strategic"
mon = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
def dkey(d): mo, y = d.split(); return int(y) * 12 + mon[mo]
ps = sorted(prec, key=lambda p: -dkey(p["date"]))
prow = [[p["date"], p["target"], p["acq"], btype(p["acq"]), n0(p["ev"]), x2(p["rev"]), x1(p["ebitda"]),
         n0(p["ev"] / p["ebitda"]), d1(p["rev"] / p["ebitda"] * 100)] for p in ps]
impl_m = [p["rev"] / p["ebitda"] * 100 for p in prec]
impl_e = [p["ev"] / p["ebitda"] for p in prec]
evs = [p["ev"] for p in prec]
def pstat(label, f):
    return ["", label, "", "", n0(f(evs)), x2(f([p["rev"] for p in prec])), x1(f([p["ebitda"] for p in prec])), n0(f(impl_e)), d1(f(impl_m))]
sp = [p for p in prec if p["acq"] in SPONSORS]; stg = [p for p in prec if p["acq"] not in SPONSORS]
def grp(label, g):
    return ["", label, "", "", n0(st.median([p["ev"] for p in g])), x2(st.median([p["rev"] for p in g])), x1(st.median([p["ebitda"] for p in g])),
            n0(st.median([p["ev"] / p["ebitda"] for p in g])), d1(st.median([p["rev"] / p["ebitda"] * 100 for p in g]))]
prow += [pstat("Mean", st.mean), pstat("Median", st.median), pstat("High", max), pstat("Low", min),
         grp(f"Median, sponsors ({len(sp)})", sp), grp(f"Median, strategics ({len(stg)})", stg)]
NQ = len(ps)
prec_tbl = {"columns": [
    {"key": "d", "label": "Announced", "width_share": 0.09, "value_kind": "text"},
    {"key": "t", "label": "Target", "width_share": 0.17, "value_kind": "text"},
    {"key": "a", "label": "Acquirer", "width_share": 0.17, "value_kind": "text"},
    {"key": "b", "label": "Buyer", "width_share": 0.08, "value_kind": "text"},
    {"key": "ev", "label": "EV ($m)", "width_share": 0.08, "value_kind": "number"},
    {"key": "r", "label": "EV / LTM revenue", "width_share": 0.1, "value_kind": "number"},
    {"key": "e", "label": "EV / LTM EBITDA", "width_share": 0.1, "value_kind": "number"},
    {"key": "ie", "label": "Implied LTM EBITDA ($m)", "width_share": 0.11, "value_kind": "number"},
    {"key": "im", "label": "Implied EBITDA margin (%)", "width_share": 0.1, "value_kind": "number"}],
    "rows": prow, "header_rows": 1}
pr = sorted(prec, key=lambda p: -p["ebitda"])
trading_ltm_med = stats["ev_ebitda_ltm"]["median"]
bar = {"type": "BAR_CLUSTERED", "categories": [f"{p['target']}, {p['date'][:3]}-{p['date'][-2:]}" for p in pr],
       "number_format": "0.0\"x\"", "text": AX,
       "series": [{"name": "EV / LTM EBITDA", "values": [p["ebitda"] for p in pr], "fill_role": "color.accent1", "line_role": "none",
                   "labels": {"show": True, "position": "inside_base", "number_format": "0.0\"x\"", "role": "type.emphasis", "ink_role": "color.ink"},
                   "points": [{"index": i, "fill_role": "color.ink_muted", "label": {"ink_role": "color.surface"}} for i, p in enumerate(pr) if p["acq"] in SPONSORS]}],
       "axes": {"category": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "none", "reverse": True, "gridlines": "none",
                             "title": "none", "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
                "value": {"visible": False, "min": 0, "max": 15, "cross_between": "between", "reverse": False}},
       "gap_width": 55, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none",
       "plot_area": {"x": 0.42, "y": 0.10, "w": 0.55, "h": 0.88}}
largest = max(prec, key=lambda p: p["ev"])
pff = [r for r in ff if r["method"] == "Precedents, EV / LTM EBITDA"][0]
recent = [p["ebitda"] for p in prec if p["date"].endswith(("2025", "2026"))]; older = [p["ebitda"] for p in prec if not p["date"].endswith(("2025", "2026"))]
top4 = pr[:4]; assert sum(p["acq"] in SPONSORS for p in top4) == 3
prem = pstats["ebitda"]["median"] / trading_ltm_med - 1
assert prem < 0
r_size = st.correlation([p["ev"] for p in prec], [p["ebitda"] for p in prec])
big = [p for p in prec if p["ev"] >= 2000]; small = [p for p in prec if p["ev"] < 2000]
assert len(big) == 3 and len(small) == 5
size_sc = {"type": "XY_SCATTER", "number_format": "0.0", "text": AX,
    "series": [{"name": "Sponsor buyer", "values": [[p["ev"], p["ebitda"]] for p in prec if p["acq"] in SPONSORS], "line_role": "none",
                "marker": {"style": "circle", "size": 6, "fill_role": "color.ink_muted", "line_role": "color.ink_muted"},
                "labels": {"show": True, "position": "right", "role": "type.data_label", "ink_role": "color.ink"},
                "points": [{"index": i, "label": ({"text": p["target"].split()[0], "position": "left"} if p["target"].startswith("Norland") else {"text": p["target"].split()[0]})} for i, p in enumerate([q for q in prec if q["acq"] in SPONSORS])]},
               {"name": "Strategic buyer", "values": [[p["ev"], p["ebitda"]] for p in prec if p["acq"] not in SPONSORS], "line_role": "none",
                "marker": {"style": "circle", "size": 6, "fill_role": "color.accent1", "line_role": "color.accent1"},
                "labels": {"show": True, "position": "right", "role": "type.data_label", "ink_role": "color.ink"},
                "points": [{"index": i, "label": ({"text": p["target"].split()[0], "position": "left"} if p["ev"] > 2500 else {"text": p["target"].split()[0]})} for i, p in enumerate([q for q in prec if q["acq"] not in SPONSORS])]}],
    "axes": {"category": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "out", "min": 500, "max": 4000, "major_unit": 500,
                          "number_format": "#,##0", "gridlines": "none", "crosses": "min",
                          "title": {"text": "Deal EV ($m)", "role": "type.axis_label", "ink_role": "color.ink", "orientation": "horizontal"},
                          "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
             "value": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "out", "min": 9, "max": 15, "major_unit": 1,
                       "number_format": "0\"x\"", "gridlines": "none", "crosses": "min",
                       "title": {"text": "EV / LTM EBITDA", "role": "type.axis_label", "ink_role": "color.ink", "orientation": "along"},
                       "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}}},
    "legend": {"position": "t", "role": "type.axis_label", "ink_role": "color.ink"}, "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.10, "y": 0.16, "w": 0.86, "h": 0.64}}
p2_bul = [
    f"Sponsors paid a median {x1(st.median([p['ebitda'] for p in sp]))} LTM EBITDA across {len(sp)} deals, strategic buyers {x1(st.median([p['ebitda'] for p in stg]))} across {len(stg)}; three of the four highest multiples are sponsor deals.",
    f"The precedent median of {x1(pstats['ebitda']['median'])} sits {abs(prem)*100:.1f}% below the listed peers' {x1(trading_ltm_med)} LTM today, so the set shows no control premium over current trading. Peer multiples at each announcement date are not in the data; checking them would show whether markets have re-rated since.",
    f"No drift over time: deals announced in 2025-2026 have a median of {x1(st.median(recent))}, those in 2023-2024 {x1(st.median(older))}.",
    f"Implied target margins run {d1(min(impl_m))}% to {d1(max(impl_m))}% (median {d1(st.median(impl_m))}%), around Falcon's {d1(fm)}%.",
    f"Larger deals priced higher: the {len(big)} deals of $2,000m or more have a median of {x1(st.median([p['ebitda'] for p in big]))} against {x1(st.median([p['ebitda'] for p in small]))} for the {len(small)} smaller (correlation {r_size:.2f}; eight deals is too few to rely on).",
    f"At the precedent median Falcon's EV is {m(pff['ev_med'])}, above the largest deal in the set ({largest['target']}, {m(largest['ev'])}): if size carries a premium, the precedent median understates Falcon.",
]
s2 = {"id": "p2-precedents", "layout": "Blank", "title": {"register": "topic", "element": "title"},
  "spec": root([
    head("2 Precedent transactions", "Precedent transactions"),
    row("body", [
        col("prec-block", [exhibit_head("prec-h", "Announced transactions, 2023-2026", "EV in $m at announcement; multiples of LTM revenue and EBITDA; implied EBITDA and margin derived from EV and the two multiples"),
                           {"type": "element", "id": "prec", "kind": "table", "table": prec_tbl},
                           text("prec-note", [P("type.footnote", "Sponsor buyers: KKR-backed Arcis, Blackstone and Carlyle; the five strategic acquirers are all in the peer set on sheet 1. Implied LTM EBITDA = EV / (EV / LTM EBITDA); implied margin = (EV / LTM revenue) / (EV / LTM EBITDA).")])], weight=1.75),
        col("rank-block", [exhibit_head("rank-h", "EV / LTM EBITDA by deal, ranked", "x; sponsor buyers in navy, strategic buyers in grey"),
                           {"type": "element", "id": "rank", "kind": "chart", "weight": 1}], weight=1)]),
    row("lower2", [
        col("size-block", [exhibit_head("size-h", "Deal size against multiple", f"$m and x; eight deals, r = {r_size:.2f}; dashed line: Falcon's EV at the precedent median"),
                           {"type": "element", "id": "size", "kind": "chart", "weight": 1}], weight=1),
        bullets("view", "Precedent view", p2_bul, weight=1.5)], weight=1),
    footer(2, "Source: falcon_precedents.csv (announced transactions; EV and multiples at announcement); falcon_comps.csv for listed peer multiples.")]),
  "styling": {"prec": {"emphasis": [
        {"rows": [NQ + 1], "fill_role": "keep", "bold": True},
        {"rows": [NQ, NQ + 2, NQ + 3], "fill_role": "keep", "italic": True},
        {"rows": [NQ + 4, NQ + 5], "fill_role": "color.surface_alt", "bold": True}],
        "cell_anchor": "b", **TLOOK}},
  "charts": {"rank": bar, "size": size_sc},
  "annotations": [
    {"id": "trading-line", "host": "rank", "kind": "reference_line", "anchor": {"value": trading_ltm_med},
     "line_role": "color.emphasis", "line_width_pt": 1.0, "dash": "dash",
     "label": {"text": f"Listed peers today {x1(trading_ltm_med)}", "role": "type.data_label", "ink_role": "color.emphasis", "position": "end_outside", "align": "center"}},
    {"id": "falcon-ev", "host": "size", "kind": "reference_line", "anchor": {"value": round(pff["ev_med"], 1), "axis": "category"},
     "line_role": "color.emphasis", "line_width_pt": 1.0, "dash": "dash",
     "label": {"text": f"Falcon {m(pff['ev_med'])}", "role": "type.data_label", "ink_role": "color.emphasis", "position": "end_outside", "align": "center"}}]}

# ---------------- Page 3: football field and implied values ----------------
order = list(reversed(ff))  # first category is drawn lowest; list bottom-up so the top reads as ff[0]
isE = ["ebitda" in r["metric"] for r in order]
lo_min = 2600; hi_max = 3800
fbar = {"type": "BAR_STACKED", "categories": [r["method"] for r in order], "number_format": "#,##0", "text": AX,
    "series": [
        {"name": "Base", "values": [round(r["ev_lo"], 1) for r in order], "fill_role": "none", "line_role": "none", "labels": {"show": False}},
        {"name": "25th pct to median", "values": [round(r["ev_med"] - r["ev_lo"], 1) for r in order], "fill_role": "color.accent1", "line_role": "color.surface", "line_width_pt": 1.0,
         "labels": {"show": False}, "points": [{"index": i, "fill_role": "color.ink_muted", "line_role": "color.surface"} for i, e in enumerate(isE) if e]},
        {"name": "Median to 75th pct", "values": [round(r["ev_hi"] - r["ev_med"], 1) for r in order], "fill_role": "color.accent1", "line_role": "color.surface", "line_width_pt": 1.0,
         "labels": {"show": False}, "points": [{"index": i, "fill_role": "color.ink_muted", "line_role": "color.surface"} for i, e in enumerate(isE) if e]}],
    "axes": {"category": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none",
                          "title": "none", "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
             "value": {"visible": True, "line_role": "color.extra_1", "line_width_pt": 0.75, "tick_marks": "out", "reverse": False, "title": "none",
                       "number_format": "#,##0", "min": lo_min, "max": hi_max, "major_unit": 200, "cross_between": "between", "gridlines": "none",
                       "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}}},
    "gap_width": 45, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
    "plot_area": {"x": 0.33, "y": 0.10, "w": 0.45, "h": 0.82}}
ov_lo = max(r["ev_lo"] for r in ff if "ebitda" in r["metric"]); ov_hi = min(r["ev_hi"] for r in ff if "ebitda" in r["metric"])
e_lo = min(r["ev_lo"] for r in ff if "ebitda" in r["metric"]); e_hi = max(r["ev_hi"] for r in ff if "ebitda" in r["metric"])
r_lo = min(r["ev_lo"] for r in ff if "rev" in r["metric"]); r_hi = max(r["ev_hi"] for r in ff if "rev" in r["metric"])
ntm = [r for r in ff if r["method"] == "Trading comps, EV / NTM EBITDA"][0]
p3_bul = [
    f"The three EBITDA methods give {m(e_lo)} to {m(e_hi)} between their 25th and 75th percentiles, and all three overlap at {m(ov_lo)} to {m(ov_hi)} (shaded): {x1(ov_lo/F['ebitda_ltm'])} to {x1(ov_hi/F['ebitda_ltm'])} LTM EBITDA, {x1(ov_lo/F['ebitda_ntm'])} to {x1(ov_hi/F['ebitda_ntm'])} NTM.",
    f"Revenue methods span {m(r_lo)} to {m(r_hi)}, wider because peer revenue multiples vary with margin (sheet 1); they are shown for completeness and add little independent information.",
    f"Precedents sit lowest on both metrics: {m(pff['ev_med'])} at the median EBITDA multiple against {m(ntm['ev_med'])} on NTM trading comps, because the deal set priced below where peers trade today (sheet 2).",
    "No DCF or LBO range is shown: the data supplied covers market multiples only.",
    "Implied equity value needs Falcon's net debt at the valuation date, which is not in the data supplied.",
]
ovl_tbl = {"columns": [{"key": "k", "label": "Falcon metric ($m)", "value_kind": "text", "width_share": 0.46},
                      {"key": "lo", "label": f"At {m(ov_lo)}", "value_kind": "number", "width_share": 0.27},
                      {"key": "hi", "label": f"At {m(ov_hi)}", "value_kind": "number", "width_share": 0.27}],
           "rows": [[f"EBITDA LTM, {n0(F['ebitda_ltm'])}", x1(ov_lo / F['ebitda_ltm']), x1(ov_hi / F['ebitda_ltm'])],
                    [f"EBITDA NTM, {n0(F['ebitda_ntm'])}", x1(ov_lo / F['ebitda_ntm']), x1(ov_hi / F['ebitda_ntm'])],
                    [f"Revenue LTM, {n0(F['rev_ltm'])}", x2(ov_lo / F['rev_ltm']), x2(ov_hi / F['rev_ltm'])],
                    [f"Revenue NTM, {n0(F['rev_ntm'])}", x2(ov_lo / F['rev_ntm']), x2(ov_hi / F['rev_ntm'])]], "header_rows": 1}
def irow(r):
    fmt = x2 if "rev" in r["metric"] else x1
    lbl = {"ebitda_ntm": "EBITDA NTM", "ebitda_ltm": "EBITDA LTM", "rev_ntm": "Revenue NTM", "rev_ltm": "Revenue LTM"}[r["metric"]]
    return [r["method"], lbl, n0(r["base"]), fmt(r["mult_lo"]), fmt(r["mult_med"]), fmt(r["mult_hi"]), n0(r["ev_lo"]), n0(r["ev_med"]), n0(r["ev_hi"]),
            x1(r["ev_med"] / F["ebitda_ltm"])]
irows = [irow(r) for r in ff]
irows += [["Less: net debt", "", "", "", "", "", "[to be supplied]", "[to be supplied]", "[to be supplied]", ""],
          ["Implied equity value", "", "", "", "", "", "[needs net debt]", "[needs net debt]", "[needs net debt]", ""]]
impl_tbl = {"columns": [
    {"key": "me", "label": ["", "Method"], "value_kind": "text"},
    {"key": "fm", "label": ["Falcon metric", "Metric"], "value_kind": "text"},
    {"key": "fv", "label": ["Falcon metric", "$m"], "value_kind": "number"},
    {"key": "q1", "label": ["Peer or deal multiple", "25th pct"], "value_kind": "number"},
    {"key": "md", "label": ["Peer or deal multiple", "Median"], "value_kind": "number"},
    {"key": "q3", "label": ["Peer or deal multiple", "75th pct"], "value_kind": "number"},
    {"key": "e1", "label": ["Implied enterprise value ($m)", "At 25th pct"], "value_kind": "number"},
    {"key": "e2", "label": ["Implied enterprise value ($m)", "At median"], "value_kind": "number"},
    {"key": "e3", "label": ["Implied enterprise value ($m)", "At 75th pct"], "value_kind": "number"},
    {"key": "xl", "label": ["", "Median EV / LTM EBITDA"], "value_kind": "number"}],
    "rows": irows, "header_rows": 2}
s3 = {"id": "p3-football", "layout": "Blank", "title": {"register": "topic", "element": "title"},
  "spec": root([
    head("3 Valuation summary", "Valuation summary: football field and implied values"),
    row("upper", [
        col("ff-block", [exhibit_head("ff-h", "Implied enterprise value by method", "$m; bar spans the 25th to 75th percentile multiple applied to Falcon; break in the bar at the median; EBITDA methods in navy"),
                         {"type": "element", "id": "ff", "kind": "chart", "weight": 1}], weight=1.55),
        col("right3", [bullets("view", "Valuation view", p3_bul),
                       col("ovl-block", [exhibit_head("ovl-h", "The EBITDA overlap restated as multiples", "x; enterprise value at each end of the overlap divided by Falcon's metric"),
                                         {"type": "element", "id": "ovl", "kind": "table", "table": ovl_tbl}])], gap="space.md", weight=1)], weight=1),
    col("impl-block", [exhibit_head("impl-h", "Implied values", "$m unless stated; multiples are the 25th percentile, median and 75th percentile of each set; last column restates each median EV on Falcon LTM EBITDA of $276m"),
                       {"type": "element", "id": "impl", "kind": "table", "table": impl_tbl},
                       text("impl-note", [P("type.footnote", "Percentiles interpolate linearly between ranked values (Excel PERCENTILE.INC). Trading comps: eight listed peers. Precedents: eight announced deals, 2023-2026.")])]),
    footer(3, "Source: falcon_comps.csv, falcon_precedents.csv; Falcon LTM and NTM revenue and EBITDA as supplied. " + SOURCE_TAIL)]),
  "styling": {"impl": {"emphasis": [{"columns": ["e2"], "fill_role": "color.surface_alt", "bold": True, "include_header": True},
                                    {"rows": [len(ff), len(ff) + 1], "fill_role": "keep", "italic": True}],
                       "cell_anchor": "b", "spanner_align": "center", **TLOOK},
              "ovl": {"cell_anchor": "b", **TLOOK}},
  "charts": {"ff": fbar},
  "annotations": [
    {"id": "overlap", "host": "ff", "kind": "band", "anchor": {"values": [round(ov_lo, 1), round(ov_hi, 1)]}, "fill_role": "color.surface_alt",
     "explained_by": {"annotation": "overlap-note"}},
    {"id": "overlap-note", "host": "ff", "kind": "callout", "anchor": {"values": [round(ov_lo, 1), round(ov_hi, 1)]}, "position": "above", "gap_role": "space.xs",
     "pad_role": "space.xs", "fill_role": "color.surface", "line_role": "color.extra_1", "line_width_pt": 0.5,
     "label": {"text": f"EBITDA methods overlap {n0(ov_lo)}-{n0(ov_hi)}", "role": "type.data_label", "ink_role": "color.ink", "align": "left"}},
    {"id": "ranges", "host": "ff", "kind": "category_row", "anchor": {"categories": [0, len(order) - 1]}, "position": "right", "gap_role": "space.sm",
     "cells": [f"{n0(r['ev_lo'])}-{n0(r['ev_hi'])}  (median {n0(r['ev_med'])})" for r in order],
     "role": "type.data_label", "ink_role": "color.ink", "align": "left", "cell_width": "own"}]}

deck = {"slides": [s1, s2, s3]}
(W / "deck").mkdir(exist_ok=True)
json.dump(deck, open(W / "deck" / "deck.json", "w"), indent=1)
print("size corr (EV vs EV/NTM EBITDA):", round(size_corr, 2))
print("fit:", round(fit.slope, 4), round(fit.intercept, 4), "Falcon", round(fit_mult, 3), round(fit_ev))
for s in deck["slides"]:
    print(s["id"])
    for t in [c for c in s["spec"]["root"]["children"]]: pass
print("\n".join(p1_bul + p2_bul + p3_bul))
