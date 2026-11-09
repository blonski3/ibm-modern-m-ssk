# Dialog of place-o-matic (no pcbnew import, runs without KiCad).

import math

import wx

from . import geometry as g
from . import w95

NAME = "place-o-matic"
VERSION = "1.0"

MODES = [("Row", g.ROW), ("Column", g.COLUMN), ("Grid", g.GRID), ("Circle", g.CIRCLE)]
SPACINGS = [("Pitch", g.PITCH), ("Gap", g.GAP)]
KEEPS = [("Keep first", g.KEEP_FIRST), ("Keep centre", g.KEEP_CENTER)]
ROTS = [("Keep ∠", g.ROT_KEEP), ("Set ∠", g.ROT_SET), ("Follow", g.ROT_FOLLOW)]
ORDERS = [("Reference", g.ORDER_REF), ("Position", g.ORDER_POS), ("Value", g.ORDER_VALUE)]
REFPTS = ["Origin", "Pads centre", "Body centre"]


def mode_bitmap(kind, colour):
    def draw(gc, size):
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour))
        if kind == g.ROW:
            for x in (1, 6, 11):
                gc.DrawRectangle(x, 5, 4, 6)
        elif kind == g.COLUMN:
            for y in (1, 6, 11):
                gc.DrawRectangle(5, y, 6, 4)
        elif kind == g.GRID:
            for x in (2, 9):
                for y in (2, 9):
                    gc.DrawRectangle(x, y, 5, 5)
        else:
            for k in range(6):
                a = k * math.pi / 3
                gc.DrawEllipse(8 + 5.5 * math.cos(a) - 2, 8 + 5.5 * math.sin(a) - 2, 4, 4)
    return w95.icon_bitmap(draw)


class Sketch(w95.Sketch):
    W, H = 290, 196

    def part(self, p, x, y, ang=0.0, hl=False, label=None):
        """A small 2-pad footprint (body + pads) centred at x, y, rotated by ang (deg CCW)."""
        gc = p.gc
        gc.PushState()
        gc.Translate(x, y)
        gc.Rotate(-math.radians(ang))
        p.rect(-14, -9, 28, 18, None, outline=w95.COL_HL if hl else p.ext)
        p.rect(-12, -6, 9, 12, w95.COL_CU, r=2)
        p.rect(3, -6, 9, 12, w95.COL_CU, r=2)
        gc.PopState()
        if label:
            p.text(label, x, y - 15, p.silk, p.small)

    def paint(self, p):
        st = self.state
        mode = st.get("mode", g.ROW)
        gap = st.get("spacing") == g.GAP
        rot = st.get("rot", g.ROT_KEEP)
        th = 0.0 if rot == g.ROT_KEEP else 30.0
        if mode == g.ROW:
            xs = [44, 104, 164, 224]
            for k, x in enumerate(xs):
                self.part(p, x, 96, th if rot != g.ROT_KEEP else 0, label="D%d" % (k + 1))
            if gap:
                p.dash(xs[0] + 14, 106, xs[0] + 14, 140)
                p.dash(xs[1] - 14, 106, xs[1] - 14, 140)
                p.arrow(xs[0] + 14, 134, xs[1] - 14, 134, "x", "X", ty=148)
            else:
                p.dash(xs[0], 106, xs[0], 140)
                p.dash(xs[1], 106, xs[1], 140)
                p.arrow(xs[0], 134, xs[1], 134, "x", "X", ty=148)
        elif mode == g.COLUMN:
            ys = [36, 80, 124, 168]
            for k, y in enumerate(ys):
                self.part(p, 120, y, th if rot != g.ROT_KEEP else 0)
                p.text("D%d" % (k + 1), 88, y, p.silk, p.small)
            if gap:
                p.dash(134, ys[0] + 9, 196, ys[0] + 9)
                p.dash(134, ys[1] - 9, 196, ys[1] - 9)
                p.arrow(190, ys[0] + 9, 190, ys[1] - 9, "y", "Y", tx=204)
            else:
                p.dash(134, ys[0], 196, ys[0])
                p.dash(134, ys[1], 196, ys[1])
                p.arrow(190, ys[0], 190, ys[1], "y", "Y", tx=204)
        elif mode == g.GRID:
            xs, ys = [52, 112, 172], [58, 118]
            k = 0
            for r_, y in enumerate(ys):
                cols = xs if not (st.get("snake") and r_ % 2) else xs[::-1]
                for x in cols:
                    k += 1
                    self.part(p, x, y, th if rot != g.ROT_KEEP else 0, label="D%d" % k)
            p.dash(xs[0], 68, xs[0], 156)
            p.dash(xs[1], 68, xs[1], 156)
            p.arrow(xs[0], 150, xs[1], 150, "x", "X", ty=164)
            p.dash(186, ys[0], 240, ys[0])
            p.dash(186, ys[1], 240, ys[1])
            p.arrow(234, ys[0], 234, ys[1], "y", "Y", tx=248)
            p.letter("N", 112, 22, p.col("cols"))
            p.arrow(38, 30, 186, 30, "cols", None)
        else:
            cx, cy, R = 118, 100, 66
            n = 6
            a0 = 0.0
            for k in range(n):
                phi = a0 + (-1 if st.get("cw") else 1) * k * 60
                x = cx + R * math.cos(math.radians(phi))
                y = cy - R * math.sin(math.radians(phi))
                ang = {g.ROT_KEEP: 0.0, g.ROT_SET: 30.0}.get(rot, phi)
                self.part(p, x, y, ang)
                p.text("D%d" % (k + 1), x + 0, y + 16, p.silk, p.small)
            p.circle(cx, cy, 2, p.dim)
            p.dash(cx, cy, cx + R + 30, cy)
            p.arrow(cx, cy, cx + (R - 16) * math.cos(math.radians(120)), cy - (R - 16) * math.sin(math.radians(120)),
                    "radius", "R", heads=1)
            # step angle arc between D1 and D2
            gc = p.gc
            c = p.col("da")
            gc.SetPen(wx.Pen(c, 1))
            path = gc.CreatePath()
            path.AddArc(cx, cy, 34, 0, -math.radians(60), False)
            gc.StrokePath(path)
            p.letter("ΔA", cx + 44, cy - 20, c)
            p.letter("A0", cx + R + 26, cy - 10, p.col("a0"))
        if rot != g.ROT_KEEP:
            p.letter("θ", self.W - 18, 16, p.col("theta"))
        if st.get("keep") == g.KEEP_FIRST:
            p.letter("◆", 14, self.H - 14, p.dim)
            p.text("first stays", 60, self.H - 14, p.off, p.small)


