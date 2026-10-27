"""Corvane Software (fictional). Every figure is invented for illustration; this script
computes and asserts each one a title, lead-in, label or table states, and prints them."""
import json, sys
OUT = {}
def put(k, v):
    OUT[k] = v
    print(f"{k} = {v}")
def r1(x): return round(x + 1e-9, 1)

Q = ["Q3 FY24","Q4 FY24","Q1 FY25","Q2 FY25","Q3 FY25","Q4 FY25","Q1 FY26","Q2 FY26","Q3 FY26"]
QS = ["Q3'24","Q4'24","Q1'25","Q2'25","Q3'25","Q4'25","Q1'26","Q2'26","Q3'26"]
sub = [228.4,241.9,252.6,266.0,280.3,296.1,309.4,325.2,342.8]
svc = [14.1,14.6,13.8,14.2,14.9,15.3,14.6,15.0,15.4]
prior_total = [190.9,205.2,214.8,227.8]          # Q3 FY23..Q2 FY24, for Y/Y only
tot = [r1(a+b) for a,b in zip(sub,svc)]
allt = prior_total + tot
yoy = [r1((allt[i+4]/allt[i]-1)*100) for i in range(9)]
put("quarters", QS); put("subscription_rev", sub); put("services_rev", svc); put("total_rev", tot); put("rev_yoy_pct", yoy)
assert tot[-1] == 358.2 and yoy[-1] == 21.3
sub_yoy = r1((sub[-1]/sub[-5]-1)*100); put("sub_rev_yoy_q3fy26", sub_yoy)
sub_share = r1(sub[-1]/tot[-1]*100); put("sub_share_q3fy26", sub_share)

arr = [1012,1068,1115,1168,1226,1292,1349,1415,1498]; arr_prev = 962
nn = [arr[0]-arr_prev] + [arr[i]-arr[i-1] for i in range(1,9)]
put("arr", arr); put("net_new_arr", nn)
arr_yoy = r1((arr[-1]/arr[-5]-1)*100); put("arr_yoy_q3fy26", arr_yoy)
nn_yoy = r1((nn[-1]/nn[-5]-1)*100); put("net_new_arr_yoy_q3fy26", nn_yoy)
assert nn[-1] == max(nn) and nn[-1] == 83
assert arr_yoy == 22.2 and nn_yoy == 43.1

nrr = [121,119,118,117,116,116,117,118,119]; grr = [93,93,92,92,92,93,93,93,94]
put("nrr", nrr); put("grr", grr)
assert min(nrr) == 116 and nrr[-1]-min(nrr) == 3
cust100 = [1488,1561,1630,1702,1779,1858,1931,2032,2148]; put("cust_100k", cust100)
c_yoy = r1((cust100[-1]/cust100[-5]-1)*100); put("cust_100k_yoy", c_yoy)
cust1m = [61,66,70,75,81,88,94,101,109]; put("cust_1m", cust1m)
c1_yoy = r1((cust1m[-1]/cust1m[-5]-1)*100); put("cust_1m_yoy", c1_yoy)
rpo = {"Q3 FY25": 1384, "Q3 FY26": 1741}; rpo_yoy = r1((1741/1384-1)*100); put("rpo_yoy", rpo_yoy)

# non-GAAP P&L, percent of total revenue, last five quarters
L5 = Q[4:]; rev5 = tot[4:]
gm  = [79.6,79.9,80.1,80.3,80.4]
sm  = [38.9,38.1,37.0,36.2,35.8]
rd  = [20.4,20.1,19.9,19.7,19.5]
ga  = [9.1,8.9,8.7,8.6,8.5]
opm = [r1(g-s-r-a) for g,s,r,a in zip(gm,sm,rd,ga)]
put("ng_gross_margin", gm); put("ng_sm_pct", sm); put("ng_rd_pct", rd); put("ng_ga_pct", ga); put("ng_op_margin", opm)
assert opm[0] == 11.2 and opm[-1] == 16.6
bridge = {"start": opm[0], "gross margin": r1(gm[-1]-gm[0]), "S&M": r1(sm[0]-sm[-1]), "R&D": r1(rd[0]-rd[-1]), "G&A": r1(ga[0]-ga[-1])}
steps = [bridge["gross margin"], bridge["S&M"], bridge["R&D"], bridge["G&A"]]
assert r1(opm[0] + sum(steps)) == opm[-1]
put("bridge_pts", bridge); put("op_margin_change_pts", r1(opm[-1]-opm[0]))
assert r1(opm[-1]-opm[0]) == 5.4 and bridge["S&M"] == 3.1
sm_share_of_gain = r1(bridge["S&M"]/5.4*100); put("sm_share_of_margin_gain_pct", sm_share_of_gain)
# bridge drawing: base and step
run = opm[0]; base = [0]; hgt = [opm[0]]
for d in steps:
    base.append(r1(run)); hgt.append(d); run = r1(run + d)
base.append(0); hgt.append(opm[-1]); put("bridge_base", base); put("bridge_height", hgt)

