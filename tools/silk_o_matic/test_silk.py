# Tests of silk-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_silk.py
# GUI:  xvfb-run -a python3 test_silk.py gui [screenshot_dir]

import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.append(HERE)

import pcbnew  # noqa: E402

import tboard as T  # noqa: E402
from silk_o_matic import geometry as g  # noqa: E402
from silk_o_matic import silk_o_matic as sm  # noqa: E402

check = T.check
TOL = 2e-6


def S(**kw):
    s = dict(side=g.AUTO, which=sm.REF, angle=g.ANG_0, gap=0.2, h=0, t=0, pad_gap=0.1, silk_gap=0.1)
    s.update(kw)
    return s


def model_for(b, fps):
    for fp in fps:
        fp.SetSelected()
    m = sm.Model(b)
    m.load(m.selected())
    return m


def by_ref(b):
    return {fp.GetReference(): fp for fp in b.GetFootprints()}


def ink(fp, which=sm.REF):
    return sm.ink_box(sm.Model.target(fp, which))


def body(fp):
    return sm.body_box(fp)[0]


def side_gap(bx, ib, side):
    """Gap between the body box and the ink box on that side, and the offset of the centres
    along the side (0 = centred)."""
    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
    ix, iy = (ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2
    if side == g.TOP:
        return bx[1] - ib[3], ix - cx
    if side == g.BOTTOM:
        return ib[1] - bx[3], ix - cx
    if side == g.LEFT:
        return bx[0] - ib[2], iy - cy
    if side == g.RIGHT:
        return ib[0] - bx[2], iy - cy
    return max(abs(ix - cx), abs(iy - cy)), 0.0


def which_side(bx, ib):
    for sd in (g.TOP, g.BOTTOM, g.LEFT, g.RIGHT):
        gp, off = side_gap(bx, ib, sd)
        if gp > -1e-6 and abs(off) < 1e-5:
            return sd
    return None


def overlap(a, b, gap=0.0):
    return (a[0] < b[2] + gap - 1e-6 and b[0] < a[2] + gap - 1e-6 and
            a[1] < b[3] + gap - 1e-6 and b[1] < a[3] + gap - 1e-6)


# ------------------------------------------------------------------ placement

def test_four_sides_and_centre():
    for ang in (0.0, 90.0, 30.0, 180.0):
        for back in (False, True):
            b = pcbnew.BOARD()
            fp = T.footprint(b, "R1", (50, 50), ang, courtyard=(1.6, 0.9), back=back)
            m = model_for(b, [fp])
            for side in (g.TOP, g.BOTTOM, g.LEFT, g.RIGHT, g.CENTER):
                for gap in (0.2, 0.5, 0.0):
                    for angle in (g.ANG_0, g.ANG_90):
                        m.apply(S(side=side, gap=gap, angle=angle, h=1.0))
                        gp, off = side_gap(body(fp), ink(fp), side)
                        want = 0.0 if side == g.CENTER else gap
                        check(abs(gp - want) < TOL and abs(off) < TOL,
                              "side %d gap %.2f fp %g back %s ang %d: gap %.6f off %.6f"
                              % (side, gap, ang, back, angle, gp, off))
                        d = sm.draw_angle(fp.Reference())
                        check(abs(d - (90.0 if angle == g.ANG_90 else 0.0)) < 1e-6, "draw angle %g" % d)


def test_size_and_thickness():
    b = pcbnew.BOARD()
    fps = [T.footprint(b, "R%d" % k, (40 + 5 * k, 50)) for k in range(1, 4)]
    fps[1].Reference().SetTextSize(pcbnew.VECTOR2I(800000, 800000))
    m = model_for(b, fps)
    m.apply(S(h=1.0))
    for fp in fps:
        r = fp.Reference()
        check(r.GetTextSize().x == 1000000 and r.GetTextSize().y == 1000000, "H 1.0")
        check(r.GetTextThickness() == 150000, "T = 15 %% of H (%d)" % r.GetTextThickness())
    m.apply(S(h=0.8, t=0.12))
    for fp in fps:
        r = fp.Reference()
        check(r.GetTextSize().y == 800000 and r.GetTextThickness() == 120000, "H 0.8 T 0.12")
    m.apply(S(h=0, t=0.1))
    sizes = sorted(fp.Reference().GetTextSize().y for fp in fps)
    check(sizes == [800000, 1270000, 1270000], "H empty keeps sizes %s" % sizes)
    check(all(fp.Reference().GetTextThickness() == 100000 for fp in fps), "T alone")
    m.apply(S())
    check(sorted(fp.Reference().GetTextSize().y for fp in fps) == [800000, 1270000, 1270000], "keep all")
    check(sm.now_text(m, sm.REF) == "2 sizes", "now readout %s" % sm.now_text(m, sm.REF))


def test_angle_modes():
    b = pcbnew.BOARD()
    wide = T.footprint(b, "R1", (40, 50), 0.0, courtyard=(1.6, 0.9))
    tall = T.footprint(b, "R2", (50, 50), 90.0, courtyard=(1.6, 0.9))
    odd = T.footprint(b, "R3", (60, 50), 30.0, courtyard=(1.6, 0.9))
    odd.Reference().SetTextAngleDegrees(0)          # follows the part: 30 on the board
    m = model_for(b, [wide, tall, odd])
    m.apply(S(angle=g.ANG_ALONG, side=g.TOP))
    check(abs(sm.draw_angle(wide.Reference())) < 1e-6, "along: wide part 0")
    check(abs(sm.draw_angle(tall.Reference()) - 90) < 1e-6, "along: tall part 90")
    m.apply(S(angle=g.ANG_KEEP, side=g.RIGHT))
    check(abs(sm.draw_angle(odd.Reference()) - 30) < 1e-6, "keep 30 (%g)" % sm.draw_angle(odd.Reference()))
    gp, off = side_gap(body(odd), ink(odd), g.RIGHT)
    check(abs(gp - 0.2) < TOL and abs(off) < TOL, "keep: rotated box still at the gap")
    m.apply(S(angle=g.ANG_90))
    check(all(abs(sm.draw_angle(fp.Reference()) - 90) < 1e-6 for fp in (wide, tall, odd)), "all 90")
    m.edits.restore()
    check(abs(sm.draw_angle(odd.Reference()) - 30) < 1e-6, "restore angle")


def test_auto_avoids_pads_silk_edge():
    b = pcbnew.BOARD()
    T.outline(b, 30, 30, 70, 70)
    r1 = T.footprint(b, "R1", (50, 50))
    m = model_for(b, [r1])
    res = m.apply(S())
    check(which_side(body(r1), ink(r1)) == g.TOP and res["crowded"] == 0, "free: top")
    # a pad of another part above -> bottom
    T.footprint(b, "R9", (50, 47.7), courtyard=None).Reference().SetVisible(False)
    m.load(m.fps)
    res = m.apply(S())
    check(which_side(body(r1), ink(r1)) == g.BOTTOM and not res["issues"].text(),
          "pad above -> bottom (%s)" % which_side(body(r1), ink(r1)))
    # a silk line below -> right
    s = pcbnew.PCB_SHAPE(b)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(T.V((48, 52)))
    s.SetEnd(T.V((52, 52)))
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(150000)
    b.Add(s)
    m.load(m.fps)
    m.apply(S())
    check(which_side(body(r1), ink(r1)) == g.RIGHT, "silk below -> right")
    # an edge on the right (narrow board) -> left
    b2 = pcbnew.BOARD()
    T.outline(b2, 30, 30, 52.5, 70)
    a = T.footprint(b2, "R1", (50, 50))
    T.footprint(b2, "R9", (50, 47.7), courtyard=None).Reference().SetVisible(False)
    s2 = s.Duplicate()
    b2.Add(s2)
    m2 = model_for(b2, [a])
    res = m2.apply(S())
    check(which_side(body(a), ink(a)) == g.LEFT and not res["issues"].text(), "edge right -> left")
    # nothing free (board just around the part): crowded, least overlap
    b3 = pcbnew.BOARD()
    T.outline(b3, 47.5, 48.5, 52.5, 51.5)
    c = T.footprint(b3, "R1", (50, 50))
    m3 = model_for(b3, [c])
    res = m3.apply(S(h=1.5))
    check(res["crowded"] == 1 and "no free place" in " ".join(res["issues"].text()),
          "crowded reported %s" % res["issues"].text())


def test_fixed_side_reports():
    b = pcbnew.BOARD()
    T.outline(b, 30, 30, 70, 70)
    r1 = T.footprint(b, "R1", (50, 50))
    T.footprint(b, "R9", (50, 47.7), courtyard=None).Reference().SetVisible(False)
    m = model_for(b, [r1])
    res = m.apply(S(side=g.TOP))
    txt = " ".join(res["issues"].text())
    check("on a pad" in txt and res["crowded"] == 0, "pad issue on fixed side: %s" % txt)
    res = m.apply(S(side=g.BOTTOM))
    check(not res["issues"].text(), "bottom is free")
    b2 = pcbnew.BOARD()
    T.outline(b2, 49, 30, 70, 70)
    a = T.footprint(b2, "R1", (50.5, 50))
    m2 = model_for(b2, [a])
    res = m2.apply(S(side=g.LEFT))
    check("board edge" in " ".join(res["issues"].text()), "edge issue")


def test_value_and_hidden():
    b = pcbnew.BOARD()
    fp = T.footprint(b, "R1", (50, 50))
    fp.Value().SetVisible(True)
    r0 = T.xy(fp.Reference().GetPosition())
    m = model_for(b, [fp])
    res = m.apply(S(which=sm.VALUE, side=g.BOTTOM, h=0.8))
    gp, off = side_gap(body(fp), ink(fp, sm.VALUE), g.BOTTOM)
    check(abs(gp - 0.2) < TOL and abs(off) < TOL, "value below")
    check(T.xy(fp.Reference().GetPosition()) == r0, "reference not moved")
    check(fp.Value().GetTextSize().y == 800000, "value size")
    check(not res["issues"].text(), "value no issues")
    # the reference text above is in the way of the value placed on top
    res = m.apply(S(which=sm.VALUE, side=g.TOP))
    check("silkscreen" in " ".join(res["issues"].text()), "value vs reference silk")
    fp.Reference().SetVisible(False)
    m.load(m.fps)
    res = m.apply(S())
    check("hidden" in " ".join(res["issues"].text()), "hidden reported")


def test_back_side_ignores_front():
    b = pcbnew.BOARD()
    T.outline(b, 30, 30, 70, 70)
    r1 = T.footprint(b, "R1", (50, 50), back=True)
    T.footprint(b, "R9", (50, 47.7), courtyard=None).Reference().SetVisible(False)   # front pads
    m = model_for(b, [r1])
    m.apply(S())
    check(r1.Reference().GetLayer() == pcbnew.B_SilkS, "back text stays on B.Silkscreen")
    check(which_side(body(r1), ink(r1)) == g.TOP, "front pads do not block a back text")
    T.footprint(b, "R8", (50, 47.7), courtyard=None, back=True).Reference().SetVisible(False)
    m.load(m.fps)
    m.apply(S())
    check(which_side(body(r1), ink(r1)) == g.BOTTOM, "back pads do")


def test_fab_layer_centre():
    b = pcbnew.BOARD()
    fp = T.footprint(b, "U1", (50, 50), courtyard=(3.0, 2.0),
                     pads=(((-2, -1), (1, 0.6)), ((-2, 1), (1, 0.6)), ((2, -1), (1, 0.6)), ((2, 1), (1, 0.6))))
    fp.Value().SetLayer(pcbnew.F_Fab)
    fp.Value().SetVisible(True)
    m = model_for(b, [fp])
    res = m.apply(S(which=sm.VALUE, side=g.CENTER, h=1.0))
    ib = ink(fp, sm.VALUE)
    check(abs((ib[0] + ib[2]) / 2 - 50) < TOL and abs((ib[1] + ib[3]) / 2 - 50) < TOL, "fab text centred")
    check(not res["issues"].text(), "no silk issues on Fab: %s" % res["issues"].text())


def test_neighbours_do_not_overlap():
    """A dense column of 0603 parts: Auto must not put two texts on each other."""
    b = pcbnew.BOARD()
    T.outline(b, 30, 30, 70, 70)
    fps = [T.footprint(b, "C%d" % (k + 1), (50, 40 + 2.2 * k), courtyard=(1.5, 0.75)) for k in range(8)]
    m = model_for(b, fps)
    res = m.apply(S(h=0.8))
    boxes = [ink(fp) for fp in fps]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            check(not overlap(boxes[i], boxes[j], 0.1), "texts C%d C%d overlap" % (i + 1, j + 1))
    check(res["crowded"] == 0, "dense column placed (%d crowded)" % res["crowded"])
    sides = {which_side(body(fp), ink(fp)) for fp in fps}
    check(len(sides) >= 2, "used other sides %s" % sides)


def test_restore_exact():
    b = pcbnew.BOARD()
    rnd = random.Random(3)
    fps = [T.footprint(b, "R%d" % k, (rnd.uniform(30, 70), rnd.uniform(30, 70)), rnd.choice((0, 90, 45, 180)),
                       back=rnd.random() < 0.3) for k in range(1, 15)]
    for fp in fps:
        fp.Value().SetVisible(True)
    before = T.snapshot(b)
    vals = {fp.GetReference(): (T.xy(fp.Value().GetPosition()), fp.Value().GetTextAngleDegrees(),
                                fp.Value().GetTextSize().y) for fp in fps}
    m = model_for(b, fps)
    for side in range(6):
        for angle in range(4):
            m.apply(S(side=side, angle=angle, h=0.9, gap=0.3))
    check(T.snapshot(b) != before, "changed")
    m.apply(S(which=sm.VALUE, h=0.7, angle=g.ANG_90))
    m.edits.restore()
    check(T.snapshot(b) == before, "restore exact")
    check(all(vals[fp.GetReference()] == (T.xy(fp.Value().GetPosition()), fp.Value().GetTextAngleDegrees(),
                                          fp.Value().GetTextSize().y) for fp in fps), "value restored")


def test_against_kicad_drc():
    """Random dense boards with silk lines and parts that stay: every text Auto placed
    without a warning is clean in KiCad's DRC (silk over mask, silk overlap, silk to edge)."""
    kinds = ("silk_over_copper", "silk_overlap", "silk_edge_clearance")
    total_flagged = total_drc_before = 0
    for seed in range(10):
        rnd = random.Random(seed)
        b = pcbnew.BOARD()
        T.outline(b, 30, 30, 56, 56)
        pts = []
        for k in range(30):
            for _ in range(80):
                p = (rnd.uniform(32, 54), rnd.uniform(32, 54))
                if all(abs(p[0] - q[0]) > 3.6 or abs(p[1] - q[1]) > 2.0 for q in pts):
                    break
            else:
                continue
            ang = rnd.choice((0, 90, 0, 270, 45, 180))
            fp = T.footprint(b, "R%d" % (k + 1), p, ang, courtyard=(1.6, 0.9), back=rnd.random() < 0.15)
            if rnd.random() < 0.3:
                fp.Value().SetVisible(True)
            pts.append(p)
        for _ in range(6):
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            a = (rnd.uniform(31, 55), rnd.uniform(31, 55))
            s.SetStart(T.V(a))
            s.SetEnd(T.V((a[0] + rnd.uniform(-5, 5), a[1] + rnd.uniform(-5, 5))))
            s.SetLayer(pcbnew.F_SilkS)
            s.SetWidth(120000)
            b.Add(s)
        allfp = list(b.GetFootprints())
        sel = [fp for fp in allfp if rnd.random() < 0.8]
        total_drc_before += len(T.drc(b, kinds))
        m = model_for(b, sel)
        res = m.apply(S(h=rnd.choice((0.8, 1.0)), angle=rnd.choice((g.ANG_0, g.ANG_ALONG)),
                        pad_gap=0.05, silk_gap=0.05))
        total_flagged += len(res["flagged"])
        mine = {fp.GetReference() for fp in sel}
        bad = set()
        for kind, items in T.drc(b, kinds):
            refs = [it.split("Reference '")[1].split("'")[0] for it in items if "Reference '" in it]
            if any(r in res["flagged"] for r in refs):
                continue                    # a crowded text put on this one: it has the warning
            for ref in refs:
                if ref in mine:
                    bad.add((kind, ref, tuple(items)))
        check(not bad, "seed %d: DRC on texts placed as free %s (crowded %d)" % (seed, sorted(bad), res["crowded"]))
    print("    DRC fuzz: %d silk errors before, %d texts with a warning after" % (total_drc_before, total_flagged))
    check(total_drc_before > 5 and total_flagged > 0, "the fuzz boards are dense enough")


def test_speed():
    b = pcbnew.BOARD()
    T.outline(b, 0, 0, 160, 120)
    fps = []
    for i in range(20):
        for j in range(15):
            fps.append(T.footprint(b, "R%d" % (i * 15 + j + 1), (5 + 7.5 * i, 5 + 7.5 * j), (0, 90)[(i + j) % 2]))
    t0 = time.time()
    m = model_for(b, fps)
    m.apply(S(h=1.0))
    t1 = time.time()
    m.apply(S(h=0.8, gap=0.3))
    t2 = time.time()
    print("    300 parts: load+first %.0f ms, next %.0f ms" % ((t1 - t0) * 1e3, (t2 - t1) * 1e3))
    check(t2 - t1 < 1.0, "speed %.2f s" % (t2 - t1))


# ------------------------------------------------------------------------ GUI

def gui(shots=None):
    from silk_o_matic import dialog as dl
    H = T.gui_harness(dl.SilkDialog)
    b = pcbnew.BOARD()
    T.outline(b, 30, 30, 70, 70)
    fps = [T.footprint(b, "R%d" % (k + 1), (40 + 4 * k, 50), (0, 90)[k % 2]) for k in range(5)]
    for fp in fps:
        fp.SetSelected()
    before = T.snapshot(b)
    st = {}

    def s_open(d):
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "silk_auto.png"))
        check(T.snapshot(b) != before, "applied on open")
        check("5 placed" in d.status.GetLabel(), "status %r" % d.status.GetLabel())
        check(d.ro["now"].GetLabel() == "1.27 / 0.15 mm", "now %r" % d.ro["now"].GetLabel())

    def s_values(d):
        d._toggle("side", 0)
        d.f["h"].SetValue("1")
        H["settle"](d)
        check(all(fp.Reference().GetTextSize().y == 1000000 for fp in fps), "H from the dialog")
        for fp in fps:
            gp, off = side_gap(body(fp), ink(fp), g.TOP)
            check(abs(gp - 0.2) < TOL, "top gap %.4f" % gp)
        d.nudge("gap", 1)
        H["settle"](d)
        check(d.f["gap"].GetValue() == "0.3", "gap nudge %r" % d.f["gap"].GetValue())
        check(all(abs(side_gap(body(fp), ink(fp), g.TOP)[0] - 0.3) < TOL for fp in fps), "gap 0.3 on board")
        d.ch["angle"].SetSelection(3)
        d.on_change()
        H["settle"](d)
        check(abs(sm.draw_angle(fps[1].Reference()) - 90) < 1e-6, "along part")
        H["shot"](d, shots and os.path.join(shots, "silk_top.png"))
        d._toggle("side", 4)
        H["settle"](d)
        check(not d.f["gap"].IsEnabled(), "gap off for centre")
        d._toggle("side", 5)
        d.more.Expand()
        d.on_more()
        d.c["pad_gap"].SetValue("0.2")
        d.on_change()
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "silk_more.png"))
        d.f["h"].SetValue("abc")
        H["settle"](d)
        check("Invalid" in d.status.GetLabel(), "invalid")
        d.f["h"].SetValue("")
        H["settle"](d)
        st["final"] = T.snapshot(b)

    H["run"](sm.SilkOMatic(), b, [s_open, s_values, lambda d: d.finish(True)])
    check(T.snapshot(b) == st.get("final"), "OK keeps")

    b2 = pcbnew.BOARD()
    f2 = [T.footprint(b2, "C%d" % k, (40 + 4 * k, 50)) for k in range(3)]
    for fp in f2:
        fp.SetSelected()
    before2 = T.snapshot(b2)

    def c_change(d):
        d._toggle("side", 1)
        d.f["h"].SetValue("0.6")
        H["settle"](d)
        check(T.snapshot(b2) != before2, "changed")

    H["run"](sm.SilkOMatic(), b2, [c_change, lambda d: d.finish(False)])
    check(T.snapshot(b2) == before2, "Cancel restores")
    H["boxes"].clear()
    b3 = pcbnew.BOARD()
    T.footprint(b3, "R1", (50, 50))
    pcbnew.GetBoard = lambda: b3
    sm.SilkOMatic().Run()
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
    sys.exit(T.report("silk-o-matic"))
