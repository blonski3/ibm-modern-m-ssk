# Tests of stitch-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_stitch.py
# GUI:  xvfb-run -a python3 test_stitch.py gui [screenshot_dir]

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
from stitch_o_matic import geo  # noqa: E402
from stitch_o_matic import geometry as g  # noqa: E402
from stitch_o_matic import stitch_o_matic as sm  # noqa: E402

check = T.check
DRC_KINDS = ("clearance", "hole_clearance", "hole_to_hole", "holes_co_located", "copper_edge_clearance",
             "shorting_items")


def S(**kw):
    s = dict(mode=g.FENCE, side=g.BOTH, pitch=1.0, offset=0.8, fpitch=2.0, margin=0.5, rpitch=2.0, inset=1.0,
             d=0.0, drill=0.0, stagger=False, hexa=True, rows=1, row_gap=0.8, end=0.0, fit=False, inside=False,
             netname="GND")
    s.update(kw)
    return s


def board(w=60, h=40):
    b = pcbnew.BOARD()
    gnd = T.net(b, "GND")
    sig = T.net(b, "SIG")
    T.outline(b, 0, 0, w, h)
    ds = b.GetDesignSettings()
    ds.m_MinClearance = int(0.2e6)
    return b, gnd, sig


def vias(b, net=None):
    return [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and (net is None or t.GetNetname() == net)]


def model(b, items=()):
    for t in items:
        t.SetSelected()
    m = sm.Model(b)
    m.load()
    return m


def pos(v):
    return T.xy(v.GetPosition())


def min_pair(ps):
    best = float("inf")
    for i in range(len(ps)):
        for j in range(i + 1, len(ps)):
            best = min(best, geo.dist(ps[i], ps[j]))
    return best


# ---------------------------------------------------------------- fence

def test_fence_straight():
    b, gnd, sig = board()
    t = T.track(b, (10, 20), (50, 20), sig, 0.25)
    m = model(b, [t])
    r = m.apply(S(pitch=1.0, offset=0.8))
    vs = vias(b, "GND")
    check(len(vs) == 82, "41 per side: %d" % len(vs))
    check(all(abs(abs(pos(v)[1] - 20) - 0.8) < 1e-6 for v in vs), "offset 0.8")
    xs = sorted(pos(v)[0] for v in vs if pos(v)[1] < 20)
    check(all(abs(b_ - a - 1.0) < 1e-6 for a, b_ in zip(xs, xs[1:])), "pitch 1.0")
    check(abs(r["gap"] - (0.8 - 0.3 - 0.125)) < 1e-9, "gap readout %s" % r["gap"])
    check(not r["issues"].text(), "no problems %s" % r["issues"].text())
    check(not T.drc(b, DRC_KINDS), "KiCad DRC clean")
    m.apply(S(pitch=1.0, offset=0.8, side=g.RIGHT))
    check(len(vias(b)) == 41 and all(pos(v)[1] > 20 for v in vias(b)), "right side = below (y down)")
    m.apply(S(pitch=1.0, offset=0.8, side=g.LEFT, end=2.0))
    xs = sorted(pos(v)[0] for v in vias(b))
    check(len(xs) == 37 and abs(xs[0] - 12) < 1e-6, "end margin %d %s" % (len(xs), xs[:2]))
    m.apply(S(pitch=1.0, offset=0.8, stagger=True))
    up = sorted(pos(v)[0] for v in vias(b) if pos(v)[1] < 20)
    dn = sorted(pos(v)[0] for v in vias(b) if pos(v)[1] > 20)
    check(abs(dn[0] - up[0] - 0.5) < 1e-6 or abs(up[0] - dn[0] - 0.5) < 1e-6, "stagger P/2")
    m.apply(S(pitch=1.0, offset=0.8, rows=2, row_gap=0.9))
    ys = sorted({round(abs(pos(v)[1] - 20), 6) for v in vias(b)})
    check(ys == [0.8, 1.7], "two rows %s" % ys)
    m.apply(S(pitch=1.3, offset=0.8, fit=True, side=g.LEFT))
    xs = sorted(pos(v)[0] for v in vias(b))
    st = [b_ - a for a, b_ in zip(xs, xs[1:])]
    check(abs(xs[0] - 10) < 1e-6 and abs(xs[-1] - 50) < 1e-6 and max(st) - min(st) < 1e-5 and st[0] <= 1.3,
          "fit: even from end to end %s" % st[:2])
    r = m.apply(S(pitch=1.0, offset=0.5))
    check("close" in r["issues"], "too close reported")
    m.clear()
    check(not vias(b), "clear removes all")


