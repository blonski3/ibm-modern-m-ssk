# Tests of net-o-matic on real boards (pcbnew module, KiCad 7+):  python3 test_net.py
# GUI:  xvfb-run -a python3 test_net.py gui [screenshot_dir]

import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.append(HERE)

import pcbnew  # noqa: E402

import tboard as T  # noqa: E402
from net_o_matic import nets as N  # noqa: E402
from net_o_matic import net_o_matic as nm  # noqa: E402

check = T.check


def V(**kw):
    v = dict(tracks=True, vias=True, pads=False, zones=True, connected=False, swap=False, net=None)
    v.update(kw)
    return v


def clear(b):
    for fp in b.GetFootprints():
        fp.ClearSelected()
        for p in fp.Pads():
            p.ClearSelected()
    for t in b.GetTracks():
        t.ClearSelected()
    for z in b.Zones():
        z.ClearSelected()


def select(b, items):
    clear(b)
    for it in items:
        it.SetSelected()
        if it.GetClass() == "FOOTPRINT":
            for p in it.Pads():
                p.SetSelected()


def pad(fp, num):
    return [p for p in fp.Pads() if p.GetNumber() == str(num)][0]


def nets_of(items):
    return [str(it.GetNetname()) for it in items]


def board():
    """J1 (GND, VBUS, D+, D-) -> U1 (GND, VBUS, D+, D-) with a few chains:
    D+ : J1.3 - t1 - t2 - via - t3(B) - U1.3 ; a no-net stub t4 off U1.1 (GND pad)."""
    b = pcbnew.BOARD()
    nm_ = {n: T.net(b, n) for n in ("GND", "VBUS", "/USB/D+", "/USB/D-", "+3V3", "Net-(U1-PA0)")}
    pads = [((0.0, k * 2.0), (1.2, 1.2)) for k in range(4)]
    j = T.footprint(b, "J1", (10.0, 10.0), pads=pads,
                    nets=[nm_["GND"], nm_["VBUS"], nm_["/USB/D+"], nm_["/USB/D-"]], courtyard=(1.0, 4.0))
    u = T.footprint(b, "U1", (30.0, 10.0), pads=pads,
                    nets=[nm_["GND"], nm_["VBUS"], nm_["/USB/D+"], nm_["/USB/D-"]], courtyard=(1.0, 4.0))
    dp = nm_["/USB/D+"]
    t1 = T.track(b, (10.0, 14.0), (15.0, 14.0), dp)
    t2 = T.track(b, (15.0, 14.0), (18.0, 17.0), dp)
    v1 = T.via(b, (18.0, 17.0), dp)
    t3 = T.track(b, (18.0, 17.0), (30.0, 14.0), dp, layer=pcbnew.B_Cu)
    # D- route on F.Cu that does not touch the D+ one
    dm = nm_["/USB/D-"]
    t5 = T.track(b, (10.0, 16.0), (14.0, 20.0), dm)
    t6 = T.track(b, (14.0, 20.0), (30.0, 20.0), dm)
    v2 = T.via(b, (22.0, 20.0), dm)                # a via in the middle of t6
    t7 = T.track(b, (30.0, 20.0), (30.0, 16.0), dm)
    # a no-net stub that starts on U1 pad 1 (GND)
    t4 = T.track(b, (30.0, 10.0), (34.0, 6.0), b.FindNet(0))
    # a lonely no-net via
    v3 = T.via(b, (40.0, 30.0), b.FindNet(0))
    return b, dict(j=j, u=u, t1=t1, t2=t2, t3=t3, t4=t4, t5=t5, t6=t6, t7=t7, v1=v1, v2=v2, v3=v3, n=nm_)


def test_rank():
    names = ["GND", "GNDA", "/USB/D+", "/USB/D-", "VBUS", "+3V3", "Net-(U1-PA0)", "Net-(U1-PA10)",
             "Net-(U1-PA2)", "SIG_GND_SENSE", "AGND"]
    r = N.rank(names, "gnd")
    check(r[0] == "GND", "exact first: %s" % r)
    check(r.index("GNDA") < r.index("SIG_GND_SENSE") < r.index("AGND"), "prefix, word, substring: %s" % r)
    r = N.rank(names, "d+")
    check(r[0] == "/USB/D+", "leaf exact: %s" % r)
    r = N.rank(names, "pa")
    check(r[:3] == ["Net-(U1-PA0)", "Net-(U1-PA2)", "Net-(U1-PA10)"], "natural order: %s" % r)
    r = N.rank(names, "u1 pa1")
    check(r == ["Net-(U1-PA10)"], "two words: %s" % r)
    r = N.rank(names, "vbs")
    check(r == ["VBUS"], "letters in order: %s" % r)
    r = N.rank(names, "", {"VBUS": 0, "+3V3": 1})
    check(r[:2] == ["VBUS", "+3V3"], "boost on top: %s" % r)
    r = N.rank(names, "g", {"AGND": 0})
    check(r[0] == "GND" or r[0] == "GNDA", "boost does not beat a better tier: %s" % r)
    check(N.no_net_matches("") and N.no_net_matches("none") and N.no_net_matches("-") and
          not N.no_net_matches("gnd"), "no net entry")


