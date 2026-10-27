"""Every figure in the Ridgeline section, invented for a fictional program and checked here.

Run: python3 figures.py > figures.txt   (also writes data.json beside this file)
All figures are illustrative; none describes a real agency, place or program.
"""
import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))
printed: list[str] = []


def say(*xs: str) -> None:
    printed.extend(xs)


def k1(x: float) -> str:
    return f"{x:.1f}"


# ---- Page 1: acres treated by method, FY2022-FY2026 (thousand acres) ----
YEARS = ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
METHODS_HIST = {
    "Prescribed fire": [9.4, 12.6, 16.1, 19.8, 23.5],
    "Mechanical thinning": [14.1, 15.8, 17.2, 18.0, 18.9],
    "Mastication": [8.2, 8.9, 9.6, 10.1, 10.4],
    "Hand thinning": [4.0, 4.6, 5.3, 5.8, 6.2],
}
TOTAL_HIST = [35.7, 41.9, 48.2, 53.7, 59.0]
for i in range(5):
    assert round(sum(v[i] for v in METHODS_HIST.values()), 1) == TOTAL_HIST[i]
pct_change = {m: (v[-1] / v[0] - 1) * 100 for m, v in METHODS_HIST.items()}
pct_change["All methods"] = (TOTAL_HIST[-1] / TOTAL_HIST[0] - 1) * 100
assert round(pct_change["All methods"]) == 65
assert round(pct_change["Prescribed fire"]) == 150
assert round(METHODS_HIST["Prescribed fire"][-1] / METHODS_HIST["Prescribed fire"][0], 1) == 2.5
# prescribed fire first exceeds mechanical thinning in FY2025
first_over = next(YEARS[i] for i in range(5) if METHODS_HIST["Prescribed fire"][i] > METHODS_HIST["Mechanical thinning"][i])
assert first_over == "FY2025"
pf_share_26 = METHODS_HIST["Prescribed fire"][-1] / TOTAL_HIST[-1] * 100
assert round(pf_share_26) == 40
say("59.0", "35.7", "65%", "+65%", "150%", "+150%", "2.5", "40%", "23.5", "18.9", "9.4", "14.1")
for m, v in pct_change.items():
    say(f"+{v:.0f}%")
for v in METHODS_HIST.values():
    say(*[k1(x) for x in v])
say(*[k1(x) for x in TOTAL_HIST])

# ---- Page 2: hazard by county (share of county land, percent) and plan ----
COUNTIES = [  # name, very high %, high %, homes in the wildland-urban interface (thousand), planned acres FY2027-29 (thousand)
    ("Elk Ridge", 31, 27, 18.4, 32.0),
    ("Cedar Fork", 26, 28, 22.1, 29.5),
    ("Granite", 22, 25, 9.8, 21.0),
    ("Juniper", 19, 24, 6.2, 16.5),
    ("Hollow Creek", 15, 23, 14.7, 17.5),
    ("Falcon", 12, 21, 11.3, 13.0),
    ("Dunmore", 9, 19, 25.6, 12.5),
    ("Alder", 7, 16, 8.9, 8.0),
    ("Basin", 4, 12, 30.2, 6.0),
    ("Ironwood", 3, 9, 4.1, 4.0),
]
combined = [vh + h for _, vh, h, _, _ in COUNTIES]
assert combined == sorted(combined, reverse=True), "bars are listed in rank order"
PLAN_ACRES = round(sum(c[4] for c in COUNTIES), 1)
assert PLAN_ACRES == 160.0
top2 = COUNTIES[0][4] + COUNTIES[1][4]
assert round(top2 / PLAN_ACRES * 100) == 38
top4 = sum(c[4] for c in COUNTIES[:4])
assert round(top4 / PLAN_ACRES * 100) == 62
homes_total = round(sum(c[3] for c in COUNTIES), 1)
assert homes_total == 151.3
say("160.0", "160,000", "38%", "62%", "151.3", "58%", "54%")
for c in COUNTIES:
    say(str(c[1]), str(c[2]), f"{c[1] + c[2]}%", k1(c[3]), k1(c[4]), f"{c[4] / PLAN_ACRES * 100:.0f}%")