def test_fence_corner_and_arc():
    b, gnd, sig = board()
    pts = [(10, 30), (30, 30), (30, 10), (45, 10)]
    ts = [T.track(b, a, c, sig, 0.2) for a, c in zip(pts, pts[1:])]
    ts.append(T.arc(b, (45, 10), (49.1421, 11.7157), (50.8579, 15.8579), sig, 0.2))
    m = model(b, ts)
    m.apply(S(pitch=1.0, offset=1.0))
    vs = [pos(v) for v in vias(b)]
    path = []
    for t in ts:
        if t.GetClass() == "PCB_ARC":
            q = geo.arc_points(T.xy(t.GetStart()), T.xy(t.GetMid()), T.xy(t.GetEnd()), 64)
            path += list(zip(q, q[1:]))
        else:
            path.append((T.xy(t.GetStart()), T.xy(t.GetEnd())))
    dmin = min(min(geo.pt_seg(p, a, c) for a, c in path) for p in vs)
    check(dmin > 1.0 - 1e-3, "no via closer than O to the path: %.4f" % dmin)
    check(min_pair(vs) >= 0.6 + 0.0, "vias apart %.3f" % min_pair(vs))
    check(len(vs) > 90, "both sides around the corners (%d)" % len(vs))
    check(not T.drc(b, DRC_KINDS), "KiCad DRC clean")


def test_fence_skips_pads_and_holes():
    b, gnd, sig = board()
    other = T.net(b, "VCC")
    t = T.track(b, (10, 20), (50, 20), sig, 0.25)
    T.footprint(b, "R1", (30, 21.2), pads=(((-1, 0), (1.0, 1.0)), ((1, 0), (1.0, 1.0))), nets=[other, gnd])
    T.via(b, (20, 18.9), gnd)                       # an existing GND via near the fence line
    m = model(b, [t])
    r = m.apply(S(pitch=1.0, offset=0.8))
    sk = r["skipped"]
    check(sk.get("pad", 0) == 2, "the two on the pads left out, the one between them fits %s" % sk)
    check(sk.get("hole", 0) >= 1, "existing via: hole to hole %s" % sk)
    check(not T.drc(b, DRC_KINDS), "KiCad DRC clean %s" % T.drc(b, DRC_KINDS))


def test_replace_old_fence():
    b, gnd, sig = board()
    t = T.track(b, (10, 20), (50, 20), sig, 0.25)
    m = model(b, [t])
    m.apply(S(pitch=1.0))
    first = len(vias(b))
    for x in b.GetTracks():
        x.ClearSelected()
    # select the track and its fence again, run with another pitch
    t.SetSelected()
    for v in vias(b):
        v.SetSelected()
    m2 = sm.Model(b)
    m2.load()
    check(len(m2.free) == first, "old fence recognised (%d)" % len(m2.free))
    m2.apply(S(pitch=2.0))
    check(len(vias(b)) == 42, "replaced: %d" % len(vias(b)))
    before = len(vias(b))
    m2.clear()
    check(len(vias(b)) == first, "cancel puts the old fence back (%d vs %d)" % (len(vias(b)), first))
    del before


