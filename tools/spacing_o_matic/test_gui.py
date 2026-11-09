# Drives the real dialog with the plugin's Run() on a pcbnew board (no PCB Editor):
#   xvfb-run -a python3 test_gui.py [screenshot_dir]
# pcbnew.GetBoard / Refresh and wx.MessageBox are replaced; everything else is real.

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import pcbnew  # noqa: E402
import wx  # noqa: E402

import test_pcbnew as T  # noqa: E402
from spacing_o_matic import geometry as g  # noqa: E402
from spacing_o_matic import spacing_o_matic as som  # noqa: E402
from spacing_o_matic import dialog as dl  # noqa: E402

SHOTS = sys.argv[1] if len(sys.argv) > 1 else None
app = wx.App(False)
boxes = []
wx.MessageBox = lambda *a, **k: boxes.append(a[0])
refreshes = [0]
pcbnew.Refresh = lambda: refreshes.__setitem__(0, refreshes[0] + 1)
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL", msg)


def find_dialog():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, dl.SpacingDialog) and w.IsShown():
            return w
    return None


def shot(win, name):
    if not SHOTS:
        return
    import time
    win.Layout()
    win.Refresh()
    for _ in range(10):
        win.Update()
        wx.GetApp().Yield(True)
        time.sleep(0.03)
    r = win.GetScreenRect()
    import subprocess          # X server screenshot (ImageMagick), crops the dialog
    subprocess.run(["import", "-window", "root", "-crop", "%dx%d+%d+%d" % (r.width, r.height, r.x, r.y),
                    os.path.join(SHOTS, name)], check=False)


def settle(d):
    """Run the debounced update now."""
    if d._timer is not None:
        d._timer.Stop()
    d.refresh_preview()


def run_plugin(board, script):
    pcbnew.GetBoard = lambda: board
    steps = list(script)

    def tick():
        d = find_dialog()
        if d is None:
            wx.CallLater(50, tick)
            return
        try:
            steps.pop(0)(d)
        except Exception as e:                     # keep the loop alive, report
            import traceback
            traceback.print_exc()
            FAILS.append("step raised %r" % e)
            d.finish(False)
            return
        if steps:
            wx.CallLater(30, tick)
    wx.CallLater(100, tick)
    som.SpacingOMatic().Run()


def offsets_of(board, ang):
    """Offsets (along the bus normal) of the straight lane tracks (length 8 mm)."""
    segs = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    import math
    out = {}
    for t in segs:
        a, b = som.xy(t.GetStart()), som.xy(t.GetEnd())
        if abs(math.dist(a, b) - 8.0) < 1.0 or (math.dist(a, b) > 5):
            n = (-math.sin(math.radians(ang)), math.cos(math.radians(ang)))
            out[t.GetNetname()] = (g.dot(a, n) + g.dot(b, n)) / 2
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------- scenario 1: OK
b, lanes = T.bus(30, [0, 0.7, 1.45, 2.1])
T.select(lanes)
before = T.coords(b)
u0 = T.unconnected(b)
state = {}


def s_open(d):
    settle(d)
    shot(d, "spacing_o_matic_dialog.png")
    check(d.now_p.GetLabel().startswith("0.650"), "now P %r" % d.now_p.GetLabel())
    check(d.f["value"].GetValue() != "", "value prefilled")
    state["value0"] = float(d.f["value"].GetValue())
    check(abs(state["value0"] - 0.7) < 0.001, "prefilled with mean pitch %s" % state["value0"])
    check(d.f["width"].GetValue() == "", "W empty = keep %r" % d.f["width"].GetValue())
    check(T.coords(b) != before, "equalised at once on open")


def s_set_value(d):
    d.f["value"].SetValue("0.6")
    settle(d)
    o = offsets_of(b, 30)
    check(all(abs(o[k + 1] - o[k] - 0.6) < 1e-5 for k in range(3)), "P 0.6 applied %s" % o)
    check(T.unconnected(b) == u0, "still connected")


def s_wheel(d):
    d.step_ch.SetSelection(dl.STEPS.index(0.05))
    for _ in range(3):
        d.bump(d.f["value"], "value", 1)        # same as one wheel notch up
    settle(d)
    check(d.f["value"].GetValue() == "0.75", "wheel +3 steps %r" % d.f["value"].GetValue())
    o = offsets_of(b, 30)
    check(all(abs(o[k + 1] - o[k] - 0.75) < 1e-5 for k in range(3)), "P 0.75 %s" % o)


def s_buttons(d):
    d.nudge("value", -1)                        # tighter
    d.nudge("shift", 1)                         # bus down
    d.nudge("shift", 1)
    settle(d)
    check(d.f["value"].GetValue() == "0.7", "tighter %r" % d.f["value"].GetValue())
    check(d.f["shift"].GetValue() == "0.1", "bus down %r" % d.f["shift"].GetValue())


def s_gap_mode(d):
    d.mode.SetSelection(1)
    d.on_change()
    settle(d)
    check(d.rows["value"][0].GetLabel() == "G", "label G")
    check(abs(float(d.f["value"].GetValue()) - 0.5) < 1e-6, "P 0.7 -> G 0.5 %r" % d.f["value"].GetValue())
    o = offsets_of(b, 30)
    check(all(abs(o[k + 1] - o[k] - 0.7) < 1e-5 for k in range(3)), "same spacing after mode switch %s" % o)
    shot(d, "spacing_o_matic_gap.png")