def test_tracks_and_vias():
    b, it = board()
    select(b, [it["t1"], it["t2"], it["v1"]])
    m = nm.Model(b)
    check(m.summary().startswith("2 tracks · 1 via"), "summary %r" % m.summary())
    iss = m.apply(V(net="GND"))
    check(nets_of([it["t1"], it["t2"], it["v1"]]) == ["GND"] * 3, "changed: %s" % nets_of([it["t1"], it["t2"], it["v1"]]))
    check(str(it["t3"].GetNetname()) == "/USB/D+", "t3 untouched")
    check("short" in iss, "t1 starts on J1 pad 3 (D+) -> short to %s" % iss.text())
    m.apply(V(net="/USB/D+"))
    check(not len(m.edits), "back on its own net = nothing changed")
    m.apply(V(net="VBUS", tracks=False))
    check(nets_of([it["t1"], it["t2"], it["v1"]]) == ["/USB/D+", "/USB/D+", "VBUS"], "Tracks off: only the via")
    m.restore_all()
    check(nets_of([it["t1"], it["t2"], it["v1"]]) == ["/USB/D+"] * 3, "restore")


def test_vias_only():
    b, it = board()
    select(b, [it["v1"], it["v2"]])
    m = nm.Model(b)
    check(m.summary().startswith("2 vias"), "summary %r" % m.summary())
    check(m.swap_pair() is not None, "two nets -> swap possible")
    m.apply(V(net="GND"))
    check(nets_of([it["v1"], it["v2"]]) == ["GND", "GND"], "vias only")
    check(nets_of([it["t2"], it["t6"]]) == ["/USB/D+", "/USB/D-"], "tracks stay")
    m.apply(V(net="GND", vias=False))
    check(nets_of([it["v1"], it["v2"]]) == ["/USB/D+", "/USB/D-"], "Vias off: nothing")


def test_connected():
    b, it = board()
    select(b, [it["t2"]])
    m = nm.Model(b)
    m.apply(V(net="+3V3", connected=True))
    chain = [it["t1"], it["t2"], it["v1"], it["t3"]]
    check(nets_of(chain) == ["+3V3"] * 4, "whole D+ chain: %s" % nets_of(chain))
    check(str(pad(it["j"], 3).GetNetname()) == "/USB/D+", "pads are not changed")
    check(str(it["t5"].GetNetname()) == "/USB/D-", "other net untouched")
    m.apply(V(net="+3V3", connected=True, vias=False))
    check(nets_of(chain) == ["+3V3", "+3V3", "/USB/D+", "+3V3"], "connected through the via, via itself kept")
    # D-: a via in the middle of a track joins it; the chain stops at U1 pad 4
    select(b, [it["t5"]])
    m.keep()
    m.select()
    m.apply(V(net="GND", connected=True))
    check(nets_of([it["t5"], it["t6"], it["v2"], it["t7"]]) == ["GND"] * 4, "D- chain with mid via")
    check(str(it["t4"].GetNetname()) == "", "no-net stub not taken")
    m.restore_all()
    check(nets_of(chain + [it["t5"], it["t6"], it["v2"], it["t7"]]) == ["/USB/D+"] * 4 + ["/USB/D-"] * 4,
          "restore all steps")


def test_touch_and_shorts():
    b, it = board()
    select(b, [it["t4"]])
    m = nm.Model(b)
    gnd = m.code_of["GND"]
    check(m.touch.most_common(1)[0][0] == gnd, "no-net stub touches U1 pad 1 (GND): %s" % m.touch)
    iss = m.apply(V(net="GND"))
    check("short" not in iss, "right net, no warning: %s" % iss.text())
    iss = m.apply(V(net="VBUS"))
    check("short" in iss and any("U1 pad 1" in x for x in iss.items("short")), "wrong net warns: %s" % iss.text())
    iss = m.apply(V(net=N.NO_NET))
    check("short" not in iss, "no net never warns")


