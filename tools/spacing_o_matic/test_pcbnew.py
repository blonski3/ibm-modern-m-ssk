# Tests on a real board with the pcbnew Python module (no PCB Editor window):
#   python3 test_pcbnew.py            (from any folder; needs KiCad's pcbnew module)
# Builds buses at many angles with pads, 45 deg leads and vias, runs the plugin's Model
# (the same code the dialog drives), checks the spacing, the connectivity (ratsnest),
# exact restore on Cancel and repeated changes without drift.

import math
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pcbnew  # noqa: E402

from spacing_o_matic import geometry as g  # noqa: E402
from spacing_o_matic import spacing_o_matic as som  # noqa: E402

IU = 1e6


def V(p):
    return pcbnew.VECTOR2I(int(round(p[0] * IU)), int(round(p[1] * IU)))


def rot(p, ang, c=(50.0, 50.0)):
    a = math.radians(ang)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a), c[1] + x * math.sin(a) + y * math.cos(a))


def new_board():
    b = pcbnew.BOARD()
    return b


def net(b, name):
    n = pcbnew.NETINFO_ITEM(b, name)
    b.Add(n)
    return n


def pad_fp(b, pos, nt, ang, size=(0.3, 0.3)):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetPosition(V(pos))
    b.Add(fp)
    p = pcbnew.PAD(fp)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I(int(size[0] * IU), int(size[1] * IU)))
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    p.SetLayerSet(ls)
    p.SetPosition(V(pos))
    p.SetNumber("1")
    p.SetNet(nt)
    fp.Add(p)
    return p


def track(b, a, c, nt, w=0.2, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(V(a))
    t.SetEnd(V(c))
    t.SetWidth(int(round(w * IU)))
    t.SetLayer(layer)
    t.SetNet(nt)
    b.Add(t)
    return t


def via(b, p, nt):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(p))
    v.SetWidth(int(0.6 * IU))
    v.SetDrill(int(0.3 * IU))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(nt)
    b.Add(v)
    return v


def bus(ang, offsets, right="pad", lead=1.5, length=8.0, w=0.2):
    """Bus around (50, 50): pad -> 45 deg lead -> lane -> 45 deg lead (or straight to a
    via, or a via right at the lane end) -> pad. Returns (board, lane tracks)."""
    b = new_board()
    lanes = []
    for k, o in enumerate(offsets):
        nt = net(b, "N%d" % k)
        y = 50 + o
        A, B = (46.0, y), (46.0 + length, y)
        PA = (A[0] - lead, y + lead)
        pad_fp(b, rot(PA, ang), nt, ang)
        track(b, rot(PA, ang), rot(A, ang), nt, w)
        lanes.append(track(b, rot(A, ang), rot(B, ang), nt, w))
        if right == "pad":
            PB = (B[0] + lead, y + lead)
            track(b, rot(B, ang), rot(PB, ang), nt, w)
            pad_fp(b, rot(PB, ang), nt, ang)
        elif right == "via":
            via(b, rot(B, ang), nt)
            pad_fp(b, rot(B, ang), nt, ang)   # via + pad on top: keeps ratsnest simple
    return b, lanes


def unconnected(b):
    b.BuildConnectivity()
    return b.GetConnectivity().GetUnconnectedCount(False) if hasattr(
        b.GetConnectivity(), "GetUnconnectedCount") else 0


def coords(b):
    out = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            out[som._uuid(t)] = (t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetWidth())
    return out


def settings(**kw):
    s = dict(mode=g.MODE_PITCH, value=0.5, values=[], width=0.0, keep=g.KEEP_CENTER,
             ends=g.ENDS_SLIDE, shift=0.0, snap=0.0, check=True, tol=1.0)
    s.update(kw)
    return s


def lane_offsets(model):
    out = []
    for L in model.bus.lanes:
        t = model.items[L["segs"][0].id]
        a, c = som.xy(t.GetStart()), som.xy(t.GetEnd())
        out.append((g.dot(a, model.bus.n) + g.dot(c, model.bus.n)) / 2)
    return out


