# Tests of geometry.py without KiCad:  python3 -m pytest -q test_geometry.py
# (or python3 test_geometry.py). Every scenario is run for many bus angles.

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402

ANGLES = [0, 7.5, 30, 45, 60, 90, 120, 135, 180, 213, 270, 315, 359]


def rot(p, ang, c=(0.0, 0.0)):
    a = math.radians(ang)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a), c[1] + x * math.sin(a) + y * math.cos(a))


class Board:
    """Tiny board model: segments + via points, with the callbacks analyze() needs."""

    def __init__(self):
        self.segs = []
        self.vias = []           # (net, point)
        self.n = 0

    def seg(self, net, a, b, w=0.2, layer=0):
        self.n += 1
        s = g.Seg("t%d" % self.n, net, layer, a, b, w)
        self.segs.append(s)
        return s

    def tracks_at(self, net, layer, p):
        k = g.key(p)
        return [s for s in self.segs if s.net == net and s.layer == layer and (g.key(s.a) == k or g.key(s.b) == k)]

    def anchored(self, net, layer, p):
        return any(n == net and math.dist(q, p) < 1e-6 for n, q in self.vias)

    def apply(self, res):
        out = Board()
        out.vias = list(self.vias)
        for s in self.segs:
            if s.id in res["moves"]:
                a, b, w = res["moves"][s.id]
                out.segs.append(g.Seg(s.id, s.net, s.layer, a, b, w))
            else:
                out.segs.append(g.Seg(s.id, s.net, s.layer, s.a, s.b, s.w))
        for k, (net, layer, a, b, w) in enumerate(res["new"]):
            out.segs.append(g.Seg("new%d" % k, net, layer, a, b, w))
        return out

    def terminals(self, net):
        """End points of the net's track chain that touch only one segment (rounded)."""
        cnt = {}
        for s in self.segs:
            if s.net == net:
                for p in (s.a, s.b):
                    cnt[g.key(p)] = cnt.get(g.key(p), 0) + 1
        return sorted(k for k, c in cnt.items() if c == 1)

    def connected(self, net):
        segs = [s for s in self.segs if s.net == net]
        comps = g._chains(segs)
        return len(comps) == 1


def bus_board(ang, offsets, ends=("slide", "slide"), length=6.0, w=0.2, widths=None, lead=2.0):
    """A bus along angle ang: lane k at offset offsets[k] from the axis, from s=0 to
    s=length. Each end: 'slide' = a 45 deg lead to a fixed terminal, 'via' = a via
    right at the lane end, 'straight' = a collinear continuation, 'free' = nothing,
    'perp' = a 90 deg lead."""
    b = Board()
    sel = []
    for k, o in enumerate(offsets):
        net = "N%d" % k
        wk = widths[k] if widths else w
        A, B = (0.0, o), (length, o)
        sel.append(b.seg(net, rot(A, ang), rot(B, ang), wk))
        for end, P, sgn in ((ends[0], A, -1), (ends[1], B, 1)):
            if end == "slide":
                Q = (P[0] + sgn * lead, P[1] + lead)    # 45 deg away (to +normal)
                b.seg(net, rot(P, ang), rot(Q, ang), wk)
                b.vias.append((net, rot(Q, ang)))
            elif end == "perp":
                Q = (P[0], P[1] + (lead + 3 * k))
                b.seg(net, rot(P, ang), rot(Q, ang), wk)
            elif end == "via":
                b.vias.append((net, rot(P, ang)))
            elif end == "straight":
                Q = (P[0] + sgn * lead, P[1])
                b.seg(net, rot(P, ang), rot(Q, ang), wk)
                b.vias.append((net, rot(Q, ang)))
    return b, sel


S0 = dict(mode=g.MODE_PITCH, value=0.5, width=0, keep=g.KEEP_FIRST, ends=g.ENDS_SLIDE, shift=0.0,
          snap=0.0)


def run(b, sel, **kw):
    bus = g.analyze(sel, b.tracks_at, b.anchored)
    s = dict(S0, **kw)
    res = g.plan(bus, s)
    return bus, res, b.apply(res)


def new_offsets(bus, nb):
    """Offsets of the lanes after the change, measured on the result board."""
    ids = [[sg.id for sg in L["segs"]] for L in bus.lanes]
    by = {s.id: s for s in nb.segs}
    out = []
    for lane in ids:
        os_ = [(g.dot(by[i].a, bus.n) + g.dot(by[i].b, bus.n)) / 2 for i in lane]
        out.append(sum(os_) / len(os_))
    return out


