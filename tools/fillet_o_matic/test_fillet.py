# Tests of fillet-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_fillet.py
# GUI:  xvfb-run -a python3 test_fillet.py gui [screenshot_dir]

import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.append(HERE)

import pcbnew  # noqa: E402

import tboard as T  # noqa: E402
from fillet_o_matic import geo  # noqa: E402
from fillet_o_matic import geometry as g  # noqa: E402
from fillet_o_matic import fillet_o_matic as fm  # noqa: E402

check = T.check


def S(**kw):
    s = dict(mode=g.ROUND, bus=g.CONCENTRIC, r=1.0, c=0.5, unit=g.UNIT_MM, ref=g.REF_INNER, min_angle=5.0,
             short=g.SHRINK, check=True)
    s.update(kw)
    return s


def polyline(b, pts, nt, w=0.2, layer=pcbnew.F_Cu, flip=()):
    out = []
    for k, (a, c) in enumerate(zip(pts, pts[1:])):
        out.append(T.track(b, c, a, nt, w, layer) if k in flip else T.track(b, a, c, nt, w, layer))
    return out


def model_for(b, items=None):
    for t in (items if items is not None else T.tracks(b)):
        t.SetSelected()
    m = fm.Model(b)
    m.load(m.selected())
    return m


def arcs(b):
    return [t for t in b.GetTracks() if t.GetClass() == "PCB_ARC"]


def segs(b):
    return [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]


def arc_r(t):
    c = geo.circle_center(T.xy(t.GetStart()), T.xy(t.GetMid()), T.xy(t.GetEnd()))
    return geo.dist(c, T.xy(t.GetStart())), c


