# Pure geometry for the spacing-o-matic plugin (no KiCad dependency, testable on its own).
# All values in mm, Y axis points down (as in KiCad). Works for a bus at any angle.
#
# Model: the selected track segments are split into "lanes", one per net: a chain of
# connected, collinear segments that run parallel to the bus direction. The perpendicular
# position of each lane (its offset o along the bus normal n) gives the spacing:
#   pitch = o[k+1] - o[k]          (centre to centre)
#   gap   = pitch - (w[k] + w[k+1]) / 2   (copper edge to copper edge)
# Setting the spacing moves every lane sideways by delta = target - o. The two ends of a
# lane keep the track connected:
#   slide   - the neighbouring segment keeps its angle, its shared end slides along it
#             (the lane end lands where the new lane line crosses the neighbour);
#   jog     - the original end point stays (pad, via, junction, straight continuation) and a
#             45 deg jog joins it to the moved lane;
#   stretch - the neighbour's shared end just moves with the lane (its angle changes);
#   free    - nothing is connected there, the end simply moves.

import math

TOL_DEG = 1.0          # segments within this angle of the bus direction are "parallel"
OFF_TOL = 0.002        # collinear segments of one lane may differ this much in offset [mm]
EPS = 1e-6

ENDS_SLIDE, ENDS_JOG, ENDS_STRETCH = "slide", "jog", "stretch"
KEEP_FIRST, KEEP_CENTER, KEEP_LAST = "first", "center", "last"
MODE_PITCH, MODE_GAP = "pitch", "gap"


class Issues:
    """Problems grouped per kind with a hint what to change ("text → hint").
    add(code, track, value): track = 1-based lane number or None; value = number used by
    the message (the worst one is kept)."""

    TEXT = {
        "one_lane": ("need at least two parallel tracks of different nets",
                     "select the straight parts of two or more tracks"),
        "multi": ("net has several parallel runs in the selection, the longest is used",
                  "select one straight run per net"),
        "gap_clr": ("gap below the netclass clearance ({v:.3f} mm short)",
                    "raise P / G by at least {v:.3f} mm"),
        "overlap": ("tracks overlap ({v:.3f} mm)", "raise P / G"),
        "close": ("closer than the clearance to other copper ({v:.3f} mm short)",
                  "move the bus (S), change P / G or Keep"),
        "short": ("too short for the 45° jogs ({v:.2f} mm missing)",
                  "change less, or set Ends to Stretch"),
        "flip": ("neighbouring segment too short, it would turn around",
                 "change less, or set Ends to 45° jog"),
        "steep": ("neighbour almost parallel, cannot slide, 45° jog used",
                  "fine; Ends: Stretch keeps it without the jog"),
        "apart": ("does not run side by side with its neighbour",
                  "check the selection (spacing measured anyway)"),
    }

    def __init__(self):
        self.d = {}

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

    @staticmethod
    def _items(items):
        if not items:
            return ""
        xs = sorted(items)
        runs, a = [], xs[0]
        for p_, q in zip(xs, xs[1:] + [None]):
            if q != p_ + 1:
                runs.append(str(a) if a == p_ else "%d–%d" % (a, p_))
                a = q
        return ("Track " if len(xs) == 1 else "Tracks ") + ", ".join(runs) + ": "

    def text(self):
        out = []
        for code, (items, v) in self.d.items():
            msg, hint = self.TEXT[code]
            v = v or 0.0
            out.append(self._items(items) + msg.format(v=v) + " → " + hint.format(v=v))
        return out


# ---------------------------------------------------------------- small vector helpers

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


def unit(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L) if L > EPS else (0.0, 0.0)


def key(p):
    """Point key for connectivity (0.1 um grid; KiCad works in nm)."""
    return (int(round(p[0] * 1e4)), int(round(p[1] * 1e4)))


class Seg:
    """A straight track segment. id is opaque (the plugin uses it to find the KiCad item)."""
    __slots__ = ("id", "net", "layer", "a", "b", "w")

    def __init__(self, id, net, layer, a, b, w):
        self.id, self.net, self.layer, self.a, self.b, self.w = id, net, layer, a, b, w

    def length(self):
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])


# ---------------------------------------------------------------- bus direction

