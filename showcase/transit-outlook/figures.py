"""Lakeshore Regional Transit Authority (fictional): every figure of the section,
computed and asserted. All inputs are invented for illustration. Writes data.json beside
this file and prints each stated figure it asserted (the build's --computed input)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
MODES = ["Bus", "Light rail", "Commuter rail", "Demand response"]
HIST_YEARS = list(range(2015, 2026))
PROJ_YEARS = list(range(2026, 2036))
YEARS = HIST_YEARS + PROJ_YEARS

# ---- ridership, millions of annual boardings (invented) ----
hist = {
 "Bus":             [60.5, 61.2, 61.8, 62.3, 62.0, 38.5, 41.0, 47.5, 51.0, 53.6, 55.2],
 "Light rail":      [21.0, 22.1, 23.0, 23.6, 24.0, 13.0, 14.5, 17.8, 20.1, 21.9, 23.0],
 "Commuter rail":   [ 8.9,  9.1,  9.3,  9.4,  9.5,  3.8,  4.5,  6.0,  7.0,  7.8,  8.4],
 "Demand response": [ 1.2, 1.25,  1.3, 1.35,  1.4,  0.8,  0.9,  1.1,  1.2,  1.3,  1.4],
}
early = {"Bus": 0.025, "Light rail": 0.030, "Commuter rail": 0.035, "Demand response": 0.03}   # 2026-2029
late = {"Bus": 0.010, "Light rail": 0.012, "Commuter rail": 0.015, "Demand response": 0.03}    # 2030-2035
new_service = {  # boardings added by new lines, millions
 "Bus": {2028: 1.5, 2029: 2.5, 2030: 2.5, 2031: 3.5, 2032: 4.5, 2033: 4.5, 2034: 4.5, 2035: 4.5},   # Lakefront BRT 2028, Crosstown BRT 2031
 "Light rail": {2030: 3.0, 2031: 5.5, 2032: 5.5, 2033: 5.5, 2034: 5.5, 2035: 5.5},                # Blue Line extension 2030
}
base = {}
for m in MODES:
    core, v = [], hist[m][-1]
    for y in PROJ_YEARS:
        v = v * (1 + (early[m] if y <= 2029 else late[m]))
        core.append(v)
    base[m] = [round(c + new_service.get(m, {}).get(y, 0.0), 1) for c, y in zip(core, PROJ_YEARS)]
series = {m: hist[m] + base[m] for m in MODES}
total = [round(sum(series[m][i] for m in MODES), 1) for i in range(len(YEARS))]
T = dict(zip(YEARS, total))

def factor(y, end):  # scenario multiplier, linear from 1.0 in 2025 to `end` in 2035
    return 1 + (end - 1) * (y - 2025) / 10
low = {y: round(T[y] * factor(y, 0.88), 1) for y in PROJ_YEARS}
high = {y: round(T[y] * factor(y, 1.10), 1) for y in PROJ_YEARS}
mode_2035 = {"Low": {m: round(series[m][-1] * 0.88, 1) for m in MODES},
             "Baseline": {m: series[m][-1] for m in MODES},
             "High": {m: round(series[m][-1] * 1.10, 1) for m in MODES}}

# ---- fares and operating cost (invented) ----
fare = {2019: {"Bus": 1.20, "Light rail": 1.45, "Commuter rail": 4.10, "Demand response": 2.40},
        2025: {"Bus": 1.02, "Light rail": 1.24, "Commuter rail": 3.80, "Demand response": 2.10}}
fare_steps = {2027: 1.05, 2031: 1.05, 2034: 1.05}
f = dict(fare[2025]); fares_by_year = {2025: dict(f)}
for y in PROJ_YEARS:
    if y in fare_steps:
        f = {m: v * fare_steps[y] for m, v in f.items()}
    fares_by_year[y] = dict(f)
fares_by_year[2019] = fare[2019]
cost = {2019: {"Bus": 480, "Light rail": 190, "Commuter rail": 150, "Demand response": 80},
        2025: {"Bus": 560, "Light rail": 228, "Commuter rail": 176, "Demand response": 98}}
new_cost = {"Bus": {2028: 18, 2031: 38}, "Light rail": {2030: 42}}  # $m a year from that year on
c = dict(cost[2025]); cost_by_year = {2019: cost[2019], 2025: dict(c)}
for y in PROJ_YEARS:
    c = {m: v * 1.03 for m, v in c.items()}
    cost_by_year[y] = {m: c[m] + max([v for yy, v in new_cost.get(m, {}).items() if yy <= y], default=0) for m in MODES}
def board(y, m):
    return series[m][YEARS.index(y)]
fare_rev = {y: round(sum(board(y, m) * fares_by_year[y][m] for m in MODES), 1) for y in [2019, 2025] + PROJ_YEARS}
op_cost = {y: round(sum(cost_by_year[y].values()), 1) for y in [2019, 2025] + PROJ_YEARS}
# history between the modelled years (invented, $m); 2019 and 2025 come from the mode build-up above
fare_hist = {2015: 141.0, 2016: 144.2, 2017: 147.5, 2018: 149.8, 2020: 82.0, 2021: 88.5, 2022: 101.3, 2023: 108.6, 2024: 114.9}
cost_hist = {2015: 812.0, 2016: 835.0, 2017: 857.0, 2018: 878.0, 2020: 918.0, 2021: 941.0, 2022: 982.0, 2023: 1015.0, 2024: 1040.0}
fare_rev.update(fare_hist); op_cost.update(cost_hist)
fare_rev = dict(sorted(fare_rev.items())); op_cost = dict(sorted(op_cost.items()))
assert list(fare_rev) == YEARS and list(op_cost) == YEARS
recovery = {y: round(100 * fare_rev[y] / op_cost[y], 1) for y in fare_rev}
cpb = {y: round(op_cost[y] / T[y], 2) for y in op_cost}
cpb_mode = {y: {m: round(cost_by_year[y][m] / board(y, m), 2) for m in MODES} for y in (2019, 2025, 2035)}
cpb_low = {y: round(op_cost[y] / low[y], 2) for y in PROJ_YEARS}
cpb_high = {y: round(op_cost[y] / high[y], 2) for y in PROJ_YEARS}
# ridership cases scale every mode alike at unchanged fares, so revenue scales with boardings
rev_low = {y: round(fare_rev[y] * low[y] / T[y], 1) for y in PROJ_YEARS}
rev_high = {y: round(fare_rev[y] * high[y] / T[y], 1) for y in PROJ_YEARS}
rec_low = {y: round(100 * rev_low[y] / op_cost[y], 1) for y in PROJ_YEARS}
rec_high = {y: round(100 * rev_high[y] / op_cost[y], 1) for y in PROJ_YEARS}
CASE_END = {"Low": 0.88, "Baseline": 1.0, "High": 1.10}
cpb_mode_case = {c: {m: round(cost_by_year[2035][m] / (board(2035, m) * f), 2) for m in MODES} for c, f in CASE_END.items()}
def pct(a, b):
    return 100 * (a / b - 1)
cpb_change = {m: {"2025": pct(cpb_mode[2025][m], cpb_mode[2019][m]), "2035": pct(cpb_mode[2035][m], cpb_mode[2019][m]),
                  "2035_low": pct(cpb_mode_case["Low"][m], cpb_mode[2019][m]), "2035_high": pct(cpb_mode_case["High"][m], cpb_mode[2019][m])} for m in MODES}
cpb_change["All modes"] = {"2025": pct(cpb[2025], cpb[2019]), "2035": pct(cpb[2035], cpb[2019]),
                           "2035_low": pct(cpb_low[2035], cpb[2019]), "2035_high": pct(cpb_high[2035], cpb[2019])}
assert all(cpb_mode_case["Baseline"][m] == cpb_mode[2035][m] for m in MODES)

# ---- capital plan, $m (invented) ----
PROGRAMS = ["State of good repair", "Expansion", "Fleet and electrification", "Stations and accessibility", "Safety, systems and technology"]
capital = {
 "State of good repair":            [210, 220, 230, 235, 240, 245, 250, 255, 260, 265],
 "Expansion":                       [120, 260, 330, 360, 260, 120, 140, 120,  60,  30],
 "Fleet and electrification":       [ 60,  70,  80,  90,  95, 100, 100,  95,  90,  80],
 "Stations and accessibility":      [ 35,  40,  45,  45,  45,  45,  40,  40,  35,  30],
 "Safety, systems and technology":  [ 55,  60,  45,  35,  30,  30,  30,  30,  30,  30],
}
prog_total = {p: sum(v) for p, v in capital.items()}
year_total = [sum(capital[p][i] for p in PROGRAMS) for i in range(10)]
plan_total = sum(prog_total.values())
assert plan_total == sum(year_total)
share = {p: round(100 * v / plan_total, 1) for p, v in prog_total.items()}

# ---- funding, $m over ten years (invented) ----
SOURCES = ["Federal formula", "Federal grants", "State grants", "Sales tax", "Bonds"]
funding = {"Federal formula": 1150, "Federal grants": 900, "State grants": 760, "Sales tax": 1520, "Bonds": 600}
funded = sum(funding.values())
gap = plan_total - funded
scen = []
def sc(name, need, fund, what):
    scen.append({"name": name, "need": need, "funded": fund, "gap": need - fund, "gap_share": round(100 * (need - fund) / need, 1), "what": what})
esc = round(plan_total * 1.08)
RENEWAL = 450
sc("Baseline", plan_total, funded, "as programmed")
sc("Sales tax renewed", plan_total, funded + RENEWAL, f"+${RENEWAL}m from 2030")
sc("Costs 8% higher", esc, funded, "need +8%")
sc("No federal grant", plan_total, funded - funding["Federal grants"], f"-${funding['Federal grants']:,}m Blue Line")
sc("Both downsides", esc, funded - funding["Federal grants"], "both of the above")

# ---- major projects (invented): start year, last year of work, cost $m, program ----
projects = [
 ("Fare system replacement",            2026, 2027,   85, "Safety, systems and technology"),
 ("Lakefront BRT (Route 1)",            2026, 2028,  210, "Expansion"),
 ("Commuter rail signal upgrade",       2026, 2029,  190, "Safety, systems and technology"),
 ("Blue Line extension to Northgate",   2026, 2030, 1350, "Expansion"),
 ("Eastside garage electrification",    2027, 2030,  180, "Fleet and electrification"),
 ("Light rail vehicle overhaul",        2027, 2032,  260, "State of good repair"),
 ("Crosstown BRT (Route 2)",            2029, 2031,  240, "Expansion"),
 ("Union Station rehabilitation",       2031, 2035,  320, "State of good repair"),
 ("Station accessibility program",      2026, 2035,  400, "Stations and accessibility"),
 ("Battery-electric bus replacement",   2026, 2035,  680, "Fleet and electrification"),
]
assert sum(p[3] for p in projects if p[4] == "Expansion") == prog_total["Expansion"]
assert sum(p[3] for p in projects if p[4] == "Fleet and electrification") == prog_total["Fleet and electrification"]
assert sum(p[3] for p in projects if p[4] == "Stations and accessibility") == prog_total["Stations and accessibility"]
done_by_2030 = [p for p in projects if p[2] <= 2030]

# ================= the figures the pages state =================
stated = []
def say(s):
    stated.append(s)

# P1
recover_year = next(y for y in PROJ_YEARS if T[y] >= T[2019])
assert recover_year == 2029, (recover_year, T[2028], T[2029], T[2019])
assert T[2028] < T[2019] <= T[2029]
rail_growth = (series["Light rail"][-1] + series["Commuter rail"][-1]) / (hist["Light rail"][-1] + hist["Commuter rail"][-1]) - 1
bus_growth = series["Bus"][-1] / hist["Bus"][-1] - 1
assert rail_growth > bus_growth
say(f"{T[2019]:.1f}"); say(f"{T[2025]:.1f}"); say(f"{T[2035]:.1f}"); say(str(recover_year))
say(f"{low[2035]:.1f}"); say(f"{high[2035]:.1f}")
say(f"{round(100*rail_growth)}%"); say(f"{round(100*bus_growth)}%")

mode_growth = {m: series[m][-1] / hist[m][-1] - 1 for m in MODES}
fastest = max(mode_growth, key=mode_growth.get)
assert fastest == "Light rail"
say(f"{round(100*mode_growth['Light rail'])}%")
cross = {"Baseline": recover_year, "High": next(y for y in PROJ_YEARS if high[y] >= T[2019]), "Low": next(y for y in PROJ_YEARS if low[y] >= T[2019])}
say(str(cross["High"])); say(str(cross["Low"]))

# P2
assert recovery[2035] < recovery[2019]
assert max(rec_high.values()) < recovery[2019]
say(f"{rec_low[2035]:.1f}%"); say(f"{rec_high[2035]:.1f}%"); say(f"${fare_rev[2019]:.1f}")
say(f"${fare_rev[2025]:.1f}"); say(f"${fare_rev[2035]:.1f}"); say(f"{recovery[2019]:.1f}%"); say(f"{recovery[2025]:.1f}%"); say(f"{recovery[2035]:.1f}%")
fare_growth = fare_rev[2035] / fare_rev[2025] - 1
ride_growth = T[2035] / T[2025] - 1
say(f"{round(100*fare_growth)}%"); say(f"{round(100*ride_growth)}%")

# P3
sgr_share = share["State of good repair"]
say(f"{round(sgr_share)}%"); say(f"${plan_total/1000:.1f} billion"); say(f"{plan_total:,}")
peak_year = PROJ_YEARS[year_total.index(max(year_total))]
say(str(peak_year)); say(f"{max(year_total):,}")
exp_peak = PROJ_YEARS[capital["Expansion"].index(max(capital["Expansion"]))]
say(str(exp_peak))
exp_build = sum(capital["Expansion"][PROJ_YEARS.index(y)] for y in range(2027, 2031))
say(f"{exp_build:,}"); say(f"{prog_total['Expansion']:,}")
exp_build_share = exp_build / prog_total["Expansion"]
assert round(3 * exp_build_share) == 2  # "two-thirds"

# P4
assert plan_total - sum(funding.values()) == gap
say(f"{gap:,}"); say(f"{funded:,}"); say(f"{round(100*funded/plan_total)}%")
gaps = [s["gap"] for s in scen]
say(f"${min(gaps):,}"); say(f"${max(gaps):,}")
say(f"${gap/1000:.1f} billion"); say(f"${min(gaps)/1000:.1f}"); say(f"${max(gaps)/1000:.1f} billion")
for s in scen:
    say(f"{s['need']:,}"); say(f"{s['funded']:,}"); say(f"{s['gap']:,}"); say(f"{s['gap_share']:.1f}%")

# P5
say(f"${cpb[2019]:.2f}"); say(f"${cpb[2025]:.2f}"); say(f"${cpb[2035]:.2f}")
say(f"${cpb_low[2035]:.2f}"); say(f"${cpb_high[2035]:.2f}")
peak_cpb_year = max(cpb, key=cpb.get)

assert all(v > cpb[2019] for v in list(cpb_low.values()) + list(cpb_high.values()) + [cpb[y] for y in PROJ_YEARS])
cost_growth = op_cost[2035] / op_cost[2025] - 1
assert ride_growth < cost_growth < fare_growth
say(f"{round(100*cost_growth)}%")
for m, d in cpb_change.items():
    say(f"+{round(d['2035'])}%")
assert max(cpb_change, key=lambda m: cpb_change[m]["2035"]) == "Bus"
assert min(v["2035_high"] for v in cpb_change.values()) > 0  # every mode above 2019 even in the high ridership case
# P4 scenario reading
renew = next(s for s in scen if s["name"] == "Sales tax renewed")["gap"]
nogrant = next(s for s in scen if s["name"] == "No federal grant")["gap"]
assert abs(renew / gap - 0.5) < 0.02 and abs(nogrant / gap - 2) < 0.03
esc_add = next(s for s in scen if s["name"] == "Costs 8% higher")["gap"] - gap
say(f"${renew:,}"); say(f"${nogrant:,}"); say(f"${esc_add:,}")

# P6
assert len(done_by_2030) == 5
assert sum(1 for p in projects if (p[1], p[2]) == (2026, 2035)) == 2
say("5"); say("$1.35 billion")

data = dict(MODES=MODES, YEARS=YEARS, HIST_YEARS=HIST_YEARS, PROJ_YEARS=PROJ_YEARS, series=series, total=total,
            low=low, high=high, mode_2035=mode_2035, fares_by_year={str(k): v for k, v in fares_by_year.items()},
            fare_rev=fare_rev, op_cost=op_cost, recovery=recovery, cpb=cpb, cpb_mode=cpb_mode, cpb_low=cpb_low, cpb_high=cpb_high,
            PROGRAMS=PROGRAMS, capital=capital, prog_total=prog_total, year_total=year_total, plan_total=plan_total, share=share,
            SOURCES=SOURCES, funding=funding, funded=funded, gap=gap, scen=scen, projects=projects,
            recover_year=recover_year, rail_growth=rail_growth, bus_growth=bus_growth, fare_growth=fare_growth, ride_growth=ride_growth,
            peak_year=peak_year, exp_peak=exp_peak, cost_growth=cost_growth,
            rev_low=rev_low, rev_high=rev_high, rec_low=rec_low, rec_high=rec_high, cpb_change=cpb_change, cpb_mode_case=cpb_mode_case,
            mode_growth=mode_growth, cross=cross, exp_build=exp_build, RENEWAL=RENEWAL)
json.dump(data, open(os.path.join(HERE, "data.json"), "w"), indent=1)
for s in stated:
    print(s)
