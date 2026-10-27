"""Writes deck/deck.json for the Corrin Medical board deck from data.json (figures.py).
Usage: python3 -I gen_deck.py [PAGE_ID ...]   (no ids: every page)"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = json.loads((HERE / "data.json").read_text())
IMG = HERE / "img"
SOURCE = ("Source: Corrin Medical management accounts and transformation plan; FY2025 is eleven months actual and a December forecast. "
          "All figures are illustrative, invented for a fictional company.")
NOTE = "All figures on this page are illustrative: Corrin Medical is a fictional company and every number was invented and computed for this example. "


# ---- tree helpers -----------------------------------------------------------------------------
def T(id, role, text, **kw):
    paras = text if isinstance(text, list) else [{"role": role, "text": text}]
    for p in paras:
        p.setdefault("role", role)
    return {"type": "element", "id": id, "kind": "text", "paragraphs": paras, **kw}


def P(role, text, **kw):
    return {"role": role, "text": text, **kw}


def R(id, children, direction="column", gap="space.sm", pad=None, align="stretch", justify="start", pads=None, **kw):
    lay = {"kind": "flex", "direction": direction, "gap_role": gap, "pad_role": pad, "align": align, "justify": justify}
    if pads:
        lay = {**lay, "pad_roles": pads}
        del lay["pad_role"]
    return {"type": "region", "id": id, "layout": lay, "children": children, **kw}


def PADS(left=None, top=None, right=None, bottom=None):
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def G(id, rows, cols, children, areas, gutter="space.sm", **kw):
    return {"type": "region", "id": id, "layout": {"kind": "grid", "rows": rows, "cols": cols, "gutter_role": gutter, "pad_role": None,
                                                     "areas": areas}, "children": children, **kw}


def IMGN(id, **kw):
    return {"type": "element", "id": id, "kind": "image", **kw}


def RULE(id, w=None, h=None, role="color.rule", lw=12700, **kw):
    return {"type": "element", "id": id, "kind": "rule", "size": {"width_emu": w, "height_emu": h}, "line_role": role, "line_width_emu": lw, **kw}


def SP(id, **kw):
    return R(id, [], **kw)


def TABLE(id, columns, rows, totals=False, **kw):
    return {"type": "element", "id": id, "kind": "table",
            "table": {"columns": columns, "rows": rows, "header_rows": 1, "totals_last_row": totals, "cell_anchor": "m",
                      "header_role": "type.table_header", "cell_role": "type.table_cell", **kw}}


def col(key, label, kind="text", **kw):
    return {"key": key, "label": label, "value_kind": kind, **kw}


def head(kicker, title):
    return R("head", [T("kicker", "type.kicker", kicker), T("title", "type.title", title)], gap="space.xs", justify="end",
             pads=PADS(None, None, None, "space.md"))


def page(id, kicker, title, body, notes, **extra):
    root = R("root", [head(kicker, title), body, T("source", "type.source_line", SOURCE)], gap="space.md",
             pads=PADS("space.margin", "space.xl", "space.margin", "space.margin"))
    s = {"id": id, "layout": "Title Only", "title": {"register": "claim", "element": "title"}, "spec": {"root": root},
         "notes": NOTE + notes}
    s.update(extra)
    return s


def icon(name, **kw):
    return {"svg": str(IMG / f"{name}.svg"), **kw}


def runs(*parts):
    """styling runs from (text, emphasis, ink) parts; ink None keeps the paragraph's"""
    out = []
    for t, em, ink in parts:
        r = {"text": t}
        if em:
            r["emphasis"] = True
        if ink:
            r["ink_role"] = ink
        out.append(r)
    return {"runs": out}


def f1(x):
    return f"{x:,.1f}"


