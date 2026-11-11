# Test helpers shared by the *-o-matic plugins: build small boards with the real pcbnew
# module, run KiCad's DRC in a separate process, drive a plugin dialog under xvfb.
# Not loaded by KiCad (only the plugin's __init__.py is).

import math
import os
import subprocess
import sys
import tempfile

import pcbnew

IU = 1e6
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL", msg)
    return cond


def V(p):
    return pcbnew.VECTOR2I(int(round(p[0] * IU)), int(round(p[1] * IU)))


def xy(v):
    return (v.x / IU, v.y / IU)


def rot(p, ang, c=(0.0, 0.0)):
    a = math.radians(ang)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a), c[1] + x * math.sin(a) + y * math.cos(a))


def net(b, name):
    n = pcbnew.NETINFO_ITEM(b, name)
    b.Add(n)
    return n


def footprint(b, ref, pos, ang=0.0, pads=(((-0.8, 0), (0.8, 0.9)), ((0.8, 0), (0.8, 0.9))),
              nets=None, courtyard=(1.6, 0.9), value="10k", back=False, smd=True):
    """Footprint with rectangular SMD pads ((x, y) local, (w, h)), a courtyard rectangle
    (half sizes) and Reference / Value texts. ang in KiCad degrees (CCW on screen)."""
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference(ref)
    fp.SetValue(value)
    b.Add(fp)
    for k, ((x, y), (w, h)) in enumerate(pads):
        p = pcbnew.PAD(fp)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD if smd else pcbnew.PAD_ATTRIB_PTH)
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(int(w * IU), int(h * IU)))
        if not smd:
            p.SetDrillSize(pcbnew.VECTOR2I(int(min(w, h) * 0.5 * IU), int(min(w, h) * 0.5 * IU)))
            ls = pcbnew.PAD.PTHMask()
        else:
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.F_Cu)
            ls.AddLayer(pcbnew.F_Mask)
            ls.AddLayer(pcbnew.F_Paste)
        p.SetLayerSet(ls)
        p.SetPosition(V((x, y)))
        if hasattr(p, "SetPos0"):          # KiCad 7: the position inside the footprint
            p.SetPos0(V((x, y)))
        p.SetNumber(str(k + 1))
        if nets and nets[k] is not None:
            p.SetNet(nets[k])
        fp.Add(p)
    if courtyard:
        cw, ch = courtyard
        for (x0, y0), (x1, y1) in (((-cw, -ch), (cw, -ch)), ((cw, -ch), (cw, ch)),
                                   ((cw, ch), (-cw, ch)), ((-cw, ch), (-cw, -ch))):
            s = pcbnew.FP_SHAPE(fp) if hasattr(pcbnew, "FP_SHAPE") else pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V((x0, y0)))
            s.SetEnd(V((x1, y1)))
            if hasattr(s, "SetStart0"):
                s.SetStart0(V((x0, y0)))
                s.SetEnd0(V((x1, y1)))
            s.SetLayer(pcbnew.F_CrtYd)
            s.SetWidth(int(0.05 * IU))
            fp.Add(s)
    try:
        fp.Reference().SetPosition(V((0, -1.5)))
        fp.Value().SetPosition(V((0, 1.5)))
        fp.Value().SetVisible(False)
    except Exception:
        pass
    fp.SetPosition(V(pos))
    if ang:
        fp.SetOrientationDegrees(ang)
    if back:
        fp.Flip(V(pos), False)
    return fp


