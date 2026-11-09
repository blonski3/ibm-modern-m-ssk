# Pure geometry of stitch-o-matic (no KiCad): where stitching vias go.
#   Fence: rows of vias on one or both sides of selected tracks, at offset O, pitch P.
#   Fill:  a square or hexagonal grid of vias inside selected zones.
#   Ring:  vias along the board outline (or a selected zone outline), inset O.
# Every candidate is then checked: board outline, inside a zone of the net (optional),
# not on a pad, clearance to copper of other nets, hole to hole, spacing between the new
# vias. mm, Y down.

import math

from . import geo

FENCE, FILL, RING = 0, 1, 2
BOTH, RIGHT, LEFT = 0, 1, 2            # side of the track, seen in its direction

TEXT = {
    "close": ("vias are {v:.3f} mm too close to the fenced track (O − D/2 − W/2 < clearance)",
              "raise O"),
    "none": ("no via fits", "a smaller via or pitch, or untick Inside zone (More)"),
    "nozone": ("Inside zone: no zone of this net covers the vias", "untick Inside zone (More), or draw a zone"),
    "nooutline": ("no closed board outline (Edge.Cuts)", "draw the outline, or select a zone"),
    "small": ("pitch {v:.3f} mm is smaller than the via", "raise P"),
}

REASONS = [("clearance", "too close to other copper"), ("pad", "on a pad"), ("hole", "hole to hole"),
           ("spacing", "too close to another new via"), ("outside", "outside the board"),
           ("zone", "outside the zones of the net"), ("path", "too close to the path")]


def issues():
    return geo.Issues(TEXT, ("", ""))


# ---------------------------------------------------------------- paths

class Piece:
    """A selected track: 'seg' a -> b or 'arc' a -> m -> b, width w."""

    def __init__(self, id, kind, a, b, w, m=None):
        self.id, self.kind, self.a, self.b, self.m, self.w = id, kind, a, b, m, w
        self.c = geo.circle_center(a, m, b) if kind == "arc" else None
        if kind == "arc" and self.c is None:
            self.kind = "seg"

    def points(self, step):
        """Points along the centre line, about step apart."""
        if self.kind == "arc":
            r = geo.dist(self.a, self.c)
            pts = geo.arc_points(self.a, self.m, self.b, 2)
            sweep = abs(_sweep(self.a, self.m, self.b, self.c))
            n = max(2, int(math.ceil(sweep * r / step)))
            return geo.arc_points(self.a, self.m, self.b, n) if n > 2 else pts
        L = geo.dist(self.a, self.b)
        n = max(1, int(math.ceil(L / step)))
        return [geo.add(self.a, geo.mul(geo.sub(self.b, self.a), k / n)) for k in range(n + 1)]


def _sweep(a, m, b, c):
    t0, tm, t1 = (math.atan2(q[1] - c[1], q[0] - c[0]) for q in (a, m, b))
    sw = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > sw:
        sw -= 2 * math.pi
    return sw


def chains(pieces):
    """Pieces joined end to end (two ends at one point) -> lists of points along each
    chain in order, sampled every `step` later; here: [[(piece, reversed)], ...]."""
    ends = {}
    for i, p in enumerate(pieces):
        for e, q in ((0, p.a), (1, p.b)):
            ends.setdefault(geo.key(q), []).append((i, e))
    used = [False] * len(pieces)

    def joint(k):
        lst = ends.get(k, ())
        return len(lst) == 2 and lst[0][0] != lst[1][0]

    def walk(i, ent):
        out = []
        cur = i
        while True:
            used[cur] = True
            p = pieces[cur]
            out.append((p, ent == 1))
            q = p.a if ent == 1 else p.b
            k = geo.key(q)
            if not joint(k):
                return out, False
            j, e = [x for x in ends[k] if x[0] != cur][0]
            if used[j]:
                return out, True
            cur, ent = j, e

    res = []
    for i, p in enumerate(pieces):
        if not used[i]:
            for e, q in ((0, p.a), (1, p.b)):
                if not joint(geo.key(q)):
                    res.append(walk(i, e))
                    break
    for i in range(len(pieces)):
        if not used[i]:
            res.append(walk(i, 0))
    return res


