# bus-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Select several parallel tracks that end in the open (their last segments are enough)
# and run Tools -> External Plugins -> bus-o-matic. They are continued together along one
# path - straight, a 45° / 90° bend, a jog or a U-turn - at a constant pitch, with a 45°
# fan first when the pitch changes; corners sharp or cut at 45° with the spacing kept.
# Changes go straight to the board; OK keeps them, Cancel restores everything.
# One undo step (Ctrl+Z).

import os

import pcbnew
import wx

from . import geo
from . import geometry as g
from . import kc
from .dialog import BusDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKS = ("PCB_TRACK", "PCB_ARC")


def end_dir(t, at_start):
    """Direction out of the track at its start (at_start) or at its end."""
    a, b = kc.xy(t.GetStart()), kc.xy(t.GetEnd())
    if t.GetClass() == "PCB_ARC":
        m = kc.xy(t.GetMid())
        c = geo.circle_center(a, m, b)
        if c is not None:
            p = a if at_start else b
            r = geo.sub(p, c)
            d = geo.unit((-r[1], r[0]))
            if geo.dot(d, geo.sub(p, m)) < 0:
                d = geo.mul(d, -1.0)
            return d
    return geo.unit(geo.sub(a, b) if at_start else geo.sub(b, a))


def chains(items):
    """Selected tracks joined at shared ends -> [(ids, [(layer, point, track, at_start)])]
    with the ends of each chain (points used once inside the selection)."""
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    at = {}
    for t in items:
        u = kc.uuid(t)
        parent[u] = u
        for st, p in ((True, t.GetStart()), (False, t.GetEnd())):
            q = kc.xy(p)
            at.setdefault((t.GetLayer(), geo.key(q)), []).append((u, t, st, q))
    for lst in at.values():
        for e in lst[1:]:
            parent[find(e[0])] = find(lst[0][0])
    groups = {}
    for t in items:
        groups.setdefault(find(kc.uuid(t)), []).append(kc.uuid(t))
    ends = {}
    for (layer, _k), lst in at.items():
        if len(lst) == 1:
            u, t, st, q = lst[0]
            ends.setdefault(find(u), []).append((layer, q, t, st))
    return [(set(ids), ends.get(root, [])) for root, ids in groups.items()]


