# Dialog of the spacing-o-matic plugin, in the style of via-o-tronic: mode choices on top,
# the dimensions as letters on a small pictogram with the values in a column next to it,
# live readout of the spacing measured now, rarely used options folded under "More".
# Colours follow the system theme. No pcbnew import here, so it runs without KiCad.

import math
import os

import wx

from . import geometry as g

NAME = "spacing-o-matic"
VERSION = "1.0"

MODES = [("Pitch", g.MODE_PITCH), ("Gap", g.MODE_GAP)]
KEEPS = [("Keep first", g.KEEP_FIRST), ("Keep centre", g.KEEP_CENTER), ("Keep last", g.KEEP_LAST)]
ENDS = [("Slide ends", g.ENDS_SLIDE), ("45° jogs", g.ENDS_JOG), ("Stretch", g.ENDS_STRETCH)]

DEFAULTS = dict(mode=0, keep=1, ends=0, value=0.0, width=0, shift=0.0, snap=0.0, tol=1.0,
                values="", check=True, nudge=2, more=False)
STEPS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25]     # mm per wheel notch / arrow click
MINIMUM = dict(value=None, width=0.05, shift=None, snap=0.0, tol=0.1)
OPTIONAL = ("width",)                              # empty = keep the track's width

_last = {}   # last used settings, kept for this KiCad session


def is_dark(colour):
    return (0.299 * colour.Red() + 0.587 * colour.Green() + 0.114 * colour.Blue()) < 128


def arrow_bitmap(angle, colour, size=16, double=False):
    """Small arrow pointing at angle (0 = right, 90 = up); double = arrows both ways."""
    img = wx.Image(size, size)
    img.InitAlpha()
    for x in range(size):
        for y in range(size):
            img.SetAlpha(x, y, 0)
    bmp = wx.Bitmap(img)
    dc = wx.MemoryDC(bmp)
    gc = wx.GraphicsContext.Create(dc)
    c = size / 2.0
    a = math.radians(angle)
    ux, uy = math.cos(a), -math.sin(a)
    gc.SetPen(wx.Pen(colour, 2))
    gc.StrokeLine(c - 5 * ux, c - 5 * uy, c + 5 * ux, c + 5 * uy)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(colour))
    for sgn in ((1, -1) if double else (1,)):
        tip = (c + sgn * 7 * ux, c + sgn * 7 * uy)
        p = gc.CreatePath()
        p.MoveToPoint(*tip)
        p.AddLineToPoint(tip[0] - sgn * 5 * ux - 4 * uy, tip[1] - sgn * 5 * uy + 4 * ux)
        p.AddLineToPoint(tip[0] - sgn * 5 * ux + 4 * uy, tip[1] - sgn * 5 * uy - 4 * ux)
        p.CloseSubpath()
        gc.FillPath(p)
    del gc
    dc.SelectObject(wx.NullBitmap)
    return bmp


def squeeze_bitmap(colour, size=16, out=False):
    """Two bars with arrows towards each other (tighter) or apart (wider)."""
    img = wx.Image(size, size)
    img.InitAlpha()
    for x in range(size):
        for y in range(size):
            img.SetAlpha(x, y, 0)
    bmp = wx.Bitmap(img)
    dc = wx.MemoryDC(bmp)
    gc = wx.GraphicsContext.Create(dc)
    gc.SetPen(wx.Pen(colour, 2))
    gc.StrokeLine(2, 2, 14, 2)
    gc.StrokeLine(2, 14, 14, 14)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(colour))
    for sgn in (-1, 1):                            # upper / lower arrow
        d = sgn if out else -sgn                   # arrow direction (+ = down)
        tip_y = 8 + sgn * 4 if out else 8 + sgn * 1
        p = gc.CreatePath()
        p.MoveToPoint(8, tip_y)
        p.AddLineToPoint(4, tip_y - d * 4)
        p.AddLineToPoint(12, tip_y - d * 4)
        p.CloseSubpath()
        gc.FillPath(p)
    del gc
    dc.SelectObject(wx.NullBitmap)
    return bmp