def s_ends_keep(d):
    for e in range(3):
        for k in range(3):
            d.ends.SetSelection(e)
            d.keep.SetSelection(k)
            d.on_change()
            settle(d)
            check(T.unconnected(b) == u0, "connected ends %d keep %d" % (e, k))
    d.ends.SetSelection(0)
    d.keep.SetSelection(1)
    d.on_change()
    settle(d)


def s_width(d):
    d.f["width"].SetValue("0.15")
    settle(d)
    ws = set(t.GetWidth() for t in b.GetTracks() if t.IsSelected())
    check(ws == {150000}, "width applied %s" % ws)
    d.f["width"].SetValue("")
    settle(d)


def s_more(d):
    d.more.Expand()
    d.on_more()
    d.c["values"].SetValue("0.4; 0.6; 0.5")
    d.on_change()
    settle(d)
    check(not d.f["value"].IsEnabled(), "value disabled with per-pair list")
    o = offsets_of(b, 30)
    gaps = [round(o[k + 1] - o[k] - 0.2, 5) for k in range(3)]
    check(gaps == [0.4, 0.6, 0.5], "per pair gaps %s" % gaps)
    shot(d, "spacing_o_matic_more.png")
    d.c["values"].SetValue("")
    d.c["snap"].SetValue("0.05")
    d.on_change()
    settle(d)
    d.c["snap"].SetValue("")
    d.more.Collapse()
    d.on_more()


def s_invalid(d):
    d.f["value"].SetValue("abc")
    settle(d)
    check("Invalid" in d.status.GetLabel(), "invalid shown %r" % d.status.GetLabel())
    d.f["value"].SetValue("0.3")                 # gap 0.3 -> fine
    settle(d)


def s_warn(d):
    d.f["value"].SetValue("0.1")                 # gap 0.1 < clearance 0.2
    settle(d)
    check(d.warn.IsShown(), "warning button shown")
    d.show_log()
    check("netclass clearance" in d.log_win.txt.GetValue(), "log text %r" % d.log_win.txt.GetValue())
    shot(d, "spacing_o_matic_warn.png")
    d.f["shift"].SetValue("0")
    d.f["value"].SetValue("0.3")
    settle(d)
    # the test board has one clearance problem of its own (lead of N3 near a pad, KiCad's
    # DRC reports it too): only that one may stay
    txt = d.log_win.txt.GetValue()
    check("netclass clearance" not in txt and txt.count("\u26a0") <= 1, "log updated %r" % txt)


def s_ok(d):
    state["final"] = T.coords(b)
    d.finish(True)


run_plugin(b, [s_open, s_set_value, s_wheel, s_buttons, s_gap_mode, s_ends_keep, s_width, s_more,
               s_invalid, s_warn, s_ok])
check(T.coords(b) == state.get("final"), "OK keeps the last change")
check(all("Track 4: closer than the clearance to other copper" in x for x in boxes), "problems at OK %s" % boxes)
o = offsets_of(b, 30)
check(all(abs(o[k + 1] - o[k] - 0.5) < 1e-5 for k in range(3)), "final G 0.3 (P 0.5) %s" % o)
check(T.unconnected(b) == u0, "connected after OK")
check(refreshes[0] > 5, "board refreshed %d" % refreshes[0])
print("scenario OK done, message boxes:", boxes)

# ---------------------------------------------------------------- scenario 2: Cancel
b, lanes = T.bus(135, [0, 0.8, 1.3], right="via")
T.select(lanes)
before = T.coords(b)
ntr = len(list(b.GetTracks()))


def c_change(d):
    d.f["value"].SetValue("0.9")
    d.ends.SetSelection(1)
    d.on_change()
    settle(d)
    check(T.coords(b) != before, "changed before cancel")
    check(len(list(b.GetTracks())) > ntr, "jogs added")


def c_cancel(d):
    d.finish(False)


run_plugin(b, [c_change, c_cancel])
check(T.coords(b) == before and len(list(b.GetTracks())) == ntr, "Cancel restores exactly")
print("scenario Cancel done")

# ---------------------------------------------------------------- scenario 3: reselect
b, lanes = T.bus(0, [0, 0.8, 1.3, 2.0])
T.select(lanes[:2])


def r_first(d):
    settle(d)
    check(d.summary.GetLabel().startswith("2 tracks"), "2 tracks %r" % d.summary.GetLabel())
    for t in b.GetTracks():
        t.ClearSelected()
    T.select(lanes)
    d.on_reselect()
    check(d.summary.GetLabel().startswith("4 tracks"), "reselect -> 4 %r" % d.summary.GetLabel())
    check(d.now_p.GetLabel().startswith("0.500–0.800"), "now after reselect %r" % d.now_p.GetLabel())


def r_ok(d):
    d.f["value"].SetValue("0.6")
    settle(d)
    d.finish(True)


run_plugin(b, [r_first, r_ok])
o = offsets_of(b, 0)
# the dialog remembers Gap mode from scenario 1: G 0.6 = P 0.8
check(all(abs(o[k + 1] - o[k] - 0.8) < 1e-5 for k in range(3)), "reselect result %s" % o)

# ---------------------------------------------------------------- scenario 4: nothing selected
boxes.clear()
b, lanes = T.bus(0, [0, 0.8])
pcbnew.GetBoard = lambda: b
som.SpacingOMatic().Run()
check(boxes and "Select" in boxes[0], "message for empty selection %s" % boxes)

# dark theme logo exists
for f in ("spacing_o_matic.png", "spacing_o_matic_dark.png", "spacing_o_matic_logo.png",
          "spacing_o_matic_logo_dark.png"):
    check(os.path.exists(os.path.join(HERE, f)), f)

print("FAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
