# Tests of bus-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_bus.py
# GUI:  xvfb-run -a python3 test_bus.py gui [screenshot_dir]

import itertools
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
from bus_o_matic import geo  # noqa: E402
from bus_o_matic import geometry as g  # noqa: E402
from bus_o_matic import bus_o_matic as bm  # noqa: E402

check = T.check
KINDS = ("clearance", "tracks_crossing", "shorting_items", "copper_edge_clearance")


def S(**kw):
    s = dict(shape=g.STRAIGHT, side=g.TURN_LEFT, ang=90, l1=3.0, l2=4.0, l3=2.0, pitch=None, corner=g.SHARP,
             c=0.0, w=None, flip=False, check=True)
    s.update(kw)
    return s


def bus(n=4, pitch=0.5, ang=0.0, stagger=0.3, w=0.2, origin=(40.0, 50.0), b=None, select="last"):
    """n tracks from the pads of a connector (so one end is connected), in direction ang
    (deg, CCW on screen), each of two segments; the open ends staggered."""
    b = b or pcbnew.BOARD()
    nets = [T.net(b, "D%d" % k) for k in range(n)]
    d = T.rot((1.0, 0.0), -ang)
    nl = (d[1], -d[0])                                   # left of d on screen

    def at(f, l):
        return (origin[0] + d[0] * f + nl[0] * l, origin[1] + d[1] * f + nl[1] * l)

    fp = T.footprint(b, "J%d" % len(list(b.GetFootprints())), origin, ang,
                     pads=[((0.0, -(k - (n - 1) / 2.0) * pitch), (w, w)) for k in range(n)],
                     nets=nets, courtyard=None)
    fp.Reference().SetVisible(False)
    tr = []
    for k in range(n):
        lat = (k - (n - 1) / 2.0) * pitch
        t1 = T.track(b, at(0, lat), at(3, lat), nets[k], w)
        t2 = T.track(b, at(3, lat), at(5 + stagger * k, lat), nets[k], w)
        if select in ("last", "all"):
            t2.SetSelected()
        if select == "all":
            t1.SetSelected()
        tr.append(t2)
    return b, nets, tr


def model(b):
    m = bm.Model(b)
    m.load(m.selected())
    return m


def ends_by_net(b):
    """The open end of each net's track run (the point used once that is not on a pad)."""
    out = {}
    for t in T.tracks(b):
        for q in (T.xy(t.GetStart()), T.xy(t.GetEnd())):
            out.setdefault(t.GetNetname(), {}).setdefault(geo.key(q), [q, 0])[1] += 1
    res = {}
    for n, pts in out.items():
        once = [q for q, c in pts.values() if c == 1]
        res[n] = once
    return res


def polyline(b, net):
    """Track pieces of a net chained from the pad end: list of points."""
    segs = [(T.xy(t.GetStart()), T.xy(t.GetEnd())) for t in T.tracks(b) if t.GetNetname() == net]
    once = ends_by_net(b)[net]
    start = min(once, key=lambda q: min(geo.dist(q, T.xy(p.GetPosition())) for fp in b.GetFootprints()
                                        for p in fp.Pads()))
    pts = [start]
    left = list(segs)
    while left:
        for i, (a, c) in enumerate(left):
            if geo.dist(a, pts[-1]) < 1e-6:
                pts.append(c)
                break
            if geo.dist(c, pts[-1]) < 1e-6:
                pts.append(a)
                break
        else:
            break
        left.pop(i)
    # merge collinear
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        u, w = geo.sub(pts[i], out[-1]), geo.sub(pts[i + 1], pts[i])
        if abs(geo.cross(geo.unit(u), geo.unit(w))) > 1e-9 or geo.dot(u, w) < 0:
            out.append(pts[i])
    out.append(pts[-1])
    return out, len(left)


