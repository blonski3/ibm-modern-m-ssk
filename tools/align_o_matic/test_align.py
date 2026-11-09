# Tests of align-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_align.py
# GUI:  xvfb-run -a python3 test_align.py gui [screenshot_dir]

import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.append(HERE)

import pcbnew  # noqa: E402

import tboard as T  # noqa: E402
from align_o_matic import geometry as g  # noqa: E402
from align_o_matic import align_o_matic as am  # noqa: E402

check = T.check
E = 1e-6


def S(**kw):
    s = dict(axis=g.AX_X, move=g.MOVE_X, refpt=g.REF_PADS, dx=0.0, dy=0.0, drag=False)
    s.update(kw)
    return s


def board(n=5, seed=1, angs=(0, 90, 30, 180, 270)):
    rnd = random.Random(seed)
    b = pcbnew.BOARD()
    nets = [T.net(b, "N%d" % k) for k in range(8)]
    j = T.footprint(b, "J1", (20.0, 30.0), 0.0,
                    pads=[((0.0, k * 2.54), (1.7, 1.7)) for k in range(4)], nets=nets[:4], courtyard=(1.2, 4.5))
    fps = []
    for k in range(n):
        fps.append(T.footprint(b, "R%d" % (k + 1), (35 + rnd.uniform(-5, 5), 25 + 6 * k + rnd.uniform(-1, 1)),
                               angs[k % len(angs)], nets=[nets[4 + k % 4], nets[(k + 1) % 4]],
                               courtyard=(1.6, 0.9)))
    return b, j, fps, nets


def clear(b):
    for fp in b.GetFootprints():
        fp.ClearSelected()
        for p in fp.Pads():
            p.ClearSelected()
    for t in b.GetTracks():
        t.ClearSelected()


def select(b, items):
    """Like KiCad: a selected footprint marks its pads selected too."""
    clear(b)
    for it in items:
        it.SetSelected()
        if it.GetClass() == "FOOTPRINT":
            for p in it.Pads():
                p.SetSelected()


def pad(fp, num):
    return [p for p in fp.Pads() if p.GetNumber() == str(num)][0]


def xy(it):
    return T.xy(it.GetPosition())


def master(m, b, item):
    select(b, [item])
    msg = m.set_master()
    check(msg is None, "master %s" % msg)


# ------------------------------------------------------------------ axes

def test_x_and_y_pads():
    for axis in (g.AX_X, g.AX_Y):
        b, j, fps, _ = board()
        m = am.Model(b)
        master(m, b, pad(j, 2))
        M = xy(pad(j, 2))
        before = {fp.GetReference(): (xy(pad(fp, 1)), xy(pad(fp, 2)), fp.GetOrientationDegrees()) for fp in fps}
        select(b, [pad(fp, 1) for fp in fps])
        iss = m.align(S(axis=axis))
        check(not iss.text(), "issues %s" % iss.text())
        for fp in fps:
            p1, p2, ang = before[fp.GetReference()]
            q1, q2 = xy(pad(fp, 1)), xy(pad(fp, 2))
            if axis == g.AX_X:
                check(abs(q1[0] - M[0]) < E and abs(q1[1] - p1[1]) < E, "X: %s pad 1 %s" % (fp.GetReference(), q1))
            else:
                check(abs(q1[1] - M[1]) < E and abs(q1[0] - p1[0]) < E, "Y: %s pad 1 %s" % (fp.GetReference(), q1))
            d1 = (q1[0] - p1[0], q1[1] - p1[1])
            d2 = (q2[0] - p2[0], q2[1] - p2[1])
            check(abs(d1[0] - d2[0]) < E and abs(d1[1] - d2[1]) < E, "the whole part moved")
            check(fp.GetOrientationDegrees() == ang, "rotation kept")
        check(xy(pad(j, 2)) == M, "master stays")