def angle_of(s):
    return math.degrees(math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0])) % 180


def check_common(b, nb, bus, res):
    for k in range(len(bus.lanes)):
        net = bus.lanes[k]["net"]
        assert nb.connected(net), "net %s split" % net
        assert b.terminals(net) == nb.terminals(net) or not b.vias, "terminals of %s moved" % net
    for s in nb.segs:
        assert s.length() > 1e-4, "zero-length segment %s" % s.id


# ---------------------------------------------------------------- tests

def test_measure_any_angle():
    for ang in ANGLES:
        b, sel = bus_board(ang, [0, 0.4, 0.9, 1.3])
        bus = g.analyze(sel, b.tracks_at, b.anchored)
        assert len(bus.lanes) == 4, ang
        p, gp = g.measure(bus.lanes)
        assert [round(x, 6) for x in p] == [0.4, 0.5, 0.4], (ang, p)
        assert [round(x, 6) for x in gp] == [0.2, 0.3, 0.2], (ang, gp)
        assert len(bus.issues) == 0, bus.issues.text()


def test_lane_order_top_or_left():
    b, sel = bus_board(0, [3, 1, 2])
    bus = g.analyze(sel, b.tracks_at, b.anchored)
    assert [L["net"] for L in bus.lanes] == ["N1", "N2", "N0"]      # top first (y down)
    b, sel = bus_board(90, [3, 1, 2])          # vertical: n points right -> left first
    bus = g.analyze(sel, b.tracks_at, b.anchored)
    xs = [L["segs"][0].a[0] for L in bus.lanes]
    assert xs == sorted(xs)


def test_pitch_slide_all_angles_all_keeps():
    for ang in ANGLES:
        for keep in (g.KEEP_FIRST, g.KEEP_CENTER, g.KEEP_LAST):
            b, sel = bus_board(ang, [0, 0.37, 0.9, 1.21, 1.9])
            bus, res, nb = run(b, sel, keep=keep, value=0.45)
            assert len(res["issues"]) == 0, (ang, keep, res["issues"].text())
            o = new_offsets(bus, nb)
            p = [o[k + 1] - o[k] for k in range(len(o) - 1)]
            assert all(abs(x - 0.45) < 1e-6 for x in p), (ang, keep, p)
            lo = [L["o"] for L in bus.lanes]
            if keep == g.KEEP_FIRST:
                assert abs(o[0] - lo[0]) < 1e-6
            if keep == g.KEEP_LAST:
                assert abs(o[-1] - lo[-1]) < 1e-6
            if keep == g.KEEP_CENTER:
                assert abs((o[0] + o[-1]) / 2 - (lo[0] + lo[-1]) / 2) < 1e-6
            check_common(b, nb, bus, res)
            # sliding keeps the 45 deg leads at 45 deg and adds no segments
            assert not res["new"]
            for s in nb.segs:
                if s.id in res["moves"] and s.id not in [x.id for x in sel]:
                    old = next(t for t in b.segs if t.id == s.id)
                    assert abs(angle_of(s) - angle_of(old)) < 1e-6


def test_gap_mode_mixed_widths():
    for ang in ANGLES:
        b, sel = bus_board(ang, [0, 0.5, 1.2], widths=[0.2, 0.4, 0.15])
        bus, res, nb = run(b, sel, mode=g.MODE_GAP, value=0.2)
        o = new_offsets(bus, nb)
        _p, gp = g.measure([dict(o=x) for x in o], [L["w"] for L in bus.lanes])
        assert all(abs(x - 0.2) < 1e-6 for x in gp), (ang, gp)
        check_common(b, nb, bus, res)


def test_width_override_changes_gap_and_lane_width():
    b, sel = bus_board(30, [0, 0.5, 1.0])
    bus, res, nb = run(b, sel, mode=g.MODE_GAP, value=0.15, width=0.3)
    o = new_offsets(bus, nb)
    assert all(abs((o[k + 1] - o[k]) - 0.45) < 1e-6 for k in range(2))
    for s in sel:
        assert abs(res["moves"][s.id][2] - 0.3) < 1e-9