def test_cancel_exact():
    b, gnd, sig = board()
    t = T.track(b, (10, 20), (50, 20), sig, 0.25)
    T.via(b, (5, 5), gnd)
    snap = T.snapshot(b)
    m = model(b, [t])
    for p in (1.0, 0.7, 2.0, 1.5):
        m.apply(S(pitch=p))
    m.clear()
    check(T.snapshot(b) == snap, "restore exact")


# ---------------------------------------------------------------- fill / ring

def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def test_fill_zone():
    b, gnd, sig = board()
    z = T.zone(b, rect(10, 10, 30, 30), gnd)
    T.footprint(b, "U1", (20, 20), pads=(((0, 0), (3.0, 3.0)),), nets=[sig])
    z.SetSelected()
    m = model(b)
    check(m.default_mode() == g.FILL, "zone selected -> Fill")
    r = m.apply(S(mode=g.FILL, fpitch=2.0, margin=0.5, hexa=False))
    vs = [pos(v) for v in vias(b)]
    check(all(10 + 0.8 - 1e-9 <= x <= 30 - 0.8 + 1e-9 and 10.8 - 1e-9 <= y <= 29.2 + 1e-9 for x, y in vs),
          "inside with margin")
    check(all(abs(x / 2 - round(x / 2)) < 1e-9 for x, y in vs), "absolute 2 mm grid")
    check(r["skipped"].get("pad", 0) == 1, "the grid point on the pad left out %s" % r["skipped"])
    check(len(vs) == 80, "9 x 9 - 1: %d" % len(vs))
    m.apply(S(mode=g.FILL, fpitch=2.0, margin=0.5, hexa=True))
    ys = sorted({round(y, 6) for x, y in (pos(v) for v in vias(b))})
    check(abs(ys[1] - ys[0] - math.sqrt(3)) < 1e-6, "hex rows %s" % ys[:2])
    check(not T.drc(b, DRC_KINDS), "KiCad DRC clean")


def test_ring_outline():
    b, gnd, sig = board(50, 30)
    m = model(b)
    check(m.default_mode() == g.RING, "nothing selected -> Ring")
    r = m.apply(S(mode=g.RING, rpitch=2.0, inset=1.0))
    vs = [pos(v) for v in vias(b)]
    dist_edge = [min(x, y, 50 - x, 30 - y) for x, y in vs]
    check(all(abs(d - 1.0) < 1e-6 or d > 1.0 for d in dist_edge) and min(dist_edge) > 1 - 1e-6,
          "inset 1 mm (min %.4f)" % min(dist_edge))
    check(76 <= len(vs) <= 80, "about perimeter / 2: %d" % len(vs))
    d = sorted(min(geo.dist(p, q) for q in vs if q is not p) for p in vs)
    check(d[-1] - d[0] < 0.1, "evenly spaced %.3f–%.3f" % (d[0], d[-1]))
    check(not r["issues"].text(), "%s" % r["issues"].text())
    check(not T.drc(b, DRC_KINDS), "KiCad DRC clean %s" % T.drc(b, DRC_KINDS))


