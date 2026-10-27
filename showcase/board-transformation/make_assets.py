"""Icons, the invented Corrin mark, and the plant map, written in the skill's SVG subset.
Usage: python3 -I make_assets.py NA_W NA_H EU_W EU_H   (each inset map's solved frame, inches)
The map reads dl/ne_110m_land.geojson (Natural Earth, public domain) as data only."""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"
IMG.mkdir(exist_ok=True)


def svg(view, shapes):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">\n' + "\n".join("  " + s for s in shapes) + "\n</svg>\n"


S = 'fill="none" stroke="color.accent1" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"'


def p(d):
    return f'<path d="{d}" {S}/>'


ICONS = {
    "order": [f'<rect x="11" y="6" width="26" height="36" rx="2" {S}/>', p("M17 14 H31"), p("M17 22 H31"), p("M17 28 H31"), p("M17 34 H25")],
    "check": [p("M24 5 L39 11 V22 C39 32 32 39 24 43 C16 39 9 32 9 22 V11 Z"), p("M17 24 L22 29 L31 19")],
    "tag": [p("M7 7 H23 L42 26 L26 42 L7 23 Z"), f'<circle cx="15" cy="15" r="3" {S}/>'],
    "box": [p("M24 6 L40 14 V34 L24 42 L8 34 V14 Z"), p("M8 14 L24 22 L40 14"), p("M24 22 V42")],
    "truck": [p("M5 13 H29 V33 H5 Z"), p("M29 19 H37 L43 26 V33 H29"),
              f'<circle cx="13" cy="36" r="4" fill="color.surface" stroke="color.accent1" stroke-width="3"/>',
              f'<circle cx="35" cy="36" r="4" fill="color.surface" stroke="color.accent1" stroke-width="3"/>'],
    "invoice": [p("M12 5 H36 V43 L32 40 L28 43 L24 40 L20 43 L16 40 L12 43 Z"), p("M17 14 H31"), p("M17 21 H31"), p("M17 28 H26")],
    "clock": [f'<circle cx="24" cy="24" r="18" {S}/>', p("M24 13 V24 L31 29")],
    "cash": [f'<rect x="5" y="13" width="38" height="22" rx="3" {S}/>', f'<circle cx="24" cy="24" r="5" {S}/>'],
    "bars": [p("M7 41 H41"), f'<rect x="10" y="28" width="6" height="9" {S}/>', f'<rect x="21" y="19" width="6" height="18" {S}/>',
             f'<rect x="32" y="9" width="6" height="28" {S}/>'],
    "trend": [p("M6 36 L18 24 L26 30 L42 12"), p("M33 12 H42 V21")],
    "factory": [p("M6 42 V22 L16 28 V22 L26 28 V22 L36 28 V9 H42 V42 Z"), p("M13 35 H17"), p("M23 35 H27"), p("M33 35 H37")],
    "people": [f'<circle cx="18" cy="16" r="6" {S}/>', p("M7 40 C7 31 12 27 18 27 C24 27 29 31 29 40"),
               f'<circle cx="33" cy="18" r="5" {S}/>', p("M31 28 C37 28 41 32 41 39")],
}
for name, shapes in ICONS.items():
    (IMG / f"{name}.svg").write_text(svg("0 0 48 48", shapes))

# the invented Corrin Medical mark: a petrol C around an orange core
a = math.radians(40)
x1, y1, y2 = 50 + 34 * math.cos(a), 50 - 34 * math.sin(a), 50 + 34 * math.sin(a)
(IMG / "corrin-mark.svg").write_text(svg("0 0 100 100", [
    f'<path d="M{x1:.2f} {y1:.2f} A34 34 0 1 0 {x1:.2f} {y2:.2f}" fill="none" stroke="color.accent1" stroke-width="15" stroke-linecap="round"/>',
    '<circle cx="73" cy="50" r="9" fill="color.emphasis" stroke="none"/>']))

def clip(poly, xmin, ymin, xmax, ymax):
    def run(pts, inside, cut):
        out = []
        for i in range(len(pts)):
            cur, prev = pts[i], pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
        return out
    def ix(p0, p1, x):
        t = (x - p0[0]) / (p1[0] - p0[0]); return (x, p0[1] + t * (p1[1] - p0[1]))
    def iy(p0, p1, y):
        t = (y - p0[1]) / (p1[1] - p0[1]); return (p0[0] + t * (p1[0] - p0[0]), y)
    pts = poly
    for inside, cut in ((lambda q: q[0] >= xmin, lambda a, b: ix(a, b, xmin)), (lambda q: q[0] <= xmax, lambda a, b: ix(a, b, xmax)),
                        (lambda q: q[1] >= ymin, lambda a, b: iy(a, b, ymin)), (lambda q: q[1] <= ymax, lambda a, b: iy(a, b, ymax))):
        if not pts:
            break
        pts = run(pts, inside, cut)
    return pts


def simplify(pts, tol):
    if len(pts) < 3:
        return pts
    def dist(p, a, b):
        if a == b:
            return math.dist(p, a)
        return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / math.dist(a, b)
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = dist(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)
    return [pts[0], pts[-1]]