def test_vias_at_lane_ends_make_45_jogs():
    for ang in ANGLES:
        b, sel = bus_board(ang, [0, 0.3, 0.8], ends=("via", "via"))
        bus, res, nb = run(b, sel, value=0.5, keep=g.KEEP_FIRST)
        moved = sum(1 for d in res["deltas"] if abs(d) > 1e-9)
        assert len(res["new"]) == 2 * moved and moved >= 1, (ang, len(res["new"]))
        for (_net, _l, a, bb, _w) in res["new"]:
            d = g.unit(g.sub(bb, a))
            assert abs(abs(g.dot(d, bus.u)) - math.sqrt(0.5)) < 1e-6, "jog not 45 deg"
        o = new_offsets(bus, nb)
        assert all(abs((o[k + 1] - o[k]) - 0.5) < 1e-6 for k in range(2))
        check_common(b, nb, bus, res)
        # via positions are terminals and did not move
        for net, q in b.vias:
            assert any(g.key(q) in (g.key(s.a), g.key(s.b)) for s in nb.segs if s.net == net)


def test_straight_continuation_and_free_ends():
    b, sel = bus_board(45, [0, 0.3, 0.8], ends=("straight", "free"))
    bus, res, nb = run(b, sel, value=0.6)
    assert len(res["new"]) == 2                 # jogs only at the straight side of lanes 2, 3
    check_common(b, nb, bus, res) if False else None
    for L in bus.lanes:
        assert nb.connected(L["net"])


def test_stretch_keeps_neighbour_end():
    for ang in (0, 45, 200):
        b, sel = bus_board(ang, [0, 0.3, 0.8], ends=("slide", "perp"))
        bus, res, nb = run(b, sel, value=0.5, ends=g.ENDS_STRETCH)
        assert not res["new"]
        check_common(b, nb, bus, res)
        o = new_offsets(bus, nb)
        assert abs(o[2] - o[1] - 0.5) < 1e-6


def test_perpendicular_neighbour_slides():
    b, sel = bus_board(10, [0, 0.3, 0.8], ends=("perp", "perp"))
    bus, res, nb = run(b, sel, value=0.5)
    assert not res["new"] and len(res["issues"]) == 0, res["issues"].text()
    for L in bus.lanes:
        assert nb.connected(L["net"])


def test_jog_too_short_reported():
    b, sel = bus_board(0, [0, 0.3, 0.8], ends=("via", "via"), length=0.5)
    _bus, res, _nb = run(b, sel, value=1.0)
    assert "short" in res["issues"], res["issues"].text()


def test_flip_falls_back_to_jog():
    # lead of 0.3 mm, lane moved by 1 mm against the lead direction -> slide impossible
    b, sel = bus_board(0, [0, 0.2], lead=0.3)
    _bus, res, nb = run(b, sel, value=0.8, keep=g.KEEP_FIRST)
    # lane 2 moves down by 0.6 mm, past the far end of its 0.3 mm leads -> jog instead
    assert "flip" in res["issues"] and len(res["new"]) == 2, res["issues"].text()
    for net in ("N0", "N1"):
        assert nb.connected(net)


def test_shift_and_snap():
    b, sel = bus_board(0, [0.013, 0.4, 0.9])
    bus, res, nb = run(b, sel, value=0.4, shift=0.25, snap=0.05)
    o = new_offsets(bus, nb)
    assert abs(o[0] - 0.25) < 1e-6, o     # 0.013 + 0.25 = 0.263 -> snapped to 0.25


def test_multi_runs_use_longest():
    b, sel = bus_board(0, [0, 0.4])
    extra = b.seg("N0", (10, 3), (11, 3))
    bus = g.analyze(sel + [extra], b.tracks_at, b.anchored)
    assert len(bus.lanes) == 2 and "multi" in bus.issues


def test_one_lane_issue():
    b, sel = bus_board(0, [0])
    bus = g.analyze(sel, b.tracks_at, b.anchored)
    assert "one_lane" in bus.issues
    assert g.plan(bus, S0)["moves"] == {}


def test_chain_of_collinear_segments():
    for ang in (0, 33, 90):
        b, sel = bus_board(ang, [0, 0.4, 1.0])
        # split lane 2 into three collinear pieces
        s = sel[1]
        m1, m2 = g.add(s.a, g.mul(g.sub(s.b, s.a), 0.3)), g.add(s.a, g.mul(g.sub(s.b, s.a), 0.7))
        b.segs.remove(s)
        parts = [b.seg(s.net, s.a, m1), b.seg(s.net, m1, m2), b.seg(s.net, m2, s.b)]
        sel2 = [sel[0]] + parts + [sel[2]]
        bus, res, nb = run(b, sel2, value=0.5)
        assert len(bus.lanes) == 3 and len(res["issues"]) == 0, res["issues"].text()
        assert nb.connected("N1")
        o = new_offsets(bus, nb)
        assert abs(o[1] - o[0] - 0.5) < 1e-6 and abs(o[2] - o[1] - 0.5) < 1e-6