def min_gap(b, nets):
    """Smallest centre-line distance between the new parts of different nets."""
    lines = {n: polyline(b, n)[0] for n in nets}
    m = 1e9
    for a, c in itertools.combinations(nets, 2):
        for p, q in zip(lines[a], lines[a][1:]):
            for r, s in zip(lines[c], lines[c][1:]):
                m = min(m, geo.seg_seg(p, q, r, s))
    return m


# ------------------------------------------------------------------ shapes

def test_straight_squares_the_ends():
    b, nets, tr = bus(4)
    before = len(T.tracks(b))
    m = model(b)
    p = m.apply(S(l1=3.0))
    check(not p.issues.text(), "issues %s" % p.issues.text())
    check(len(T.tracks(b)) == before, "last pieces made longer, no new ones (%d)" % len(T.tracks(b)))
    xs = {n.GetNetname(): max(q[0] for q in ends_by_net(b)[n.GetNetname()]) for n in nets}
    check(all(abs(x - (45.9 + 3.0)) < 1e-6 for x in xs.values()), "ends square at 48.9: %s" % xs)
    check(abs(min_gap(b, [n.GetNetname() for n in nets]) - 0.5) < 1e-6, "pitch kept")


def test_bend_left_right():
    for side, sign in ((g.TURN_LEFT, -1), (g.TURN_RIGHT, 1)):
        for ang in (90, 45):
            b, nets, tr = bus(4)
            m = model(b)
            p = m.apply(S(shape=g.BEND, side=side, ang=ang, l1=3.0, l2=4.0))
            check(not p.issues.text(), "bend issues %s" % p.issues.text())
            names = [n.GetNetname() for n in nets]
            for nm in names:
                pts, rest = polyline(b, nm)
                check(rest == 0, "connected chain %s" % nm)
                d = geo.unit(geo.sub(pts[-1], pts[-2]))
                want = (math.cos(math.radians(ang)), sign * math.sin(math.radians(ang)))
                check(abs(d[0] - want[0]) < 1e-6 and abs(d[1] - want[1]) < 1e-6,
                      "end direction %s side %d ang %d: %s" % (nm, side, ang, d))
                check(len(pts) == 3, "pad, bend, end: %d points" % len(pts))
            gap = min_gap(b, names)
            check(abs(gap - 0.5) < 1e-6, "pitch through the bend %.6f" % gap)
            # ends on one line perpendicular to the last direction
            ends = [polyline(b, nm)[0][-1] for nm in names]
            proj = [geo.dot(e, want) for e in ends]
            check(max(proj) - min(proj) < 1e-6, "ends square after the bend")


def test_cut_corner_inner_c():
    b, nets, tr = bus(4)
    m = model(b)
    p = m.apply(S(shape=g.BEND, corner=g.CUT, c=0.3))
    check(not p.issues.text(), "issues %s" % p.issues.text())
    cuts = []
    for n in nets:
        pts, _ = polyline(b, n.GetNetname())
        for a, c in zip(pts, pts[1:]):
            d = geo.unit(geo.sub(c, a))
            if abs(abs(d[0]) - abs(d[1])) < 1e-6:
                cuts.append(geo.dist(a, c))
    check(len(cuts) == 4, "a 45° cut on every track (%d)" % len(cuts))
    check(abs(min(cuts) - 0.3) < 1e-5, "inner cut = C (%.6f)" % min(cuts))
    check(abs(min_gap(b, [n.GetNetname() for n in nets]) - 0.5) < 1e-6, "pitch kept in the cut")


def test_jog_and_uturn():
    b, nets, tr = bus(3)
    m = model(b)
    p = m.apply(S(shape=g.JOG, ang=45, l1=2, l2=3, l3=2))
    names = [n.GetNetname() for n in nets]
    check(not p.issues.text(), "jog issues %s" % p.issues.text())
    for nm in names:
        pts, _ = polyline(b, nm)
        d = geo.unit(geo.sub(pts[-1], pts[-2]))
        check(abs(d[0] - 1) < 1e-9, "jog ends straight on")
    check(abs(min_gap(b, names) - 0.5) < 1e-6, "jog pitch")
    p = m.apply(S(shape=g.UTURN, l1=2, l2=3, l3=2))
    check(not p.issues.text(), "U issues %s" % p.issues.text())
    for nm in names:
        pts, _ = polyline(b, nm)
        d = geo.unit(geo.sub(pts[-1], pts[-2]))
        check(abs(d[0] + 1) < 1e-9, "U ends going back")
    check(abs(min_gap(b, names) - 0.5) < 1e-6, "U pitch %.4f" % min_gap(b, names))
    p = m.apply(S(shape=g.UTURN, l1=2, l2=1.2, l3=2))
    check("short" in p.issues, "U-turn too tight reported")