def chain_points(chain, step):
    pts = []
    for p, rev in chain:
        q = p.points(step)
        if rev:
            q = q[::-1]
        pts += q if not pts else q[1:]
    return pts


def offset_points(pts, o, closed=False):
    """Points offset by o to the right of the travel direction (negative: left), with
    round joins on the outside of turns; the inside overlaps are removed later by the
    distance test."""
    out = []
    segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if closed else [])
    prev_n = None
    for a, b in segs:
        d = geo.unit(geo.sub(b, a))
        if d == (0.0, 0.0):
            continue
        nn = geo.perp(d)
        if prev_n is not None:
            out += _join(a, prev_n, nn, o)
        out.append(geo.add(a, geo.mul(nn, o)))
        out.append(geo.add(b, geo.mul(nn, o)))
        prev_n = nn
    if closed and out and len(segs) > 1:
        first = geo.perp(geo.unit(geo.sub(segs[0][1], segs[0][0])))
        out += _join(segs[0][0], prev_n, first, o)
        out.append(geo.add(segs[0][0], geo.mul(first, o)))
    return out


def _join(a, n1, n2, o):
    """Round join points around a from normal n1 to n2 (only on the outside)."""
    turn = geo.cross(n1, n2)
    if not (turn * o < 0 or (abs(turn) < 1e-12 and geo.dot(n1, n2) < 0)):
        return []
    a0 = math.atan2(n1[1], n1[0])
    a1 = math.atan2(n2[1], n2[0])
    da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    k = max(1, int(abs(da) * abs(o) / 0.05))
    return [geo.add(a, (math.cos(a0 + da * j / k) * o, math.sin(a0 + da * j / k) * o)) for j in range(1, k)]


def runs(points, keep, step):
    """Split points into runs of kept ones; small jumps (inside corners) are bridged."""
    out, cur = [], []
    last = None
    for p in points:
        if not keep(p):
            continue
        if cur and geo.dist(p, last) > 4 * step + 1e-9:
            out.append(cur)
            cur = []
        if not cur or geo.dist(p, last) > 1e-9:
            cur.append(p)
        last = p
    if cur:
        out.append(cur)
    return out