def clusters(b):
    """Connected groups of tracks per net, by exact end points (nm)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for t in T.tracks(b):
        s, e = t.GetStart(), t.GetEnd()
        a = (t.GetNetCode(), t.GetLayer(), s.x, s.y)
        c = (t.GetNetCode(), t.GetLayer(), e.x, e.y)
        parent[find(a)] = find(c)
    return len({find(x) for x in list(parent)})


def tangent_ok(b, tol=2e-3, verbose=False):
    """Every arc end that touches a straight track is tangent to it."""
    ends = {}
    for t in segs(b):
        for p, q in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ends.setdefault((t.GetLayer(), p.x, p.y), []).append(geo.unit(geo.sub(T.xy(q), T.xy(p))))
    bad = 0
    for a in arcs(b):
        r, c = arc_r(a)
        for p in (a.GetStart(), a.GetEnd()):
            for d in ends.get((a.GetLayer(), p.x, p.y), ()):
                rv = geo.unit(geo.sub(T.xy(p), c))
                if abs(geo.dot(rv, d)) > tol:
                    bad += 1
                    if verbose:
                        print("   not tangent: arc", T.xy(a.GetStart()), T.xy(a.GetMid()), T.xy(a.GetEnd()),
                              "r %.5f dot %.5f" % (r, geo.dot(rv, d)))
    return bad == 0


def lane_spacing(b, n1, n2, step=0.02, worst=False):
    """Smallest centre-line distance between the tracks of two nets (sampled); with
    worst=True the largest distance from a point of n1 (3 mm away from its ends) to n2."""
    def pts(nc):
        out = []
        for t in T.tracks(b):
            if t.GetNetCode() != nc:
                continue
            if t.GetClass() == "PCB_ARC":
                out += geo.arc_points(T.xy(t.GetStart()), T.xy(t.GetMid()), T.xy(t.GetEnd()), 64)
            else:
                a, c = T.xy(t.GetStart()), T.xy(t.GetEnd())
                n = max(1, int(geo.dist(a, c) / step))
                out += [geo.add(a, geo.mul(geo.sub(c, a), k / n)) for k in range(n + 1)]
        return out

    def segs_of(nc):
        out = []
        for t in T.tracks(b):
            if t.GetNetCode() != nc:
                continue
            if t.GetClass() == "PCB_ARC":
                q = geo.arc_points(T.xy(t.GetStart()), T.xy(t.GetMid()), T.xy(t.GetEnd()), 256)
                out += list(zip(q, q[1:]))
            else:
                out.append((T.xy(t.GetStart()), T.xy(t.GetEnd())))
        return out
    S2 = segs_of(n2)
    P1 = pts(n1)
    if worst:
        ends = [q for t in T.tracks(b) if t.GetNetCode() == n1 for q in (T.xy(t.GetStart()), T.xy(t.GetEnd()))]
        cnt = {}
        for q in ends:
            cnt[geo.key(q)] = cnt.get(geo.key(q), 0) + 1
        free = [q for q in ends if cnt[geo.key(q)] == 1]
        P1 = [p for p in P1 if min(geo.dist(p, q) for q in free) > 3.0]
        return max(min(geo.pt_seg(p, a, c) for a, c in S2) for p in P1)
    return min(min(geo.pt_seg(p, a, c) for a, c in S2) for p in P1)


# ---------------------------------------------------------------- tests

def test_single_corner():
    for flip in ((), (0,), (1,), (0, 1)):
        b = pcbnew.BOARD()
        n = T.net(b, "A")
        polyline(b, [(0, 0), (10, 0), (10, -10)], n, flip=flip)
        before = T.snapshot(b)
        m = model_for(b)
        res = m.apply(S(r=2.0))
        check(len(arcs(b)) == 1, "one arc %s" % (flip,))
        r, c = arc_r(arcs(b)[0])
        check(abs(r - 2.0) < 1e-5, "radius 2: %.6f" % r)
        check(geo.dist(c, (8, -2)) < 1e-5, "centre %s" % (c,))
        check(clusters(b) == 1, "connected %s" % (flip,))
        check(tangent_ok(b), "tangent")
        L = sorted(geo.dist(T.xy(t.GetStart()), T.xy(t.GetEnd())) for t in segs(b))
        check(abs(L[0] - 8) < 1e-5 and abs(L[1] - 8) < 1e-5, "legs shortened by R: %s" % L)
        check(res.stats["done"] == 1 and not res.issues.text(), "stats %s %s" % (res.stats, res.issues.text()))
        m.edits.restore()
        check(T.snapshot(b) == before, "restore exact")


def test_refillet_and_sharp():
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (10, 0), (15, 5), (15, 20), (0, 20)], n)
    m = model_for(b)
    m.apply(S(r=1.0))
    check(len(arcs(b)) == 3, "3 arcs")
    for t in b.GetTracks():
        t.ClearSelected()
    m2 = model_for(b)                       # board that already has arcs
    check(g.describe(m2.pieces) == "R 1.000 mm", "describe %r" % g.describe(m2.pieces))
    res = m2.apply(S(r=1.0))
    check(not res.ops, "same R -> nothing to do (%d ops)" % len(res.ops))
    m2.apply(S(r=3.0))
    rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
    check(rs == [3.0, 3.0, 3.0], "re-filleted %s" % rs)
    check(clusters(b) == 1 and tangent_ok(b), "refillet connected/tangent")
    m2.apply(S(mode=g.SHARP))
    check(not arcs(b), "sharp: no arcs")
    corners = sorted((round(T.xy(t.GetEnd())[0], 6), round(T.xy(t.GetEnd())[1], 6)) for t in segs(b))
    check((10.0, 0.0) in corners and (15.0, 5.0) in corners and (15.0, 20.0) in corners,
          "corners back exactly %s" % corners)
    check(len(segs(b)) == 4 and clusters(b) == 1, "4 segments again")
    m2.apply(S(mode=g.CHAMFER, c=1.0))
    check(not arcs(b) and len(segs(b)) == 7 and clusters(b) == 1, "chamfer from arcs: %d" % len(segs(b)))
    m2.edits.restore()
    check(len(arcs(b)) == 3 and len(segs(b)) == 4, "restore puts the arcs back")


def bus(b, n_lanes=3, pitch=0.5, turn=90.0, w=0.2, rot=0.0, reverse=()):
    """Parallel lanes going right, then turning left (up on screen) by `turn` degrees;
    lane 0 is the inner one. The whole layout is rotated by rot."""
    nets = []
    a = math.radians(turn)
    d2 = (math.cos(a), -math.sin(a))
    out2 = geo.perp(d2)                      # right-hand side of the outgoing leg = outward
    for k in range(n_lanes):
        nt = T.net(b, "L%d" % k)
        nets.append(nt)
        off = k * pitch
        start = (0.0, off)
        hit = geo.line_cross(start, (1.0, 0.0), geo.add((10.0, 0.0), geo.mul(out2, off)), d2)
        corner = geo.add(start, (hit[0], 0.0))
        end = geo.add(corner, geo.mul(d2, 10.0))
        pts = [T.rot(q, rot) for q in (start, corner, end)]
        polyline(b, pts, nt, w, flip=(0,) if k in reverse else ())
    return nets


def test_bus_concentric():
    for turn in (90.0, 45.0, 30.0, 135.0):
        for rot in (0.0, 17.0, 90.0, 233.0):
            b = pcbnew.BOARD()
            nets = bus(b, 3, 0.5, turn, rot=rot, reverse=(1,))
            m = model_for(b)
            m.apply(S(r=1.0))
            rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
            check(rs == [1.0, 1.5, 2.0], "concentric radii turn %g rot %g: %s" % (turn, rot, rs))
            cs = [arc_r(a)[1] for a in arcs(b)]
            dc = max(geo.dist(c, cs[0]) for c in cs)
            check(dc < 3e-4, "one centre (%.6f)" % dc)
            for k in range(2):
                sp = lane_spacing(b, nets[k].GetNetCode(), nets[k + 1].GetNetCode())
                sp2 = lane_spacing(b, nets[k].GetNetCode(), nets[k + 1].GetNetCode(), worst=True)
                check(abs(sp - 0.5) < 2e-3 and abs(sp2 - 0.5) < 2e-3,
                      "spacing kept %g/%g: %.4f–%.4f" % (turn, rot, sp, sp2))
            check(clusters(b) == 3 and tangent_ok(b), "bus connected")
            m.apply(S(r=1.0, ref=g.REF_OUTER))
            rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
            check(rs == [0.5, 1.0], "outer ref, inner left sharp: %s" % rs)
            m.apply(S(r=1.0, ref=g.REF_MIDDLE))
            rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
            check(rs == [0.5, 1.0, 1.5], "middle ref %s" % rs)
            m.apply(S(r=1.0, bus=g.SAME))
            rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
            check(rs == [1.0, 1.0, 1.0], "same R %s" % rs)
            sp = lane_spacing(b, nets[0].GetNetCode(), nets[1].GetNetCode(), worst=True)
            check(sp > 0.5 + 1e-3, "same R: spacing not kept in the turn (%.4f)" % sp)
            m.apply(S(mode=g.CHAMFER, c=0.6))
            for k in range(2):
                sp = lane_spacing(b, nets[k].GetNetCode(), nets[k + 1].GetNetCode())
                sp2 = lane_spacing(b, nets[k].GetNetCode(), nets[k + 1].GetNetCode(), worst=True)
                check(abs(sp - 0.5) < 2e-3 and abs(sp2 - 0.5) < 2e-3,
                      "chamfer spacing kept %g/%g: %.4f–%.4f" % (turn, rot, sp, sp2))
            check(clusters(b) == 3, "chamfer connected")
            m.edits.restore()


def test_outer_ref_negative():
    b = pcbnew.BOARD()
    bus(b, 3, 0.5, 90.0)
    m = model_for(b)
    res = m.apply(S(r=0.8, ref=g.REF_OUTER))     # inner would need 0.8 - 1.0 < 0
    check("neg" in res.issues, "negative inner radius reported")
    check(len(arcs(b)) == 2, "two arcs, inner sharp (%d)" % len(arcs(b)))


def test_short_segments():
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (0.5, 0), (0.5, -0.5)], n)
    m = model_for(b)
    res = m.apply(S(r=2.0))
    r, _c = arc_r(arcs(b)[0])
    check(abs(r - 0.5) < 1e-5, "shrunk to 0.5: %.4f" % r)
    check("short" in res.issues, "short reported")
    check(len(segs(b)) == 0 and clusters(b) == 1, "legs used up")
    res = m.apply(S(r=2.0, short=g.SKIP))
    check(not arcs(b) and "skip" in res.issues, "skip leaves it sharp")
    # zig-zag: two corners share a short middle part
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (5, 0), (6, -1), (11, -1)], n)
    m = model_for(b)
    m.apply(S(r=5.0))
    check(len(arcs(b)) == 2 and clusters(b) == 1 and tangent_ok(b), "zigzag shrink connected")
    for t in segs(b):
        check(geo.dist(T.xy(t.GetStart()), T.xy(t.GetEnd())) > 1e-4, "no zero-length leftovers")


def test_junction_via_pad():
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (10, 0), (10, -10)], n)
    T.track(b, (10, 0), (20, 0), n)              # third track at the corner (not selected)
    m = model_for(b, T.tracks(b)[:2])
    res = m.apply(S())
    check(not arcs(b) and "junction" in res.issues, "T junction left sharp")
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (10, 0), (10, -10)], n)
    T.via(b, (10, 0), n)
    m = model_for(b)
    res = m.apply(S())
    check(not arcs(b) and "junction" in res.issues, "via at the corner left sharp")
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (10, 0), (10, -10)], n)
    T.footprint(b, "R1", (10, 0), pads=(((0, 0), (1, 1)), ((3, 0), (1, 1))), nets=[n, None])
    m = model_for(b)
    res = m.apply(S())
    check(not arcs(b) and "junction" in res.issues, "pad at the corner left sharp")


def test_big_arc_kept():
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    T.arc(b, (0, 0), (5, -5), (10, 0), n)        # 180 deg
    m = model_for(b)
    res = m.apply(S(mode=g.SHARP))
    check(len(arcs(b)) == 1 and "bigarc" in res.issues, "half circle kept")


def test_units_w_and_min_angle():
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    polyline(b, [(0, 0), (10, 0), (20, -0.5), (30, -0.5), (30, -10)], n, w=0.25)
    m = model_for(b)
    m.apply(S(r=4.0, unit=g.UNIT_W, min_angle=5.0))
    rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
    check(rs == [1.0], "×W radius, the 2.9° kinks stay: %s" % rs)
    m.apply(S(r=4.0, unit=g.UNIT_W, min_angle=1.0))
    check(len(arcs(b)) == 3, "min angle 1° rounds the kinks too (%d)" % len(arcs(b)))


def test_check_vs_drc():
    b = pcbnew.BOARD()
    n = T.net(b, "A")
    o = T.net(b, "B")
    polyline(b, [(0, 0), (10, 0), (10, -10)], n, w=0.25)
    T.via(b, (10 - 1.768 / math.sqrt(2), -1.768 / math.sqrt(2)), o, d=0.6, drill=0.3)  # 0.1 mm from R=3
    ds = b.GetDesignSettings()
    ds.m_MinClearance = int(0.2e6)
    try:
        ds.GetDefault().SetClearance(int(0.2e6))
    except Exception:
        pass
    m = model_for(b, segs(b))
    res = m.apply(S(r=0.5))
    mine = "clr" in res.issues
    kicad = T.drc(b)
    check(not mine and not kicad, "small R clear: mine %s kicad %s" % (mine, kicad))
    res = m.apply(S(r=3.0))
    mine = "clr" in res.issues
    kicad = T.drc(b)
    check(mine and kicad, "big R too close to the via: mine %s kicad %s" % (res.issues.text(), kicad))
    check(abs(res.issues.d["clr"][1] - 0.1) < 0.006, "shortfall 0.1 mm: %s" % res.issues.text())


def test_check_after_changes():
    """The copper around is collected from the untouched board: arcs made by an earlier
    change are not taken for other copper."""
    b = pcbnew.BOARD()
    bus(b, 3, 0.5, 90.0)
    m = model_for(b)
    for v in (S(r=2.1, ref=g.REF_MIDDLE), S(r=2.1), S(r=0.7), S(mode=g.CHAMFER, c=1.5), S(r=3.0, bus=g.SAME)):
        res = m.apply(v)
        check(not res.issues.text(), "no false clearance problems %s: %s" % (v, res.issues.text()))


def test_drc_agreement():
    """Random corners with a via of another net inside the turn: my check and KiCad's
    DRC agree (cases within 3 µm of the limit or with touching copper are left out)."""
    rnd = random.Random(11)
    agree = total = hits = 0
    for it in range(70):
        b = pcbnew.BOARD()
        n = T.net(b, "A")
        o = T.net(b, "B")
        turn = rnd.uniform(30, 150)
        a = math.radians(turn)
        P = (20.0, 20.0)
        d2 = (math.cos(a), -math.sin(a))
        polyline(b, [(5.0, 20.0), P, geo.add(P, geo.mul(d2, 15.0))], n, w=rnd.choice([0.2, 0.25]))
        bis = geo.unit(geo.sub(d2, (1.0, 0.0)))
        R = rnd.uniform(0.5, 4.0)
        cen = geo.add(P, geo.mul(bis, R / math.cos(a / 2)))
        ang = rnd.uniform(-0.6, 0.6) * (math.pi - a) / 2
        u = geo.rot(geo.mul(bis, -1.0), math.degrees(ang))
        dv = R + rnd.choice([-1, 1]) * rnd.uniform(0.4, 0.75)
        vp = geo.add(cen, geo.mul(u, dv))
        T.via(b, vp, o, d=0.6, drill=0.3)
        ds = b.GetDesignSettings()
        ds.m_MinClearance = int(0.2e6)
        m = model_for(b, segs(b))
        if m.apply(S(r=0.1)).issues.text():
            continue                                # already too close before
        res = m.apply(S(r=R))
        short = res.issues.d.get("clr", [None, 0.0])[1] or 0.0
        if abs(short) > 0.2 - 0.003 or abs(short - 0.0) < 0.003 and short > 0:
            continue
        kicad = bool(T.drc(b))
        total += 1
        hits += kicad
        if kicad == (short > 0.003):
            agree += 1
        else:
            print("   disagree: turn %.1f R %.3f mine %.4f kicad %s" % (turn, R, short, kicad))
    print("  KiCad DRC agrees %d / %d (%d too close)" % (agree, total, hits))
    check(total >= 20 and agree == total and 5 <= hits <= total - 5,
          "drc agreement %d/%d (%d too close)" % (agree, total, hits))


def test_fuzz():
    rnd = random.Random(7)
    for it in range(150):
        b = pcbnew.BOARD()
        nets = [T.net(b, "N%d" % k) for k in range(3)]
        for nt in nets:
            p = (rnd.uniform(0, 50), rnd.uniform(0, 50))
            ang = rnd.uniform(0, 360)
            pts = [p]
            for _ in range(rnd.randint(1, 6)):
                ang += rnd.choice([-1, 1]) * rnd.choice([10, 30, 45, 60, 90, 120, 135, 150, 170, rnd.uniform(5, 175)])
                L = rnd.choice([0.3, 1.0, 3.0, rnd.uniform(0.1, 8)])
                p = (p[0] + L * math.cos(math.radians(ang)), p[1] + L * math.sin(math.radians(ang)))
                pts.append(p)
            polyline(b, pts, nt, rnd.choice([0.15, 0.2, 0.3]),
                     flip=[k for k in range(len(pts)) if rnd.random() < 0.3])
        before = T.snapshot(b)
        n0 = clusters(b)
        m = model_for(b)
        for mode in (g.ROUND, g.CHAMFER, g.SHARP, g.ROUND):
            v = S(mode=mode, r=rnd.choice([0.2, 0.5, 1.0, 3.0]), c=rnd.choice([0.2, 0.5, 2.0]),
                  short=rnd.choice([g.SHRINK, g.SKIP]), min_angle=rnd.choice([0.0, 5.0, 20.0]),
                  bus=rnd.choice([g.CONCENTRIC, g.SAME]))
            m.apply(v)
            check(clusters(b) == n0, "fuzz %d mode %d: connected (%d vs %d)" % (it, mode, clusters(b), n0))
            if mode == g.ROUND and v["min_angle"] == 0.0 and v["short"] == g.SHRINK:
                # (with a minimum angle or Skip a sharp kink may sit right at an arc end)
                check(tangent_ok(b, verbose=True), "fuzz %d tangent" % it)
            for a in arcs(b):
                r, _c = arc_r(a)
                check(r > 1e-3, "fuzz %d arc radius %g" % (it, r))
            for t in segs(b):
                check(t.GetStart() != t.GetEnd(), "fuzz %d zero-length segment" % it)
        # re-run on the result (arcs in the selection) and back to sharp
        for t in b.GetTracks():
            t.ClearSelected()
        m2 = model_for(b)
        m2.apply(S(mode=g.SHARP, min_angle=0.0))
        check(clusters(b) == n0 and not arcs(b), "fuzz %d sharp again" % it)
        m2.edits.restore()
        m.edits.restore()
        check(T.snapshot(b) == before, "fuzz %d restore" % it)


def test_speed():
    b = pcbnew.BOARD()
    base = [(0.0, 0.0)]
    for j in range(10):                      # staircase: right, up, right, up ...
        base.append((base[-1][0] + 10, base[-1][1]))
        base.append((base[-1][0], base[-1][1] - 10))
    for k in range(8):
        nt = T.net(b, "S%d" % k)
        o = k * 0.4
        polyline(b, [(x + o, y + o) for x, y in base], nt)
    via_net = T.net(b, "V")
    for k in range(50):
        T.via(b, (k * 2.0, 5.0), via_net)
    m = model_for(b)
    for rs, lim in (((0.5, 1.0, 1.5), 0.25), ((2.5, 3.0), 0.5)):
        t0 = time.time()
        for r in rs:
            m.apply(S(r=r))
        dt = (time.time() - t0) / len(rs)
        print("  %.1f ms per change (%d tracks, %d corners, %d groups, R %s)" % (
            dt * 1e3, len(m.pieces), len(m.prep.corners), len(m.prep.groups), rs))
        check(dt < lim, "speed %.3f s" % dt)
    check(len(m.prep.groups) == 19, "19 bus corners (%d)" % len(m.prep.groups))


# ---------------------------------------------------------------- GUI

def gui(shots=None):
    from fillet_o_matic import dialog as dl
    H = T.gui_harness(dl.FilletDialog)
    b = pcbnew.BOARD()
    nets = bus(b, 3, 0.5, 90.0)
    for t in T.tracks(b):
        t.SetSelected()
    before = T.snapshot(b)
    st = {}

    def s_open(d):
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "fillet_round.png"))
        check(len(arcs(b)) == 3, "applied on open")
        check(d.ro["now"].GetLabel() == "3 sharp", "now %r" % d.ro["now"].GetLabel())

    def s_values(d):
        d.f["r"].SetValue("2")
        H["settle"](d)
        rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
        check(rs == [2.0, 2.5, 3.0], "R 2 applied %s" % rs)
        d.nudge("size", 1)
        H["settle"](d)
        check(d.f["r"].GetValue() == "2.1", "nudge %r" % d.f["r"].GetValue())
        d._toggle("mode", 1)
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "fillet_chamfer.png"))
        check(not arcs(b) and len(segs(b)) == 9, "chamfer mode")
        d.nudge("size", 1)
        H["settle"](d)
        check(d.f["c"].GetValue() != "", "c nudged")
        d._toggle("mode", 2)
        H["settle"](d)
        check(len(segs(b)) == 6, "sharp mode")
        d._toggle("mode", 0)
        d.ch["bus"].SetSelection(1)
        d.on_change()
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "fillet_same.png"))
        rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
        check(rs == [2.1, 2.1, 2.1], "same R %s" % rs)
        d.ch["bus"].SetSelection(0)
        d.more.Expand()
        d.on_more()
        d.ch["ref"].SetSelection(1)
        d.on_change()
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "fillet_more.png"))
        rs = sorted(round(arc_r(a)[0], 3) for a in arcs(b))
        check(rs == [1.6, 2.1, 2.6], "middle ref %s" % rs)
        d.f["r"].SetValue("x")
        H["settle"](d)
        check("Invalid" in d.status.GetLabel(), "invalid")
        d.f["r"].SetValue("1")
        H["settle"](d)
        st["final"] = T.snapshot(b)

    H["run"](fm.FilletOMatic(), b, [s_open, s_values, lambda d: d.finish(True)])
    check(T.snapshot(b) == st.get("final"), "OK keeps")
    check(lane_spacing(b, nets[0].GetNetCode(), nets[1].GetNetCode()) > 0.499, "spacing after OK")

    b2 = pcbnew.BOARD()
    bus(b2, 2, 0.5, 45.0)
    for t in T.tracks(b2):
        t.SetSelected()
    before2 = T.snapshot(b2)
    H["run"](fm.FilletOMatic(), b2, [lambda d: H["settle"](d), lambda d: d.finish(False)])
    check(T.snapshot(b2) == before2, "Cancel restores")
    H["boxes"].clear()
    b3 = pcbnew.BOARD()
    import pcbnew as pn
    pn.GetBoard = lambda: b3
    fm.FilletOMatic().Run()
    check(H["boxes"] and "Select" in H["boxes"][0], "empty selection message")
    del before


if __name__ == "__main__":
    if os.environ.get("TDUMP"):
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ["TDUMP"]), exit=True)
    if len(sys.argv) > 1 and sys.argv[1] == "gui":
        gui(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                n0 = len(T.FAILS)
                fn()
                print("ok  " if len(T.FAILS) == n0 else "FAIL", name)
    sys.exit(T.report("fillet-o-matic"))
