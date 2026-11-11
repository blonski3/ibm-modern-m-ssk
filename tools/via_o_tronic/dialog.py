# Dialog of the via-o-tronic plugin. Built around the common case (fan out a row of
# aQFN/QFN pins to a row of vias): direction arrows and routing mode on top, the main
# dimensions as fields on a small pictogram, rarely used options folded under "More".
# Colours follow the system theme. No pcbnew import here, so it runs without KiCad.

import math
import os
import re

import time

import wx

from . import geometry as g

NAME = "via-o-tronic"
VERSION = "2.2"

# direction buttons: label, angle (0 = right, 90 = up)
DIRS = [("→", 0), ("↗", 45), ("↑", 90), ("↖", 135),
        ("←", 180), ("↙", 225), ("↓", 270), ("↘", 315)]
ROUTES = [("A / 45° / B", g.ROUTE_OFFSET), ("45° at via", g.ROUTE_45_VIA),
          ("45° at pad", g.ROUTE_45_PAD), ("Straight", g.ROUTE_STRAIGHT),
          ("Autoroute", g.ROUTE_AUTO)]
SLACKS = [("Bends at pads", g.SLACK_VIA), ("Bends at vias", g.SLACK_PAD)]
PITCHES = ["Auto", "As pins", "Custom"]
LINES = [("Common", g.LINE_COMMON), ("Per item", g.LINE_EACH)]
REFS = [("Edge → centre", g.REF_EDGE_CENTER), ("Edge → edge", g.REF_EDGE),
        ("Centre → centre", g.REF_CENTER)]
ALIGNS = [("Centre", g.ALIGN_CENTER), ("First", g.ALIGN_FIRST), ("Last", g.ALIGN_LAST)]
PROFILES = [("Constant", g.PROF_CONST), ("Increasing", g.PROF_INC), ("Decreasing", g.PROF_DEC),
            ("V", g.PROF_V), ("A", g.PROF_A), ("Zigzag", g.PROF_ZIGZAG), ("List", g.PROF_CUSTOM)]
GROUPS = [("Across", g.GROUP_ACROSS), ("Along", g.GROUP_ALONG), ("Grid 2×", g.GROUP_GRID)]

DEFAULTS = dict(dir=0, angle="", ref=0, line=0, align=0, route=0, slack=0, pitch_mode=0,
                profile=0, step=0.5, custom="0; 0.5; 1.0",
                vias_per=1, group_mode=0, group_spacing=0, ar_grid=0.05, ar_margin=1.5,
                dist=1.5, lead_pad=0.3, lead_via=0.3, avoid=True, shift=0.0, pitch=0.8,
                via_d=0, via_drill=0, width=0, zigzag=0, zig=0, more=False, live=True, nudge=2, nc={})
STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]      # mm per wheel notch / arrow click
# field -> minimum value when stepping (None = no limit)
MINIMUM = dict(zig=0.0, lead_pad=0.0, lead_via=0.0, dist=0.0, pitch=0.05, shift=None, width=0.05,
               via_d=0.1, via_drill=0.05, step=None, group_spacing=0.0, ar_grid=0.01,
               ar_margin=0.0)

OPTIONAL = ("width", "via_d", "via_drill", "zig")   # empty = netclass / auto

_last = {}   # last used settings, kept for this KiCad session


def is_dark(colour):
    return (0.299 * colour.Red() + 0.587 * colour.Green() + 0.114 * colour.Blue()) < 128


def arrow_bitmap(angle, colour, size=16):
    """Small arrow pointing at angle (0 = right, 90 = up) for the direction buttons."""
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
    tip = (c + 6 * ux, c + 6 * uy)
    gc.SetPen(wx.Pen(colour, 2))
    gc.StrokeLine(c - 6 * ux, c - 6 * uy, c + 2 * ux, c + 2 * uy)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(colour))
    p = gc.CreatePath()
    p.MoveToPoint(*tip)
    p.AddLineToPoint(tip[0] - 6 * ux - 4 * uy, tip[1] - 6 * uy + 4 * ux)
    p.AddLineToPoint(tip[0] - 6 * ux + 4 * uy, tip[1] - 6 * uy - 4 * ux)
    p.CloseSubpath()
    gc.FillPath(p)
    del gc
    dc.SelectObject(wx.NullBitmap)
    return bmp


# ---------------------------------------------------------------- pictogram