# ---------------------------------------------------------------- pictogram

DRAW_W, DRAW_H = 300, 200
LANES_Y = (62, 94, 126, 158)          # lanes after the change: equal pitch (32 px)
PADS_Y = (36, 84, 140, 182)           # where the tracks come from (uneven)
PAD_X = 16
LANE_W = 9
X_END = 236                           # lanes leave the picture here
X_P, X_G = 262, 204                   # dimension lines
COL_CU = wx.Colour(200, 52, 52)
COL_GHOST = wx.Colour(200, 52, 52, 70)
COL_HL = wx.Colour(255, 140, 0)


class Drawing(wx.Panel):
    """Bus sketch with lettered dimensions P (pitch), G (gap), W (width), S (shift)."""

    def __init__(self, parent):
        super().__init__(parent, size=(DRAW_W, DRAW_H))
        self.SetMinSize((DRAW_W, DRAW_H))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.mode = g.MODE_PITCH
        self.ends = g.ENDS_SLIDE
        self.keep = g.KEEP_CENTER
        self.hl = None
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def set_state(self, mode=None, ends=None, keep=None, hl=False):
        if mode is not None:
            self.mode = mode
        if ends is not None:
            self.ends = ends
        if keep is not None:
            self.keep = keep
        if hl is not False:
            self.hl = hl
        self.Refresh()

    def _path(self, k):
        py, ly = PADS_Y[k], LANES_Y[k]
        dy = abs(ly - py)
        x0 = PAD_X + 10
        if self.ends == g.ENDS_JOG:
            return [(x0, py), (x0 + 30, py), (x0 + 30 + dy, ly), (X_END, ly)]
        if self.ends == g.ENDS_STRETCH:
            return [(x0, py), (x0 + 56, ly), (X_END, ly)]
        return [(x0, py), (x0 + dy, ly), (X_END, ly)]

    def on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        bg = self.GetParent().GetBackgroundColour()
        dark = is_dark(bg)
        dim = wx.Colour(110, 190, 255) if dark else wx.Colour(0, 90, 190)
        off = wx.Colour(100, 100, 100) if dark else wx.Colour(170, 170, 170)
        ext = wx.Colour(105, 105, 105) if dark else wx.Colour(175, 175, 175)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        hl = self.hl
        active = "value"

        def col(key, on=True):
            if key == hl or (key == active and hl == "value"):
                return COL_HL
            return dim if on else off

        def dash(x0, y0, x1, y1):
            gc.SetPen(wx.Pen(ext, 1, wx.PENSTYLE_SHORT_DASH))
            gc.StrokeLine(x0, y0, x1, y1)

        def letter(text, x, y, c):
            gc.SetFont(font, c)
            w, h = gc.GetTextExtent(text)
            gc.SetBrush(wx.Brush(bg))
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.DrawRectangle(x - w / 2 - 2, y - h / 2, w + 4, h)
            gc.DrawText(text, x - w / 2, y - h / 2)

        def arrow(x0, y0, x1, y1, c, text, tx, ty, inward=False):
            gc.SetPen(wx.Pen(c, 1))
            gc.StrokeLine(x0, y0, x1, y1)
            gc.SetBrush(wx.Brush(c))
            gc.SetPen(wx.TRANSPARENT_PEN)
            for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
                L = math.hypot(bx - ax, by - ay) or 1
                ux, uy = (bx - ax) / L, (by - ay) / L
                if inward:                      # arrows outside, pointing at the gap
                    ux, uy = -ux, -uy
                p = gc.CreatePath()
                p.MoveToPoint(ax, ay)
                p.AddLineToPoint(ax + 6 * ux - 3 * uy, ay + 6 * uy + 3 * ux)
                p.AddLineToPoint(ax + 6 * ux + 3 * uy, ay + 6 * uy - 3 * ux)
                p.CloseSubpath()
                gc.FillPath(p)
            letter(text, tx, ty, c)

        # pads on the left, ghost of the old (uneven) lane positions
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(COL_CU))
        for py in PADS_Y:
            gc.DrawRoundedRectangle(PAD_X - 8, py - 7, 18, 14, 3)
        ghost = [70, 92, 136, 150]
        gc.SetPen(wx.Pen(wx.Colour(COL_CU.Red(), COL_CU.Green(), COL_CU.Blue(), 60), LANE_W))
        for gy in ghost:
            gc.StrokeLine(150, gy, X_END, gy)
        # tracks
        for k in range(len(LANES_Y)):
            c = COL_HL if (hl == "width" and k == 3) else COL_CU
            gc.SetPen(wx.Pen(c, LANE_W))
            pts = self._path(k)
            p = gc.CreatePath()
            p.MoveToPoint(*pts[0])
            for q in pts[1:]:
                p.AddLineToPoint(*q)
            gc.StrokePath(p)
        # the lane that keeps its place
        kk = {g.KEEP_FIRST: 0, g.KEEP_LAST: 3}.get(self.keep)
        gc.SetBrush(wx.Brush(dim))
        gc.SetPen(wx.TRANSPARENT_PEN)
        if kk is None:                         # centre line of the bus
            yc = (LANES_Y[0] + LANES_Y[-1]) / 2.0
            dash(140, yc, X_END + 8, yc)
            ys = yc
        else:
            ys = LANES_Y[kk]
        p = gc.CreatePath()
        p.MoveToPoint(X_END + 4, ys)
        p.AddLineToPoint(X_END + 12, ys - 5)
        p.AddLineToPoint(X_END + 12, ys + 5)
        p.CloseSubpath()
        gc.FillPath(p)
        # P: centre to centre (lanes 1-2), G: edge to edge (lanes 2-3)
        pitch_on = self.mode == g.MODE_PITCH
        dash(X_END, LANES_Y[0], X_P + 5, LANES_Y[0])
        dash(X_END, LANES_Y[1], X_P + 5, LANES_Y[1])
        cp = COL_HL if hl in ("value", "pitch") and pitch_on else (dim if pitch_on else off)
        arrow(X_P, LANES_Y[0], X_P, LANES_Y[1], cp, "P", X_P + 14, (LANES_Y[0] + LANES_Y[1]) / 2.0)
        g1, g2 = LANES_Y[1] + LANE_W / 2.0, LANES_Y[2] - LANE_W / 2.0
        cg = COL_HL if hl in ("value", "gap") and not pitch_on else (off if pitch_on else dim)
        arrow(X_G, g1, X_G, g2, cg, "G", X_G + 14, (g1 + g2) / 2.0)
        # S: shift of the whole bus (dashed = where it would be without S)
        cs = col("shift")
        dash(150, LANES_Y[-1] + 22, X_END, LANES_Y[-1] + 22)
        arrow(X_G - 30, LANES_Y[-1] + 22, X_G - 30, LANES_Y[-1] + 36, cs, "S", X_G - 16,
              LANES_Y[-1] + 29)
        # W with a short leader
        gc.SetPen(wx.Pen(col("width"), 1))
        gc.StrokeLine(110, LANES_Y[3] + 3, 120, LANES_Y[3] + 22)
        letter("W", 126, LANES_Y[3] + 28, col("width"))