# ---- Page 3: cost per acre by method, FY2026 dollars ----
COST = {  # labor, equipment, materials and fuel, planning and monitoring
    "Prescribed fire": (95, 40, 25, 60),
    "Mastication": (180, 390, 70, 60),
    "Hand thinning": (820, 90, 60, 80),
    "Mechanical thinning": (610, 760, 150, 90),
}
COST_TOTAL = {m: sum(v) for m, v in COST.items()}
assert COST_TOTAL == {"Prescribed fire": 220, "Mastication": 700, "Hand thinning": 1050, "Mechanical thinning": 1610}
PLAN_BY_METHOD = {"Prescribed fire": 64.0, "Mechanical thinning": 44.0, "Mastication": 28.0, "Hand thinning": 24.0}
assert sum(PLAN_BY_METHOD.values()) == PLAN_ACRES
COST_M = {m: PLAN_BY_METHOD[m] * 1000 * COST_TOTAL[m] / 1e6 for m in PLAN_BY_METHOD}
assert {m: round(v, 2) for m, v in COST_M.items()} == {"Prescribed fire": 14.08, "Mechanical thinning": 70.84, "Mastication": 19.6, "Hand thinning": 25.2}
TOTAL_COST_M = round(sum(COST_M.values()), 2)
assert TOTAL_COST_M == 129.72
avg_cost = TOTAL_COST_M * 1e6 / (PLAN_ACRES * 1000)
assert round(avg_cost) == 811
pf_acre_share = PLAN_BY_METHOD["Prescribed fire"] / PLAN_ACRES * 100
pf_cost_share = COST_M["Prescribed fire"] / TOTAL_COST_M * 100
mt_acre_share = PLAN_BY_METHOD["Mechanical thinning"] / PLAN_ACRES * 100
mt_cost_share = COST_M["Mechanical thinning"] / TOTAL_COST_M * 100
assert (round(pf_acre_share), round(pf_cost_share), round(mt_acre_share), round(mt_cost_share)) == (40, 11, 28, 55)
ratio = COST_TOTAL["Mechanical thinning"] / COST_TOTAL["Prescribed fire"]
assert round(ratio, 1) == 7.3
say("$220", "$700", "$1,050", "$1,610", "$811", "129.7", "$129.7M", "40%", "11%", "28%", "55%", "7.3")
for m in COST:
    say(*[str(x) for x in COST[m]], f"{PLAN_BY_METHOD[m]:.1f}", f"{COST_M[m]:.1f}", f"{PLAN_BY_METHOD[m] / PLAN_ACRES * 100:.0f}%", f"{COST_M[m] / TOTAL_COST_M * 100:.0f}%")

# ---- Page 4: crews and equipment ----
RESOURCES = [  # resource, in service FY2026, needed at the FY2028 peak
    ("Hand crews (20 people)", 14, 22),
    ("Engine crews", 26, 30),
    ("Qualified burn bosses", 9, 16),
    ("Masticators", 11, 15),
    ("Feller-bunchers", 6, 9),
    ("Skidders", 8, 11),
]
gaps = {r: n - h for r, h, n in RESOURCES}
assert gaps["Qualified burn bosses"] == 7 and gaps["Hand crews (20 people)"] == 8
burn_boss_growth = (16 / 9 - 1) * 100
assert round(burn_boss_growth) == 78
CREW_DAYS = {  # fiscal year: (needed, available) crew-days
    "FY2027": (6800, 5900),
    "FY2028": (8900, 7400),
    "FY2029": (8300, 8500),
}
short = {y: n - a for y, (n, a) in CREW_DAYS.items()}
assert short == {"FY2027": 900, "FY2028": 1500, "FY2029": -200}
assert max(short, key=short.get) == "FY2028"
LEAD_TIME = {"Hand crews (20 people)": 4, "Engine crews": 3, "Qualified burn bosses": 18, "Masticators": 9, "Feller-bunchers": 6, "Skidders": 5}
assert max(LEAD_TIME, key=LEAD_TIME.get) == "Qualified burn bosses" and LEAD_TIME["Qualified burn bosses"] == 18
assert sorted(LEAD_TIME.values())[-2] * 2 == 18  # twice the next longest
say(*[str(v) for v in LEAD_TIME.values()])
say("8", "7", "78%", "+78%", "1,500", "6,800", "5,900", "8,900", "7,400", "8,300", "8,500", "900", "200")
for r, h, n in RESOURCES:
    say(str(h), str(n), f"+{n - h}", f"+{(n / h - 1) * 100:.0f}%")