def select(ts):
    for t in ts:
        t.SetSelected()


FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL", msg)


def test_angles_modes():
    for ang in (0, 15, 30, 45, 60, 90, 135, 180, 222.5, 270, 300):
        for right in ("pad", "via"):
            for mode, val in ((g.MODE_PITCH, 0.62), (g.MODE_GAP, 0.45)):
                for ends in (g.ENDS_SLIDE, g.ENDS_JOG, g.ENDS_STRETCH):
                    b, lanes = bus(ang, [0, 0.71, 1.43, 2.1, 2.95])
                    if right == "via":
                        b, lanes = bus(ang, [0, 0.71, 1.43, 2.1, 2.95], right="via")
                    u0 = unconnected(b)
                    before = coords(b)
                    select(lanes)
                    m = som.Model(b)
                    tr, _ = m.selected_tracks()
                    m.load(tr, 1.0)
                    tag = "ang %g right %s %s %s" % (ang, right, mode, ends)
                    check(len(m.bus.lanes) == 5, tag + " lanes %d" % len(m.bus.lanes))
                    res, warn = m.evaluate(settings(mode=mode, value=val, ends=ends))
                    m.apply(res)
                    o = lane_offsets(m)
                    step = val if mode == g.MODE_PITCH else val + 0.2
                    check(all(abs(o[k + 1] - o[k] - step) < 2e-6 for k in range(4)), tag + " spacing %s" % o)
                    check(unconnected(b) == u0, tag + " unconnected %d -> %d" % (u0, unconnected(b)))
                    check(not [w for w in warn if "other copper" not in w], tag + " " + str(warn))
                    if ends == g.ENDS_SLIDE and right == "pad":
                        check(not res["new"], tag + " jogs added while sliding")
                    if right == "via" and ends != g.ENDS_STRETCH:
                        check(len(res["new"]) > 0, tag + " no jog at the via end")
                    # 10 more changes, then restore: exact original coordinates
                    rnd = random.Random(int(ang * 10))
                    for _ in range(10):
                        res, warn = m.evaluate(settings(mode=mode, value=rnd.uniform(0.3, 0.9),
                                                        ends=ends, shift=rnd.uniform(-0.3, 0.3)))
                        m.apply(res)
                        check(unconnected(b) == u0, tag + " unconnected after repeat")
                    m.restore()
                    check(coords(b) == before, tag + " restore not exact")


def test_keep_and_shift_and_snap():
    b, lanes = bus(0, [0.013, 0.4, 0.95])
    select(lanes)
    m = som.Model(b)
    m.load(m.selected_tracks()[0], 1.0)
    for keep, idx in ((g.KEEP_FIRST, 0), (g.KEEP_LAST, -1)):
        before = [L["o"] for L in m.bus.lanes]
        res, _ = m.evaluate(settings(keep=keep, value=0.5))
        m.apply(res)
        o = lane_offsets(m)
        check(abs(o[idx] - before[idx]) < 2e-6, "keep %s" % keep)
    res, _ = m.evaluate(settings(keep=g.KEEP_FIRST, value=0.5, shift=0.2, snap=0.1))
    m.apply(res)
    o = lane_offsets(m)
    check(abs((o[0] + 50) % 0.1) < 2e-6 or abs((o[0] + 50) % 0.1 - 0.1) < 2e-6, "snap %s" % o)
    m.restore()


def test_width_and_per_pair():
    b, lanes = bus(30, [0, 0.4, 0.8, 1.2])
    select(lanes)
    m = som.Model(b)
    m.load(m.selected_tracks()[0], 1.0)
    res, _ = m.evaluate(settings(mode=g.MODE_GAP, value=0.2, width=0.15))
    m.apply(res)
    for L in m.bus.lanes:
        check(m.items[L["segs"][0].id].GetWidth() == 150000, "width")
    o = lane_offsets(m)
    check(all(abs(o[k + 1] - o[k] - 0.35) < 2e-6 for k in range(3)), "gap with width %s" % o)
    res, _ = m.evaluate(settings(values=[0.4, 0.6, 0.5], keep=g.KEEP_FIRST))
    m.apply(res)
    o = lane_offsets(m)
    check([round(o[k + 1] - o[k], 5) for k in range(3)] == [0.4, 0.6, 0.5], "per pair %s" % o)
    m.restore()


