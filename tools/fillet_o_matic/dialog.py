# Dialog of fillet-o-matic (no pcbnew import, runs without KiCad).

import math

import wx

from . import geometry as g
from . import w95

NAME = "fillet-o-matic"
VERSION = "1.0"

MODES = [("Round: tangent arcs", g.ROUND), ("Chamfer: straight cut", g.CHAMFER),
         ("Sharp: arcs back to sharp corners", g.SHARP)]
BUS = [("Concentric", g.CONCENTRIC), ("Same R", g.SAME)]
UNITS = ["mm", "× W"]
REFS = ["Inner", "Middle", "Outer"]
SHORTS = ["Shrink", "Skip"]


def mode_bitmap(kind, colour):
    def draw(gc, size):
        gc.SetPen(wx.Pen(colour, 3))
        p = gc.CreatePath()
        p.MoveToPoint(2, 14)
        if kind == g.ROUND:
            p.AddLineToPoint(5, 14)
            p.AddArc(5, 5, 9, math.pi / 2, 0, False)
            p.AddLineToPoint(14, 2)
        elif kind == g.CHAMFER:
            p.AddLineToPoint(8, 14)
            p.AddLineToPoint(14, 8)
            p.AddLineToPoint(14, 2)
        else:
            p.AddLineToPoint(14, 14)
            p.AddLineToPoint(14, 2)
        gc.StrokePath(p)
    return w95.icon_bitmap(draw)


class Sketch(w95.Sketch):
    """Three parallel tracks turning up by 90°."""
    W, H = 250, 190
    S = 15            # px between the tracks
    PX, PY = 150, 120  # corner of the inner track
    R0 = 42           # inner radius / setback in px

    def paint(self, p):
        st = self.state
        mode = st.get("mode", g.ROUND)
        same = st.get("bus") == g.SAME
        ref = st.get("ref", g.REF_INNER)
        S, PX, PY, R0 = self.S, self.PX, self.PY, self.R0
        smax = 2 * S
        sref = (0, smax / 2.0, smax)[ref]
        for k in range(3):
            s = k * S
            cx, cy = PX + s, PY + s                    # sharp corner of track k
            pts = []
            if mode == g.SHARP:
                pts = [(12, cy), (cx, cy), (cx, 14)]
                p.path(pts, w95.COL_CU, 6)
                continue
            if mode == g.ROUND:
                R = R0 if same else R0 - sref + s
                ox, oy = cx - R, cy - R                 # arc centre
                gc = p.gc
                gc.SetPen(wx.Pen(w95.COL_CU, 6))
                path = gc.CreatePath()
                path.MoveToPoint(12, cy)
                path.AddLineToPoint(ox, cy)
                path.AddArc(ox, oy, R, math.pi / 2, 0, False)
                path.AddLineToPoint(cx, 14)
                gc.StrokePath(path)
            else:
                f = math.tan(math.pi / 8) / math.cos(math.pi / 4)
                t = R0 if same else R0 + (s - sref) * f
                p.path([(12, cy), (cx - t, cy), (cx, cy - t), (cx, 14)], w95.COL_CU, 6)
        # dimensions
        k = (0, 1, 2)[ref] if not same else 0
        s = k * S
        cx, cy = PX + s, PY + s
        if mode == g.ROUND:
            R = R0 if same else R0 - sref + s
            ox, oy = cx - R, cy - R
            p.circle(ox, oy, 2, p.dim)
            a = math.radians(225 - 180)
            p.arrow(ox, oy, ox + R * math.cos(a) - 3, oy + R * math.sin(a) - 3, "r", None, heads=1)
            p.letter("R", ox + 0.45 * R * math.cos(a) - 8, oy + 0.45 * R * math.sin(a) + 6, p.col("r"))
        elif mode == g.CHAMFER:
            f = math.tan(math.pi / 8) / math.cos(math.pi / 4)
            t = R0 if same else R0 + (s - sref) * f
            y = PY - 14
            p.dash(cx - t, cy - 4, cx - t, y - 4)
            p.dash(cx, cy - 4, cx, y - 4)
            p.arrow(cx - t, y, cx, y, "c", "C", ty=y - 10)
        # spacing marks (kept through the turn when concentric)
        if mode != g.SHARP:
            c = p.dim if not same else p.off
            p.gc.SetPen(wx.Pen(c, 1))
            for k in range(2):
                p.arrow(PX + k * S + 4, 36, PX + (k + 1) * S - 4, 36, None, None)
                ang = math.radians(45)
                ox, oy = PX - R0, PY - R0
                if mode == g.ROUND and not same:
                    r0 = R0 - sref + k * S
                    x0, y0 = ox + (r0 + 4) * math.cos(ang), oy + (r0 + 4) * math.sin(ang)
                    x1, y1 = ox + (r0 + S - 4) * math.cos(ang), oy + (r0 + S - 4) * math.sin(ang)
                    p.arrow(x0, y0, x1, y1, None, None)
            p.text("s", PX + 2 * S + 12, 36, c, p.small)
            if same:
                p.text("spacing grows in the turn", 92, self.H - 12, p.off, p.small)
            else:
                p.text("spacing kept", 70, self.H - 12, p.off, p.small)
        if st.get("unit") == g.UNIT_W and mode != g.SHARP:
            p.letter("× W", 40, 22, p.col(("r", "c")))


