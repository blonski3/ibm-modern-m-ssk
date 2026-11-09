# Dialog of bus-o-matic (no pcbnew import, runs without KiCad).

import wx

from . import geo
from . import geometry as g
from . import w95

NAME = "bus-o-matic"
VERSION = "1.0"

SHAPES = [("Straight: L1", g.STRAIGHT), ("Bend: L1, turn, L2", g.BEND),
          ("Jog: L1, turn, L2, turn back, L3", g.JOG), ("U-turn: L1, turn, L2, turn again, L3", g.UTURN)]
SIDES = [("Turn left (as seen on screen, looking along the tracks)", g.TURN_LEFT),
         ("Turn right", g.TURN_RIGHT)]
ANGLES = ["45°", "90°"]
CORNERS = ["Sharp", "45° cut"]

_ICON = {g.STRAIGHT: ([(1, 11), (15, 11)], [(1, 6), (15, 6)]),
         g.BEND: ([(1, 14), (13, 14), (13, 1)], [(1, 10), (9, 10), (9, 1)]),
         g.JOG: ([(1, 14), (6, 14), (11, 9), (15, 9)], [(1, 10), (4.3, 10), (9.3, 5), (15, 5)]),
         g.UTURN: ([(1, 15), (13, 15), (13, 2), (1, 2)], [(1, 11), (9, 11), (9, 6), (1, 6)])}


def shape_bitmap(kind, colour):
    def draw(gc, size):
        for k, pts in enumerate(_ICON[kind]):
            gc.SetPen(wx.Pen(w95.COL_CU if k == 0 else colour, 2))
            path = gc.CreatePath()
            path.MoveToPoint(*pts[0])
            for q in pts[1:]:
                path.AddLineToPoint(*q)
            gc.StrokePath(path)
    return w95.icon_bitmap(draw)


def side_bitmap(side, colour):
    def draw(gc, size):
        gc.SetPen(wx.Pen(colour, 2))
        path = gc.CreatePath()
        if side == g.TURN_LEFT:
            path.MoveToPoint(1, 13)
            path.AddLineToPoint(10, 13)
            path.AddLineToPoint(10, 3)
            gc.StrokePath(path)
            gc.SetBrush(wx.Brush(colour))
            gc.SetPen(wx.TRANSPARENT_PEN)
            tri = gc.CreatePath()
            tri.MoveToPoint(10, 0)
            tri.AddLineToPoint(14, 5)
            tri.AddLineToPoint(6, 5)
            tri.CloseSubpath()
            gc.FillPath(tri)
        else:
            path.MoveToPoint(1, 3)
            path.AddLineToPoint(10, 3)
            path.AddLineToPoint(10, 13)
            gc.StrokePath(path)
            gc.SetBrush(wx.Brush(colour))
            gc.SetPen(wx.TRANSPARENT_PEN)
            tri = gc.CreatePath()
            tri.MoveToPoint(10, 16)
            tri.AddLineToPoint(14, 11)
            tri.AddLineToPoint(6, 11)
            tri.CloseSubpath()
            gc.FillPath(tri)
    return w95.icon_bitmap(draw)


