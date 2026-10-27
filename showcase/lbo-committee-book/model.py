"""Corvane Flow Systems (fictional): the LBO model behind the six pages. Every figure is invented
and illustrative. run(params) is the whole model, so every sensitivity cell is a full re-run."""
from statistics import mean, median

HIST = [2021, 2022, 2023, 2024, 2025]
ENTRY = 2026          # FY2026E: the year the deal closes on (31 December 2026)
PROJ = [2027, 2028, 2029, 2030, 2031]

SEG = {  # revenue $m, FY2021A..FY2025A, FY2026E
    "Engineered valves": [228.0, 251.5, 270.2, 281.9, 296.4, 309.8],
    "Pumps and systems": [141.2, 155.0, 161.8, 158.3, 167.5, 175.1],
    "Aftermarket and services": [118.6, 129.4, 142.7, 155.2, 168.9, 182.3],
}
EBITDA_H = [80.0, 90.6, 101.2, 106.6, 117.1, 126.0]
GM_H = [32.1, 32.6, 33.5, 34.1, 34.7, 35.2]          # gross margin pre-D&A, %
CAPEX_H = [16.9, 18.3, 19.6, 20.8, 21.5, 22.7]
BACKLOG_H = [198.4, 221.7, 238.0, 241.9, 259.3, 274.6]
SEG_MARGIN_26 = {"Engineered valves": 21.0, "Pumps and systems": 13.5, "Aftermarket and services": 30.5}
CORPORATE_26 = -18.3
END_MKT = [("Chemicals and petrochemicals", 22.4), ("Water and wastewater", 18.6), ("Power generation", 14.2),
           ("Midstream oil and gas", 12.1), ("General industrial", 11.8), ("Food, beverage and pharma", 11.3),
           ("Mining and minerals", 9.6)]

BASE = {
    "growth": {"Engineered valves": [5.0, 5.5, 5.5, 5.0, 4.5], "Pumps and systems": [3.5, 4.0, 4.5, 4.0, 4.0],
               "Aftermarket and services": [8.5, 8.5, 8.0, 7.5, 7.5]},
    "margin": [19.9, 20.8, 21.6, 22.3, 22.8],
    "gm": [35.7, 36.2, 36.7, 37.2, 37.7],
    "growth_delta": 0.0, "margin_delta": 0.0,
    "entry_mult": 10.0, "exit_mult": 10.0, "exit_year": 2031,
    "tlb_x": 4.50, "notes_x": 1.25, "sofr_delta": 0.0,
}
DOWNSIDE_GROWTH = {"Engineered valves": [-10.0, 2.0, 5.0, 5.0, 4.5], "Pumps and systems": [-12.0, 1.0, 4.5, 4.0, 4.0],
                   "Aftermarket and services": [-2.0, 6.0, 7.0, 7.0, 7.0]}
DOWNSIDE_MARGIN = [17.2, 17.9, 18.8, 19.4, 19.8]
SOFR = [3.60, 3.40, 3.30, 3.25, 3.25]
TLB_MARGIN, NOTES_RATE, RCF_SIZE, RCF_FEE = 3.50, 8.25, 175.0, 0.375
DA_PCT, CAPEX_PCT, NWC_PCT, TAX = 3.1, 3.3, 17.5, 25.0
MIN_CASH, FIN_FEE_PCT, OID_PCT, MA_FEES, EXIT_FEE_PCT, MIP_PCT = 25.0, 2.25, 1.0, 21.5, 1.5, 6.0
ROLLOVER, REFI_DEBT = 40.0, 286.4
COVENANT = 6.60  # springing first-lien net leverage maximum, tested when the RCF is over 40% drawn
HURDLE_IRR, HURDLE_MOIC = 20.0, 2.5


def r1(x):
    return round(x + 1e-9, 1)


