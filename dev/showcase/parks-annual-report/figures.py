# Illustrative figures for the fictional Brannoch National Parks Service, year to 31 March 2026.
out = []
def say(*a): out.append(" ".join(str(x) for x in a))

# Page 1: visits and access (thousands of visits per month, April to March)
months = ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar"]
prev = [570, 700, 850, 1010, 1120, 920, 750, 470, 360, 310, 380, 500]
curr = [610, 750, 910, 1060, 1180, 980, 810, 510, 380, 330, 400, 500]
tp, tc = sum(prev), sum(curr)
assert tp == 7940 and tc == 8420
growth = (tc / tp - 1) * 100
assert round(growth, 1) == 6.0
peak = max(curr); assert peak == 1180 and months[curr.index(peak)] == "Aug"
low = min(curr); assert low == 330 and months[curr.index(low)] == "Jan"
assert round(peak / low, 1) == 3.6
summer = sum(curr[3:5]); assert round(summer / tc * 100) == 27   # Jul+Aug share
say("8.42 million", "7.94 million", "6.0%", "1.18 million", "330,000", "1,180", "330", "3.6", "27%")
mode_prev = {"Car": 71, "Bus, shuttle or train": 19, "On foot or by bike": 10}
mode_curr = {"Car": 64, "Bus, shuttle or train": 25, "On foot or by bike": 11}
assert sum(mode_prev.values()) == 100 and sum(mode_curr.values()) == 100
assert mode_curr["Bus, shuttle or train"] - mode_prev["Bus, shuttle or train"] == 6
nocar = 100 - mode_curr["Car"]; assert nocar == 36
say("71%", "64%", "19%", "25%", "36%", "6 points")
stepfree_prev, stepfree_curr = 188, 241
assert stepfree_curr - stepfree_prev == 53
say("188 km", "241 km", "53 km")
assert sum(c > p for c, p in zip(curr, prev)) == 11 and curr[-1] == prev[-1]
say("11 of 12")
pupils = 41300; say("41,300")

# Page 2: conservation (counted population change since the 2021 baseline, %)
species = {"Water vole": 41, "Pine marten": 34, "Red squirrel": 22, "Golden eagle (pairs)": 18,
           "Natterjack toad": 12, "Black grouse": 5, "Atlantic salmon (returning)": -6,
           "Freshwater pearl mussel": -9, "Capercaillie": -14}
up = [k for k, v in species.items() if v > 0]; down = [k for k, v in species.items() if v < 0]
assert len(species) == 9 and len(up) == 6 and len(down) == 3
assert sorted(species.values(), reverse=True) == list(species.values())
habitat = {"Peatland re-wetted": 1260, "Native woodland planted": 540, "Wetland restored": 340}
hab_total = sum(habitat.values()); assert hab_total == 2140
hab_target = 2000; assert round(hab_total / hab_target * 100) == 107
say("6 of 9", "+41%", "-14%", "2,140", "2,000", "107%", "1,260", "540", "340")
hab_share = {k: round(v / hab_total * 100) for k, v in habitat.items()}
assert list(hab_share.values()) == [59, 25, 16] and sum(hab_share.values()) == 100
say("59%", "25%", "16%", "100%")

# Page 3: budget, $m
income = {"Government grant": 96.4, "Parking, camping and permits": 28.7, "Shops, cafes and leases": 11.2,
          "Donations and legacies": 7.9, "Grants from trusts": 4.1}
income_prev = {"Government grant": 94.0, "Parking, camping and permits": 25.9, "Shops, cafes and leases": 10.6,
               "Donations and legacies": 6.8, "Grants from trusts": 3.5}
inc = round(sum(income.values()), 1); inc_prev = round(sum(income_prev.values()), 1)
assert inc == 148.3 and inc_prev == 140.8
spend = {"Conservation and habitats": 46.1, "Rangers and visitor services": 35.6,
         "Trails, roads and buildings": 31.8, "Running the service": 15.2,
         "Education and community": 12.4, "Volunteer programme": 4.0}
sp = round(sum(spend.values()), 1); assert sp == 145.1
reserve = round(inc - sp, 1); assert reserve == 3.2
# of every $100 spent, largest remainder so the shares add to 100
raw = {k: v / sp * 100 for k, v in spend.items()}
fl = {k: int(v) for k, v in raw.items()}
rem = 100 - sum(fl.values())
for k in sorted(raw, key=lambda k: raw[k] - fl[k], reverse=True)[:rem]: fl[k] += 1
per100 = fl; assert sum(per100.values()) == 100
assert per100 == {"Conservation and habitats": 32, "Rangers and visitor services": 24,
                  "Trails, roads and buildings": 22, "Running the service": 10,
                  "Education and community": 9, "Volunteer programme": 3}
gov_share = income["Government grant"] / inc * 100; assert round(gov_share) == 65
own = round(inc - income["Government grant"], 1); assert own == 51.9
assert round((inc / inc_prev - 1) * 100, 1) == 5.3
say("$148.3m", "$140.8m", "$145.1m", "$3.2m", "65%", "$51.9m", "32", "24", "22", "10", "9", "3", "5.3%")
for k in income: say(f"{income_prev[k]:.1f}", f"{income[k]:.1f}")
for k in spend: say(f"{spend[k]:.1f}")

# Page 4: volunteers
years = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
vols = [2950, 3410, 3880, 4320, 4760]
hours = [118, 139, 158, 171, 192]  # thousands
assert round((hours[-1] / hours[0] - 1) * 100) == 63
assert round((vols[-1] / vols[0] - 1) * 100) == 61
activities = {"Habitat work": 74, "Trail repair": 48, "Welcoming and guiding": 39, "Wildlife surveys": 21, "Litter clean-ups": 10}
assert sum(activities.values()) == hours[-1]
rate = 24.50
value = hours[-1] * 1000 * rate / 1e6; assert round(value, 2) == 4.70
prog = spend["Volunteer programme"]; assert round(value / prog, 2) == 1.18
fte = hours[-1] * 1000 / 1650; assert round(fte) == 116
say("4,760", "192,000", "2,950", "63%", "$4.70m", "$24.50", "$4.0m", "$1.18", "116", "74,000", "48,000", "39,000", "21,000", "10,000")
for v in vols: say(f"{v:,}")
per_vol = [round(h * 1000 / v, 1) for h, v in zip(hours, vols)]
assert per_vol == [40.0, 40.8, 40.7, 39.6, 40.3], per_vol
say("40", "61%", *[f"{x:.1f}" for x in per_vol])

# Page 5: priorities for 2026-27, $m
prio = {"Rivers": 3.4, "Getting here": 2.6, "Step-free trails": 1.9, "Repairs": 4.8, "Volunteers": 0.9}
pt = round(sum(prio.values()), 1); assert pt == 13.6
assert stepfree_curr + 40 == 281
assert mode_curr["Bus, shuttle or train"] + 5 == 30
backlog, fix = 214, 60; assert round(fix / backlog * 100) == 28
assert 4760 + 540 == 5300
say("$13.6m", "281 km", "30%", "60 of 214", "28%", "5,300", "18 km", "12 river sites", "16 to 25")
print("\n".join(out))
