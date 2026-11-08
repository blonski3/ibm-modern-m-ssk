# Dialog of the via-o-tronic plugin. Built around the common case (fan out a row of
# aQFN/QFN pins to a row of vias): direction arrows and routing mode on top, the main
# dimensions as fields on a small pictogram, rarely used options folded under "More".
# Colours follow the system theme. No pcbnew import here, so it runs without KiCad.

import math
import os

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
                dist=0.3, lead_pad=0.3, lead_via=0.5, shift=0.0, pitch=0.8,
                via_d=0, via_drill=0, width=0, more=False, live=True, nudge=2, nc={})
STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]      # mm per wheel notch / arrow click
# field -> minimum value when stepping (None = no limit)
MINIMUM = dict(lead_pad=0.0, lead_via=0.0, dist=0.0, pitch=0.05, shift=None, width=0.05,
               via_d=0.1, via_drill=0.05, step=None, group_spacing=0.0, ar_grid=0.01,
               ar_margin=0.0)

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

# picture coordinates (px), drawn for the direction "Right"
PADS_Y = (120, 160, 200)
PAD_X0, PAD_X1 = 18, 42
VIAS_Y = (70, 115, 160)            # via pitch 45, row shifted up (S) by 45
VIA_X = 296
BEND1_X = 80
VIA_R, DRILL_R = 10, 4.5
TRACK_W = 6
X_DIM = 322                        # vertical P/S dimension line
X_FLD = 350                        # field column right of the vias
FIELD_W = 58
PIC_W, PIC_H = X_FLD + 96, 250

COL_CU = wx.Colour(200, 52, 52)
COL_VIA = wx.Colour(226, 186, 40)


