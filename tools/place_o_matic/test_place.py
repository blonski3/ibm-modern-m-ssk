# Tests of place-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_place.py
# GUI:  xvfb-run -a python3 test_place.py gui [screenshot_dir]

import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.append(HERE)

import pcbnew  # noqa: E402

import tboard as T  # noqa: E402
from place_o_matic import geo  # noqa: E402
from place_o_matic import geometry as g  # noqa: E402
from place_o_matic import place_o_matic as pm  # noqa: E402

check = T.check


def S(**kw):
    s = dict(mode=g.ROW, spacing=g.PITCH, keep=g.KEEP_FIRST, rot=g.ROT_KEEP, x=2.54, y=2.54, cols=3,
             radius=10.0, a0=0.0, da=0, theta=0.0, dx=0.0, dy=0.0, order=g.ORDER_REF, reverse=False,
             refpt=0, axis_angle=0.0, snap=0, snake=False, cw=False, check=True)
    s.update(kw)
    return s


def board_with(n, seed=1, angs=None, sizes=None, back=False):
    rnd = random.Random(seed)
    b = pcbnew.BOARD()
    refs = ["R%d" % (k + 1) for k in range(n)]
    order = list(range(n))
    rnd.shuffle(order)
    fps = []
    for k in order:
        pos = (50 + rnd.uniform(-8, 8), 50 + rnd.uniform(-8, 8))
        cy = sizes[k] if sizes else (1.6, 0.9)
        pads = (((-cy[0] / 2, 0), (0.8, 0.9)), ((cy[0] / 2, 0), (0.8, 0.9)))
        fp = T.footprint(b, refs[k], pos, angs[k] if angs else 0.0, pads=pads, courtyard=cy,
                         value="%dk" % (n - k), back=back)
        fps.append(fp)
    return b, fps


def model_for(b, fps):
    for fp in fps:
        fp.SetSelected()
    m = pm.Model(b)
    m.load(m.selected())
    return m


def by_ref(b):
    return {fp.GetReference(): fp for fp in b.GetFootprints()}


def pos(fp):
    return T.xy(fp.GetPosition())


def test_row_pitch_by_reference():
    b, fps = board_with(6)
    before = T.snapshot(b)
    m = model_for(b, fps)
    first = pos(by_ref(b)["R1"])
    for rep in range(5):
        m.apply(S(x=2.54 + rep * 0.5))
    pl, iss, moved = m.apply(S(x=3.81))
    f = by_ref(b)
    for k in range(6):
        p = pos(f["R%d" % (k + 1)])
        check(abs(p[0] - (first[0] + 3.81 * k)) < 2e-6 and abs(p[1] - first[1]) < 1e-6,
              "row R%d at %s" % (k + 1, p))
    check(not iss.text(), "row issues %s" % iss.text())
    m.edits.restore()
    check(T.snapshot(b) == before, "row restore exact")


def test_column_gap_mixed_sizes():
    sizes = [(1.6, 0.9), (3.0, 1.5), (1.0, 0.5), (2.0, 2.0)]
    b, fps = board_with(4, sizes=sizes)
    m = model_for(b, fps)
    m.apply(S(mode=g.COLUMN, spacing=g.GAP, y=0.5))
    f = by_ref(b)
    ys = [pos(f["R%d" % (k + 1)])[1] for k in range(4)]
    for k in range(3):
        gap = (ys[k + 1] - sizes[k + 1][1]) - (ys[k] + sizes[k][1])
        check(abs(gap - 0.5) < 3e-6, "column gap %d = %.4f" % (k, gap))


def test_grid_and_snake():
    b, fps = board_with(7)
    m = model_for(b, fps)
    m.apply(S(mode=g.GRID, cols=3, x=3.0, y=4.0, snake=True))
    f = by_ref(b)
    p1 = pos(f["R1"])
    exp = {1: (0, 0), 2: (1, 0), 3: (2, 0), 4: (2, 1), 5: (1, 1), 6: (0, 1), 7: (0, 2)}
    for k, (c, r) in exp.items():
        p = pos(f["R%d" % k])
        check(abs(p[0] - p1[0] - 3.0 * c) < 1e-6 and abs(p[1] - p1[1] - 4.0 * r) < 1e-6,
              "grid R%d at %s" % (k, p))