def test_pitch_fan():
    for new in (0.3, 0.8, 1.27):
        b, nets, tr = bus(5, pitch=0.5)
        m = model(b)
        p = m.apply(S(pitch=new, l1=2.0))
        names = [n.GetNetname() for n in nets]
        check("short" not in p.issues, "fan %g issues %s" % (new, p.issues.text()))
        ends = sorted(polyline(b, nm)[0][-1][1] for nm in names)
        gaps = [c - a for a, c in zip(ends, ends[1:])]
        check(all(abs(x - new) < 1e-6 for x in gaps), "new pitch %g: %s" % (new, gaps))
        mg = min_gap(b, names)
        check(mg > min(0.5, new) - 1e-6, "fan keeps neighbours apart %.4f" % mg)
        clr = "clr" in p.issues
        check(clr == (min(0.5, new) - 0.2 < 0.2 - 1e-9), "clearance verdict for %g: %s" % (new, p.issues.text()))
        drc = T.drc(b, KINDS)
        check(bool(drc) == clr, "KiCad DRC agrees for pitch %g (%d)" % (new, len(drc)))


def test_angled_bus():
    for ang in (45.0, 90.0, 135.0, 30.0):
        b, nets, tr = bus(4, ang=ang)
        m = model(b)
        p = m.apply(S(shape=g.BEND, l1=2, l2=3, corner=g.CUT, c=0.2))
        names = [n.GetNetname() for n in nets]
        check("short" not in p.issues and "clr" not in p.issues, "angled %g issues %s" % (ang, p.issues.text()))
        mg = min_gap(b, names)
        check(abs(mg - 0.5) < 1e-5, "angled %g pitch %.6f" % (ang, mg))
        if ang != 30.0:
            check("notpar" not in p.issues, "45° multiples snap")
        check(not T.drc(b, KINDS), "angled %g KiCad DRC clean" % ang)


def test_open_end_and_flip():
    b, nets, tr = bus(3, select="all")
    m = model(b)
    check(len(m.lanes) == 3, "one lane per track (%d)" % len(m.lanes))
    check(all(abs(ln.out[0] - 1) < 1e-9 for ln in m.lanes), "continued from the open ends")
    # free stubs, open on both ends: majority / flip
    b2 = pcbnew.BOARD()
    ns = [T.net(b2, "S%d" % k) for k in range(3)]
    for k in range(3):
        T.track(b2, (10, 10 + k), (15, 10 + k), ns[k]).SetSelected()
    m2 = model(b2)
    d1 = m2.lanes[0].out
    check(all(ln.out == d1 for ln in m2.lanes), "all lanes the same way")
    m2.apply(S(flip=True))
    check(all(ln.out == (-d1[0], -d1[1]) for ln in m2.lanes), "flip: the other ends")
    m2.edits.restore()
    # a track ending on a via is not open there
    b3, nets3, tr3 = bus(2)
    T.via(b3, T.xy(tr3[0].GetEnd()), nets3[0])
    m3 = model(b3)
    p = m3.apply(S())
    check("connected" in p.issues, "via end reported as connected")