def test_clearance_check_vs_obstacles():
    b, lanes = bus(0, [0, 0.6, 1.2])
    other = net(b, "OTHER")
    # a foreign track just above the bus and a foreign pad below it
    track(b, (47, 49.35), (53, 49.35), other, 0.2)
    pad_fp(b, (50, 51.9), other, 0, size=(0.5, 0.5))
    select(lanes)
    m = som.Model(b)
    m.load(m.selected_tracks()[0], 1.0)
    res, warn = m.evaluate(settings(value=0.6, keep=g.KEEP_CENTER))
    check(not any("clearance to other copper" in w for w in warn), "false alarm %s" % warn)
    res, warn = m.evaluate(settings(value=0.6, keep=g.KEEP_CENTER, shift=-0.3))
    check(1 in res["issues"].d.get("close", [()])[0], "track 1 vs foreign track %s" % warn)
    res, warn = m.evaluate(settings(value=0.6, keep=g.KEEP_CENTER, shift=0.35))
    check(any("other copper" in w for w in warn), "track 3 vs foreign pad %s" % warn)
    res, warn = m.evaluate(settings(value=0.35))
    check(any("netclass clearance" in w for w in warn), "gap vs netclass %s" % warn)
    res, warn = m.evaluate(settings(value=0.35, check=False))
    check(not any("other copper" in w for w in warn), "check off still checks copper")


def test_selection_filters():
    b, lanes = bus(45, [0, 0.6, 1.2])
    # select everything incl. leads: same result
    for t in b.GetTracks():
        t.SetSelected()
    m = som.Model(b)
    tr, arcs = m.selected_tracks()
    m.load(tr, 1.0)
    check(len(m.bus.lanes) == 3 and m.bus.ignored == 6, "select all: lanes %d ignored %d"
          % (len(m.bus.lanes), m.bus.ignored))
    res, _ = m.evaluate(settings(value=0.6))
    m.apply(res)
    o = lane_offsets(m)
    check(all(abs(o[k + 1] - o[k] - 0.6) < 2e-6 for k in range(2)), "select all spacing")
    m.restore()


def test_summary_and_log():
    b, lanes = bus(0, [0, 0.4, 0.8])
    fn = os.path.join(tempfile.mkdtemp(), "t.kicad_pcb")
    b.SetFileName(fn)
    select(lanes)
    m = som.Model(b)
    m.load(m.selected_tracks()[0], 1.0)
    s = som.summary(m)
    check(s.startswith("3 tracks, 0°, F.Cu"), "summary %r" % s)
    r = som.readouts(m.bus)
    check(r["now_p"] == "0.400 mm" and r["now_g"] == "0.200 mm", "readouts %s" % r)
    som.write_log(b, settings(), "P 0.5 mm", ["Track 1: x → y"], m)
    check(os.path.exists(os.path.join(os.path.dirname(fn), "spacing_o_matic.log")), "log")


def test_saved_board_and_drc():
    """Apply, save, load again: the file holds the new geometry and stays connected."""
    b, lanes = bus(30, [0, 0.33, 0.9, 1.4], right="via")
    d = tempfile.mkdtemp()
    fn = os.path.join(d, "bus.kicad_pcb")
    select(lanes)
    m = som.Model(b)
    m.load(m.selected_tracks()[0], 1.0)
    res, _ = m.evaluate(settings(value=0.45))
    m.apply(res)
    pcbnew.SaveBoard(fn, b)
    b2 = pcbnew.LoadBoard(fn)
    check(unconnected(b2) == 0, "saved board unconnected %d" % unconnected(b2))
    check(len(coords(b2)) == len(coords(b)), "saved track count")


