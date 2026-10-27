"""Corrin Medical (fictional): every figure the eight board pages state, invented for an
illustrative deck, computed and asserted here. Prints the figures for --computed on stdout
and writes data.json beside this file for the deck generator."""
import json
import sys
from pathlib import Path

out: list[str] = []


def f0(x): return f"{x:,.0f}"
def f1(x): return f"{x:,.1f}"
def add(*xs): out.extend(xs)


# ---- P&L baseline and target -------------------------------------------------------------
REV = {2025: 1240.0, 2026: 1310.0, 2027: 1380.0, 2028: 1450.0}
EBITDA25 = 186.0
COGS25, COGS28 = 620.0, 696.0          # cost of goods sold, $m

# bridge FY2025 EBITDA -> FY2028 exit run-rate, $m
bridge = [("FY2025 EBITDA", EBITDA25, "total"), ("Volume and mix", 38.0, "step"),
          ("Procurement", 34.0, "step"), ("Footprint", 29.0, "step"), ("Commercial and order-to-cash", 18.0, "step"),
          ("Operating model", 22.0, "step"), ("Wage and material inflation", -31.0, "step"),
          ("Recurring run costs", -6.0, "step")]
ebitda28 = round(sum(v for _, v, _ in bridge), 1)
assert ebitda28 == 290.0, ebitda28
m25 = round(EBITDA25 / REV[2025] * 100, 1)
m28 = round(ebitda28 / REV[2028] * 100, 1)
assert (m25, m28) == (15.0, 20.0)
uplift = round(ebitda28 - EBITDA25, 1)
assert uplift == 104.0
levers = {"Procurement": 34.0, "Footprint": 29.0, "Commercial and order-to-cash": 18.0, "Operating model": 22.0}
lever_total = sum(levers.values())
assert lever_total == 103.0
add(f0(EBITDA25), f0(ebitda28), f1(m25), f1(m28), f0(uplift), f0(lever_total), "5.0", "37")

# ---- initiatives: run-rate $m, cost to achieve $m, ease 1-5, lever, wave -------------------
INIT = [
    # code, name, lever, run-rate, cost, ease, wave, start, design, deliver (months from Jan 2026)
    ("P1", "Direct-material re-sourcing", "Procurement", 16.0, 6.0, 3.8, 1, 0, 4, 14),
    ("P2", "BOM value engineering, top 20 SKUs", "Procurement", 11.0, 9.0, 2.3, 2, 6, 6, 18),
    ("P3", "Indirect spend and freight tender", "Procurement", 7.0, 2.0, 4.4, 1, 1, 3, 6),
    ("F1", "Salt Lake City exit", "Footprint", 15.0, 38.0, 1.8, 2, 6, 6, 9),
    ("F2", "Tuttlingen exit to Brno", "Footprint", 9.0, 24.0, 2.2, 3, 13, 8, 9),
    ("F3", "Lean and OEE in retained plants", "Footprint", 5.0, 6.0, 4.0, 1, 2, 3, 22),
    ("C1", "Contract-price master, GPO compliance", "Commercial and order-to-cash", 10.0, 7.0, 4.2, 1, 0, 5, 7),
    ("C2", "Bill-only and consignment digitised", "Commercial and order-to-cash", 4.0, 8.0, 3.3, 2, 9, 5, 10),
    ("C3", "Collections and dispute automation", "Commercial and order-to-cash", 4.0, 6.0, 3.6, 1, 3, 4, 8),
    ("O1", "Shared-services hub, Brno", "Operating model", 12.0, 34.0, 2.7, 2, 6, 6, 18),
    ("O2", "Spans and layers, commercial and G&A", "Operating model", 7.0, 9.0, 3.4, 1, 1, 4, 5),
    ("O3", "Global quality and regulatory function", "Operating model", 3.0, 16.0, 2.4, 1, 3, 4, 9),
]
DEFERRED = [("X1", "Own distribution in DACH", 2.0, 1.5), ("X2", "Single-step ERP replacement", 3.0, 1.2)]
for lever, v in levers.items():
    s = round(sum(i[3] for i in INIT if i[2] == lever), 1)
    assert s == v, (lever, s, v)
cta = round(sum(i[4] for i in INIT), 1)
assert cta == 165.0, cta
cta_by_lever = {lv: round(sum(i[4] for i in INIT if i[2] == lv), 1) for lv in levers}
assert cta_by_lever == {"Procurement": 17.0, "Footprint": 68.0, "Commercial and order-to-cash": 21.0, "Operating model": 59.0}, cta_by_lever
add(f0(cta), *[f0(v) for v in cta_by_lever.values()])
for i in INIT:
    add(f0(i[3]), f0(i[4]), f"{i[5]:.1f}")