def test_ring_rounded_and_zone():
    b = pcbnew.BOARD()
    gnd = T.net(b, "GND")
    # rounded rectangle outline from segments and arcs
    R = 3.0
    W, H = 40.0, 25.0
    segs = [((R, 0), (W - R, 0)), ((W, R), (W, H - R)), ((W - R, H), (R, H)), ((0, H - R), (0, R))]
    for a, c in segs:
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(T.V(a))
        s.SetEnd(T.V(c))
        s.SetLayer(pcbnew.Edge_Cuts)
        b.Add(s)
    for c, a0 in (((W - R, R), -90), ((W - R, H - R), 0), ((R, H - R), 90), ((R, R), 180)):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        st = (c[0] + R * math.cos(math.radians(a0)), c[1] + R * math.sin(math.radians(a0)))
        md = (c[0] + R * math.cos(math.radians(a0 + 45)), c[1] + R * math.sin(math.radians(a0 + 45)))
        en = (c[0] + R * math.cos(math.radians(a0 + 90)), c[1] + R * math.sin(math.radians(a0 + 90)))
        s.SetArcGeometry(T.V(st), T.V(md), T.V(en))
        s.SetLayer(pcbnew.Edge_Cuts)
        b.Add(s)
    m = model(b)
    check(len(m.outlines) == 1, "one closed outline (%d)" % len(m.outlines))
    m.apply(S(mode=g.RING, rpitch=1.5, inset=0.8))
    vs = [pos(v) for v in vias(b)]
    ol = m.outlines[0]
    de = [min(geo.pt_seg(p, a, c) for a, c in zip(ol, ol[1:] + ol[:1])) for p in vs]
    check(min(de) > 0.8 - 0.01 and max(de) < 0.8 + 0.01, "inset along arcs %.3f–%.3f" % (min(de), max(de)))
    check(min_pair(vs) > 1.3, "no bunching in the corners %.3f" % min_pair(vs))
    m.clear()
    # zone ring
    z = T.zone(b, rect(10, 8, 30, 18), gnd)
    z.SetSelected()
    m2 = model(b)
    m2.apply(S(mode=g.RING, rpitch=1.0, inset=0.5))
    vs = [pos(v) for v in vias(b)]
    check(all(10.5 - 1e-6 <= x <= 29.5 + 1e-6 and 8.5 - 1e-6 <= y <= 17.5 + 1e-6 for x, y in vs) and len(vs) == 56,
          "ring inside the zone (%d)" % len(vs))


def test_inside_zone():
    b, gnd, sig = board()
    t = T.track(b, (10, 20), (50, 20), sig, 0.25)
    T.zone(b, rect(5, 10, 30, 30), gnd)
    m = model(b, [t])
    r = m.apply(S(pitch=1.0, inside=True))
    xs = [pos(v)[0] for v in vias(b)]
    check(xs and max(xs) <= 30 and r["skipped"].get("zone", 0) > 0, "only inside the GND zone")
    r = m.apply(S(pitch=1.0, inside=True, netname="SIG"))
    check("nozone" in r["issues"] and not vias(b), "no SIG zone reported")


def test_fuzz():
    rnd = random.Random(5)
    for it in range(25):
        b, gnd, sig = board()
        other = T.net(b, "VCC")
        p = (rnd.uniform(15, 45), rnd.uniform(10, 30))
        pts = [p]
        ang = rnd.uniform(0, 360)
        for _ in range(rnd.randint(1, 5)):
            ang += rnd.choice([-1, 1]) * rnd.choice([30, 45, 90, 120, rnd.uniform(10, 150)])
            L = rnd.uniform(1, 12)
            p = (p[0] + L * math.cos(math.radians(ang)), p[1] + L * math.sin(math.radians(ang)))
            pts.append(p)
        ts = [T.track(b, a, c, sig, 0.2) for a, c in zip(pts, pts[1:])]
        for _ in range(4):
            T.via(b, (rnd.uniform(5, 55), rnd.uniform(5, 35)), rnd.choice([gnd, other]))
        snap = T.snapshot(b)
        base = {(k, tuple(sorted(x))) for k, x in T.drc(b, DRC_KINDS)}
        m = model(b, ts)
        v = S(pitch=rnd.choice([0.8, 1.0, 1.5]), offset=rnd.choice([0.7, 1.0, 1.5]),
              stagger=rnd.random() < 0.5, rows=rnd.choice([1, 2]), side=rnd.choice([g.BOTH, g.LEFT, g.RIGHT]))
        m.apply(v)
        vs = [pos(x) for x in vias(b) if x.GetNetname() == "GND"]
        made = len(vias(b)) - 4
        check(made > 0, "fuzz %d made vias" % it)
        bad = [x for x in T.drc(b, DRC_KINDS) if (x[0], tuple(sorted(x[1]))) not in base]
        check(not bad, "fuzz %d KiCad DRC %s" % (it, bad[:1]))
        del vs
        m.clear()
        check(T.snapshot(b) == snap, "fuzz %d restore" % it)