class LogWindow(wx.Frame):
    """Small live log of the current problems with hints; Copy puts it on the clipboard."""

    def __init__(self, parent):
        super().__init__(parent, title=NAME + " – log", size=(560, 260),
                         style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.FRAME_TOOL_WINDOW)
        pnl = wx.Panel(self)
        self.txt = wx.TextCtrl(pnl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
        copy = wx.Button(pnl, label="Copy")
        copy.Bind(wx.EVT_BUTTON, self.on_copy)
        bs = wx.BoxSizer(wx.VERTICAL)
        bs.Add(self.txt, 1, wx.ALL | wx.EXPAND, 6)
        bs.Add(copy, 0, wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT, 6)
        pnl.SetSizer(bs)
        p = parent.GetScreenRect()
        self.SetPosition((p.GetLeft(), p.GetBottom() + 4))

    def update(self, text):
        if self.txt.GetValue() != text:
            self.txt.SetValue(text)

    def on_copy(self, _evt):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.txt.GetValue()))
            wx.TheClipboard.Close()


class _Mods:
    """Keyboard modifiers at the time of a button click (Shift = x10, Ctrl = /10)."""

    def __init__(self):
        st = wx.GetMouseState()
        self._s, self._c = st.ShiftDown(), st.ControlDown()

    def ShiftDown(self):
        return self._s

    def ControlDown(self):
        return self._c