def test_clearance_check_matches_drc():
    b, nets, tr = bus(3)
    other = T.net(b, "X")
    T.track(b, (48.95, 47.0), (48.95, 53.0), other, 0.25)    # across the way (ends at 48.6)
    m = model(b)
    p = m.apply(S(l1=3.0))
    check("clr" in p.issues, "track in the way reported")
    check(bool(T.drc(b, KINDS)), "and KiCad DRC sees it")
    p = m.apply(S(l1=2.0))
    check("clr" not in p.issues, "short enough: clear (%s)" % p.issues.text())
    check(not T.drc(b, KINDS), "KiCad DRC clean too")
    T.outline(b, 30, 40, 48.5, 60)
    m = model(b)
    p = m.apply(S(l1=3.0))
    check("clr" in p.issues, "board edge reported")


def test_width_option():
    b, nets, tr = bus(3)
    m = model(b)
    n0 = len(T.tracks(b))
    m.apply(S(w=0.15, l1=2.0))
    new = [t for t in T.tracks(b) if t.GetWidth() == 150000]
    check(len(new) == 3 and len(T.tracks(b)) == n0 + 3, "new pieces with W 0.15 (%d)" % len(new))


def test_restore_exact():
    b, nets, tr = bus(5, stagger=0.4)
    before = T.snapshot(b)
    m = model(b)
    for shape in range(4):
        for corner in range(2):
            for pitch in (None, 0.3, 0.9):
                m.apply(S(shape=shape, corner=corner, c=0.2, pitch=pitch, side=shape % 2, ang=(45, 90)[corner]))
    check(T.snapshot(b) != before, "changed")
    m.edits.restore()
    check(T.snapshot(b) == before, "restore exact")


def test_against_kicad_drc():
    """Random buses with short tracks of another net put near the new path (0.02-0.35 mm
    from it): the clearance verdict per net agrees with KiCad's DRC."""
    agree = total = flagged = 0
    for seed in range(24):
        rnd = random.Random(seed)
        n = rnd.randint(2, 6)
        pitch = rnd.choice((0.4, 0.5, 0.635))
        b, nets, tr = bus(n, pitch=pitch, ang=rnd.choice((0, 90, 45, 180, 30)), stagger=rnd.uniform(0, 0.5))
        v = S(shape=rnd.randrange(4), side=rnd.randrange(2), ang=rnd.choice((45, 90)), l1=rnd.uniform(1, 5),
              l2=rnd.uniform(3, 6), l3=rnd.uniform(1, 4), corner=rnd.randrange(2), c=rnd.uniform(0, 0.5),
              pitch=rnd.choice((None, 0.45, 0.6, 1.0)))
        m = model(b)
        p = m.apply(v)
        if p.issues.text():
            m.edits.restore()
            continue
        paths = [list(x) for x in p.paths]
        segs = [(a_, c_) for path in paths for a_, c_ in zip(path, path[1:])]
        m.edits.restore()
        other = T.net(b, "X")
        for _ in range(3):
            a_, c_ = rnd.choice(segs)
            if geo.dist(a_, c_) < 0.5:
                continue
            t = rnd.uniform(0.15, 0.85)
            q = geo.add(a_, geo.mul(geo.sub(c_, a_), t))
            d = geo.unit(geo.sub(c_, a_))
            nl = (d[1], -d[0]) if rnd.random() < 0.5 else (-d[1], d[0])
            off = 0.1 + 0.1 + rnd.uniform(0.02, 0.35)
            m1 = geo.add(q, geo.mul(nl, off))
            p0, p1 = geo.sub(m1, geo.mul(d, 0.2)), geo.add(m1, geo.mul(d, 0.2))
            if min(geo.seg_seg(p0, p1, x, y) for x, y in segs) < 0.2 + 1e-3:
                continue                       # would touch another track: nets merge on load
            T.track(b, p0, p1, other, 0.2)
        old = {it.split("[")[1].split("]")[0] for _k, items in T.drc(b, KINDS) for it in items if "[D" in it}
        m = model(b)
        p = m.apply(v)
        mine = set(p.issues.items("clr"))
        kicad = set()
        for _kind, items in T.drc(b, KINDS):
            for it in items:
                if "[D" in it:
                    kicad.add(it.split("[")[1].split("]")[0])
        flagged += len(mine)
        for nm in [x.GetNetname() for x in nets]:
            if nm in old:                       # the stub is also near the old part
                continue
            total += 1
            if (nm in mine) == (nm in kicad):
                agree += 1
            else:
                check(False, "seed %d net %s: mine %s kicad %s" % (seed, nm, nm in mine, nm in kicad))
    print("    DRC fuzz: %d / %d nets agree, %d flagged" % (agree, total, flagged))
    check(flagged > 3 and total > 20, "the fuzz has near misses")