def test_circle_follow_and_cw():
    for cw in (False, True):
        b, fps = board_with(8)
        m = model_for(b, fps)
        m.apply(S(mode=g.CIRCLE, radius=12.0, a0=90.0, rot=g.ROT_FOLLOW, theta=90.0, keep=g.KEEP_CENTER, cw=cw))
        f = by_ref(b)
        pts = [pos(f["R%d" % (k + 1)]) for k in range(8)]
        c = g.bbox_center(pts)
        for k, p in enumerate(pts):
            check(abs(geo.dist(p, c) - 12.0) < 1e-5, "circle radius R%d" % (k + 1))
            phi = math.degrees(math.atan2(-(p[1] - c[1]), p[0] - c[0])) % 360
            want = (90.0 + (-45.0 if cw else 45.0) * k) % 360
            check(abs((phi - want + 180) % 360 - 180) < 1e-4, "circle angle R%d %.3f vs %.3f" % (k + 1, phi, want))
            fa = f["R%d" % (k + 1)].GetOrientationDegrees() % 360
            check(abs((fa - (want + 90.0)) % 360) < 1e-4 or abs((fa - (want + 90.0)) % 360 - 360) < 1e-4,
                  "follow rotation R%d %.3f" % (k + 1, fa))


def test_rotated_parts_refpoints():
    angs = [30.0, 90.0, 0.0, 45.0, 180.0]
    for refpt in (0, 1, 2):
        b, fps = board_with(5, angs=angs)
        m = model_for(b, fps)
        m.apply(S(refpt=refpt, x=5.0))
        m.set_refpt(refpt)
        # the reference points of the items (from their new position) sit 5 mm apart
        items = sorted(m.items, key=lambda it: geo.natural_key(it.ref))
        f = by_ref(b)
        anchors = [it.anchor(pos(f[it.ref]), f[it.ref].GetOrientationDegrees()) for it in items]
        for k in range(4):
            check(abs(anchors[k + 1][0] - anchors[k][0] - 5.0) < 1e-6 and abs(anchors[k + 1][1] - anchors[k][1]) < 1e-6,
                  "refpt %d spacing %s" % (refpt, anchors))
        for it in items:
            check(abs(f[it.ref].GetOrientationDegrees() - it.angle) < 1e-9, "rotation kept")


def test_set_rotation_and_gap_uses_rotated_bodies():
    b, fps = board_with(4, sizes=[(2.0, 0.5)] * 4)
    m = model_for(b, fps)
    m.apply(S(spacing=g.GAP, x=0.3, rot=g.ROT_SET, theta=90.0))
    f = by_ref(b)
    xs = [pos(f["R%d" % (k + 1)])[0] for k in range(4)]
    for k in range(3):
        check(abs((xs[k + 1] - xs[k]) - (1.0 + 0.3)) < 3e-6, "rotated gap pitch %.4f" % (xs[k + 1] - xs[k]))
    for fp in f.values():
        check(abs(fp.GetOrientationDegrees() - 90.0) < 1e-9, "set rotation")


def test_keep_centre_offset_snap_axis():
    b, fps = board_with(5)
    m = model_for(b, fps)
    m.set_refpt(0)
    c0 = g.bbox_center([it.anchor() for it in m.items])
    m.apply(S(keep=g.KEEP_CENTER, x=3.0))
    pts = [pos(fp) for fp in b.GetFootprints()]
    check(geo.dist(g.bbox_center(pts), c0) < 1e-6, "keep centre")
    m.apply(S(keep=g.KEEP_CENTER, x=3.0, dx=1.0, dy=-2.0))
    pts = [pos(fp) for fp in b.GetFootprints()]
    check(geo.dist(g.bbox_center(pts), (c0[0] + 1, c0[1] - 2)) < 1e-6, "dx dy")
    m.apply(S(x=3.0, snap=0.5))
    p1 = pos(by_ref(b)["R1"])
    check(abs(p1[0] * 2 - round(p1[0] * 2)) < 1e-6 and abs(p1[1] * 2 - round(p1[1] * 2)) < 1e-6, "snap %s" % (p1,))
    m.apply(S(x=2.0, axis_angle=45.0))
    f = by_ref(b)
    for k in range(4):
        d = geo.sub(pos(f["R%d" % (k + 2)]), pos(f["R%d" % (k + 1)]))
        check(abs(d[0] - 2 * math.cos(math.radians(45))) < 1e-6 and abs(d[1] + 2 * math.sin(math.radians(45))) < 1e-6,
              "axis 45 %s" % (d,))