def bus_axes(segs, tol_deg=TOL_DEG):
    """Dominant direction of the segments (length weighted, angles mod 180).
    Returns (u, n): u along the bus, n = normal; oriented so that n points down,
    or right for a vertical bus, i.e. lane 1 is the top (or left) one."""
    bins = {}
    for s in segs:
        L = s.length()
        if L < EPS:
            continue
        ang = math.degrees(math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0])) % 180.0
        bins.setdefault(int(round(ang / tol_deg)) % int(round(180 / tol_deg)), []).append((ang, L))
    if not bins:
        return (1.0, 0.0), (0.0, 1.0)
    # weight of a bin includes its neighbours, so 44.6 and 45.4 deg count together
    nb = int(round(180 / tol_deg))
    weight = lambda b: sum(L for k in (b - 1, b, b + 1) for _a, L in bins.get(k % nb, []))
    best = max(bins, key=weight)
    # mean angle of the best bin and neighbours (handle the 0/180 wrap)
    ref = bins[best][0][0]
    acc, tot = 0.0, 0.0
    for k in (best - 1, best, best + 1):
        for ang, L in bins.get(k % nb, []):
            d = (ang - ref + 90.0) % 180.0 - 90.0
            acc += d * L
            tot += L
    ang = math.radians(ref + acc / tot)
    u = (math.cos(ang), math.sin(ang))
    n = (-u[1], u[0])
    if n[1] < -1e-9 or (abs(n[1]) <= 1e-9 and n[0] < 0):
        u, n = (-u[0], -u[1]), (-n[0], -n[1])
    return u, n


def is_parallel(s, u, tol_deg=TOL_DEG):
    d = unit(sub(s.b, s.a))
    return abs(cross(d, u)) <= math.sin(math.radians(tol_deg)) and d != (0.0, 0.0)


# ---------------------------------------------------------------- lanes

class Bus:
    def __init__(self, u, n):
        self.u, self.n = u, n
        self.lanes = []
        self.issues = Issues()
        self.ignored = 0          # selected segments that are not part of a lane


def _chains(segs):
    """Connected components of segments (by shared end points)."""
    at = {}
    for i, s in enumerate(segs):
        at.setdefault(key(s.a), []).append(i)
        at.setdefault(key(s.b), []).append(i)
    seen, out = set(), []
    for i in range(len(segs)):
        if i in seen:
            continue
        stack, comp = [i], []
        seen.add(i)
        while stack:
            j = stack.pop()
            comp.append(segs[j])
            for p in (segs[j].a, segs[j].b):
                for k in at[key(p)]:
                    if k not in seen:
                        seen.add(k)
                        stack.append(k)
        out.append(comp)
    return out


def analyze(selected, tracks_at, anchored, tol_deg=TOL_DEG):
    """selected: list of Seg (the user's selection).
    tracks_at(net, layer, point) -> list of Seg of that net/layer with an end at point
    (all board tracks, not only the selection).
    anchored(net, layer, point) -> True if a pad or via of the net sits at point.
    Returns a Bus with lanes sorted by offset."""
    u, n = bus_axes(selected, tol_deg)
    bus = Bus(u, n)
    par = [s for s in selected if is_parallel(s, u, tol_deg)]
    bus.ignored = len(selected) - len(par)
    by_net = {}
    for s in par:
        by_net.setdefault((s.net, s.layer), []).append(s)
    nets_seen = {}
    for (net, layer), segs in by_net.items():
        cands = []
        for comp in _chains(segs):
            # a chain must be collinear (one offset); split by offset if not
            groups = []
            for s in sorted(comp, key=lambda s: dot(s.a, n)):
                o = (dot(s.a, n) + dot(s.b, n)) / 2.0
                if groups and abs(groups[-1][0] - o) <= OFF_TOL:
                    groups[-1][1].append(s)
                else:
                    groups.append([o, [s]])
            for _o, g in groups:
                for c in _chains(g):
                    cands.append(c)
        cands.sort(key=lambda c: -sum(s.length() for s in c))
        lane = _make_lane(cands[0], net, layer, u, n, tracks_at, anchored, tol_deg)
        nets_seen.setdefault(net, []).append((lane, len(cands) > 1))
    for net, items in nets_seen.items():
        # the same net on two layers: keep the longer lane only
        items.sort(key=lambda it: -(it[0]["smax"] - it[0]["smin"]))
        lane, multi = items[0]
        lane["multi"] = multi or len(items) > 1
        bus.lanes.append(lane)
    bus.lanes.sort(key=lambda L: L["o"])
    for k, L in enumerate(bus.lanes):
        L["no"] = k + 1
        if L["multi"]:
            bus.issues.add("multi", k + 1)
    for k in range(len(bus.lanes) - 1):
        A, B = bus.lanes[k], bus.lanes[k + 1]
        if min(A["smax"], B["smax"]) - max(A["smin"], B["smin"]) <= 0:
            bus.issues.add("apart", k + 2)
    if len(bus.lanes) < 2:
        bus.issues.add("one_lane")
    return bus


