# place-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Select two or more footprints and run Tools -> External Plugins -> place-o-matic.
# The footprints are arranged in a row, a column, a grid or on a circle with an exact
# pitch (reference point to reference point) or gap (body edge to body edge), in the
# order of their references (R1, R2, ... R10), of their position or of their value.
# Every change is applied to the board at once; OK keeps it, Cancel puts everything
# back. One undo step (Ctrl+Z). Tracks are not dragged along (like KiCad's own Move).

import math
import os

import pcbnew
import wx

from . import geo
from . import geometry as g
from . import kc
from .dialog import PlaceDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))


def _bbox_local(fp, pos, ang):
    """Body outline from pads and graphics (no texts), as a box in footprint coordinates."""
    pts = []
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetBottom()),
                     (bb.GetLeft(), bb.GetBottom()), (bb.GetRight(), bb.GetTop())):
            pts.append(g.kr(geo.sub((kc.mm(x), kc.mm(y)), pos), -ang))
    for gi in fp.GraphicalItems():
        cls = gi.GetClass()
        if "TEXT" in cls.upper() or "FIELD" in cls.upper():
            continue
        try:
            bb = gi.GetBoundingBox()
        except Exception:
            continue
        for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetBottom()),
                     (bb.GetLeft(), bb.GetBottom()), (bb.GetRight(), bb.GetTop())):
            pts.append(g.kr(geo.sub((kc.mm(x), kc.mm(y)), pos), -ang))
    if not pts:
        return [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    b = geo.bbox(pts)
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]


def body_local(fp):
    """Courtyard (or pads + graphics box) relative to the origin, at angle 0."""
    pos = kc.xy(fp.GetPosition())
    ang = fp.GetOrientationDegrees()
    try:
        layer = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
        try:
            fp.BuildCourtyardCaches()
        except Exception:
            pass
        poly = fp.GetCourtyard(layer)
        if poly.OutlineCount() == 1:
            ol = poly.Outline(0)
            pts = [kc.xy(ol.CPoint(k)) for k in range(ol.PointCount())]
            if len(pts) >= 3:
                return [g.kr(geo.sub(p, pos), -ang) for p in pts], "courtyard"
        elif poly.OutlineCount() > 1:
            pts = []
            for i in range(poly.OutlineCount()):
                ol = poly.Outline(i)
                pts += [g.kr(geo.sub(kc.xy(ol.CPoint(k)), pos), -ang) for k in range(ol.PointCount())]
            b = geo.bbox(pts)
            return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])], "courtyard"
    except Exception:
        pass
    return _bbox_local(fp, pos, ang), "box"


