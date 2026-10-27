# Results of the font evaluations

Machine: Ubuntu 24.04, LibreOffice 24.2.7.2, poppler 24.02.0, fontconfig 2.15.0, the
HarfBuzz text ruler. `unshare -rn` and `strace` were available, so every command ran with
no network and every process was traced.

## Before and after the change

"Before" is the code of the main branch, with the same checks. The script
`scripts/fonts.py` did not exist there, so most checks failed. The checks that passed
before passed because nothing ran: for example, no stand-in was proposed because no report
was made.

| Scenario | Checks that pass before | Checks that pass after |
|---|---|---|
| S1 installed faces | 1 of 3 | 3 of 3 |
| S2 embedded font, embedding allowed | 2 of 8 | 8 of 8 |
| S3 embedded font, restricted | 0 of 7 | 7 of 7 |
| S4 PDF with a subset font only | 0 of 5 | 5 of 5 |
| S5 the user supplies the font | 0 of 5 | 5 of 5 |
| S6 no reference, a face the recipient may lack | 1 of 5 | 5 of 5 |
| S7 no network use; nothing changed outside the work folder | 4 of 4 | 4 of 4 |

Before the change, in S5, the user's font file was in the fonts folder, but LibreOffice
drew the text in Inter. After the change, LibreOffice draws the text in the user's font.

## With each fix removed

We removed each fix from the code, one at a time, and ran all the checks again. Then we
put the fix back. Each removal makes at least one check fail:

| Fix removed | Checks that fail |
|---|---|
| LibreOffice gets the fontconfig configuration of the run | 2: LibreOffice draws the face from the fonts folder (S2, S5) |
| The text ruler reads the files of the fonts folder | 6, in S2, S5 and S6 |
| Extraction reads the fsType | 4, in S3: the restricted font is read as extractable |
| Extraction needs `--licence-confirmed` | 1: extract without the confirmation refuses (S2) |
| A PDF subset is read as missing | 2, in S4 |
| The width of the stand-in is measured against the PDF | 1, in S4 |
| A restricted file in the fonts folder is not used | 1, in S3 |
| Each bold and italic style is checked | 1, in S6 |
| No network call (a call to `socket.getaddrinfo` was added to the report) | 1, in S7: the audit hook logged the call |
| Only the faces of the guide stop the report once a guide exists | 1, in S4 |
| The fontconfig cache goes into the folder of the run | 1, in S7: a cache file was written to the system cache folder |

## The width instrument

To check the width measurement, we measured the test face against a PDF that LibreOffice
drew in that face. With the same glyphs (the base font), the difference is +0.2% over 11
words. With Inter, the difference is +17.0% (10th to 90th percentile of words: +9.0% to
+24.6%). `tools/measure/font_probe.py` makes these measurements again.
