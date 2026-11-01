import json
d = json.load(open("digest.stub.json"))
T = True
def R(c, what, msg, how, marks, cot=True, ax=False, val=True):
    return dict(candidate=c, what=what, message=msg, how_drawn=how, marks=marks, chart_or_table=cot, axis_labels=ax, value_labels=val)
TBL = "7pt Calibri, no fills except light grey-blue E9EDF2 section bands and a shaded focus row or column, hairline grey row rules, 1pt dark rule under the header and the table bottom, numbers right-aligned, negatives in parentheses"
ex = {
1: [R("p001-c3","two-column fact table: item label in bold, description","what the business is at a glance",TBL+"; labels bold in column one","nothing marked; reference table"),
    R("p001-c4","horizontal bar chart of revenue share by end market, seven bars","44% of revenue is defensive","bars sorted within group, navy for defensive and grey for cyclical, value labels at bar ends, no axis, category labels left","two right brackets group the bars, each labelled with the group name and its share; colour also carries the grouping and the subtitle explains it",ax=True),
    R("p001-c5","small region table with totals","North America is the bulk; Asia Pacific grows fastest",TBL,"fastest CAGR set in blue"),
    R("p001-c6","segment summary table with total row","aftermarket is the high-margin growth segment",TBL,"best and worst values in blue and red text; subtitle does not explain colours, note below does"),
    R("p001-c7","multi-year historical financial table with banded section headers","steady growth and margin expansion",TBL+"; italics for ratio rows, bold totals","budget year in blue, a fall in red, explained in the note line under the table"),
    R("p001-c8","operating KPI table","delivery and pricing are stable",TBL,"one value under threshold in red, explained in subtitle"),
    R("p001-c9","bulleted text panels plus a top-customers table","strengths, risks and diligence findings","bold 8pt panel heads, 8pt bullets; table in the same style","claims stated in bullets with figures; no marks")],
2: [R("p002-c3","stacked column showing the capital stack, one column","equity is the largest layer","three stacked segments, navy, mid blue, grey, labels inside segments with $ and x EBITDA; arrow callout for the thin layer","an arrow callout labels the thin notes segment; no other mark",val=T),
    R("p002-c4","sources of funds table","sponsor equity and TLB fund the deal",TBL,"key tranche amounts in blue"),
    R("p002-c5","uses of funds table",  "purchase of equity dominates uses",TBL,"nothing marked"),
    R("p002-c6","fees and costs table","fees are 3.5% of EV",TBL,"nothing marked"),
    R("p002-c7","pro forma capitalisation table, full width","total leverage 5.75x",TBL+"; shaded total row","total capitalisation row shaded; leverage figure in blue"),
    R("p002-c8","key terms text table","term loan is covenant-lite",TBL,"nothing marked"),
    R("p002-c9","purchase price analysis table, implied multiples against peers","entry multiple under peer medians",TBL,"focus row shaded"),
    R("p002-c10","cash interest table","first-year cash interest by tranche",TBL,"nothing marked"),
    R("p002-c11","ownership table","sponsor owns most",TBL,"nothing marked")],
3: [R("p003-c3","large operating model table with banded sections","revenue and EBITDA grow each forecast year",TBL+"; forecast columns in blue","forecast values in blue, explained in subtitle"),
    R("p003-c4","base vs management plan table","sponsor case under management",TBL,"nothing marked"),
    R("p003-c5","reinvestment table","capex is modest",TBL,"nothing marked"),
    R("p003-c6","key assumptions table","margin assumption rises every year",TBL,"margin row shaded"),
    R("p003-c7","column chart of EBITDA by year, eleven bars","EBITDA grows throughout","history grey, forecast navy, value labels above bars, category labels below, no gridlines, no axis line values","colour splits history from forecast, explained in subtitle",ax=True),
    R("p003-c8","cases compared table, shaded base column","downside returns fall below hurdle",TBL,"base column shaded; downside returns in red")],
4: [R("p004-c3","sponsor returns build-up table","2.56x and 20.7%",TBL,"result rows shaded"),
    R("p004-c4","waterfall bridge of equity value, stacked columns","EBITDA growth creates most of the value","grey start, navy increases, red decreases, values printed above each step, no axis","colours explain direction in subtitle; no other mark",ax=True),
    R("p004-c5","IRR by exit year table","returns by hold period",TBL,"under-hurdle values in red, base cell shaded"),
    R("p004-c6","proceeds by holder table","sponsor takes most exit proceeds",TBL,"total bold"),
    R("p004-c7","break-even inputs table","margin is the most sensitive input",TBL,"cushion column bold"),
    R("p004-c8","sensitivity grid","returns by entry debt and exit multiple",TBL,"base cell shaded, under-hurdle values red, explained under the grid"),
    R("p004-c9","sensitivity grid of IRR by growth and margin","margin matters more than growth",TBL,"base cell shaded and under-hurdle values red, explained in a note under the grid"),
    R("p004-c10","sensitivity grid of IRR by entry and exit multiple","paying more needs multiple expansion",TBL,"base cell shaded and under-hurdle values red, explained in a note under the grid"),
    R("p004-c11","sensitivity grid of MOIC by entry and exit multiple","high entry multiples miss the hurdle",TBL,"base cell shaded and under-hurdle values red, explained in a note under the grid")],
5: [R("p005-c3","clustered column chart, base vs downside leverage by year, with a covenant line","headroom stays above 26%","navy base, red downside, value labels above bars, legend on top, orange covenant line","orange covenant line in legend; a bracket with a label '26.6% headroom' marks the tightest gap",ax=True),
    R("p005-c4","credit statistics table, base and downside","leverage falls in both cases",TBL,"covenant rows in red for downside"),
    R("p005-c5","precedent LBO financings table with statistics block and focus row","proposed terms sit at the median",TBL+"; mean/high/low italic, median bold, focus row shaded with blue text","focus row shaded and blue"),
    R("p005-c6","debt capacity table","proposed debt passes most tests",TBL,"proposed row shaded"),
    R("p005-c7","downside definition table","a sharp one-year volume shock",TBL,"shocks in red"),
    R("p005-c8","rate sensitivity table","returns barely move with rates",TBL,"current column shaded")],
6: [R("p006-c2","horizontal bar chart, four exit routes, MOIC and IRR inside bars","two routes clear the hurdle","navy bars above the hurdle, red below, labels inside bars, dashed orange vertical hurdle line labelled 'Hurdle 2.5x'","orange dashed line with a text label marks the hurdle; colour shows pass and fail, explained in subtitle",ax=True),
    R("p006-c3","horizontal bar chart of reference multiples, seven bars sorted","most references sit above the base exit","grey bars with values inside at the left, category labels left, navy vertical reference line labelled 'Base exit 10.0x'","navy line with label marks the base multiple",ax=True),
    R("p006-c5","exit scenario table with shaded base column","sponsor exit route is the base",TBL,"base column shaded; returns under hurdle in red"),
    R("p006-c6","listed peers trading multiples table with statistics block and focus row","entry multiple vs peer median",TBL+"; mean/high/low italic, median bold, target row shaded with navy bold text","target row shaded; note explains the peer subset"),
    R("p006-c7","precedent transactions table with medians by buyer type","strategic buyers pay more",TBL,"median strategic bold; others italic")],
}
for p in d["pages"]:
    p["exhibits"] = ex[p["slide"]]
    p["source_line"] = True
json.dump(d, open("digest.json","w"), indent=1)
