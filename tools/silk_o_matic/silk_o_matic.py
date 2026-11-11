# silk-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Select footprints and run Tools -> External Plugins -> silk-o-matic. Their reference
# (or value) texts go above, below, left, right or on the centre of the part, at a gap
# from its courtyard, all with one size and a readable angle; Auto tries the sides in
# turn and takes the first one free of pads, other silkscreen and the board edge.
# Changes go straight to the board; OK keeps them, Cancel restores everything.
# One undo step (Ctrl+Z).

import os

import pcbnew
import wx

from . import geo
from . import geometry as g
from . import kc
from .dialog import SilkDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))
REF, VALUE = 0, 1


def is_text(item):
    return hasattr(item, "GetText") and not hasattr(item, "GetShape")


def draw_angle(t):
    a = t.GetDrawRotation()
    try:
        return float(a.AsDegrees())
    except AttributeError:
        return float(a)


def set_abs_angle(t, fp, A):
    """Text angle as seen on the board (KiCad 7 stores it relative to the footprint)."""
    t.SetTextAngleDegrees(A)
    d = draw_angle(t)
    if abs(((d - A) + 90.0) % 180.0 - 90.0) > 0.01:
        t.SetTextAngleDegrees(A - fp.GetOrientationDegrees())


def bbox_mm(bb):
    return (kc.mm(bb.GetLeft()), kc.mm(bb.GetTop()), kc.mm(bb.GetRight()), kc.mm(bb.GetBottom()))


def body_box(fp):
    """Courtyard bounding box, or pads + graphics (no texts) when there is none."""
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
            return geo.bbox(pts), "courtyard"
    except Exception:
        pass
    boxes = [bbox_mm(p.GetBoundingBox()) for p in fp.Pads()]
    for gi in fp.GraphicalItems():
        if not is_text(gi):
            try:
                boxes.append(bbox_mm(gi.GetBoundingBox()))
            except Exception:
                pass
    if not boxes:
        c = kc.xy(fp.GetPosition())
        return (c[0] - 0.5, c[1] - 0.5, c[0] + 0.5, c[1] + 0.5), "box"
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
            max(b[3] for b in boxes)), "box"


def ink_box(t):
    """Box of the drawn strokes (tighter than GetBoundingBox, which has line spacing)."""
    try:
        bb = t.GetEffectiveTextShape().BBox()
        x, y = kc.mm(bb.GetX()), kc.mm(bb.GetY())
        if bb.GetWidth() > 0 and bb.GetHeight() > 0:
            return (x, y, x + kc.mm(bb.GetWidth()), y + kc.mm(bb.GetHeight()))
    except Exception:
        pass
    return bbox_mm(t.GetBoundingBox())


def text_poly(t):
    b = ink_box(t)
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]