def test_swap():
    b, it = board()
    select(b, [it["t1"], it["t5"], it["v3"]])
    m = nm.Model(b)
    check(m.swap_pair() == tuple(sorted((m.code_of["/USB/D+"], m.code_of["/USB/D-"]))), "pair %s" % (m.swap_pair(),))
    m.apply(V(swap=True))
    check(nets_of([it["t1"], it["t5"], it["v3"]]) == ["/USB/D-", "/USB/D+", ""], "swapped, no-net via left")
    m.restore_all()
    check(nets_of([it["t1"], it["t5"]]) == ["/USB/D+", "/USB/D-"], "restore")
    select(b, [it["t1"], it["t2"]])
    m = nm.Model(b)
    check(m.swap_pair() is None, "one net -> no swap")


def test_new_net_and_no_net():
    b, it = board()
    select(b, [it["v3"]])
    m = nm.Model(b)
    n0 = b.GetNetCount()
    iss = m.apply(V(net="TEST_NET"))
    check(str(it["v3"].GetNetname()) == "TEST_NET" and "newnet" in iss, "new net made")
    check(b.FindNet("TEST_NET") is not None, "on the board")
    m.apply(V(net="TEST_NET"))
    check(b.GetNetCount() == n0 + 1, "redo does not pile up nets (%d)" % b.GetNetCount())
    m.apply(V(net="GND"))
    check(b.FindNet("TEST_NET") is None, "new net removed when not used")
    m.apply(V(net="TEST2"))
    m.keep()
    check("TEST2" in m.code_of, "kept new net is in the list")
    m.restore_all()
    check(b.FindNet("TEST2") is None and b.GetNetCount() == n0, "cancel removes it")
    select(b, [it["t1"]])
    m = nm.Model(b)
    m.apply(V(net=N.NO_NET))
    check(it["t1"].GetNetCode() == 0, "no net")


def test_pads_and_zones():
    b, it = board()
    z = T.zone(b, [(0, 0), (5, 0), (5, 5), (0, 5)], it["n"]["GND"])
    p4 = pad(it["u"], 4)
    select(b, [z, p4, it["t6"]])
    m = nm.Model(b)
    check(m.summary().startswith("1 track · 1 pad · 1 zone"), "summary %r" % m.summary())
    iss = m.apply(V(net="+3V3"))
    check(str(z.GetNetname()) == "+3V3" and "zone" in iss, "zone changed")
    check(str(p4.GetNetname()) == "/USB/D-", "pads off by default")
    iss = m.apply(V(net="+3V3", pads=True))
    check(str(p4.GetNetname()) == "+3V3" and "pad" in iss, "pad with Pads on")
    m.apply(V(net="+3V3", zones=False))
    check(str(z.GetNetname()) == "GND", "Zones off")
    select(b, [it["u"]])
    m = nm.Model(b)
    check(not m.sel["pad"] and m.other == 1, "a selected footprint is not its pads")


def test_steps_keep_cancel():
    b, it = board()
    snap = {kc_uuid(t): t.GetNetCode() for t in b.GetTracks()}
    select(b, [it["t1"]])
    m = nm.Model(b)
    m.apply(V(net="GND"))
    m.keep()
    select(b, [it["t5"], it["v2"]])
    m.select()
    check(m.now[m.code_of["/USB/D-"]] == 2, "new selection read")
    m.apply(V(net="VBUS"))
    m.keep()
    check(m.done_text() == "2 changes, 3 items", "done %r" % m.done_text())
    check(m.recent[:2] == ["VBUS", "GND"], "recent %s" % m.recent)
    m.restore_all()
    check({kc_uuid(t): t.GetNetCode() for t in b.GetTracks()} == snap, "cancel restores both steps")


def kc_uuid(t):
    return t.m_Uuid.AsString()


