"""(c) The shared case set: 30 sentences x 3 widths, Arial 9.5 pt (Liberation Sans on both sides)."""

SENTENCES = [
    "Calder trades below its flow control peers on every forward multiple",
    "Enterprise values at the close on 14 August 2026; EBITDA and sales on consensus; medians exclude Calder.",
    "A century-old flow control franchise with an aftermarket annuity attached",
    "Aftermarket mix rose from 38% to 47% of revenue over three years, lifting gross margin by 410 bps.",
    "The installed base of 1.2 million valves generates recurring service revenue of $340 million.",
    "Management guides to mid-single-digit organic growth and 50-100 bps of annual margin expansion.",
    "Long-cycle project awards in LNG, hydrogen-ready pipelines and water re-use underpin the backlog.",
    "Net debt/EBITDA of 2.1x leaves headroom for a bolt-on programme without a rating change.",
    "Pricing actions offset 90% of input-cost inflation in FY25; the residual landed in Q4.",
    "Three of the five strategic buyers screened have announced flow-control acquisitions since 2023.",
    "Supercalifragilisticexpialidocious-grade unbreakable tokens stress the character-break rule here",
    "x",
    "Short line.",
    "EV/EBITDA (CY26E) 9.4x vs peer median 11.8x; EV/Sales (CY26E) 1.9x vs 2.3x.",
    "Revenue growth CY26E of 6.8% sits above the peer median of 4.1% and the subject's own three-year CAGR.",
    "The medians exclude the subject; the quartiles are computed on the eight listed peers only.",
    "Working-capital release of $55m in FY26E reflects inventory normalisation after the FY24 build.",
    "Key risks: customer concentration (top ten at 41%), raw-material pass-through lag, FX translation.",
    "Process timeline: teaser week 1, NDA and CIM weeks 2-3, first-round bids week 6, final bids week 11.",
    "Sources: company filings, consensus estimates, deal team analysis; figures in $ millions unless stated.",
    "Hyphen-heavy copy: well-known, best-in-class, end-to-end, go-to-market, state-of-the-art, re-use.",
    "Numbers and symbols: $1,234.5m; (12.3%); 7.5x; 2026E; +410 bps; -3.2%; 1/4; 50:50; 99.99%.",
    "UPPERCASE KICKER TEXT WITH TRACKING EXPECTATIONS AND NO LOWERCASE AT ALL",
    "Mixed punctuation... ellipses, quotes \"like this\", 'and this', brackets [1], braces {2}, semi;colons.",
    "A very long sentence that keeps going and going so that it must wrap several times in a narrow column and more than once even in the widest column that this case set measures today.",
    "Tabs and  double  spaces  inside  a  sentence  are  kept  as  authored",
    "Trailing spaces at the end of this sentence are free      ",
    "The quick brown fox jumps over the lazy dog while the five boxing wizards jump quickly.",
    "AVAWAY kerning pairs To Ta Te Yo Wa LT AV AW: whole-run shaping, never summed fragments.",
    "Section 2.1(a)(ii) of the SPA caps the warranty basket at 1.0% of the purchase price.",
]
WIDTHS_EMU = [1_500_000, 2_800_000, 5_000_000]
FAMILY, SIZE_PT = "Arial", 9.5
CASES = [(s, w) for s in SENTENCES for w in WIDTHS_EMU]