# ---------------------------------------------------------------- dialog

class SpacingDialog(wx.Dialog):
    """Modeless while it is open (zoom, pan, select other tracks and press the reselect
    button). Every change is applied to the board at once (OK keeps it, Cancel puts the
    tracks back). preview_cb(values) -> dict(info, warnings, now_p, now_g, move, width);
    reselect_cb() -> (summary text, means or None) or None."""

    def __init__(self, frame, defaults, summary, preview_cb, reselect_cb, here):
        super().__init__(None, title=NAME,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP | wx.DIALOG_NO_PARENT)
        self.preview_cb = preview_cb
        self.reselect_cb = reselect_cb
        self.result = False
        self.log_win = None
        self.last = {}
        self._loop = None
        self._timer = None
        v = dict(DEFAULTS, **defaults)
        remembered = dict(_last)
        remembered.pop("value", None)          # the value starts from what is measured now
        remembered.pop("values", None)
        v.update(remembered)
        if v["value"] <= 0:
            v["value"] = defaults.get("mean_p" if v["mode"] == 0 else "mean_g", 0.3)
        self.means = dict(p=defaults.get("mean_p", 0.0), g=defaults.get("mean_g", 0.0))
        self.nc = dict(width=defaults.get("avg_width", 0.2))
        dark = is_dark(self.GetBackgroundColour())
        try:
            self.SetIcon(wx.Icon(os.path.join(here, "spacing_o_matic.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass
        fg = self.GetForegroundColour()
        dimc = wx.Colour(110, 190, 255) if dark else wx.Colour(0, 90, 190)

        box = wx.BoxSizer(wx.VERTICAL)

        # logo, summary, reselect
        head = wx.BoxSizer(wx.HORIZONTAL)
        logo = os.path.join(here, "spacing_o_matic_logo_dark.png" if dark else "spacing_o_matic_logo.png")
        if os.path.exists(logo):
            head.Add(wx.StaticBitmap(self, bitmap=wx.Bitmap(logo, wx.BITMAP_TYPE_PNG)),
                     0, wx.ALIGN_CENTER_VERTICAL)
        head.AddStretchSpacer()
        self.reselect = wx.Button(self, label="↻", style=wx.BU_EXACTFIT)
        self.reselect.SetToolTip("Use the tracks selected now (measures them again)")
        head.Add(self.reselect, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(head, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)
        self.summary = wx.StaticText(self, label=summary)
        self.summary.SetForegroundColour(wx.Colour(140, 140, 140))
        box.Add(self.summary, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        # mode, what stays in place, how the ends follow
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.mode = wx.Choice(self, choices=[m[0] for m in MODES])
        self.mode.SetSelection(min(v["mode"], len(MODES) - 1))
        self.mode.SetToolTip("Pitch = centre to centre (P), Gap = copper edge to edge (G)")
        self.keep = wx.Choice(self, choices=[k[0] for k in KEEPS])
        self.keep.SetSelection(min(v["keep"], len(KEEPS) - 1))
        self.keep.SetToolTip("Which track stays in place: the first (top / left), the last, "
                             "or the centre line of the bus")
        self.ends = wx.Choice(self, choices=[e[0] for e in ENDS])
        self.ends.SetSelection(min(v["ends"], len(ENDS) - 1))
        self.ends.SetToolTip("Slide ends: the neighbouring segments keep their angle (45° stays 45°); "
                             "where that is impossible (pad, via, junction) a 45° jog is added.\n"
                             "45° jogs: the ends stay, a 45° jog joins them to the moved track.\n"
                             "Stretch: the neighbours' ends move with the track (their angle changes).")
        for c in (self.mode, self.keep, self.ends):
            row.Add(c, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)
        box.Add(row, 0, wx.ALL, 8)

        # drawing + values
        self.draw = Drawing(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.f, self.rows = {}, {}
        FW = 64

        def bold(text):
            lbl = wx.StaticText(self, label=text)
            lbl.SetForegroundColour(dimc)
            lbl.SetFont(lbl.GetFont().Bold())
            return lbl

        def hover(key, *ws):
            for w in ws:
                w.Bind(wx.EVT_ENTER_WINDOW, lambda e, k=key: (self.draw.set_state(hl=k), e.Skip()))
                w.Bind(wx.EVT_LEAVE_WINDOW, lambda e: (self.draw.set_state(hl=self._focus_key()), e.Skip()))

        def field(key, lab, tip, tail=None):
            val = v.get(key, 0)
            t = wx.TextCtrl(self, value="" if key in OPTIONAL and not val else "%g" % round(val, 4),
                            size=(FW, -1), style=wx.TE_PROCESS_ENTER)
            t.SetToolTip(tip)
            if key in OPTIONAL:
                try:
                    t.SetHint("keep")
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, self.on_change)
            lbl = bold(lab)
            fgs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
            if tail is None:
                fgs.Add(t, 0)
            else:
                h = wx.BoxSizer(wx.HORIZONTAL)
                h.Add(t, 0)
                h.Add(tail, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 3)
                fgs.Add(h, 0)
            self.f[key] = t
            self.rows[key] = (lbl, t)
            hover(key, t, lbl)
            t.Bind(wx.EVT_SET_FOCUS, lambda e, k=key: (self.draw.set_state(hl=k), e.Skip()))
            return t

        self.use_now = wx.Button(self, label="= now", style=wx.BU_EXACTFIT)
        self.use_now.SetToolTip("Take the average spacing measured now (equalise without changing it)")
        self.use_now.Bind(wx.EVT_BUTTON, self.on_use_now)
        field("value", "P", "Spacing to set [mm]: pitch P (centre → centre) or gap G "
                            "(edge → edge), see the choice above", tail=self.use_now)
        field("width", "W", "Track width [mm] for all the tracks, empty = keep each one's width")
        field("shift", "S", "Move the whole bus sideways [mm], + = down / right "
                            "(to the side of the last track)")

        def readout(lab, tip):
            lbl = bold(lab)
            t = wx.StaticText(self, label="–")
            t.SetToolTip(tip)
            fgs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
            fgs.Add(t, 0, wx.ALIGN_CENTER_VERTICAL)
            return t

        fgs.Add((0, 4))
        fgs.Add((0, 4))
        self.now_p = readout("P now", "Pitch measured on the board now, smallest – largest [mm]")
        self.now_g = readout("G now", "Gap measured on the board now, smallest – largest [mm]")
        self.new_txt = readout("Move", "Largest sideways move of a track for these settings [mm]")
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        # click buttons: spacing tighter / wider, bus up / down, step
        nud = wx.BoxSizer(wx.HORIZONTAL)
        lab = wx.StaticText(self, label="Spacing")
        lab.SetForegroundColour(wx.Colour(140, 140, 140))
        nud.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.nudge_btn = []
        for bmp, tip, key, sign in ((squeeze_bitmap(fg), "Tighter (P/G − step)", "value", -1),
                                    (squeeze_bitmap(fg, out=True), "Wider (P/G + step)", "value", 1)):
            b = wx.BitmapButton(self, bitmap=bmp, style=wx.BU_EXACTFIT)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_BUTTON, lambda e, k=key, sg=sign: self.nudge(k, sg))
            nud.Add(b, 0, wx.RIGHT, 1)
            self.nudge_btn.append(b)
        lab = wx.StaticText(self, label="Bus")
        lab.SetForegroundColour(wx.Colour(140, 140, 140))
        nud.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)
        for ang, tip, sign in ((90, "Bus up / left (S − step)", -1),
                               (270, "Bus down / right (S + step)", 1)):
            b = wx.BitmapButton(self, bitmap=arrow_bitmap(ang, fg), style=wx.BU_EXACTFIT)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_BUTTON, lambda e, sg=sign: self.nudge("shift", sg))
            nud.Add(b, 0, wx.RIGHT, 1)
            self.nudge_btn.append(b)
        self.step_ch = wx.Choice(self, choices=["%g mm" % st for st in STEPS])
        self.step_ch.SetSelection(min(v.get("nudge", 2), len(STEPS) - 1))
        self.step_ch.SetToolTip("Step for these buttons and for the mouse wheel / ↑↓ on any value.\n"
                                "Shift = ×10, Ctrl = ÷10")
        nud.Add(self.step_ch, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        # rarely used options
        self.more = wx.CollapsiblePane(self, label="More",
                                       style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE)
        mp = self.more.GetPane()

        def num(key, tip, width=64, hint=None):
            val = v.get(key, "")
            txt = val if isinstance(val, str) else ("" if hint and not val else "%g" % val)
            t = wx.TextCtrl(mp, value=txt, size=(width, -1))
            t.SetToolTip(tip)
            if hint:
                try:
                    t.SetHint(hint)
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, self.on_change)
            return t

        self.c = dict(
            snap=num("snap", "Put the kept track (or the centre line) on this grid [mm], "
                             "the pitch stays exact; empty = off", hint="off"),
            tol=num("tol", "Segments within this angle of the bus direction count as "
                           "parallel [°]"),
            values=num("values", "Different spacing for each pair, top → bottom: "
                                 "values separated with ; (P or G as chosen). Empty = all equal",
                       width=170, hint="0.4; 0.4; 0.6 …"),
        )
        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=4)
        for lab, key in (("Snap", "snap"), ("Angle tol.", "tol")):
            grid.Add(wx.StaticText(mp, label=lab), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
            grid.Add(self.c[key], 0)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP, 4)
        lr = wx.BoxSizer(wx.HORIZONTAL)
        lr.Add(wx.StaticText(mp, label="Per pair"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 4)
        lr.Add(self.c["values"], 1)
        ps.Add(lr, 0, wx.TOP | wx.BOTTOM | wx.EXPAND, 4)
        mp.SetSizer(ps)
        self.more.Collapse(not v.get("more", False))
        self.more.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_more)
        box.Add(self.more, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        # check, log, status, buttons
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.check = wx.CheckBox(self, label="Check")
        self.check.SetValue(v.get("check", True))
        self.check.SetToolTip("Check the clearance to pads, tracks and vias of other nets "
                              "(zones and the board edge are not checked)")
        self.status = wx.StaticText(self, label="", size=(170, -1),
                                    style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE)
        bottom.Add(self.check, 0, wx.ALIGN_CENTER_VERTICAL)
        self.warn = wx.Button(self, label="⚠ 0", style=wx.BU_EXACTFIT)
        self.warn.SetToolTip("Show the log: what failed and what to change")
        self.warn.Bind(wx.EVT_BUTTON, lambda e: self.show_log())
        self.warn.Hide()
        bottom.Add(self.warn, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 8)
        bottom.Add(self.status, 1, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        bottom.Add(wx.Button(self, wx.ID_CANCEL), 0, wx.RIGHT, 4)
        ok = wx.Button(self, wx.ID_OK)
        ok.SetDefault()
        bottom.Add(ok, 0)
        box.Add(bottom, 0, wx.ALL | wx.EXPAND, 8)

        self.SetSizerAndFit(box)
        self.place(frame)

        for c in (self.mode, self.keep, self.ends):
            c.Bind(wx.EVT_CHOICE, self.on_change)
        self.check.Bind(wx.EVT_CHECKBOX, self.on_change)
        self.reselect.Bind(wx.EVT_BUTTON, self.on_reselect)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(True), id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(False), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, lambda e: self.finish(False))
        for key, t in self.f.items():
            self.spinnable(t, key)
        for key in ("snap", "tol"):
            self.spinnable(self.c[key], key)
        self.update_enabled()

    # -- running without blocking the PCB Editor
    def run(self):
        loop_cls = getattr(wx, "GUIEventLoop", None)
        if loop_cls is None:
            self.result = self.ShowModal() == wx.ID_OK
            return self.result
        self.Show()
        self._loop = loop_cls()
        self._loop.Run()
        return self.result

    def finish(self, ok):
        if self._timer is not None:
            self._timer.Stop()
        self.result = ok
        self.remember()
        if self.log_win:
            self.log_win.Destroy()
            self.log_win = None
        if self.IsModal():
            self.EndModal(wx.ID_OK if ok else wx.ID_CANCEL)
            return
        self.Hide()
        if self._loop is not None and self._loop.IsRunning():
            self._loop.Exit()

    def place(self, frame):
        pos = _last.get("pos")
        if pos is None and frame is not None:
            r = frame.GetScreenRect()
            w, _h = self.GetSize()
            pos = (r.GetRight() - w - 30, r.GetTop() + 110)
        if pos is not None:
            self.SetPosition(wx.Point(*pos))

    def remember(self):
        p = self.GetPosition()
        _last["pos"] = (p.x, p.y)
        _last["more"] = self.more.IsExpanded()

    # -- stepping values with the mouse wheel, arrow keys and the buttons
    def step_size(self, evt=None):
        st = STEPS[self.step_ch.GetSelection()]
        if evt is not None:
            if evt.ShiftDown():
                st *= 10
            elif evt.ControlDown():
                st /= 10.0
        return st

    def bump(self, ctrl, key, n, evt=None):
        s = ctrl.GetValue().strip().replace(",", ".")
        try:
            if s in ("", "keep", "off"):
                val = float(self.nc.get(key, 0.0))
            else:
                val = float(s)
        except ValueError:
            return
        st = self.step_size(evt) if key != "tol" else 0.5
        val = round(val + n * st, 4)
        lo = MINIMUM.get(key)
        if lo is not None:
            val = max(lo, val)
        ctrl.SetValue("%g" % val)          # fires EVT_TEXT -> preview
        ctrl.SetInsertionPointEnd()

    def spinnable(self, ctrl, key):
        def wheel(evt):
            if not ctrl.IsEnabled():
                return
            self.bump(ctrl, key, 1 if evt.GetWheelRotation() > 0 else -1, evt)

        def keys(evt):
            n = {wx.WXK_UP: 1, wx.WXK_DOWN: -1, wx.WXK_PAGEUP: 10,
                 wx.WXK_PAGEDOWN: -10}.get(evt.GetKeyCode())
            if n is None:
                evt.Skip()
                return
            self.bump(ctrl, key, n, evt)
        ctrl.Bind(wx.EVT_MOUSEWHEEL, wheel)
        ctrl.Bind(wx.EVT_KEY_DOWN, keys)
        tip = ctrl.GetToolTipText() if hasattr(ctrl, "GetToolTipText") else ""
        ctrl.SetToolTip((tip + "\n" if tip else "") + "Scroll or ↑↓ to change")

    def nudge(self, key, sign):
        self.bump(self.f[key], key, sign, _Mods())

    def on_use_now(self, _evt=None):
        m = self.means["p" if self.mode.GetSelection() == 0 else "g"]
        self.f["value"].SetValue("%g" % round(m, 4))

    def _focus_key(self):
        w = wx.Window.FindFocus()
        for k, t in self.f.items():
            if t is w:
                return k
        return None

    def on_more(self, _evt=None):
        _last["more"] = self.more.IsExpanded()
        self.Layout()
        self.Fit()

    def update_enabled(self):
        mode = MODES[self.mode.GetSelection()][1]
        lbl = self.rows["value"][0]
        want = "P" if mode == g.MODE_PITCH else "G"
        if lbl.GetLabel() != want:
            lbl.SetLabel(want)
            # switching the mode keeps the tracks where the current value puts them:
            # convert P <-> G with the average width
            try:
                val = float(self.f["value"].GetValue().replace(",", "."))
                wd = self.nc.get("width", 0.0)
                self.f["value"].ChangeValue("%g" % round(val - wd if want == "G" else val + wd, 4))
            except ValueError:
                pass
        self.draw.set_state(mode=mode, ends=ENDS[self.ends.GetSelection()][1],
                            keep=KEEPS[self.keep.GetSelection()][1])
        per_pair = bool(self.c["values"].GetValue().strip())
        self.f["value"].Enable(not per_pair)
        self.use_now.Enable(not per_pair)

    def on_change(self, _evt=None):
        self.update_enabled()
        if self._timer is not None:
            self._timer.Stop()
        self._timer = wx.CallLater(120, self.refresh_preview)

    def on_reselect(self, _evt=None):
        res = self.reselect_cb()
        if res is not None:
            text, means = res
            self.summary.SetLabel(text)
            if means:
                self.means.update(means)
        self.Layout()
        self.Fit()
        self.refresh_preview()

    def refresh_preview(self):
        if not self.IsShown():
            return
        try:
            v = self.values()
        except ValueError as e:
            self.set_status(dict(info="Invalid value" + (": %s" % e if str(e) else ""), warnings=[]))
            return
        wx.BeginBusyCursor()
        try:
            res = self.preview_cb(v)
        finally:
            wx.EndBusyCursor()
        self.set_status(res)

    def set_status(self, res):
        self.last = res or {}
        info = self.last.get("info", "")
        warn = self.last.get("warnings", [])
        self.status.SetLabel(info.split("\n")[0])
        self.status.SetToolTip(info)
        if warn:
            self.warn.SetLabel("⚠ %d" % len(warn))
        if self.warn.IsShown() != bool(warn):
            self.warn.Show(bool(warn))
            self.Layout()
        for key, ctrl in (("now_p", self.now_p), ("now_g", self.now_g), ("move", self.new_txt)):
            if key in self.last:
                ctrl.SetLabel(self.last[key])
        if "width" in self.last:
            self.nc["width"] = self.last["width"]
        if self.log_win:
            self.log_win.update(self.log_text())

    def log_text(self):
        out = [self.last.get("info", "").split("\n")[0], ""]
        warn = self.last.get("warnings", [])
        out += ["⚠ " + w for w in warn] if warn else ["No problems."]
        return "\n".join(out)

    def show_log(self):
        if not self.log_win:
            self.log_win = LogWindow(self)
            self.log_win.Bind(wx.EVT_CLOSE, self._log_closed)
        self.log_win.update(self.log_text())
        self.log_win.Show()
        self.log_win.Raise()

    def _log_closed(self, _evt):
        self.log_win.Destroy()
        self.log_win = None

    def values(self):
        def f(ctrl, optional=False):
            s = ctrl.GetValue().strip().replace(",", ".")
            if optional and s in ("", "keep", "off"):
                return 0.0
            return float(s)
        per = self.c["values"].GetValue().replace(",", ".").replace(";", " ").split()
        raw = dict(mode=self.mode.GetSelection(), keep=self.keep.GetSelection(),
                   ends=self.ends.GetSelection(),
                   value=f(self.f["value"]) if not per else 0.0,
                   width=f(self.f["width"], True), shift=f(self.f["shift"]),
                   snap=f(self.c["snap"], True), tol=f(self.c["tol"]),
                   values=self.c["values"].GetValue(),
                   check=self.check.GetValue(),
                   nudge=self.step_ch.GetSelection())
        try:
            per_list = [float(x) for x in per]
        except ValueError:
            raise ValueError("Per pair")
        if raw["width"] < 0:
            raise ValueError("W")
        if raw["snap"] < 0:
            raise ValueError("Snap")
        if not 0.05 <= raw["tol"] <= 20:
            raise ValueError("Angle tol.")
        _last.update(raw)
        return dict(raw, mode=MODES[raw["mode"]][1], keep=KEEPS[raw["keep"]][1],
                    ends=ENDS[raw["ends"]][1], values=per_list)