def along(run, pitch, e0=0.0, e1=0.0, phase=0.0, fit=False, closed=False):
    """Points at pitch along the run (a polyline), from e0 after its start to e1 before
    its end. fit: spread them evenly so the first and last sit exactly at e0 / end - e1
    (closed loop: an even count all round)."""
    if len(run) < 2 or pitch <= 0:
        return []
    pts = run + [run[0]] if closed else run
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + geo.dist(a, b))
    L = cum[-1]
    if closed:
        n = max(3, int(round(L / pitch))) if fit else int(L // pitch)
        if n < 1:
            return []
        st = L / n if fit else pitch
        ss = [(phase + k * st) % L for k in range(n)]
    else:
        span = L - e0 - e1
        if span < -1e-9:
            return []
        if fit:
            n = int(math.ceil(span / pitch - 1e-9)) + 1 if span > 1e-9 else 1
            st = span / (n - 1) if n > 1 else 0.0
            ss = [e0 + k * st for k in range(n)]
            if phase and n > 1:
                ss = [e0 + st / 2.0 + k * st for k in range(n - 1)]
        else:
            ss = []
            s = e0 + phase
            while s <= L - e1 + 1e-9:
                ss.append(s)
                s += pitch
    out = []
    j = 0
    for s in sorted(ss):
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg < 1e-12 else (s - cum[j]) / seg
        a, b = pts[j], pts[j + 1]
        out.append(geo.add(a, geo.mul(geo.sub(b, a), min(1.0, max(0.0, t)))))
    return out


def path_grid(pieces, step):
    """Centre lines for distance tests: straight pieces whole, arcs as the same chords
    the offsets were made from."""
    grid = geo.Grid(cell=1.0)
    for p in pieces:
        pts = p.points(step) if p.kind == "arc" else [p.a, p.b]
        for a, b in zip(pts, pts[1:]):
            grid.add(geo.Obstacle("seg", (a, b, 0.0), 0, None))
    return grid


def dist_to(grid, p, r):
    best = float("inf")
    for o in grid.near_pt(p, r):
        best = min(best, o.dist_pt(p))
    return best


# ---------------------------------------------------------------- candidates

def fence(pieces, s):
    """Candidates [(point, tag)] along the selected tracks."""
    step = min(0.05, s["pitch"] / 8.0)
    pg = path_grid(pieces, step)
    rows = max(1, int(s.get("rows", 1)))
    sides = {BOTH: (1, -1), RIGHT: (1,), LEFT: (-1,)}[s.get("side", BOTH)]
    out = []
    for chain, closed in chains(pieces):
        pts = chain_points(chain, step)
        if len(pts) < 2:
            continue
        for si, sg in enumerate(sides):
            for r in range(rows):
                o = s["offset"] + r * s.get("row_gap", s["pitch"])
                cand = offset_points(pts, sg * o, closed)
                keep = lambda p, o=o: dist_to(pg, p, o + 0.5) >= o - 1e-5
                stag = s.get("stagger") and ((si + r) % 2 == 1)
                rs = runs(cand, keep, step)
                for run in rs:
                    whole = closed and len(rs) == 1
                    ph = s["pitch"] / 2.0 if stag else 0.0
                    for p in along(run, s["pitch"], s.get("end", 0.0), s.get("end", 0.0), ph,
                                   s.get("fit", False), whole):
                        out.append((p, (si, r)))
    return out


def poly_area(poly):
    return 0.5 * sum(geo.cross(a, b) for a, b in zip(poly, poly[1:] + poly[:1]))


def ring(polys, s):
    """Vias inset by O from closed outlines (board edge or zone)."""
    out = []
    step = min(0.1, s["pitch"] / 8.0)
    for poly in polys:
        if len(poly) < 3:
            continue
        pts = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            L = geo.dist(a, b)
            n = max(1, int(math.ceil(L / step)))
            pts += [geo.add(a, geo.mul(geo.sub(b, a), k / n)) for k in range(n)]
        pg = geo.Grid(cell=1.0)
        for a, b in zip(poly, poly[1:] + poly[:1]):
            pg.add(geo.Obstacle("seg", (a, b, 0.0), 0, None))
        o = s["offset"]
        # y down: with a positive shoelace area the inside is on the right of travel
        sg = 1 if poly_area(poly) > 0 else -1
        cand = offset_points(pts, sg * o, closed=True)
        keep = lambda p: geo.inside(p, poly) and dist_to(pg, p, o + 0.5) >= o - 1e-4
        rs = runs(cand, keep, step)
        if len(rs) > 1 and geo.dist(rs[0][0], rs[-1][-1]) <= 4 * step:
            rs[0] = rs[-1] + rs[0]
            rs.pop()
        for run in rs:
            closed = len(rs) == 1 and geo.dist(run[0], run[-1]) <= 4 * step
            for p in along(run, s["pitch"], 0.0, 0.0, 0.0, True, closed):
                out.append((p, (0, 0)))
    return out


def fill(areas, s, radius):
    """Grid points inside areas [(outline, holes)] at least margin + via radius from
    their edges. The grid is on absolute multiples of the pitch (same points every time)."""
    P = s["pitch"]
    out = []
    hexa = s.get("stagger")
    dy = P * math.sqrt(3) / 2.0 if hexa else P
    m = s.get("offset", 0.0) + radius
    for outline, holes in areas:
        if len(outline) < 3:
            continue
        bb = geo.bbox(outline)
        edges = geo.Grid(cell=max(1.0, P))
        for poly in [outline] + list(holes):
            for a, b in zip(poly, poly[1:] + poly[:1]):
                edges.add(geo.Obstacle("seg", (a, b, 0.0), 0, None))
        j0 = int(math.floor(bb[1] / dy))
        j1 = int(math.ceil(bb[3] / dy))
        for j in range(j0, j1 + 1):
            y = j * dy
            sh = P / 2.0 if hexa and j % 2 else 0.0
            i0 = int(math.floor((bb[0] - sh) / P))
            i1 = int(math.ceil((bb[2] - sh) / P))
            for i in range(i0, i1 + 1):
                p = (i * P + sh, y)
                if not geo.inside(p, outline) or any(geo.inside(p, h) for h in holes):
                    continue
                if dist_to(edges, p, m + 0.01) < m - 1e-9:
                    continue
                out.append((p, (0, 0)))
    return out


# ---------------------------------------------------------------- checks

class Rules:
    """What a via must keep away from. copper: geo.Grids of all copper (any net, edge
    included); pads: geo.Grid of pad shapes; holes: geo.Grids of drill circles;
    outlines: closed board outlines (None = do not check); zone: callable(p) -> bool or
    None; path: geo.Grid of the fenced centre lines (fence mode)."""

    def __init__(self, copper=(), pads=None, holes=(), outlines=None, zone=None, h2h=0.25,
                 pad_gap=0.05):
        self.copper, self.pads, self.holes = list(copper), pads, list(holes)
        self.outlines, self.zone = outlines, zone
        self.h2h, self.pad_gap = h2h, pad_gap


def accept(cands, rules, s, net, clr):
    """-> (accepted points, {reason: count})."""
    r = s["d"] / 2.0
    rd = s["drill"] / 2.0
    keep_apart = max(s["d"] + 0.01, s["drill"] + rules.h2h)
    placed = geo.Grid(cell=max(0.5, keep_apart))
    acc = []
    skipped = {}

    def skip(why):
        skipped[why] = skipped.get(why, 0) + 1

    for p, _tag in cands:
        if rules.outlines is not None and not any(geo.inside(p, ol) for ol in rules.outlines):
            skip("outside")
            continue
        if rules.zone is not None and not rules.zone(p):
            skip("zone")
            continue
        if rules.pads is not None and any(o.dist_pt(p) - r < rules.pad_gap
                                          for o in rules.pads.near_pt(p, r + rules.pad_gap + 0.1)):
            skip("pad")
            continue
        if any(geo.circle_clear(gr, p, r, net, None, clr) > 1e-6 for gr in rules.copper):
            skip("clearance")
            continue
        if any(geo.dist(p, o.data[0]) - o.data[1] - rd < rules.h2h - 1e-9
               for gr in rules.holes for o in gr.near_pt(p, rd + rules.h2h + 1.0)):
            skip("hole")
            continue
        if any(geo.dist(p, q.data[0]) < keep_apart - 1e-9 for q in placed.near_pt(p, keep_apart)):
            skip("spacing")
            continue
        placed.add(geo.Obstacle("circle", (p, 0.0), 0, None))
        acc.append(p)
    return acc, skipped


def skipped_text(skipped):
    names = dict(REASONS)
    parts = ["%d %s" % (n, names.get(k, k)) for k, n in sorted(skipped.items(), key=lambda x: -x[1])]
    return ", ".join(parts)


def outline_polys(segs):
    """Closed loops from outline segments [(a, b)] (any order / direction)."""
    ends = {}
    for i, (a, b) in enumerate(segs):
        ends.setdefault(geo.key(a), []).append((i, 0))
        ends.setdefault(geo.key(b), []).append((i, 1))
    used = [False] * len(segs)
    out = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        a, b = segs[i]
        loop = [a]
        cur = b
        ok = False
        for _ in range(len(segs)):
            if geo.key(cur) == geo.key(loop[0]):
                ok = True
                break
            loop.append(cur)
            nxt = [(j, e) for j, e in ends.get(geo.key(cur), ()) if not used[j]]
            if not nxt:
                break
            j, e = nxt[0]
            used[j] = True
            cur = segs[j][1 - e]
        if ok and len(loop) >= 3:
            out.append(loop)
    return out
