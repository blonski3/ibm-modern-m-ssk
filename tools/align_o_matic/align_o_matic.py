# align-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Align pads, footprints and vias to a master: select the master (a pad, a footprint or
# a via) and press Master, then select the slaves and press Align. They move onto a line
# through the master - same X, same Y or a 45° diagonal, so only one coordinate changes -
# or onto the master itself. The window stays open for as many actions as needed; the
# last one follows the settings live, Undo takes actions back one by one. OK keeps all,
# Cancel restores everything. One undo step (Ctrl+Z) for the whole session.

import os

import pcbnew
import wx

from . import geo
from . import geometry as g
from . import kc
from .dialog import AlignDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))


def body_centre(fp):
    """Centre of the courtyard box, or of the pads + graphics box when there is none."""
    try:
        try:
            fp.BuildCourtyardCaches()
        except Exception:
            pass
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        pts = []
        for i in range(poly.OutlineCount()):
            ol = poly.Outline(i)
            pts += [kc.xy(ol.CPoint(k)) for k in range(ol.PointCount())]
        if len(pts) >= 3:
            return g.centre(pts)
    except Exception:
        pass
    pts = []
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        pts += [kc.xy(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop())), kc.xy(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))]
    return g.centre(pts) if pts else kc.xy(fp.GetPosition())


class Mover:
    """Something that moves as one: a footprint (by its selected pads, or as a whole by
    the reference point) or a via."""

    def __init__(self, item, pads=None):
        self.item = item
        self.pads = pads
        self.via = item.GetClass() == "PCB_VIA"

    def key(self):
        return kc.uuid(self.item)

    def name(self):
        if self.via:
            return "via %s" % (self.item.GetNetname() or "")
        ref = self.item.GetReference()
        if self.pads:
            return "%s pad %s" % (ref, ",".join(p.GetNumber() for p in self.pads))
        return ref

    def point(self, refpt):
        if self.via:
            return kc.xy(self.item.GetPosition())
        if self.pads:
            return g.centre([kc.xy(p.GetPosition()) for p in self.pads])
        if refpt == g.REF_PADS:
            pts = [kc.xy(p.GetPosition()) for p in self.item.Pads()]
            if pts:
                return g.centre(pts)
        elif refpt == g.REF_BODY:
            return body_centre(self.item)
        return kc.xy(self.item.GetPosition())

    def locked(self):
        try:
            return self.item.IsLocked()
        except Exception:
            return False


def read_selection(board):
    """-> (movers, number of other selected items). A selected footprint counts as a
    whole (KiCad marks its pads selected too); otherwise its selected pads."""
    movers, other = [], 0
    for fp in board.GetFootprints():
        if fp.IsSelected():
            movers.append(Mover(fp))
            continue
        pads = [p for p in fp.Pads() if p.IsSelected()]
        if pads:
            movers.append(Mover(fp, pads))
    for t in board.GetTracks():
        if t.IsSelected():
            if t.GetClass() == "PCB_VIA":
                movers.append(Mover(t))
            else:
                other += 1
    for d in board.GetDrawings():
        try:
            if d.IsSelected():
                other += 1
        except Exception:
            pass
    return movers, other


class Action:
    def __init__(self, board, movers, other):
        self.edits = kc.Edits(board)
        self.movers = movers
        self.other = other
        self.moved = 0
        self.dmax = 0.0