def _make_lane(chain, net, layer, u, n, tracks_at, anchored, tol_deg):
    ids = set(s.id for s in chain)
    cnt = {}
    for s in chain:
        for p in (s.a, s.b):
            cnt[key(p)] = cnt.get(key(p), 0) + 1
    L = sum(s.length() for s in chain)
    o = sum((dot(s.a, n) + dot(s.b, n)) / 2.0 * s.length() for s in chain) / max(L, EPS)
    ends = []
    for s in chain:
        for which in ("a", "b"):
            p = getattr(s, which)
            if cnt[key(p)] == 1:
                ends.append(dict(p=p, seg=s, which=which))
    along = [dot(p, u) for s in chain for p in (s.a, s.b)]
    smin, smax = min(along), max(along)
    if len(ends) != 2:           # closed loop or odd shape: treat as one segment span
        ends = ends[:2]
    for e in ends:
        e["out"] = u if dot(e["p"], u) >= (smin + smax) / 2.0 else (-u[0], -u[1])
        others = [t for t in tracks_at(net, layer, e["p"]) if t.id not in ids]
        e["adj"] = None
        if anchored(net, layer, e["p"]):
            e["kind"] = "fixed"
        elif not others:
            e["kind"] = "free"
        elif len(others) == 1:
            t = others[0]
            F = t.b if key(t.a) == key(e["p"]) else t.a
            d = unit(sub(e["p"], F))
            if abs(cross(d, u)) <= math.sin(math.radians(tol_deg)):
                e["kind"] = "fixed"           # straight continuation: needs a jog
            else:
                e["kind"] = "slide"
                e["adj"] = t
                e["F"] = F
        else:
            e["kind"] = "fixed"               # junction
    w = max(s.w for s in chain)
    return dict(net=net, layer=layer, segs=chain, o=o, w=w, ends=ends, smin=smin, smax=smax,
                length=L)


# ---------------------------------------------------------------- measuring

def measure(lanes, widths=None):
    """Pitches and gaps between neighbouring lanes (lists, len = lanes - 1)."""
    ws = widths or [L["w"] for L in lanes]
    pitches = [lanes[k + 1]["o"] - lanes[k]["o"] for k in range(len(lanes) - 1)]
    gaps = [p - (ws[k] + ws[k + 1]) / 2.0 for k, p in enumerate(pitches)]
    return pitches, gaps


def span_text(vals):
    if not vals:
        return "–"
    lo, hi = min(vals), max(vals)
    return "%.3f" % lo if hi - lo < 0.0005 else "%.3f–%.3f" % (lo, hi)


# ---------------------------------------------------------------- planning

def targets(lanes, mode, value, widths, keep, shift=0.0, snap=0.0, values=None):
    """New offsets of the lanes. values: optional per-gap list (overrides value)."""
    t = [0.0]
    for k in range(len(lanes) - 1):
        v = (values[k] if k < len(values) else values[-1]) if values else value
        step = v if mode == MODE_PITCH else v + (widths[k] + widths[k + 1]) / 2.0
        t.append(t[-1] + step)
    o = [L["o"] for L in lanes]
    if keep == KEEP_FIRST:
        base = o[0] - t[0]
    elif keep == KEEP_LAST:
        base = o[-1] - t[-1]
    else:                                   # keep the centre line of the bus
        base = (o[0] + o[-1]) / 2.0 - (t[0] + t[-1]) / 2.0
    base += shift
    if snap > 0:
        ref = t[0] + base if keep == KEEP_FIRST else (t[-1] + base if keep == KEEP_LAST
                                                      else (t[0] + t[-1]) / 2.0 + base)
        base += round(ref / snap) * snap - ref
    return [x + base for x in t]