# Drawing (px), always for the direction "Right". Dimensions are letters on the drawing,
# the values are typed in the column next to it; the dimension of the field under the
# mouse or with the keyboard focus is highlighted.
CHIP_X = 26                        # chip body edge
PADS_Y = (82, 122, 162)
PAD_X0, PAD_X1 = 20, 44            # pads stick out of the body, edge facing the vias = 44
VIAS_Y = (52, 92, 132)             # via pitch 40, via row shifted up (S) by 30
VIA_X = 240
LEAD_A = 26                        # A / B in px
VIA_R, DRILL_R = 9, 4
TRACK_W = 5
DRAW_W, DRAW_H = 318, 216
Y_D, Y_A, Y_B = 204, 184, 26
X_PS = 290
ZIG_PX = 22                        # zigzag: far vias this much farther (px)
VIA_LAYOUTS = ["Row", "Zigzag"]

COL_CU = wx.Colour(200, 52, 52)
COL_VIA = wx.Colour(226, 186, 40)
COL_HL = wx.Colour(255, 140, 0)


class Drawing(wx.Panel):
    """Fanout sketch with lettered dimensions."""

    def __init__(self, parent):
        super().__init__(parent, size=(DRAW_W, DRAW_H))
        self.SetMinSize((DRAW_W, DRAW_H))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.mode = g.ROUTE_OFFSET
        self.slack = g.SLACK_VIA
        self.zig = False
        self.hl = None
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def set_state(self, mode=None, slack=None, hl=False, zig=None):
        if zig is not None:
            self.zig = zig
        if mode is not None:
            self.mode = mode
        if slack is not None:
            self.slack = slack
        if hl is not False:
            self.hl = hl
        self.Refresh()

    def vx(self, k):
        return VIA_X + (ZIG_PX if self.zig and k % 2 else 0)

    def _paths(self):
        out = []
        for k, (py, vy) in enumerate(zip(PADS_Y, VIAS_Y)):
            jog = py - vy
            X = self.vx(k)
            s = (PAD_X1 - 10, py)
            if self.mode == g.ROUTE_OFFSET:
                if self.slack == g.SLACK_PAD:
                    b2 = X - LEAD_A
                    out.append([s, (b2 - jog, py), (b2, vy), (X, vy)])
                else:
                    b1 = PAD_X1 + LEAD_A
                    out.append([s, (b1, py), (b1 + jog, vy), (X, vy)])
            elif self.mode == g.ROUTE_45_PAD:
                out.append([s, (PAD_X1, py), (PAD_X1 + jog, vy), (X, vy)])
            elif self.mode == g.ROUTE_STRAIGHT:
                out.append([s, (X, vy)])
            elif self.mode == g.ROUTE_AUTO:
                m = 120 + 14 * k
                out.append([s, (m, py), (m + jog, vy), (X, vy)])
            else:
                out.append([s, (X - jog, py), (X, vy)])
        return out

    def on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        bg = self.GetParent().GetBackgroundColour()
        dark = is_dark(bg)
        dim = wx.Colour(110, 190, 255) if dark else wx.Colour(0, 90, 190)
        ext = wx.Colour(105, 105, 105) if dark else wx.Colour(175, 175, 175)
        body = wx.Colour(70, 70, 70) if dark else wx.Colour(205, 205, 205)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        hl = self.hl

        def col(key):
            return COL_HL if key == hl else dim

        def dash(x0, y0, x1, y1):
            gc.SetPen(wx.Pen(ext, 1, wx.PENSTYLE_SHORT_DASH))
            gc.StrokeLine(x0, y0, x1, y1)

        def arrow(x0, y0, x1, y1, key, text, tx, ty):
            c = col(key)
            gc.SetPen(wx.Pen(c, 2 if key == hl else 1))
            gc.StrokeLine(x0, y0, x1, y1)
            gc.SetBrush(wx.Brush(c))
            gc.SetPen(wx.TRANSPARENT_PEN)
            for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
                L = math.hypot(bx - ax, by - ay) or 1
                ux, uy = (bx - ax) / L, (by - ay) / L
                p = gc.CreatePath()
                p.MoveToPoint(ax, ay)
                p.AddLineToPoint(ax + 6 * ux - 3 * uy, ay + 6 * uy + 3 * ux)
                p.AddLineToPoint(ax + 6 * ux + 3 * uy, ay + 6 * uy - 3 * ux)
                p.CloseSubpath()
                gc.FillPath(p)
            letter(text, tx, ty, key)

        def letter(text, x, y, key):
            gc.SetFont(font, col(key))
            w, h = gc.GetTextExtent(text)
            gc.SetBrush(wx.Brush(bg))
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.DrawRectangle(x - w / 2 - 2, y - h / 2, w + 4, h)
            gc.DrawText(text, x - w / 2, y - h / 2)

        # chip body, tracks, pads, vias
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(body))
        gc.DrawRoundedRectangle(-10, PADS_Y[0] - 34, CHIP_X + 10, PADS_Y[-1] - PADS_Y[0] + 68, 4)
        paths = self._paths()
        for k, pts in enumerate(paths):
            gc.SetPen(wx.Pen(COL_HL if (hl == "width" and k == 0) else COL_CU, TRACK_W))
            p = gc.CreatePath()
            p.MoveToPoint(*pts[0])
            for q in pts[1:]:
                p.AddLineToPoint(*q)
            gc.StrokePath(p)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(COL_CU))
        for py in PADS_Y:
            gc.DrawRoundedRectangle(PAD_X0, py - 6, PAD_X1 - PAD_X0, 12, 3)
        for k, vy in enumerate(VIAS_Y):
            ring = COL_HL if (hl == "via_d" and k == len(VIAS_Y) - 1) else COL_VIA
            gc.SetBrush(wx.Brush(ring))
            X = self.vx(k)
            gc.DrawEllipse(X - VIA_R, vy - VIA_R, 2 * VIA_R, 2 * VIA_R)
            hole = COL_HL if (hl == "via_drill" and k == len(VIAS_Y) - 1) else bg
            gc.SetBrush(wx.Brush(hole))
            gc.DrawEllipse(X - DRILL_R, vy - DRILL_R, 2 * DRILL_R, 2 * DRILL_R)

        # D: pad edge -> via centre
        dash(PAD_X1, PADS_Y[-1] + 7, PAD_X1, Y_D + 5)
        dash(VIA_X, VIAS_Y[-1] + VIA_R, VIA_X, Y_D + 5)
        arrow(PAD_X1, Y_D, VIA_X, Y_D, "dist", "D", (PAD_X1 + VIA_X) / 2.0, Y_D)
        if self.zig:                               # Z: near -> far via column
            xf = self.vx(1)
            dash(xf, VIAS_Y[1] + VIA_R, xf, Y_D + 5)
            arrow(VIA_X, Y_D, xf, Y_D, "zig", "Z", (VIA_X + xf) / 2.0, Y_D - 12)
        last = paths[-1]
        if self.mode == g.ROUTE_OFFSET:
            if self.slack == g.SLACK_PAD:          # B: second bend -> via centre (top track)
                b2 = paths[0][2][0]
                dash(b2, VIAS_Y[0] - 4, b2, Y_B - 5)
                dash(VIA_X, VIAS_Y[0] - VIA_R, VIA_X, Y_B - 5)
                arrow(b2, Y_B, VIA_X, Y_B, "lead_via", "B", (b2 + VIA_X) / 2.0, Y_B)
            else:                                  # A: pad edge -> first bend (bottom track)
                b1 = last[1][0]
                dash(b1, PADS_Y[-1] + 4, b1, Y_A + 5)
                arrow(PAD_X1, Y_A, b1, Y_A, "lead_pad", "A", (PAD_X1 + b1) / 2.0, Y_A - 11)
        # P and S on one vertical line right of the vias
        dash(self.vx(0) + VIA_R, VIAS_Y[0], X_PS + 5, VIAS_Y[0])
        dash(self.vx(1) + VIA_R, VIAS_Y[1], X_PS + 5, VIAS_Y[1])
        dash(PAD_X1 + 4, PADS_Y[1], X_PS + 5, PADS_Y[1])
        arrow(X_PS, VIAS_Y[0], X_PS, VIAS_Y[1], "pitch", "P", X_PS + 14, (VIAS_Y[0] + VIAS_Y[1]) / 2.0)
        arrow(X_PS, VIAS_Y[1], X_PS, PADS_Y[1], "shift", "S", X_PS + 14, (VIAS_Y[1] + PADS_Y[1]) / 2.0)
        # W and via labels with short leaders
        top = paths[0]
        wx0 = (top[0][0] + top[1][0]) / 2.0
        gc.SetPen(wx.Pen(col("width"), 1))
        gc.StrokeLine(wx0, PADS_Y[0] - 3, wx0 + 10, PADS_Y[0] - 22)
        letter("W", wx0 + 16, PADS_Y[0] - 28, "width")
        key = "via_drill" if hl == "via_drill" else "via_d"
        gc.SetPen(wx.Pen(col(key), 1))
        gc.StrokeLine(VIA_X + 6, VIAS_Y[-1] + 7, VIA_X + 16, VIAS_Y[-1] + 24)
        letter("⌀", VIA_X + 22, VIAS_Y[-1] + 30, key)