def test_orders():
    b, fps = board_with(5)
    m = model_for(b, fps)
    m.apply(S(order=g.ORDER_VALUE))
    f = by_ref(b)
    xs = {r: pos(fp)[0] for r, fp in f.items()}
    # values: R1 = 5k ... R5 = 1k -> value order R5, R4, ... R1
    check(sorted(xs, key=xs.get) == ["R5", "R4", "R3", "R2", "R1"], "value order %s" % sorted(xs, key=xs.get))
    m.apply(S(order=g.ORDER_REF, reverse=True))
    xs = {r: pos(fp)[0] for r, fp in f.items()}
    check(sorted(xs, key=xs.get) == ["R5", "R4", "R3", "R2", "R1"], "reverse")
    m.edits.restore()
    m.set_refpt(0)
    before = sorted(m.items, key=lambda it: it.anchor()[0])
    m.apply(S(order=g.ORDER_POS))
    xs = {r: pos(fp)[0] for r, fp in f.items()}
    check(sorted(xs, key=xs.get) == [it.ref for it in before], "position order kept")


def test_checks():
    b, fps = board_with(4, sizes=[(1.6, 0.9)] * 4)
    T.outline(b, 30, 30, 70, 70)
    other = T.footprint(b, "U1", (50 + 2.54 * 2, 60), courtyard=(3, 3))
    m = model_for(b, fps)
    _pl, iss, _ = m.apply(S(x=2.0, keep=g.KEEP_FIRST))
    check("overlap" in iss, "overlap at pitch 2.0 < 3.2 courtyard %s" % iss.text())
    _pl, iss, _ = m.apply(S(x=4.0))
    check("overlap" not in iss, "no overlap at 4.0")
    p1 = pos(by_ref(b)["R1"])
    _pl, iss, _ = m.apply(S(x=4.0, dy=60 - p1[1], dx=0))
    check("hits" in iss, "hits U1 %s" % iss.text())
    _pl, iss, _ = m.apply(S(x=4.0, dx=40))
    check("outside" in iss, "outside the board %s" % iss.text())
    _pl, iss, _ = m.apply(S(x=4.0, dx=40, check=False))
    check(not iss.text(), "check off")
    _ = other


def test_back_side_and_restore():
    b, fps = board_with(5, back=True, angs=[0, 30, 60, 90, 120])
    before = T.snapshot(b)
    m = model_for(b, fps)
    rnd = random.Random(3)
    for k in range(30):
        m.apply(S(mode=rnd.choice([g.ROW, g.COLUMN, g.GRID, g.CIRCLE]), x=rnd.uniform(1, 5), y=rnd.uniform(1, 5),
                  radius=rnd.uniform(3, 15), rot=rnd.choice([g.ROT_KEEP, g.ROT_SET, g.ROT_FOLLOW]),
                  theta=rnd.uniform(0, 360), keep=rnd.choice([g.KEEP_FIRST, g.KEEP_CENTER]),
                  refpt=rnd.randint(0, 2), spacing=rnd.choice([g.PITCH, g.GAP])))
    m.edits.restore()
    after = T.snapshot(b)
    bad = [k for k in before if before[k] != after[k]]
    # orientation round trips through float degrees: allow 1e-9
    for k in bad:
        a, c = before[k], after[k]
        check(all((abs(x - y) < 1e-6 if isinstance(x, float) else x == y) for x, y in zip(a, c)),
              "restore %s %s" % (a, c))