def test_footprint_ref_points():
    for refpt in (g.REF_ORIGIN, g.REF_PADS, g.REF_BODY):
        b, j, fps, _ = board()
        m = am.Model(b)
        master(m, b, fps[0])
        v = S(axis=g.AX_Y, refpt=refpt)
        M = m.master_point(v)
        select(b, fps[1:])
        m.align(v)
        for fp in fps[1:]:
            p = am.Mover(fp).point(refpt)
            check(abs(p[1] - M[1]) < E, "refpt %d: %s at y %.6f vs %.6f" % (refpt, fp.GetReference(), p[1], M[1]))
        if refpt == g.REF_ORIGIN:
            check(all(abs(xy(fp)[1] - xy(fps[0])[1]) < E for fp in fps), "origins in one row")


def test_diagonals_one_coordinate():
    for axis in (g.AX_DIAG_UP, g.AX_DIAG_DOWN):
        for move in (g.MOVE_X, g.MOVE_Y):
            b, j, fps, _ = board()
            m = am.Model(b)
            master(m, b, pad(j, 1))
            M = xy(pad(j, 1))
            old = {fp.GetReference(): xy(pad(fp, 2)) for fp in fps}
            select(b, [pad(fp, 2) for fp in fps])
            m.align(S(axis=axis, move=move))
            s = -1.0 if axis == g.AX_DIAG_UP else 1.0
            for fp in fps:
                q, o = xy(pad(fp, 2)), old[fp.GetReference()]
                check(abs((q[1] - M[1]) - s * (q[0] - M[0])) < 2 * E, "on the 45° line %s" % fp.GetReference())
                if move == g.MOVE_X:
                    check(abs(q[1] - o[1]) < E, "only X changed")
                else:
                    check(abs(q[0] - o[0]) < E, "only Y changed")


def test_offsets_and_onto():
    b, j, fps, nets = board()
    vias = [T.via(b, (40 + k, 60), nets[0]) for k in range(2)]
    m = am.Model(b)
    master(m, b, pad(j, 3))
    M = xy(pad(j, 3))
    select(b, vias[:1])
    m.align(S(axis=g.AX_ONTO))
    check(xy(vias[0]) == M, "via onto the pad %s" % (xy(vias[0]),))
    select(b, vias[1:])
    m.align(S(axis=g.AX_ONTO, dx=1.27, dy=-0.635))
    q = xy(vias[1])
    check(abs(q[0] - M[0] - 1.27) < E and abs(q[1] - M[1] + 0.635) < E, "onto with offsets %s" % (q,))
    select(b, [pad(fp, 1) for fp in fps])
    m.align(S(axis=g.AX_X, dx=-2.54))
    check(all(abs(xy(pad(fp, 1))[0] - (M[0] - 2.54)) < E for fp in fps), "X with DX")


def test_many_actions_live_and_undo():
    b, j, fps, _ = board()
    snap0 = T.snapshot(b)
    m = am.Model(b)
    master(m, b, pad(j, 1))
    M = xy(pad(j, 1))
    select(b, [pad(fp, 1) for fp in fps[:2]])
    m.align(S(axis=g.AX_X))
    after_x = T.snapshot(b)
    m.apply(S(axis=g.AX_Y))                      # the live action follows the settings
    check(all(abs(xy(pad(fp, 1))[1] - M[1]) < E for fp in fps[:2]), "live: now Y")
    check(T.snapshot(b) != after_x, "redone")
    m.apply(S(axis=g.AX_X))
    check(T.snapshot(b) == after_x, "back to X exactly")
    select(b, [pad(fp, 2) for fp in fps[2:]])
    m.align(S(axis=g.AX_Y))
    snap2 = T.snapshot(b)
    m.apply(S(axis=g.AX_X))                      # changes only the second action
    check(all(abs(xy(pad(fp, 1))[0] - M[0]) < E for fp in fps[:2]), "first action kept")
    m.apply(S(axis=g.AX_Y))
    check(T.snapshot(b) == snap2, "second action redone exactly")
    master(m, b, fps[4])                          # new master, the last action is kept
    select(b, fps[:2])
    m.align(S(axis=g.AX_Y, refpt=g.REF_ORIGIN))
    check(abs(xy(fps[0])[1] - xy(fps[4])[1]) < E, "third action with the new master")
    check(m.done_text() == "3 actions, 7 moved", m.done_text())
    m.undo()
    check(T.snapshot(b) == snap2, "undo the third")
    m.undo()
    check(T.snapshot(b) == after_x, "undo the second")
    m.apply(S(axis=g.AX_Y))
    check(T.snapshot(b) == after_x, "after undo nothing is live")
    m.undo()
    check(T.snapshot(b) == snap0, "undo all")
    check(not m.undo(), "nothing left")
    master(m, b, pad(j, 1))
    for k in range(4):
        select(b, [pad(fps[k], 1)])
        m.align(S(axis=(g.AX_X, g.AX_Y, g.AX_DIAG_UP, g.AX_ONTO)[k]))
    m.restore_all()
    check(T.snapshot(b) == snap0, "Cancel restores all actions")