class Model:
    def __init__(self, board):
        self.board = board
        self.master = None
        self.stack = []             # done actions, the last one is live
        self.live = None

    # ---------------------------------------------------------- master
    def set_master(self):
        """The one selected pad / footprint / via becomes the master. -> message or None."""
        movers, _other = read_selection(self.board)
        if len(movers) != 1 or (movers[0].pads and len(movers[0].pads) != 1):
            return "Select exactly one pad, footprint or via for the master (now %d)" % (
                sum(len(m.pads) if m.pads else 1 for m in movers))
        self.commit()
        self.master = movers[0]
        return None

    def master_point(self, v):
        return self.master.point(v["refpt"]) if self.master else None

    def master_text(self, v):
        if not self.master:
            return "- (select one, press ⌖)"
        p = self.master_point(v)
        return "%s · %.3f, %.3f" % (self.master.name(), p[0], p[1])

    # ---------------------------------------------------------- actions
    def commit(self):
        """The live action stays as it is; the next change starts a new one."""
        self.live = None

    def align(self, v):
        movers, other = read_selection(self.board)
        self.commit()
        a = Action(self.board, movers, other)
        self.stack.append(a)
        self.live = a
        return self.apply(v)

    def undo(self):
        if not self.stack:
            return False
        a = self.stack.pop()
        a.edits.restore()
        self.live = None
        return True

    def restore_all(self):
        while self.stack:
            self.stack.pop().edits.restore()
        self.live = None

    def ends_index(self):
        """(layer, key) -> [(track, at_start)] of all straight tracks."""
        idx = {}
        for t in self.board.GetTracks():
            if t.GetClass() != "PCB_TRACK":
                continue
            for st, q in ((True, t.GetStart()), (False, t.GetEnd())):
                idx.setdefault((t.GetLayer(), geo.key(kc.xy(q))), []).append((t, st))
        return idx

    def apply(self, v):
        """Redo the live action with the settings v. -> Issues."""
        iss = geo.Issues(g.TEXT, ("", ""))
        a = self.live
        if a is None:
            return iss
        a.edits.restore()
        a.moved, a.dmax = 0, 0.0
        m = self.master_point(v)
        if m is None:
            return iss
        if not a.movers:
            iss.add("nothing")
        if a.other:
            iss.add("other", None, a.other)
        idx = self.ends_index() if v.get("drag") else None
        mkey = self.master.key()
        cu = [L for L in range(pcbnew.PCB_LAYER_ID_COUNT) if pcbnew.IsCopperLayer(L)] if idx else []
        for mv in a.movers:
            if mv.key() == mkey:
                iss.add("master", mv.name())
                continue
            if mv.locked():
                iss.add("locked", mv.name())
                continue
            p = mv.point(v["refpt"])
            d = g.delta(p, m, v["axis"], v["move"], v["dx"], v["dy"])
            if abs(d[0]) < 1e-7 and abs(d[1]) < 1e-7:
                continue
            di = (int(round(d[0] * kc.IU)), int(round(d[1] * kc.IU)))
            ends = []
            if idx is not None:
                pts = [(mv.item.GetPosition(), mv.item, mv.item.GetNetCode())] if mv.via else \
                      [(pd.GetPosition(), pd, pd.GetNetCode()) for pd in mv.item.Pads()]
                for q, it, net in pts:
                    k = geo.key(kc.xy(q))
                    for L in cu:
                        if not it.IsOnLayer(L):
                            continue
                        for t, st in idx.get((L, k), ()):
                            if t.GetNetCode() == net:
                                ends.append((t, st))
            a.edits.save(mv.item)
            pos = mv.item.GetPosition()
            mv.item.SetPosition(pcbnew.VECTOR2I(pos.x + di[0], pos.y + di[1]))
            for t, st in ends:
                a.edits.save(t)
                q = t.GetStart() if st else t.GetEnd()
                q = pcbnew.VECTOR2I(q.x + di[0], q.y + di[1])
                if st:
                    t.SetStart(q)
                else:
                    t.SetEnd(q)
            a.moved += 1
            a.dmax = max(a.dmax, geo.length(d))
        return iss

    def done_text(self):
        n = len(self.stack)
        items = sum(a.moved for a in self.stack)
        return "%d action%s, %d moved" % (n, "" if n == 1 else "s", items)

    def last_text(self):
        if not self.stack:
            return "-"
        a = self.stack[-1]
        return "%d moved, ≤ %.3f mm" % (a.moved, a.dmax) + ("" if a is self.live else " (kept)")


_running = [False]


class AlignOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Placement"
        self.description = "Align pads, footprints and vias to a master pad: same X, same Y or 45°, many times in one go"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "align_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "align_o_matic_dark.png")

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
        first = None
        movers, _o = read_selection(board)
        if len(movers) == 1 and not (movers[0].pads and len(movers[0].pads) > 1):
            model.set_master()
        elif movers:
            first = "Several items selected: select the master alone and press ⌖ Master"
        state = dict(msg=first)

        def apply(v):
            iss = model.apply(v)
            kc.refresh()
            warnings = iss.text()
            if state["msg"]:
                info = state["msg"]
            elif model.master is None:
                info = "Select one item, press ⌖ Master"
            elif model.live is not None:
                info = "Aligned %d. Select the next, ⇥ Align" % model.live.moved
            else:
                info = "Select the items, press ⇥ Align"
            return dict(info=info, warnings=warnings,
                        ro=dict(master=model.master_text(v), last=model.last_text(), done=model.done_text()))

        def act(name, v):
            state["msg"] = None
            if name == "master":
                state["msg"] = model.set_master()
            elif name == "align":
                if model.master is None:
                    state["msg"] = "Set the master first (select it alone, press ⌖ Master)"
                else:
                    model.align(v)
            elif name == "undo":
                if not model.undo():
                    state["msg"] = "Nothing to undo"

        dlg = AlignDialog(kc.pcb_frame(), HERE, "Pads, footprints and vias → a line through the master",
                          apply, None, {})
        dlg.act_cb = act
        wx.CallAfter(dlg.refresh)
        ok = dlg.run()
        try:
            v = dlg.values()
        except ValueError:
            v = None
        dlg.Destroy()
        if ok and v is not None:
            model.apply(v)
            kc.write_log(board, "align_o_matic.log",
                         ", ".join("%s=%s" % (k, v.get(k)) for k in sorted(v) if k not in ("nudge", "more")),
                         [model.done_text()])
        else:
            model.restore_all()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        # no Refresh here: KiCad rebuilds the view and the connectivity itself right after
        # Run() returns (RebuildAndRefresh), a second full rebuild only costs time
