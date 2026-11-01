"""Project Falcon valuation figures. Every number stated in the deck is computed and asserted here."""
import csv, statistics as st
from pathlib import Path
IN = Path("/home/user/pptx-skill/inputs")

def pct(xs, q):
    # Excel PERCENTILE.INC (linear interpolation), the banking convention
    xs = sorted(xs); h = (len(xs) - 1) * q; lo = int(h); hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (h - lo)

rows = list(csv.DictReader(open(IN / "falcon_comps.csv")))
peers = [r for r in rows if r["Ticker"]]
falc = [r for r in rows if not r["Ticker"]][0]
assert len(peers) == 8 and falc["Company"].startswith("Target: Falcon")
F = {k: float(falc[k]) for k in ["Revenue LTM ($m)", "Revenue NTM ($m)", "EBITDA LTM ($m)", "EBITDA NTM ($m)"]}
F_metric = {"rev_ltm": F["Revenue LTM ($m)"], "rev_ntm": F["Revenue NTM ($m)"],
            "ebitda_ltm": F["EBITDA LTM ($m)"], "ebitda_ntm": F["EBITDA NTM ($m)"]}

comps = []
for r in peers:
    ev = float(r["Enterprise value ($m)"])
    eq = float(r["Equity value ($m)"])
    c = dict(name=r["Company"], ticker=r["Ticker"], px=r["Share price ($)"], eq=eq, ev=ev,
             net_debt=ev - eq,
             ev_rev_ltm=ev / float(r["Revenue LTM ($m)"]), ev_rev_ntm=ev / float(r["Revenue NTM ($m)"]),
             ev_ebitda_ltm=ev / float(r["EBITDA LTM ($m)"]), ev_ebitda_ntm=ev / float(r["EBITDA NTM ($m)"]),
             growth=float(r["Revenue growth NTM (%)"]), margin=float(r["EBITDA margin LTM (%)"]))
    # margin in the file must agree with the file's own EBITDA / revenue
    assert abs(float(r["EBITDA LTM ($m)"]) / float(r["Revenue LTM ($m)"]) * 100 - c["margin"]) < 0.06, c["name"]
    comps.append(c)
assert abs(F["EBITDA LTM ($m)"] / F["Revenue LTM ($m)"] * 100 - float(falc["EBITDA margin LTM (%)"])) < 0.06

keys = ["ev_rev_ltm", "ev_rev_ntm", "ev_ebitda_ltm", "ev_ebitda_ntm", "growth", "margin"]
stats = {k: dict(mean=st.mean([c[k] for c in comps]), median=st.median([c[k] for c in comps]),
                 q1=pct([c[k] for c in comps], .25), q3=pct([c[k] for c in comps], .75),
                 hi=max(c[k] for c in comps), lo=min(c[k] for c in comps)) for k in keys}

prec = []
for r in csv.DictReader(open(IN / "falcon_precedents.csv")):
    prec.append(dict(date=r["Date announced"], target=r["Target"], acq=r["Acquirer"], ev=float(r["Enterprise value ($m)"]),
                     rev=float(r["EV / LTM revenue (x)"]), ebitda=float(r["EV / LTM EBITDA (x)"])))
assert len(prec) == 8
pstats = {k: dict(mean=st.mean([p[k] for p in prec]), median=st.median([p[k] for p in prec]),
                  q1=pct([p[k] for p in prec], .25), q3=pct([p[k] for p in prec], .75),
                  hi=max(p[k] for p in prec), lo=min(p[k] for p in prec)) for k in ["rev", "ebitda"]}

# Football field: interquartile range of each method's multiples applied to Falcon's matching metric; median marked
methods = [
    ("Trading comps, EV / NTM EBITDA", stats["ev_ebitda_ntm"], "ebitda_ntm"),
    ("Trading comps, EV / LTM EBITDA", stats["ev_ebitda_ltm"], "ebitda_ltm"),
    ("Precedents, EV / LTM EBITDA", pstats["ebitda"], "ebitda_ltm"),
    ("Trading comps, EV / NTM revenue", stats["ev_rev_ntm"], "rev_ntm"),
    ("Trading comps, EV / LTM revenue", stats["ev_rev_ltm"], "rev_ltm"),
    ("Precedents, EV / LTM revenue", pstats["rev"], "rev_ltm"),
]
ff = []
for name, s, m in methods:
    base = F_metric[m]
    ff.append(dict(method=name, metric=m, base=base, mult_lo=s["q1"], mult_med=s["median"], mult_hi=s["q3"],
                   ev_lo=s["q1"] * base, ev_med=s["median"] * base, ev_hi=s["q3"] * base))