class PlaceDialog(w95.OMatic):
    NAME = NAME
    FILE = "place_o_matic"
    DEFAULTS = dict(mode=0, spacing=0, keep=0, rot=0, x=2.54, y=2.54, cols=4, radius=10.0,
                    a0=0.0, da=0, theta=0.0, dx=0.0, dy=0.0, order=0, reverse=False, refpt=0,
                    axis_angle=0.0, snap=0, snake=False, cw=False, check=True, nudge=3, more=False)
    STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 1.27, 2.54]
    STEP_DEFAULT = 3
    MINIMUM = dict(cols=1, radius=0.0, snap=0.0)
    OPTIONAL = dict(da="auto", snap="off")
    INTEGERS = {"cols"}
    ANGLES = {"a0", "da", "theta", "axis_angle"}
    NOT_REMEMBERED = {"dx", "dy"}
    LAST = {}
    CHECK_TIP = "Check courtyard overlaps (between the placed footprints and with the others) and the board outline"

    def build(self, box):
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.toggles(self, "mode", [mode_bitmap(m[1], self.fg) for m in MODES],
                             [m[0] for m in MODES]), 0, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.choice(self, "spacing", [s[0] for s in SPACINGS],
                            "Pitch = reference point to reference point, Gap = body edge to body edge "
                            "(courtyard, or the footprint outline without texts)"), 0, wx.LEFT, 6)
        top.Add(self.choice(self, "keep", [k[0] for k in KEEPS],
                            "Keep first: the first footprint stays where it is.\n"
                            "Keep centre: the centre of the group stays."), 0, wx.LEFT, 4)
        box.Add(top, 0, wx.ALL, 8)

        self.draw = Sketch(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.field(fgs, "x", "X", "Row pitch / gap [mm]")
        self.field(fgs, "y", "Y", "Column pitch / gap [mm]")
        self.field(fgs, "cols", "N", "Footprints per row (grid)")
        self.field(fgs, "radius", "R", "Circle radius [mm] (to the reference points)")
        self.field(fgs, "a0", "A0", "Angle of the first footprint on the circle [°], 0 = right, CCW")
        self.field(fgs, "da", "ΔA", "Angle step [°], empty = 360 / count")
        rot = self.choice(self, "rot", [r[0] for r in ROTS],
                          "Keep: every footprint keeps its rotation.\nSet: all get θ.\n"
                          "Follow: θ relative to the row direction / the circle (tangential)")
        self.field(fgs, "theta", "θ", "Rotation [°] (Set / Follow)", tail=rot)
        self.field(fgs, "dx", "DX", "Move the whole group [mm], + = right")
        self.field(fgs, "dy", "DY", "Move the whole group [mm], + = down")
        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.readout(fgs, "now", "Now", "Distance between neighbours now along the row / column, "
                                        "smallest – largest [mm]")
        self.readout(fgs, "move", "Move", "Largest move of a footprint [mm]")
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        nud = wx.BoxSizer(wx.HORIZONTAL)
        nud.Add(self.grey(self, "Pitch"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg), "Tighter (− step)", "pitch", -1), 0)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg, out=True), "Wider (+ step)", "pitch", 1),
                0, wx.LEFT, 1)
        nud.Add(self.grey(self, "Move"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)
        for ang, tip, key, sg in ((180, "Left (DX − step)", "dx", -1), (90, "Up (DY − step)", "dy", -1),
                                  (270, "Down (DY + step)", "dy", 1), (0, "Right (DX + step)", "dx", 1)):
            nud.Add(self.nudge_button(self, w95.arrow_bitmap(ang, self.fg), tip, key, sg), 0, wx.RIGHT, 1)
        nud.Add(self.step_choice(self), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        mp = self.more_pane(box)
        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=4)
        grid.Add(wx.StaticText(mp, label="Order"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        h = wx.BoxSizer(wx.HORIZONTAL)
        h.Add(self.choice(mp, "order", [o[0] for o in ORDERS],
                          "Order of the footprints: by reference (R1, R2, … R10), by their position "
                          "now along the row / column, or by value"), 0)
        h.Add(self.checkbox(mp, "reverse", "Reverse", "Reverse the order"), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 4)
        grid.Add(h, 0)
        grid.Add(wx.StaticText(mp, label="Ref. point"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        grid.Add(self.choice(mp, "refpt", REFPTS,
                             "The point of each footprint that sits on the pitch: the footprint origin, "
                             "the centre of its pads or the centre of its body"), 0)
        grid.Add(wx.StaticText(mp, label="Row angle"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.num(mp, "axis_angle", "Direction of the row [°], 0 = right, CCW (rotates the "
                                            "whole layout)"), 0)
        grid.Add(wx.StaticText(mp, label="Snap"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        grid.Add(self.num(mp, "snap", "Put the first footprint (circle: the centre) on this grid [mm]"), 0)
        grid.Add((0, 0))
        grid.Add(self.checkbox(mp, "snake", "Snake", "Grid: every second row runs backwards"), 0)
        grid.Add((0, 0))
        grid.Add(self.checkbox(mp, "cw", "Clockwise", "Circle: go clockwise"), 0)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP | wx.BOTTOM, 4)
        mp.SetSizer(ps)

    def nudge(self, key, sign):
        if key == "pitch":
            mode = MODES[self.tg["mode"][1]][1]
            key = {g.ROW: "x", g.COLUMN: "y", g.GRID: "x", g.CIRCLE: "radius"}[mode]
            if mode == g.GRID:
                super().nudge("y", sign)
        super().nudge(key, sign)

    def on_state(self):
        mode = MODES[self.tg["mode"][1]][1]
        rot = ROTS[self.ch["rot"].GetSelection()][1]
        self.draw.set_state(mode=mode, spacing=SPACINGS[self.ch["spacing"].GetSelection()][1],
                            rot=rot, keep=KEEPS[self.ch["keep"].GetSelection()][1],
                            snake=self.cb["snake"].GetValue(), cw=self.cb["cw"].GetValue())
        circ = mode == g.CIRCLE
        self.show_rows(dict(x=mode in (g.ROW, g.GRID), y=mode in (g.COLUMN, g.GRID), cols=mode == g.GRID,
                            radius=circ, a0=circ, da=circ))
        self.f["theta"].Enable(rot != g.ROT_KEEP)
        self.ch["spacing"].Enable(not circ)
        self.cb["snake"].Enable(mode == g.GRID)
        self.cb["cw"].Enable(circ)

    def on_reselected(self, defaults):
        super().on_reselected(defaults)

    def convert(self, raw):
        if raw["cols"] < 1:
            raise ValueError("N")
        if raw["radius"] < 0:
            raise ValueError("R")
        if raw["snap"] < 0:
            raise ValueError("Snap")
        return dict(raw, mode=MODES[raw["mode"]][1], spacing=SPACINGS[raw["spacing"]][1],
                    keep=KEEPS[raw["keep"]][1], rot=ROTS[raw["rot"]][1], order=ORDERS[raw["order"]][1])
