# Shared pure geometry of the *-o-matic KiCad plugins (no KiCad, no wx; testable alone).
# All values in mm, Y axis points down (as in KiCad). Copied into every plugin folder,
# so each plugin stays self-contained.

import math

EPS = 1e-9


# ---------------------------------------------------------------- vectors

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def length(v):
    return math.hypot(v[0], v[1])


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def unit(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L) if L > EPS else (0.0, 0.0)


def perp(v):
    """Rotate 90 deg (screen: x right, y down -> from 'right' to 'down')."""
    return (-v[1], v[0])


def rot(p, deg, c=(0.0, 0.0)):
    a = math.radians(deg)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a), c[1] + x * math.sin(a) + y * math.cos(a))


def key(p):
    """Point key for connectivity (0.1 um grid; KiCad works in nm)."""
    return (int(round(p[0] * 1e4)), int(round(p[1] * 1e4)))


def line_cross(p, d, q, e):
    """Intersection of lines p + t d and q + s e -> (t, s) or None when parallel."""
    den = cross(d, e)
    if abs(den) < 1e-12:
        return None
    w = sub(q, p)
    return cross(w, e) / den, cross(w, d) / den


# ---------------------------------------------------------------- distances

def pt_seg(p, a, b):
    ab = sub(b, a)
    L2 = dot(ab, ab)
    if L2 < 1e-18:
        return dist(p, a)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / L2))
    return dist(p, add(a, mul(ab, t)))


def _orient(a, b, c):
    return cross(sub(b, a), sub(c, a))


def seg_seg(a, b, c, d):
    """Distance between segments ab and cd (0 if they cross)."""
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def inside(p, poly):
    c = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > p[1]) != (y1 > p[1]):
            if p[0] < x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0):
                c = not c
    return c


def seg_poly(a, b, poly):
    if inside(a, poly) or inside(b, poly):
        return 0.0
    return min(seg_seg(a, b, p, q) for p, q in zip(poly, poly[1:] + poly[:1]))


def pt_poly(p, poly):
    """Distance from a point to a polygon (0 inside)."""
    if inside(p, poly):
        return 0.0
    return min(pt_seg(p, a, b) for a, b in zip(poly, poly[1:] + poly[:1]))


def poly_poly(P, Q):
    """Distance between two polygons (0 if they overlap)."""
    if inside(P[0], Q) or inside(Q[0], P):
        return 0.0
    best = float("inf")
    for a, b in zip(P, P[1:] + P[:1]):
        for c, d in zip(Q, Q[1:] + Q[:1]):
            best = min(best, seg_seg(a, b, c, d))
            if best == 0.0:
                return 0.0
    return best


def rect_poly(c, w, h, deg=0.0):
    """Corners of a w x h rectangle centred at c, rotated by deg (KiCad: CCW on screen)."""
    a = -math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        out.append((c[0] + dx * ca - dy * sa, c[1] + dx * sa + dy * ca))
    return out


def bbox(points, grow=0.0):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)


def arc_points(start, mid, end, n=8):
    """Points along the circular arc start -> mid -> end."""
    c = circle_center(start, mid, end)
    if c is None:
        return [start, end]
    r = dist(start, c)
    t0, tm, t1 = (math.atan2(q[1] - c[1], q[0] - c[0]) for q in (start, mid, end))
    sweep = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > sweep:
        sweep -= 2 * math.pi
    return [(c[0] + r * math.cos(t0 + sweep * i / n), c[1] + r * math.sin(t0 + sweep * i / n))
            for i in range(n + 1)]


def circle_center(a, m, b):
    (ax, ay), (mx, my), (bx, by) = a, m, b
    d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (my - by) + (mx * mx + my * my) * (by - ay) + (bx * bx + by * by) * (ay - my)) / d
    uy = ((ax * ax + ay * ay) * (bx - mx) + (mx * mx + my * my) * (ax - bx) + (bx * bx + by * by) * (mx - ax)) / d
    return (ux, uy)


# ---------------------------------------------------------------- copper obstacles

class Obstacle:
    """Board copper: kind 'seg' (a, b, half width), 'circle' (c, r) or 'poly' (points).
    layer None = all copper layers (through vias / holes). id = the board item."""
    __slots__ = ("kind", "data", "net", "layer", "id", "bbox", "clr")

    def __init__(self, kind, data, net, layer, id=None, clr=0.0):
        self.kind, self.data, self.net, self.layer, self.id, self.clr = kind, data, net, layer, id, clr
        if kind == "seg":
            a, b, h = data
            self.bbox = (min(a[0], b[0]) - h, min(a[1], b[1]) - h, max(a[0], b[0]) + h, max(a[1], b[1]) + h)
        elif kind == "circle":
            c, r = data
            self.bbox = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
        else:
            self.bbox = bbox(data)

    def dist_seg(self, a, b):
        """Copper distance from the centre line ab (the caller subtracts its half width)."""
        if self.kind == "seg":
            p, q, h = self.data
            return seg_seg(a, b, p, q) - h
        if self.kind == "circle":
            c, r = self.data
            return pt_seg(c, a, b) - r
        return seg_poly(a, b, self.data)

    def dist_pt(self, p):
        if self.kind == "seg":
            a, b, h = self.data
            return pt_seg(p, a, b) - h
        if self.kind == "circle":
            c, r = self.data
            return dist(p, c) - r
        return pt_poly(p, self.data)