def drc_track_nets(b):
    """Nets of tracks in KiCad's own clearance violations (pcbnew.WriteDRCReport)."""
    import re
    d = tempfile.mkdtemp()
    fn = os.path.join(d, "x.kicad_pcb")
    pcbnew.SaveBoard(fn, b)
    rpt = os.path.join(d, "drc.rpt")
    # in a fresh process: repeated DRC runs in one process stop reporting (KiCad 7)
    import subprocess
    subprocess.run([sys.executable, "-c",
                    "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)",
                    fn, rpt], check=True, capture_output=True)
    nets, block = set(), None
    for line in open(rpt, encoding="utf-8"):
        if line.startswith("["):
            block = line.startswith("[clearance]")
            continue
        if block:
            m = re.search(r"Track \[([^\]]+)\]", line)
            if m:
                nets.add(m.group(1))
    return nets


def test_check_matches_kicad_drc():
    """The quick clearance check flags the same tracks as KiCad's DRC (random cases)."""
    if not hasattr(pcbnew, "WriteDRCReport"):
        print("  (no WriteDRCReport, skipped)")
        return
    rnd = random.Random(7)
    agree = 0
    for it in range(40):
        ang = rnd.choice([0, 30, 45, 90, 135, 200, 315])
        offs = [0.0]
        for _ in range(rnd.randint(2, 5)):
            offs.append(offs[-1] + rnd.uniform(0.6, 1.1))
        right = rnd.choice(["pad", "via"])
        b, lanes = bus(ang, offs, right=right)
        before = drc_track_nets(b)
        select(lanes)
        m = som.Model(b)
        m.load(m.selected_tracks()[0], 1.0)
        s = settings(mode=rnd.choice([g.MODE_PITCH, g.MODE_GAP]), value=rnd.uniform(0.3, 0.9),
                     keep=rnd.choice([g.KEEP_FIRST, g.KEEP_CENTER, g.KEEP_LAST]),
                     ends=rnd.choice([g.ENDS_SLIDE, g.ENDS_JOG, g.ENDS_STRETCH]),
                     shift=rnd.choice([0.0, 0.3, -0.3]))
        res, warn = m.evaluate(s)
        m.apply(res)
        kicad = drc_track_nets(b) - before
        mine = set()
        iss = res["issues"].d
        for code in ("close", "gap_clr", "overlap"):
            if code in iss:
                for no in iss[code][0]:
                    mine.add(m.netname[m.bus.lanes[no - 1]["net"]])
                    if code != "close" and no >= 2:        # a gap involves both neighbours
                        mine.add(m.netname[m.bus.lanes[no - 2]["net"]])
        tag = "drc it %d ang %s %s %s" % (it, ang, right, s)
        check(kicad <= mine, tag + " KiCad finds %s, check found %s" % (sorted(kicad), sorted(mine)))
        extra = mine - kicad - before
        check(not extra, tag + " false alarm %s (KiCad %s)" % (sorted(extra), sorted(kicad)))
        agree += kicad <= mine and not extra
    print("  check == KiCad DRC in %d / 40 random cases" % agree)


def test_speed():
    import time
    offs = [k * 0.5 + random.Random(k).uniform(-0.1, 0.1) for k in range(32)]
    b, lanes = bus(20, offs, length=40)
    # lots of unrelated copper around
    other = net(b, "GND")
    for k in range(3000):
        x, y = 30 + (k % 60) * 0.7, 30 + (k // 60) * 0.9
        if 44 < y < 70:
            continue
        track(b, (x, y), (x + 0.4, y), other, 0.15)
    select(lanes)
    m = som.Model(b)
    t0 = time.time()
    m.load(m.selected_tracks()[0], 1.0)
    t1 = time.time()
    for k in range(20):
        res, _ = m.evaluate(settings(value=0.4 + k * 0.01))
        m.apply(res)
    t2 = time.time()
    print("speed: load %.0f ms, evaluate+apply %.1f ms each (32 tracks, 3000 others)"
          % ((t1 - t0) * 1e3, (t2 - t1) / 20 * 1e3))
    check((t2 - t1) / 20 < 0.2, "too slow")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            n0 = len(FAILS)
            fn()
            print("ok  " if len(FAILS) == n0 else "FAIL", name)
    print("FAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)