def run(p=None, downside=False):
    p = {**BASE, **(p or {})}
    e26 = EBITDA_H[-1]
    ev = r1(p["entry_mult"] * e26)
    tlb0 = r1(p["tlb_x"] * e26)
    notes0 = r1(p["notes_x"] * e26)
    fin_fees = r1((tlb0 + notes0) * FIN_FEE_PCT / 100)
    oid = r1(tlb0 * OID_PCT / 100)
    uses = {"Purchase of equity": r1(ev - REFI_DEBT), "Refinance existing debt": REFI_DEBT,
            "Cash to balance sheet": MIN_CASH, "Financing fees and OID": r1(fin_fees + oid),
            "M&A advisory and other costs": MA_FEES}
    total_uses = r1(sum(uses.values()))
    sponsor = r1(total_uses - tlb0 - notes0 - ROLLOVER)
    sources = {"Revolver ($175.0m), undrawn": 0.0, "First-lien term loan B": tlb0,
               "Senior unsecured notes": notes0, "Management rollover": ROLLOVER, "Sponsor equity": sponsor}
    assert r1(sum(sources.values())) == total_uses
    seg_rev = {k: [v[-1]] for k, v in SEG.items()}
    growth = DOWNSIDE_GROWTH if downside else p["growth"]
    margin = DOWNSIDE_MARGIN if downside else p["margin"]
    years = [y for y in PROJ if y <= p["exit_year"]]
    rows = []
    tlb, notes = tlb0, notes0
    rev_prev = sum(v[-1] for v in SEG.values())
    for i, y in enumerate(years):
        for k in seg_rev:
            seg_rev[k].append(r1(seg_rev[k][-1] * (1 + (growth[k][i] + p["growth_delta"]) / 100)))
        rev = r1(sum(seg_rev[k][-1] for k in seg_rev))
        ebitda = r1(rev * (margin[i] + p["margin_delta"]) / 100)
        gp = r1(rev * p["gm"][i] / 100)
        sga = r1(gp - ebitda)
        da = r1(rev * DA_PCT / 100)
        ebit = r1(ebitda - da)
        tlb_rate = max(SOFR[i] + p["sofr_delta"], 0.50) + TLB_MARGIN
        int_tlb = r1(tlb * tlb_rate / 100)
        int_notes = r1(notes * NOTES_RATE / 100)
        int_rcf = r1(RCF_SIZE * RCF_FEE / 100)
        interest = r1(int_tlb + int_notes + int_rcf)
        ebt = r1(ebit - interest)
        tax = r1(max(ebt, 0) * TAX / 100)
        ni = r1(ebt - tax)
        capex = r1(rev * CAPEX_PCT / 100)
        dnwc = r1((rev - rev_prev) * NWC_PCT / 100)
        fcf = r1(ebitda - capex - dnwc - interest - tax)
        mand = min(r1(tlb0 * 0.01), tlb)
        sweep = min(max(r1(fcf - mand), 0.0), r1(tlb - mand))
        paydown = r1(mand + sweep)
        assert fcf >= mand, (y, fcf)
        tlb = r1(tlb - paydown)
        net_debt = r1(tlb + notes - MIN_CASH)
        fl_net = r1(tlb - MIN_CASH)
        rows.append(dict(year=y, seg={k: seg_rev[k][-1] for k in seg_rev}, rev=rev, growth=r1((rev / rev_prev - 1) * 100),
                         gp=gp, sga=sga, ebitda=ebitda, margin=r1(ebitda / rev * 100), da=da, ebit=ebit,
                         int_tlb=int_tlb, int_notes=int_notes, int_rcf=int_rcf, interest=interest, ebt=ebt, tax=tax, ni=ni,
                         capex=capex, dnwc=dnwc, fcf=fcf, mand=mand, sweep=sweep, paydown=paydown, tlb=tlb, notes=notes,
                         debt=r1(tlb + notes), net_debt=net_debt, lev=round(r1(tlb + notes) / ebitda, 2),
                         net_lev=round(net_debt / ebitda, 2), fl_net_lev=round(fl_net / ebitda, 2),
                         cover=round(ebitda / interest, 2), cover_capex=round((ebitda - capex) / interest, 2),
                         fcf_debt=r1(fcf / r1(tlb + notes + paydown) * 100),
                         headroom=r1((1 - fl_net / (COVENANT * ebitda)) * 100), tlb_rate=round(tlb_rate, 2)))
        rev_prev = rev
    last = rows[-1]
    exit_ev = r1(p["exit_mult"] * last["ebitda"])
    exit_fees = r1(exit_ev * EXIT_FEE_PCT / 100)
    equity_exit = r1(exit_ev - exit_fees - last["net_debt"])
    invested = r1(sponsor + ROLLOVER)
    mip = r1(max(equity_exit - invested, 0) * MIP_PCT / 100)
    to_holders = r1(equity_exit - mip)
    sponsor_share = sponsor / invested
    proceeds = r1(to_holders * sponsor_share)
    moic = proceeds / sponsor
    hold = len(years)
    irr = (moic ** (1 / hold) - 1) * 100
    return dict(p=p, ev=ev, tlb0=tlb0, notes0=notes0, fin_fees=fin_fees, oid=oid, uses=uses, total_uses=total_uses,
                sources=sources, sponsor=sponsor, invested=invested, rows=rows, exit_ev=exit_ev, exit_fees=exit_fees,
                equity_exit=equity_exit, mip=mip, to_holders=to_holders, sponsor_share=sponsor_share, proceeds=proceeds,
                moic=moic, irr=irr, hold=hold)