def test_speed():
    b, nets, tr = bus(16, pitch=0.4)
    for k in range(400):
        T.track(b, (60 + (k % 20), 30 + k // 20), (60.5 + (k % 20), 30 + k // 20), nets[0])
    m = model(b)
    t0 = time.time()
    m.apply(S(shape=g.UTURN, l2=8.0, corner=g.CUT, c=0.2, pitch=0.3))
    t1 = time.time()
    m.apply(S(shape=g.UTURN, l2=8.5, corner=g.CUT, c=0.2, pitch=0.3))
    t2 = time.time()
    print("    16 tracks: first %.0f ms, next %.0f ms" % ((t1 - t0) * 1e3, (t2 - t1) * 1e3))
    check(t2 - t1 < 0.5, "speed")


# ------------------------------------------------------------------------ GUI

def gui(shots=None):
    from bus_o_matic import dialog as dl
    H = T.gui_harness(dl.BusDialog)
    b, nets, tr = bus(4)
    names = [n.GetNetname() for n in nets]
    before = T.snapshot(b)
    st = {}

    def s_open(d):
        H["settle"](d)
        check(T.snapshot(b) != before, "applied on open")
        check(d.ro["now"].GetLabel() == "4 tracks, P 0.500", "now %r" % d.ro["now"].GetLabel())
        H["shot"](d, shots and os.path.join(shots, "bus_straight.png"))

    def s_values(d):
        d._toggle("shape", 1)
        d.f["l1"].SetValue("2")
        H["settle"](d)
        pts, _ = polyline(b, names[0])
        check(len(pts) == 3, "bend from the dialog (%d)" % len(pts))
        d.ch["corner"].SetSelection(1)
        d.f["c"].SetValue("0.3")
        d.on_change()
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "bus_bend.png"))
        d.nudge("pitch", -1)
        H["settle"](d)
        check(d.f["pitch"].GetValue() == "0.25", "pitch nudge from keep %r" % d.f["pitch"].GetValue())
        check(d.warn.IsShown(), "pitch 0.25 too close: warning")
        d.f["pitch"].SetValue("0.6")
        d._toggle("shape", 3)
        d._toggle("side", 1)
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "bus_uturn.png"))
        d._toggle("shape", 2)
        d.ch["ang"].SetSelection(0)
        d.more.Expand()
        d.on_more()
        d.on_change()
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "bus_more.png"))
        d.f["l1"].SetValue("x")
        H["settle"](d)
        check("Invalid" in d.status.GetLabel(), "invalid")
        d.f["l1"].SetValue("3")
        H["settle"](d)
        st["final"] = T.snapshot(b)

    H["run"](bm.BusOMatic(), b, [s_open, s_values, lambda d: d.finish(True)])
    check(T.snapshot(b) == st.get("final"), "OK keeps")

    b2, nets2, tr2 = bus(3)
    before2 = T.snapshot(b2)

    def c_change(d):
        d._toggle("shape", 1)
        H["settle"](d)
        check(T.snapshot(b2) != before2, "changed")

    H["run"](bm.BusOMatic(), b2, [c_change, lambda d: d.finish(False)])
    check(T.snapshot(b2) == before2, "Cancel restores")
    H["boxes"].clear()
    b3 = pcbnew.BOARD()
    pcbnew.GetBoard = lambda: b3
    bm.BusOMatic().Run()
    check(H["boxes"] and "Select" in H["boxes"][0], "empty selection message")


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
    sys.exit(T.report("bus-o-matic"))
