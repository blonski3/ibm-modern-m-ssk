# Pure geometry of fillet-o-matic (no KiCad). Selected track segments and arcs are joined
# into chains; every arc becomes its sharp corner (where its two straight neighbours meet),
# then each corner is rounded with a tangent arc, cut with a chamfer, or left sharp.
# Corners of parallel tracks that turn together (a bus) are made concentric, so the
# spacing stays the same through the turn. mm, Y down.

import math

from . import geo

ROUND, CHAMFER, SHARP = 0, 1, 2
CONCENTRIC, SAME = 0, 1
REF_INNER, REF_MIDDLE, REF_OUTER = 0, 1, 2
SHRINK, SKIP = 0, 1
UNIT_MM, UNIT_W = 0, 1
BUS_GAP = 6.0          # mm: corners of one bus are at most this far from the next one
EPS = 1e-6
MIN_T = 0.005          # mm: smaller fillets / cuts are not made (KiCad cannot round them to nm)

TEXT = {
    "short": ("radius / cut made smaller ({v:.3f} mm left), the straight parts are too short",
              "a smaller value, or longer straight parts"),
    "skip": ("left sharp, the straight parts are too short", "a smaller value, or Too short: Shrink (More)"),
    "halfw": ("radius is below half the track width (W/2 = {v:.3f} mm)", "R ≥ W/2"),
    "junction": ("corner meets a third track, a via or a pad, left as it is",
                 "round it by hand, or select only the tracks"),
    "bigarc": ("arc of {v:.0f}° or more, left as it is", "edit it by hand"),
    "neg": ("the inner track would need a radius ≤ 0, left sharp", "a bigger value, or R of: Inner (More)"),
    "clr": ("{v:.3f} mm too close to other copper", "a smaller value, or move that copper"),
}


def issues():
    return geo.Issues(TEXT, ("At", "At"))


def where(p):
    return "(%.2f %.2f)" % (p[0], p[1])


# ---------------------------------------------------------------- pieces

def arc_info(a, m, b):
    """(centre, radius, tangent at a, tangent at b (directions of travel a -> b), |sweep| deg)."""
    c = geo.circle_center(a, m, b)
    if c is None:
        return None
    r = geo.dist(a, c)
    ta = geo.unit(geo.perp(geo.sub(a, c)))
    if geo.dot(ta, geo.sub(m, a)) < 0:
        ta = geo.mul(ta, -1.0)
    tb = geo.unit(geo.perp(geo.sub(b, c)))
    if geo.dot(tb, geo.sub(b, m)) < 0:
        tb = geo.mul(tb, -1.0)
    t0, tm, t1 = (math.atan2(q[1] - c[1], q[0] - c[0]) for q in (a, m, b))
    sweep = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > sweep:
        sweep = 2 * math.pi - sweep
    return c, r, ta, tb, math.degrees(sweep)


class Piece:
    """A selected track: kind 'seg' or 'arc' (a -> m -> b), width w, layer, net code."""

    def __init__(self, id, kind, a, b, w, layer, net, m=None):
        self.id, self.kind, self.a, self.b, self.m = id, kind, a, b, m
        self.w, self.layer, self.net = w, layer, net
        self.info = arc_info(a, m, b) if kind == "arc" else None

    def length(self):
        return geo.dist(self.a, self.b)

    def oriented(self, rev):
        """(start, end, direction of travel at start, at end)."""
        if self.kind == "seg":
            a, b = (self.b, self.a) if rev else (self.a, self.b)
            d = geo.unit(geo.sub(b, a))
            return a, b, d, d
        c, r, ta, tb, _s = self.info
        if rev:
            return self.b, self.a, geo.mul(tb, -1.0), geo.mul(ta, -1.0)
        return self.a, self.b, ta, tb


def usable(p):
    if p.length() < EPS:
        return False
    if p.kind == "arc":
        return p.info is not None and p.info[4] < 178.0
    return True


# ---------------------------------------------------------------- chains