def plan(bus, s):
    """Settings s: mode, value, width (0 = keep), keep, ends, shift, snap.
    Returns dict(moves={seg.id: (a, b, w)}, new=[(net, layer, a, b, w)],
    deltas=[...], targets=[...], issues=Issues, widths=[...])."""
    lanes = bus.lanes
    issues = Issues()
    for code, (items, v) in bus.issues.d.items():
        for it in items or [None]:
            issues.add(code, it, v)
    out = dict(moves={}, new=[], deltas=[], targets=[], issues=issues, widths=[])
    if len(lanes) < 2:
        return out
    widths = [s.get("width") or L["w"] for L in lanes]
    out["widths"] = widths
    tg = targets(lanes, s["mode"], s["value"], widths, s["keep"], s.get("shift", 0.0),
                 s.get("snap", 0.0), s.get("values"))
    out["targets"] = tg
    u, n = bus.u, bus.n
    tan_tol = math.sin(math.radians(10.0))
    for k, (L, t, w) in enumerate(zip(lanes, tg, widths)):
        dl = t - L["o"]
        out["deltas"].append(dl)
        moved = {}
        for sg in L["segs"]:
            # snap the lane onto its exact new line (removes tiny collinearity errors)
            a = add(sg.a, mul(n, t - dot(sg.a, n)))
            b = add(sg.b, mul(n, t - dot(sg.b, n)))
            moved[sg.id] = [a, b, w if s.get("width") else sg.w]
        trim = 0.0                         # along-length taken by jogs
        for e in L["ends"]:
            sg, which = e["seg"], e["which"]
            idx = 0 if which == "a" else 1
            E = e["p"]
            new_end = add(E, mul(n, t - dot(E, n)))
            kind = e["kind"]
            if abs(dl) < 1e-7:
                moved[sg.id][idx] = E if kind != "free" else new_end
                continue
            mode = s["ends"]
            if kind == "slide" and mode != ENDS_JOG:
                adj, F = e["adj"], e["F"]
                if mode == ENDS_STRETCH:
                    _set_adj(out["moves"], adj, F, new_end)
                    moved[sg.id][idx] = new_end
                    continue
                d = unit(sub(E, F))
                dn = dot(d, n)
                if abs(dn) < tan_tol:
                    issues.add("steep", k + 1)
                    kind = "fixed"
                else:
                    tt = (t - dot(F, n)) / dn         # distance from F along d
                    if tt < 0.005:
                        issues.add("flip", k + 1)
                        kind = "fixed"
                    else:
                        P = add(F, mul(d, tt))
                        _set_adj(out["moves"], adj, F, P)
                        moved[sg.id][idx] = P
                        continue
            if kind == "free":
                moved[sg.id][idx] = new_end
                continue
            if mode == ENDS_STRETCH and kind == "fixed":
                # straight connector from the old point to the moved lane end
                moved[sg.id][idx] = new_end
                out["new"].append((L["net"], L["layer"], new_end, E, w))
                continue
            # 45 deg jog: the lane end steps back by |dl| along the lane
            back = abs(dl)
            J = add(new_end, mul(e["out"], -back))
            trim += back
            moved[sg.id][idx] = J
            out["new"].append((L["net"], L["layer"], J, E, w))
        # check that no lane segment turned around (lane too short / neighbour)
        span = L["smax"] - L["smin"]
        if trim > span - 0.005:
            issues.add("short", k + 1, trim - span + 0.005)
        for sg in L["segs"]:
            a, b, _w = moved[sg.id]
            if dot(sub(b, a), sub(sg.b, sg.a)) < 0:
                issues.add("short", k + 1, abs(dot(sub(b, a), u)))
        for sid, (a, b, ww) in moved.items():
            out["moves"][sid] = (tuple(a), tuple(b), ww)
    pit, gaps = measure([dict(o=t) for t in tg], widths)
    for k, gp in enumerate(gaps):
        if gp < -1e-6:
            issues.add("overlap", k + 2, -gp)
    return out


def _set_adj(moves, adj, F, P):
    """Move the end of neighbour adj that is not F to P (keeps an earlier move of the
    other end, e.g. a short segment between two lanes of the same net)."""
    prev = moves.get(adj.id)
    a, b, w = prev if prev else (adj.a, adj.b, adj.w)
    if key(adj.a) == key(F):
        moves[adj.id] = (a, P, w)
    else:
        moves[adj.id] = (P, b, w)


def check_gaps(lanes, tg, widths, clr, issues):
    """Gap between neighbouring lanes against the netclass clearance (clr: net -> mm)."""
    for k in range(len(lanes) - 1):
        need = max(clr.get(lanes[k]["net"], 0.0), clr.get(lanes[k + 1]["net"], 0.0))
        gap = tg[k + 1] - tg[k] - (widths[k] + widths[k + 1]) / 2.0
        if gap < need - 1e-4 and gap >= -1e-6:
            issues.add("gap_clr", k + 2, need - gap)


# ---------------------------------------------------------------- clearance check