class FilletDialog(w95.OMatic):
    NAME = NAME
    FILE = "fillet_o_matic"
    DEFAULTS = dict(mode=0, bus=0, r=1.0, c=0.5, unit=0, ref=0, min_angle=5.0, short=0, check=True,
                    nudge=2, more=False)
    STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
    STEP_DEFAULT = 2
    MINIMUM = dict(r=0.0, c=0.0, min_angle=0.0)
    ANGLES = {"min_angle"}
    LAST = {}
    CHECK_TIP = "Check the clearance of the new arcs / cuts to copper of other nets (netclass clearance)"

    def build(self, box):
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.toggles(self, "mode", [mode_bitmap(m[1], self.fg) for m in MODES],
                             [m[0] for m in MODES]), 0, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.choice(self, "bus", [b[0] for b in BUS],
                            "Concentric: parallel tracks that turn together get arcs around one centre, "
                            "so their spacing stays the same in the turn.\n"
                            "Same R: every corner gets the same radius (like KiCad's Fillet Tracks)."),
                0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        top.Add(self.choice(self, "unit", UNITS, "R and C in mm, or as a multiple of the track width W"),
                0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 4)
        box.Add(top, 0, wx.ALL, 8)

        self.draw = Sketch(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.field(fgs, "r", "R", "Radius of the arc at the track centre line [mm or × W].\n"
                                  "Concentric: of the inner track (see More: R of)")
        self.field(fgs, "c", "C", "Chamfer: how far back from the corner the cut starts, along each "
                                  "track [mm or × W]")
        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.readout(fgs, "now", "Now", "Arc radii and sharp corners of the selection before the change")
        self.readout(fgs, "corners", "Done", "Corners changed / made smaller to fit / left as they are")
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        nud = wx.BoxSizer(wx.HORIZONTAL)
        nud.Add(self.grey(self, "Size"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg), "Smaller (− step)", "size", -1), 0)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg, out=True), "Bigger (+ step)", "size", 1),
                0, wx.LEFT, 1)
        nud.Add(self.step_choice(self), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        mp = self.more_pane(box)
        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=4)
        grid.Add(wx.StaticText(mp, label="R of"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.choice(mp, "ref", REFS, "Concentric: which track of a bus gets exactly R (or C); "
                                              "the others follow"), 0)
        grid.Add(wx.StaticText(mp, label="Min angle"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        grid.Add(self.num(mp, "min_angle", "Corners that turn less than this [°] stay as they are "
                                           "(arcs are always redone)"), 0)
        grid.Add(wx.StaticText(mp, label="Too short"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.choice(mp, "short", SHORTS, "When the straight parts are too short for R / C:\n"
                                                  "Shrink: make it as big as fits, Skip: leave the corner"), 0)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP | wx.BOTTOM, 4)
        mp.SetSizer(ps)

    def nudge(self, key, sign):
        if key == "size":
            key = "c" if MODES[self.tg["mode"][1]][1] == g.CHAMFER else "r"
        super().nudge(key, sign)

    def on_state(self):
        mode = MODES[self.tg["mode"][1]][1]
        self.draw.set_state(mode=mode, bus=BUS[self.ch["bus"].GetSelection()][1],
                            ref=self.ch["ref"].GetSelection(), unit=self.ch["unit"].GetSelection())
        self.show_rows(dict(r=mode == g.ROUND, c=mode == g.CHAMFER))
        sharp = mode == g.SHARP
        for w in (self.ch["bus"], self.ch["unit"], self.ch["ref"], self.ch["short"]):
            w.Enable(not sharp)

    def convert(self, raw):
        if raw["r"] < 0 or raw["c"] < 0:
            raise ValueError("R / C")
        return dict(raw, mode=MODES[raw["mode"]][1], bus=BUS[raw["bus"]][1])