# Rounding convention: multiples are rounded to 0.1x (EBITDA) / 0.01x (revenue) for display, but EVs use unrounded multiples
def p(label, v, fmt): print(f"{label}: {format(v, fmt)}")

print("== Falcon metrics ($m)")
for k, v in F_metric.items(): p(k, v, ".0f")
p("Falcon EBITDA margin LTM %", float(falc["EBITDA margin LTM (%)"]), ".1f")
p("Falcon revenue growth NTM %", float(falc["Revenue growth NTM (%)"]), ".1f")
print("== Trading comps")
for c in comps:
    print(f"{c['name']} | EV {c['ev']:,.0f} | Eq {c['eq']:,.0f} | ND {c['net_debt']:,.0f} | {c['ev_rev_ltm']:.2f}x {c['ev_rev_ntm']:.2f}x | {c['ev_ebitda_ltm']:.1f}x {c['ev_ebitda_ntm']:.1f}x | g {c['growth']:.1f} | m {c['margin']:.1f}")
for k in keys:
    s = stats[k]; f = ".2f" if "rev" in k else ".1f"
    print(f"{k}: " + " ".join(f"{n} {format(s[n], f)}" for n in ["mean", "median", "q1", "q3", "hi", "lo"]))
print("== Precedents")
for k in ["rev", "ebitda"]:
    s = pstats[k]; f = ".2f" if k == "rev" else ".1f"
    print(f"prec {k}: " + " ".join(f"{n} {format(s[n], f)}" for n in ["mean", "median", "q1", "q3", "hi", "lo"]))
print("== Football field (implied EV $m, interquartile; median)")
for r in ff:
    fm = ".2f" if "rev" in r["metric"] else ".1f"
    print(f"{r['method']} | on {r['metric']} {r['base']:.0f} | {format(r['mult_lo'], fm)}x-{format(r['mult_hi'], fm)}x (med {format(r['mult_med'], fm)}x) | EV {r['ev_lo']:,.0f}-{r['ev_hi']:,.0f} (med {r['ev_med']:,.0f})")

# Derived claims
ebitda_meds = [r["ev_med"] for r in ff if "ebitda" in r["metric"]]
lo_e, hi_e = min(r["ev_lo"] for r in ff if "ebitda" in r["metric"]), max(r["ev_hi"] for r in ff if "ebitda" in r["metric"])
p("EBITDA methods: EV low end", lo_e, ",.0f"); p("EBITDA methods: EV high end", hi_e, ",.0f")
p("EBITDA methods: median-of-medians", st.median(ebitda_meds), ",.0f")
prem = pstats["ebitda"]["median"] / stats["ev_ebitda_ltm"]["median"] - 1
p("Precedent median LTM EBITDA vs trading median LTM EBITDA, premium %", prem * 100, ".1f")
# Ranks of Falcon growth / margin in peer set
g_rank = 1 + sum(c["growth"] > float(falc["Revenue growth NTM (%)"]) for c in comps)
m_rank = 1 + sum(c["margin"] > float(falc["EBITDA margin LTM (%)"]) for c in comps)
p("Falcon growth rank among 9 (1 = highest)", g_rank, "d"); p("Falcon margin rank among 9", m_rank, "d")
# Peer correlation: margin vs EV/NTM EBITDA (for the scatter claim)
xs = [c["margin"] for c in comps]; ys = [c["ev_ebitda_ntm"] for c in comps]
p("corr(margin, EV/NTM EBITDA)", st.correlation(xs, ys), ".2f")
# Revenue methods range
lo_r, hi_r = min(r["ev_lo"] for r in ff if "rev" in r["metric"]), max(r["ev_hi"] for r in ff if "rev" in r["metric"])
p("Revenue methods: EV low end", lo_r, ",.0f"); p("Revenue methods: EV high end", hi_r, ",.0f")
# Precedent recency: 2025-2026 deals vs older
recent = [p_["ebitda"] for p_ in prec if p_["date"].endswith(("2025", "2026"))]
older = [p_["ebitda"] for p_ in prec if not p_["date"].endswith(("2025", "2026"))]
p("Precedents 2025-26 median EBITDA x", st.median(recent), ".1f"); p("Precedents 2023-24 median EBITDA x", st.median(older), ".1f")
sponsor = [p_["ebitda"] for p_ in prec if p_["acq"] in ("KKR-backed Arcis", "Blackstone", "Carlyle")]
strat = [p_["ebitda"] for p_ in prec if p_["acq"] not in ("KKR-backed Arcis", "Blackstone", "Carlyle")]
p("Precedents sponsor median EBITDA x", st.median(sponsor), ".1f"); p("Precedents strategic median EBITDA x", st.median(strat), ".1f")