for x in DEFERRED:
    add(f0(x[2]), f"{x[3]:.1f}")
EASE_MID, VALUE_MID = 3.0, 8.0
quick = [i[0] for i in INIT if i[5] >= EASE_MID and i[3] >= VALUE_MID]
bets = [i[0] for i in INIT if i[5] < EASE_MID and i[3] >= VALUE_MID]
fills = [i[0] for i in INIT if i[5] >= EASE_MID and i[3] < VALUE_MID]
hard_small = [i[0] for i in INIT if i[5] < EASE_MID and i[3] < VALUE_MID]
assert quick == ["P1", "C1"] and bets == ["P2", "F1", "F2", "O1"], (quick, bets)
quick_val = sum(i[3] for i in INIT if i[0] in quick)
bets_val = sum(i[3] for i in INIT if i[0] in bets)
bets_cost = sum(i[4] for i in INIT if i[0] in bets)
assert (quick_val, bets_val, bets_cost) == (26.0, 47.0, 105.0)
# no initiative sits on a threshold: the quadrant call is never a tie
assert all(abs(i[5] - EASE_MID) >= 0.25 and abs(i[3] - VALUE_MID) >= 1 for i in INIT), [i[0] for i in INIT if abs(i[5] - EASE_MID) < 0.25 or abs(i[3] - VALUE_MID) < 1]
bets_share = round(bets_val / lever_total * 100, 1)
bets_cost_share = round(bets_cost / cta * 100, 1)
assert (bets_share, bets_cost_share) == (45.6, 63.6)
wave1 = [i for i in INIT if i[6] == 1]
wave1_val, wave1_cost = sum(i[3] for i in wave1), sum(i[4] for i in wave1)
assert (len(wave1), wave1_val, wave1_cost) == (7, 52.0, 52.0), (len(wave1), wave1_val, wave1_cost)
add(f0(quick_val), f0(bets_val), f0(bets_cost), f0(bets_share), f0(bets_cost_share), f0(wave1_val), f0(wave1_cost))
deferred_val = sum(x[2] for x in DEFERRED)
add(f0(deferred_val))

# ---- phasing and cash case ---------------------------------------------------------------
run_rate = {2026: 32.0, 2027: 71.0, 2028: 103.0}
volume = {2026: 12.0, 2027: 25.0, 2028: 38.0}
inflation = {2026: -10.0, 2027: -21.0, 2028: -31.0}
run_cost = {2026: -3.0, 2027: -5.0, 2028: -6.0}
ebitda_rr = {y: round(EBITDA25 + volume[y] + run_rate[y] + inflation[y] + run_cost[y], 1) for y in run_rate}
assert ebitda_rr == {2026: 217.0, 2027: 256.0, 2028: 290.0}, ebitda_rr
margin_rr = {y: round(ebitda_rr[y] / REV[y] * 100, 1) for y in run_rate}
assert margin_rr == {2026: 16.6, 2027: 18.6, 2028: 20.0}, margin_rr
# in-year savings as phased in the benefit plan, whole $m; each within $1m of the mean of the
# run-rate at the start and end of its year
in_year = {2026: 16.0, 2027: 51.0, 2028: 87.0}
prev_rr = {2026: 0.0, 2027: run_rate[2026], 2028: run_rate[2027]}
assert all(abs(in_year[y] - (prev_rr[y] + run_rate[y]) / 2) <= 1.0 for y in in_year)
opex = {2026: 44.0, 2027: 36.0, 2028: 18.0}
capex = {2026: 28.0, 2027: 25.0, 2028: 14.0}
cost_y = {y: opex[y] + capex[y] for y in opex}
assert cost_y == {2026: 72.0, 2027: 61.0, 2028: 32.0} and sum(cost_y.values()) == cta
assert (sum(opex.values()), sum(capex.values())) == (98.0, 67.0)