class LogWindow(wx.Frame):
    """Small live log of the current problems with hints; Copy puts it on the clipboard."""

    def __init__(self, parent):
        super().__init__(parent, title=NAME + " \u2013 log", size=(520, 240),
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

class ViaDialog(wx.Dialog):
    """Modeless while it is open: the PCB Editor underneath stays usable (zoom, pan,
    selecting pads), and the reselect button re-reads what is selected."""

    def __init__(self, frame, defaults, summary, preview_cb, reselect_cb, here):
        # No parent on purpose: GNOME/Mutter attaches child dialogs to the parent window
        # (cannot be moved, parent dimmed). STAY_ON_TOP keeps it above the PCB Editor.
        super().__init__(None, title=NAME,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP | wx.DIALOG_NO_PARENT)
        self.preview_cb = preview_cb
        self.reselect_cb = reselect_cb
        self.result = False
        self.log_win = None
        self.last_msg = ""
        self._loop = None
        self._timer = None
        v = dict(DEFAULTS, **defaults)
        v.update(_last)
        dark = is_dark(self.GetBackgroundColour())
        try:
            self.SetIcon(wx.Icon(os.path.join(here, "via_o_tronic.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass

        box = wx.BoxSizer(wx.VERTICAL)

        # logo, netclass summary and reselect
        head = wx.BoxSizer(wx.HORIZONTAL)
        logo = os.path.join(here, "via_o_tronic_logo_dark.png" if dark else "via_o_tronic_logo.png")
        if os.path.exists(logo):
            head.Add(wx.StaticBitmap(self, bitmap=wx.Bitmap(logo, wx.BITMAP_TYPE_PNG)),
                     0, wx.ALIGN_CENTER_VERTICAL)
        head.AddStretchSpacer()
        self.reselect = wx.Button(self, label="↻", style=wx.BU_EXACTFIT)
        self.reselect.SetToolTip("Use the pads/tracks selected now")
        head.Add(self.reselect, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(head, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)
        self.summary = wx.StaticText(self, label=summary)
        self.summary.SetForegroundColour(wx.Colour(140, 140, 140))
        box.Add(self.summary, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        # direction + mode
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.dirs = []
        fg = self.GetForegroundColour()
        for k, (lab, ang) in enumerate(DIRS):
            b = wx.ToggleButton(self, label="", style=wx.BU_EXACTFIT)
            b.SetBitmap(arrow_bitmap(ang, fg))
            b.SetToolTip("%d°" % ang)
            b.Bind(wx.EVT_TOGGLEBUTTON, lambda e, k=k: self.on_dir(k))
            self.dirs.append(b)
            row.Add(b, 0, wx.RIGHT, 1)
        self.dir = min(v.get("dir", 0), len(DIRS) - 1)
        self.route = wx.Choice(self, choices=[r[0] for r in ROUTES])
        self.route.SetSelection(min(v.get("route", 0), len(ROUTES) - 1))
        self.route.SetToolTip("Track routing")
        self.slack = wx.Choice(self, choices=[s[0] for s in SLACKS])
        self.slack.SetSelection(min(v.get("slack", 0), len(SLACKS) - 1))
        self.slack.SetToolTip("Where the bends line up when the tracks need different lengths")
        row.Add(self.route, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        row.Add(self.slack, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 4)
        box.Add(row, 0, wx.ALL, 8)

        # drawing + values
        self.draw = Drawing(self)
        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=5)
        self.f, self.rows = {}, {}
        FW = 62
        dimc = wx.Colour(110, 190, 255) if dark else wx.Colour(0, 90, 190)

        def sub(key, tip, lbl):
            val = v.get(key, 0)
            t = wx.TextCtrl(self, value="" if key in OPTIONAL and not val else "%g" % val,
                            size=(FW, -1))
            t.SetToolTip(tip)
            if key in OPTIONAL:
                try:
                    t.SetHint("auto")
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, self.on_change)
            self.f[key] = t
            self.rows[key] = (lbl, t)
            for w in (t, lbl):
                w.Bind(wx.EVT_ENTER_WINDOW, lambda e, k=key: (self.draw.set_state(hl=k), e.Skip()))
                w.Bind(wx.EVT_LEAVE_WINDOW, lambda e: (self.draw.set_state(hl=self._focus_key()), e.Skip()))
            t.Bind(wx.EVT_SET_FOCUS, lambda e, k=key: (self.draw.set_state(hl=k), e.Skip()))
            return t

        def field(key, lab, tip, extra=None, tail=None):
            val = v.get(key, 0)
            t = wx.TextCtrl(self, value="" if key in OPTIONAL and not val else "%g" % val,
                            size=(FW, -1))
            t.SetToolTip(tip)
            if key in OPTIONAL:
                try:
                    t.SetHint("auto")
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, self.on_change)
            lbl = wx.StaticText(self, label=lab)
            lbl.SetForegroundColour(dimc)
            lbl.SetFont(lbl.GetFont().Bold())
            fgs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
            if extra is None and tail is None:
                fgs.Add(t, 0)
            else:
                h = wx.BoxSizer(wx.HORIZONTAL)
                if extra is not None:
                    h.Add(extra, 0, wx.RIGHT, 3)
                h.Add(t, 0)
                if tail is not None:          # (label, key, tip) of a second field on this row
                    tl, tk, tt = tail
                    l2 = wx.StaticText(self, label=tl)
                    l2.SetForegroundColour(dimc)
                    l2.SetFont(l2.GetFont().Bold())
                    h.Add(l2, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
                    fgs.Add(h, 0)
                    h.Add(sub(tk, tt, l2), 0)
                else:
                    fgs.Add(h, 0)
            self.f[key] = t
            self.rows[key] = (lbl, t)
            for w in (t, lbl):
                w.Bind(wx.EVT_ENTER_WINDOW, lambda e, k=key: (self.draw.set_state(hl=k), e.Skip()))
                w.Bind(wx.EVT_LEAVE_WINDOW, lambda e: (self.draw.set_state(hl=self._focus_key()), e.Skip()))
            t.Bind(wx.EVT_SET_FOCUS, lambda e, k=key: (self.draw.set_state(hl=k), e.Skip()))
            return t

        self.pitch_mode = wx.Choice(self, choices=PITCHES)
        self.pitch_mode.SetSelection(min(v.get("pitch_mode", 0), len(PITCHES) - 1))
        self.pitch_mode.SetToolTip("Via pitch. Auto = via + clearance (Zigzag: (via + 2 clearance + track) / 2), "
                                   "As pins, Custom")
        self.pitch_mode.Bind(wx.EVT_CHOICE, self.on_change)
        self.layout = wx.Choice(self, choices=VIA_LAYOUTS)
        self.layout.SetSelection(min(v.get("zigzag", 0), 1))
        self.layout.SetToolTip("Row: all vias on one line.\nZigzag: every second via farther by Z, so the "
                               "tracks can keep a tight pitch P")
        self.layout.Bind(wx.EVT_CHOICE, self.on_change)
        vl = wx.StaticText(self, label="Vias")
        fgs.Add(vl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        fgs.Add(self.layout, 0, wx.EXPAND)
        field("dist", "D", "Pad \u2192 via row distance [mm] (how it is measured: More \u2192 D from)")
        field("lead_pad", "A", "Straight lead from the pad edge to the 45\u00b0 bend [mm]")
        field("lead_via", "B", "Straight lead from the 45\u00b0 bend into the via [mm]")
        field("zig", "Z", "Zigzag: how much farther every second via is [mm]; "
                          "empty = smallest that keeps the via clearance at pitch P")
        field("shift", "S", "Sideways shift of the via row [mm], + = to the left of the direction")
        field("pitch", "P", "Via pitch [mm] (Custom)", extra=self.pitch_mode)
        field("width", "W", "Track width [mm], empty = netclass")
        field("via_d", "\u2300", "Via diameter [mm], empty = netclass",
              tail=("\u25cb", "via_drill", "Via drill [mm], empty = netclass"))
        lbl = wx.StaticText(self, label="L")
        lbl.SetFont(lbl.GetFont().Bold())
        lbl.SetForegroundColour(dimc)
        self.length = wx.StaticText(self, label="\u2013")
        self.length.SetToolTip("Track length pad \u2192 via (shortest \u2013 longest)")
        fgs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        fgs.Add(self.length, 0, wx.ALIGN_CENTER_VERTICAL)
        self.fgs = fgs
        mid = wx.BoxSizer(wx.HORIZONTAL)
        mid.Add(self.draw, 0, wx.ALIGN_CENTER_VERTICAL)
        mid.Add(fgs, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(mid, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        # moving the via row by clicking, and the step used by clicks and the mouse wheel
        nud = wx.BoxSizer(wx.HORIZONTAL)
        lab = wx.StaticText(self, label="Move vias")
        lab.SetForegroundColour(wx.Colour(140, 140, 140))
        nud.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.nudge_btn = []
        for ang, tip, key, sign in ((180, "Vias closer (D \u2212 step)", "dist", -1),
                                    (90, "Via row up (S + step)", "shift", 1),
                                    (270, "Via row down (S \u2212 step)", "shift", -1),
                                    (0, "Vias farther (D + step)", "dist", 1)):
            b = wx.BitmapButton(self, bitmap=arrow_bitmap(ang, fg), style=wx.BU_EXACTFIT)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_BUTTON, lambda e, k=key, sg=sign: self.nudge(k, sg))
            nud.Add(b, 0, wx.RIGHT, 1)
            self.nudge_btn.append(b)
        self.step_ch = wx.Choice(self, choices=["%g mm" % st for st in STEPS])
        self.step_ch.SetSelection(min(v.get("nudge", 2), len(STEPS) - 1))
        self.step_ch.SetToolTip("Step for these arrows and for the mouse wheel / \u2191\u2193 on any value.\n"
                                "Shift = \u00d710, Ctrl = \u00f710")
        nud.Add(self.step_ch, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        box.Add(nud, 0, wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 4)

        # rarely used options
        self.more = wx.CollapsiblePane(self, label="More",
                                       style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE)
        mp = self.more.GetPane()

        def choice(opts, key, tip):
            c = wx.Choice(mp, choices=[o[0] for o in opts])
            c.SetSelection(min(v.get(key, 0), len(opts) - 1))
            c.SetToolTip(tip)
            c.Bind(wx.EVT_CHOICE, self.on_change)
            return c

        def num(key, tip, hint=None):
            val = v.get(key, "")
            if isinstance(val, str):
                txt = val
            elif hint and not val:
                txt = ""
            else:
                txt = "%g" % val
            t = wx.TextCtrl(mp, value=txt, size=(64, -1))
            t.SetToolTip(tip)
            if hint:
                try:
                    t.SetHint(hint)
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, self.on_change)
            return t

        self.c = dict(
            line=choice(LINES, "line", "Vias on one common line, or each at its own distance"),
            ref=choice(REFS, "ref", "How D is measured (pad → via)"),
            align=choice(ALIGNS, "align", "Where the via row starts along the pads"),
            angle=num("angle", "Custom direction [deg], overrides the arrows", "°"),
            profile=choice(PROFILES, "profile", "Extra length per track"),
            step=num("step", "Profile step [mm]"),
            custom=num("custom", "Extra lengths [mm], separated with ;"),
            vias_per=num("vias_per", "Vias per pad"),
            group_mode=choice(GROUPS, "group_mode", "Layout of several vias per pad"),
            group_spacing=num("group_spacing", "Via spacing in a group [mm]", "auto"),
            ar_grid=num("ar_grid", "Router grid [mm] (Autoroute and Avoid)"),
            ar_margin=num("ar_margin", "Router search margin [mm] (Autoroute and Avoid)"),
        )
        rows = [("Via line", "line", "D from", "ref", "Align", "align"),
                ("Length", "profile", "Step", "step", "List", "custom"),
                ("Vias/pad", "vias_per", "Layout", "group_mode", "Spacing", "group_spacing"),
                ("Angle", "angle", "Route grid", "ar_grid", "Margin", "ar_margin")]
        grid = wx.FlexGridSizer(cols=6, vgap=4, hgap=4)
        for r in rows:
            for lab, key in zip(r[0::2], r[1::2]):
                if key is None:
                    grid.AddMany([(0, 0), (0, 0)])
                    continue
                grid.Add(wx.StaticText(mp, label=lab), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
                grid.Add(self.c[key], 0, wx.EXPAND)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(grid, 0, wx.TOP | wx.BOTTOM, 4)
        mp.SetSizer(ps)
        self.more.Collapse(not v.get("more", False))
        self.more.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_more)
        box.Add(self.more, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        # preview, status, buttons on one line
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.live = wx.CheckBox(self, label="Preview")
        self.live.SetValue(v.get("live", True))
        self.status = wx.StaticText(self, label="", size=(150, -1),
                                    style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE)
        self.avoid = wx.CheckBox(self, label="Avoid")
        self.avoid.SetValue(v.get("avoid", True))
        self.avoid.SetToolTip("Reroute tracks and move vias that would hit pads, tracks or vias of other nets")
        bottom.Add(self.live, 0, wx.ALIGN_CENTER_VERTICAL)
        bottom.Add(self.avoid, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 8)
        self.warn = wx.Button(self, label="\u26a0 0", style=wx.BU_EXACTFIT)
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

        self.route.Bind(wx.EVT_CHOICE, self.on_change)
        self.slack.Bind(wx.EVT_CHOICE, self.on_change)
        self.live.Bind(wx.EVT_CHECKBOX, self.on_change)
        self.avoid.Bind(wx.EVT_CHECKBOX, self.on_change)
        self.reselect.Bind(wx.EVT_BUTTON, self.on_reselect)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(True), id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(False), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, lambda e: self.finish(False))
        self.nc = dict(v.get("nc") or {})
        for key, t in self.f.items():
            self.spinnable(t, key)
        for key in ("step", "group_spacing", "ar_grid", "ar_margin"):
            self.spinnable(self.c[key], key)
        self.spinnable(self.c["vias_per"], "vias_per", integer=True)
        self.spinnable(self.c["angle"], "angle", angle=True)
        self.update_enabled()

    # -- running without blocking the PCB Editor
    def run(self):
        """Show the dialog and wait in a nested event loop, so the plugin's Run() (and
        with it KiCad's single undo step) lasts until OK/Cancel, while the editor
        window keeps receiving mouse and keyboard events."""
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
        """Last position if known, otherwise the top right corner of the PCB Editor."""
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

    def on_dir(self, k):
        self.dir = k
        self.c["angle"].ChangeValue("")
        self.on_change()

    # -- stepping values with the mouse wheel, arrow keys and the nudge buttons
    def step_size(self, evt=None):
        st = STEPS[self.step_ch.GetSelection()]
        if evt is not None:
            if evt.ShiftDown():
                st *= 10
            elif evt.ControlDown():
                st /= 10.0
        return st

    def bump(self, ctrl, key, n, evt=None, integer=False, angle=False):
        """Add n steps to the value in ctrl (an empty optional field starts from the
        netclass value, an empty angle from the selected arrow)."""
        s = ctrl.GetValue().strip().replace(",", ".")
        try:
            if s in ("", "auto"):
                val = DIRS[self.dir][1] if angle else float(self.nc.get(key, 0.0))
            else:
                val = float(s)
        except ValueError:
            return
        if integer:
            val = max(1, int(round(val)) + n)
            txt = "%d" % val
        elif angle:
            val = (val + n * (45.0 if evt is not None and evt.ShiftDown() else 5.0)) % 360
            txt = "%g" % val
        else:
            st = self.step_size(evt)
            val = round(val + n * st, 4)
            lo = MINIMUM.get(key)
            if lo is not None:
                val = max(lo, val)
            txt = "%g" % val
        ctrl.SetValue(txt)            # fires EVT_TEXT -> preview
        ctrl.SetInsertionPointEnd()

    def spinnable(self, ctrl, key, integer=False, angle=False):
        def wheel(evt):
            if not ctrl.IsEnabled():
                return
            n = 1 if evt.GetWheelRotation() > 0 else -1
            self.bump(ctrl, key, n, evt, integer, angle)

        def keys(evt):
            k = evt.GetKeyCode()
            n = {wx.WXK_UP: 1, wx.WXK_DOWN: -1, wx.WXK_PAGEUP: 10, wx.WXK_PAGEDOWN: -10}.get(k)
            if n is None:
                evt.Skip()
                return
            self.bump(ctrl, key, n, evt, integer, angle)
        ctrl.Bind(wx.EVT_MOUSEWHEEL, wheel)
        ctrl.Bind(wx.EVT_KEY_DOWN, keys)
        tip = ctrl.GetToolTipText() if hasattr(ctrl, "GetToolTipText") else ""
        ctrl.SetToolTip((tip + "\n" if tip else "") + "Scroll or \u2191\u2193 to change")

    def nudge(self, key, sign):
        """Arrow buttons: move the whole via row by one step (D or S)."""
        self.bump(self.f[key], key, sign, _Mods())

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
        custom_angle = bool(self.c["angle"].GetValue().strip())
        for k, b in enumerate(self.dirs):
            b.SetValue(k == self.dir and not custom_angle)
        route = ROUTES[self.route.GetSelection()][1]
        slack = SLACKS[self.slack.GetSelection()][1]
        off = route == g.ROUTE_OFFSET
        zig = self.layout.GetSelection() == 1
        self.draw.set_state(mode=route, slack=slack, zig=zig)
        self.slack.Enable(off)
        shown = {"lead_pad": off and slack == g.SLACK_VIA, "lead_via": off and slack == g.SLACK_PAD,
                 "zig": zig}
        changed = False
        for key, show in shown.items():
            for w in self.rows[key]:
                if w.IsShown() != show:
                    w.Show(show)
                    changed = True
        if changed:
            self.Layout()
        self.f["pitch"].Enable(self.pitch_mode.GetSelection() == 2)
        self.c["align"].Enable(self.pitch_mode.GetSelection() != 1)
        auto = route == g.ROUTE_AUTO or self.avoid.GetValue()
        self.c["ar_grid"].Enable(auto)
        self.c["ar_margin"].Enable(auto)
        prof = self.c["profile"].GetSelection()
        self.c["step"].Enable(prof not in (0, len(PROFILES) - 1))
        self.c["custom"].Enable(prof == len(PROFILES) - 1)
        try:
            many = int(float(self.c["vias_per"].GetValue().replace(",", "."))) > 1
        except ValueError:
            many = True
        self.c["group_mode"].Enable(many)
        self.c["group_spacing"].Enable(many)

    def on_change(self, _evt=None):
        self.update_enabled()
        if self._timer is not None:
            self._timer.Stop()
        self._timer = wx.CallLater(getattr(self, "_delay", 250), self.refresh_preview)

    def on_reselect(self, _evt=None):
        msg = self.reselect_cb()
        if msg is not None:
            self.summary.SetLabel(msg)
        self.refresh_preview()

    def refresh_preview(self):
        if not self.IsShown():
            return
        try:
            v = self.values()
        except ValueError as e:
            self.set_status("Invalid value" + (": %s" % e if str(e) else ""))
            return
        wx.BeginBusyCursor()
        t0 = time.time()
        try:
            msg = self.preview_cb(v if self.live.GetValue() else None)
        finally:
            wx.EndBusyCursor()
            # KiCad 9/10 rebuild the whole view per change: wait about as long as it took
            self._delay = int(max(250, min(700, (time.time() - t0) * 1200)))
        self.set_status(msg)

    def set_status(self, msg):
        """Info line on the dialog; problems (lines with a hint) behind the warning button."""
        self.last_msg = msg or ""
        lines = [l for l in self.last_msg.split("\n") if l.strip()]
        warn = [l for l in lines if "\u2192" in l]
        info = [l for l in lines if "\u2192" not in l]
        text = re.sub(r",? ?L [0-9.\u2013]+ mm", "", info[0]) if info else ""
        self.status.SetLabel(text)
        self.status.SetToolTip("\n".join(info))
        if warn:
            self.warn.SetLabel("\u26a0 %d" % len(warn))
        if self.warn.IsShown() != bool(warn):
            self.warn.Show(bool(warn))
            self.Layout()
        m = re.search(r"L ([0-9.]+(?:\u2013[0-9.]+)?) mm", self.last_msg)
        self.length.SetLabel(m.group(1) + " mm" if m else "\u2013")
        if self.log_win:
            self.log_win.update(self.log_text())

    def log_text(self):
        lines = [l for l in self.last_msg.split("\n") if l.strip()]
        warn = [l for l in lines if "\u2192" in l]
        info = [l for l in lines if "\u2192" not in l]
        out = info[:1] + [""]
        out += ["\u26a0 " + w for w in warn] if warn else ["No problems."]
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
            if optional and s in ("", "auto"):
                return 0.0
            return float(s)
        fc = lambda k, opt=False: f(self.c[k], opt)
        fp = lambda k: f(self.f[k], k in OPTIONAL)
        sel = lambda k: self.c[k].GetSelection()
        ang_txt = self.c["angle"].GetValue().strip().replace(",", ".")
        raw = dict(dir=self.dir, angle=ang_txt, ref=sel("ref"), line=sel("line"), align=sel("align"),
                   route=self.route.GetSelection(), slack=self.slack.GetSelection(),
                   pitch_mode=self.pitch_mode.GetSelection(),
                   dist=fp("dist"), pitch=fp("pitch"),
                   lead_pad=fp("lead_pad"), lead_via=fp("lead_via"), shift=fp("shift"),
                   via_d=fp("via_d"), via_drill=fp("via_drill"), width=fp("width"),
                   profile=sel("profile"), step=fc("step"),
                   vias_per=int(fc("vias_per")), group_mode=sel("group_mode"),
                   group_spacing=fc("group_spacing", True),
                   ar_grid=fc("ar_grid"), ar_margin=fc("ar_margin"),
                   custom=self.c["custom"].GetValue(),
                   live=self.live.GetValue(), nudge=self.step_ch.GetSelection(),
                   avoid=self.avoid.GetValue(), zigzag=self.layout.GetSelection(),
                   zig=fp("zig"))
        if raw["vias_per"] < 1 or raw["group_spacing"] < 0:
            raise ValueError("vias/pad")
        if raw["ar_grid"] < 0.01 or raw["ar_margin"] < 0:
            raise ValueError("route grid")
        if raw["zig"] < 0:
            raise ValueError("Z")
        if raw["lead_pad"] < 0 or raw["lead_via"] < 0:
            raise ValueError("A, B")
        if min(raw["via_d"], raw["via_drill"], raw["width"]) < 0:
            raise ValueError("sizes")
        if raw["via_d"] and raw["via_drill"] and raw["via_drill"] >= raw["via_d"]:
            raise ValueError("drill ≥ via")
        angle = float(ang_txt) if ang_txt else DIRS[raw["dir"]][1]
        custom = [float(x) for x in raw["custom"].replace(",", ".").replace(";", " ").split()]
        _last.update(raw)
        return dict(raw, angle=angle, ref=REFS[raw["ref"]][1], line=LINES[raw["line"]][1],
                    align=ALIGNS[raw["align"]][1], route=ROUTES[raw["route"]][1],
                    slack_id=SLACKS[raw["slack"]][1],
                    profile_id=PROFILES[raw["profile"]][1], custom_list=custom)