# ---- page 1: summary ----------------------------------------------------------------------------
def p1():
    u25, u28 = D["util25"], D["util28"]
    PA = D["PATHS"]
    fm = {"ebitda": lambda v: f"${v:.0f}m", "margin": lambda v: f"{round(v)}%", "o2c": lambda v: f"{v:.0f}", "dio": lambda v: f"{v:.0f}",
          "otif": lambda v: f"{v:.0f}%", "util": lambda v: f"{round(v)}%", "price": lambda v: f"{v:.1f}%", "ga": lambda v: f"{v:.1f}%"}
    tiles = [
        ("Run-rate EBITDA", "$290m", "+$104m", "from $186m", "p. 5", "ebitda", "$103m from four levers and $38m from volume, less $37m of inflation and run costs"),
        ("EBITDA margin", "20%", "+5 pts", "from 15%", "p. 5", "margin", "EBITDA grows faster than revenue, which rises 5.4% a year to $1,450m"),
        ("Order-to-cash days", "51", "-19 days", "from 70", "p. 2", "o2c", "Avoidable delay falls from 25 to 6 days, releasing $75m of receivables"),
        ("Inventory days", "105", "-37 days", "from 142", "p. 5", "dio", "One global plan across five plants releases $71m of stock"),
        ("On time, in full", "96%", "+9 pts", "from 87%", "p. 6", "otif", "One global supply chain; lines dual-qualified before each move"),
        ("Network utilisation", f"{u28}%", f"+{u28 - u25} pts", f"from {u25}%", "p. 3", "util", "Steps up in 2027 as Salt Lake City closes, and again with Tuttlingen"),
        ("Invoice lines priced right", "99.5%", "+6.7 pts", "from 92.8%", "p. 2", "price", "One contract-price master replaces 12 hand-kept GPO price lists"),
        ("G&A cost, % of revenue", "9.4%", "-2.2 pts", "from 11.6%", "p. 7", "ga", "Brno hub, 190 fewer G&A roles and two fewer management layers"),
    ]
    OWN = [("CFO", "all twelve"), ("CFO", "all twelve"), ("CFO", "C1 to C3, O1"), ("COO", "F3, planning"),
           ("COO", "F1 to F3"), ("COO", "F1, F2"), ("CCO", "C1"), ("CFO", "O1, O2")]
    kids, styling = [], {}
    for n, (label, tgt, delta, base, pg, key, how) in enumerate(tiles):
        tid = f"k{n}"
        path = PA[key]
        top = max(path)
        bars = []
        for yr, v, role in zip(("2025", "2026", "2027", "2028"), path, ("color.accent3", "color.accent2", "color.accent2", "color.accent1")):
            parts = [{"type": "element", "id": f"{tid}-b{yr}", "kind": "rect", "fill_role": role, "weight": v, "size": {"width_emu": None, "height_emu": 73152}}]
            if top - v > 0:
                parts.append(SP(f"{tid}-s{yr}", weight=top - v))
            bars.append(R(f"{tid}-r{yr}", [R(f"{tid}-yc{yr}", [T(f"{tid}-y{yr}", "type.caption", "FY" + yr[2:])], size={"width_emu": 265176, "height_emu": None}),
                                           R(f"{tid}-bar{yr}", parts, direction="row", gap=None, align="center", weight=1),
                                           R(f"{tid}-xc{yr}", [T(f"{tid}-x{yr}", "type.caption", [P("type.caption", fm[key](v), align="right", ink_role="color.accent1" if yr == "2028" else "color.ink_muted")])],
                                             size={"width_emu": 356616, "height_emu": None})],
                          direction="row", gap="space.xs", align="center"))
        kids.append(R(tid, [
            R(f"{tid}-top", [T(f"{tid}-l", "type.h2", label, weight=1, anchor="t"), T(f"{tid}-pg", "type.caption", [P("type.caption", pg, align="right")], weight=0.3)],
              direction="row", gap="space.xs", align="start", size={"width_emu": None, "height_emu": 310896}),
            T(f"{tid}-v", "type.kpi", tgt),
            T(f"{tid}-d", "type.body", f"{delta} {base}"),
            R(f"{tid}-bars", bars, gap="space.xs"),
            T(f"{tid}-how", "type.body", how, weight=1, anchor="t"),
            RULE(f"{tid}-fr", h=12700, role="color.rule"),
            T(f"{tid}-own", "type.caption", [P("type.caption", "Owner: " + OWN[n][0]), P("type.caption", "Initiatives: " + OWN[n][1])]),
        ], gap="space.xs", pad="space.md", fill_role="color.surface_alt", weight=1))
        styling[f"{tid}-own"] = {"paragraphs": {"0": runs(("Owner:", True, "color.ink"), (" " + OWN[n][0], False, None)),
                                                "1": runs(("Initiatives:", True, "color.ink"), (" " + OWN[n][1], False, None))}}
        styling[f"{tid}-d"] = {"paragraphs": {"0": runs((delta, True, "color.accent1"), (" " + base, False, "color.ink_muted"))}}
    tilerow = R("tiles", kids, direction="row", gap="space.sm", align="stretch", weight=1)
    contents = TABLE("contents", [col("pg", "Page", "number", width_share=0.1), col("s", "What it proves")], [
        ["2", "Order to cash: 70 days today, six pain points costing $28m a year"],
        ["3", "Footprint: seven plants become five; utilisation from 64% to 84%"],
        ["4", "Prioritisation: fourteen initiatives on value, ease and cost"],
        ["5", "Value bridge: $186m to $290m of EBITDA, and the cash case"],
        ["6", "Roadmap: 2026 to 2028, six milestones, three dependencies"],
        ["7", "Operating model: five new units, two fewer layers"],
        ["8", "Risks: nine scored before and after mitigation"]],
        emphasis=[{"columns": ["pg"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])
    asks = [("Programme.", " Approve Corrin 2028 and the $165m to deliver it: $98m of one-off cost and $67m of capital, $72m of it in 2026."),
            ("Footprint.", " Approve the exits of Salt Lake City by September 2027 and Tuttlingen by June 2028, subject to consultation."),
            ("Operating model.", " Approve a shared-services hub in Brno, global procurement, and quality and regulatory reporting to the CEO.")]
    ask_rows = []
    for k, (a, b) in enumerate(asks):
        ask_rows.append(R(f"ask{k}", [R(f"ask{k}-n", [T(f"ask{k}-nt", "type.step", [P("type.step", str(k + 1), ink_role="color.ink_inverse", align="center")], weight=1, anchor="m")],
                                        size={"width_emu": 201168, "height_emu": 201168}, fill_role="color.accent1", prst="ellipse"),
                                      T(f"ask{k}-t", "type.body", a + b, weight=1)], direction="row", gap="space.sm", align="start"))
        styling[f"ask{k}-t"] = {"paragraphs": {"0": runs((a, True, None), (b, False, None))}}
    cash = TABLE("cost", [col("c", "$m", width_share=0.4), col("y26", "2026", "number"), col("y27", "2027", "number"), col("y28", "2028", "number"), col("t", "Total", "number")],
                 [["One-off operating cost", "44", "36", "18", "98"], ["Capital expenditure", "28", "25", "14", "67"], ["Cost to achieve", "72", "61", "32", "165"],
                  ["Net cash after cost", "(16)", "52", "99", "135"], ["Cumulative net cash", "(16)", "36", "135", ""]],
                 emphasis=[{"rows": [2], "fill_role": "keep", "bold": True}, {"rows": [4], "fill_role": "keep", "bold": True, "ink_role": "color.accent1"}],
                 edge_rules={"row_interior": {"width_pt": 0.5, "color_role": "color.rule"}})
    top = R("top", [
        R("ask-c", [T("ask-h", "type.h1", "Three approvals asked of the board"),
                    R("ask", ask_rows, gap="space.md", pad="space.md", fill_role="color.surface_alt"),
                    T("ask-n", "type.body", "If approved, the programme launches in January 2026 at M1, and the board reviews it at each of five further milestones to December 2028.")],
          gap="space.xs", weight=1.25),
        R("cost-c", [T("cost-h", "type.h1", "What it costs and when it pays back"), cash,
                     T("cost-n", "type.body", "Cash turns positive in 2027 because working capital is released ahead of the full run-rate.")], gap="space.xs", weight=1),
        R("pack-c", [T("pack-h", "type.h1", "In this pack"), contents], gap="space.xs", weight=1.15)],
        direction="row", gap="space.gutter", align="stretch")
    lower = R("lower", [T("tiles-h", "type.h1", "Eight commitments for FY2028"),
                        T("tiles-u", "type.caption", "FY2028 target in petrol and its change from the FY2025 baseline; bars show FY2025, the FY2026 and FY2027 interim targets and FY2028 on one scale; the page that proves each, top right"),
                        tilerow], gap="space.xs", weight=1)
    body = R("body", [top, lower], gap="space.lg", weight=1)
    return page("p1-summary", "Board decision  |  Corrin 2028",
                "Corrin 2028 adds $104m of EBITDA and releases $146m of working capital by FY2028; the board is asked to approve the programme, two plant exits and the $165m it costs",
                body, "The ask is three approvals: the programme and its $165m, the two plant exits, and the operating model. Walk the eight commitments left to right; each names the page that proves it.",
                styling=styling)


# ---- page 2: order to cash ----------------------------------------------------------------------
def p2():
    st = D["o2c_stages"]
    names = ["Capture order", "Price and credit", "Allocate and pick", "Ship, confirm use", "Invoice", "Collect", "Apply cash"]
    icons = ["order", "tag", "box", "truck", "invoice", "clock", "cash"]
    W0 = 1.2
    chevrons, icon_cells, images = [SP("fl-0", weight=W0)], [SP("ic-0", weight=W0)], {}
    for i in range(7):
        hot = i == 5
        chevrons.append(R(f"st{i+1}", [T(f"st{i+1}-t", "type.step", [P("type.step", f"{i+1}  {names[i]}", ink_role="color.ink_inverse", align="center")], weight=1, anchor="m")],
                          weight=1, fill_role="color.emphasis" if hot else "color.accent1", prst="homePlate" if i == 0 else "chevron",
                          size={"width_emu": None, "height_emu": 283464},
                          pads=PADS("space.md" if i == 0 else "space.lg", "space.xs", "space.lg", "space.xs")))
        images[f"ic{i+1}"] = icon(icons[i], height_role="space.xl", width_role="space.xl", align="center", valign="middle")
        icon_cells.append(R(f"icc{i+1}", [IMGN(f"ic{i+1}")], weight=1, align="center"))
    flow = R("flow", chevrons, direction="row", gap=None, align="stretch")
    iconrow = R("iconrow", icon_cells, direction="row", gap=None, align="center")
    share = [W0 / (W0 + 7)] + [1 / (W0 + 7)] * 7
    cols = [col("m", "Per order")] + [col(f"s{i+1}", "", "number", width_share=share[i + 1], align="center") for i in range(7)]
    rows = [["Days, FY2025"] + [f1(s[1]) for s in st], ["Days, FY2028 target"] + [f1(s[2]) for s in st],
            ["Handled by hand, FY2025"] + [f"{s[3]}%" for s in st], ["Handled by hand, FY2028"] + [f"{s[4]}%" for s in st]]
    metrics = TABLE("metrics", cols, rows, header_align="center",
                    emphasis=[{"rows": [1, 3], "fill_role": "keep", "ink_role": "color.accent1", "bold": True},
                              {"rows": [0, 2], "columns": [f"s{i+1}" for i in range(7)], "fill_role": "keep", "ink_role": "color.ink", "bold": False},
                              {"rows": [0], "columns": ["s6"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": True}])
    codes = ["O1, C1", "C1", "C2", "O1", "C3", "C3"]
    prow = []
    for n, (stepi, text, cost) in enumerate(D["PAIN"]):
        prow.append([str(n + 1), f"{stepi + 1}  {names[stepi]}", text, f1(cost), codes[n]])
    prow.append(["", "Total", "", f1(sum(p[2] for p in D["PAIN"])), ""])
    pains = TABLE("pains", [col("n", "#", "number", width_share=0.04, align="center", total="none"), col("step", "Step", width_share=0.17),
                            col("p", "Pain point and evidence", width_share=0.55, total="none"), col("c", "$m a year", "number", width_share=0.11),
                            col("fix", "Fixed by", total="none")], prow, totals=True,
                  emphasis=[{"columns": ["n"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": True},
                            {"rows": [1], "columns": ["c"], "fill_role": "keep", "bold": True}])
    chart = {
        "type": "BAR_STACKED", "categories": ["FY2025", "FY2028 target"], "number_format": "0",
        "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
        "series": [
            {"name": "Contract terms", "values": [45.0, 45.0], "fill_role": "color.surface_alt", "line_role": "color.rule", "line_width_pt": 0.75,
             "labels": {"show": True, "position": "center", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink"},
             "points": []},
            {"name": "Avoidable delay", "values": [25.0, 6.0], "fill_role": "color.emphasis", "line_role": "none",
             "labels": {"show": True, "position": "center", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink_inverse"},
             "points": []}],
        "axes": {"category": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": True,
                              "gridlines": "none", "title": "none", "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
                 "value": {"visible": False, "min": 0, "max": 72, "cross_between": "between"}},
        "gap_width": 35, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
        "plot_area": {"x": 0.22, "y": 0.03, "w": 0.76, "h": 0.94}}
    split = TABLE("split", [col("l", "Avoidable days, by where they arise", width_share=0.6), col("a", "FY2025", "number"), col("b", "FY2028", "number")], [
        ["Collect past contract terms, step 6", "13.8", "2.5"],
        ["Processing in the other six steps", "11.2", "3.5"],
        ["Avoidable delay", "25.0", "6.0"]], totals=True,
        emphasis=[{"columns": ["b"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])
    right = R("o2c-right", [T("days-h", "type.h1", "Where the 70 days go"),
                            T("days-u", "type.caption", "Average days from order to cash: pale, contract terms, unchanged; orange, avoidable delay"),
                            {"type": "element", "id": "days", "kind": "chart", "weight": 1},
                            split,
                            T("days-t", "type.body", "Cutting 19 avoidable days releases $75m of receivables at FY2028 revenue. The C initiatives capture $18m of the $28m a year, 64%.")],
                gap="space.sm", weight=1)
    fixes = [("C1  Contract-price master", "$10m run-rate for $7m; live in the US in May 2026; fixes pain point 2 and the pricing half of 1"),
             ("C2  Bill-only digitised", "$4m for $8m; surgeons' implant use reported from the theatre on the day of surgery: pain point 3"),
             ("C3  Collections automation", "$4m for $6m; disputes routed by cause and cash matched by rule: pain points 5 and 6"),
             ("O1  Brno hub", "Order entry and invoicing move to one team in January 2027, removing the re-keying in pain points 1 and 4")]
    fixrow = R("fixes", [R(f"fx{k}", [T(f"fx{k}-h", "type.h2", a), T(f"fx{k}-t", "type.body", b)], gap="space.xs", pad="space.sm",
                           fill_role="color.surface_alt", weight=1) for k, (a, b) in enumerate(fixes)], direction="row", gap="space.sm", align="stretch")
    left = R("o2c-left", [T("pain-h", "type.h1", "Six pain points cost $28m a year"),
                          T("pain-u", "type.caption", "Numbers match the orange marks on the flow; cost is annual leakage, rework and write-off"), pains,
                          SP("fix-sp", weight=1),
                          T("fix-h", "type.h1", "Four initiatives remove them"), fixrow],
             gap="space.xs", weight=2.1)
    body = R("body", [
        R("flowblock", [T("flow-h", "type.h1", "The cycle today: seven steps, 70 days from order to cash, 58.8 of them in Collect"),
                        T("flow-u", "type.caption", "Average days per order and the share of orders handled by hand at each step; FY2028 target in petrol; the dominant step in orange"),
                        flow, iconrow, metrics], gap="space.xs"),
        R("lower", [left, right], direction="row", gap="space.gutter", weight=1)], gap="space.lg", weight=1)
    ann = []
    for n, (stepi, _, _) in enumerate(D["PAIN"]):
        ann.append({"id": f"pp{n+1}", "host": f"ic{stepi+1}", "kind": "badge", "anchor": {"box": [0, 0, 1, 1]}, "position": "right",
                    "gap_role": "space.sm", "fill_role": "color.emphasis",
                    "label": {"text": str(n + 1), "role": "type.data_label", "ink_role": "color.ink_inverse", "align": "center"}})
    return page("p2-o2c", "Diagnosis  |  Order to cash",
                "Order-to-cash takes 70 days, 25 beyond contract terms; six pain points cost $28m a year",
                body, "Collect includes the 45 contractual days; only the 13.8 days past terms are avoidable there. Pricing errors at step 2 are the largest leak at $14.6m a year.",
                images=images, charts={"days": chart}, annotations=ann)


# ---- page 3: footprint ----------------------------------------------------------------------------
def p3():
    pl = D["PLANTS"]
    products = {1: "Monitoring systems", 2: "Infusion pumps", 3: "Infusion sets", 4: "Catheters", 5: "EU sterile catheters", 6: "Surgical instruments", 7: "Reprocessing"}
    actions = {1: "Expand: pump electronics", 2: "Exit by September 2027", 3: "Expand: infusion sets", 4: "Retain", 5: "Retain", 6: "Exit by June 2028", 7: "Expand: instruments"}
    rows = []
    for p in pl:
        rows.append([p[1], products[p[0]], str(p[6]), str(p[8]) if p[8] else "-", str(p[7]), str(p[9]) if p[9] else "-",
                     f"{p[10]:,}", f"{p[11]:,}" if p[11] else "-", actions[p[0]]])
    rows.append(["Network", "Seven plants to five", f"{D['cap25']:,}", f"{D['cap28']:,}", str(D["util25"]), str(D["util28"]), f"{D['hc25']:,}", f"{D['hc28']:,}", ""])
    exits = [i for i, p in enumerate(pl) if p[8] == 0]
    table = TABLE("plants", [
        col("p", ["", "Plant"], width_share=0.15), col("pr", ["", "Products"], width_share=0.19, total="none"),
        col("c25", ["Capacity, $m", "FY25"], "number", width_share=0.07), col("c28", ["Capacity, $m", "FY28"], "number", width_share=0.07),
        col("u25", ["Utilisation, %", "FY25"], "number", width_share=0.075, total="none"), col("u28", ["Utilisation, %", "FY28"], "number", width_share=0.075, total="none"),
        col("h25", ["Headcount", "FY25"], "number", width_share=0.075), col("h28", ["Headcount", "FY28"], "number", width_share=0.075),
        col("a", ["", "Action"], total="none")], rows, totals=True, spanner_align="center")
    table["table"]["header_rows"] = 2
    table["table"]["emphasis"] = [{"rows": exits, "fill_role": "keep", "ink_role": "color.emphasis", "bold": False},
                                  {"columns": ["c28", "u28", "h28"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}]
    mp = json.loads((IMG / "plant-map.json").read_text())["plants"]
    images = {"map-na": {"svg": str(IMG / "map-na.svg"), "align": "center", "valign": "middle"},
              "map-eu": {"svg": str(IMG / "map-eu.svg"), "align": "center", "valign": "middle"},
              "key-ar": {"svg": str(IMG / "key-arrow.svg"), "height_role": "space.md", "width_role": "space.xl", "align": "center", "valign": "middle"}}
    place = {1: "right", 2: "above", 3: "right", 4: "left", 5: "below", 6: "below", 7: "above"}
    ann = []
    for p in pl:
        m = mp[str(p[0])]
        x, y, dx, dy = m["x"], m["y"], m["dx"], m["dy"]
        closing = p[8] == 0
        ann.append({"id": f"site{p[0]}", "host": f"map-{m['inset']}", "kind": "mark", "prst": "ellipse",
                    "anchor": {"box": [round(x - dx / 2, 5), round(y - dy / 2, 5), round(x + dx / 2, 5), round(y + dy / 2, 5)]},
                    "fill_role": "color.emphasis" if closing else "color.accent1", "line_role": "color.surface", "line_width_pt": 1.0,
                    "gap_role": "space.xs",
                    "label": {"text": p[1], "role": "type.data_label", "ink_role": "color.ink", "align": "left", "position": place[p[0]]}})
    inset = lambda id, title, w: R(f"{id}-c", [T(f"{id}-h", "type.h2", title), IMGN(id, weight=1)], gap="space.xs", weight=w)
    maps = R("maps", [inset("map-na", "North America", 1.0), inset("map-eu", "Europe", 1.25)], direction="row", gap="space.md", weight=1)
    dot = lambda id, role: R(id, [], size={"width_emu": 118872, "height_emu": 118872}, fill_role=role, prst="ellipse")
    key = R("key", [dot("kd1", "color.emphasis"), T("kt1", "type.caption", "Plant that closes", weight=1),
                    dot("kd2", "color.accent1"), T("kt2", "type.caption", "Plant retained or expanded", weight=1.45),
                    IMGN("key-ar"), T("kt3", "type.caption", "Production lines move", weight=1.3), SP("k-end", weight=0.3)], direction="row", gap="space.sm", align="center")
    facts = R("facts", [
        R("fact1", [T("f1-v", "type.kpi", f"{D['util28']}%"), T("f1-l", "type.body", f"Network utilisation in FY2028, capacity-weighted, from {D['util25']}%")], gap="space.xs", pad="space.md", fill_role="color.surface_alt", weight=1),
        R("fact2", [T("f2-v", "type.kpi", "9 lines"), T("f2-l", "type.body", "Moved in three transfers, one at a time, by June 2028")], gap="space.xs", pad="space.md", fill_role="color.surface_alt", weight=1),
        R("fact3", [T("f3-v", "type.kpi", "-150"), T("f3-l", "type.body", "Net headcount: 4,020 to 3,870, as receiving plants hire 550")], gap="space.xs", pad="space.md", fill_role="color.surface_alt", weight=1)],
        direction="row", gap="space.md", align="stretch")
    left = R("map-col", [T("map-h", "type.h1", "Two regional clusters, two closures, three line transfers"),
                         T("map-u", "type.caption", "Each closing plant's lines go to the nearest plant that already makes or services the product"),
                         maps, key,
                         T("map-n", "type.body", "Salt Lake City's pump electronics move to Minneapolis and its infusion sets to Ciudad Juarez; "
                                                 "Tuttlingen's instruments move 590 km to Brno, which already reprocesses them."),
                         facts],
                gap="space.sm", weight=1.1)
    econ = TABLE("econ", [col("i", "Footprint initiative", width_share=0.42), col("s", "Run-rate saving, $m", "number", width_share=0.2),
                          col("c", "One-off cost, $m", "number", width_share=0.2), col("p", "Payback, years", "number", total="none")], [
        ["F1  Salt Lake City exit", "15", "38", "2.5"], ["F2  Tuttlingen exit to Brno", "9", "24", "2.7"],
        ["F3  Lean and OEE in retained plants", "5", "6", "1.2"], ["Footprint lever", "29", "68", "2.3"]], totals=True,
        emphasis=[{"columns": ["s"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}, {"rows": [0, 1], "columns": ["i"], "fill_role": "keep", "ink_role": "color.emphasis"}])
    right = R("tab-col", [T("tab-h", "type.h1", "Capacity, utilisation and headcount by plant"),
                          T("tab-u", "type.caption", "Capacity is annual output at standard cost; utilisation is output over capacity; FY2028 in petrol, closing plants in orange"),
                          table,
                          T("tab-n", "type.body", "Capacity falls by $130m to $1,250m: the network loses its two least-used plants, at 48% and 41%, and fills the rest."),
                          T("tr-h", "type.h1", "Three line transfers, one at a time"),
                          TABLE("transfers", [col("l", "Lines moved", width_share=0.3), col("f", "From", width_share=0.16), col("t", "To", width_share=0.16),
                                              col("v", "Validation", width_share=0.2), col("c", "Cut-over")], [
                              ["Pump electronics, 2 lines", "Salt Lake City", "Minneapolis", "Jan to Apr 2027", "June 2027"],
                              ["Infusion sets, 3 lines", "Salt Lake City", "Ciudad Juarez", "Mar to Jul 2027", "September 2027"],
                              ["Surgical instruments, 4 lines", "Tuttlingen", "Brno", "Oct 2027 to Mar 2028", "June 2028"]],
                                emphasis=[{"columns": ["f"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": False}]),
                          T("tr-n", "type.footnote", "Each line runs 10 to 12 weeks of bridge stock through its cut-over; validation is re-qualification under the receiving plant's quality system."),
                          T("ec-h", "type.h1", "The $29m saving pays back the $68m in 2.3 years"),
                          econ,
                          T("ec-n", "type.footnote", "Payback is one-off cost and capital over the run-rate saving; F1's saving starts at M4 in September 2027 and F2's at M5 in June 2028.")],
                gap="space.sm", weight=1.3)
    body = R("body", [left, right], direction="row", gap="space.gutter", weight=1)
    return page("p3-footprint", "Footprint  |  Seven plants to five",
                "Two plant exits lift network utilisation from 64% to 84% and save $29m a year",
                body, "The pairing is geographic: each closing plant's lines go to the nearest plant that already makes or services the product. Payback is the one-off cost over the run-rate saving. Map outlines and lakes are Natural Earth, public domain.",
                images=images, annotations=ann)


# ---- page 4: prioritisation matrix ----------------------------------------------------------------
SIZES = [(10, 7), (25, 11), (999, 15)]          # cost to achieve under $Xm -> marker size, pt


def msize(cost):
    return next(s for lim, s in SIZES if cost < lim)


def p4():
    init = D["INIT"]
    bets = {"P2", "F1", "F2", "O1"}

    def ser(name, items, role, size, ink, places):
        return {"name": name, "values": [[it[5], it[3]] for it in items], "line_role": "none", "smooth": False,
                "marker": {"style": "circle", "size": size, "fill_role": role, "line_role": role},
                "labels": {"show": True, "position": "right", "role": "type.data_label", "ink_role": ink},
                "points": [{"index": k, "label": {"text": it[0], **({"position": places[it[0]]} if it[0] in places else {})}} for k, it in enumerate(items)]}
    places = {"O1": "left", "F2": "left", "C3": "below", "P3": "below"}
    series = []
    for grp, role, ink in (("bet", "color.emphasis", "color.ink"), ("other", "color.accent1", "color.ink")):
        for lim, size in SIZES:
            items = [it for it in init if (it[0] in bets) == (grp == "bet") and msize(it[4]) == size]
            if items:
                series.append(ser(f"{'Strategic bets' if grp == 'bet' else 'Other initiatives'}, {size}pt", items, role, size, ink, places))
    dfr = {"name": "Deferred", "values": [[x[3], x[2]] for x in D["DEFERRED"]], "line_role": "none", "smooth": False,
           "marker": {"style": "circle", "size": 7, "fill_role": "color.accent3", "line_role": "color.accent3"},
           "labels": {"show": True, "position": "right", "role": "type.data_label", "ink_role": "color.ink_muted"},
           "points": [{"index": k, "label": {"text": x[0]}} for k, x in enumerate(D["DEFERRED"])]}
    series.append(dfr)
    chart = {"type": "XY_SCATTER", "number_format": "0", "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
             "series": series,
             "axes": {"category": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False,
                                   "min": 1, "max": 5, "major_unit": 1, "number_format": "0", "gridlines": "none", "crosses": "min",
                                   "title": {"text": "Ease of delivery, 1 hard to 5 easy", "role": "type.axis_label", "ink_role": "color.ink_muted", "orientation": "horizontal"},
                                   "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink_muted"}},
                      "value": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False,
                                "min": 0, "max": 18, "major_unit": 2, "number_format": "0", "gridlines": "none", "crosses": "min",
                                "title": {"text": "Run-rate EBITDA, $m", "role": "type.axis_label", "ink_role": "color.ink_muted", "orientation": "along"},
                                "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink_muted"}}},
             "legend": "none", "plot_fill_role": "none", "title": "none",
             "plot_area": {"x": 0.085, "y": 0.07, "w": 0.83, "h": 0.8}}
    lab = lambda t, pos, al: {"text": t, "role": "type.h2", "ink_role": "color.accent1", "align": al, "position": pos}
    ann = [
        {"id": "q-quick", "host": "matrix", "kind": "band", "anchor": {"region": {"x": [3.0, 5.0], "y": [8.0, 18.0]}}, "fill_role": "color.surface_alt",
         "label": lab("Quick wins", "inside_top_right", "right")},
        {"id": "q-bets-l", "host": "matrix", "kind": "band", "anchor": {"region": {"x": [1.08, 2.9], "y": [8.5, 17.6]}}, "fill_role": "color.surface",
         "label": lab("Strategic bets", "inside_top_left", "left")},
        {"id": "q-fill-l", "host": "matrix", "kind": "band", "anchor": {"region": {"x": [3.1, 4.95], "y": [0.4, 7.5]}}, "fill_role": "color.surface",
         "label": lab("Fill-ins", "inside_bottom_right", "right")},
        {"id": "q-low-l", "host": "matrix", "kind": "band", "anchor": {"region": {"x": [1.08, 2.9], "y": [0.4, 7.5]}}, "fill_role": "color.surface",
         "label": lab("Defer unless enabling", "inside_bottom_left", "left")},
        {"id": "q-ease", "host": "matrix", "kind": "reference_line", "anchor": {"value": 3.0, "axis": "category"}, "line_role": "color.accent1",
         "line_width_pt": 0.75, "dash": "dash", "gap_role": "space.xs",
         "label": {"text": "Ease 3", "role": "type.axis_label", "ink_role": "color.accent1", "align": "center", "position": "end_outside"}},
        {"id": "q-value", "host": "matrix", "kind": "reference_line", "anchor": {"value": 8.0}, "line_role": "color.accent1",
         "line_width_pt": 0.75, "dash": "dash", "gap_role": "space.xs",
         "label": {"text": "$8m", "role": "type.axis_label", "ink_role": "color.accent1", "align": "left", "position": "end_outside"}},
    ]
    quad = {}
    for it in init:
        quad[it[0]] = ("Quick win" if it[5] >= 3 else "Strategic bet") if it[3] >= 8 else ("Fill-in" if it[5] >= 3 else "Enabler")
    order = sorted(init, key=lambda it: ("PFCO".index(it[0][0]), it[0]))
    rows = [[it[0], it[1], f"{it[3]:.0f}", f"{it[4]:.0f}", f"{it[5]:.1f}", quad[it[0]], str(it[6])] for it in order]
    rows.append(["", "Total, twelve initiatives", "103", "165", "", "", ""])
    bet_rows = [k for k, it in enumerate(order) if it[0] in bets]
    oth_rows = [k for k, it in enumerate(order) if it[0] not in bets]
    tab = TABLE("inits", [col("c", "Code", width_share=0.07), col("n", "Initiative", width_share=0.4), col("v", "$m EBITDA", "number", width_share=0.11),
                          col("k", "$m cost", "number", width_share=0.1), col("e", "Ease", "number", width_share=0.08, total="none"),
                          col("q", "Quadrant", width_share=0.15, total="none"), col("w", "Wave", "number", total="none")], rows, totals=True,
                emphasis=[{"rows": oth_rows, "columns": ["c"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True},
                          {"rows": bet_rows, "columns": ["c", "q"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": True}])
    size_key = R("skey", [T("sk-t", "type.caption", "Marker size is the cost to achieve:", weight=1.7),
                          R("sk1", [], size={"width_emu": 7 * 12700, "height_emu": 7 * 12700}, fill_role="color.accent3", prst="ellipse"), T("sk1-t", "type.caption", "under $10m", weight=0.75),
                          R("sk2", [], size={"width_emu": 11 * 12700, "height_emu": 11 * 12700}, fill_role="color.accent3", prst="ellipse"), T("sk2-t", "type.caption", "$10m to $25m", weight=0.85),
                          R("sk3", [], size={"width_emu": 15 * 12700, "height_emu": 15 * 12700}, fill_role="color.accent3", prst="ellipse"), T("sk3-t", "type.caption", "over $25m", weight=0.75),
                          SP("sk-end", weight=1.2)],
               direction="row", gap="space.sm", align="center")
    right = R("tab-col", [T("tab-h", "type.h1", "Twelve initiatives in the plan"),
                          T("tab-u", "type.caption", "Run-rate EBITDA and cost to achieve, $m; ease scored 1 hard to 5 easy; strategic bets in orange"),
                          tab,
                          T("tab-n", "type.body", [
                              P("type.body", "The four strategic bets, P2, F1, F2 and O1, carry $47m of the $103m, 46%, and $105m of the $165m cost, 64%: they are where delivery risk sits."),
                              P("type.body", "The quick wins, P1 and C1, add $26m for $13m and start in January 2026. Wave 1 is seven initiatives worth $52m for $52m of cost, all started by April 2026."),
                              P("type.body", "Deferred: X1 own distribution in DACH ($2m, ease 1.5) and X2 single-step ERP replacement ($3m, ease 1.2).")]),
                          T("lv-h", "type.h1", "By lever: what each dollar of EBITDA costs"),
                          TABLE("levers", [col("l", "Lever", width_share=0.4), col("v", "$m EBITDA", "number", width_share=0.16), col("k", "$m cost", "number", width_share=0.16),
                                           col("r", "Cost per $ of EBITDA", "number", total="none")], [
                              ["Procurement, P1 to P3", "34", "17", "0.50"], ["Footprint, F1 to F3", "29", "68", "2.34"],
                              ["Commercial and order to cash, C1 to C3", "18", "21", "1.17"], ["Operating model, O1 to O3", "22", "59", "2.68"],
                              ["Total", "103", "165", ""]], totals=True,
                                emphasis=[{"rows": [1, 3], "columns": ["r"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": True}])],
              gap="space.sm", weight=1)
    left = R("mx-col", [T("mx-h", "type.h1", "Value against ease of delivery, sized by cost"),
                        T("mx-u", "type.caption", "Each point is one initiative by code: strategic bets in orange, other initiatives in petrol, deferred ideas in grey"),
                        {"type": "element", "id": "matrix", "kind": "chart", "weight": 1}, size_key], gap="space.xs", weight=1.1)
    body = R("body", [left, right], direction="row", gap="space.gutter", weight=1)
    return page("p4-priority", "Prioritisation  |  Initiatives",
                "Four strategic bets hold 46% of the value and 64% of the cost; two quick wins start now",
                body, "Ease combines technical, regulatory and people complexity on a 1 to 5 scale scored by the Transformation Office. Quick wins are P1 and C1; marker size groups the cost to achieve.",
                charts={"matrix": chart}, annotations=ann)


# ---- page 5: bridge -------------------------------------------------------------------------------
def p5():
    cats = ["FY2025 EBITDA", "Volume and mix", "Inflation", "Run costs", "Procurement", "Footprint", "Commercial, O2C", "Operating model", "FY2028 run-rate"]
    deltas = [186, 38, -31, -6, 34, 29, 18, 22, 290]
    base, step, run = [], [], 0
    for k, d in enumerate(deltas):
        if k in (0, 8):
            base.append(0); step.append(d); run = d if k == 0 else run
        else:
            lo, hi = min(run, run + d), max(run, run + d)
            base.append(lo); step.append(hi - lo); run += d
    assert run == 290
    fills = [{"index": 0, "fill_role": "color.accent1"}, {"index": 8, "fill_role": "color.accent1"}] + \
            [{"index": k, "fill_role": "color.positive"} for k in (1, 4, 5, 6, 7)] + [{"index": k, "fill_role": "color.negative"} for k in (2, 3)]
    texts = ["$186m", "+38", "(31)", "(6)", "+34", "+29", "+18", "+22", "$290m"]
    chart = {"type": "COLUMN_STACKED", "categories": cats, "number_format": "0", "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
             "series": [
                 {"name": "Base", "values": base, "fill_role": "none", "line_role": "none", "labels": {"show": False}},
                 {"name": "Step", "values": step, "fill_role": "color.accent1", "line_role": "none", "labels": {"show": False}, "points": fills},
                 {"name": "Label", "values": [0] * 9, "fill_role": "none", "line_role": "none",
                  "labels": {"show": True, "position": "inside_base", "role": "type.data_label", "ink_role": "color.ink"},
                  "points": [{"index": k, "label": {"text": t}} for k, t in enumerate(texts)]}],
             "axes": {"category": {"visible": True, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": False, "gridlines": "none",
                                   "title": "none", "labels": {"show": True, "position": "low", "rotation_deg": 0, "role": "type.axis_label", "ink_role": "color.ink"}},
                      "value": {"visible": False, "min": 0, "max": 300, "cross_between": "between"}},
             "gap_width": 30, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
             "plot_area": {"x": 0.1, "y": 0.22, "w": 0.89, "h": 0.54},
             "bridge": {"deltas": deltas, "totals": [0, 8]}}
    ann = [
        {"id": "levers", "host": "bridge", "kind": "bracket", "anchor": {"categories": [4, 7]}, "side": "above", "style": "square",
         "gap_role": "space.lg", "depth_role": "space.xs", "line_role": "color.emphasis", "line_width_pt": 1.0,
         "label": {"text": "Four transformation levers +$103m", "role": "type.h2", "ink_role": "color.emphasis", "align": "center"}},
        {"id": "drift", "host": "bridge", "kind": "bracket", "anchor": {"categories": [1, 3]}, "side": "above", "style": "square",
         "gap_role": "space.lg", "depth_role": "space.xs", "line_role": "color.ink_muted", "line_width_pt": 1.0,
         "label": {"text": "Volume less inflation and run costs +$1m", "role": "type.h2", "ink_role": "color.ink_muted", "align": "center"}},
        {"id": "ctc", "host": "bridge", "kind": "category_row", "anchor": {"categories": [0, 8]}, "position": "below",
         "gap_role": "type.axis_label", "gap_lines": 3, "cell_width": "uniform", "align": "center", "role": "type.data_label", "ink_role": "color.accent1",
         "cells": [None, None, None, None, "$17m", "$68m", "$21m", "$59m", None],
         "shape": {"prst": "rect", "line_role": "color.accent1", "line_width_pt": 0.75, "fill_role": "color.surface", "pad_role": "space.xs"},
         "label": {"text": "Cost to achieve, $165m in all", "role": "type.caption", "ink_role": "color.accent1", "max_width_share": 0.085, "align": "left"}}]
    yrs = ["2026", "2027", "2028"]
    rr = D["run_rate"]; vol = D["volume"]; inf = D["inflation"]; rc = D["run_cost"]; eb = D["ebitda_rr"]; mg = D["margin_rr"]
    b1 = TABLE("build", [col("l", "$m, run-rate at year end", width_share=0.36), col("y25", "2025", "number")] + [col("y" + y[2:], y, "number") for y in yrs], [
        ["Revenue", "1,240"] + [f"{D['REV'][y]:,.0f}" for y in yrs],
        ["EBITDA at FY2025", "186", "186", "186", "186"],
        ["Volume and mix", "", *[f"{vol[y]:.0f}" for y in yrs]],
        ["Inflation", "", *[f"({-inf[y]:.0f})" for y in yrs]],
        ["Run costs", "", *[f"({-rc[y]:.0f})" for y in yrs]],
        ["Transformation levers", "", *[f"{rr[y]:.0f}" for y in yrs]],
        ["Run-rate EBITDA", "186", *[f"{eb[y]:.0f}" for y in yrs]],
        ["EBITDA margin, %", "15.0", *[f"{mg[y]:.1f}" for y in yrs]]],
        emphasis=[{"rows": [6], "fill_role": "keep", "bold": True, "ink_role": "color.accent1"}, {"rows": [7], "fill_role": "keep", "italic": True, "bold": False},
                  {"rows": [0], "fill_role": "keep", "ink_role": "color.ink_muted", "bold": False}])
    iy = D["in_year"]; op = D["opex"]; cp = D["capex"]; wc = D["wc_y"]; nt = D["net_y"]; cu = D["cum"]
    neg = lambda v: f"({abs(v):.0f})" if v < 0 else f"{v:.0f}"
    b2 = TABLE("cash", [col("l", "$m, in year", width_share=0.36), *[col("y" + y[2:], y, "number") for y in yrs], col("t", "Total", "number")], [
        ["In-year savings", *[f"{iy[y]:.0f}" for y in yrs], "154"],
        ["Working capital released", *[f"{wc[y]:.0f}" for y in yrs], "146"],
        ["One-off operating cost", *[f"({op[y]:.0f})" for y in yrs], "(98)"],
        ["Capital expenditure", *[f"({cp[y]:.0f})" for y in yrs], "(67)"],
        ["Net cash", *[neg(nt[y]) for y in yrs], "135"],
        ["Cumulative net cash", *[neg(cu[y]) for y in yrs], ""]],
        emphasis=[{"rows": [4, 5], "fill_role": "keep", "bold": True}, {"rows": [5], "columns": ["y27"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True}])
    lower = R("lower", [
        R("b1c", [T("b1-h", "type.h1", "EBITDA builds over three years"), T("b1-u", "type.caption", "Run-rate at each year end, $m; margin on that year's revenue"), b1], gap="space.xs", weight=1),
        R("b2c", [T("b2-h", "type.h1", "Cash turns positive in 2027"), T("b2-u", "type.caption", "In-year savings as phased in the benefit plan, $m"), b2], gap="space.xs", weight=1),
        R("b3c", [T("b3-h", "type.h1", "What the bridge assumes"), T("b3", "type.body", [
            P("type.body", "Volume and mix: revenue grows 5.4% a year to $1,450m on the current portfolio, with no new launches.", bullet_level=0),
            P("type.body", "Inflation: wages 3.5% and materials 2.5% a year, offset only where index clauses apply.", bullet_level=0),
            P("type.body", "Run costs: $6m a year for the planning system, the hub's licences and the quality function.", bullet_level=0),
            P("type.body", "Working capital: $75m from receivables and $71m from inventory, at FY2028 revenue and cost.", bullet_level=0),
            P("type.body", "Cost to achieve: $165m, $98m of it one-off operating cost and $67m capital; 44% falls in 2026.", bullet_level=0)])],
          gap="space.xs", weight=0.9)], direction="row", gap="space.gutter")
    body = R("body", [R("bridge-c", [T("br-h", "type.h1", "FY2025 EBITDA to FY2028 exit run-rate, $m"),
                                     T("br-u", "type.caption", "Totals in dark petrol, increases in mid petrol, decreases in grey; volume first nets off inflation and run costs; cost to achieve under each lever"),
                                     {"type": "element", "id": "bridge", "kind": "chart", "weight": 1}], gap="space.xs", weight=1), lower], gap="space.lg", weight=1)
    return page("p5-bridge", "Value  |  EBITDA bridge and cash",
                "Volume offsets inflation and run costs; four levers add $103m, taking EBITDA to $290m",
                body, "Volume alone covers inflation and run costs: $38m against $37m. The levers are the case: $103m of run-rate EBITDA for $165m of cost to achieve, a 20% margin on $1,450m of revenue. Cash turns positive in 2027 because working capital is released early.",
                charts={"bridge": chart}, annotations=ann)


# ---- page 6: roadmap ------------------------------------------------------------------------------
def p6():
    init = {i[0]: i for i in D["INIT"]}
    order = sorted(init, key=lambda c: (init[c][7], "PFCO".index(c[0]), c))
    cats = ["", "Milestones"] + [f"{c}  {init[c][1]}" for c in order]
    n = len(cats)
    base = [0, 0] + [init[c][7] for c in order]
    des = [0, 0] + [init[c][8] for c in order]
    dlv = [0, 0] + [init[c][9] for c in order]
    VMIN, VMAX = -1.0, 37.6
    chart = {"type": "BAR_STACKED", "categories": cats, "number_format": "0", "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
             "series": [
                 {"name": "Start", "values": base, "fill_role": "none", "line_role": "none", "labels": {"show": False}},
                 {"name": "Design", "values": des, "fill_role": "color.accent2", "line_role": "none", "labels": {"show": False}},
                 {"name": "Deliver", "values": dlv, "fill_role": "color.accent1", "line_role": "none", "labels": {"show": False}}],
             "axes": {"category": {"visible": True, "line_role": "none", "tick_marks": "none", "reverse": True, "gridlines": "none",
                                   "title": "none", "labels": {"show": True, "role": "type.axis_label", "ink_role": "color.ink"}},
                      "value": {"visible": False, "min": VMIN, "max": VMAX, "cross_between": "between", "crosses": "min"}},
             "gap_width": 55, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
             "plot_area": {"x": 0.235, "y": 0.0, "w": 0.625, "h": 1.0}}
    yl = lambda t: {"text": t, "role": "type.h2", "ink_role": "color.accent1", "align": "left", "position": "inside_top_left"}
    ann = [
        {"id": "y26", "host": "gantt", "kind": "band", "anchor": {"region": {"categories": [0, n - 1], "values": [0, 12]}}, "fill_role": "color.surface", "label": yl("2026")},
        {"id": "y27", "host": "gantt", "kind": "band", "anchor": {"region": {"categories": [0, n - 1], "values": [12, 24]}}, "fill_role": "color.surface_alt", "label": yl("2027")},
        {"id": "y28", "host": "gantt", "kind": "band", "anchor": {"region": {"categories": [0, n - 1], "values": [24, 36]}}, "fill_role": "color.surface", "label": yl("2028")},
    ]
    # quarter ticks in the header row, each labelled with the month the quarter opens
    for m in range(3, 36, 3):
        if m % 12 == 0:
            continue
        ann.append({"id": f"q{m}", "host": "gantt", "kind": "mark", "prst": "line", "anchor": {"region": {"categories": [0, 0], "values": [m - 0.02, m + 0.02]}},
                    "points": [[0.5, 0.5], [0.5, 0.85]], "line_role": "color.ink_muted", "line_width_pt": 0.75,
                    "label": {"text": {3: "Apr", 6: "Jul", 9: "Oct"}[m % 12], "role": "type.axis_label", "ink_role": "color.ink_muted", "align": "center", "position": "right"},
                    "gap_role": "space.xs"})
    for code, m, _, _ in D["MILESTONES"]:
        lo, hi = m - 0.55, m + 0.55
        ann.append({"id": f"ms-{code}", "host": "gantt", "kind": "mark", "prst": "diamond", "anchor": {"region": {"categories": [1, 1], "values": [lo, hi]}},
                    "fill_role": "color.emphasis", "label": {"text": code, "role": "type.data_label", "ink_role": "color.ink", "align": "left",
                                                              "position": "right"}, "gap_role": "space.xs"})
    deps = {"F1": "O3's validation plan, M3", "O1": "C1's price master, M3", "F2": "F1's exit, M4"}
    cells = [{"text": "Delivery waits for", "role": "type.caption", "ink_role": "color.ink_muted"}, None] + [deps.get(c) for c in order]
    ann.append({"id": "deps", "host": "gantt", "kind": "category_row", "anchor": {"categories": [0, n - 1]}, "position": "right",
                "gap_role": "space.md", "cell_width": "own", "align": "left", "role": "type.data_label", "ink_role": "color.emphasis", "cells": cells})
    ms = []
    for k, (code, m, text, date) in enumerate(D["MILESTONES"]):
        ms.append(R(f"m{k}", [T(f"m{k}-c", "type.h2", f"{code}  {date}"), T(f"m{k}-t", "type.body", text)], gap="space.xs", weight=1))
    styling = {f"m{k}-c": {"paragraphs": {"0": runs((code, True, "color.emphasis"), (f"  {date}", False, None))}}
               for k, (code, _, _, date) in enumerate(D["MILESTONES"])}
    body = R("body", [
        R("g-c", [T("g-h", "type.h1", "Twelve initiatives, January 2026 to December 2028, in order of start"),
                  T("g-u", "type.caption", "Light petrol: design; petrol: delivery to full run-rate; orange diamonds: milestones; right: deliveries that wait for another initiative or a milestone"),
                  {"type": "element", "id": "gantt", "kind": "chart", "weight": 1}], gap="space.xs", weight=1),
        R("ms-c", [T("ms-h", "type.h1", "Milestones the board will see reported"), R("ms", ms, direction="row", gap="space.gutter")], gap="space.xs")],
        gap="space.md", weight=1)
    return page("p6-roadmap", "Roadmap  |  2026 to 2028",
                "Seven initiatives start by April 2026; the two plant exits run back to back to June 2028",
                body, "Dependencies: Salt Lake City line transfers cannot begin until the global quality function has issued the validation master plan at M3; the Brno hub takes over order to cash only on the live price master; Tuttlingen moves after Salt Lake City frees the validation team at M4.",
                charts={"gantt": chart}, annotations=ann, styling=styling)


# ---- page 7: operating model -----------------------------------------------------------------------
def p7():
    cols = [
        ("Chief Financial Officer", "same", [("FP&A and treasury", "Planning, reporting, capital", "same"),
                                              ("Global Business Services", "Brno: finance and order to cash", "new"),
                                              ("Tax and internal control", "Group tax, controls, audit liaison", "same")]),
        ("Chief Operating Officer", "same", [("Five plants", "Minneapolis, Juarez, Alajuela, Galway, Brno", "same"),
                                              ("Supply chain and planning", "One plan, inventory, logistics", "new"),
                                              ("Global procurement", "Direct and indirect, from plant buyers", "new")]),
        ("Chief Commercial Officer", "same", [("Americas", "Direct sales, service, distributors", "same"),
                                               ("EMEA and Asia-Pacific", "Direct sales and 31 distributors", "same"),
                                               ("Pricing and contracts", "Price master, GPO terms, rebates", "new")]),
        ("Chief Quality and Regulatory Officer", "new", [("Quality system and CAPA", "From the COO's plants", "moved"),
                                                          ("Regulatory affairs", "EU MDR and FDA, from R&D", "moved"),
                                                          ("Post-market surveillance", "Complaints, vigilance, from sales", "moved")]),
        ("Chief Technology Officer", "same", [("R&D programmes", "Monitoring, infusion, catheters", "same"),
                                               ("Sustaining engineering", "From the plants; runs P2", "moved"),
                                               ("IT and digital", "ERP upgrade and planning system", "same")]),
        ("Chief People Officer", "same", [("HR business partners", "Leaders and works councils", "same"),
                                           ("Talent and reward", "Retention pool for exiting sites", "same"),
                                           ("Change and communications", "One change network for 2028", "same")]),
    ]
    styling = {}
    columns = []
    HEAD_H = 365760
    for k, (head_, kind, units) in enumerate(cols):
        if kind == "new":
            hd = R(f"c{k}-hd", [T(f"c{k}-hd-t", "type.step", [P("type.step", "New: " + head_, ink_role="color.ink")], weight=1, anchor="m")],
                   pads=PADS("space.sm", None, "space.sm", None), fill_role="color.surface", line_role="color.emphasis", line_width_emu=19050,
                   size={"width_emu": None, "height_emu": HEAD_H})
            styling[f"c{k}-hd-t"] = {"paragraphs": {"0": runs(("New:", True, "color.emphasis"), (" " + head_, False, None))}}
        else:
            hd = R(f"c{k}-hd", [T(f"c{k}-hd-t", "type.step", [P("type.step", head_, ink_role="color.ink_inverse")], weight=1, anchor="m")],
                   pads=PADS("space.sm", None, "space.sm", None), fill_role="color.accent1", size={"width_emu": None, "height_emu": HEAD_H})
        rows = [R(f"c{k}-stub", [RULE(f"c{k}-stub-r", w=12700, h=109728)], direction="row", gap=None, pads=PADS("space.md", None, None, None))]
        for u, (nm, det, uk) in enumerate(units):
            uid = f"c{k}-u{u}"
            last = u == len(units) - 1
            style = {"new": dict(line_role="color.emphasis", line_width_emu=19050, fill_role="color.surface"),
                     "moved": dict(line_role="color.accent1", line_width_emu=12700, fill_role="color.surface"),
                     "same": dict(fill_role="color.surface_alt")}[uk]
            tag = {"new": "New", "moved": "Moved", "same": None}[uk]
            box = R(uid, [T(f"{uid}-t", "type.h2", [P("type.h2", (tag + ": " if tag else "") + nm), P("type.caption", det)])], pad="space.sm", **style, size={"width_emu": None, "height_emu": 594360})
            if tag:
                styling[f"{uid}-t"] = {"paragraphs": {"0": runs((tag + ":", True, "color.emphasis" if tag == "New" else "color.accent1"), (" " + nm, False, None))}}
            rail = R(f"{uid}-rail", [RULE(f"{uid}-ra", w=12700, weight=1), RULE(f"{uid}-rb", w=12700, weight=1) if not last else SP(f"{uid}-rb", weight=1)],
                     gap=None, size={"width_emu": 12700, "height_emu": None})
            tick = R(f"{uid}-tk", [SP(f"{uid}-tk0", weight=1), RULE(f"{uid}-tkr", w=91440, h=12700), SP(f"{uid}-tk1", weight=1)], gap=None,
                     size={"width_emu": 91440, "height_emu": None})
            wrap = R(f"{uid}-w", [box], pads=PADS(None, "space.xs", None, "space.xs"), weight=1)
            rows.append(R(f"{uid}-row", [rail, tick, wrap], direction="row", gap=None, align="stretch", pads=PADS("space.md", None, None, None)))
        sub = R(f"c{k}-sub", rows, gap=None)
        columns.append(R(f"c{k}", [R(f"c{k}-v", [RULE(f"c{k}-vr", w=12700, h=137160)], direction="row", gap=None, justify="center"), hd, sub],
                         gap=None, pads=PADS("space.xs", None, "space.xs", None), weight=1))
    l2 = R("l2", columns, direction="row", gap=None, align="start")
    ceo = R("ceo-row", [SP("ceo-sp1", weight=2.5),
                        R("ceo", [T("ceo-t", "type.step", [P("type.step", "Chief Executive Officer", ink_role="color.ink_inverse", align="center")])], pad="space.sm",
                          fill_role="color.accent1", weight=1),
                        RULE("ceo-link", h=12700, weight=0.25),
                        R("tmo", [T("tmo-t", "type.h2", [P("type.h2", "Transformation Office"), P("type.caption", "Runs the M1 to M6 gates; closes December 2028")])],
                          pad="space.sm", fill_role="color.surface_alt", weight=1.4),
                        SP("ceo-sp3", weight=0.85)], direction="row", gap=None, align="center")
    v0 = R("v0", [RULE("v0r", w=12700, h=137160)], direction="row", gap=None, justify="center")
    hbar = R("hbar", [SP("hb-sp1", weight=0.5), RULE("hbr", h=12700, weight=5), SP("hb-sp2", weight=0.5)], direction="row", gap=None)
    key = R("key", [T("key-t", "type.caption", "Orange outline: new, five in all, counting the quality and regulatory function; petrol outline: moved from another function; grey: unchanged; the Transformation Office closes in December 2028")],
            pads=PADS(None, "space.md", None, None))
    chart_block = R("org", [ceo, v0, hbar, l2, key], gap=None)
    rows = [list(r) for r in D["OPM"]]
    tab = TABLE("opm", [col("m", "Measure", width_share=0.6), col("a", "FY2025", "number"), col("b", "FY2028", "number")], rows,
                emphasis=[{"columns": ["b"], "fill_role": "keep", "ink_role": "color.accent1", "bold": True},
                          {"rows": [5], "columns": ["m"], "fill_role": "keep", "bold": True}])
    gov = TABLE("gov", [col("f", "Forum", width_share=0.36), col("c", "Chair", width_share=0.13), col("w", "Meets", width_share=0.14), col("d", "Decides")], [
        ["Board", "Chair", "Quarterly", "Passes gates M1 to M6"],
        ["Transformation committee", "CEO", "Monthly", "Scope, budget and sequence"],
        ["Transformation Office", "Director", "Weekly", "Plans, risks and benefit tracking"],
        ["Benefit review", "CFO", "Monthly", "What enters the run-rate"]],
        emphasis=[{"columns": ["f"], "fill_role": "keep", "bold": True}])
    principles = ["One owner per process end to end: order to cash sits in the Brno hub, not in fourteen countries.",
                  "Quality and regulatory report to the CEO, independent of the plants they audit.",
                  "Plants make; procurement, planning and engineering serve all five plants."]
    prs = []
    for k, t in enumerate(principles):
        prs.append(R(f"pr{k}", [R(f"pr{k}-n", [T(f"pr{k}-nt", "type.step", [P("type.step", str(k + 1), ink_role="color.ink_inverse", align="center")], weight=1, anchor="m")],
                                   size={"width_emu": 182880, "height_emu": 182880}, fill_role="color.accent1", prst="ellipse"),
                                 T(f"pr{k}-t", "type.body", t, weight=1)], direction="row", gap="space.sm", align="start"))
    strip = R("strip", [
        R("s1c", [T("s1-h", "type.h1", "Three design principles"), R("prs", prs, gap="space.sm")], gap="space.sm", weight=1),
        R("s2c", [T("s2-h", "type.h1", "Layers, spans and G&A cost"), tab], gap="space.xs", weight=0.85),
        R("s3c", [T("s3-h", "type.h1", "Governance to December 2028"), gov], gap="space.xs", weight=1.15)],
        direction="row", gap="space.gutter")
    body = R("body", [chart_block, SP("org-gap", weight=1), strip], gap="space.md", weight=1)
    return page("p7-opmodel", "Operating model  |  2028",
                "Five new units and two fewer layers cut G&A from 11.6% to 9.4% of revenue",
                body, "New units: Global Business Services in Brno, supply chain and planning, global procurement, pricing and contracts, and the quality and regulatory function reporting to the CEO.",
                styling=styling)


# ---- page 8: risks -------------------------------------------------------------------------------
def zone(l, i):
    s = l * i
    return "color.zone_high" if s >= 15 else ("color.zone_mid" if s >= 6 else "color.zone_low")


def matrix(prefix, title, li, si):
    cells, areas = [], []
    by = {}
    for r in D["RISKS"]:
        by.setdefault((r[li], r[si]), []).append(r[0])
    for row in range(5):
        L = 5 - row
        cid = f"{prefix}-l{L}"
        cells.append(T(cid, "type.caption", [P("type.caption", str(L), align="center")], anchor="m"))
        areas.append({"child_id": cid, "row": row, "col": 0, "row_span": 1, "col_span": 1})
        for S in range(1, 6):
            cid = f"{prefix}-{L}{S}"
            codes = by.get((L, S), [])
            if codes:
                cells.append(T(cid, "type.cell_tag", [P("type.cell_tag", c, align="center") for c in codes], fill_role=zone(L, S), anchor="m"))
            else:
                cells.append(SP(cid, fill_role=zone(L, S)))
            areas.append({"child_id": cid, "row": row, "col": S, "row_span": 1, "col_span": 1})
    g = G(f"{prefix}-grid", 5, 6, cells, areas, gutter="space.xs", weight=1)
    labs = R(f"{prefix}-sev", [SP(f"{prefix}-corner", weight=1)] + [T(f"{prefix}-s{S}", "type.caption", [P("type.caption", str(S), align="center")], weight=1) for S in range(1, 6)],
             direction="row", gap="space.xs")
    axis = R(f"{prefix}-ax", [SP(f"{prefix}-ax0", weight=1), T(f"{prefix}-axt", "type.caption", [P("type.caption", "Severity", align="center")], weight=5)],
             direction="row", gap="space.xs")
    return R(f"{prefix}-c", [T(f"{prefix}-h", "type.h2", title), T(f"{prefix}-lk", "type.caption", "Likelihood"), g, labs, axis], gap="space.xs", weight=1)


def p8():
    mb = matrix("mb", "Before mitigation", 2, 3)
    ma = matrix("ma", "After mitigation", 4, 5)
    keyrow = R("zkey", [
        R("zk1", [SP("zk1-s", fill_role="color.zone_low", size={"width_emu": 137160, "height_emu": 91440}), T("zk1-t", "type.caption", "Acceptable: 5 or less")], direction="row", gap="space.xs", align="center", weight=1),
        R("zk2", [SP("zk2-s", fill_role="color.zone_mid", size={"width_emu": 137160, "height_emu": 91440}), T("zk2-t", "type.caption", "ALARP: 6 to 12")], direction="row", gap="space.xs", align="center", weight=0.85),
        R("zk3", [SP("zk3-s", fill_role="color.zone_high", size={"width_emu": 137160, "height_emu": 91440}), T("zk3-t", "type.caption", "Unacceptable: 15 or more")], direction="row", gap="space.xs", align="center", weight=1.1)],
        direction="row", gap="space.md")
    left = R("mx", [T("mx-h", "type.h1", "Nine risks, before and after mitigation"),
                    T("mx-u", "type.caption", "Likelihood 1 rare to 5 frequent; severity 1 negligible to 5 catastrophic; score is the product"),
                    R("pair", [mb, ma], direction="row", gap="space.gutter", weight=1), keyrow,
                    T("mx-n", "type.body", "R1 and R2 come from moving validated lines. Bridge stock, build-ahead and dual qualification cut their likelihood; severity stays high because a supply gap reaches patients.")],
             gap="space.sm", weight=0.95)
    texts = {
        "R1": ("Line re-validation delays the Salt Lake City exit", "Validation master plan per line; 10 weeks of bridge stock"),
        "R2": ("US hospital supply interrupted during line moves", "12-week build-ahead; lines dual-qualified before cut-over"),
        "R3": ("GPO renegotiation delays price-master benefits", "Phase by contract renewal date; leakage tracked monthly"),
        "R4": ("Order-management upgrade overruns", "Upgrade the current ERP in place; no big-bang replacement"),
        "R5": ("Key staff leave the two closing plants early", "$4.2m retention pool; knowledge transfer signed off per line"),
        "R6": ("Works-council consultation extends the German exit", "Consultation opens Q1 2027 with 4 months of float"),
        "R7": ("EU MDR recertification collides with transfers", "One regulatory calendar; notified-body slots booked for 2027"),
        "R8": ("Inflation runs above the $31m in the plan", "Index clauses in 70% of supply contracts by 2027"),
        "R9": ("Change fatigue lowers sales productivity", "Commercial roles change once, in a single wave"),
    }
    rows = []
    for r in D["RISKS"]:
        mc = D["MITIG"][r[0]]
        rows.append([r[0], texts[r[0]][0], r[6], texts[r[0]][1], f"{mc:.1f}" if mc else "-", str(r[2] * r[3]), str(r[4] * r[5])])
    emph = [{"columns": ["id"], "fill_role": "keep", "bold": True}]
    for k, r in enumerate(D["RISKS"]):
        emph.append({"rows": [k], "columns": ["b"], "fill_role": zone(r[2], r[3]), "bold": True})
        emph.append({"rows": [k], "columns": ["a"], "fill_role": zone(r[4], r[5]), "bold": True})
    emph.append({"rows": [0, 1], "columns": ["id"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": True})
    reg = TABLE("register", [col("id", "ID", width_share=0.045), col("r", "Risk", width_share=0.3), col("o", "Owner", width_share=0.085),
                             col("m", "Mitigation", width_share=0.35), col("c", "Cost, $m", "number", width_share=0.08),
                             col("b", "Before", "number", width_share=0.07, align="center"),
                             col("a", "After", "number", align="center")], rows, header_align="left", emphasis=emph)
    ew = TABLE("warn", [col("id", "ID", width_share=0.06), col("i", "Early-warning indicator", width_share=0.43), col("t", "Trigger", width_share=0.28), col("e", "Escalates to")], [
        ["R1", "Validation deviations per moved line", "More than 2 open per line", "Board, next meeting"],
        ["R2", "US service level, moved product families", "Under 95% for 2 weeks", "CEO within 48 hours"],
        ["R3", "Contracts repriced to the renewal plan", "Under 80% of plan", "CCO and CFO"],
        ["R4", "Upgrade sprints closed to plan", "Under 80% in a quarter", "Audit committee"],
        ["R5", "Regretted leavers at the closing plants", "More than 5 in a quarter", "CEO and CPO"],
        ["R6", "Works-council dates met as agreed", "Any date 4 weeks late", "CEO and CPO"],
        ["R7", "Notified-body slots confirmed for 2027", "Under 3 confirmed by June", "CQRO and CEO"],
        ["R8", "Supplier price index against the plan", "Above plan two quarters", "Audit committee"]],
        emphasis=[{"rows": [0, 1], "columns": ["id"], "fill_role": "keep", "ink_role": "color.emphasis", "bold": True}, {"rows": [2, 3, 4, 5, 6, 7], "columns": ["id"], "fill_role": "keep", "bold": True}])
    zt = TABLE("zones", [col("z", "Zone", width_share=0.5), col("b", "Before", "number", align="center", width_share=0.25), col("a", "After", "number", align="center")], [
        ["Unacceptable", "2", "0"], ["ALARP", "7", "6"], ["Acceptable", "0", "3"], ["Sum of scores", "100", "48"]],
        emphasis=[{"rows": [0], "columns": ["z"], "fill_role": "color.zone_high", "bold": True}, {"rows": [1], "columns": ["z"], "fill_role": "color.zone_mid", "bold": True},
                  {"rows": [2], "columns": ["z"], "fill_role": "color.zone_low", "bold": True},
                  {"rows": [3], "fill_role": "keep", "bold": True}])
    zones = R("zn-c", [T("zn-h", "type.h1", "Risks by zone"), T("zn-u", "type.caption", "Count of risks, and their scores summed"), zt],
              gap="space.xs", weight=0.75)
    warn = R("ew-c", [T("ew-h", "type.h1", "What the board will see before a risk lands"), T("ew-u", "type.caption", "Indicators reported monthly by the Transformation Office; a trigger escalates the risk out of cycle"), ew],
             gap="space.xs", weight=2.25)
    right = R("reg-c", [T("reg-h", "type.h1", "Risk register"), T("reg-u", "type.caption", "Mitigation costs $14m in all, inside the $165m; scores before and after mitigation, shaded by zone; owners report monthly"), reg,
                        SP("ew-sp", weight=1),
                        R("lowr", [zones, warn], direction="row", gap="space.gutter", align="start")],
              gap="space.xs", weight=1.35)
    body = R("body", [left, right], direction="row", gap="space.gutter", weight=1)
    return page("p8-risk", "Risk  |  Delivery risks",
                "Mitigation brings all nine risks to ALARP or below; the two worst come from line transfers",
                body, "Zones follow the ISO 14971 convention the board knows from product risk: acceptable, as low as reasonably practicable, and unacceptable. Owners: COO, CFO, CCO, CPO and the Chief Quality and Regulatory Officer.")


PAGES = {"p1-summary": p1, "p2-o2c": p2, "p3-footprint": p3, "p4-priority": p4, "p5-bridge": p5, "p6-roadmap": p6, "p7-opmodel": p7, "p8-risk": p8}
if __name__ == "__main__":
    ids = sys.argv[1:] or list(PAGES)
    deck = {"slides": [PAGES[i]() for i in ids]}
    (HERE / "deck").mkdir(exist_ok=True)
    (HERE / "deck" / "deck.json").write_text(json.dumps(deck, indent=1))
    print("wrote", [s["id"] for s in deck["slides"]])