# working capital: order-to-cash days and inventory days on FY2028 revenue and COGS
o2c_stages = [  # name, days FY2025, days FY2028 target, manual touch % FY2025, FY2028
    ("Capture order", 0.9, 0.2, 41, 10),
    ("Check price and credit", 1.6, 0.3, 36, 8),
    ("Allocate and pick", 1.2, 0.8, 22, 15),
    ("Ship and confirm use", 3.1, 1.6, 30, 12),
    ("Invoice", 2.4, 0.2, 18, 3),
    ("Collect", 58.8, 47.5, 25, 8),
    ("Apply cash, settle disputes", 2.0, 0.4, 28, 6),
]
TERMS = 45.0
o2c25 = round(sum(s[1] for s in o2c_stages), 1)
o2c28 = round(sum(s[2] for s in o2c_stages), 1)
assert (o2c25, o2c28) == (70.0, 51.0), (o2c25, o2c28)
avoid25 = round(o2c25 - TERMS, 1)
avoid28 = round(o2c28 - TERMS, 1)
overdue25 = round(58.8 - TERMS, 1)
overdue28 = round(47.5 - TERMS, 1)
assert (avoid25, avoid28, overdue25, overdue28) == (25.0, 6.0, 13.8, 2.5)
o2c_cut = round(o2c25 - o2c28, 1)
recv_exact = o2c_cut * REV[2028] / 365
DIO25, DIO28 = 142, 105
inv_exact = (DIO25 - DIO28) * COGS28 / 365
# stated in whole $m; the parts add to the stated whole
recv_release, inv_release, wc_release = round(recv_exact), round(inv_exact), round(recv_exact + inv_exact)
assert (o2c_cut, recv_release, inv_release, wc_release) == (19.0, 75, 71, 146) and recv_release + inv_release == wc_release, (recv_exact, inv_exact)
# headline day counts are whole days
assert all(float(v).is_integer() for v in (o2c25, o2c28, avoid25, avoid28, o2c_cut))
add(f0(o2c25), f0(o2c28), f0(avoid25), f0(avoid28), f0(TERMS), f1(overdue25), f1(overdue28), f0(o2c_cut),
    f0(recv_release), f0(inv_release), f0(wc_release), f0(DIO25), f0(DIO28), str(DIO25 - DIO28))
proc25, proc28 = round(o2c25 - 58.8, 1), round(o2c28 - 47.5, 1)   # days in every step but Collect
assert (proc25, proc28) == (11.2, 3.5) and round(proc25 + overdue25, 1) == avoid25 and round(proc28 + overdue28, 1) == avoid28
collect_share = round(58.8 / o2c25 * 100)
assert collect_share == 84
add(f1(proc25), f1(proc28), str(collect_share), "58.8")
for s in o2c_stages:
    add(f1(s[1]), f1(s[2]), str(s[3]), str(s[4]))
wc_y = {2026: 40.0, 2027: 62.0, 2028: 44.0}
assert sum(wc_y.values()) == wc_release
net_y = {y: round(in_year[y] + wc_y[y] - cost_y[y], 1) for y in cost_y}
cum, c = {}, 0.0
for y in sorted(net_y):
    c = round(c + net_y[y], 1)
    cum[y] = c
assert net_y == {2026: -16.0, 2027: 52.0, 2028: 99.0} and cum == {2026: -16.0, 2027: 36.0, 2028: 135.0}, (net_y, cum)
assert sum(in_year.values()) == 154 and sum(net_y.values()) == 135
add(*[f0(v) for v in run_rate.values()], *[f0(v) for v in volume.values()], *[f0(-v) for v in inflation.values()],
    *[f0(-v) for v in run_cost.values()], *[f0(v) for v in ebitda_rr.values()], *[f1(v) for v in margin_rr.values()],
    *[f0(v) for v in in_year.values()], *[f0(v) for v in opex.values()], *[f0(v) for v in capex.values()],
    *[f0(v) for v in cost_y.values()], *[f0(v) for v in wc_y.values()], *[f0(abs(v)) for v in net_y.values()],
    *[f0(abs(v)) for v in cum.values()], "98", "67", "154", "135", *[f0(v) for v in REV.values()])

# pain points: step index (0-based), text, annual cost $m
PAIN = [
    (0, "41% of orders arrive by fax or e-mail and are re-keyed; 3.8% carry an entry error", 3.1),
    (1, "12 GPO price lists kept by hand; 7.2% of invoice lines priced wrong", 14.6),
    (3, "Bill-only implant use reported 9.0 days after surgery; consignment counted by hand", 2.8),
    (4, "Invoices issued 2.4 days after shipment; 18% need a manual release", 1.2),
    (5, "9.4% of invoices disputed, 34 days to resolve: 13.8 days past terms", 4.9),
    (6, "28% of remittances matched to invoices by hand", 1.4),
]
pain_total = round(sum(p[2] for p in PAIN), 1)
assert pain_total == 28.0
c_capture = round(levers["Commercial and order-to-cash"] / pain_total * 100, 1)
assert c_capture == 64.3
add(f0(pain_total), f1(pain_total), *[f1(p[2]) for p in PAIN], f0(c_capture), "41", "3.8", "12", "7.2", "9.0", "2.4", "18", "9.4", "34", "28")
invoice_acc25, invoice_acc28 = round(100 - 7.2, 1), 99.5
assert invoice_acc25 == 92.8
add(f1(invoice_acc25), f1(invoice_acc28))

