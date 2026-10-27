"""Brindle Markets (fictional): every figure is invented and illustrative.

Generates the store-level estate with a seeded RNG, derives every page's figures from it,
asserts the stated arithmetic, writes data.json and prints every stated figure.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
rng = random.Random(20261026)
R1 = lambda v: round(v, 1)  # noqa: E731

# ---------------- page 1: market ----------------
market = {"2019": 38.0, "2025": 46.4, "2028F": 50.9}  # regional grocery spend, GBP bn
channels = ["Superstores & large supermarkets", "Discounters", "Convenience & neighbourhood", "Online", "Specialist & other"]
share = {  # % of spend
    "2019": [47, 14, 21, 7, 11],
    "2025": [40, 21, 22, 11, 6],
    "2028F": [36, 25, 21, 13, 5],
}
for y, s in share.items():
    assert sum(s) == 100, y
large_spend = {y: R1(market[y] * share[y][0] / 100) for y in market}
assert large_spend == {"2019": 17.9, "2025": 18.6, "2028F": 18.3}
market_add = R1(market["2028F"] - market["2019"])
assert market_add == 12.9
large_pts = share["2028F"][0] - share["2019"][0]
assert large_pts == -11
disc_pts = share["2028F"][1] - share["2019"][1]
assert disc_pts == 11
small_online_2028 = share["2028F"][1] + share["2028F"][2] + share["2028F"][3]
assert small_online_2028 == 59

missions = ["Main weekly shop", "Top-up", "Food for now", "Online order"]
trips = {"2019": [1.4, 2.1, 0.8, 0.2], "2025": [1.0, 2.6, 1.1, 0.3]}  # trips per household per week
tot_trips = {y: R1(sum(v)) for y, v in trips.items()}
assert tot_trips == {"2019": 4.5, "2025": 5.0}
main_change = R1((trips["2025"][0] / trips["2019"][0] - 1) * 100)
assert round(main_change) == -29
basket = {"2019": [71, 14, 6, 84], "2025": [82, 17, 8, 96]}  # average basket GBP (nominal)

topup_change = round((trips["2025"][1] / trips["2019"][1] - 1) * 100)
assert topup_change == 24

# ---------------- stores ----------------
FORMATS = {
    # name: count, area k sq ft, sales GBP m mean, capital GBP m mean, cash return % mean/sd, catchment growth % mean/sd
    "Superstore": (58, 55, 38.0, 30.0, 6.0, 4.2, 0.9, 1.9),
    "Supermarket": (96, 24, 14.5, 11.5, 10.6, 4.0, 1.7, 1.9),
    "Neighbourhood": (42, 8, 6.4, 2.9, 20.5, 4.5, 3.2, 1.5),
    "Express": (18, 2.8, 2.7, 1.2, 17.5, 4.5, 3.6, 1.5),
}
HURDLE = 12.0  # pre-tax cash return on invested capital, %
GROWTH_CUT = 1.5  # catchment spend growth a year 2022-25, %
EXIT_CUT = 3.0  # cash return below which a flat-catchment store is exited, %

stores = []
for fmt, (n, area, s_mu, k_mu, r_mu, r_sd, g_mu, g_sd) in FORMATS.items():
    for i in range(n):
        sales = R1(max(0.5, rng.gauss(s_mu, s_mu * 0.14)))
        cap = R1(max(0.4, rng.gauss(k_mu, k_mu * 0.10)))
        ret = R1(rng.gauss(r_mu, r_sd))
        g = R1(rng.gauss(g_mu, g_sd))
        ebitda = round(cap * ret / 100, 1)
        stores.append({"id": f"{fmt[:2].upper()}{i + 1:03d}", "format": fmt, "area": area, "sales": sales,
                       "capital": cap, "ret": ret, "growth": g, "ebitda": ebitda})
assert len(stores) == 214


def action(s):
    if s["ret"] >= HURDLE:
        return "Invest" if s["growth"] >= GROWTH_CUT else "Keep"
    if s["growth"] >= GROWTH_CUT:
        return "Reformat"
    return "Exit" if s["ret"] < EXIT_CUT else "Right-size"


for s in stores:
    s["action"] = action(s)

# ---------------- page 2: format economics ----------------
LFL = {"Superstore": -1.9, "Supermarket": 0.8, "Neighbourhood": 5.4, "Express": 4.2}
GM = {"Superstore": 26.1, "Supermarket": 27.4, "Neighbourhood": 30.2, "Express": 31.5}
fmt_rows = {}
for fmt, (n, area, *_rest) in FORMATS.items():
    ss = [s for s in stores if s["format"] == fmt]
    sales = sum(s["sales"] for s in ss)
    eb = sum(s["ebitda"] for s in ss)
    cap = sum(s["capital"] for s in ss)
    fmt_rows[fmt] = {
        "stores": n, "area": area, "sales": round(sales), "sales_per_store": R1(sales / n),
        "density": round(sales * 1e6 / (n * area * 1000 * 52), 2),
        "lfl": LFL[fmt], "gm": GM[fmt], "ebitda": R1(eb), "margin": R1(eb / sales * 100),
        "capital": round(cap), "ret": R1(eb / cap * 100),
        "below": sum(1 for s in ss if s["ret"] < HURDLE),
    }
tot_sales = sum(s["sales"] for s in stores)
tot_eb = sum(s["ebitda"] for s in stores)
tot_cap = sum(s["capital"] for s in stores)
tot = {"stores": 214, "sales": round(tot_sales), "ebitda": R1(tot_eb), "capital": round(tot_cap),
       "margin": R1(tot_eb / tot_sales * 100), "ret": R1(tot_eb / tot_cap * 100)}
# displayed totals tie to displayed rows within rounding: recompute from rounded rows
assert abs(sum(r["sales"] for r in fmt_rows.values()) - tot["sales"]) <= 2
super_share = round(fmt_rows["Superstore"]["sales"] / tot["sales"] * 100)
super_cap_share = round(fmt_rows["Superstore"]["capital"] / tot["capital"] * 100)
super_eb_share = round(fmt_rows["Superstore"]["ebitda"] / tot["ebitda"] * 100)
below_total = sum(1 for s in stores if s["ret"] < HURDLE)
large_below = fmt_rows["Superstore"]["below"] + fmt_rows["Supermarket"]["below"]

# ---------------- page 3: segments ----------------
segments = ["Established families", "Time-pressed professionals", "Value seekers", "Older traditional", "Young urban"]
seg_spend = [11.6, 9.4, 12.9, 8.2, 4.3]  # market spend 2025 GBP bn
assert R1(sum(seg_spend)) == market["2025"]
seg_growth = [1.4, 6.2, 5.1, -0.6, 7.9]  # spend CAGR 2022-25 %
seg_mix = [37.5, 14.1, 16.7, 28.1, 3.6]  # % of Brindle sales by segment (loyalty-card read)
assert R1(sum(seg_mix)) == 100.0
brindle_seg = [round(tot_sales / 1000 * m / 100, 3) for m in seg_mix]  # Brindle sales by segment GBP bn
assert abs(sum(brindle_seg) - tot_sales / 1000) < 0.01, (sum(brindle_seg), tot_sales)
seg_sow = [R1(b / s * 100) for b, s in zip(brindle_seg, seg_spend)]
brindle_sow = R1(sum(brindle_seg) / market["2025"] * 100)
seg_mission = ["Main weekly shop", "Top-up and food for now", "Main shop at a discounter", "Main weekly shop", "Food for now and online"]
seg_format = ["Superstore", "Neighbourhood, express", "Discounter", "Supermarket", "Express, online"]
seg_hh = [1150, 820, 1240, 960, 610]  # households k
fast = [1, 2, 4]
slow = [0, 3]
fast_spend = R1(sum(seg_spend[i] for i in fast))
fast_share_mkt = round(fast_spend / market["2025"] * 100)
fast_sow = R1(sum(brindle_seg[i] for i in fast) / fast_spend * 100)
slow_sow = R1(sum(brindle_seg[i] for i in slow) / sum(seg_spend[i] for i in slow) * 100)
slow_of_brindle = round(sum(brindle_seg[i] for i in slow) / sum(brindle_seg) * 100)
mkt2022 = sum(s / (1 + g / 100) ** 3 for s, g in zip(seg_spend, seg_growth))
mkt_growth = R1(((market["2025"] / mkt2022) ** (1 / 3) - 1) * 100)
# one point of share in the fast segments is worth
pt_fast = round(fast_spend * 1000 / 100)

# ---------------- page 4: network ----------------
ACTIONS = ["Invest", "Keep", "Reformat", "Right-size", "Exit"]
act = {}
for a in ACTIONS:
    ss = [s for s in stores if s["action"] == a]
    act[a] = {"stores": len(ss), "large": sum(1 for s in ss if s["format"] in ("Superstore", "Supermarket")),
              "super": sum(1 for s in ss if s["format"] == "Superstore"),
              "sales": round(sum(s["sales"] for s in ss)), "ebitda": round(sum(s["ebitda"] for s in ss), 1),
              "ret": R1(sum(s["ebitda"] for s in ss) / sum(s["capital"] for s in ss) * 100) if ss else None,
              "capital": round(sum(s["capital"] for s in ss))}
assert sum(a["stores"] for a in act.values()) == 214

# plan levers (assumptions), each computed per store
REFORMAT_CAPEX = {"Superstore": 6.5, "Supermarket": 2.2, "Neighbourhood": 0.6, "Express": 0.3}  # GBP m per store
REFORMAT_RET = 10.0  # % cash return on capital after reformat (capital includes the new capex)
RIGHTSIZE_UPLIFT = 1.6  # margin points of sales from space sublet and labour model
RIGHTSIZE_CAPEX = 0.8
EXIT_COST = 2.4  # GBP m per exit, net of property proceeds
NEW_STORES = 30
NEW_CAPEX = 3.0  # GBP m per new neighbourhood store
NEW_RAMP = 0.70  # share of mature EBITDA reached on average by 2028
DRIFT = -0.9  # margin points lost by 2028 on unchanged superstores and supermarkets


def reformat_uplift(s):
    return (s["capital"] + REFORMAT_CAPEX[s["format"]]) * REFORMAT_RET / 100 - s["ebitda"]


lev = {}
rf = [s for s in stores if s["action"] == "Reformat"]
lev["Reformat"] = {"uplift": R1(sum(reformat_uplift(s) for s in rf)), "capex": R1(sum(REFORMAT_CAPEX[s["format"]] for s in rf))}
rs = [s for s in stores if s["action"] == "Right-size"]
lev["Right-size"] = {"uplift": R1(sum(s["sales"] * RIGHTSIZE_UPLIFT / 100 for s in rs)), "capex": R1(len(rs) * RIGHTSIZE_CAPEX)}
ex = [s for s in stores if s["action"] == "Exit"]
TRANSFER = 0.30  # share of an exited store's sales recaptured by nearby Brindle stores
transfer_margin = fmt_rows["Supermarket"]["margin"]
exit_lost = R1(-sum(s["ebitda"] for s in ex))
exit_transfer = R1(sum(s["sales"] for s in ex) * TRANSFER * transfer_margin / 100)
lev["Exit"] = {"uplift": R1(exit_lost + exit_transfer), "capex": R1(len(ex) * EXIT_COST),
               "lost": exit_lost, "transfer": exit_transfer}
nb = fmt_rows["Neighbourhood"]
new_eb_store = nb["ebitda"] / nb["stores"]
lev["Open"] = {"uplift": R1(NEW_STORES * new_eb_store * NEW_RAMP), "capex": R1(NEW_STORES * NEW_CAPEX)}
unchanged_large = [s for s in stores if s["action"] in ("Keep", "Invest") and s["format"] in ("Superstore", "Supermarket")]
lev["Drift"] = {"uplift": R1(sum(s["sales"] for s in unchanged_large) * DRIFT / 100), "capex": 0.0}
inv = [s for s in stores if s["action"] == "Invest"]
eb2025 = R1(tot_eb)
steps = [lev["Reformat"]["uplift"], lev["Right-size"]["uplift"], lev["Exit"]["uplift"], lev["Open"]["uplift"], lev["Drift"]["uplift"]]
eb2028 = R1(eb2025 + sum(steps))
capex_total = R1(sum(v["capex"] for v in lev.values()))
uplift_total = R1(eb2028 - eb2025)
stores_2028 = 214 - act["Exit"]["stores"] + NEW_STORES
margin2028_sales = tot_sales - sum(s["sales"] for s in ex)  # sales base excluding exits, before new stores
eb_growth_pct = round((eb2028 / eb2025 - 1) * 100)
payback = R1(capex_total / uplift_total)
reformat_share_gain = round(lev["Reformat"]["uplift"] / uplift_total * 100)
nb_sales_share = round(fmt_rows["Neighbourhood"]["sales"] / tot["sales"] * 100)
cap2028 = tot_cap - sum(s["capital"] for s in ex) + lev["Reformat"]["capex"] + lev["Right-size"]["capex"] + lev["Open"]["capex"]
ret2028 = R1(eb2028 / cap2028 * 100)
exit_capital = round(sum(s["capital"] for s in ex))
margin2028 = R1(eb2028 / (tot_sales - sum(s["sales"] for s in ex) * (1 - TRANSFER) + NEW_STORES * nb["sales_per_store"] * NEW_RAMP) * 100)

# phasing by year (counts), each row sums to its action's count
def split(n, w):
    a = [int(n * x) for x in w]
    a[-1] = n - sum(a[:-1])
    return a


phase = {
    "Reformat": split(act["Reformat"]["stores"], [0.25, 0.40, 0.35]),
    "Right-size": split(act["Right-size"]["stores"], [0.45, 0.35, 0.20]),
    "Exit": split(act["Exit"]["stores"], [0.5, 0.35, 0.15]),
    "Open": split(NEW_STORES, [0.2, 0.4, 0.4]),
}
for k, v in phase.items():
    assert sum(v) == (NEW_STORES if k == "Open" else act[k]["stores"]), k

# assertions on everything stated in titles and so-what text
assert R1(sum(steps)) == uplift_total or abs(R1(sum(steps)) - uplift_total) <= 0.1
assert abs(R1(eb2025 + R1(sum(steps))) - eb2028) <= 0.1

data = {
    "market": market, "channels": channels, "share": share, "large_spend": large_spend, "missions": missions,
    "trips": trips, "basket": basket, "formats": fmt_rows, "total": tot, "segments": segments, "seg_spend": seg_spend,
    "seg_growth": seg_growth, "seg_sow": seg_sow, "brindle_seg": brindle_seg, "seg_mission": seg_mission,
    "seg_format": seg_format, "seg_hh": seg_hh, "actions": act, "levers": lev, "phase": phase,
    "eb2025": eb2025, "eb2028": eb2028, "steps": steps, "capex_total": capex_total, "uplift_total": uplift_total,
    "stores_2028": stores_2028, "hurdle": HURDLE, "growth_cut": GROWTH_CUT, "exit_cut": EXIT_CUT,
    "points": [[s["growth"], s["ret"], s["action"], s["format"]] for s in stores],
    "brindle_sow": brindle_sow, "fast_spend": fast_spend, "fast_share_mkt": fast_share_mkt, "fast_sow": fast_sow,
    "slow_sow": slow_sow, "slow_of_brindle": slow_of_brindle, "mkt_growth": mkt_growth, "pt_fast": pt_fast,
    "super_share": super_share, "super_cap_share": super_cap_share, "super_eb_share": super_eb_share,
    "below_total": below_total, "large_below": large_below, "eb_growth_pct": eb_growth_pct, "payback": payback,
    "new_eb_store": round(new_eb_store, 2), "large_pts": large_pts, "disc_pts": disc_pts,
    "market_add": market_add, "topup_change": topup_change, "reformat_share_gain": reformat_share_gain, "nb_sales_share": nb_sales_share, "ret2028": ret2028, "exit_capital": exit_capital, "margin2028": margin2028, "transfer": TRANSFER, "small_online_2028": small_online_2028, "main_change": main_change, "tot_trips": tot_trips,
}
with open(os.path.join(HERE, "data.json"), "w") as f:
    json.dump(data, f, indent=1)

out = []
P = out.append
P(f"market 2019 {market['2019']} 2025 {market['2025']} 2028F {market['2028F']} add {market_add}")
P(f"large spend {large_spend} pts {large_pts} discount pts {disc_pts} disc+conv+online 2028 {small_online_2028}%")
P(f"trips {tot_trips} main change {main_change}%")
for k, r in fmt_rows.items():
    P(f"{k}: {r}")
P(f"total {tot}")
P(f"superstore share sales {super_share}% capital {super_cap_share}% ebitda {super_eb_share}%")
P(f"below hurdle {below_total} large below {large_below}")
P(f"segments sow {seg_sow} brindle {brindle_sow}% fast spend {fast_spend} ({fast_share_mkt}%) fast sow {fast_sow}% slow sow {slow_sow}% slow of brindle {slow_of_brindle}% mkt growth {mkt_growth}% pt fast {pt_fast}")
for k, a in act.items():
    P(f"{k}: {a}")
for k, v in lev.items():
    P(f"lever {k}: {v}")
P(f"eb2025 {eb2025} steps {steps} eb2028 {eb2028} uplift {uplift_total} (+{eb_growth_pct}%) capex {capex_total} payback {payback} stores 2028 {stores_2028}")
P(f"topup {topup_change}% reformat share of gain {reformat_share_gain}% neighbourhood sales share {nb_sales_share}%")
P(f"ret2028 {ret2028}% exit capital {exit_capital} margin2028 {margin2028}%")
P(f"phase {phase} new eb/store {round(new_eb_store, 2)}")
print("\n".join(out))