def build_chains(pieces, blocked):
    """Chains of pieces joined end to end where exactly two of them meet on the same
    layer and net and nothing else is there (blocked = {(layer, key)}).
    -> [[(piece, reversed), ...], ...] in travel order."""
    ends = {}
    for i, p in enumerate(pieces):
        for e, q in ((0, p.a), (1, p.b)):
            ends.setdefault((p.layer, p.net, geo.key(q)), []).append((i, e))

    def joint(k):
        lst = ends.get(k, ())
        return len(lst) == 2 and lst[0][0] != lst[1][0] and (k[0], k[2]) not in blocked

    used = [False] * len(pieces)

    def walk(i, ent):
        chain = []
        cur = i
        while True:
            used[cur] = True
            p = pieces[cur]
            chain.append((p, ent == 1))
            q = p.a if ent == 1 else p.b
            k = (p.layer, p.net, geo.key(q))
            if not joint(k):
                break
            nxt = [(j, e) for j, e in ends[k] if j != cur]
            j, e = nxt[0]
            if used[j]:
                break
            cur, ent = j, e
        return chain

    chains = []
    for i, p in enumerate(pieces):
        if used[i]:
            continue
        for e, q in ((0, p.a), (1, p.b)):
            if not joint((p.layer, p.net, geo.key(q))):
                chains.append(walk(i, e))
                break
    for i in range(len(pieces)):
        if not used[i]:
            chains.append(walk(i, 0))          # closed loop
    return chains


def _turn(u1, u2):
    """Unsigned turn angle (rad) from direction u1 to u2."""
    return math.atan2(abs(geo.cross(u1, u2)), geo.dot(u1, u2))


class Poly:
    """A chain as a polyline: verts, segs (between verts[j] and verts[j+1]: dict with the
    straight piece it reuses ('item'), the arcs it came from, width), vsrc[i] = the arc
    whose sharp corner verts[i] is."""

    def __init__(self, chain):
        self.layer = chain[0][0].layer
        self.net = chain[0][0].net
        verts, segs, vsrc, soft = [], [], [], []
        n = len(chain)
        ori = [p.oriented(rev) for p, rev in chain]
        verts.append(ori[0][0])
        vsrc.append(None)
        soft.append(False)
        for i, ((p, rev), (a, b, din, dout)) in enumerate(zip(chain, ori)):
            if p.kind == "seg":
                segs.append(dict(items=[p], arcs=[], w=p.w))
                verts.append(b)
                vsrc.append(None)
                soft.append(i + 1 < n and chain[i + 1][0].kind == "arc")
                continue
            if i > 0:
                soft[-1] = True                 # arc start joins the previous piece
            u_in = ori[i - 1][3] if i > 0 and chain[i - 1][0].kind == "seg" else din
            u_out = ori[i + 1][2] if i + 1 < n and chain[i + 1][0].kind == "seg" else dout
            V = self._corner(a, b, u_in, u_out, p) or self._corner(a, b, din, dout, p)
            segs.append(dict(items=[], arcs=[p], w=p.w))
            verts.append(V)
            vsrc.append(p)
            soft.append(False)
            segs.append(dict(items=[], arcs=[p], w=p.w))
            verts.append(b)
            vsrc.append(None)
            soft.append(i + 1 < n)
        soft[-1] = False
        # merge the straight parts on both sides of former arc ends
        V2, S2, src2 = [verts[0]], [segs[0]], [vsrc[0]]
        for i in range(1, len(verts) - 1):
            u1 = geo.unit(geo.sub(verts[i], V2[-1]))
            u2 = geo.unit(geo.sub(verts[i + 1], verts[i]))
            if soft[i] and (geo.dist(verts[i], V2[-1]) < EPS or geo.dist(verts[i + 1], verts[i]) < EPS
                            or (abs(geo.cross(u1, u2)) < 1e-7 and geo.dot(u1, u2) > 0)):
                s = S2[-1]
                items = s["items"] + segs[i]["items"]
                S2[-1] = dict(items=items, arcs=s["arcs"] + segs[i]["arcs"],
                              w=items[0].w if items else s["w"])
                continue
            V2.append(verts[i])
            src2.append(vsrc[i])
            S2.append(segs[i])
        V2.append(verts[-1])
        src2.append(vsrc[-1])
        self.verts, self.segs, self.vsrc = V2, S2, src2
        self.arcs = [p for p, _r in chain if p.kind == "arc"]
        self.lengths = [geo.dist(a, b) for a, b in zip(V2, V2[1:])]

    @staticmethod
    def _corner(a, b, u_in, u_out, p):
        hit = geo.line_cross(a, u_in, b, u_out)
        if hit is None:
            return None
        t, s = hit
        lim = 10.0 * (geo.dist(a, b) + p.info[1])
        if t <= EPS or s >= -EPS or t > lim or -s > lim:
            return None
        return geo.add(a, geo.mul(u_in, t))