# ---- the plant maps: two insets, North America and Europe ------------------------------------
# Each inset is drawn at its frame's own aspect, so the picture fills the frame and a site's
# fraction of the frame is its fraction of the picture. Sites are not drawn here: the deck
# places each as a mark with its name, so dot and name are one system.
na_w, na_h, eu_w, eu_h = (float(v) for v in sys.argv[1:5]) if len(sys.argv) > 4 else (2.6, 2.4, 3.0, 2.4)
INSETS = {
    # name: (lon0, lon1, lat_mid, frame w in, frame h in)
    "na": (-122.0, -78.0, 29.0, na_w, na_h),
    "eu": (-12.0, 21.0, 49.5, eu_w, eu_h),
}
land = json.loads((HERE / "dl2" / "ne_50m_land.geojson").read_text())
lakes = json.loads((HERE / "dl2" / "ne_50m_lakes.geojson").read_text())
data = json.loads((HERE / "data.json").read_text())
SITE_INSET = {1: "na", 2: "na", 3: "na", 4: "na", 5: "eu", 6: "eu", 7: "eu"}
MOVES = [(2, 1), (2, 3), (6, 7)]
MARK_IN = 0.17                      # a site mark's diameter on the page, inches
out = {}
for name, (lon0, lon1, lat_mid, fw, fh) in INSETS.items():
    K = math.cos(math.radians(lat_mid))
    w = (lon1 - lon0) * K
    h = w * fh / fw
    lat1 = lat_mid + h / 2
    upi = w / fw                     # svg units per inch

    def proj(lon, lat):
        return (lon - lon0) * K, (lat1 - lat)

    def rings_of(coll, min_in):
      rings = []
      for f in coll["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            ring = clip([proj(lon, lat) for lon, lat in poly[0]], 0, 0, w, h)
            if len(ring) < 3:
                continue
            ring = simplify(ring + [ring[0]], 0.01 * upi)
            area = abs(sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring)))) / 2
            if area < (min_in * upi) ** 2 or len(ring) < 4:
                continue
            rings.append(ring)
      return rings
    path = lambda rs: " ".join("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in r[:-1]) + " Z" for r in rs)
    rings = rings_of(land, 0.035)
    lk = rings_of(lakes, 0.07)
    shapes = [f'<path d="{path(rings)}" fill="color.land" stroke="none"/>']
    if lk:
        shapes.append(f'<path d="{path(lk)}" fill="color.surface" stroke="none"/>')
    sw = 0.01 * upi                     # the inset's frame, drawn in the picture so the site marks sit on one element
    shapes.append(f'<rect x="{sw / 2:.3f}" y="{sw / 2:.3f}" width="{w - sw:.3f}" height="{h - sw:.3f}" fill="none" stroke="color.rule" stroke-width="{sw:.3f}"/>')
    pos = {pl[0]: proj(pl[4], pl[3]) for pl in data["PLANTS"] if SITE_INSET[pl[0]] == name}
    for a_, b_ in MOVES:
        if a_ not in pos:
            continue
        (xa, ya), (xb, yb) = pos[a_], pos[b_]
        L = math.dist((xa, ya), (xb, yb))
        ux, uy = (xb - xa) / L, (yb - ya) / L
        r = (MARK_IN / 2 + 0.035) * upi           # clear of the site marks
        head, half = 0.10 * upi, 0.045 * upi
        sx, sy = xa + ux * r, ya + uy * r
        ex, ey = xb - ux * r, yb - uy * r
        bx, by = ex - ux * head, ey - uy * head
        shapes.append(f'<line x1="{sx:.3f}" y1="{sy:.3f}" x2="{bx:.3f}" y2="{by:.3f}" fill="none" stroke="color.emphasis" stroke-width="{0.022 * upi:.3f}"/>')
        nx, ny = -uy, ux
        shapes.append(f'<polygon points="{ex:.3f},{ey:.3f} {bx + nx * half:.3f},{by + ny * half:.3f} {bx - nx * half:.3f},{by - ny * half:.3f}" '
                      f'fill="color.emphasis" stroke="none"/>')
    (IMG / f"map-{name}.svg").write_text(svg(f"0 0 {w:.3f} {h:.3f}", shapes))
    for n, (x, y) in pos.items():
        out[str(n)] = {"inset": name, "x": round(x / w, 5), "y": round(y / h, 5), "dx": round(MARK_IN / fw, 5), "dy": round(MARK_IN / fh, 5)}
    print(name, "units", round(w, 2), round(h, 2), "rings", len(rings), "bytes", (IMG / f"map-{name}.svg").stat().st_size)
(IMG / "plant-map.json").write_text(json.dumps({"frames": {"na": [na_w, na_h], "eu": [eu_w, eu_h]}, "plants": out}, indent=1))
# the key's arrow
(IMG / "key-arrow.svg").write_text(svg("0 0 60 20", ['<line x1="3" y1="10" x2="44" y2="10" fill="none" stroke="color.emphasis" stroke-width="3.5"/>',
                                                    '<polygon points="57,10 43,3 43,17" fill="color.emphasis" stroke="none"/>']))
print(json.dumps(out))
