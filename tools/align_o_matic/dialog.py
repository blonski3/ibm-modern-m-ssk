# Dialog of align-o-matic (no pcbnew import, runs without KiCad).

import wx

from . import geometry as g
from . import w95

NAME = "align-o-matic"
VERSION = "1.0"

AXES = [("X: same X as the master (a vertical line), only X changes", g.AX_X),
        ("Y: same Y as the master (a horizontal line), only Y changes", g.AX_Y),
        ("XY ↗: on the 45° line going up-right through the master; only X or Y changes (Move)",
         g.AX_DIAG_UP),
        ("YX ↘: on the 45° line going down-right through the master; only X or Y changes (Move)",
         g.AX_DIAG_DOWN),
        ("Onto the master: both X and Y (e.g. a via onto a pad)", g.AX_ONTO)]
MOVES = ["Move X", "Move Y"]
REFS = ["Origin", "Pads centre", "Body centre"]


def axis_bitmap(kind, colour):
    def draw(gc, size):
        gc.SetPen(wx.Pen(colour, 1, wx.PENSTYLE_SHORT_DASH))
        if kind == g.AX_X:
            gc.StrokeLine(8, 0, 8, 16)
        elif kind == g.AX_Y:
            gc.StrokeLine(0, 8, 16, 8)
        elif kind == g.AX_DIAG_UP:
            gc.StrokeLine(1, 15, 15, 1)
        elif kind == g.AX_DIAG_DOWN:
            gc.StrokeLine(1, 1, 15, 15)
        else:
            gc.StrokeLine(8, 1, 8, 15)
            gc.StrokeLine(1, 8, 15, 8)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(w95.COL_CU))
        gc.DrawRectangle(5, 5, 6, 6)
    return w95.icon_bitmap(draw)


class Sketch(w95.Sketch):
    """Master pad, the line through it and three parts moving onto it (fitted to the
    picture; the left pad of each part is its selected pad)."""
    W, H = 230, 170
    SLAVES = [(60.0, -60.0), (100.0, -28.0), (140.0, 40.0)]

    def part(self, p, x, y, colour, ghost=False):
        if ghost:
            p.gc.SetPen(wx.Pen(p.off, 1, wx.PENSTYLE_SHORT_DASH))
            p.gc.SetBrush(wx.TRANSPARENT_BRUSH)
            p.gc.DrawRectangle(x - 13, y - 6, 26, 12)
            return
        p.rect(x - 13, y - 6, 26, 12, None, outline=p.ext)
        p.rect(x - 11, y - 4, 8, 8, colour, r=1)
        p.rect(x + 3, y - 4, 8, 8, colour, r=1)

    def paint(self, p):
        st = self.state
        axis = st.get("axis", g.AX_X)
        move = st.get("move", g.MOVE_X)
        dx, dy = (14.0 if st.get("dx") else 0.0), (-14.0 if st.get("dy") else 0.0)
        slaves = self.SLAVES[:1] if axis == g.AX_ONTO else self.SLAVES
        moves = []
        for sx, sy in slaves:
            px, py = sx - 7, sy
            tx, ty = g.target((px, py), (0.0, 0.0), axis, move, dx, dy)
            moves.append(((sx, sy), (sx + tx - px, sy + ty - py)))
        pts = [(0.0, 0.0)] + [q for mv in moves for q in mv]
        x0, x1 = min(q[0] for q in pts) - 16, max(q[0] for q in pts) + 16
        y0, y1 = min(q[1] for q in pts) - 10, max(q[1] for q in pts) + 22
        k = min(1.0, (self.W - 12) / (x1 - x0), (self.H - 12) / (y1 - y0))
        ox = (self.W - k * (x1 - x0)) / 2.0 - k * x0
        oy = (self.H - k * (y1 - y0)) / 2.0 - k * y0

        def T(q):
            return (ox + k * q[0], oy + k * q[1])

        mx, my = T((0.0, 0.0))
        kdx, kdy = k * dx, k * dy
        if axis == g.AX_X:
            p.dash(mx + kdx, 4, mx + kdx, self.H - 4)
        elif axis == g.AX_Y:
            p.dash(4, my + kdy, self.W - 4, my + kdy)
        elif axis in (g.AX_DIAG_UP, g.AX_DIAG_DOWN):
            s = -1.0 if axis == g.AX_DIAG_UP else 1.0
            lx, ly = (mx + kdx, my) if move == g.MOVE_X else (mx, my + kdy)
            L = 300
            p.dash(lx - L, ly - s * L, lx + L, ly + s * L)
        else:
            p.dash(mx + kdx - 16, my + kdy, mx + kdx + 16, my + kdy)
            p.dash(mx + kdx, my + kdy - 16, mx + kdx, my + kdy + 16)
        for old, new in moves:
            (ax_, ay_), (bx_, by_) = T(old), T(new)
            self.part(p, ax_, ay_, None, ghost=True)
            L = ((bx_ - ax_) ** 2 + (by_ - ay_) ** 2) ** 0.5
            if L > 30:
                ux, uy = (bx_ - ax_) / L, (by_ - ay_) / L
                p.arrow(ax_ + ux * 15, ay_ + uy * 8, bx_ - ux * 15, by_ - uy * 8, None, heads=1)
        for old, new in moves:
            bx_, by_ = T(new)
            self.part(p, bx_, by_, w95.COL_CU)
        p.rect(mx - 6, my - 6, 12, 12, w95.COL_CU, r=2)
        p.gc.SetPen(wx.Pen(w95.COL_HL, 2))
        p.gc.SetBrush(wx.TRANSPARENT_BRUSH)
        p.gc.DrawRectangle(mx - 9, my - 9, 18, 18)
        p.text("master", mx, my + 17, p.off, p.small)
        diag = axis in (g.AX_DIAG_UP, g.AX_DIAG_DOWN)
        if dx and (axis in (g.AX_X, g.AX_ONTO) or (diag and move == g.MOVE_X)):
            p.arrow(mx, 10, mx + kdx, 10, "dx", None)
            p.letter("DX", mx + kdx + 14, 10, p.col("dx"))
        if dy and (axis in (g.AX_Y, g.AX_ONTO) or (diag and move == g.MOVE_Y)):
            p.arrow(10, my, 10, my + kdy, "dy", None)
            p.letter("DY", 22, my + kdy - 8, p.col("dy"))


