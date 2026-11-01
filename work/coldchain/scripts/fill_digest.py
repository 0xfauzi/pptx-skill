import json, sys
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
def R(cand, what, msg, how, marks, ct, ax, vl):
    return {"candidate": cand, "what": what, "message": msg, "how_drawn": how, "marks": marks,
            "chart_or_table": ct, "axis_labels": ax, "value_labels": vl}
LINE_HOW = "thin coloured lines on a white plot, light grey horizontal gridlines, no frame, axis numbers in grey Arial, bold black chart title over a plain unit line; series named by coloured bold labels at the line ends instead of a legend; other cases in grey"
E = {
 1: [R("p001-c1","cover photograph of energy infrastructure in a wide crop with a slanted cut","the report's subject: energy","photo with diagonal white cut, thin blue rule under it","nothing marked",False,False,False)],
 2: [],
 3: [R("p003-c1","picture of report covers and a table of side-case download links, beside a text column","the product is a suite of documents","pasted picture to the right of body text","nothing marked",False,False,False)],
 4: [R("p004-c4","two line charts side by side: past projections against the realised history","past outlooks over- and under-shot the realised series","history in black, past projections in thin grey lines, the latest in blue; labels at line ends; 'historical data series' label in the plot","the latest projection is coloured blue and named at its end; the history is labelled in words inside the plot",True,True,False)],
 5: [R("p005-c1","two-column table: case groups in dark navy cells with white text, their assumptions in light-blue banded cells","what each scenario assumes","navy left column with merged cells per group, alternating pale blue rows on the right, bold 'Low:'/'High:' run-in labels, thin white rules between cells, footnote in italic under it","bold run-in labels mark low and high; no colour emphasis",True,False,False)],
 6: [R("p006-c1","two-column table of policy cases, navy label cells and pale blue description cells","what each policy case assumes","same navy and pale blue table as page 5, single rows, italic disclaimer under it","nothing marked",True,False,False)],
 7: [R("p007-c1","left: stacked horizontal bars of consumption by fuel per case; right: dot strip of each fuel's share across cases with a grey bar for the 2025 value","gas and liquids stay the largest fuels in every case","bars sorted with 2025 on top; fuel legend set as coloured words above the bars; dots shaded by year; grey background bar for the base year","an explanatory callout with a curved arrow says what each dot is; the 2025 bar is labelled in grey text",True,True,False)],
 8: [R("p008-c1","line chart of four sectors 2000 to 2050 with shaded ranges across cases","industrial grows, the rest stay flat",LINE_HOW+"; shaded bands give the range across cases","a dashed vertical line at 2025 labelled '2025' and 'projections' separates history from forecast; series labels at the right end in the series colour",True,True,False)],
 9: [R("p009-c1","left: stacked horizontal bars by transport mode per case; right: gasoline consumption lines","regulation cases change fleet mix and fuel use","bars with mode names as coloured words to the right; lines with labels at the ends; the 2025 bar on top","dashed 2025 line with 'projections'; policy cases coloured, others grey, each named at the line end",True,True,False)],
 10: [R("p010-c1","two line charts of vehicle shares across cases","electric shares rise in every case","percent axis, grey case lines, one coloured policy case","dashed 2025 'projections' line; coloured case named at its end",True,True,False)],
 11: [R("p011-c2","two line charts of electricity consumption across cases","data center load drives growth",LINE_HOW,"dashed 2025 line; the high-demand case in dark red and named in a stacked label block, other cases grey",True,True,False),
      R("p011-c1","line chart by census division with an inset US map shading two divisions","growth concentrates in two divisions","map inset in the plot, divisions coloured to match their lines","the two divisions are coloured and named on the map; the other lines grey",True,True,False)],
 12: [R("p012-c1","left: capacity line chart across cases; right: stacked horizontal bars of generation by source per case","gas, solar and wind grow most",LINE_HOW+"; bars with the source legend as coloured words","dashed 2025 'projections' line; baseline black dashed and named; others grey",True,True,False)],
 13: [R("p013-c1","three line charts side by side: gas production, consumption, exports","gas grows across most cases",LINE_HOW,"dashed 2025 line; coloured cases named by a word block in the third panel",True,True,False)],
 14: [R("p014-c1","three line charts: crude production, crude exports, liquids exports","oil output stays high",LINE_HOW,"dashed 2025 'projections' line; the outlier low case in gold and named",True,True,False)],
 15: [R("p015-c1","one line chart of nuclear generation across cases","nuclear generation is stable",LINE_HOW,"dashed 2025 line; two cases coloured and named at their ends",True,True,False)],
 16: [R("p016-c1","agency logo with tagline and contact links","where to find the full report","centred logo picture over two lines of text with links","nothing marked",False,False,False)],
}
SRC = {4:True,5:False,6:False,7:True,8:True,9:True,10:True,11:True,12:True,13:True,14:True,15:True}
for p in d["pages"]:
    p["exhibits"] = E[p["slide"]]
    has = any(r["chart_or_table"] for r in p["exhibits"])
    p["source_line"] = SRC.get(p["slide"]) if has else None
json.dump(d, open(dst,"w"), indent=1)
