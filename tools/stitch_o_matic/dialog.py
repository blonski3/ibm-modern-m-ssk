# Dialog of stitch-o-matic (no pcbnew import, runs without KiCad).

import wx

from . import geometry as g
from . import w95

NAME = "stitch-o-matic"
VERSION = "1.0"

MODES = [("Fence: vias along the selected tracks", g.FENCE),
         ("Fill: a grid of vias in the selected zones", g.FILL),
         ("Ring: vias along the board edge (or the selected zone's edge)", g.RING)]
SIDES = [("Both sides", g.BOTH), ("Right", g.RIGHT), ("Left", g.LEFT)]


def mode_bitmap(kind, colour):
    def draw(gc, size):
        gc.SetPen(wx.TRANSPARENT_PEN)
        if kind == g.FENCE:
            gc.SetBrush(wx.Brush(w95.COL_CU))
            gc.DrawRectangle(1, 7, 14, 2)
            gc.SetBrush(wx.Brush(colour))
            for x in (2, 7, 12):
                gc.DrawEllipse(x - 1, 1, 4, 4)
                gc.DrawEllipse(x - 1, 11, 4, 4)
        elif kind == g.FILL:
            gc.SetBrush(wx.Brush(colour))
            for x in (2, 7, 12):
                for y in (2, 7, 12):
                    gc.DrawEllipse(x - 1, y - 1, 4, 4)
        else:
            gc.SetPen(wx.Pen(colour, 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRoundedRectangle(0.5, 0.5, 15, 15, 3)
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(colour))
            for x, y in ((3, 3), (8, 3), (13, 3), (3, 8), (13, 8), (3, 13), (8, 13), (13, 13)):
                gc.DrawEllipse(x - 1.5, y - 1.5, 3, 3)
    return w95.icon_bitmap(draw)


class Sketch(w95.Sketch):
    W, H = 250, 170

    def paint(self, p):
        st = self.state
        mode = st.get("mode", g.FENCE)
        if mode == g.FENCE:
            y = 88
            p.path([(14, y), (150, y), (200, y - 50), (236, y - 50)], w95.COL_CU, 7)
            side = st.get("side", g.BOTH)
            stag = st.get("stagger")
            for sg, on in ((-1, side in (g.BOTH, g.LEFT)), (1, side in (g.BOTH, g.RIGHT))):
                if not on:
                    continue
                x0 = 24 + (14 if stag and sg > 0 else 0)
                for k in range(5):
                    p.via(x0 + k * 28, y + sg * 26, r=6, hole=2.5)
            p.dash(24, y - 26, 24, y - 56)
            p.dash(52, y - 26, 52, y - 56)
            p.arrow(24, y - 50, 52, y - 50, "pitch", "P", ty=y - 62)
            p.dash(140, y, 180, y)
            p.arrow(170, y, 170, y + 26, "offset", "O", tx=182)
            if st.get("rows", 1) > 1:
                p.letter("×%d" % st["rows"], 26, y + 50, p.col("rows"))
        elif mode == g.FILL:
            p.rect(20, 18, 200, 130, None, r=6, outline=w95.COL_CU)
            P = 26
            for j in range(5):
                sh = P / 2 if st.get("hexa") and j % 2 else 0
                for i in range(7):
                    x = 42 + i * P + sh
                    yy = 40 + j * 22 if st.get("hexa") else 40 + j * P * 0.85
                    if x < 205:
                        p.via(x, yy, r=5, hole=2)
            p.arrow(42, 160, 68, 160, "fpitch", "P", tx=55, ty=160)
            p.arrow(20, 30, 37, 30, "margin", None)
            p.letter("M", 28, 18, p.col("margin"))
        else:
            p.rect(14, 14, 222, 142, None, r=14, outline=p.silk)
            for k in range(8):
                p.via(36 + k * 25, 34, r=5, hole=2)
                p.via(36 + k * 25, 136, r=5, hole=2)
            for k in range(1, 4):
                p.via(34, 34 + k * 25.5, r=5, hole=2)
                p.via(216, 34 + k * 25.5, r=5, hole=2)
            p.arrow(36, 52, 61, 52, "rpitch", "P", ty=64)
            p.arrow(120, 14, 120, 34, "inset", None)
            p.letter("O", 134, 24, p.col("inset"))
        p.text("vias: D / d from the netclass", self.W / 2, self.H - 6, p.off, p.small)


class StitchDialog(w95.OMatic):
    NAME = NAME
    FILE = "stitch_o_matic"
    DEFAULTS = dict(mode=0, side=0, pitch=1.0, offset=0.8, fpitch=2.0, margin=0.5, rpitch=2.0, inset=1.0,
                    d=0, drill=0, stagger=False, hexa=True, rows=1, row_gap=0.8, end=0.0, fit=False,
                    inside=False, nudge=2, more=False)
    STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
    STEP_DEFAULT = 2
    MINIMUM = dict(pitch=0.1, fpitch=0.1, rpitch=0.1, offset=0.0, margin=0.0, inset=0.0, rows=1, row_gap=0.0,
                   end=0.0, d=0.0, drill=0.0)
    OPTIONAL = dict(d="auto", drill="auto")
    INTEGERS = {"rows"}
    HAS_CHECK = False
    LAST = {}

    def build(self, box):
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.toggles(self, "mode", [mode_bitmap(m[1], self.fg) for m in MODES],
                             [m[0] for m in MODES]), 0, wx.ALIGN_CENTER_VERTICAL)
        nets = list(self.v.get("nets") or ["GND"])
        self.net_ch = wx.Choice(self, choices=nets)
        want = self.v.get("netname")
        if want not in nets:
            want = self.v.get("net_default")
        self.net_ch.SetSelection(nets.index(want) if want in nets else 0)
        self.net_ch.SetToolTip("Net of the new vias (they connect through its zones)")
        self.net_ch.Bind(wx.EVT_CHOICE, self.on_change)
        top.Add(self.net_ch, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        top.Add(self.choice(self, "side", [s_[0] for s_ in SIDES], "Fence: which side of the tracks"),
                0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 4)
        box.Add(top, 0, wx.ALL, 8)

        self.draw = Sketch(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.field(fgs, "pitch", "P", "Fence: distance between vias along the track [mm]")
        self.field(fgs, "offset", "O", "Fence: from the track centre line to the via centre [mm]")
        self.field(fgs, "fpitch", "P", "Fill: grid pitch [mm]")
        self.field(fgs, "margin", "M", "Fill: from the zone edge to the via edge [mm]")
        self.field(fgs, "rpitch", "P", "Ring: distance between vias along the edge [mm] (spread evenly)")
        self.field(fgs, "inset", "O", "Ring: from the edge to the via centre [mm]")
        self.field(fgs, "d", "D", "Via diameter [mm], empty (auto) = the netclass of the net")
        self.field(fgs, "drill", "d", "Via drill [mm], empty (auto) = the netclass of the net")
        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.readout(fgs, "count", "Vias", "Vias placed")
        self.readout(fgs, "gap", "Gap", "Fence: via edge to track edge [mm]")
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)
        self.left = wx.StaticText(self, label="")
        self.left.SetForegroundColour(w95.GREY)
        box.Add(self.left, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        nud = wx.BoxSizer(wx.HORIZONTAL)
        nud.Add(self.grey(self, "Pitch"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg), "Denser (− step)", "P", -1), 0)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg, out=True), "Sparser (+ step)", "P", 1),
                0, wx.LEFT, 1)
        nud.Add(self.grey(self, "Offset"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)
        nud.Add(self.nudge_button(self, w95.arrow_bitmap(270, self.fg), "Closer (− step)", "O", -1), 0)
        nud.Add(self.nudge_button(self, w95.arrow_bitmap(90, self.fg), "Further (+ step)", "O", 1), 0, wx.LEFT, 1)
        nud.Add(self.step_choice(self), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        mp = self.more_pane(box)
        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=4)
        grid.Add(wx.StaticText(mp, label="Rows"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.num(mp, "rows", "Fence: rows of vias on each side"), 0)
        grid.Add(wx.StaticText(mp, label="Row gap"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        grid.Add(self.num(mp, "row_gap", "Fence: distance between the rows [mm]"), 0)
        grid.Add(wx.StaticText(mp, label="Ends"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.num(mp, "end", "Fence: no vias this close to the ends of the tracks [mm]"), 0)
        grid.Add((0, 0))
        grid.Add(self.checkbox(mp, "fit", "Fit", "Fence: spread the vias evenly from end to end "
                                                "(pitch ≤ P)"), 0)
        grid.Add((0, 0))
        grid.Add(self.checkbox(mp, "stagger", "Stagger", "Fence: the other side / row shifted by P/2"), 0)
        grid.Add((0, 0))
        grid.Add(self.checkbox(mp, "hexa", "Hex grid", "Fill: every other row shifted by P/2"), 0)
        grid.Add((0, 0))
        grid.Add(self.checkbox(mp, "inside", "Inside zone", "Only where a zone of the net is (no dangling vias)"),
                 0)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP | wx.BOTTOM, 4)
        mp.SetSizer(ps)

    def mode(self):
        return MODES[self.tg["mode"][1]][1]

    def nudge(self, key, sign):
        m = self.mode()
        if key == "P":
            key = {g.FENCE: "pitch", g.FILL: "fpitch", g.RING: "rpitch"}[m]
        else:
            key = {g.FENCE: "offset", g.FILL: "margin", g.RING: "inset"}[m]
        super().nudge(key, sign)

    def on_state(self):
        m = self.mode()
        rows = 1
        try:
            rows = max(1, int(self.c["rows"].GetValue()))
        except (ValueError, KeyError):
            pass
        self.draw.set_state(mode=m, side=SIDES[self.ch["side"].GetSelection()][1],
                            stagger=self.cb["stagger"].GetValue(), hexa=self.cb["hexa"].GetValue(), rows=rows)
        self.show_rows(dict(pitch=m == g.FENCE, offset=m == g.FENCE, fpitch=m == g.FILL, margin=m == g.FILL,
                            rpitch=m == g.RING, inset=m == g.RING, gap=m == g.FENCE))
        self.ch["side"].Enable(m == g.FENCE)
        for k in ("rows", "row_gap", "end"):
            self.c[k].Enable(m == g.FENCE)
        for k in ("fit", "stagger"):
            self.cb[k].Enable(m == g.FENCE)
        self.cb["hexa"].Enable(m == g.FILL)

    def set_status(self, res):
        super().set_status(res)
        left = (res or {}).get("left", "")
        if self.left.GetLabel() != left:
            self.left.SetLabel(left)
            self.Layout()
            self.Fit()

    def raw_values(self):
        raw = super().raw_values()
        raw["netname"] = self.net_ch.GetString(self.net_ch.GetSelection())
        return raw

    def convert(self, raw):
        if raw["rows"] < 1:
            raise ValueError("Rows")
        for k in ("pitch", "fpitch", "rpitch"):
            if raw[k] <= 0:
                raise ValueError("P")
        if raw["d"] < 0 or raw["drill"] < 0:
            raise ValueError("D")
        return dict(raw, mode=MODES[raw["mode"]][1], side=SIDES[raw["side"]][1])