def hist():
    out = []
    for i, y in enumerate(HIST + [ENTRY]):
        rev = r1(sum(v[i] for v in SEG.values()))
        out.append(dict(year=y, seg={k: v[i] for k, v in SEG.items()}, rev=rev, ebitda=EBITDA_H[i],
                        margin=r1(EBITDA_H[i] / rev * 100), gm=GM_H[i], gp=r1(rev * GM_H[i] / 100), capex=CAPEX_H[i],
                        backlog=BACKLOG_H[i], am_share=r1(SEG["Aftermarket and services"][i] / rev * 100),
                        conv=r1((EBITDA_H[i] - CAPEX_H[i]) / EBITDA_H[i] * 100)))
    for i in range(1, len(out)):
        out[i]["growth"] = r1((out[i]["rev"] / out[i - 1]["rev"] - 1) * 100)
    out[0]["growth"] = None
    return out


def cagr(a, b, n):
    return ((b / a) ** (1 / n) - 1) * 100


# Fictional listed peers: EV $m, EV/Rev 26E, EV/EBITDA 26E, 27E, rev growth 26E %, EBITDA margin 26E %,
# aftermarket share %, net debt / EBITDA, P/E 27E
PEERS = [
    ("Brightwater Valve Group", 9840, 2.91, 13.6, 12.5, 6.1, 21.4, 38, 1.4, 19.8),
    ("Aldergate Controls", 7215, 2.48, 12.4, 11.6, 5.2, 20.0, 34, 1.9, 18.1),
    ("Norrland Flow", 5630, 2.12, 11.8, 11.0, 4.8, 18.0, 31, 2.2, 17.4),
    ("Castellan Process Technologies", 4980, 2.36, 11.5, 10.7, 5.6, 20.5, 29, 1.6, 16.9),
    ("Saxe-Halden", 4410, 1.71, 10.9, 10.3, 3.9, 15.7, 27, 2.4, 15.6),
    ("Tessaly Pumps", 3865, 1.64, 10.2, 9.6, 3.4, 16.1, 24, 2.8, 14.8),
    ("Pemberton Fluid Systems", 3120, 1.83, 10.6, 9.9, 4.5, 17.3, 30, 2.0, 15.9),
    ("Hartwell Motion and Flow", 2775, 1.42, 9.4, 8.9, 2.9, 15.1, 22, 3.1, 13.7),
    ("Orenvale Engineering", 2240, 1.58, 9.8, 9.2, 4.1, 16.1, 26, 2.6, 14.4),
    ("Quillon Instruments", 1960, 2.05, 11.2, 10.4, 6.4, 18.3, 33, 1.2, 17.0),
    ("Varga Hydraulics", 1515, 1.21, 8.6, 8.1, 2.2, 14.1, 19, 3.4, 12.6),
    ("Kormoran Industrial", 1180, 1.37, 9.1, 8.6, 3.6, 15.1, 21, 2.9, 13.2),
]

