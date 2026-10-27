"""Scratch judge: drive gallery.py's geometry pipeline (no render) on the corpus
and diff against deckgen's recorded manifests and skeletons."""
import itertools
import json
import math
import os
import random
import sys
from pathlib import Path

# PPTX_SKILL: the skill under test (default: the repo this file sits in); DECKGEN: the
# deckgen checkout whose recorded manifests are the oracle (default: the working directory)
SKILL = Path(os.environ.get("PPTX_SKILL", Path(__file__).resolve().parents[2] / "skills" / "designing-presentations"))
DECKGEN = Path(os.environ.get("DECKGEN", Path.cwd()))
sys.path.insert(0, str(SKILL / "scripts"))
import gallery as g  # noqa: E402
from extract_style import hungarian_max  # noqa: E402

FIX = DECKGEN / "fixtures" / "gallery"
CORPUS = DECKGEN / "fixtures" / "corpus"

# 1. Hungarian against brute force
random.seed(7)
for trial in range(300):
    n, m = random.randint(1, 5), random.randint(1, 5)
    matrix = [[round(random.random(), 3) for _ in range(m)] for _ in range(n)]
    k = min(n, m)
    rows, cols = list(range(n)), list(range(m))
    best = 0.0
    for rs in itertools.permutations(rows, k):
        for cs in itertools.permutations(cols, k):
            best = max(best, sum(matrix[r][c] for r, c in zip(rs, cs)))
    got = hungarian_max(matrix)
    assert math.isclose(got, best, abs_tol=1e-9), (matrix, got, best)
print("hungarian_max: 300 random matrices up to 5x5 agree with brute force")


def run(name: str, width_px: int = 1920):
    deck = g.join_deck(CORPUS / f"{name}.pptx")
    shown = [s for s in deck.slides if not s.hidden]
    emu_per_px = max(deck.width_emu, deck.height_emu) / width_px
    pad_floor = math.ceil(g.CROP_PAD_MIN_RASTER_PX * emu_per_px)
    found = g.components(deck, shown, g.COMPONENT_GAP_EMU)
    groups = [g.normalized_members(c) for c in found]
    labels = [g.member_labels(c) for c in found]
    boxes = [g.crop_box(c, pad_floor, deck) for c in found]
    subst = [g.is_substantive(c) for c in found]
    survives = [subst[i] and g.is_legible(boxes[i], emu_per_px) for i, c in enumerate(found)]
    clusters = g.leader_clusters(groups, labels=labels, threshold=g.COMPONENT_SIMILARITY_TAU)
    chosen = g.select(found, clusters, groups, labels, lambda i: survives[i], g.GALLERY_POOL_MAX, {})
    unlimited = g.select(found, clusters, groups, labels, lambda i: survives[i], 10**6, {})
    exemplars = g.select_exemplars(shown, g.EXEMPLAR_POOL_MAX)
    families = g.slide_families(shown)
    rec = json.loads((FIX / name / "manifest.json").read_text())
    t = rec["totals"]
    print(f"\n=== {name}: slides {len(deck.slides)} (rec {t['slides']})")
    print(f"components {len(found)} (rec {t['components']}); substantive {sum(subst)}; candidates {sum(survives)} (rec {t['candidates']})")
    print(f"clusters {len(clusters)} (rec {t['clusters']}); showable clusters {len(unlimited)}; crops {len(chosen)} (rec {t['crops']})")
    print(f"families {len(families)}; exemplars {len(exemplars)} (rec {t['exemplars']})")
    # crops side by side
    mine = {(c.component.slide.index, tuple(l.ref for l in c.component.members)): (c, boxes[c.index]) for c in chosen}
    theirs = {(r["source_slide_index"], tuple(r["members"])): r for r in rec["crops"]}
    mismatches = 0
    for key, r in theirs.items():
        if key not in mine:
            print(f"  MISSING in port: {r['gallery_id']} slide {key[0]+1} {r['caption']}")
            mismatches += 1
            continue
        c, box = mine[key]
        rb = r["crop_box_emu"]
        rbox = (rb["left"], rb["top"], rb["width"], rb["height"])
        cap = g.caption(c, box)
        cid = f"comp-{c.cluster+1}"
        diffs = []
        if rbox != box:
            diffs.append(f"box {rbox} vs {box}")
        if cap != r["caption"]:
            diffs.append(f"caption\n      rec: {r['caption']}\n      got: {cap}")
        if cid != r["cluster_id"]:
            diffs.append(f"cluster {r['cluster_id']} vs {cid}")
        if c.occurrences != r["occurrences"]:
            diffs.append(f"occ {r['occurrences']} vs {c.occurrences}")
        if list(c.categories) != r["categories"]:
            diffs.append(f"cat {r['categories']} vs {list(c.categories)}")
        if diffs:
            mismatches += 1
            print(f"  DIFF {r['gallery_id']}: " + "; ".join(diffs))
    for key, (c, box) in mine.items():
        if key not in theirs:
            print(f"  EXTRA in port: slide {key[0]+1} {g.caption(c, box)}")
            mismatches += 1
    print(f"crop rows matching exactly: {len(chosen) - mismatches} of {len(chosen)} (recorded {len(rec['crops'])})")
    # exemplars
    rec_ex = {e["exemplar_id"]: e for e in rec["exemplars"]}
    for fi, slide, size in exemplars:
        eid = f"ex-{fi+1:02d}"
        r = rec_ex.get(eid)
        ok = r is not None and r["source_slide_index"] == slide.index and r["slide_family"] == f"family-{fi+1}"
        print(f"  {eid} slide {slide.index+1} family-{fi+1} size {size}: {'match' if ok else 'DIFF rec ' + str(r)}")
        if r:
            del rec_ex[eid]
    for eid in rec_ex:
        print(f"  MISSING exemplar {eid}: {rec_ex[eid]}")
    # skeletons vs committed
    for sk in sorted((FIX / name / "exemplars").glob("*.skeleton.json")):
        rec_sk = json.loads(sk.read_text())
        slide = next(s for s in deck.slides if s.index == rec_sk["slide_index"])
        mine_sk = g.skeleton(slide, deck)
        if mine_sk == rec_sk:
            print(f"  skeleton {sk.name}: identical ({len(rec_sk['shapes'])} shapes)")
        else:
            a, b = rec_sk["shapes"], mine_sk["shapes"]
            print(f"  skeleton {sk.name}: DIFF rec {len(a)} shapes vs {len(b)}")
            for x, y in zip(a, b):
                if x != y:
                    print("     rec", x)
                    print("     got", y)
    return found, survives, clusters, chosen, unlimited


results = {name: run(name) for name in ("jazz", "keybank", "netflix")}