def pads_center_local(fp):
    pos = kc.xy(fp.GetPosition())
    ang = fp.GetOrientationDegrees()
    pts = [kc.xy(p.GetPosition()) for p in fp.Pads()]
    if not pts:
        return (0.0, 0.0)
    b = geo.bbox(pts)
    return g.kr(geo.sub(((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0), pos), -ang)


class Model:
    def __init__(self, board):
        self.board = board
        self.edits = kc.Edits(board)
        self.fps = []
        self.items = []
        self.others = None

    def selected(self):
        return [fp for fp in self.board.GetFootprints() if fp.IsSelected()]

    def load(self, fps):
        self.edits.restore()
        self.fps = list(fps)
        self.items, self.byid, self.kinds = [], {}, set()
        for fp in self.fps:
            local, kind = body_local(fp)
            self.kinds.add(kind)
            it = g.Item(kc.uuid(fp), fp.GetReference(), fp.GetValue(), kc.xy(fp.GetPosition()),
                        fp.GetOrientationDegrees(), local)
            it.pads_c = pads_center_local(fp)
            b = geo.bbox(local)
            it.body_c = ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
            self.items.append(it)
            self.byid[it.id] = fp
        self.others = None
        self.outline_bb = None
        segs = kc.board_outline(self.board)
        if segs:
            self.outline_bb = geo.bbox([p for s in segs for p in s])

    def other_bodies(self):
        if self.others is None:
            sel = set(self.byid)
            self.others = []
            for fp in self.board.GetFootprints():
                u = kc.uuid(fp)
                if u in sel:
                    continue
                local, _k = body_local(fp)
                pos, ang = kc.xy(fp.GetPosition()), fp.GetOrientationDegrees()
                self.others.append((u, [geo.add(pos, g.kr(q, ang)) for q in local]))
        return self.others

    def set_refpt(self, k):
        for it in self.items:
            it.anchor_local = [(0.0, 0.0), it.pads_c, it.body_c][k]

    def apply(self, v):
        self.edits.restore()
        self.set_refpt(v["refpt"])
        placements, issues = g.plan(self.items, v)
        moved = 0.0
        for it, pos, ang in placements:
            fp = self.byid[it.id]
            self.edits.save(fp)
            if abs((ang - fp.GetOrientationDegrees() + 180) % 360 - 180) > 1e-9:
                fp.SetOrientationDegrees(ang)
            fp.SetPosition(kc.P(pos))
            moved = max(moved, geo.dist(pos, it.pos))
        if v.get("check") and placements:
            g.check(placements, self.other_bodies(), self.outline_bb, issues)
        return placements, issues, moved


def summary(model):
    refs = sorted((it.ref for it in model.items), key=geo.natural_key)
    txt = ", ".join(refs[:8]) + (" …" if len(refs) > 8 else "")
    kinds = " (courtyard)" if model.kinds == {"courtyard"} else (" (no courtyard: pads + graphics box)"
                                                                  if model.kinds == {"box"} else "")
    return "%d footprints: %s%s" % (len(refs), txt, kinds)


def measured(model, v):
    ax = g.kr((1.0, 0.0), v.get("axis_angle", 0.0))
    if v["mode"] == g.COLUMN:
        ax = g.kr((0.0, 1.0), v.get("axis_angle", 0.0))
    model.set_refpt(v["refpt"])
    d = g.measure(model.items, ax)
    if not d:
        return "–"
    lo, hi = min(d), max(d)
    return ("%.3f mm" % lo) if hi - lo < 5e-4 else ("%.3f–%.3f mm" % (lo, hi))


def guesses(model):
    """Start values from the board: when the footprints already stand roughly in a row
    (column), its median pitch; otherwise the largest body + 0.5 mm. Circle: a radius
    that fits all the bodies with 0.5 mm between them."""
    model.set_refpt(0)
    up = lambda x, st=0.05: math.ceil(x / st - 1e-9) * st
    out = {}
    pts = [it.anchor() for it in model.items]
    for key, ax, other in (("x", (1.0, 0.0), (0.0, 1.0)), ("y", (0.0, 1.0), (1.0, 0.0))):
        size = max(e[1] - e[0] for e in (it.extent(it.angle, ax) for it in model.items))
        across = max(e[1] - e[0] for e in (it.extent(it.angle, other) for it in model.items))
        spread = max(geo.dot(p, other) for p in pts) - min(geo.dot(p, other) for p in pts)
        d = [x for x in g.measure(model.items, ax) if x > 0.05]
        if d and spread <= across:
            out[key] = round(sorted(d)[len(d) // 2], 3)
        else:
            out[key] = round(up(size + 0.5), 3)
    big = max(max(e[1] - e[0] for e in (it.extent(it.angle, ax) for it in model.items))
              for ax in ((1.0, 0.0), (0.0, 1.0)))
    out["radius"] = round(max(1.0, up(len(model.items) * (big + 0.5) / (2 * math.pi), 0.5)), 2)
    return out


_running = [False]


class PlaceOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Placement"
        self.description = "Arrange the selected footprints in a row, column, grid or circle with an exact pitch or gap"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "place_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "place_o_matic_dark.png")

    def Run(self):
        if _running[0]:
            wx.MessageBox(NAME + " is already open.", NAME)
            return
        _running[0] = True
        try:
            self._run()
        finally:
            _running[0] = False

    def _run(self):
        board = pcbnew.GetBoard()
        model = Model(board)
        fps = model.selected()
        if len(fps) < 2:
            wx.MessageBox("Select two or more footprints.", NAME)
            return
        model.load(fps)
        state = dict(key=None, info="", warnings=[])

        def key_of(v):
            return tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("nudge", "more")))

        def apply(v):
            if state["key"] == key_of(v):
                return dict(info=state["info"], warnings=state["warnings"])
            placements, issues, moved = model.apply(v)
            warnings = issues.text()
            n = len(placements)
            info = "%d placed, moved ≤ %.3f mm" % (n, moved)
            state.update(key=key_of(v), info=info, warnings=warnings)
            kc.refresh()
            return dict(info=info, warnings=warnings,
                        ro=dict(now=measured(model, v), move="%.3f mm" % moved))

        def reselect():
            model.edits.restore()
            fps = model.selected()
            if len(fps) < 2:
                kc.refresh()
                state["key"] = None
                return ("(select two or more footprints, kept the previous selection)\n" + summary(model), None)
            model.load(fps)
            state["key"] = None
            return (summary(model), dict(nc=guesses(model)))

        gs = guesses(model)
        defaults = dict(gs, nc=gs)          # used only for values not remembered from last time
        dlg = PlaceDialog(kc.pcb_frame(), HERE, summary(model), apply, reselect, defaults)
        wx.CallAfter(dlg.refresh)
        ok = dlg.run()
        try:
            v = dlg.values()
        except ValueError:
            v = None
        dlg.Destroy()
        if ok and v is not None:
            if state["key"] != key_of(v):
                apply(v)
            kc.write_log(board, "place_o_matic.log",
                         ", ".join("%s=%s" % (k, v.get(k)) for k in sorted(v) if k not in ("nudge", "more")),
                         [state["info"]] + ["! " + w for w in state["warnings"]])
            if state["warnings"]:
                wx.MessageBox("\n".join(state["warnings"]) + "\n\n(also in place_o_matic.log next to the board)",
                              NAME + " - problems")
        else:
            model.edits.restore()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        kc.refresh()

