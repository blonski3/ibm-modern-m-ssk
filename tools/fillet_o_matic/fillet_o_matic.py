# fillet-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Select tracks (straight segments and arcs) and run Tools -> External Plugins ->
# fillet-o-matic. Every corner between selected tracks is rounded with a tangent arc,
# cut with a chamfer, or made sharp again; existing arcs are redone, so the radius of
# rounded tracks can be changed later. Parallel tracks that turn together get concentric
# arcs (spacing kept). Changes go straight to the board; OK keeps them, Cancel restores
# everything. One undo step (Ctrl+Z).

import os

import pcbnew
import wx

from . import geo
from . import geometry as g
from . import kc
from .dialog import FilletDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKS = ("PCB_TRACK", "PCB_ARC")


class Model:
    def __init__(self, board):
        self.board = board
        self.edits = kc.Edits(board)
        self.proj = kc.project_netclasses(board)
        self.pieces = []
        self.byid = {}
        self.prep = None
        self.prep_key = None
        self.static = None
        self.clr = {}

    def selected(self):
        return [t for t in self.board.GetTracks() if t.IsSelected() and t.GetClass() in TRACKS]

    def load(self, items):
        self.edits.restore()
        self.byid, self.pieces = {}, []
        for t in items:
            u = kc.uuid(t)
            self.byid[u] = t
            a, b = kc.xy(t.GetStart()), kc.xy(t.GetEnd())
            if t.GetClass() == "PCB_ARC":
                p = g.Piece(u, "arc", a, b, kc.mm(t.GetWidth()), t.GetLayer(), t.GetNetCode(), kc.xy(t.GetMid()))
            else:
                p = g.Piece(u, "seg", a, b, kc.mm(t.GetWidth()), t.GetLayer(), t.GetNetCode())
            if p.length() >= g.EPS:
                self.pieces.append(p)
        self.blocked = self._blocked()
        self.prep = self.prep_key = self.static = None

    def _blocked(self):
        """(layer, key) of points where two selected tracks meet but something else is
        there too: another track end, a via or a pad."""
        count = {}
        pts = {}
        for p in self.pieces:
            for q in (p.a, p.b):
                k = (p.layer, geo.key(q))
                count[k] = count.get(k, 0) + 1
                pts[k] = q
        cand = {k for k, n in count.items() if n == 2}
        if not cand:
            return set()
        sel = {p.id for p in self.pieces}
        out = set()
        for t in self.board.GetTracks():
            cls = t.GetClass()
            if cls == "PCB_VIA":
                k2 = geo.key(kc.xy(t.GetPosition()))
                for k in cand:
                    if k[1] == k2 and t.IsOnLayer(k[0]):
                        out.add(k)
            elif kc.uuid(t) not in sel:
                for q in (t.GetStart(), t.GetEnd()):
                    k = (t.GetLayer(), geo.key(kc.xy(q)))
                    if k in cand:
                        out.add(k)
        for fp in self.board.GetFootprints():
            bb = fp.GetBoundingBox()
            x0, y0, x1, y1 = kc.mm(bb.GetLeft()), kc.mm(bb.GetTop()), kc.mm(bb.GetRight()), kc.mm(bb.GetBottom())
            inside = [k for k in cand if x0 <= pts[k][0] <= x1 and y0 <= pts[k][1] <= y1 and k not in out]
            if not inside:
                continue
            for pad in fp.Pads():
                for k in inside:
                    if k in out or not pad.IsOnLayer(k[0]):
                        continue
                    try:
                        kind, data = kc.pad_shape(pad, k[0])
                    except Exception:
                        continue
                    if geo.Obstacle(kind, data, 0, k[0]).dist_pt(pts[k]) <= 1e-6:
                        out.add(k)
        return out

    def static_grid(self):
        if self.static is None:
            pts = [q for p in self.pieces for q in (p.a, p.b)]
            if not pts:
                self.static = geo.Grid()
                return self.static
            window = geo.bbox(pts, 3.0)
            layers = sorted({p.layer for p in self.pieces})
            sel = {p.id for p in self.pieces}
            self.static = geo.Grid(kc.collect_copper(self.board, layers, window, skip=sel, edge=True), 1.0)
        return self.static

    def clr_of(self, net):
        if net not in self.clr:
            item = next((self.byid[p.id] for p in self.pieces if p.net == net), None)
            self.clr[net] = kc.netclass(item, self.board, self.proj)["clearance"] if item else 0.2
        return self.clr[net]

    def apply(self, v):
        self.edits.restore()
        if v.get("check"):
            self.static_grid()                  # collected from the untouched board
        if self.prep_key != v["min_angle"]:
            self.prep = g.Prep(self.pieces, self.blocked, v["min_angle"])
            self.prep_key = v["min_angle"]
        res = g.plan(self.prep, v)
        for op in res.ops:
            kind = op[0]
            if kind == "set":
                it = self.byid[op[1]]
                self.edits.save(it)
                it.SetStart(kc.P(op[2]))
                it.SetEnd(kc.P(op[3]))
            elif kind == "del":
                it = self.byid[op[1]]
                if it.IsSelected():
                    it.ClearSelected()
                self.edits.remove(it)
            else:
                like = self.byid[op[-2]]
                if kind == "seg":
                    t = pcbnew.PCB_TRACK(self.board)
                    t.SetStart(kc.P(op[1]))
                    t.SetEnd(kc.P(op[2]))
                else:
                    t = pcbnew.PCB_ARC(self.board)
                    t.SetStart(kc.P(op[1]))
                    t.SetMid(kc.P(op[2]))
                    t.SetEnd(kc.P(op[3]))
                t.SetWidth(kc.iu(op[-1]))
                t.SetLayer(like.GetLayer())
                t.SetNet(like.GetNet())
                self.edits.add(t)
        if v.get("check"):
            g.check(res.final, self.static_grid(), self.clr_of, res.issues, self.prep, res.exact)
        return res