def test_selection_with_leads_included():
    # user drags a box over everything: leads (45 deg) are selected too
    for ang in ANGLES:
        b, sel = bus_board(ang, [0, 0.33, 0.71, 1.2])
        bus, res, nb = run(b, list(b.segs), value=0.4)
        assert len(bus.lanes) == 4 and bus.ignored == 8, (ang, bus.ignored)
        o = new_offsets(bus, nb)
        assert all(abs((o[k + 1] - o[k]) - 0.4) < 1e-6 for k in range(3))
        check_common(b, nb, bus, res)


def test_copper_check():
    b, sel = bus_board(0, [0, 0.4, 0.8])
    bus = g.analyze(sel, b.tracks_at, b.anchored)
    res = g.plan(bus, dict(S0, value=0.25))
    segs = [(L["no"], L["net"], L["layer"], *res["moves"][sg.id][:2], res["moves"][sg.id][2], None)
            for L in bus.lanes for sg in L["segs"]]
    other = [g.Obstacle("circle", ((3.0, -0.35), 0.2), "X", 0, id="v1"),
             g.Obstacle("poly", [(4.8, 0.9), (5.2, 0.9), (5.2, 1.2), (4.8, 1.2)], "Y", None, id="p1")]
    iss = g.Issues()
    worst = g.check_copper(segs, g.Grid(other), {"N0": 0.1, "N1": 0.1, "N2": 0.1}, set(), iss)
    # lanes at 0, 0.25, 0.5 with 0.2 wide tracks: gap 0.05 < clearance 0.1 between lanes,
    # via at y=-0.35 r 0.2 -> 0.05 from lane 1 edge (needs 0.1), pad 0.3 from lane 3 edge
    assert set(worst) == {1, 2, 3}, worst
    assert abs(worst[1] - 0.05) < 1e-6
    iss2 = g.Issues()
    g.check_gaps(bus.lanes, res["targets"], res["widths"], {"N0": 0.1, "N1": 0.1, "N2": 0.1}, iss2)
    assert "gap_clr" in iss2


def test_random_buses_stay_connected():
    rnd = random.Random(1)
    for it in range(300):
        ang = rnd.uniform(0, 360)
        n = rnd.randint(2, 9)
        offs = sorted(rnd.uniform(0, 4) for _ in range(n))
        offs = [o + 0.25 * k for k, o in enumerate(offs)]          # keep them apart
        ends = (rnd.choice(["slide", "via", "straight", "free", "perp"]),
                rnd.choice(["slide", "via", "straight", "free", "perp"]))
        b, sel = bus_board(ang, offs, ends=ends, length=rnd.uniform(3, 12), lead=rnd.uniform(0.5, 3))
        s = dict(mode=rnd.choice([g.MODE_PITCH, g.MODE_GAP]), value=rnd.uniform(0.25, 0.8),
                 keep=rnd.choice([g.KEEP_FIRST, g.KEEP_CENTER, g.KEEP_LAST]),
                 ends=rnd.choice([g.ENDS_SLIDE, g.ENDS_JOG, g.ENDS_STRETCH]), width=0.0,
                 shift=rnd.choice([0.0, 0.3, -0.2]), snap=0.0)
        bus, res, nb = run(b, sel, **s)
        assert len(bus.lanes) == n
        bad = [c for c in ("short", "flip") if c in res["issues"]]
        for L in bus.lanes:
            assert nb.connected(L["net"]), (it, ang, ends, s, L["net"])
            assert b.terminals(L["net"]) == nb.terminals(L["net"]) or ends[0] == "free" or ends[1] == "free", it
        o = new_offsets(bus, nb)
        step = s["value"] if s["mode"] == g.MODE_PITCH else s["value"] + 0.2
        if not bad:
            assert all(abs((o[k + 1] - o[k]) - step) < 1e-6 for k in range(n - 1)), (it, o)
            for x in nb.segs:
                assert x.length() > 1e-4, (it, x.id)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
