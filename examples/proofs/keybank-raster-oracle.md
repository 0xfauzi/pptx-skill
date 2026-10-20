# Raster evidence: /tmp/claude-0/-home-user-deckgen/bb2024fa-587c-54ed-917f-288f1f2efaef/scratchpad/raster/keybank-render

12 pages at 100 dpi, slide 10.00 x 7.50 in.
Every value here is inference from pixels (provenance raster_inference, confidence <= 0.5). Faces cannot be read from pixels.

## Palette by painted area

| hex | share | chroma |
|---|---|---|
| FFFFFF | 78.1% | 0.0 |
| D3D7DA | 5.1% | 0.027 |
| 113D63 | 3.8% | 0.322 |
| 1E4A7F | 2.2% | 0.38 |
| 9BA4AC | 1.6% | 0.067 |
| 8F7374 | 1.5% | 0.11 |
| AFB6BE | 1.5% | 0.059 |
| 818F9D | 1.3% | 0.11 |
| CBC3C2 | 1.2% | 0.035 |
| A29696 | 1.0% | 0.047 |
| 485D72 | 1.0% | 0.165 |
| 56789B | 0.9% | 0.271 |
| 11181E | 0.4% | 0.051 |
| 303B53 | 0.3% | 0.137 |
| 082D51 | 0.2% | 0.286 |
| 113D6D | 0.1% | 0.361 |

## Dark pixel clusters (text ink candidates)

| hex | share of dark pixels | luma |
|---|---|---|
| 010101 | 25.7% | 0.004 |
| ABBAC7 | 4.9% | 0.721 |
| 7E7E7E | 3.5% | 0.494 |
| 141414 | 3.2% | 0.078 |
| 1C1C1C | 2.7% | 0.11 |
| 648099 | 2.6% | 0.486 |

## Colour roles proposed

| role | hex | share | basis |
|---|---|---|---|
| color.surface | FFFFFF | 78.1% | painted area |
| color.ink | 010101 | 25.7% | modal dark pixel colour |
| color.ink_muted | 7E7E7E | 3.5% | second dark cluster |
| color.accent1 | 113D63 | 3.8% | painted area |
| color.accent2 | 1E4A7F | 2.2% | painted area |
| color.accent3 | 56789B | 0.9% | painted area |
| color.surface_alt | D3D7DA | 5.1% | largest light neutral fill |

## Chrome (one colour on >= 50% of pages)

| kind | anchor | box in | hex |
|---|---|---|---|
| rule | top | 0.00, 0.90, 10.00 x 0.05 | 113D63 |
| rule | bottom | 0.00, 6.92, 10.00 x 0.05 | 113D63 |
| block | top_left | 0.00, 0.88, 4.20 x 0.03 | 648099 |
| block | top_left | 0.00, 0.95, 0.17 x 0.40 | 113D63 |
| block | bottom_left | 0.40, 7.10, 1.02 x 0.20 | 113D63 |
| block | bottom_left | 1.50, 7.10, 0.82 x 0.25 | 113D63 |

## Margins (modal cluster within 6pt, chrome excluded)

- left: 0.42 in on 11 pages (min 0.10, median 0.42)
- right: 0.55 in on 8 pages (min 0.33, median 0.55)
- top: 0.47 in on 11 pages (min 0.47, median 0.47)
- bottom: 0.68 in on 4 pages (min 0.17, median 0.75)

## Line pitch

Modal pitch 14pt over 11 pages: [29.5, 14.4, 59.0, 14.4, 9.4, 59.0, 13.0, 13.7, 12.2, 59.0, 14.4]
Body size estimate 11.7pt (pitch / 1.2 (the explicit line spacing the pptx corpus writes; confidence 0.4))
Ink-run heights (pt: count): {4: 16, 5: 6, 6: 12, 7: 8, 8: 4, 9: 44, 10: 1, 11: 6, 12: 6, 13: 1, 14: 1, 17: 9, 18: 3, 19: 5, 23: 1, 29: 1, 30: 1, 48: 12, 49: 9, 54: 1, 55: 3}
Sizes those runs imply at cap height 0.716 em (run height: size): {4: 5.6, 5: 7.0, 6: 8.4, 7: 9.8, 8: 11.2, 9: 12.6, 10: 14.0, 11: 15.4, 12: 16.8, 13: 18.2, 14: 19.6, 17: 23.7, 18: 25.1, 19: 26.5, 23: 32.1, 29: 40.5, 30: 41.9, 48: 67.0, 49: 68.4, 54: 75.4, 55: 76.8}

## Still open

- /typography/families: match the letterforms by eye against fc-match candidates; a metric alias keeps fit measurement valid.
- /typography/roles/*: sizes from the line heights above and the pages; weights, case and alignment by eye.
- /composition, /tables, /charts: from the page images and the gallery crops.