class Corner:
    __slots__ = ("poly", "i", "P", "d1", "d2", "phi", "bis", "w", "layer", "arc", "s", "smax", "wref", "n", "g")

    def __init__(self, poly, i, n):
        v = poly.verts
        self.poly, self.i, self.n = poly, i, n
        self.P = v[i]
        self.d1 = geo.unit(geo.sub(v[i], v[i - 1]))
        self.d2 = geo.unit(geo.sub(v[i + 1], v[i]))
        self.phi = _turn(self.d1, self.d2)
        self.bis = geo.unit(geo.sub(self.d2, self.d1))
        self.w = min(poly.segs[i - 1]["w"], poly.segs[i]["w"])
        self.layer = poly.layer
        self.arc = poly.vsrc[i]
        self.s, self.smax, self.wref, self.g = 0.0, 0.0, self.w, n


class Prep:
    """Everything that depends only on the selection and the minimum angle."""

    def __init__(self, pieces, blocked, min_angle):
        self.issues = []                     # (code, where, value) found while preparing
        good = []
        for p in pieces:
            if usable(p):
                good.append(p)
            elif p.kind == "arc" and p.info is not None and p.length() >= EPS:
                self.issues.append(("bigarc", where(p.m), 178.0))
        self.pieces = good
        self.chains = build_chains(good, blocked)
        self.polys = [Poly(c) for c in self.chains]
        lim = math.radians(max(0.0, min_angle))
        self.corners = []
        for poly in self.polys:
            poly.corner_at = {}
            for i in range(1, len(poly.verts) - 1):
                c = Corner(poly, i, len(self.corners))
                if c.phi >= max(lim, 1e-6) or (c.arc is not None and c.phi > 1e-6):
                    poly.corner_at[i] = c
                    self.corners.append(c)
        self._junctions(good, blocked, lim)
        self._groups()

    def _junctions(self, pieces, blocked, lim):
        at = {}
        for p in pieces:
            for rev in (False, True):
                a, b, din, dout = p.oriented(rev)
                at.setdefault((p.layer, geo.key(a)), []).append((a, din))
        for k, lst in at.items():
            if k in blocked and len(lst) == 2:
                u1, u2 = geo.mul(lst[0][1], -1.0), lst[1][1]
                if _turn(u1, u2) >= max(lim, 1e-6):
                    self.issues.append(("junction", where(lst[0][0]), None))

    def _groups(self):
        """Corners of parallel tracks turning together: same layer, turn and bisector,
        corner points on one line along the bisector, neighbours ≤ BUS_GAP apart."""
        cs = self.corners
        parent = list(range(len(cs)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        cos_tol = math.cos(math.radians(0.5))
        for i in range(len(cs)):
            a = cs[i]
            for j in range(i + 1, len(cs)):
                b = cs[j]
                if a.layer != b.layer or abs(a.phi - b.phi) > math.radians(0.5):
                    continue
                if geo.dot(a.bis, b.bis) < cos_tol:
                    continue
                d = geo.sub(b.P, a.P)
                if geo.length(d) > BUS_GAP or abs(geo.cross(d, a.bis)) > 0.02:
                    continue
                parent[find(i)] = find(j)
        groups = {}
        for i in range(len(cs)):
            groups.setdefault(find(i), []).append(cs[i])
        self.groups = list(groups.values())
        for gi, grp in enumerate(self.groups):
            for c in grp:
                c.g = gi
            inner = max(geo.dot(c.P, c.bis) for c in grp)
            for c in grp:
                c.s = (inner - geo.dot(c.P, c.bis)) * math.cos(c.phi / 2.0)
            smax = max(c.s for c in grp)
            wref = max(c.w for c in grp)
            for c in grp:
                c.smax, c.wref = smax, wref


# ---------------------------------------------------------------- plan

class Result:
    def __init__(self):
        self.ops = []          # ("set", id, a, b) ("del", id) ("seg", a, b, like_id, w) ("arc", a, m, b, like_id, w)
        self.final = []        # every resulting piece: dict(kind, a, b, m, w, layer, net, new, cn)
        self.exact = set()     # corners done exactly as wanted (no shrinking)
        self.issues = issues()
        self.stats = dict(corners=0, done=0, reduced=0, skipped=0, rmin=None, rmax=None)


def setbacks(prep, s, res):
    """Wanted setback (distance from the corner along each leg) per corner."""
    mode = s["mode"]
    want = {}
    for c in prep.corners:
        if mode == SHARP:
            want[c.n] = 0.0
            continue
        base = s["r"] if mode == ROUND else s["c"]
        if s.get("unit") == UNIT_W:
            base *= c.wref if s.get("bus") == CONCENTRIC else c.w
        off = 0.0
        if s.get("bus", CONCENTRIC) == CONCENTRIC:
            ref = s.get("ref", REF_INNER)
            off = c.s - (0.0, c.smax / 2.0, c.smax)[ref]
        if mode == ROUND:
            R = base + off
            if R <= 1e-4:
                if base > 0:
                    res.issues.add("neg", where(c.P))
                want[c.n] = 0.0
                continue
            want[c.n] = R * math.tan(c.phi / 2.0)
        else:
            f = math.tan(c.phi / 4.0) / math.cos(c.phi / 2.0)
            t = base + off * f
            if t <= 1e-4:
                if base > 0:
                    res.issues.add("neg", where(c.P))
                want[c.n] = 0.0
                continue
            want[c.n] = t
    return want


def fit(poly, want):
    """Setbacks that fit the straight parts: scale down where two corners share a part,
    then let each corner grow back into the room left. {vertex index: setback}."""
    t = {i: want[c.n] for i, c in poly.corner_at.items()}
    L = poly.lengths
    for j, Lj in enumerate(L):
        ta, tb = t.get(j, 0.0), t.get(j + 1, 0.0)
        if ta + tb > Lj:
            if ta > 0 and tb > 0:
                k = Lj / (ta + tb)
                t[j], t[j + 1] = ta * k, tb * k
            elif ta > 0:
                t[j] = Lj
            else:
                t[j + 1] = Lj
    for i in sorted(t):
        c = poly.corner_at[i]
        room = min(L[i - 1] - t.get(i - 1, 0.0), L[i] - t.get(i + 1, 0.0))
        t[i] = min(want[c.n], max(t[i], room))
    return t


def plan(prep, s):
    res = Result()
    for code, w, v in prep.issues:
        res.issues.add(code, w, v)
    want = setbacks(prep, s, res)
    mode = s["mode"]
    res.stats["corners"] = len(prep.corners)
    def tmin(c):
        """Smallest setback worth making: 5 µm, and for arcs a 5 µm radius."""
        return max(MIN_T, MIN_T * math.tan(c.phi / 2.0)) if mode == ROUND else MIN_T
    for c in prep.corners:
        if want[c.n] < tmin(c):
            want[c.n] = 0.0
    for poly in prep.polys:
        t = fit(poly, want)
        tiny = [i for i, c in poly.corner_at.items() if 0 < t[i] < tmin(c)]
        if tiny:
            w2 = dict(want)
            for i in tiny:
                w2[poly.corner_at[i].n] = 0.0
                res.issues.add("skip", where(poly.verts[i]))
                res.stats["skipped"] += 1
            t = fit(poly, w2)
        if s.get("short") == SKIP and mode != SHARP:
            w2 = dict(want)
            for _ in range(len(t) + 1):
                bad = [i for i, c in poly.corner_at.items() if t[i] < w2[c.n] * (1 - 1e-6)]
                if not bad:
                    break
                for i in bad:
                    w2[poly.corner_at[i].n] = 0.0
                    res.issues.add("skip", where(poly.verts[i]))
                    res.stats["skipped"] += 1
                t = fit(poly, w2)
        _emit(poly, t, want, mode, s, res)
    return res


def _emit(poly, t, want, mode, s, res):
    """Ops for one chain. The end points of the straight parts and of the corner pieces
    are the very same numbers, so KiCad's rounding to nm keeps them connected."""
    V = poly.verts
    act = {}                                   # vertex -> (T1, T2, setback) of a changed corner
    for i, c in poly.corner_at.items():
        ti = t.get(i, 0.0)
        if mode == SHARP or ti <= EPS:
            continue
        act[i] = [geo.sub(c.P, geo.mul(c.d1, ti)), geo.add(c.P, geo.mul(c.d2, ti)), ti]
    kept = {}
    for i in act:
        c = poly.corner_at[i]
        if mode == ROUND and c.arc is not None:
            T1, T2, ti = act[i]
            R = ti / math.tan(c.phi / 2.0)
            M = geo.sub(geo.add(c.P, geo.mul(c.bis, R / math.cos(c.phi / 2.0))), geo.mul(c.bis, R))
            ends = _same_arc(c.arc, T1, M, T2)
            if ends:
                act[i][0], act[i][1] = ends
                kept[i] = c.arc
    # straight parts
    seg_pts = []
    for j, sg in enumerate(poly.segs):
        a = act[j][1] if j in act else V[j]
        b = act[j + 1][0] if (j + 1) in act else V[j + 1]
        d = geo.sub(b, a)
        items = sg["items"]
        if geo.dot(d, geo.sub(V[j + 1], V[j])) <= 0 or geo.length(d) < EPS:
            p = V[j] if j not in act else (V[j + 1] if (j + 1) not in act else geo.mul(geo.add(a, b), 0.5))
            a = b = p
        elif items:
            it = items[0]
            fwd = geo.dot(geo.sub(it.b, it.a), d) >= 0
            ia, ib = (it.a, it.b) if fwd else (it.b, it.a)
            if geo.dist(a, ia) < 2e-6 and j not in kept:
                a = ia
            if geo.dist(b, ib) < 2e-6 and (j + 1) not in kept:
                b = ib
        if j in act:
            act[j][1] = a
        if (j + 1) in act:
            act[j + 1][0] = b
        seg_pts.append((a, b))
    for j, (sg, (a, b)) in enumerate(zip(poly.segs, seg_pts)):
        items = sg["items"]
        for extra in items[1:]:
            res.ops.append(("del", extra.id))
        if geo.dist(a, b) < EPS:
            if items:
                res.ops.append(("del", items[0].id))
            continue
        if items:
            it = items[0]
            fwd = geo.dot(geo.sub(it.b, it.a), geo.sub(b, a)) >= 0
            sa, sb = (a, b) if fwd else (b, a)
            changed = sa != it.a or sb != it.b
            if changed:
                res.ops.append(("set", it.id, sa, sb))
            res.final.append(dict(kind="seg", a=a, b=b, m=None, w=it.w, layer=poly.layer, net=poly.net,
                                  new=changed, cn=_ends(poly, act, j)))
        else:
            like = sg["arcs"][0]
            res.ops.append(("seg", a, b, like.id, sg["w"]))
            res.final.append(dict(kind="seg", a=a, b=b, m=None, w=sg["w"], layer=poly.layer, net=poly.net,
                                  new=True, cn=_ends(poly, act, j)))
    # corners
    for i, (T1, T2, ti) in act.items():
        c = poly.corner_at[i]
        if ti < want[c.n] * (1 - 1e-6):
            res.stats["reduced"] += 1
            res.issues.add("short", where(c.P), ti)
        else:
            res.exact.add(c.n)
        res.stats["done"] += 1
        like = (poly.segs[i - 1]["items"] or poly.segs[i]["items"] or poly.segs[i - 1]["arcs"]
                or poly.segs[i]["arcs"])[0]
        f = dict(layer=poly.layer, net=poly.net, a=T1, b=T2, cn=(c.n,))
        if mode == ROUND:
            R = ti / math.tan(c.phi / 2.0)
            res.stats["rmin"] = R if res.stats["rmin"] is None else min(res.stats["rmin"], R)
            res.stats["rmax"] = R if res.stats["rmax"] is None else max(res.stats["rmax"], R)
            if R < c.w / 2.0 - 1e-9:
                res.issues.add("halfw", where(c.P), c.w / 2.0)
            if i in kept:
                f.update(kind="arc", m=kept[i].m, w=kept[i].w, new=False)
            else:
                ctr = geo.add(c.P, geo.mul(c.bis, R / math.cos(c.phi / 2.0)))
                M = geo.sub(ctr, geo.mul(c.bis, R))
                res.ops.append(("arc", T1, M, T2, like.id, c.w))
                f.update(kind="arc", m=M, w=c.w, new=True)
        else:
            res.ops.append(("seg", T1, T2, like.id, c.w))
            f.update(kind="seg", m=None, w=c.w, new=True)
        res.final.append(f)
    keep_ids = {a.id for a in kept.values()}
    for a in poly.arcs:
        if a.id not in keep_ids:
            res.ops.append(("del", a.id))


def _ends(poly, act, j):
    return tuple(poly.corner_at[i].n for i in (j, j + 1) if i in act)


def _same_arc(arc, T1, M, T2):
    """The arc's own (start, end) in travel order when it already is this fillet."""
    if geo.dist(arc.m, M) > 1e-3:
        return None
    for a, b in ((arc.a, arc.b), (arc.b, arc.a)):
        if geo.dist(a, T1) < 2e-6 and geo.dist(b, T2) < 2e-6:
            return a, b
    return None


# ---------------------------------------------------------------- now / check

def describe(pieces, min_angle=1.0):
    """What the selection looks like now: arc radii and sharp corners."""
    radii = sorted(p.info[1] for p in pieces if p.kind == "arc" and p.info)
    prep = Prep([p for p in pieces if p.kind == "seg"], set(), min_angle)
    sharp = len(prep.corners)
    parts = []
    if radii:
        lo, hi = radii[0], radii[-1]
        parts.append("R %.3f mm" % lo if hi - lo < 5e-4 else "R %.3f–%.3f" % (lo, hi))
    if sharp:
        parts.append("%d sharp" % sharp)
    return ", ".join(parts) or "straight"


def piece_segs(f):
    """[(a, b, extra half width)]: an arc as chords at most 4 µm from it, moved out by
    half that, so the error is ±2 µm (KiCad's own DRC approximates arcs to 5 µm)."""
    if f["kind"] != "arc":
        return [(f["a"], f["b"], 0.0)]
    if "chords" not in f:
        info = arc_info(f["a"], f["m"], f["b"])
        if info is None or info[1] < 1e-6:
            f["chords"] = [(f["a"], f["b"], 0.0)]
            return f["chords"]
        c, r = info[0], info[1]
        step = 2.0 * math.acos(max(-1.0, 1.0 - 0.004 / r))
        n = max(2, int(math.ceil(math.radians(info[4]) / step)))
        pts = geo.arc_points(f["a"], f["m"], f["b"], n)
        sag = r * (1.0 - math.cos(math.radians(info[4]) / n / 2.0))
        out = []
        for p, q in zip(pts, pts[1:]):
            u = geo.unit(geo.sub(geo.mul(geo.add(p, q), 0.5), c))
            sh = geo.mul(u, sag / 2.0)
            out.append((geo.add(p, sh), geo.add(q, sh), 0.0))
        f["chords"] = out
    return f["chords"]


def check(final, static, clr_of, iss, prep=None, exact=()):
    """Clearance of the new pieces to other copper (static grid) and to the other
    selected tracks after the change. Pieces of one bus turn that came out exactly
    concentric keep the spacing they had, so they are not checked against each other."""
    dyn = geo.Grid(cell=1.0)
    for k, f in enumerate(final):
        for a, b, x in piece_segs(f):
            dyn.add(geo.Obstacle("seg", (a, b, f["w"] / 2.0 + x), f["net"], f["layer"], id=k))
    members = {}
    ok_groups = set()
    if prep is not None:
        for gi, grp in enumerate(prep.groups):
            if len(grp) > 1 and all(c.n in exact for c in grp):
                ok_groups.add(gi)
        for k, f in enumerate(final):
            for n in f.get("cn", ()):
                gi = prep.corners[n].g
                if gi in ok_groups:
                    members.setdefault(gi, set()).add(k)
    for k, f in enumerate(final):
        if not f["new"]:
            continue
        clr = clr_of(f["net"])
        skip = {k}
        if prep is not None:
            for n in f.get("cn", ()):
                skip |= members.get(prep.corners[n].g, set())
        short = 0.0
        for a, b, x in piece_segs(f):
            w = f["w"] + 2 * x
            short = max(short, geo.seg_clear(static, a, b, w, f["net"], f["layer"], clr),
                        geo.seg_clear(dyn, a, b, w, f["net"], f["layer"], clr, skip=skip))
        if short > 1e-4:
            mid = f["m"] if f["kind"] == "arc" else geo.mul(geo.add(f["a"], f["b"]), 0.5)
            iss.add("clr", where(mid), short)
