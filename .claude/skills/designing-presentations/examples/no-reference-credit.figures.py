"""Larkspur Rail Freight (examples/no-reference-credit.*): every figure the two pages state that the brief does not: computed and asserted here, printed for --computed."""
import sys

Y = [2021, 2022, 2023, 2024, 2025]
car = [182, 191, 204, 199, 213]
com = {"Intermodal": [61.4, 66.0, 72.8, 70.1, 78.5], "Chemicals": [44.2, 47.9, 51.3, 53.0, 56.6],
       "Agriculture": [38.7, 36.2, 40.9, 42.5, 41.8], "Aggregates": [27.5, 29.8, 31.1, 30.4, 33.2], "Coal": [22.9, 20.4, 17.6, 14.8, 12.3]}
ebitda = [58.3, 61.0, 66.9, 64.2, 72.4]
capex = [24.1, 26.5, 28.0, 25.7, 29.9]
interest = [14.2, 13.8, 15.9, 17.1, 16.4]
taxes = [4.0, 4.6, 5.2, 4.9, 6.1]
net_debt = [228.0, 226.5, 238.0, 252.4, 230.2]
LEV_MAX, COVER_MIN = 4.00, 3.00
out = []
def f1(x): return f"{x:,.1f}"
def cagr(a, b): return (b / a) ** 0.25 - 1
rev = [round(sum(v[i] for v in com.values()), 1) for i in range(5)]
assert rev == [194.7, 200.3, 213.7, 210.8, 222.4], rev
out += [f1(r) for r in rev]
rpc = [round(r * 1e6 / (c * 1e3)) for r, c in zip(rev, car)]
out += [f"{x:,}" for x in rpc]
growth = [None] + [round((rev[i] / rev[i - 1] - 1) * 100, 1) for i in range(1, 5)]
out += [f1(g) for g in growth[1:]]
opex = [round(r - e, 1) for r, e in zip(rev, ebitda)]
out += [f1(x) for x in opex]
margin = [round(e / r * 100, 1) for e, r in zip(ebitda, rev)]
out += [f1(x) for x in margin]
fcf = [round(e - c - i - t, 1) for e, c, i, t in zip(ebitda, capex, interest, taxes)]
out += [f1(x) for x in fcf]
lev = [round(d / e, 2) for d, e in zip(net_debt, ebitda)]
cover = [round(e / i, 2) for e, i in zip(ebitda, interest)]
out += [f"{x:.2f}" for x in lev + cover]
c = {"car": cagr(car[0], car[-1]), "rpc": cagr(rpc[0], rpc[-1]), "rev": cagr(rev[0], rev[-1]), "ebitda": cagr(ebitda[0], ebitda[-1]),
     "capex": cagr(capex[0], capex[-1]), "opex": cagr(opex[0], opex[-1]), "fcf": cagr(fcf[0], fcf[-1]),
     "interest": cagr(interest[0], interest[-1]), "taxes": cagr(taxes[0], taxes[-1]), "nd": cagr(net_debt[0], net_debt[-1])}
c.update({k: cagr(v[0], v[-1]) for k, v in com.items()})
out += [f"{v * 100:.1f}" for v in c.values()]
# covenant headroom: EBITDA could fall by this share before the leverage test fails; the cover test by its own
lev_room = [round((1 - d / (LEV_MAX * e)) * 100, 1) for d, e in zip(net_debt, ebitda)]
cover_room = [round((1 - COVER_MIN * i / e) * 100, 1) for e, i in zip(ebitda, interest)]
out += [f1(x) for x in lev_room + cover_room]
share21 = {k: round(v[0] / rev[0] * 100, 1) for k, v in com.items()}
share25 = {k: round(v[-1] / rev[-1] * 100, 1) for k, v in com.items()}
out += [f1(x) for x in list(share21.values()) + list(share25.values())]
# rounded shares need not add to 100.0 (2025 adds to 99.9): the share columns' totals cell states 100.0 and ties out by "none"
out.append("100.0")
assert lev[-1] == 3.18 and max(lev) < LEV_MAX and min(cover) > COVER_MIN, (lev, lev_room)
growth_share = round(share25["Intermodal"] + share25["Chemicals"], 1)
assert growth_share == 60.7 and min(cover) == 3.75 and max(lev) == lev[3] == 3.93 and lev_room[3] == 1.7
out.append(f1(growth_share))
growth_share21 = round(share21["Intermodal"] + share21["Chemicals"], 1)
assert growth_share21 == 54.2
out.append(f1(growth_share21))
op_ratio = [round(o / r * 100, 1) for o, r in zip(opex, rev)]
capex_share = [round(c / r * 100, 1) for c, r in zip(capex, rev)]
conversion = [round(f / e * 100, 1) for f, e in zip(fcf, ebitda)]
out += [f1(x) for x in op_ratio + capex_share + conversion]
intermodal_24 = round((com["Intermodal"][3] / com["Intermodal"][2] - 1) * 100, 1)
assert intermodal_24 == -3.7
out.append(f1(intermodal_24))
debt = {"tlb": 185.0, "rcf": 20.0, "notes": 41.4}
cash, rcf_commit = 16.2, 50.0
gross = round(sum(debt.values()), 1)
assert gross == 246.4 and round(gross - cash, 1) == net_debt[-1] == 230.2
liquidity = round(cash + rcf_commit - debt["rcf"], 1)
assert liquidity == 46.2
out += [f1(gross), f1(liquidity), f1(rcf_commit - debt["rcf"])]
gross_lev = round(gross / ebitda[-1], 2)
out.append(f"{gross_lev:.2f}")
print("# ratios", op_ratio, capex_share, conversion, gross_lev, file=sys.stderr)
print(" ".join(dict.fromkeys(out)))
for name, v in [("rev", rev), ("rpc", rpc), ("growth", growth), ("opex", opex), ("margin", margin), ("fcf", fcf), ("lev", lev), ("cover", cover),
                ("lev_room", lev_room), ("cover_room", cover_room), ("share21", share21), ("share25", share25)]:
    print("#", name, v, file=sys.stderr)
print("#", {k: round(v * 100, 1) for k, v in c.items()}, file=sys.stderr)