# Fictional industrial LBO financings: borrower, closed, EV $m, EV/EBITDA, total lev, first-lien lev, equity %,
# TLB spread bp, OID, corporate ratings
FINANCINGS = [
    ("Halberd Pumps", "Q3 2026", 1840, 11.2, 6.00, 4.75, 44, 350, 99.50, "B2 / B"),
    ("Ostrava Valve Holdings", "Q3 2026", 960, 10.1, 5.50, 4.50, 46, 375, 99.00, "B2 / B"),
    ("Marrow Industrial Controls", "Q2 2026", 1420, 10.8, 5.75, 4.25, 47, 325, 99.50, "B2 / B+"),
    ("Tidewell Fluid Handling", "Q2 2026", 720, 9.6, 5.25, 5.25, 45, 400, 98.50, "B3 / B"),
    ("Ferrous Flow Partners", "Q1 2026", 2350, 12.0, 6.25, 4.75, 48, 325, 99.75, "B2 / B"),
    ("Lindqvist Actuation", "Q1 2026", 610, 9.4, 5.00, 5.00, 47, 425, 98.50, "B3 / B-"),
    ("Corran Seals and Gaskets", "Q4 2025", 1130, 10.5, 5.75, 4.50, 45, 350, 99.00, "B2 / B"),
    ("Westbury Process Equipment", "Q4 2025", 880, 9.9, 5.50, 5.50, 44, 375, 99.00, "B2 / B"),
    ("Aurel Metering", "Q3 2025", 1560, 11.5, 6.00, 4.50, 49, 350, 99.25, "B2 / B"),
    ("Brennan Compressor Group", "Q3 2025", 1990, 10.9, 5.75, 4.75, 46, 350, 99.50, "B1 / B+"),
    ("Stellan Filtration", "Q2 2025", 740, 10.2, 5.25, 5.25, 48, 400, 98.75, "B3 / B"),
    ("Pell and Rook Instruments", "Q2 2025", 1275, 11.0, 6.00, 4.50, 45, 375, 99.00, "B2 / B"),
]


def stats(vals):
    return {"Mean": mean(vals), "Median": median(vals), "High": max(vals), "Low": min(vals)}


GEO = [("North America", 61.0, 58.0), ("Europe", 26.0, 27.0), ("Asia Pacific and rest of world", 13.0, 15.0)]   # share %, FY2021A and FY2026E

# operating KPIs, FY2021A..FY2026E
OPS = {
    "Book-to-bill (x)": [1.06, 1.08, 1.03, 0.99, 1.05, 1.04],
    "Price realisation (%)": [2.1, 5.8, 4.4, 2.6, 2.9, 2.7],
    "On-time delivery (%)": [88.4, 84.9, 89.7, 92.3, 93.8, 94.6],
    "Top 10 customers (% of revenue)": [24.0, 23.1, 22.5, 21.9, 21.4, 21.0],
    "Employees (year end)": [3920, 4040, 4150, 4210, 4290, 4350],
}

# fictional precedent M&A in flow control: date, target, acquirer, EV $m, EV/EBITDA LTM, EV/revenue
PRECEDENTS = [
    ("Jun 2026", "Ostrava Valve Holdings", "Halvard Capital", 960, 10.1, 1.86),
    ("Mar 2026", "Lumen Fluid Controls", "Brightwater Valve Group", 1430, 12.6, 2.44),
    ("Nov 2025", "Delacroix Pompes", "Saxe-Halden", 615, 11.4, 1.97),
    ("Aug 2025", "Ridgeway Actuators", "Aldergate Controls", 880, 12.9, 2.62),
    ("May 2025", "Torvik Process Valves", "Norrland Flow", 1120, 11.8, 2.21),
    ("Jan 2025", "Calder Pump Works", "Kestrel Ridge Partners", 540, 9.6, 1.48),
    ("Oct 2024", "Seaborne Flow Services", "Castellan Process Technologies", 760, 13.4, 2.85),
    ("Jun 2024", "Mattox Industrial Valves", "Pemberton Fluid Systems", 1015, 11.1, 2.05),
    ("Feb 2024", "Arlen Hydraulic Systems", "Varga Hydraulics", 430, 9.2, 1.39),
    ("Sep 2023", "Penrose Metering", "Quillon Instruments", 690, 12.2, 2.30),
]
STRATEGIC = {"Lumen Fluid Controls", "Delacroix Pompes", "Ridgeway Actuators", "Torvik Process Valves", "Seaborne Flow Services",
             "Mattox Industrial Valves", "Arlen Hydraulic Systems", "Penrose Metering"}

FEES = [("Financing fees (2.25% of funded debt)", None), ("Original issue discount (1.0% of TLB)", None),
        ("M&A advisory", 12.6), ("Legal, accounting and diligence", 6.4), ("R&W insurance and other", 2.5)]
MAINT_CAPEX_PCT = 2.1