def test_speed():
    rnd = random.Random(3)
    b = pcbnew.BOARD()
    nets = [T.net(b, "N%03d" % k) for k in range(400)]
    for k in range(120):
        T.footprint(b, "U%d" % k, (10 + (k % 12) * 8.0, 10 + (k // 12) * 8.0),
                    pads=[((x * 0.65, 0.0), (0.4, 1.0)) for x in range(8)],
                    nets=[nets[rnd.randrange(400)] for _ in range(8)], courtyard=(3.0, 1.0))
    trs = []
    for k in range(3000):
        x, y = rnd.uniform(0, 100), rnd.uniform(0, 90)
        trs.append(T.track(b, (x, y), (x + rnd.uniform(-3, 3), y + rnd.uniform(-3, 3)), nets[k % 400]))
    vias = [T.via(b, (rnd.uniform(0, 100), rnd.uniform(0, 90)), nets[k % 400]) for k in range(400)]
    select(b, trs[:40] + vias[:10])
    t0 = time.time()
    m = nm.Model(b)
    t1 = time.time()
    for name in ("N001", "N002", "N003", "N004", "N005"):
        m.apply(V(net=name, connected=True))
    t2 = time.time()
    for q in ("n", "n0", "n00", "n001", "n1", "x"):
        N.rank(m.names, q)
    t3 = time.time()
    print("    speed: open %.0f ms (960 pads, 3400 tracks/vias), apply %.1f ms, filter %.2f ms" %
          ((t1 - t0) * 1e3, (t2 - t1) * 1e3 / 5, (t3 - t2) * 1e3 / 6))
    check(t1 - t0 < 3.0 and (t2 - t1) / 5 < 0.5 and (t3 - t2) / 6 < 0.05, "fast enough")


# ---------------------------------------------------------------- GUI

def gui(shots=None):
    import wx
    from net_o_matic import dialog as dl
    H = T.gui_harness(dl.NetDialog)
    b, it = board()
    select(b, [it["t4"], it["t1"]])
    st = {}

    def s_open(d):
        H["settle"](d)
        check(d.search.GetValue() == "" and d.list.rows, "list filled")
        check(d.pick == (dl.ROW_NET, "GND"), "touching net highlighted at the start: %s" % (d.pick,))
        check(str(it["t4"].GetNetname()) == "GND", "and shown live")
        H["shot"](d, shots and os.path.join(shots, "net_open.png"))

    def s_type(d):
        d.search.SetValue("vb")
        H["settle"](d)
        check(d.pick == (dl.ROW_NET, "VBUS"), "typing picks VBUS: %s" % (d.pick,))
        check(nets_of([it["t4"], it["t1"]]) == ["VBUS", "VBUS"], "live VBUS")
        check(d.warn.IsShown(), "short warning shown")
        d.on_search_key(_Key(wx.WXK_DOWN))
        check(d.list.selected() in (-1, 0, 1), "arrow moves")
        d.search.SetValue("d-")
        H["settle"](d)
        check(d.pick == (dl.ROW_NET, "/USB/D-"), "d- -> /USB/D-: %s" % (d.pick,))
        d.search.SetValue("newnet1")
        H["settle"](d)
        check(d.pick is None and d.list.rows[-1][0] == dl.ROW_NEW, "unknown name: new row offered, not picked")
        check(nets_of([it["t4"], it["t1"]]) == ["", "/USB/D+"], "nothing picked -> board as before")
        d.search.SetValue("-")
        H["settle"](d)
        check(d.pick == (dl.ROW_NONE, N.NO_NET), "'-' = no net")
        d.search.SetValue("gnd")
        H["settle"](d)
        H["shot"](d, shots and os.path.join(shots, "net_gnd.png"))
        st["t4"] = str(it["t4"].GetNetname())
        d.accept()

    H["run"](nm.NetOMatic(), b, [s_open, s_type])
    check(str(it["t4"].GetNetname()) == "GND" and str(it["t1"].GetNetname()) == "GND", "Enter keeps GND")

    # vias only + swap + reselect + cancel
    b2, it2 = board()
    select(b2, [it2["v1"], it2["v2"]])
    snap = {kc_uuid(t): t.GetNetCode() for t in b2.GetTracks()}

    def c_swap(d):
        H["settle"](d)
        check(d.cb["vias"].GetLabel() == "Vias 2" and not d.cb["tracks"].IsEnabled(), "vias only labels")
        check(d.swap.IsEnabled(), "swap enabled for two nets")
        d.swap.SetValue(True)
        d.on_swap(None)
        H["settle"](d)
        check(nets_of([it2["v1"], it2["v2"]]) == ["/USB/D-", "/USB/D+"], "swapped live")
        H["shot"](d, shots and os.path.join(shots, "net_swap.png"))
        select(b2, [it2["t6"]])
        d.on_reselect()
        check(len(d.model.done) == 1 and nets_of([it2["v1"], it2["v2"]]) == ["/USB/D-", "/USB/D+"],
              "swap kept after ↻")
        check(d.pick == (dl.ROW_NET, "/USB/D+"), "t6 now touches the swapped via (D+): %s" % (d.pick,))
        d.search.SetValue("+3")
        H["settle"](d)
        d.cb["connected"].SetValue(True)
        d.on_change()
        H["settle"](d)
        check(str(it2["t7"].GetNetname()) == "+3V3", "connected in the window")
        d.more.Expand()
        d.on_more()
        H["shot"](d, shots and os.path.join(shots, "net_more.png"))

    H["run"](nm.NetOMatic(), b2, [c_swap, lambda d: d.finish(False)])
    check({kc_uuid(t): t.GetNetCode() for t in b2.GetTracks()} == snap, "Cancel restores both steps")


class _Key:
    def __init__(self, code):
        self.code = code

    def GetKeyCode(self):
        return self.code

    def Skip(self):
        pass


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
    sys.exit(T.report("net-o-matic"))