def test_speed():
    import time
    b, fps = board_with(60)
    for k in range(400):
        T.footprint(b, "C%d" % k, (k % 20 * 4.0, 100 + k // 20 * 4.0))
    m = model_for(b, fps)
    t0 = time.time()
    for k in range(10):
        m.apply(S(mode=g.GRID, cols=10, x=3 + k * 0.1, y=3))
    dt = (time.time() - t0) / 10
    print("  speed: %.1f ms per change (60 placed, 400 others, check on)" % (dt * 1e3))
    check(dt < 0.5, "too slow %.3f" % dt)


# ---------------------------------------------------------------- GUI

def gui(shots=None):
    from place_o_matic import dialog as dl
    H = T.gui_harness(dl.PlaceDialog)
    b, fps = board_with(6)
    for fp in fps:
        fp.SetSelected()
    before = T.snapshot(b)
    st = {}

    def s_open(d):
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "place_row.png"))
        check(T.snapshot(b) != before, "applied on open")
        check(d.ro["now"].GetLabel() != "–", "now readout")

    def s_modes(d):
        for k in range(4):
            d._toggle("mode", k)
            H["settle"](d)
            check(d.status.GetLabel().startswith("6 placed"), "mode %d status %r" % (k, d.status.GetLabel()))
            if shots:
                H["shot"](d, os.path.join(shots, "place_mode%d.png" % k))
        d._toggle("mode", 0)
        H["settle"](d)

    def s_values(d):
        d.f["x"].SetValue("5")
        H["settle"](d)
        f = by_ref(b)
        check(abs(pos(f["R2"])[0] - pos(f["R1"])[0] - 5) < 1e-6, "X 5 applied")
        d.step_ch.SetSelection(d.STEPS.index(1.27))
        d.nudge("pitch", 1)
        H["settle"](d)
        check(d.f["x"].GetValue() == "6.27", "pitch nudge %r" % d.f["x"].GetValue())
        d.nudge("dx", 1)
        d.nudge("dy", -1)
        H["settle"](d)
        check(d.f["dx"].GetValue() == "1.27" and d.f["dy"].GetValue() == "-1.27", "move nudge")
        d.ch["rot"].SetSelection(1)
        d.f["theta"].SetValue("90")
        d.on_change()
        H["settle"](d)
        check(all(abs(fp.GetOrientationDegrees() - 90) < 1e-9 for fp in b.GetFootprints()), "rotation set")
        d.more.Expand()
        d.on_more()
        d.ch["order"].SetSelection(2)
        d.cb["reverse"].SetValue(True)
        d.on_change()
        H["settle"](d)
        if shots:
            H["shot"](d, os.path.join(shots, "place_more.png"))
        d.f["x"].SetValue("0.5")
        H["settle"](d)
        check(d.warn.IsShown(), "overlap warning shown")
        d.f["x"].SetValue("abc")
        H["settle"](d)
        check("Invalid" in d.status.GetLabel(), "invalid")
        d.f["x"].SetValue("4")
        H["settle"](d)
        st["final"] = T.snapshot(b)

    def s_ok(d):
        d.finish(True)

    H["run"](pm.PlaceOMatic(), b, [s_open, s_modes, s_values, s_ok])
    check(T.snapshot(b) == st.get("final"), "OK keeps")

    b2, fps2 = board_with(4)
    for fp in fps2:
        fp.SetSelected()
    before2 = T.snapshot(b2)

    def c_change(d):
        d._toggle("mode", 3)
        H["settle"](d)
        check(T.snapshot(b2) != before2, "changed")

    H["run"](pm.PlaceOMatic(), b2, [c_change, lambda d: d.finish(False)])
    check(T.snapshot(b2) == before2, "Cancel restores")
    H["boxes"].clear()
    b3, _ = board_with(1)
    import pcbnew as pn
    pn.GetBoard = lambda: b3
    pm.PlaceOMatic().Run()
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
    sys.exit(T.report("place-o-matic"))