# ---- plants -------------------------------------------------------------------------------
PLANTS = [  # n, name, country, lat, lon, products, capacity $m FY25, util FY25 %, capacity FY28, util FY28 %, hc25, hc28, action
    (1, "Minneapolis", "US", 44.98, -93.27, "Monitoring systems", 260, 66, 290, 86, 640, 760, "Retain; takes pump electronics"),
    (2, "Salt Lake City", "US", 40.76, -111.89, "Infusion pumps", 150, 48, 0, None, 410, 0, "Exit by September 2027"),
    (3, "Ciudad Juarez", "MX", 31.69, -106.42, "Infusion sets, consumables", 300, 79, 360, 88, 980, 1150, "Expand: two lines"),
    (4, "Alajuela", "CR", 10.02, -84.21, "Catheters", 210, 70, 210, 81, 720, 760, "Retain"),
    (5, "Galway", "IE", 53.27, -9.05, "Catheters, EU sterile", 190, 66, 190, 78, 530, 560, "Retain"),
    (6, "Tuttlingen", "DE", 47.98, 8.82, "Surgical instruments", 110, 41, 0, None, 290, 0, "Exit by June 2028"),
    (7, "Brno", "CZ", 49.19, 16.61, "Instruments, reprocessing", 160, 52, 200, 80, 450, 640, "Expand: takes Tuttlingen"),
]
cap25 = sum(p[6] for p in PLANTS)
cap28 = sum(p[8] for p in PLANTS)
used25 = sum(p[6] * p[7] / 100 for p in PLANTS)
used28 = sum(p[8] * (p[9] or 0) / 100 for p in PLANTS)
util25 = round(used25 / cap25 * 100, 1)
util28 = round(used28 / cap28 * 100, 1)
hc25 = sum(p[10] for p in PLANTS)
hc28 = sum(p[11] for p in PLANTS)
assert (cap25, cap28, hc25, hc28) == (1380, 1250, 4020, 3870), (cap25, cap28, hc25, hc28)
assert (util25, util28) == (63.9, 83.6), (util25, util28)
u25, u28 = round(util25), round(util28)       # stated in whole percent
assert (u25, u28, u28 - u25) == (64, 84, 20)
add(f0(cap25), f0(cap28), f0(u25), f0(u28), "20", f0(hc25), f0(hc28), f0(hc25 - hc28), str(cap25 - cap28))
for p in PLANTS:
    add(str(p[6]), str(p[7]), str(p[8]), str(p[9]) if p[9] else "", f0(p[10]), f0(p[11]))
fp_saving = levers["Footprint"]
fp_one_off = cta_by_lever["Footprint"]
add(f0(fp_saving), f0(fp_one_off))

# ---- operating model ----------------------------------------------------------------------
GA25, GA28 = 143.8, 136.3     # G&A cost, $m
ga_pct25, ga_pct28 = round(GA25 / REV[2025] * 100, 1), round(GA28 / REV[2028] * 100, 1)
assert (ga_pct25, ga_pct28) == (11.6, 9.4)
OPM = [("Management layers, CEO to front line", "9", "7"), ("Average span of control", "4.8", "7.0"),
       ("G&A headcount", "1,180", "990"), ("Back-office locations", "14", "3"),
       ("G&A cost ($m)", f1(GA25), f1(GA28)), ("G&A cost, % of revenue", f1(ga_pct25), f1(ga_pct28))]
ga_hc_cut = 1180 - 990
assert ga_hc_cut == 190
add(f1(ga_pct25), f1(ga_pct28), f1(GA25), f1(GA28), "190", "1,180", "990", "9", "7", "4.8", "7.0", "14", "3")

# ---- KPI tiles ----------------------------------------------------------------------------
OTIF25, OTIF28 = 87.0, 96.0
add(f0(OTIF25), f0(OTIF28), f0(OTIF28 - OTIF25), f1(invoice_acc28 - invoice_acc25), f1(ga_pct25 - ga_pct28), f0(m25), f0(m28), "5")