class Sketch(w95.Sketch):
    """Three tracks continued by the real geometry, scaled into the picture."""
    W, H = 250, 190
    M = 24

    def paint(self, p):
        st = self.state
        shape = st.get("shape", g.STRAIGHT)
        fan = st.get("fan", 0)                 # 0 keep, -1 closer, +1 further apart
        fp = 6.0 if fan < 0 else 14.0
        S = 10.0
        lanes = [g.Lane((-k * 4.0, -S * (1 - k)), (1, 0), 0.2, 0, k, chain=(), seg=None) for k in range(3)]
        lanes[1].end = (6.0, 0.0)
        v = dict(shape=shape, side=st.get("side", g.TURN_LEFT), ang=st.get("ang", 90), l1=40.0, l2=40.0,
                 l3=40.0, pitch=fp if fan else None, corner=st.get("corner", g.SHARP), c=5.0)
        if shape == g.UTURN and v["ang"] == 90:
            v["l2"] = 45.0
        plan = g.plan(lanes, v)
        stubs = [[(ln.end[0] - 22, ln.end[1]), ln.end] for ln in plan.lanes]
        allp = [q for path in plan.paths for q in path] + [q for s in stubs for q in s]
        x0, y0, x1, y1 = geo.bbox(allp)
        M = self.M
        k = min((self.W - 2 * M) / max(x1 - x0, 1e-6), (self.H - 2 * M - 10) / max(y1 - y0, 1e-6), 2.2)
        ox = (self.W - k * (x1 - x0)) / 2.0 - k * x0
        oy = (self.H - 10 - k * (y1 - y0)) / 2.0 - k * y0

        def T(q):
            return (ox + k * q[0], oy + k * q[1])

        for s in stubs:
            p.path([T(q) for q in s], p.off, 4)
        for path in plan.paths:
            p.path([T(q) for q in path], w95.COL_CU, 4)
        mid = plan.paths[1]
        gpts = plan.stats["guide"]
        names = ["L1", "L2", "L3"]
        keys = ["l1", "l2", "l3"]
        for i, (a, b) in enumerate(zip(gpts, gpts[1:])):
            m = T(geo.mul(geo.add(a, b), 0.5))
            d = geo.unit(geo.sub(b, a))
            n = g.left(d)
            # on the outside of the turn next to it (left of travel when straight)
            t1 = -1.0 if v["side"] == g.TURN_LEFT else 1.0
            side = 1.0 if shape == g.STRAIGHT else (-t1 if (i == 2 and shape == g.JOG) else t1)
            off = ((fp if fan else S) * k + 12) * side
            p.letter(names[i], m[0] + n[0] * off, m[1] + n[1] * off, p.col(keys[i]))
        # pitch at the end
        ends = [path[-1] for path in plan.paths]
        e0, e2 = T(ends[0]), T(ends[2])
        dx, dy = e2[0] - e0[0], e2[1] - e0[1]
        L = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        ux, uy = dx / L, dy / L
        e1 = T(ends[1])
        p.arrow(e1[0] - ux * 2, e1[1] - uy * 2, e0[0] + ux * 2, e0[1] + uy * 2, "pitch", None)
        last = T(mid[-1])
        prev = T(mid[-2])
        fx, fy = last[0] - prev[0], last[1] - prev[1]
        fl = max((fx * fx + fy * fy) ** 0.5, 1e-6)
        p.letter("P", e1[0] + fx / fl * 12 - ux * 6, e1[1] + fy / fl * 12 - uy * 6, p.col("pitch"))
        if shape == g.UTURN:
            pass
        elif fan:
            p.text("45° fan to the new pitch first", self.W / 2, self.H - 6, p.off, p.small)
        elif shape == g.STRAIGHT:
            p.text("ends squared, then L1", self.W / 2, self.H - 6, p.off, p.small)