def summary(model):
    n_arc = sum(1 for p in model.pieces if p.kind == "arc")
    nets = len({p.net for p in model.pieces})
    return "%d tracks (%d arcs), %d net%s" % (len(model.pieces), n_arc, nets, "" if nets == 1 else "s")


def guesses(model):
    """Start values: the radius of the selected arcs when there are any, otherwise
    3 × the track width (at least 0.5 mm); chamfer 2 × width (at least 0.3 mm)."""
    radii = sorted(p.info[1] for p in model.pieces if p.kind == "arc" and p.info)
    ws = sorted(p.w for p in model.pieces) or [0.2]
    w = ws[len(ws) // 2]
    out = dict(c=round(max(0.3, 2 * w), 2))
    if radii:
        out["r"] = round(radii[0], 3)
    else:
        out["r"] = round(max(0.5, 3 * w), 2)
    return out


def info_line(res, mode):
    st = res.stats
    if mode == g.SHARP:
        return "%d corners sharp" % st["corners"]
    if not st["corners"]:
        return "no corners in the selection"
    txt = "%d of %d corners" % (st["done"], st["corners"])
    if mode == g.ROUND and st["rmin"] is not None:
        lo, hi = st["rmin"], st["rmax"]
        txt += ", R %.3f" % lo if hi - lo < 5e-4 else ", R %.3f–%.3f" % (lo, hi)
    return txt


_running = [False]


class FilletOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Routing"
        self.description = "Round, chamfer or un-round the corners of the selected tracks (concentric for buses)"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "fillet_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "fillet_o_matic_dark.png")

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
        items = model.selected()
        if not items:
            wx.MessageBox("Select tracks (segments and arcs) whose corners should change.", NAME)
            return
        model.load(items)
        state = dict(key=None, info="", warnings=[])

        def key_of(v):
            return tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("nudge", "more")))

        def apply(v):
            if state["key"] == key_of(v):
                return dict(info=state["info"], warnings=state["warnings"])
            res = model.apply(v)
            warnings = res.issues.text()
            info = info_line(res, v["mode"])
            st = res.stats
            done = "%d" % st["done"]
            if st["reduced"]:
                done += ", %d smaller" % st["reduced"]
            if st["corners"] - st["done"] and v["mode"] != g.SHARP:
                done += ", %d left" % (st["corners"] - st["done"])
            state.update(key=key_of(v), info=info, warnings=warnings)
            kc.refresh()
            return dict(info=info, warnings=warnings,
                        ro=dict(now=g.describe(model.pieces, v["min_angle"]), corners=done))

        def reselect():
            model.edits.restore()
            items = model.selected()
            if not items:
                kc.refresh()
                state["key"] = None
                return ("(nothing selected, kept the previous tracks)\n" + summary(model), None)
            model.load(items)
            state["key"] = None
            return (summary(model), dict(nc=guesses(model)))

        gs = guesses(model)
        defaults = dict(gs, nc=gs)
        dlg = FilletDialog(kc.pcb_frame(), HERE, summary(model), apply, reselect, defaults)
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
            kc.write_log(board, "fillet_o_matic.log",
                         ", ".join("%s=%s" % (k, v.get(k)) for k in sorted(v) if k not in ("nudge", "more")),
                         [state["info"]] + ["! " + w for w in state["warnings"]])
            if state["warnings"]:
                wx.MessageBox("\n".join(state["warnings"]) + "\n\n(also in fillet_o_matic.log next to the board)",
                              NAME + " - problems")
        else:
            model.edits.restore()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        kc.refresh()