ng_oi = [r1(r*m/100) for r,m in zip(rev5,opm)]; put("ng_op_income", ng_oi)
sbc = [47.9,49.6,50.2,51.4,52.3]; amort = [6.4,6.4,6.2,6.1,6.1]; ptax = [1.9,1.2,3.1,2.2,2.4]; restr = [3.2,0.0,0.0,1.1,0.0]
gaap_oi = [r1(n-s-a-p-x) for n,s,a,p,x in zip(ng_oi,sbc,amort,ptax,restr)]
for i in range(5):
    assert r1(gaap_oi[i]+sbc[i]+amort[i]+ptax[i]+restr[i]) == ng_oi[i]
put("gaap_op_income", gaap_oi); put("sbc", sbc); put("amort", amort); put("payroll_tax", ptax); put("restructuring", restr)
gaap_m = [r1(g/r*100) for g,r in zip(gaap_oi,rev5)]; put("gaap_op_margin", gaap_m)
sbc_pct = [r1(s/r*100) for s,r in zip(sbc,rev5)]; put("sbc_pct_rev", sbc_pct)
put("ng_op_income_yoy_pct", r1((ng_oi[-1]/ng_oi[0]-1)*100))

ocf = [61.2,74.8,70.3,73.9,86.5]; capex = [7.1,8.0,7.4,8.3,9.8]
fcf = [r1(o-c) for o,c in zip(ocf,capex)]; fcfm = [r1(f/r*100) for f,r in zip(fcf,rev5)]
put("fcf", fcf); put("fcf_margin", fcfm)
rule40 = r1(yoy[-1] + fcfm[-1]); put("rule_of_40_q3fy26", rule40)

# CAC payback: prior-quarter non-GAAP S&M / (net new ARR x gross margin), months
sm_dollars_all = {}
sm_prev_q2fy25 = r1(280.2*0.395)  # Q2 FY25 S&M at 39.5% of revenue
sm_d = [r1(r*s/100) for r,s in zip(rev5,sm)]
prev = [sm_prev_q2fy25] + sm_d[:-1]
payback = [r1(p/(n*g/100)*12) for p,n,g in zip(prev, nn[4:], gm)]
put("sm_dollars", sm_d); put("sm_prior_q", prev); put("cac_payback_months", payback)
magic = [round((n)/p,2) for n,p in zip(nn[4:], prev)]  # net new ARR / prior-quarter S&M
put("magic_number", magic)

cohorts = {"FY2021":[1.00,1.38,1.66,1.88,2.05],"FY2022":[1.00,1.35,1.62,1.82],"FY2023":[1.00,1.41,1.71],"FY2024":[1.00,1.47],"FY2025":[1.00]}
put("cohorts", cohorts)
y2 = {k:v[1] for k,v in cohorts.items() if len(v)>1}
assert max(y2, key=y2.get) == "FY2024" and y2["FY2024"] == 1.47
y3 = {k:v[2] for k,v in cohorts.items() if len(v)>2}
assert max(y3, key=y3.get) == "FY2023"
cohort_land_arr = {"FY2021":38.4,"FY2022":51.2,"FY2023":63.9,"FY2024":72.6,"FY2025":80.1}
put("cohort_land_arr", cohort_land_arr)