class BusDialog(w95.OMatic):
    NAME = NAME
    FILE = "bus_o_matic"
    DEFAULTS = dict(shape=0, side=0, ang=1, corner=0, l1=5.0, l2=5.0, l3=5.0, pitch=0, c=0.0, w=0,
                    flip=False, check=True, nudge=2, more=False)
    STEPS = [0.05, 0.1, 0.25, 0.5, 1.0, 2.54]
    STEP_DEFAULT = 3
    MINIMUM = dict(l1=0.0, l2=0.0, l3=0.0, pitch=0.01, c=0.0, w=0.01)
    OPTIONAL = dict(pitch="keep", w="keep")
    LAST = {}
    CHECK_TIP = "Check the clearance of the new tracks to copper of other nets and to each other " \
                "(netclass clearance, board edge)"

    def build(self, box):
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.toggles(self, "shape", [shape_bitmap(s[1], self.fg) for s in SHAPES],
                             [s[0] for s in SHAPES]), 0, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.toggles(self, "side", [side_bitmap(s[1], self.fg) for s in SIDES],
                             [s[0] for s in SIDES]), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        top.Add(self.choice(self, "ang", ANGLES, "Angle of each turn"), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(top, 0, wx.ALL, 8)

        self.draw = Sketch(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.field(fgs, "l1", "L1", "Straight on from the (squared) ends, after the fan [mm, centre line]")
        self.field(fgs, "l2", "L2", "After the first turn [mm, centre line]")
        self.field(fgs, "l3", "L3", "After the second turn [mm, centre line]")
        self.field(fgs, "pitch", "P", "Pitch (centre to centre) of the continued tracks [mm];\n"
                                      "empty = keep how they are now")
        cor = self.choice(self, "corner", CORNERS, "90° corners: sharp, or cut at 45° with the spacing kept "
                                                   "(round them later with fillet-o-matic)")
        fgs.Add(self.bold(self, "∟"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        fgs.Add(cor, 0)
        self.field(fgs, "c", "C", "45° cut of the inner track [mm]; the outer ones get longer cuts")
        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.readout(fgs, "now", "Now", "Tracks and their pitch now")
        self.readout(fgs, "done", "Done", "Length added to each track")
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        nud = wx.BoxSizer(wx.HORIZONTAL)
        nud.Add(self.grey(self, "Pitch"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg), "Closer (− step)", "pitch", -1), 0)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg, out=True), "Further (+ step)", "pitch", 1),
                0, wx.LEFT, 1)
        nud.Add(self.grey(self, "L1"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)
        nud.Add(self.nudge_button(self, w95.arrow_bitmap(180, self.fg), "Shorter (− step)", "l1", -1), 0)
        nud.Add(self.nudge_button(self, w95.arrow_bitmap(0, self.fg), "Longer (+ step)", "l1", 1), 0, wx.LEFT, 1)
        nud.Add(self.step_choice(self), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        mp = self.more_pane(box)
        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=4)
        grid.Add(wx.StaticText(mp, label="Width"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.num(mp, "w", "Width of the new tracks [mm]; empty = each one like its last piece"), 0)
        grid.Add(self.checkbox(mp, "flip", "Other end",
                               "Continue from the other end of tracks that are open on both ends"),
                 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP | wx.BOTTOM, 4)
        mp.SetSizer(ps)

    def on_state(self):
        shape = SHAPES[self.tg["shape"][1]][1]
        ang = (45, 90)[self.ch["ang"].GetSelection()]
        corner = self.ch["corner"].GetSelection()
        fan = 0
        try:
            pv = float(self.f["pitch"].GetValue().strip().replace(",", "."))
            now = float(self.nc.get("pitch", pv))
            fan = 0 if abs(pv - now) < 1e-6 else (-1 if pv < now else 1)
        except ValueError:
            pass
        self.draw.set_state(shape=shape, side=self.tg["side"][1], ang=ang, corner=corner, fan=fan)
        self.show_rows(dict(l2=shape != g.STRAIGHT, l3=shape in (g.JOG, g.UTURN)))
        turns = shape != g.STRAIGHT
        for b in self.tg["side"][0]:
            b.Enable(turns)
        self.ch["ang"].Enable(turns)
        self.ch["corner"].Enable(turns and ang == 90)
        self.f["c"].Enable(turns and ang == 90 and corner == g.CUT)

    def convert(self, raw):
        for k in ("l1", "l2", "l3", "c", "pitch", "w"):
            if raw[k] < 0:
                raise ValueError(k.upper())
        return dict(raw, shape=SHAPES[raw["shape"]][1], side=SIDES[raw["side"]][1],
                    ang=(45, 90)[raw["ang"]], pitch=raw["pitch"] or None, w=raw["w"] or None)