class Grid:
    """Spatial hash of obstacles (cell in mm) for fast neighbourhood queries."""

    def __init__(self, obstacles=(), cell=1.0):
        self.cell = cell
        self.cells = {}
        for o in obstacles:
            self.add(o)

    def add(self, o):
        for c in self._cells(o.bbox):
            self.cells.setdefault(c, []).append(o)

    def _cells(self, bb):
        c = self.cell
        for i in range(int(math.floor(bb[0] / c)), int(math.floor(bb[2] / c)) + 1):
            for j in range(int(math.floor(bb[1] / c)), int(math.floor(bb[3] / c)) + 1):
                yield (i, j)

    def near(self, bb):
        out = set()
        for c in self._cells(bb):
            out.update(self.cells.get(c, ()))
        return out

    def near_seg(self, a, b, r):
        c = self.cell
        L = dist(a, b)
        n = max(1, int(math.ceil(L / (c * 0.5))))
        cells = set()
        for k in range(n + 1):
            x = a[0] + (b[0] - a[0]) * k / n
            y = a[1] + (b[1] - a[1]) * k / n
            for i in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
                for j in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                    cells.add((i, j))
        out = set()
        for cc in cells:
            out.update(self.cells.get(cc, ()))
        return out

    def near_pt(self, p, r):
        return self.near((p[0] - r, p[1] - r, p[0] + r, p[1] + r))


def circle_clear(grid, c, r, net, layer, clr, skip=()):
    """Shortfall [mm] of a copper circle (via) to other nets (0 = clear)."""
    worst = 0.0
    for o in grid.near_pt(c, r + clr + 0.5):
        if o.net == net and net is not None and net >= 0:
            continue
        if o.id in skip or (o.layer is not None and layer is not None and o.layer != layer):
            continue
        need = max(clr, o.clr)
        m = r + need
        bb = o.bbox
        if bb[0] > c[0] + m or bb[2] < c[0] - m or bb[1] > c[1] + m or bb[3] < c[1] - m:
            continue
        short = need - (o.dist_pt(c) - r)
        if short > worst:
            worst = short
    return worst


def seg_clear(grid, a, b, w, net, layer, clr, skip=()):
    """Shortfall [mm] of a track ab of width w to copper of other nets (0 = clear)."""
    worst = 0.0
    r = w / 2.0 + clr + 0.5
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    for o in grid.near_seg(a, b, r):
        if o.net == net and net is not None and net >= 0:
            continue
        if o.id in skip or (o.layer is not None and layer is not None and o.layer != layer):
            continue
        need = max(clr, o.clr)
        m = w / 2.0 + need
        bb = o.bbox
        if bb[0] > x1 + m or bb[2] < x0 - m or bb[1] > y1 + m or bb[3] < y0 - m:
            continue
        short = need - (o.dist_seg(a, b) - w / 2.0)
        if short > worst:
            worst = short
    return worst


# ---------------------------------------------------------------- problems with hints

class Issues:
    """Problems grouped per kind with a hint what to change ("text → hint").
    TEXT = {code: (message, hint)} with {v} = the worst value. add(code, item, value):
    item = a number (shown as 'Items 1-3') or a name, value = number for the message."""

    TEXT = {}
    ITEM = ("Item", "Items")

    def __init__(self, text=None, item=None):
        self.d = {}
        if text:
            self.TEXT = text
        if item:
            self.ITEM = item

    def add(self, code, item=None, value=None):
        e = self.d.setdefault(code, [set(), None])
        if item is not None:
            e[0].add(item)
        if value is not None:
            e[1] = value if e[1] is None else max(e[1], value)

    def __len__(self):
        return len(self.d)

    def __contains__(self, code):
        return code in self.d

    def items(self, code):
        return self.d.get(code, [set(), None])[0]

    def _items(self, items):
        if not items:
            return ""
        nums = sorted(x for x in items if isinstance(x, int))
        names = sorted(str(x) for x in items if not isinstance(x, int))
        runs = []
        if nums:
            a = nums[0]
            for p_, q in zip(nums, nums[1:] + [None]):
                if q != p_ + 1:
                    runs.append(str(a) if a == p_ else "%d–%d" % (a, p_))
                    a = q
        parts = runs + names
        if len(parts) > 8:
            parts = parts[:8] + ["…"]
        word = self.ITEM[0] if len(nums) + len(names) == 1 else self.ITEM[1]
        return word + " " + ", ".join(parts) + ": "

    def text(self):
        out = []
        for code, (items, v) in self.d.items():
            msg, hint = self.TEXT[code]
            v = v or 0.0
            out.append(self._items(items) + msg.format(v=v) + " → " + hint.format(v=v))
        return out


def natural_key(s):
    """'R10' after 'R9': split digits for sorting references."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]