def test_speed():
    b, gnd, sig = board(100, 80)
    z = T.zone(b, rect(5, 5, 95, 75), gnd)
    for k in range(40):
        T.footprint(b, "R%d" % k, (10 + (k % 8) * 10, 10 + (k // 8) * 12), nets=[sig, gnd])
    z.SetSelected()
    m = model(b)
    t0 = time.time()
    r = m.apply(S(mode=g.FILL, fpitch=1.5, margin=0.5))
    t1 = time.time()
    m.apply(S(mode=g.FILL, fpitch=1.4, margin=0.5))
    t2 = time.time()
    print("  fill: %d vias, first %.0f ms (grids), next %.0f ms" % (len(r["points"]), (t1 - t0) * 1e3,
                                                                    (t2 - t1) * 1e3))
    check(t2 - t1 < 1.0, "fill speed %.2f s" % (t2 - t1))
    t = T.track(b, (5, 40), (95, 40), sig)
    z.ClearSelected()
    m = model(b, [t])
    m.apply(S())
    t0 = time.time()
    m.apply(S(pitch=0.9))
    dt = time.time() - t0
    print("  fence 90 mm: %.0f ms" % (dt * 1e3))
    check(dt < 0.3, "fence speed %.2f" % dt)


# ---------------------------------------------------------------- GUI

def gui(shots=None):
    from stitch_o_matic import dialog as dl
    H = T.gui_harness(dl.StitchDialog)
    b, gnd, sig = board()
    t = T.track(b, (10, 20), (50, 20), sig, 0.25)
    T.track(b, (50, 20), (55, 15), sig, 0.25).SetSelected()
    t.SetSelected()
    st = {}

    def s_open(d):
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "stitch_fence.png"))
        check(len(vias(b)) > 80, "fence on open (%d)" % len(vias(b)))
        check(d.net_ch.GetStringSelection() == "GND", "GND chosen")

    def s_values(d):
        d.f["pitch"].SetValue("2")
        H["settle"](d)
        n2 = len(vias(b))
        check(40 < n2 < 60, "pitch 2 -> %d" % n2)
        d.nudge("O", 1)
        H["settle"](d)
        check(d.f["offset"].GetValue() == "0.9", "offset nudge %r" % d.f["offset"].GetValue())
        d.f["d"].SetValue("0.5")
        H["settle"](d)
        check(all(abs(v.GetWidth() - 500000) < 2 for v in vias(b)), "via D 0.5")
        d.f["d"].SetValue("")
        d._toggle("mode", 2)
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "stitch_ring.png"))
        check(len(vias(b)) > 60, "ring mode (%d)" % len(vias(b)))
        d._toggle("mode", 0)
        d.more.Expand()
        d.on_more()
        d.c["rows"].SetValue("2")
        d.cb["stagger"].SetValue(True)
        d.on_change()
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "stitch_more.png"))
        d.f["offset"].SetValue("0.4")
        H["settle"](d)
        check(d.warn.IsShown(), "too close warning")
        d.f["offset"].SetValue("0.8")
        H["settle"](d)
        st["n"] = len(vias(b))

    H["run"](sm.StitchOMatic(), b, [s_open, s_values, lambda d: d.finish(True)])
    check(len(vias(b)) == st.get("n"), "OK keeps")
    b2, gnd2, sig2 = board()
    snap = T.snapshot(b2)
    H["run"](sm.StitchOMatic(), b2, [lambda d: H["settle"](d), lambda d: d.finish(False)])
    check(T.snapshot(b2) == snap, "Cancel restores (ring)")


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
    sys.exit(T.report("stitch-o-matic"))
