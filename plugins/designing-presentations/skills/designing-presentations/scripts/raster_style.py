#!/usr/bin/env python3
"""Measure what a raster reference can still tell: palette by painted area, chrome by
cross-page pixel agreement, margins by ink extents, line pitch by autocorrelation.

    python3 scripts/raster_style.py ref.pdf --out work/ref/raster [--dpi 100] [--max-pages 40]
    python3 scripts/raster_style.py renders/ --out work/ref/raster --page-emu 9144000x6858000

A PDF is triaged first (ooxml.pdf_triage); only its raster pages are measured, each
cropped to the slide box the triage found (the image inside an EDGAR print, or the page
itself for a scan). A directory of PNGs is measured as given, one page per file, and
--page-emu says what size the pages stand for.

Every value is inference from pixels: the patch it writes (colour roles and margins in
complete_guide.py's own shapes, chrome candidates as notes) carries provenance
raster_inference at confidence <= 0.5, and the report names the dpi, because a 72 dpi
print bounds how finely a size can be read (a 12pt line is 12 px tall). Faces cannot be
read from pixels; the report leaves /typography/families open.

Calibration (keybank.pptx rendered at 100 dpi and re-measured): line pitch over body text modal 14pt over 11
pages, 14.4pt (1.2 x the 12pt body, the explicit lnSpc the reference writes) on 3 of them, so
a body of 11.7pt against 12pt in the file; the modal text-line height is close to the size for
mixed-case Arial lines; chrome rows found at the top rule and bottom rule the OOXML walk
reports; margins within one spacing step of the walk's.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from extract_style import contrast  # noqa: E402
from ooxml import delta_e, pdf_triage  # noqa: E402

EMU_PER_PT = 12700
EMU_PER_INCH = 914400
WORK_WIDTH = 400
"""Colour and chrome run on pages scaled to this width: a 0.1in feature on a 10in page is
4 px, enough to find a rule and cheap enough to compare 50 pages."""
CHROME_AGREEMENT = 0.5
"""A pixel that holds one colour on at least half the pages is furniture, the same bar the
OOXML walk uses for a motif (marks on >= 50% of slides)."""
FULL_SPAN = 0.85
"""A chrome row or column filled across this share of the page is a rule or band."""
MERGE_DELTA_E = 6.0
"""Quantised colours closer than this (CIE76) are one colour: anti-aliasing and JPEG noise
spread a flat fill over neighbours a few units apart."""
INK_LUMA_DROP = 0.25
"""A pixel is ink when its luma (0 to 1) sits this far below the surface's. Asserted, not
measured; the read-back of keybank at 100 dpi it served is in the repository's README.md (ink within 1 unit)."""
CAP_HEIGHT_EM = 0.716
"""Arial and Helvetica cap height; an ink run of a line without descenders is this tall.
Times is 0.66 and Calibri 0.64, so a size read this way carries a 10% band."""
"""A pixel darker than the surface by this much luminance (0..1) is ink for the margin and
line-pitch profiles; lighter fills and pale rules are not text."""


def _hex(rgb: tuple[int, int, int]) -> str:
    return "%02X%02X%02X" % rgb


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _bucket(rgb: tuple[int, int, int], bits: int = 5) -> tuple[int, int, int]:
    shift = 8 - bits
    return (rgb[0] >> shift, rgb[1] >> shift, rgb[2] >> shift)


def _chroma(rgb: tuple[int, int, int]) -> float:
    return (max(rgb) - min(rgb)) / 255.0


# --- page loading -----------------------------------------------------------------------


def pages_from_pdf(pdf: Path, out: Path, dpi: int, max_pages: int | None) -> tuple[list[Path], dict, tuple[int, int]]:
    tri = pdf_triage(str(pdf), max_pages)
    wanted = tri["raster_pages"] or tri["evidence_pages"]
    if max_pages is not None:
        wanted = [p for p in wanted if p <= max_pages]
    box = tri.get("slide_box_pt")
    pages_by_no = {p["page"]: p for p in tri["pages"]}
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for no in wanted:
        stem = out / f"page-{no:03d}"
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(no), "-l", str(no), "-singlefile", str(pdf), str(stem)],
                       check=True, capture_output=True)
        png = stem.with_suffix(".png")
        page = pages_by_no[no]
        page_box = page.get("slide_box_pt") or box
        if page_box and page.get("class") != "raster_only":
            im = Image.open(png)
            sx = im.width / page["width_pt"]
            sy = im.height / page["height_pt"]
            crop = (int(page_box[0] * sx), int(page_box[1] * sy), int(page_box[2] * sx), int(page_box[3] * sy))
            im.crop(crop).save(png)
        paths.append(png)
    if tri.get("slide_size_in"):
        page_emu = (int(tri["slide_size_in"][0] * EMU_PER_INCH), int(tri["slide_size_in"][1] * EMU_PER_INCH))
    elif box:
        page_emu = (int((box[2] - box[0]) * EMU_PER_PT), int((box[3] - box[1]) * EMU_PER_PT))
    else:
        page_emu = (int(tri["modal_page_pt"][0] * EMU_PER_PT), int(tri["modal_page_pt"][1] * EMU_PER_PT))
    return paths, tri, page_emu