class Model:
    def __init__(self, board):
        self.board = board
        self.edits = kc.Edits(board)
        self.proj = kc.project_netclasses(board)
        self.static = None
        self.clr = {}
        self.lanes = []
        self.byid = {}
        self.flip = None

    def selected(self):
        return [t for t in self.board.GetTracks() if t.IsSelected() and t.GetClass() in TRACKS]

    def load(self, items):
        self.edits.restore()
        self.items = items
        self.byid = {kc.uuid(t): t for t in items}
        self.static = None
        self.chains = chains(items)
        self.busy = self.occupied([(e[0], e[1]) for _ids, ends in self.chains for e in ends])
        self.flip = None
        self.make_lanes(False)

    def occupied(self, cands):
        """(layer, key) of the candidate ends where another track, a via or a pad is."""
        cand = {(L, geo.key(p)): p for L, p in cands}
        out = set()
        if not cand:
            return out
        sel = set(self.byid)
        for t in self.board.GetTracks():
            if t.GetClass() == "PCB_VIA":
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
            inside = [k for k, p in cand.items() if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
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
                    if geo.Obstacle(kind, data, 0, k[0]).dist_pt(cand[k]) <= 1e-6:
                        out.add(k)
        return out

    def make_lanes(self, flip):
        """One lane per chain: its open end (or, with flip / when both are open, the end
        that points the other way than the rest)."""
        if self.flip == flip:
            return
        self.flip = flip
        self.connected = []
        picks = []
        for ids, ends in self.chains:
            if not ends:
                continue                                      # a closed loop
            free = [e for e in ends if (e[0], geo.key(e[1])) not in self.busy]
            if not free:
                self.connected.append(ends[0][2])
            picks.append((ids, free or ends))
        fixed = [c[0] for _ids, c in picks if len(c) == 1]
        ref = None
        if fixed:
            ref = geo.unit((sum(end_dir(e[2], e[3])[0] for e in fixed),
                            sum(end_dir(e[2], e[3])[1] for e in fixed)))
        lanes = []
        for ids, cands in picks:
            if len(cands) > 1:
                if ref is None or ref == (0.0, 0.0):
                    ref = end_dir(cands[0][2], cands[0][3])
                cands = sorted(cands, key=lambda e: -geo.dot(end_dir(e[2], e[3]), ref))
                e = cands[-1] if flip else cands[0]
            else:
                e = cands[0]
            layer, q, t, st = e
            nm = t.GetNetname() or "#%d" % (len(lanes) + 1)
            ln = g.Lane(q, end_dir(t, st), kc.mm(t.GetWidth()), layer, t.GetNetCode() or -1, nm, ids, kc.uuid(t))
            ln.at_start = st
            lanes.append(ln)
        self.lanes = lanes

    def static_grid(self):
        if self.static is None:
            layers = sorted({ln.layer for ln in self.lanes}) or [pcbnew.F_Cu]
            self.static = geo.Grid(kc.collect_copper(self.board, layers, None, edge=True), 1.0)
        return self.static

    def clr_of(self, ln):
        if ln.net not in self.clr:
            self.clr[ln.net] = kc.netclass(self.byid[ln.seg], self.board, self.proj)["clearance"]
        return self.clr[ln.net]

    def apply(self, v):
        self.edits.restore()
        if v.get("check"):
            self.static_grid()                      # collected from the untouched board
        self.make_lanes(v.get("flip", False))
        plan = g.plan(self.lanes, v)
        W = v.get("w")
        for ln, verts in zip(plan.lanes, plan.paths):
            if len(verts) < 2:
                continue
            w = W or ln.w
            last = self.byid[ln.seg]
            segs = list(zip(verts, verts[1:]))
            a, b = segs[0]
            if (last.GetClass() == "PCB_TRACK" and abs(kc.mm(last.GetWidth()) - w) < 1e-6 and
                    geo.dot(geo.unit(geo.sub(b, a)), ln.out) > 1 - 1e-9):
                self.edits.save(last)                     # straight on: make the last piece longer
                if ln.at_start:
                    last.SetStart(kc.P(b))
                else:
                    last.SetEnd(kc.P(b))
                segs = segs[1:]
            for a, b in segs:
                t = pcbnew.PCB_TRACK(self.board)
                t.SetStart(kc.P(a))
                t.SetEnd(kc.P(b))
                t.SetWidth(kc.iu(w))
                t.SetLayer(ln.layer)
                t.SetNet(last.GetNet())
                self.edits.add(t)
        for t in self.connected:
            plan.issues.add("connected", t.GetNetname() or None)
        if v.get("check"):
            g.check(plan, self.static_grid(), self.clr_of, plan.issues, lambda ln: W or ln.w)
        return plan


def summary(model):
    nets = len({ln.net for ln in model.lanes})
    return "%d tracks to continue (%d net%s), %d selected pieces" % (
        len(model.lanes), nets, "" if nets == 1 else "s", len(model.items))


def guesses(model):
    gaps = []
    if len(model.lanes) > 1:
        d0, _ = g.frame(model.lanes)
        os_ = sorted(geo.dot(ln.end, g.left(d0)) for ln in model.lanes)
        gaps = g.pitch_of(os_)
    ws = sorted(ln.w for ln in model.lanes) or [0.2]
    return dict(pitch=round(gaps[0], 4) if gaps else 0.5, w=round(ws[len(ws) // 2], 4))


def done_text(plan):
    add = plan.stats.get("added") or []
    if not add:
        return "-"
    lo, hi = min(add), max(add)
    return "+%.2f mm" % lo if hi - lo < 5e-3 else "+%.2f–%.2f mm" % (lo, hi)


_running = [False]


class BusOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Routing"
        self.description = "Continue several parallel tracks together: straight, bend, jog or U-turn at one pitch"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "bus_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "bus_o_matic_dark.png")

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
            wx.MessageBox("Select the tracks to continue (their last segments are enough); "
                          "they should end in the open.", NAME)
            return
        model.load(items)
        if not model.lanes:
            wx.MessageBox("The selected tracks have no ends to continue (closed loops).", NAME)
            return
        state = dict(key=None, info="", warnings=[])

        def key_of(v):
            return tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("nudge", "more")))

        def apply(v):
            if state["key"] == key_of(v):
                return dict(info=state["info"], warnings=state["warnings"])
            plan = model.apply(v)
            warnings = plan.issues.text()
            info = "%d tracks %s" % (len(plan.lanes), done_text(plan))
            state.update(key=key_of(v), info=info, warnings=warnings)
            kc.refresh()
            return dict(info=info, warnings=warnings,
                        ro=dict(now=g.describe(model.lanes), done=done_text(plan)))

        def reselect():
            model.edits.restore()
            items = model.selected()
            state["key"] = None
            if not items:
                kc.refresh()
                return ("(nothing selected, kept the previous tracks)\n" + summary(model), None)
            model.load(items)
            return (summary(model), dict(nc=guesses(model)))

        gs = guesses(model)
        dlg = BusDialog(kc.pcb_frame(), HERE, summary(model), apply, reselect, dict(nc=gs))
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
            kc.write_log(board, "bus_o_matic.log",
                         ", ".join("%s=%s" % (k, v.get(k)) for k in sorted(v) if k not in ("nudge", "more")),
                         [state["info"]] + ["! " + w for w in state["warnings"]])
        else:
            model.edits.restore()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        kc.refresh()