def test_rules_and_issues():
    b, j, fps, nets = board()
    m = am.Model(b)
    select(b, [pad(j, 1), pad(j, 2)])
    check(m.set_master() is not None, "two pads: no master")
    select(b, [])
    check(m.set_master() is not None, "nothing: no master")
    master(m, b, pad(j, 1))
    fps[1].SetLocked(True)
    t = T.track(b, (1, 1), (2, 2), nets[0])
    select(b, [j, fps[0], fps[1], t])
    iss = m.align(S(axis=g.AX_Y))
    txt = " ".join(iss.text())
    check("master itself" in txt and "locked" in txt and "tracks" in txt, "issues: %s" % txt)
    check(m.stack[-1].moved == 1, "only R1 moved (%d)" % m.stack[-1].moved)
    select(b, [])
    iss = m.align(S())
    check("nothing to align" in " ".join(iss.text()), "empty selection")


def test_drag_track_ends():
    for drag in (False, True):
        b, j, fps, nets = board()
        r = fps[0]
        p1 = pad(r, 1)
        a = xy(p1)
        t = T.track(b, a, (a[0] + 5, a[1] + 3), p1.GetNet())
        t_other = T.track(b, a, (a[0] - 3, a[1]), nets[7])     # another net through the pad: stays
        v = T.via(b, (60, 60), nets[0])
        tv = T.track(b, (60, 60), (65, 60), nets[0])
        m = am.Model(b)
        master(m, b, pad(j, 4))
        select(b, [p1, v])
        m.align(S(axis=g.AX_X, drag=drag))
        moved = T.xy(t.GetStart()) == xy(p1)
        check(moved == drag, "drag %s: track end on the pad %s" % (drag, moved))
        check(T.xy(t.GetEnd()) == (a[0] + 5, a[1] + 3), "far end stays")
        check(T.xy(t_other.GetStart()) == a, "other net not dragged")
        check((T.xy(tv.GetStart()) == xy(v)) == drag, "via track end")
        m.restore_all()
        check(T.xy(t.GetStart()) == a and T.xy(tv.GetStart()) == (60, 60), "restore drags")


def test_back_side_and_rotated_master():
    b, j, fps, _ = board()
    back = T.footprint(b, "U9", (50, 50), 45.0, back=True, courtyard=(2, 1),
                       pads=(((-1.5, 0), (0.6, 0.6)), ((1.5, 0), (0.6, 0.6))))
    m = am.Model(b)
    master(m, b, pad(back, 2))
    M = xy(pad(back, 2))
    select(b, fps)
    m.align(S(axis=g.AX_X, refpt=g.REF_BODY))
    for fp in fps:
        check(abs(am.body_centre(fp)[0] - M[0]) < E, "body centre on the master's X")
    check(back.IsFlipped(), "back part stays on the back")