class AlignDialog(w95.OMatic):
    NAME = NAME
    FILE = "align_o_matic"
    DEFAULTS = dict(axis=0, move=0, refpt=1, dx=0.0, dy=0.0, drag=False, nudge=2, more=False)
    STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 1.27, 2.54]
    STEP_DEFAULT = 2
    MINIMUM = {}
    HAS_CHECK = False
    LAST = {}
    act_cb = None

    def build(self, box):
        self.reselect.Hide()                         # the buttons below take the selection
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.toggles(self, "axis", [axis_bitmap(a[1], self.fg) for a in AXES], [a[0] for a in AXES]),
                0, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.choice(self, "move", MOVES, "45° lines: which coordinate of the slaves changes"),
                0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        top.Add(self.choice(self, "refpt", REFS,
                            "Point of a whole footprint that goes onto the line (master and slaves).\n"
                            "Selected pads always use the pad centre (several pads: their centre)"),
                0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 4)
        box.Add(top, 0, wx.ALL, 8)

        self.draw = Sketch(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.field(fgs, "dx", "DX", "Offset of the line from the master in X [mm] (X, Onto, 45° with Move X)")
        self.field(fgs, "dy", "DY", "Offset of the line from the master in Y [mm] (Y, Onto, 45° with Move Y)")
        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.readout(fgs, "master", "Master", "The master and its point (X, Y in mm)")
        self.readout(fgs, "last", "Last", "The last Align: how many moved, the biggest move")
        self.readout(fgs, "done", "Done", "All actions in this window (Undo takes them back one by one)")
        for t in self.ro.values():
            t.SetMinSize((190, -1))
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        acts = wx.BoxSizer(wx.HORIZONTAL)
        self.btn = {}
        for key, label, tip in (("master", "⌖ Master", "Make the selected pad / footprint / via the master"),
                                ("align", "⇥ Align", "Align the selected items to the master.\n"
                                                     "Changing the settings right after redoes this Align"),
                                ("undo", "↶ Undo", "Take the last Align back")):
            b = wx.Button(self, label=label)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_BUTTON, lambda e, k=key: self.on_act(k))
            acts.Add(b, 0, wx.RIGHT, 4)
            self.btn[key] = b
        acts.Add(self.step_choice(self), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(acts, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 6)

        mp = self.more_pane(box)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(self.checkbox(mp, "drag", "Drag track ends",
                             "Track ends on the moved pads and vias move with them (same net)"),
               0, wx.ALL, 4)
        mp.SetSizer(ps)

    def on_act(self, key):
        try:
            v = self.values()
        except ValueError as e:
            self.set_status(dict(info="Invalid value: %s" % e, warnings=[]))
            return
        if self.act_cb is not None:
            self.act_cb(key, v)
        if self._timer is not None:
            self._timer.Stop()
        self.refresh()

    def on_state(self):
        axis = AXES[self.tg["axis"][1]][1]
        self.ch["move"].Enable(axis in (g.AX_DIAG_UP, g.AX_DIAG_DOWN))
        move = self.ch["move"].GetSelection()

        def nonzero(k):
            try:
                return abs(float(self.f[k].GetValue().replace(",", ".") or 0)) > 1e-9
            except ValueError:
                return False
        diag = axis in (g.AX_DIAG_UP, g.AX_DIAG_DOWN)
        self.f["dx"].Enable(axis in (g.AX_X, g.AX_ONTO) or (diag and move == g.MOVE_X))
        self.f["dy"].Enable(axis in (g.AX_Y, g.AX_ONTO) or (diag and move == g.MOVE_Y))
        self.draw.set_state(axis=axis, move=move, dx=nonzero("dx"), dy=nonzero("dy"))

    def convert(self, raw):
        return dict(raw, axis=AXES[raw["axis"]][1])