# ---- risks: id, text, L, I, residual L, residual I, owner, mitigation -----------------------
RISKS = [
    ("R1", "Line transfer re-validation delays the Salt Lake City exit", 4, 4, 2, 3, "COO, CQRO", "Validation master plan per line; 10 weeks of bridge stock"),
    ("R2", "Supply to US hospitals interrupted during line moves", 3, 5, 2, 4, "COO", "12-week build-ahead; dual-qualified lines before cut-over"),
    ("R3", "GPO renegotiations delay price-master benefits", 3, 3, 2, 2, "CCO", "Phase by contract renewal date; leakage tracked monthly"),
    ("R4", "Order-management upgrade over-runs", 4, 3, 3, 2, "CFO", "Upgrade the current ERP in place; no big-bang replacement"),
    ("R5", "Key staff leave Tuttlingen and Salt Lake City before exit", 4, 3, 2, 2, "CPO", "$4.2m retention pool; knowledge transfer signed off per line"),
    ("R6", "Works-council consultation extends the German timeline", 3, 3, 2, 3, "CPO", "Consultation opens Q1 2027; 4 months of float in plan"),
    ("R7", "EU MDR recertification collides with transfers", 3, 4, 2, 3, "CQRO", "One regulatory calendar; notified-body slots booked for 2027"),
    ("R8", "Inflation above the $31m in the plan", 3, 3, 3, 2, "CFO", "Index clauses in 70% of supply contracts by 2027"),
    ("R9", "Change fatigue lowers sales productivity", 2, 3, 1, 2, "CCO", "Commercial roles change once, in one wave"),
]
def zone(l, i):
    s = l * i
    return "high" if s >= 15 else ("mid" if s >= 6 else "low")
inherent_high = [r[0] for r in RISKS if zone(r[2], r[3]) == "high"]
residual_high = [r[0] for r in RISKS if zone(r[4], r[5]) == "high"]
residual_low = [r[0] for r in RISKS if zone(r[4], r[5]) == "low"]
assert inherent_high == ["R1", "R2"] and residual_high == [] and residual_low == ["R3", "R5", "R9"], (inherent_high, residual_low)
add("4.2", "70", "10", "12", "4")
before_z = [zone(r[2], r[3]) for r in RISKS]
after_z = [zone(r[4], r[5]) for r in RISKS]
zc = {z: (before_z.count(z), after_z.count(z)) for z in ("high", "mid", "low")}
sum_b, sum_a = sum(r[2] * r[3] for r in RISKS), sum(r[4] * r[5] for r in RISKS)
assert zc == {"high": (2, 0), "mid": (7, 6), "low": (0, 3)} and (sum_b, sum_a) == (100, 48), (zc, sum_b, sum_a)
cut = round((sum_b - sum_a) / sum_b * 100)
assert cut == 52
add("100", "48", "52", "0", "6", "7", "9")
# footprint economics: payback of each footprint initiative, years = cost to achieve / run-rate saving
fp = {i[0]: (i[3], i[4]) for i in INIT if i[2] == "Footprint"}
payback = {k: round(c / v, 1) for k, (v, c) in fp.items()}
assert payback == {"F1": 2.5, "F2": 2.7, "F3": 1.2} and round(68 / 29, 1) == 2.3, payback
add(*[f"{v:.1f}" for v in payback.values()], "2.3")
lines_moved = 2 + 3 + 4
assert lines_moved == 9
add("9")
share26 = round(cost_y[2026] / cta * 100)
assert share26 == 44
add("44")
assert volume[2028] + inflation[2028] + run_cost[2028] == 1.0
add("1")
# KPI paths FY2025, FY2026, FY2027, FY2028 (FY2026 and FY2027 are the plan's interim targets)
PATHS = {
    "ebitda": [EBITDA25, ebitda_rr[2026], ebitda_rr[2027], ebitda_rr[2028]],
    "margin": [m25, margin_rr[2026], margin_rr[2027], margin_rr[2028]],
    "o2c": [o2c25, 64.0, 57.0, o2c28],
    "dio": [DIO25, 131, 117, DIO28],
    "otif": [OTIF25, 90.0, 93.0, OTIF28],
    "util": [util25, 67.0, 76.0, util28],
    "price": [invoice_acc25, 96.5, 98.8, invoice_acc28],
    "ga": [ga_pct25, 11.1, 10.2, ga_pct28],
}
for k, v in PATHS.items():
    up = v[-1] > v[0]
    assert all((b > a) if up else (b < a) for a, b in zip(v, v[1:])), (k, v)   # each path moves one way, year on year