# ---- Page 5: three-year schedule, FY2027-FY2029, in quarters (Q1 = Jul-Sep) ----
SCHEDULE = [  # task, start quarter index (0 = FY2027 Q1), duration in quarters
    ("Permits and environmental review", 0, 3),
    ("Crew hiring and burn-boss training", 1, 4),
    ("Hand thinning near homes: Dunmore, Basin", 1, 7),
    ("Mechanical thinning: Elk Ridge, Cedar Fork", 2, 9),
    ("Mastication: Granite, Juniper", 3, 6),
    ("Prescribed fire: all high-hazard counties", 4, 8),
    ("Other counties: Alder, Falcon, Hollow Creek, Ironwood", 6, 6),
    ("Effectiveness monitoring", 8, 4),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
def month(idx):  # idx months after July 2026
    m = 6 + idx
    return f"{MONTHS[m % 12]} {2026 + m // 12}"
SCHEDULE_SPANS = []
for _, s, d in SCHEDULE:
    assert 0 <= s and s + d <= 12
    q0, q1 = s, s + d - 1
    a, b = f"FY{27 + q0 // 4}\u00a0Q{q0 % 4 + 1}", f"FY{27 + q1 // 4}\u00a0Q{q1 % 4 + 1}"
    SCHEDULE_SPANS.append(f"{a}-Q{q1 % 4 + 1}" if q0 // 4 == q1 // 4 else f"{a}-{b}")
assert [x.replace("\u00a0", " ") for x in (SCHEDULE_SPANS[0], SCHEDULE_SPANS[3], SCHEDULE_SPANS[-1])] == ["FY27 Q1-Q3", "FY27 Q3-FY29 Q3", "FY29 Q1-Q4"]  # no-break spaces keep each label on one line
say(*SCHEDULE_SPANS)
PLAN_YEARLY = {  # thousand acres FY2027, FY2028, FY2029
    "Prescribed fire": (16.0, 22.0, 26.0),
    "Mechanical thinning": (12.0, 17.0, 15.0),
    "Mastication": (8.0, 11.0, 9.0),
    "Hand thinning": (6.0, 9.0, 9.0),
}
for m, v in PLAN_YEARLY.items():
    assert round(sum(v), 1) == PLAN_BY_METHOD[m]
YEAR_TOTALS = tuple(round(sum(v[i] for v in PLAN_YEARLY.values()), 1) for i in range(3))
assert YEAR_TOTALS == (42.0, 59.0, 59.0) and sum(YEAR_TOTALS) == PLAN_ACRES
fy28_vs_fy26 = (YEAR_TOTALS[1] / TOTAL_HIST[-1] - 1) * 100
assert round(fy28_vs_fy26) == 0  # FY2027 dips while permits clear; FY2028 and FY2029 return to the FY2026 pace
say("42.0", "59.0", "59.0", "12")
for m, v in PLAN_YEARLY.items():
    say(*[k1(x) for x in v], k1(sum(v)))

# ---- Page 6: expected hazard reduction ----
HZ_YEARS = ["FY2026", "FY2027", "FY2028", "FY2029", "FY2030"]
WITH_PLAN = [1240, 1214, 1168, 1116, 1098]  # thousand acres in high or very high hazard
WITHOUT = [1240, 1262, 1285, 1306, 1327]
assert WITH_PLAN[0] == WITHOUT[0]
avoided = WITHOUT[-1] - WITH_PLAN[-1]
assert avoided == 229
assert round(avoided / WITHOUT[-1] * 100, 1) == 17.3
below_today = WITH_PLAN[0] - WITH_PLAN[-1]
assert below_today == 142 and round(below_today / WITH_PLAN[0] * 100, 1) == 11.5
REDUCTION_PP = {"Elk Ridge": 21, "Cedar Fork": 19, "Granite": 14, "Juniper": 13, "Hollow Creek": 11,
                "Falcon": 9, "Dunmore": 8, "Alder": 6, "Basin": 5, "Ironwood": 3}
share_2030 = {c[0]: c[1] + c[2] - REDUCTION_PP[c[0]] for c in COUNTIES}
assert share_2030["Elk Ridge"] == 37 and share_2030["Cedar Fork"] == 35
assert max(share_2030.values()) == 37
growth = (WITHOUT[-1] / WITHOUT[0]) ** (1 / 4) - 1
assert round(growth * 100, 1) == 1.7
say("1.7", "1.7%", "65", "9")
say("1,240", "1,098", "1,327", "229", "229,000", "17.3%", "142", "11.5%", "21", "37%", "35%")
for y, a, b in zip(HZ_YEARS, WITH_PLAN, WITHOUT):
    say(f"{a:,}", f"{b:,}")
for c in COUNTIES:
    say(f"{c[1] + c[2]}", f"{share_2030[c[0]]}", f"-{REDUCTION_PP[c[0]]}")

# ---- Page 2 (added): where the homes are against where the acres go ----
HOME_SHARE = {c[0]: c[3] / homes_total * 100 for c in COUNTIES}
ACRE_SHARE = {c[0]: c[4] / PLAN_ACRES * 100 for c in COUNTIES}
GROUPS = {"Elk Ridge and Cedar Fork": ["Elk Ridge", "Cedar Fork"], "Basin and Dunmore": ["Basin", "Dunmore"]}
GROUPS["Other six counties"] = [c[0] for c in COUNTIES if c[0] not in GROUPS["Elk Ridge and Cedar Fork"] + GROUPS["Basin and Dunmore"]]
assert len(GROUPS["Other six counties"]) == 6
GROUP_SHARES = {g: (sum(c[3] for c in COUNTIES if c[0] in ns) / homes_total * 100, sum(c[4] for c in COUNTIES if c[0] in ns) / PLAN_ACRES * 100) for g, ns in GROUPS.items()}
assert abs(sum(v[0] for v in GROUP_SHARES.values()) - 100) < 1e-9 and abs(sum(v[1] for v in GROUP_SHARES.values()) - 100) < 1e-9
assert {g: (round(a), round(b)) for g, (a, b) in GROUP_SHARES.items()} == {"Elk Ridge and Cedar Fork": (27, 38), "Basin and Dunmore": (37, 12), "Other six counties": (36, 50)}
assert sorted(HOME_SHARE, key=HOME_SHARE.get)[-2:] == ["Dunmore", "Basin"]  # the two counties with the most WUI homes
assert (round(HOME_SHARE["Basin"]), round(ACRE_SHARE["Basin"]), round(HOME_SHARE["Dunmore"]), round(ACRE_SHARE["Dunmore"])) == (20, 4, 17, 8)
say("37%", "12%", "27%", "38%", "36%", "50%", "30.2", "25.6", "20%", "17%", "4%", "8%")
for c in COUNTIES:
    say(f"{HOME_SHARE[c[0]]:.0f}%")
for g, (a, b) in GROUP_SHARES.items():
    say(f"{a:.0f}", f"{b:.0f}")

# ---- Page 4 (added): lead times sorted, shortfall per year ----
LEAD_SORTED = sorted(LEAD_TIME.items(), key=lambda kv: -kv[1])
assert [k for k, _ in LEAD_SORTED][:2] == ["Qualified burn bosses", "Masticators"]
say("900 short", "1,500 short", "200 spare", "+200")

# ---- Page 6 (added): cuts by county ----
assert min(REDUCTION_PP.values()) == 3 and max(REDUCTION_PP.values()) == 21
say("3", "21")
AVOIDED = [b - a for a, b in zip(WITH_PLAN, WITHOUT)]
assert AVOIDED == [0, 48, 117, 190, 229]
say(*[f"{v:,}" for v in AVOIDED])
assert round(COST_TOTAL["Hand thinning"] / COST_TOTAL["Prescribed fire"], 1) == 4.8
say("4.8")

data = dict(YEARS=YEARS, METHODS_HIST=METHODS_HIST, TOTAL_HIST=TOTAL_HIST, pct_change=pct_change,
            COUNTIES=COUNTIES, COST=COST, COST_TOTAL=COST_TOTAL, PLAN_BY_METHOD=PLAN_BY_METHOD, COST_M=COST_M,
            TOTAL_COST_M=TOTAL_COST_M, avg_cost=avg_cost, RESOURCES=RESOURCES, CREW_DAYS=CREW_DAYS,
            SCHEDULE=SCHEDULE, SCHEDULE_SPANS=SCHEDULE_SPANS, LEAD_TIME=LEAD_TIME, PLAN_YEARLY=PLAN_YEARLY, YEAR_TOTALS=YEAR_TOTALS, HZ_YEARS=HZ_YEARS,
            WITH_PLAN=WITH_PLAN, WITHOUT=WITHOUT, REDUCTION_PP=REDUCTION_PP, share_2030=share_2030,
            HOME_SHARE=HOME_SHARE, ACRE_SHARE=ACRE_SHARE, GROUP_SHARES=GROUP_SHARES, LEAD_SORTED=LEAD_SORTED, AVOIDED=AVOIDED, homes_total=homes_total)
json.dump(data, open(os.path.join(OUT, "data.json"), "w"), indent=1)
print("\n".join(dict.fromkeys(printed)))