# guidance
q3_guide = {"rev": (350.0,354.0), "ng_oi": (52.0,54.0)}
put("q3_rev_beat_vs_high", r1(tot[-1]-q3_guide["rev"][1])); put("q3_oi_beat_vs_high", r1(ng_oi[-1]-q3_guide["ng_oi"][1]))
assert r1(tot[-1]-354.0) == 4.2 and r1(ng_oi[-1]-54.0) == 5.5
q4fy25 = tot[5]
q4g = (372.0,376.0); put("q4_guide_yoy", (r1((q4g[0]/q4fy25-1)*100), r1((q4g[1]/q4fy25-1)*100)))
fy25 = r1(sum(tot[2:6])); put("fy25_rev", fy25)
ytd = r1(sum(tot[6:9])); put("fy26_ytd_rev", ytd)
fyg = (r1(ytd+q4g[0]), r1(ytd+q4g[1])); put("fy26_guide_now", fyg)
assert fyg == (1394.4, 1398.4)
hist = [("Initial (Feb)",1355.0,1365.0),("After Q1 (May)",1367.0,1377.0),("After Q2 (Aug)",1379.0,1389.0),("After Q3 (Oct)",fyg[0],fyg[1])]
mids = [r1((a+b)/2) for _,a,b in hist]; put("fy26_guide_mid_history", mids)
put("fy26_guide_raise_total", r1(mids[-1]-mids[0])); put("fy26_guide_raise_pct", r1((mids[-1]/mids[0]-1)*100))
assert r1(mids[-1]-mids[0]) == 36.4
put("fy26_guide_yoy", (r1((fyg[0]/fy25-1)*100), r1((fyg[1]/fy25-1)*100)))
q4oi = (61.0,63.0); put("q4_guide_op_margin", (r1(q4oi[0]/q4g[0]*100), r1(q4oi[1]/q4g[1]*100)))
fy_oi_ytd = r1(sum(ng_oi[2:5])); fy_oi = (r1(fy_oi_ytd+q4oi[0]), r1(fy_oi_ytd+q4oi[1]))
put("fy26_ng_oi_ytd", fy_oi_ytd); put("fy26_ng_oi_guide", fy_oi); put("fy26_ng_op_margin_guide", (r1(fy_oi[0]/fyg[0]*100), r1(fy_oi[1]/fyg[1]*100)))
q3_guide_margin = (r1(52.0/350.0*100), r1(54.0/354.0*100)); put("q3_guide_op_margin", q3_guide_margin)
assert q3_guide_margin == (14.9, 15.3)
rule40_q = [r1(y+f) for y,f in zip(yoy[4:], fcfm)]; put("rule_of_40_by_q", rule40_q)
put("fcf_margin_change_pts", r1(fcfm[-1]-fcfm[0]))
put("gaap_op_margin_change_pts", r1(gaap_m[-1]-gaap_m[0]))
put("q2_fy26_fy_oi_guide", (214.0, 218.0))
put("fy26_guide_raise_this_q", r1(mids[-1]-mids[-2]))
put("nrr_change_from_trough", nrr[-1]-min(nrr))
put("fy2024_cohort_y2_vs_fy2021_y2", r1((1.47-1.38)*100))
assert payback[-1] == min(payback) and magic[-1] == max(magic)
put("sbc_pct_change_pts", r1(sbc_pct[-1]-sbc_pct[0]))
put("rule_of_40_change_pts", r1(rule40_q[-1]-rule40_q[0]))
put("q3_margin_beat_vs_high_pts", r1(opm[-1]-q3_guide_margin[1]))
put("arr_growth_minus_rev_growth_pts", r1(arr_yoy - yoy[-1]))
prior_record = max(nn[:-1]); put("prior_record_net_new_arr", prior_record); put("record_margin_over_prior", nn[-1]-prior_record)
assert (prior_record, nn[-1]-prior_record) == (66, 17)
assert min(yoy[4:]) == 21.3 and max(yoy[4:]) == 21.7
aug = (1379.0, 1389.0)
put("fy26_aug_guide_yoy", (r1((aug[0]/fy25-1)*100), r1((aug[1]/fy25-1)*100)))
put("fy26_aug_guide_op_margin", (r1(214.0/aug[0]*100), r1(218.0/aug[1]*100)))
put("nrr_rising_quarters", sum(1 for i in range(6,9) if nrr[i] > nrr[i-1]))
assert all(nrr[i] > nrr[i-1] for i in range(6,9)) and nrr[5] == 116
opm9 = [8.1, 9.0, 9.6, 10.4] + opm; put("ng_op_margin_9q", opm9)
fcfm9 = [14.9, 18.8, 16.2, 16.8] + fcfm; put("fcf_margin_9q", fcfm9)
arr_prev4 = [800, 846, 897, 962]
arr_all = arr_prev4 + arr
arr_yoy9 = [r1((arr_all[i+4]/arr_all[i]-1)*100) for i in range(9)]; put("arr_yoy_9q", arr_yoy9)
assert arr_yoy9[-1] == arr_yoy and arr_all[3] == arr_prev
fcf_tot = [r1(o - c) for o, c in zip(ocf, capex)]
assert fcf_tot == fcf
put("operating_cash_flow", ocf); put("capex", capex)
sub_svc = {"Q3 FY25": (sub[4], svc[4], tot[4]), "Q3 FY26": (sub[8], svc[8], tot[8])}
assert all(r1(a+b) == c for a,b,c in sub_svc.values())
put("services_yoy", r1((svc[8]/svc[4]-1)*100)); put("total_rev_yoy", yoy[-1])
put("services_share_q3fy26", r1(svc[8]/tot[8]*100)); put("sub_share_q3fy25", r1(sub[4]/tot[4]*100)); put("services_share_q3fy25", r1(svc[4]/tot[4]*100))
assert r1(sub[8]/tot[8]*100 + svc[8]/tot[8]*100) == 100.0
lt = {"Gross margin": (80.4, "80-82"), "Sales and marketing": (35.8, "28-30"), "Research and development": (19.5, "15-17"), "General and administrative": (8.5, "6-7"), "Operating margin": (16.6, "25-28"), "Free cash flow margin": (21.4, "28-30")}
assert lt["Operating margin"][0] == opm[-1] and lt["Free cash flow margin"][0] == fcfm[-1]
put("long_term_targets", lt)
put("op_margin_gap_to_target_low_pts", r1(25 - opm[-1]))
below = [i for i in range(4, 8) if arr_yoy9[i] < yoy[i]]
assert below == [4, 5, 6, 7] and arr_yoy9[3] < yoy[3] and arr_yoy9[8] > yoy[8]
put("quarters_arr_growth_under_revenue_growth_before_q3fy26", 5)  # Q2 FY25 to Q2 FY26
assert all(arr_yoy9[i] < yoy[i] for i in range(3, 8)) and arr_yoy9[2] > yoy[2]
json.dump(OUT, open(sys.argv[1], "w"), indent=1) if len(sys.argv) > 1 else None