def load_pages(paths: list[Path]) -> list[Image.Image]:
    return [Image.open(p).convert("RGB") for p in paths]


# --- palette ----------------------------------------------------------------------------


def palette(pages: list[Image.Image], colors: int = 24) -> list[dict]:
    """Colours by painted area over all pages, merged within MERGE_DELTA_E."""
    small = [im.resize((WORK_WIDTH, max(1, round(im.height * WORK_WIDTH / im.width)))) for im in pages]
    height = sum(im.height for im in small)
    mosaic = Image.new("RGB", (WORK_WIDTH, height))
    y = 0
    for im in small:
        mosaic.paste(im, (0, y))
        y += im.height
    q = mosaic.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = Counter(q.get_flattened_data() if hasattr(q, 'get_flattened_data') else q.getdata())
    entries: list[dict] = []
    for idx, n in counts.most_common():
        rgb = (pal[3 * idx], pal[3 * idx + 1], pal[3 * idx + 2])
        entries.append({"rgb": rgb, "count": n})
    merged: list[dict] = []
    for e in entries:
        for m in merged:
            if delta_e(_hex(e["rgb"]), _hex(m["rgb"])) < MERGE_DELTA_E:
                total = m["count"] + e["count"]
                m["rgb"] = tuple(round((m["rgb"][i] * m["count"] + e["rgb"][i] * e["count"]) / total) for i in range(3))
                m["count"] = total
                break
        else:
            merged.append(dict(e))
    total = sum(m["count"] for m in merged) or 1
    for m in merged:
        m["hex"] = _hex(m["rgb"])
        m["share"] = round(m["count"] / total, 4)
        m["chroma"] = round(_chroma(m["rgb"]), 3)
    merged.sort(key=lambda m: -m["share"])
    return merged