def pt_seg(p, a, b):
    ab = sub(b, a)
    L2 = dot(ab, ab)
    if L2 < EPS * EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / L2))
    q = add(a, mul(ab, t))
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _orient(a, b, c):
    return cross(sub(b, a), sub(c, a))


def seg_seg(a, b, c, d):
    """Distance between segments ab and cd (0 if they cross)."""
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 * d2 < 0 and d3 * d4 < 0:
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


class Obstacle:
    """Copper of the board: kind 'seg' (a, b, half width), 'circle' (c, r) or 'poly'
    (points). layer None = all copper layers (through vias, through-hole pads).
    id = the board item, so the items we move can be skipped."""
    __slots__ = ("kind", "data", "net", "layer", "id", "bbox")

    def __init__(self, kind, data, net, layer, id=None):
        self.kind, self.data, self.net, self.layer, self.id = kind, data, net, layer, id
        if kind == "seg":
            a, b, h = data
            self.bbox = (min(a[0], b[0]) - h, min(a[1], b[1]) - h, max(a[0], b[0]) + h, max(a[1], b[1]) + h)
        elif kind == "circle":
            c, r = data
            self.bbox = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
        else:
            xs = [p[0] for p in data]
            ys = [p[1] for p in data]
            self.bbox = (min(xs), min(ys), max(xs), max(ys))

    def dist(self, a, b):
        """Copper-to-copper distance from the centre line ab (subtract the half width)."""
        if self.kind == "seg":
            p, q, h = self.data
            return seg_seg(a, b, p, q) - h
        if self.kind == "circle":
            c, r = self.data
            return pt_seg(c, a, b) - r
        return seg_poly(a, b, self.data)


class Grid:
    """Spatial hash of obstacles (cell in mm) for fast neighbourhood queries."""

    def __init__(self, obstacles, cell=1.0):
        self.cell = cell
        self.cells = {}
        for o in obstacles:
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
        """Obstacles in the cells of a corridor of half width r around segment ab
        (a long diagonal track touches far fewer cells than its bounding box)."""
        c = self.cell
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(L / (c * 0.5))))
        cells = set()
        for k in range(n + 1):
            x = a[0] + (b[0] - a[0]) * k / n
            y = a[1] + (b[1] - a[1]) * k / n
            for i in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
                for j in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                    cells.add((i, j))
        out = set()
        get = self.cells.get
        for cc in cells:
            out.update(get(cc, ()))
        return out


def check_copper(segments, grid, clr, skip, issues, lane_ids=frozenset()):
    """segments: [(lane_no, net, layer, a, b, w, sid)] = the new geometry. Each is checked
    against board copper of other nets (grid, items in skip ignored) and against the new
    segments of other nets. Two parallel lane segments are not compared here: their
    distance is the gap, checked exactly by check_gaps(). clr: net -> clearance [mm]."""
    worst = {}
    news = [Obstacle("seg", (a, b, w / 2.0), net, layer, id=("new", i, sid in lane_ids))
            for i, (_no, net, layer, a, b, w, sid) in enumerate(segments)]
    ngrid = Grid(news, grid.cell)
    for i, (no, net, layer, a, b, w, sid) in enumerate(segments):
        is_lane = sid in lane_ids
        c = clr.get(net, 0.0)
        r = w / 2.0 + c + 0.01
        bb = (min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)
        reach = r + 0.25 * grid.cell
        for o in grid.near_seg(a, b, reach) | ngrid.near_seg(a, b, reach):
            if o.net == net or (o.layer is not None and o.layer != layer) or o.id in skip:
                continue
            if isinstance(o.id, tuple) and (o.id[1] == i or (is_lane and o.id[2])):
                continue
            if o.bbox[2] < bb[0] or o.bbox[0] > bb[2] or o.bbox[3] < bb[1] or o.bbox[1] > bb[3]:
                continue
            # cheap reject: obstacle bbox farther from the line than needed
            ox, oy = (o.bbox[0] + o.bbox[2]) / 2.0, (o.bbox[1] + o.bbox[3]) / 2.0
            orad = math.hypot(o.bbox[2] - o.bbox[0], o.bbox[3] - o.bbox[1]) / 2.0
            if pt_seg((ox, oy), a, b) - orad > r:
                continue
            short = c - (o.dist(a, b) - w / 2.0)
            if short > 1e-4:
                worst[no] = max(worst.get(no, 0.0), short)
    for no, v in worst.items():
        issues.add("close", no, v)
    return worst
