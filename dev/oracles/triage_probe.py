"""Per-page facts for PDF triage: chars, image coverage, size histogram of the text layer, fonts."""
import sys, collections, json
import pdfplumber
out = {}
for path in sys.argv[1:]:
    rows = []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages[:12]):
            pw, ph = float(page.width), float(page.height)
            chars = page.chars
            imgs = page.images
            cov = 0.0
            for im in imgs:
                x0, x1 = max(0, im["x0"]), min(pw, im["x1"]); t, b = max(0, im["top"]), min(ph, im["bottom"])
                if x1 > x0 and b > t: cov += (x1 - x0) * (b - t)
            cov = round(cov / (pw * ph), 3)
            sizes = collections.Counter(round(float(c["size"])) for c in chars)
            fonts = collections.Counter(c.get("fontname", "?") for c in chars)
            # chars lying inside an image bbox
            inside = 0
            for c in chars:
                for im in imgs:
                    if im["x0"] <= c["x0"] <= im["x1"] and im["top"] <= c["top"] <= im["bottom"]:
                        inside += 1; break
            text = "".join(c["text"] for c in chars[:80])
            rows.append({"page": i + 1, "size_pt": [round(pw), round(ph)], "chars": len(chars), "images": len(imgs),
                         "image_cover": cov, "chars_in_image": inside, "sizes": dict(sizes.most_common(5)),
                         "fonts": dict(fonts.most_common(3)), "sample": text[:60]})
    out[path.split("/")[-1]] = {"pages": n, "rows": rows}
print(json.dumps(out, indent=1))