class Model:
    def __init__(self, board):
        self.board = board
        self.edits = kc.Edits(board)
        self.worlds = {}
        self.fps = []

    def selected(self):
        return [fp for fp in self.board.GetFootprints() if fp.IsSelected()]

    def load(self, fps):
        self.edits.restore()
        self.fps = sorted(fps, key=lambda fp: geo.natural_key(fp.GetReference()))
        self.ids = {kc.uuid(fp) for fp in self.fps}
        self.bodies = {kc.uuid(fp): body_box(fp) for fp in self.fps}
        self.outlines = geo.outline_polys(kc.board_outline(self.board))
        self.worlds = {}

    @staticmethod
    def target(fp, which):
        return fp.Value() if which == VALUE else fp.Reference()

    def world(self, back, silk, which, v):
        """The pads, silk and outline around (collected once per side and target);
        texts on Fab or other layers only keep inside the board."""
        if not silk:
            return g.World((), (), self.outlines, pad_gap=v["pad_gap"], silk_gap=v["silk_gap"])
        key = (back, which)
        if key not in self.worlds:
            self.worlds[key] = self.collect(back, which)
        pads, lines = self.worlds[key]
        return g.World(pads, lines, self.outlines, pad_gap=v["pad_gap"], silk_gap=v["silk_gap"])

    def collect(self, back, which):
        b = self.board
        silk = pcbnew.B_SilkS if back else pcbnew.F_SilkS
        cu = pcbnew.B_Cu if back else pcbnew.F_Cu
        pads, lines = [], []
        mine = {kc.uuid(self.target(fp, which)) for fp in self.fps}
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if pad.IsOnLayer(cu):
                    try:
                        kind, data = kc.pad_shape(pad, cu)
                        pads.append(geo.Obstacle(kind, data, 0, None))
                    except Exception:
                        pass
            items = list(fp.GraphicalItems()) + [fp.Reference(), fp.Value()]
            for it in items:
                try:
                    if it.GetLayer() != silk:
                        continue
                    if is_text(it):
                        if it.IsVisible() and kc.uuid(it) not in mine:
                            lines.append(geo.Obstacle("poly", text_poly(it), 0, None, id=kc.uuid(it)))
                    else:
                        w = kc.mm(it.GetWidth()) / 2.0
                        for a, c in kc.edge_segments(it):
                            lines.append(geo.Obstacle("seg", (a, c, w), 0, None, id=kc.uuid(fp)))
                except Exception:
                    pass
        for d in b.GetDrawings():
            try:
                if d.GetLayer() != silk:
                    continue
                if is_text(d):
                    lines.append(geo.Obstacle("poly", text_poly(d), 0, None))
                else:
                    w = kc.mm(d.GetWidth()) / 2.0
                    for a, c in kc.edge_segments(d):
                        lines.append(geo.Obstacle("seg", (a, c, w), 0, None))
            except Exception:
                pass
        return pads, lines

    def apply(self, v):
        self.edits.restore()
        iss = g.issues()
        placed, crowded, flagged = 0, 0, set()
        worlds = {}                 # fresh per change: the texts placed now are added to it
        for fp in self.fps:
            t = self.target(fp, v["which"])
            layer = t.GetLayer()
            back = layer in (pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_Cu, pcbnew.B_CrtYd)
            silk = layer in (pcbnew.F_SilkS, pcbnew.B_SilkS)
            self.edits.save(t)
            if v["h"]:
                t.SetTextSize(pcbnew.VECTOR2I(kc.iu(v["h"]), kc.iu(v["h"])))
            if v["t"]:
                t.SetTextThickness(kc.iu(v["t"]))
            elif v["h"]:
                t.SetTextThickness(kc.iu(round(v["h"] * 0.15, 3)))
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
            body, _kind = self.bodies[kc.uuid(fp)]
            A = g.angle_for(v["angle"], body[2] - body[0], body[3] - body[1], draw_angle(t))
            set_abs_angle(t, fp, A)
            ib = ink_box(t)
            tw, th = ib[2] - ib[0], ib[3] - ib[1]
            p0 = kc.xy(t.GetPosition())
            ox, oy = (ib[0] + ib[2]) / 2.0 - p0[0], (ib[1] + ib[3]) / 2.0 - p0[1]
            wkey = (back, silk)
            world = worlds.get(wkey)
            if world is None:
                world = worlds[wkey] = self.world(back, silk, v["which"], v)
            c, _side, hits = g.choose(world, body, tw, th, v["gap"], v["side"])
            t.SetPosition(kc.P((c[0] - ox, c[1] - oy)))     # the strokes centred on c
            if t.IsVisible():
                world.add_text(g.box(c, tw, th), id=kc.uuid(t))
            else:
                iss.add("hidden", fp.GetReference())
            placed += 1
            ref = fp.GetReference()
            if hits:
                flagged.add(ref)
                if v["side"] == g.AUTO:
                    iss.add("crowded", ref, sum(hits.values()))
                    crowded += 1
                for kind, val in hits.items():
                    if v["side"] != g.AUTO:
                        iss.add(kind, ref, val)
        return dict(placed=placed, crowded=crowded, issues=iss, flagged=flagged)


def summary(model):
    refs = [fp.GetReference() for fp in model.fps]
    txt = ", ".join(refs[:8]) + (" …" if len(refs) > 8 else "")
    return "%d footprints: %s" % (len(refs), txt)


def now_text(model, which):
    sizes = set()
    for fp in model.fps:
        t = Model.target(fp, which)
        sizes.add((round(kc.mm(t.GetTextSize().y), 3), round(kc.mm(t.GetTextThickness()), 3)))
    if len(sizes) == 1:
        h, th = sizes.pop()
        return "%g / %g mm" % (h, th)
    return "%d sizes" % len(sizes)


_running = [False]


class SilkOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Silkscreen"
        self.description = "Put the reference texts of the selected footprints above / below / beside them, one size"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "silk_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "silk_o_matic_dark.png")

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
        if not fps:
            wx.MessageBox("Select the footprints whose reference texts should move.", NAME)
            return
        model.load(fps)
        state = dict(key=None, info="", warnings=[])
        now = {}

        def key_of(v):
            return tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("nudge", "more")))

        def apply(v):
            if state["key"] == key_of(v):
                return dict(info=state["info"], warnings=state["warnings"])
            if v["which"] not in now:
                model.edits.restore()
                now[v["which"]] = now_text(model, v["which"])
            r = model.apply(v)
            info = "%d placed" % r["placed"] + (", %d crowded" % r["crowded"] if r["crowded"] else "")
            warnings = r["issues"].text()
            state.update(key=key_of(v), info=info, warnings=warnings)
            kc.refresh()
            return dict(info=info, warnings=warnings, ro=dict(now=now[v["which"]], done=info))

        def reselect():
            model.edits.restore()
            fps = model.selected()
            now.clear()
            state["key"] = None
            if not fps:
                kc.refresh()
                return ("(nothing selected, kept the previous footprints)\n" + summary(model), None)
            model.load(fps)
            return (summary(model), None)

        dlg = SilkDialog(kc.pcb_frame(), HERE, summary(model), apply, reselect, {})
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
            kc.write_log(board, "silk_o_matic.log",
                         ", ".join("%s=%s" % (k, v.get(k)) for k in sorted(v) if k not in ("nudge", "more")),
                         [state["info"]] + ["! " + w for w in state["warnings"]])
        else:
            model.edits.restore()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        # no Refresh here: KiCad rebuilds the view and the connectivity itself right after
        # Run() returns (RebuildAndRefresh), a second full rebuild only costs time