def track(b, a, c, nt, w=0.2, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(V(a))
    t.SetEnd(V(c))
    t.SetWidth(int(round(w * IU)))
    t.SetLayer(layer)
    t.SetNet(nt)
    b.Add(t)
    return t


def arc(b, a, m, c, nt, w=0.2, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_ARC(b)
    t.SetStart(V(a))
    t.SetMid(V(m))
    t.SetEnd(V(c))
    t.SetWidth(int(round(w * IU)))
    t.SetLayer(layer)
    t.SetNet(nt)
    b.Add(t)
    return t


def via(b, p, nt, d=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(p))
    v.SetWidth(int(d * IU))
    v.SetDrill(int(drill * IU))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(nt)
    b.Add(v)
    return v


def outline(b, x0, y0, x1, y1):
    for (a, c) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(a))
        s.SetEnd(V(c))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(int(0.1 * IU))
        b.Add(s)


def zone(b, pts, nt, layer=pcbnew.F_Cu):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(nt)
    ol = z.Outline()
    ol.NewOutline()
    for p in pts:
        ol.Append(int(p[0] * IU), int(p[1] * IU))
    b.Add(z)
    return z


def tracks(b):
    return [t for t in b.GetTracks() if t.GetClass() in ("PCB_TRACK", "PCB_ARC")]


def snapshot(b):
    """Exact state of tracks, vias and footprints (for restore checks)."""
    out = {}
    for t in b.GetTracks():
        u = t.m_Uuid.AsString()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            out[u] = ("via", p.x, p.y, t.GetWidth())
        else:
            s, e = t.GetStart(), t.GetEnd()
            m = t.GetMid() if t.GetClass() == "PCB_ARC" else s
            out[u] = (t.GetClass(), s.x, s.y, e.x, e.y, m.x, m.y, t.GetWidth(), t.GetLayer())
    for fp in b.GetFootprints():
        p = fp.GetPosition()
        r = fp.Reference()
        rp = r.GetPosition()
        out[fp.m_Uuid.AsString()] = ("fp", p.x, p.y, fp.GetOrientationDegrees(), rp.x, rp.y,
                                     r.GetTextAngleDegrees(), r.GetTextSize().x, r.GetTextThickness())
    return out


def unconnected(b):
    b.BuildConnectivity()
    try:
        return b.GetConnectivity().GetUnconnectedCount(False)
    except Exception:
        return 0


def drc(b, kinds=("clearance",)):
    """KiCad's own DRC in a fresh process (repeated runs in one process stop reporting).
    Returns a list of (kind, [item descriptions])."""
    d = tempfile.mkdtemp()
    fn = os.path.join(d, "t.kicad_pcb")
    pcbnew.SaveBoard(fn, b)
    rpt = os.path.join(d, "drc.rpt")
    subprocess.run([sys.executable, "-c",
                    "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "u=getattr(pcbnew, 'EDA_UNITS_MILLIMETRES', None) or pcbnew.EDA_UNITS_MM; "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], u, True)",
                    fn, rpt], check=True, capture_output=True)
    out, cur = [], None
    for line in open(rpt, encoding="utf-8"):
        if line.startswith("["):
            k = line[1:line.index("]")]
            cur = [k, []] if k in kinds else None
            if cur:
                out.append(cur)
        elif cur is not None and line.strip().startswith("@("):
            cur[1].append(line.strip())
    return out


def report(name):
    print("%s FAILURES: %d" % (name, len(FAILS)))
    return 1 if FAILS else 0


# ---------------------------------------------------------------- GUI driving

def gui_harness(dialog_cls):
    """Replace pcbnew.GetBoard / Refresh and wx.MessageBox; returns helpers."""
    import wx
    app = wx.App(False)
    boxes = []
    wx.MessageBox = lambda *a, **k: boxes.append(a[0])
    refreshes = [0]
    pcbnew.Refresh = lambda: refreshes.__setitem__(0, refreshes[0] + 1)

    def find():
        for w in wx.GetTopLevelWindows():
            if isinstance(w, dialog_cls) and w.IsShown():
                return w
        return None

    def settle(d):
        if d._timer is not None:
            d._timer.Stop()
        d.refresh()

    def shot(win, path):
        if not path:
            return
        import time
        win.Layout()
        win.Refresh()
        for _ in range(10):
            win.Update()
            wx.GetApp().Yield(True)
            time.sleep(0.03)
        r = win.GetScreenRect()
        subprocess.run(["import", "-window", "root", "-crop",
                        "%dx%d+%d+%d" % (r.width, r.height, r.x, r.y), path], check=False)

    def run(plugin, board, steps):
        pcbnew.GetBoard = lambda: board
        steps = list(steps)

        def tick():
            d = find()
            if d is None:
                wx.CallLater(50, tick)
                return
            try:
                steps.pop(0)(d)
            except Exception as e:
                import traceback
                traceback.print_exc()
                FAILS.append("step raised %r" % e)
                d.finish(False)
                return
            if steps:
                wx.CallLater(30, tick)
        wx.CallLater(100, tick)
        plugin.Run()

    return dict(app=app, boxes=boxes, refreshes=refreshes, settle=settle, shot=shot, run=run)