print("== Extra claims")
p("corr(margin, EV/NTM revenue)", st.correlation([c["margin"] for c in comps], [c["ev_rev_ntm"] for c in comps]), ".2f")
p("corr(growth, EV/NTM revenue)", st.correlation([c["growth"] for c in comps], [c["ev_rev_ntm"] for c in comps]), ".2f")
eb = [r for r in ff if "ebitda" in r["metric"]]
ov_lo, ov_hi = max(r["ev_lo"] for r in eb), min(r["ev_hi"] for r in eb)
assert ov_lo < ov_hi
p("EBITDA methods overlap low", ov_lo, ",.0f"); p("EBITDA methods overlap high", ov_hi, ",.0f")
largest = max(prec, key=lambda x: x["ev"])
print(f"Largest precedent: {largest['target']} {largest['ev']:,.0f}")
prec_lo = [r for r in ff if r["method"] == "Precedents, EV / LTM EBITDA"][0]
assert prec_lo["ev_med"] > largest["ev"]
p("Precedent-implied EV at median exceeds largest precedent by", prec_lo["ev_med"] - largest["ev"], ",.0f")
ns = sum(p_["acq"] in ("KKR-backed Arcis", "Blackstone", "Carlyle") for p_ in prec)
print(f"Sponsor deals {ns}, strategic deals {len(prec)-ns}")
srt = sorted(prec, key=lambda x: -x["ebitda"])
print("Precedents ranked:", [(x["target"], x["ebitda"]) for x in srt])
print("Peers ranked by margin:", [(c["name"], c["margin"]) for c in sorted(comps, key=lambda c: -c["margin"])])
print("Peers ranked by growth:", [(c["name"], c["growth"]) for c in sorted(comps, key=lambda c: -c["growth"])])
p("Peer median margin", stats["margin"]["median"], ".2f"); p("Peer median growth", stats["growth"]["median"], ".2f")
p("Precedents median EBITDA EV $m", prec_lo["ev_med"], ",.0f")
ntm = [r for r in ff if r["method"] == "Trading comps, EV / NTM EBITDA"][0]
p("Trading NTM EBITDA median EV $m", ntm["ev_med"], ",.0f")
# implied multiples at the EBITDA overlap, for the table
for v in (ov_lo, ov_hi):
    print(f"At EV {v:,.0f}: {v/F_metric['ebitda_ltm']:.1f}x LTM EBITDA, {v/F_metric['ebitda_ntm']:.1f}x NTM EBITDA, {v/F_metric['rev_ltm']:.2f}x LTM revenue")
print("== Overlap restated")
for v in (ov_lo, ov_hi):
    print(f"EV {v:,.0f}: LTM EBITDA {v/F_metric['ebitda_ltm']:.1f}x NTM EBITDA {v/F_metric['ebitda_ntm']:.1f}x LTM rev {v/F_metric['rev_ltm']:.2f}x NTM rev {v/F_metric['rev_ntm']:.2f}x")
print("== Precedent size vs multiple")
r_size = st.correlation([p_["ev"] for p_ in prec], [p_["ebitda"] for p_ in prec])
p("corr(deal EV, EV/LTM EBITDA)", r_size, ".2f")
r_size_s = st.correlation([p_["ev"] for p_ in prec if p_["acq"] not in ("KKR-backed Arcis", "Blackstone", "Carlyle")], [p_["ebitda"] for p_ in prec if p_["acq"] not in ("KKR-backed Arcis", "Blackstone", "Carlyle")])
p("corr strategic only", r_size_s, ".2f")
big = [p_ for p_ in prec if p_["ev"] >= 2000]; small = [p_ for p_ in prec if p_["ev"] < 2000]
print(f"Deals >= $2,000m: {len(big)} median {st.median([b['ebitda'] for b in big]):.1f}x; < $2,000m: {len(small)} median {st.median([b['ebitda'] for b in small]):.1f}x")
fitp = st.linear_regression([p_["ev"] for p_ in prec], [p_["ebitda"] for p_ in prec])
print(f"fit slope per $1bn {fitp.slope*1000:.2f}x intercept {fitp.intercept:.2f}")