def ink_colours(pages: list[Image.Image], surface_hex: str) -> list[dict]:
    """Text ink is a small share of painted area and anti-aliasing spreads it over grey
    levels, so median cut never gives it a bin (measured on keybank: no 000000 entry in a
    24-colour palette of pages whose text is black). The ink is the modal 5-bit colour among
    pixels at least INK_LUMA_DROP darker than the surface, taken at full resolution where
    glyph cores keep their colour; a second cluster at a different luminance is the muted ink."""
    surf = _luma(tuple(int(surface_hex[i:i + 2], 16) for i in (0, 2, 4)))
    buckets: Counter = Counter()
    sums: dict[tuple[int, int, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for im in pages:
        px = im.load()
        step = max(1, im.width // 1100)
        for y in range(0, im.height, step):
            for x in range(0, im.width, step):
                rgb = px[x, y]
                if _luma(rgb) <= surf - INK_LUMA_DROP and _chroma(rgb) < 0.25:
                    b = _bucket(rgb)
                    buckets[b] += 1
                    acc = sums[b]
                    acc[0] += rgb[0]
                    acc[1] += rgb[1]
                    acc[2] += rgb[2]
                    acc[3] += 1
    total = sum(buckets.values()) or 1
    out = []
    for b, n in buckets.most_common(12):
        acc = sums[b]
        rgb = (round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]))
        out.append({"hex": _hex(rgb), "share_of_dark": round(n / total, 3), "luma": round(_luma(rgb), 3)})
    return out


def colour_roles(pal: list[dict], inks: list[dict]) -> dict:
    surface = pal[0]
    roles: dict[str, dict] = {"color.surface": {"hex": surface["hex"], "share": surface["share"]}}
    if inks:
        roles["color.ink"] = {"hex": inks[0]["hex"], "share": inks[0]["share_of_dark"], "basis": "modal dark pixel colour"}
        lighter = [c for c in inks[1:] if c["luma"] >= inks[0]["luma"] + 0.12 and contrast(c["hex"], surface["hex"]) >= 3.0]
        if lighter:
            roles["color.ink_muted"] = {"hex": lighter[0]["hex"], "share": lighter[0]["share_of_dark"], "basis": "second dark cluster"}
    accents = [c for c in pal[1:] if c["chroma"] >= 0.25 and c["share"] >= 0.002]
    for i, c in enumerate(accents[:4]):
        roles[f"color.accent{i + 1}"] = {"hex": c["hex"], "share": c["share"]}
    light = [c for c in pal[1:] if c["chroma"] < 0.15 and contrast(c["hex"], surface["hex"]) < 2.0 and c["share"] >= 0.01]
    if light:
        roles["color.surface_alt"] = {"hex": light[0]["hex"], "share": light[0]["share"], "basis": "largest light neutral fill"}
    return roles


# --- chrome by cross-page agreement ------------------------------------------------------


def chrome_mask(pages: list[Image.Image], surface_hex: str) -> tuple[list[list[int]], dict]:
    """1 where at least CHROME_AGREEMENT of the pages hold one colour that is not the surface."""
    w = WORK_WIDTH
    h = max(1, round(pages[0].height * w / pages[0].width))
    small = [im.resize((w, h)).load() for im in pages]
    surf = _bucket(tuple(int(surface_hex[i:i + 2], 16) for i in (0, 2, 4)))
    mask = [[0] * w for _ in range(h)]
    colour: dict[tuple[int, int], tuple[int, int, int]] = {}
    n = len(pages)
    for y in range(h):
        for x in range(w):
            votes: Counter = Counter()
            for px in small:
                votes[_bucket(px[x, y])] += 1
            b, k = votes.most_common(1)[0]
            if b != surf and k / n >= CHROME_AGREEMENT:
                mask[y][x] = 1
                colour[(x, y)] = tuple(v << 3 for v in b)
    return mask, {"width": w, "height": h, "colour": colour}


def _box_samples(pages: list[Image.Image], box_px: tuple[float, float, float, float], w: int, h: int) -> list[tuple[int, int, int]]:
    """Full-resolution pixels under a chrome box (mask coordinates), from up to eight pages."""
    samples: list[tuple[int, int, int]] = []
    for im in pages[: min(len(pages), 8)]:
        sx, sy = im.width / w, im.height / h
        px = im.load()
        x0, y0, x1, y1 = (max(0, int(box_px[0] * sx)), max(0, int(box_px[1] * sy)), min(im.width, int(math.ceil(box_px[2] * sx)) + 1),
                          min(im.height, int(math.ceil(box_px[3] * sy)) + 1))
        for y in range(y0, y1):
            for x in range(x0, x1, max(1, (x1 - x0) // 200)):
                samples.append(px[x, y])
    return samples


def _modal_hex(samples: list[tuple[int, int, int]]) -> str:
    bucket = Counter(_bucket(c) for c in samples).most_common(1)[0][0]
    members = [c for c in samples if _bucket(c) == bucket]
    return _hex(tuple(round(sum(c[i] for c in members) / len(members)) for i in range(3)))


def darkest_colour(pages: list[Image.Image], box_px: tuple[float, float, float, float], w: int, h: int) -> str:
    """Modal colour of the darkest fifth of the pixels under a chrome box, at full resolution:
    a 0.75pt rule is one anti-aliased pixel row at 100 dpi, so a mean would be a blend. For a
    rule or a mark's ink only: under a band the darkest fifth is the text set on it."""
    samples = _box_samples(pages, box_px, w, h)
    if not samples:
        return "000000"
    samples.sort(key=_luma)
    return _modal_hex(samples[: max(1, len(samples) // 5)])


def fill_colour(pages: list[Image.Image], box_px: tuple[float, float, float, float], w: int, h: int) -> str:
    """A band's fill: the modal colour of all its pixels at full resolution (what covers most
    of it), the bucket refined by the mean of its members."""
    samples = _box_samples(pages, box_px, w, h)
    return _modal_hex(samples) if samples else "000000"


def chrome_entries(mask: list[list[int]], meta: dict, page_emu: tuple[int, int], pages: list[Image.Image]) -> list[dict]:
    w, h = meta["width"], meta["height"]
    sx, sy = page_emu[0] / w, page_emu[1] / h
    entries: list[dict] = []
    used = [[0] * w for _ in range(h)]
    # full-span rows -> rules and bands
    rows = [sum(mask[y]) / w for y in range(h)]
    y = 0
    while y < h:
        if rows[y] >= FULL_SPAN:
            y0 = y
            while y < h and rows[y] >= FULL_SPAN:
                y += 1
            colours = Counter(meta["colour"].get((x, yy)) for yy in range(y0, y) for x in range(w) if mask[yy][x])
            hexes = _hex(colours.most_common(1)[0][0])
            height_emu = int((y - y0) * sy)
            kind = "rule" if (y - y0) <= max(2, h * 0.01) else "band"
            colour_of = darkest_colour if kind == "rule" else fill_colour
            entries.append({"kind": kind, "orientation": "horizontal", "box_emu": [0, int(y0 * sy), page_emu[0], height_emu],
                            "hex": colour_of(pages, (0, y0, w, y), w, h), "hex_bucket": hexes,
                            "anchor": "top" if y0 < h / 2 else "bottom"})
            for yy in range(y0, y):
                for x in range(w):
                    used[yy][x] = 1
        else:
            y += 1
    cols = [sum(mask[y][x] for y in range(h)) / h for x in range(w)]
    x = 0
    while x < w:
        if cols[x] >= FULL_SPAN:
            x0 = x
            while x < w and cols[x] >= FULL_SPAN:
                x += 1
            colours = Counter(meta["colour"].get((xx, y)) for y in range(h) for xx in range(x0, x) if mask[y][xx])
            hexes = _hex(colours.most_common(1)[0][0])
            kind = "rule" if (x - x0) <= max(2, w * 0.01) else "band"
            colour_of = darkest_colour if kind == "rule" else fill_colour
            entries.append({"kind": kind, "orientation": "vertical", "box_emu": [int(x0 * sx), 0, int((x - x0) * sx), page_emu[1]],
                            "hex": colour_of(pages, (x0, 0, x, h), w, h), "hex_bucket": hexes,
                            "anchor": "left" if x0 < w / 2 else "right"})
            for y in range(h):
                for xx in range(x0, x):
                    used[y][xx] = 1
        else:
            x += 1
    # remaining components -> blocks (logo, page number area, labels)
    seen = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if mask[y][x] and not used[y][x] and not seen[y][x]:
                stack = [(x, y)]
                seen[y][x] = 1
                xs, ys, cols_c = [], [], Counter()
                while stack:
                    cx, cy = stack.pop()
                    xs.append(cx)
                    ys.append(cy)
                    cols_c[meta["colour"].get((cx, cy))] += 1
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1), (cx + 1, cy + 1), (cx - 1, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not used[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = 1
                            stack.append((nx, ny))
                if len(xs) < 12:
                    continue
                x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
                anchor_v = "top" if (y0 + y1) / 2 < h / 2 else "bottom"
                anchor_h = "left" if (x0 + x1) / 2 < w / 2 else "right"
                entries.append({"kind": "block", "box_emu": [int(x0 * sx), int(y0 * sy), int((x1 - x0) * sx), int((y1 - y0) * sy)],
                                "hex": darkest_colour(pages, (x0, y0, x1, y1), w, h), "hex_bucket": _hex(cols_c.most_common(1)[0][0]),
                                "anchor": f"{anchor_v}_{anchor_h}", "pixels": len(xs)})
    return entries


# --- margins and line pitch ----------------------------------------------------------------


def ink_profiles(im: Image.Image, surface_hex: str, mask: list[list[int]] | None, width: int) -> tuple[list[int], list[int], int, int]:
    """Row and column counts of ink pixels (darker than the surface by INK_LUMA_DROP), with
    chrome pixels removed. Returns (rows, cols, w, h) at the given working width."""
    w = width
    h = max(1, round(im.height * w / im.width))
    px = im.resize((w, h)).convert("L").load()
    surf = _luma(tuple(int(surface_hex[i:i + 2], 16) for i in (0, 2, 4)))
    cutoff = (surf - INK_LUMA_DROP) * 255
    rows = [0] * h
    cols = [0] * w
    mh = len(mask) if mask else 0
    mw = len(mask[0]) if mask else 0
    for y in range(h):
        my = int(y * mh / h) if mh else 0
        for x in range(w):
            if px[x, y] < cutoff:
                if mask and mask[my][int(x * mw / w)]:
                    continue
                rows[y] += 1
                cols[x] += 1
    return rows, cols, w, h


def margins(pages: list[Image.Image], surface_hex: str, mask: list[list[int]], page_emu: tuple[int, int]) -> dict:
    per_side: dict[str, list[int]] = defaultdict(list)
    for im in pages:
        rows, cols, w, h = ink_profiles(im, surface_hex, mask, WORK_WIDTH)
        sx, sy = page_emu[0] / w, page_emu[1] / h
        tx = max(2, int(0.004 * h * w / 100))  # a column needs a few ink pixels before it counts
        xs = [x for x in range(w) if cols[x] >= tx]
        ys = [y for y in range(h) if rows[y] >= tx]
        if not xs or not ys:
            continue
        per_side["left"].append(int(xs[0] * sx))
        per_side["right"].append(int((w - 1 - xs[-1]) * sx))
        per_side["top"].append(int(ys[0] * sy))
        per_side["bottom"].append(int((h - 1 - ys[-1]) * sy))
    out = {}
    tol = 6 * EMU_PER_PT
    for side, vals in per_side.items():
        vals.sort()
        best, best_n = vals[0], 0
        for v in vals:  # the modal cluster within 6pt, as the OOXML extractor does
            n = sum(1 for u in vals if abs(u - v) <= tol)
            if n > best_n:
                best, best_n = v, n
        cluster = sorted(u for u in vals if abs(u - best) <= tol)
        out[side] = {"emu": cluster[len(cluster) // 2], "pages": best_n, "min_emu": vals[0], "median_emu": vals[len(vals) // 2]}
    return out


def line_pitch(pages: list[Image.Image], surface_hex: str, mask: list[list[int]], page_emu: tuple[int, int], dpi: int) -> dict:
    """Dominant vertical period of the ink row profile inside the margins, per page, then the
    modal pitch; plus the histogram of ink-run heights (text lines when they stand apart)."""
    pitches: list[float] = []
    heights: Counter = Counter()
    for im in pages:
        w = im.width
        rows, _cols, w, h = ink_profiles(im, surface_hex, mask, w)
        pt_per_px = 72.0 / dpi
        binary = [1 if r >= 0.02 * w else 0 for r in rows]
        # runs of ink rows
        y = 0
        while y < h:
            if binary[y]:
                y0 = y
                while y < h and binary[y]:
                    y += 1
                hp = round((y - y0) * pt_per_px)
                if 4 <= hp <= 80:
                    heights[hp] += 1
            else:
                y += 1
        mean = sum(binary) / h if h else 0
        if mean <= 0 or mean >= 0.95:
            continue
        centred = [b - mean for b in binary]
        best_lag, best = None, 0.0
        lo, hi = max(3, int(6 / pt_per_px)), min(h // 2, int(60 / pt_per_px))
        prev = None
        for lag in range(lo, hi):
            ac = sum(centred[i] * centred[i + lag] for i in range(h - lag)) / max(1, h - lag)
            if prev is not None and ac > best and ac > prev:
                best_lag, best = lag, ac
            prev = ac
        if best_lag:
            pitches.append(round(best_lag * pt_per_px, 1))
    modal = Counter(round(p) for p in pitches).most_common(1)[0][0] if pitches else None
    # a text line without descenders is cap height tall: 0.716 em for Arial and Helvetica,
    # 0.66 for Times (measured on keybank's render: 9pt runs for the 12pt body, 18pt for 24pt titles)
    sizes = {h: round(h / CAP_HEIGHT_EM, 1) for h in heights}
    return {"pitch_pt_modal": modal, "pitch_pt_per_page": pitches, "line_heights_pt": dict(sorted(heights.items())),
            "size_estimates_pt_by_run_height": dict(sorted(sizes.items())),
            "body_size_pt_estimate": round(modal / 1.2, 1) if modal else None,
            "basis": "pitch / 1.2 (the explicit line spacing the pptx corpus writes; confidence 0.4)"}


# --- main ------------------------------------------------------------------------------------


def measure(pages: list[Image.Image], page_emu: tuple[int, int], dpi: int) -> dict:
    pal = palette(pages)
    inks = ink_colours(pages, pal[0]["hex"])
    roles = colour_roles(pal, inks)
    mask, meta = chrome_mask(pages, roles["color.surface"]["hex"])
    chrome = chrome_entries(mask, meta, page_emu, pages)
    marg = margins(pages, roles["color.surface"]["hex"], mask, page_emu)
    pitch = line_pitch(pages, roles["color.surface"]["hex"], mask, page_emu, dpi)
    return {"pages": len(pages), "dpi": dpi, "page_emu": list(page_emu), "palette": pal[:16], "dark_clusters": inks, "color_roles": roles, "chrome": chrome,
            "margins": marg, "line_pitch": pitch, "mask": (mask, meta)}


MARGIN_SIDES = ("left", "right", "top", "bottom")


def patch_from(m: dict) -> dict:
    """The addresses complete_guide.py accepts as measured here, in its own shapes: colour
    roles, and the margins when all four sides carry ink (a side with none is left to you).
    Chrome is not in the patch: a pixel component is not yet a chrome entry (which kind it is,
    its text and text style, the pages it is on are read off the page images), so the
    candidates are listed in /notes/raster_chrome and raster.json for you to write /chrome."""
    patch: dict = {}
    for role, spec in m["color_roles"].items():
        patch[f"/color/roles/{role}"] = {"hex": spec["hex"], "provenance": "raster_inference", "confidence": 0.5,
                                         "why": f"raster_inference: {spec['share']:.1%} of painted area at {m['dpi']} dpi"}
    if m["margins"] and set(m["margins"]) == set(MARGIN_SIDES):
        patch["/spacing/margins"] = {side: {"emu": int(v["emu"]), "provenance": "raster_inference", "confidence": 0.5,
                                            "why": f"raster_inference: ink extents on {v['pages']} of {m['pages']} pages"}
                                     for side, v in m["margins"].items()}
    elif m["margins"]:
        patch["/notes/raster_margins"] = (f"raster_style measured margins on {sorted(m['margins'])} only (a side with no ink on any page is "
                                          f"not measured): {({k: v['emu'] for k, v in m['margins'].items()})} EMU; answer /spacing/margins yourself")
    if m["chrome"]:
        patch["/notes/raster_chrome"] = ("raster_style chrome candidates (raster.json chrome, chrome-mask.png), not chrome entries: "
                                         + "; ".join(f"{c['kind']} {c.get('anchor')} box_emu {c['box_emu']} hex {c['hex']}" for c in m["chrome"][:12])
                                         + ("; ..." if len(m["chrome"]) > 12 else "") + ". Write /chrome in its own shape from the page images")
    est = m["line_pitch"].get("body_size_pt_estimate")
    if est:
        patch["/notes/raster_body_size"] = (f"raster_style: body size estimate {est}pt from a {m['line_pitch']['pitch_pt_modal']}pt line pitch "
                                            f"(confidence 0.4; set /typography/roles/type.body yourself after looking at the pages)")
    return patch


def report(m: dict, source: str) -> str:
    out = [f"# Raster evidence: {source}", "", f"{m['pages']} pages at {m['dpi']} px per slide inch, slide {m['page_emu'][0] / EMU_PER_INCH:.2f} x {m['page_emu'][1] / EMU_PER_INCH:.2f} in.",
           m.get("resolution_note", ""),
           "Every value here is inference from pixels (provenance raster_inference, confidence <= 0.5). Faces cannot be read from pixels.", "",
           "## Palette by painted area", "", "| hex | share | chroma |", "|---|---|---|"]
    out += [f"| {c['hex']} | {c['share']:.1%} | {c['chroma']} |" for c in m["palette"]]
    out += ["", "## Dark pixel clusters (text ink candidates)", "", "| hex | share of dark pixels | luma |", "|---|---|---|"]
    out += [f"| {c['hex']} | {c['share_of_dark']:.1%} | {c['luma']} |" for c in m["dark_clusters"][:6]]
    out += ["", "## Colour roles proposed", "", "| role | hex | share | basis |", "|---|---|---|---|"]
    out += [f"| {r} | {s['hex']} | {s['share']:.1%} | {s.get('basis', 'painted area')} |" for r, s in m["color_roles"].items()]
    out += ["", "## Chrome (one colour on >= 50% of pages)", "", "| kind | anchor | box in | hex |", "|---|---|---|---|"]
    for c in m["chrome"]:
        b = c["box_emu"]
        out.append(f"| {c['kind']} | {c['anchor']} | {b[0] / EMU_PER_INCH:.2f}, {b[1] / EMU_PER_INCH:.2f}, {b[2] / EMU_PER_INCH:.2f} x {b[3] / EMU_PER_INCH:.2f} | {c['hex']} |")
    out += ["", "## Margins (modal cluster within 6pt, chrome excluded)", ""]
    out += [f"- {side}: {v['emu'] / EMU_PER_INCH:.2f} in on {v['pages']} pages (min {v['min_emu'] / EMU_PER_INCH:.2f}, median {v['median_emu'] / EMU_PER_INCH:.2f})" for side, v in m["margins"].items()]
    lp = m["line_pitch"]
    out += ["", "## Line pitch", "", f"Modal pitch {lp['pitch_pt_modal']}pt over {len(lp['pitch_pt_per_page'])} pages: {lp['pitch_pt_per_page']}",
            f"Body size estimate {lp['body_size_pt_estimate']}pt ({lp['basis']})", f"Ink-run heights (pt: count): {lp['line_heights_pt']}",
            f"Sizes those runs imply at cap height {CAP_HEIGHT_EM} em (run height: size): {lp['size_estimates_pt_by_run_height']}", ""]
    out += ["## Still open", "", "- /typography/families: match the letterforms by eye against fc-match candidates; a metric alias keeps fit measurement valid.",
            "- /typography/roles/*: sizes from the line heights above and the pages; weights, case and alignment by eye.",
            "- /composition, /tables, /charts: from the page images and the gallery crops.", ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="a PDF, or a directory of page PNGs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--page-emu", default=None, help="WxH in EMU for a PNG directory (a PDF carries its own size)")
    args = ap.parse_args(argv)
    import cli
    out = cli.out_path(args.out, "raster folder")
    out.mkdir(parents=True, exist_ok=True)
    src = Path(args.source)
    triage = None
    if src.is_dir():
        paths = sorted(p for p in src.iterdir() if p.suffix.lower() == ".png" and not p.stem.startswith(("grid", "mask")))
        if args.max_pages:
            paths = paths[: args.max_pages]
        if not args.page_emu:
            raise SystemExit("--page-emu WxH is required for a directory of PNGs")
        w, h = (int(v) for v in args.page_emu.lower().split("x"))
        page_emu = (w, h)
        pages = load_pages(paths)
        dpi = round(pages[0].width / (w / EMU_PER_INCH)) if pages else args.dpi
    else:
        paths, triage, page_emu = pages_from_pdf(src, out / "pages", args.dpi, args.max_pages)
        pages = load_pages(paths)
        # pixels per SLIDE inch: a print that scaled the slide by 0.76 shows fewer pixels per slide inch
        dpi = round(pages[0].width / (page_emu[0] / EMU_PER_INCH)) if pages else args.dpi
    if not pages:
        raise SystemExit("no pages to measure")
    m = measure(pages, page_emu, dpi)
    mask, meta = m.pop("mask")
    mask_im = Image.new("L", (meta["width"], meta["height"]), 255)
    px = mask_im.load()
    for y in range(meta["height"]):
        for x in range(meta["width"]):
            if mask[y][x]:
                px[x, y] = 0
    mask_im.save(out / "chrome-mask.png")
    if triage:
        m["triage"] = {k: triage.get(k) for k in ("deck_class", "counts", "raster_pages", "slide_box_pt", "slide_size_in", "size_basis", "print_scale", "effective_dpi", "modal_page_pt")}
        m["resolution_note"] = (f"page size {triage.get('slide_size_in')} in ({triage.get('size_basis')}); rendered at {args.dpi} dpi on a print that scaled it by {triage.get('print_scale')}; the embedded "
                                f"image carries about {triage.get('effective_dpi')} dpi of the print, so one slide point is "
                                f"{dpi / 72:.1f} px and a size read from pixels carries about a {72 / max(dpi, 1) * 2:.1f}pt band")
    (out / "raster.json").write_text(json.dumps(m, indent=1))  # the note above is part of the record
    (out / "raster.patch.json").write_text(json.dumps(patch_from(m), indent=1))
    (out / "raster.md").write_text(report(m, str(src)))
    print(json.dumps({"out": str(out), "pages": m["pages"], "dpi": dpi, "surface": m["color_roles"]["color.surface"]["hex"],
                      "chrome": len(m["chrome"]), "margins": {k: v["emu"] for k, v in m["margins"].items()},
                      "pitch_pt": m["line_pitch"]["pitch_pt_modal"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
