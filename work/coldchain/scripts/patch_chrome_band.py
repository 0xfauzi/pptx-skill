"""Reclassify chrome-1 (a filled 10 x 0.486 in footer bar) from 'rule' to 'band' in the working guide.
Why: extract_style.py tests aspect before fill, so the bar became a 'rule' and the contrast gate
ignored it as backing for the white footer text drawn on it. Everything else is left as extracted."""
import json, sys
p = sys.argv[1]
g = json.load(open(p))
for ch in g["chrome"]:
    if ch["chrome_id"] == "chrome-1":
        assert ch["kind"] == "rule" and ch["fill_hex"] == "0096D7" and ch["box_in"][3] > 0.4
        ch["kind"] = "band"
        ch["patched_by_session"] = "kind rule -> band: filled 0.486 in bar, misclassified by the aspect test (extract_style.py ~l.1535)"
g["chrome_patch_note"] = "chrome-1 reclassified rule -> band after complete_guide; see scripts/patch_chrome_band.py"
json.dump(g, open(p, "w"), indent=1)
print("patched chrome-1")