class Pictogram(wx.Panel):
    """Fanout drawing with the editable dimensions placed on it."""

    # key -> (label, x of the field, y of its centre, tooltip)
    FIELDS = {
        "lead_via": ("B", 186, 20, "B: straight lead into the via centre [mm]"),
        "width": ("W", 26, 72, "Track width [mm], empty = netclass"),
        "pitch": ("", X_FLD, 110, "P: via pitch [mm]"),
        "shift": ("S", X_FLD, 150, "S: shift of the via row [mm], + = to the left of the direction"),
        "via_d": ("⌀", X_FLD, 192, "Via diameter [mm], empty = netclass"),
        "via_drill": ("○", X_FLD, 230, "Via drill [mm], empty = netclass"),
        "lead_pad": ("A", 100, 230, "A: straight lead from the pad edge [mm]"),
        "dist": ("D", 186, 230, "D: pad to via row [mm] (measured as set in More)"),
    }
    OPTIONAL = ("width", "via_d", "via_drill")   # empty = netclass

    def __init__(self, parent, v, on_change):
        super().__init__(parent, size=(PIC_W, PIC_H))
        self.SetMinSize((PIC_W, PIC_H))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.mode = g.ROUTE_OFFSET
        self.ctrl = {}
        for key, (_lab, x, yc, tip) in self.FIELDS.items():
            val = v.get(key, 0)
            txt = "" if key in self.OPTIONAL and not val else "%g" % val
            t = wx.TextCtrl(self, value=txt, size=(FIELD_W, -1))
            t.SetPosition((x, int(yc - t.GetBestSize().height / 2)))
            t.SetToolTip(tip)
            if key in self.OPTIONAL:
                try:
                    t.SetHint("auto")
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, on_change)
            self.ctrl[key] = t
        self.pitch_mode = wx.Choice(self, choices=PITCHES, size=(FIELD_W + 28, -1))
        self.pitch_mode.SetPosition((X_FLD, int(70 - self.pitch_mode.GetBestSize().height / 2)))
        self.pitch_mode.SetSelection(min(v.get("pitch_mode", 0), len(PITCHES) - 1))
        self.pitch_mode.SetToolTip("P: via pitch. Auto = via + clearance")
        self.pitch_mode.Bind(wx.EVT_CHOICE, on_change)
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def set_mode(self, mode):
        self.mode = mode
        off = mode == g.ROUTE_OFFSET
        self.ctrl["lead_pad"].Show(off)
        self.ctrl["lead_via"].Show(off)
        self.ctrl["dist"].Show(not off)
        self.ctrl["pitch"].Enable(self.pitch_mode.GetSelection() == 2)
        self.Refresh()

    @staticmethod
    def _arrow(gc, x0, y0, x1, y1, col):
        gc.SetPen(wx.Pen(col, 1))
        gc.StrokeLine(x0, y0, x1, y1)
        gc.SetBrush(wx.Brush(col))
        for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
            L = math.hypot(bx - ax, by - ay) or 1
            ux, uy = (bx - ax) / L, (by - ay) / L
            p = gc.CreatePath()
            p.MoveToPoint(ax, ay)
            p.AddLineToPoint(ax + 6 * ux - 2.5 * uy, ay + 6 * uy + 2.5 * ux)
            p.AddLineToPoint(ax + 6 * ux + 2.5 * uy, ay + 6 * uy - 2.5 * ux)
            p.CloseSubpath()
            gc.FillPath(p)

    def _paths(self):
        out = []
        for k, (py, vy) in enumerate(zip(PADS_Y, VIAS_Y)):
            dl = py - vy
            s = (PAD_X1 - 12, py)
            if self.mode == g.ROUTE_OFFSET:
                out.append([s, (BEND1_X, py), (BEND1_X + dl, vy), (VIA_X, vy)])
            elif self.mode == g.ROUTE_45_PAD:
                out.append([s, (PAD_X1, py), (PAD_X1 + dl, vy), (VIA_X, vy)])
            elif self.mode == g.ROUTE_STRAIGHT:
                out.append([s, (VIA_X, vy)])
            elif self.mode == g.ROUTE_AUTO:
                m = 150 + 20 * k
                out.append([s, (m, py), (m + dl, vy), (VIA_X, vy)])
            else:
                out.append([s, (VIA_X - dl, py), (VIA_X, vy)])
        return out

    def on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        bg = self.GetParent().GetBackgroundColour()
        dark = is_dark(bg)
        dim = wx.Colour(110, 190, 255) if dark else wx.Colour(0, 90, 190)
        ext = wx.Colour(110, 110, 110) if dark else wx.Colour(170, 170, 170)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        off = self.mode == g.ROUTE_OFFSET

        def dash(x0, y0, x1, y1):
            gc.SetPen(wx.Pen(ext, 1, wx.PENSTYLE_SHORT_DASH))
            gc.StrokeLine(x0, y0, x1, y1)

        paths = self._paths()
        gc.SetPen(wx.Pen(COL_CU, TRACK_W))
        for pts in paths:
            p = gc.CreatePath()
            p.MoveToPoint(*pts[0])
            for q in pts[1:]:
                p.AddLineToPoint(*q)
            gc.StrokePath(p)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(COL_CU))
        for py in PADS_Y:
            gc.DrawRoundedRectangle(PAD_X0, py - 7, PAD_X1 - PAD_X0, 14, 4)
        for vy in VIAS_Y:
            gc.SetBrush(wx.Brush(COL_VIA))
            gc.DrawEllipse(VIA_X - VIA_R, vy - VIA_R, 2 * VIA_R, 2 * VIA_R)
            gc.SetBrush(wx.Brush(bg))
            gc.DrawEllipse(VIA_X - DRILL_R, vy - DRILL_R, 2 * DRILL_R, 2 * DRILL_R)

        y_low = 230
        if off:
            dash(PAD_X1, PADS_Y[-1] + 8, PAD_X1, y_low + 5)
            dash(BEND1_X, PADS_Y[-1] + 4, BEND1_X, y_low + 5)
            self._arrow(gc, PAD_X1, y_low, BEND1_X, y_low, dim)
            b2 = BEND1_X + PADS_Y[0] - VIAS_Y[0]
            y_top = 42
            dash(b2, VIAS_Y[0] - 4, b2, y_top - 5)
            dash(VIA_X, VIAS_Y[0] - VIA_R, VIA_X, y_top - 5)
            self._arrow(gc, b2, y_top, VIA_X, y_top, dim)
        else:
            dash(PAD_X1, PADS_Y[-1] + 8, PAD_X1, y_low + 5)
            dash(VIA_X, VIAS_Y[-1] + VIA_R, VIA_X, y_low + 5)
            self._arrow(gc, PAD_X1, y_low, 170, y_low, dim)
            dash(170, y_low, VIA_X, y_low)
        dash(VIA_X + VIA_R, VIAS_Y[0], X_DIM + 5, VIAS_Y[0])
        dash(VIA_X + VIA_R, VIAS_Y[1], X_DIM + 5, VIAS_Y[1])
        dash(PAD_X1 + 4, PADS_Y[1], X_DIM + 5, PADS_Y[1])
        self._arrow(gc, X_DIM, VIAS_Y[0], X_DIM, VIAS_Y[1], dim)
        self._arrow(gc, X_DIM, VIAS_Y[1], X_DIM, PADS_Y[1], dim)

        gc.SetPen(wx.Pen(dim, 1))
        w = self.ctrl["width"]
        wx_, wy_ = w.GetPosition()
        gc.StrokeLine(PAD_X1 + 22, PADS_Y[0] - 3, wx_ + 14, wy_ + w.GetSize().height)
        for key, r in (("via_d", VIA_R - 1), ("via_drill", DRILL_R - 1)):
            f = self.ctrl[key]
            fx, fy = f.GetPosition()
            a = math.radians(50)
            gc.StrokeLine(VIA_X + r * math.cos(a), VIAS_Y[-1] + r * math.sin(a),
                          fx - 16, fy + f.GetSize().height / 2.0)

        gc.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD), dim)

        def label(ctrl, lab):
            if not ctrl.IsShown():
                return
            x, y = ctrl.GetPosition()
            tw, th = gc.GetTextExtent(lab)
            gc.DrawText(lab, x - tw - 4, y + (ctrl.GetSize().height - th) / 2.0)
        for key, (lab, _x, _y, _tip) in self.FIELDS.items():
            if lab:
                label(self.ctrl[key], lab)
        label(self.pitch_mode, "P")


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

        self.pic = Pictogram(self, v, self.on_change)
        box.Add(self.pic, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 8)

        # moving the via row by clicking, and the step used by clicks and the mouse wheel
        nud = wx.BoxSizer(wx.HORIZONTAL)
        lab = wx.StaticText(self, label="Move vias")
        lab.SetForegroundColour(wx.Colour(140, 140, 140))
        nud.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.nudge_btn = []
        for ang, tip, key, sign in ((180, "Vias closer (B / D \u2212 step)", "far", -1),
                                    (90, "Via row up (S + step)", "shift", 1),
                                    (270, "Via row down (S \u2212 step)", "shift", -1),
                                    (0, "Vias farther (B / D + step)", "far", 1)):
            b = wx.BitmapButton(self, bitmap=arrow_bitmap(ang, fg), style=wx.BU_EXACTFIT)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_BUTTON, lambda e, k=key, sg=sign: self.nudge(k, sg))
            nud.Add(b, 0, wx.RIGHT, 1)
            self.nudge_btn.append(b)
        self.step_ch = wx.Choice(self, choices=["%g mm" % st for st in STEPS])
        self.step_ch.SetSelection(min(v.get("nudge", 2), len(STEPS) - 1))
        self.step_ch.SetToolTip("Step for the arrows and for the mouse wheel / \u2191\u2193 keys on any value.\n"
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
            ar_grid=num("ar_grid", "Autoroute grid [mm]"),
            ar_margin=num("ar_margin", "Autoroute search margin [mm]"),
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
        bottom.Add(self.live, 0, wx.ALIGN_CENTER_VERTICAL)
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
        self.reselect.Bind(wx.EVT_BUTTON, self.on_reselect)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(True), id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(False), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, lambda e: self.finish(False))
        self.nc = dict(v.get("nc") or {})
        for key, t in self.pic.ctrl.items():
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

    def nudge(self, what, sign):
        """Arrow buttons: move the whole via row by one step."""
        if what == "shift":
            ctrl, key = self.pic.ctrl["shift"], "shift"
        elif ROUTES[self.route.GetSelection()][1] == g.ROUTE_OFFSET:
            ctrl, key = self.pic.ctrl["lead_via"], "lead_via"
        else:
            ctrl, key = self.pic.ctrl["dist"], "dist"
        self.bump(ctrl, key, sign, _Mods())

    def on_more(self, _evt=None):
        _last["more"] = self.more.IsExpanded()
        self.Layout()
        self.Fit()

    def update_enabled(self):
        custom_angle = bool(self.c["angle"].GetValue().strip())
        for k, b in enumerate(self.dirs):
            b.SetValue(k == self.dir and not custom_angle)
        route = ROUTES[self.route.GetSelection()][1]
        self.pic.set_mode(route)
        self.slack.Enable(route == g.ROUTE_OFFSET)
        self.c["ref"].Enable(route != g.ROUTE_OFFSET)
        self.c["align"].Enable(self.pic.pitch_mode.GetSelection() != 1)
        auto = route == g.ROUTE_AUTO
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
        self._timer = wx.CallLater(250, self.refresh_preview)

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
        try:
            msg = self.preview_cb(v if self.live.GetValue() else None)
        finally:
            wx.EndBusyCursor()
        self.set_status(msg)

    def set_status(self, msg):
        """Short text on the dialog (warning count if any), the full text in the tooltip."""
        lines = [l for l in (msg or "").split("\n") if l.strip()]
        warn = [l for l in lines if "Item" in l or "too close" in l]
        if warn:
            text = "⚠ %d warning%s" % (len(warn), "s" if len(warn) > 1 else "")
        else:
            text = lines[0] if lines else ""
        self.status.SetLabel(text)
        self.status.SetToolTip("\n".join(lines))

    def values(self):
        def f(ctrl, optional=False):
            s = ctrl.GetValue().strip().replace(",", ".")
            if optional and s in ("", "auto"):
                return 0.0
            return float(s)
        fc = lambda k, opt=False: f(self.c[k], opt)
        fp = lambda k: f(self.pic.ctrl[k], k in Pictogram.OPTIONAL)
        sel = lambda k: self.c[k].GetSelection()
        ang_txt = self.c["angle"].GetValue().strip().replace(",", ".")
        raw = dict(dir=self.dir, angle=ang_txt, ref=sel("ref"), line=sel("line"), align=sel("align"),
                   route=self.route.GetSelection(), slack=self.slack.GetSelection(),
                   pitch_mode=self.pic.pitch_mode.GetSelection(),
                   dist=fp("dist"), pitch=fp("pitch"),
                   lead_pad=fp("lead_pad"), lead_via=fp("lead_via"), shift=fp("shift"),
                   via_d=fp("via_d"), via_drill=fp("via_drill"), width=fp("width"),
                   profile=sel("profile"), step=fc("step"),
                   vias_per=int(fc("vias_per")), group_mode=sel("group_mode"),
                   group_spacing=fc("group_spacing", True),
                   ar_grid=fc("ar_grid"), ar_margin=fc("ar_margin"),
                   custom=self.c["custom"].GetValue(),
                   live=self.live.GetValue(), nudge=self.step_ch.GetSelection())
        if raw["vias_per"] < 1 or raw["group_spacing"] < 0:
            raise ValueError("vias/pad")
        if raw["ar_grid"] < 0.01 or raw["ar_margin"] < 0:
            raise ValueError("route grid")
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
