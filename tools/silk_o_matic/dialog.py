# Dialog of silk-o-matic (no pcbnew import, runs without KiCad).

import wx

from . import geometry as g
from . import w95

NAME = "silk-o-matic"
VERSION = "1.0"

SIDES = [("Top", g.TOP), ("Bottom", g.BOTTOM), ("Left", g.LEFT), ("Right", g.RIGHT),
         ("Centre (for the Fab layer)", g.CENTER),
         ("Auto: the first free side (top, bottom, right, left)", g.AUTO)]
ANGLES = ["Keep ∠", "0°", "90°", "Along part"]
WHICH = ["Reference", "Value"]


def side_bitmap(kind, colour):
    def draw(gc, size):
        gc.SetPen(wx.Pen(colour, 1))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRectangle(4.5, 5.5, 7, 5)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(w95.COL_HL))
        if kind == g.TOP:
            gc.DrawRectangle(4, 1, 8, 2)
        elif kind == g.BOTTOM:
            gc.DrawRectangle(4, 13, 8, 2)
        elif kind == g.LEFT:
            gc.DrawRectangle(0, 7, 3, 2)
        elif kind == g.RIGHT:
            gc.DrawRectangle(13, 7, 3, 2)
        elif kind == g.CENTER:
            gc.DrawRectangle(6, 7, 4, 2)
        else:
            gc.SetFont(wx.Font(6, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD), colour)
            gc.DrawRectangle(4, 1, 8, 2)
            gc.SetBrush(wx.Brush(colour))
            gc.DrawRectangle(13, 7, 2, 2)
            gc.DrawRectangle(4, 13, 8, 1)
    return w95.icon_bitmap(draw)


class Sketch(w95.Sketch):
    W, H = 230, 170

    def paint(self, p):
        st = self.state
        side = st.get("side", g.TOP)
        bx, by, bw, bh = 80, 66, 70, 40
        p.rect(bx, by, bw, bh, None, outline=p.ext)                 # courtyard
        p.rect(bx + 6, by + 8, 20, bh - 16, w95.COL_CU, r=2)
        p.rect(bx + bw - 26, by + 8, 20, bh - 16, w95.COL_CU, r=2)
        p.text("courtyard", bx - 20, by + bh + 7, p.off, p.small)
        G = 14
        tw, th = 34, 16
        pos = {g.TOP: (bx + bw / 2, by - G - th / 2), g.BOTTOM: (bx + bw / 2, by + bh + G + th / 2),
               g.LEFT: (bx - G - tw / 2, by + bh / 2), g.RIGHT: (bx + bw + G + tw / 2, by + bh / 2),
               g.CENTER: (bx + bw / 2, by + bh / 2)}
        shown = g.TOP if side == g.AUTO else side
        if side == g.AUTO:
            for sd in (g.BOTTOM, g.RIGHT, g.LEFT):
                x, y = pos[sd]
                p.gc.SetPen(wx.Pen(p.off, 1, wx.PENSTYLE_SHORT_DASH))
                p.gc.SetBrush(wx.TRANSPARENT_BRUSH)
                p.gc.DrawRectangle(x - tw / 2, y - th / 2, tw, th)
        x, y = pos[shown]
        ang = 90.0 if st.get("angle") == g.ANG_90 else 0.0
        p.text("R1", x, y, p.silk, wx.Font(13 if st.get("big") else 11, wx.FONTFAMILY_SWISS,
                                             wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD), angle=ang)
        c = p.col("gap")
        if shown == g.TOP:
            p.arrow(bx + bw - 8, by, bx + bw - 8, by - G, "gap", None)
            p.letter("G", bx + bw + 4, by - G / 2, c)
            p.arrow(x - tw / 2 - 8, y - th / 2, x - tw / 2 - 8, y + th / 2, "h", None)
            p.letter("H", x - tw / 2 - 18, y, p.col("h"))
        elif shown == g.BOTTOM:
            p.arrow(bx + bw - 8, by + bh, bx + bw - 8, by + bh + G, "gap", None)
            p.letter("G", bx + bw + 4, by + bh + G / 2, c)
        elif shown == g.LEFT:
            p.arrow(bx, by + 6, bx - G, by + 6, "gap", None)
            p.letter("G", bx - G / 2, by - 4, c)
        elif shown == g.RIGHT:
            p.arrow(bx + bw, by + 6, bx + bw + G, by + 6, "gap", None)
            p.letter("G", bx + bw + G / 2, by - 4, c)
        if side == g.AUTO:
            p.text("first free of pads, silk, edge", self.W / 2, self.H - 8, p.off, p.small)


class SilkDialog(w95.OMatic):
    NAME = NAME
    FILE = "silk_o_matic"
    DEFAULTS = dict(side=g.AUTO, which=0, angle=g.ANG_0, gap=0.2, h=0, t=0, pad_gap=0.1, silk_gap=0.1,
                    nudge=2, more=False)
    STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
    STEP_DEFAULT = 2
    MINIMUM = dict(gap=-5.0, h=0.0, t=0.0, pad_gap=0.0, silk_gap=0.0)
    OPTIONAL = dict(h="keep", t="keep")
    HAS_CHECK = False
    LAST = {}

    def build(self, box):
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.toggles(self, "side", [side_bitmap(s_[1], self.fg) for s_ in SIDES],
                             [s_[0] for s_ in SIDES]), 0, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.choice(self, "which", WHICH, "Which text to move"), 0,
                wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(top, 0, wx.ALL, 8)

        self.draw = Sketch(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.field(fgs, "gap", "G", "From the courtyard (or the pads and outline) to the text [mm]")
        self.field(fgs, "h", "H", "Text height = width [mm], empty = keep each one's size")
        self.field(fgs, "t", "T", "Line thickness [mm], empty = 15 % of H (or keep)")
        ang = self.choice(self, "angle", ANGLES, "Keep: as it is. 0° / 90°: all the same.\n"
                                                "Along part: 0° for wide parts, 90° for tall ones")
        fgs.Add(self.bold(self, "∠"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        fgs.Add(ang, 0)
        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.readout(fgs, "now", "Now", "Text size / thickness before the change")
        self.readout(fgs, "done", "Done", "Texts placed; crowded = no free side, put where it overlaps least")
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        nud = wx.BoxSizer(wx.HORIZONTAL)
        nud.Add(self.grey(self, "Gap"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg), "Closer (− step)", "gap", -1), 0)
        nud.Add(self.nudge_button(self, w95.squeeze_bitmap(self.fg, out=True), "Further (+ step)", "gap", 1),
                0, wx.LEFT, 1)
        nud.Add(self.step_choice(self), 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        mp = self.more_pane(box)
        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=4)
        grid.Add(wx.StaticText(mp, label="Pad gap"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        grid.Add(self.num(mp, "pad_gap", "Keep the text this far from pads (solder mask openings) [mm]"), 0)
        grid.Add(wx.StaticText(mp, label="Silk gap"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        grid.Add(self.num(mp, "silk_gap", "Keep the text this far from other silkscreen [mm]"), 0)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP | wx.BOTTOM, 4)
        mp.SetSizer(ps)

    def on_state(self):
        side = SIDES[self.tg["side"][1]][1]
        try:
            big = float(self.f["h"].GetValue() or 0) >= 1.2
        except ValueError:
            big = False
        self.draw.set_state(side=side, angle=self.ch["angle"].GetSelection(), big=big)
        self.f["gap"].Enable(side != g.CENTER)

    def convert(self, raw):
        if raw["h"] < 0 or raw["t"] < 0:
            raise ValueError("H / T")
        return dict(raw, side=SIDES[raw["side"]][1])