add("217", "256", "17", "19", "64", "57", "131", "117", "90", "93", "67", "76", "96.5", "98.8", "11.1", "10.2")
# mitigation cost by risk, $m, inside the cost to achieve
MITIG = {"R1": 2.6, "R2": 3.8, "R3": 0.4, "R4": 1.5, "R5": 4.2, "R6": 0.6, "R7": 0.9, "R8": 0.0, "R9": 0.3}
mit_total = round(sum(MITIG.values()), 1)
assert mit_total == 14.3 and round(mit_total) == 14 and mit_total < cta
add(*[f"{v:.1f}" for v in MITIG.values()], "14.3", "14")
for r in RISKS:
    add(str(r[2] * r[3]), str(r[4] * r[5]))

# receiving plants' hires, distance Tuttlingen to Brno, revenue growth, lever cost per $ of EBITDA
hires = sum(p[11] - p[10] for p in PLANTS if p[11] > p[10])
assert hires == 550 and hc25 - hc28 == 150, hires
t, b = PLANTS[5], PLANTS[6]
import math as _m
km = 6371 * 2 * _m.asin(_m.sqrt(_m.sin(_m.radians(b[3] - t[3]) / 2) ** 2 + _m.cos(_m.radians(t[3])) * _m.cos(_m.radians(b[3])) * _m.sin(_m.radians(b[4] - t[4]) / 2) ** 2))
assert round(km, -1) == 590, km
growth = round(((REV[2028] / REV[2025]) ** (1 / 3) - 1) * 100, 1)
assert growth == 5.4, growth
per = {lv: round(cta_by_lever[lv] / levers[lv], 2) for lv in levers}
assert per == {"Procurement": 0.5, "Footprint": 2.34, "Commercial and order-to-cash": 1.17, "Operating model": 2.68}, per
assert -(inflation[2028] + run_cost[2028]) == 37
add("550", "590", "5.4", "3.5", "2.5", "130", *[f"{v:.2f}" for v in per.values()], "4", "3", "5")

# ---- gantt milestones ---------------------------------------------------------------------
MILESTONES = [("M1", 0, "Programme launch; Transformation Office live", "January 2026"),
              ("M2", 5, "Contract-price master live in the US", "May 2026"),
              ("M3", 12, "Brno hub opens; validation master plan issued", "December 2026"),
              ("M4", 21, "Salt Lake City exit complete", "September 2027"),
              ("M5", 30, "Tuttlingen exit complete", "June 2028"),
              ("M6", 36, "Full $103m run-rate; programme closes", "December 2028")]
for code, name, *_ in INIT:
    pass
ends = {i[0]: i[7] + i[8] + i[9] for i in INIT}
assert ends["F1"] == 21 and ends["F2"] == 30 and ends["C1"] == 12 and max(ends.values()) <= 36, ends
assert INIT[3][7] + INIT[3][8] == 12      # F1 delivery starts when O3's validation plan is out (dependency)
assert INIT[4][7] + INIT[4][8] == ends["F1"]  # F2 delivery starts when F1 completes
assert INIT[9][7] + INIT[9][8] == ends["C1"]  # O1 delivery starts on the live price master

data = {k: v for k, v in dict(REV=REV, EBITDA25=EBITDA25, bridge=bridge, levers=levers, INIT=INIT, DEFERRED=DEFERRED,
                              run_rate=run_rate, volume=volume, inflation=inflation, run_cost=run_cost, ebitda_rr=ebitda_rr,
                              margin_rr=margin_rr, in_year=in_year, opex=opex, capex=capex, cost_y=cost_y, wc_y=wc_y, net_y=net_y,
                              per_lever=per, cum=cum, o2c_stages=o2c_stages, PAIN=PAIN, PLANTS=PLANTS, OPM=OPM, RISKS=RISKS,
                              MILESTONES=MILESTONES, cta_by_lever=cta_by_lever, PATHS=PATHS, MITIG=MITIG,
                              util25=u25, util28=u28, cap25=cap25, cap28=cap28, hc25=hc25, hc28=hc28,
                              wc_release=wc_release, recv_release=recv_release, inv_release=inv_release).items()}
Path(__file__).with_name("data.json").write_text(json.dumps(data, indent=1, default=str))
print(" ".join(dict.fromkeys(out)))
print("# ebitda_rr", ebitda_rr, "margin", margin_rr, "cum", cum, "util", util25, util28, file=sys.stderr)