def test_speed():
    b = pcbnew.BOARD()
    j = T.footprint(b, "J1", (5, 5))
    fps = [T.footprint(b, "R%d" % k, (10 + (k % 20) * 4, 10 + (k // 20) * 3), (0, 90)[k % 2]) for k in range(300)]
    for k in range(600):
        T.track(b, (k * 0.1, 100), (k * 0.1, 101), T.net(b, "S%d" % k) if k < 3 else b.GetNetInfo().GetNetItem(0))
    m = am.Model(b)
    master(m, b, pad(j, 1))
    select(b, fps)
    t0 = time.time()
    m.align(S(axis=g.AX_Y, drag=True))
    t1 = time.time()
    m.apply(S(axis=g.AX_X, drag=True))
    t2 = time.time()
    print("    300 parts: align %.0f ms, live change %.0f ms" % ((t1 - t0) * 1e3, (t2 - t1) * 1e3))
    check(t2 - t1 < 0.5, "speed")


# ------------------------------------------------------------------------ GUI

def gui(shots=None):
    from align_o_matic import dialog as dl
    H = T.gui_harness(dl.AlignDialog)
    b, j, fps, _ = board()
    snap0 = T.snapshot(b)
    select(b, [pad(j, 1)])                       # one item selected at start: the master
    M = xy(pad(j, 1))
    st = {}

    def s_open(d):
        H["settle"](d)
        check(d.ro["master"].GetLabel().startswith("J1 pad 1"), "master %r" % d.ro["master"].GetLabel())
        H["shot"](d, shots and os.path.join(shots, "align_x.png"))

    def s_actions(d):
        select(b, [pad(fp, 1) for fp in fps[:3]])
        d.on_act("align")
        check(all(abs(xy(pad(fp, 1))[0] - M[0]) < E for fp in fps[:3]), "aligned X from the window")
        d._toggle("axis", 1)
        H["settle"](d)
        check(all(abs(xy(pad(fp, 1))[1] - M[1]) < E for fp in fps[:3]), "toggle Y redoes it live")
        check("3 moved" in d.ro["last"].GetLabel(), "last %r" % d.ro["last"].GetLabel())
        select(b, [fps[4]])
        d.on_act("master")
        check(d.ro["master"].GetLabel().startswith("R5"), "new master %r" % d.ro["master"].GetLabel())
        select(b, [pad(fps[3], 2)])
        d._toggle("axis", 2)
        d.f["dx"].SetValue("0.5")
        H["settle"](d)
        d.on_act("align")
        H["shot"](d, shots and os.path.join(shots, "align_diag.png"))
        check(d.ro["done"].GetLabel() == "2 actions, 4 moved", "done %r" % d.ro["done"].GetLabel())
        select(b, [pad(j, 1), pad(j, 2)])
        d.on_act("master")
        check("exactly one" in d.status.GetLabel(), "two pads refused: %r" % d.status.GetLabel())
        d.on_act("undo")
        check(d.ro["done"].GetLabel() == "1 action, 3 moved", "undo %r" % d.ro["done"].GetLabel())
        d.more.Expand()
        d.on_more()
        d._toggle("axis", 4)
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "align_more.png"))
        st["final"] = T.snapshot(b)

    H["run"](am.AlignOMatic(), b, [s_open, s_actions, lambda d: d.finish(True)])
    check(T.snapshot(b) == st.get("final"), "OK keeps")

    b2, j2, fps2, _ = board()
    snap2 = T.snapshot(b2)
    select(b2, [pad(j2, 1)])

    def c_change(d):
        H["settle"](d)
        select(b2, fps2)
        d.on_act("align")
        select(b2, [pad(fps2[0], 2)])
        d.on_act("master")
        select(b2, [fps2[1]])
        d.on_act("align")
        check(T.snapshot(b2) != snap2, "changed")

    H["run"](am.AlignOMatic(), b2, [c_change, lambda d: d.finish(False)])
    check(T.snapshot(b2) == snap2, "Cancel restores every action")
    check(T.snapshot(b) != snap0, "first board changed")


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
    sys.exit(T.report("align-o-matic"))
