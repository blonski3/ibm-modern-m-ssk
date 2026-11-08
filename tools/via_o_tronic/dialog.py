# Dialog of the via-o-tronic plugin: a pictogram with every editable dimension drawn on
# it, a short list of the remaining options below, and the Win95-style logo on top.
# No pcbnew import here, so the window can be opened and tested without KiCad.

import math
import os

import wx

from . import geometry as g

NAME = "via-o-tronic"
VERSION = "2.0"

DIRS = [("Right", 0), ("Up-right 45", 45), ("Up", 90), ("Up-left 45", 135),
        ("Left", 180), ("Down-left 45", 225), ("Down", 270), ("Down-right 45", 315)]
ALIGNS = [("Centre of selection", g.ALIGN_CENTER), ("From first item", g.ALIGN_FIRST),
          ("From last item", g.ALIGN_LAST)]
REFS = [("Pad edge to via centre", g.REF_EDGE_CENTER),
        ("Pad edge to via edge (copper gap)", g.REF_EDGE),
        ("Pad centre to via centre", g.REF_CENTER)]
LINES = [("Common line (from farthest item)", g.LINE_COMMON), ("Separate for each item", g.LINE_EACH)]
ROUTES = [("Lead / 45 deg / lead (A, B)", g.ROUTE_OFFSET),
          ("45 deg bend at via", g.ROUTE_45_VIA), ("45 deg bend at pad", g.ROUTE_45_PAD),
          ("Straight (any angle)", g.ROUTE_STRAIGHT),
          ("Autoroute (avoid pads, tracks, vias, board edge)", g.ROUTE_AUTO)]
SLACKS = [("Lead into via (B), bends line up at the pads", g.SLACK_VIA),
          ("Lead from pad (A), bends line up at the vias", g.SLACK_PAD)]
PITCHES = ["Auto", "As pins", "Custom"]
PROFILES = [("Constant", g.PROF_CONST), ("Increasing", g.PROF_INC), ("Decreasing", g.PROF_DEC),
            ("V: centre shortest", g.PROF_V), ("A: centre longest", g.PROF_A),
            ("Zigzag (every 2nd)", g.PROF_ZIGZAG), ("Custom list", g.PROF_CUSTOM)]
GROUPS = [("Side by side (across)", g.GROUP_ACROSS), ("One behind another (along)", g.GROUP_ALONG),
          ("Grid, 2 rows", g.GROUP_GRID)]

DEFAULTS = dict(dir=0, angle=0, ref=0, line=0, align=0, route=0, slack=0, pitch_mode=0,
                profile=0, step=0.5, custom="0; 0.5; 1.0",
                vias_per=1, group_mode=0, group_spacing=0, ar_grid=0.05, ar_margin=1.5,
                dist=0.3, lead_pad=0.3, lead_via=0.5, shift=0.0, pitch=0.8,
                via_d=0, via_drill=0, width=0)

_last = {}   # last used settings, kept for this KiCad session


# ---------------------------------------------------------------- pictogram

# picture coordinates (px) - drawn for the direction "Right"
PADS_Y = (170, 235, 300)
PAD_X0, PAD_X1 = 40, 80            # pad outline, the edge faces the vias at x = 80
VIAS_Y = (95, 170, 245)            # via row: pitch 75, shifted up (S) by 65
VIA_X = 470
BEND1_X = 140                      # end of lead A
VIA_R, DRILL_R = 15, 7
TRACK_W = 9
PIC_W, PIC_H = 700, 420
FIELD_W = 80
X_DIM = 530                        # vertical dimension line for P and S
X_FLD = 560                        # column of fields right of the vias

COL_BG = wx.Colour(0, 16, 35)
COL_CU = wx.Colour(200, 52, 52)
COL_VIA = wx.Colour(236, 200, 60)
COL_DIM = wx.Colour(120, 220, 255)
COL_TXT = wx.Colour(235, 235, 235)
COL_EXT = wx.Colour(90, 110, 140)


class Pictogram(wx.Panel):
    """Fanout drawing with editable dimension fields placed on it."""

    # key -> (label, x of the field's left edge, y of its centre, tooltip)
    FIELDS = {
        "lead_pad": ("A", 70, 378, "A: straight lead from the pad edge to the 45 deg jog [mm]"),
        "lead_via": ("B", 302, 36, "B: straight lead from the 45 deg jog into the via centre [mm]\n"
                                   "(on a common via line the other tracks get more, see 'Extra length goes to')"),
        "dist": ("D", 235, 378, "D: distance from the pad to the via row [mm] (see 'D measured')"),
        "pitch": ("", X_FLD, 150, "P: via pitch [mm] (Custom)"),
        "shift": ("S", X_FLD, 205, "S: sideways shift of the via row [mm], pad row centre to via row centre;\n"
                                   "+ = to the left of the direction (for Right: up)"),
        "via_d": ("⌀", X_FLD, 275, "Via diameter [mm]; empty = from the netclass of each net"),
        "via_drill": ("drill", X_FLD, 318, "Via drill [mm]; empty = from the netclass of each net"),
        "width": ("W", 112, 110, "W: track width [mm]; empty = from the netclass of each net"),
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
            h = t.GetBestSize().height
            t.SetPosition((x, int(yc - h / 2)))
            t.SetToolTip(tip)
            if key in self.OPTIONAL:
                try:
                    t.SetHint("auto")
                except Exception:
                    pass
            t.Bind(wx.EVT_TEXT, on_change)
            self.ctrl[key] = t
        self.pitch_mode = wx.Choice(self, choices=PITCHES, size=(FIELD_W + 40, -1))
        h = self.pitch_mode.GetBestSize().height
        self.pitch_mode.SetPosition((X_FLD, int(110 - h / 2)))
        self.pitch_mode.SetSelection(min(v.get("pitch_mode", 0), len(PITCHES) - 1))
        self.pitch_mode.SetToolTip("P: via pitch along the row. Auto = via + clearance from the netclass")
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

    # -- drawing helpers
    @staticmethod
    def _arrow(gc, x0, y0, x1, y1, col=COL_DIM):
        gc.SetPen(wx.Pen(col, 1))
        gc.StrokeLine(x0, y0, x1, y1)
        gc.SetBrush(wx.Brush(col))
        for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
            L = math.hypot(bx - ax, by - ay) or 1
            ux, uy = (bx - ax) / L, (by - ay) / L
            p = gc.CreatePath()
            p.MoveToPoint(ax, ay)
            p.AddLineToPoint(ax + 8 * ux - 3.5 * uy, ay + 8 * uy + 3.5 * ux)
            p.AddLineToPoint(ax + 8 * ux + 3.5 * uy, ay + 8 * uy - 3.5 * ux)
            p.CloseSubpath()
            gc.FillPath(p)

    @staticmethod
    def _dash(gc, x0, y0, x1, y1):
        gc.SetPen(wx.Pen(COL_EXT, 1, wx.PENSTYLE_SHORT_DASH))
        gc.StrokeLine(x0, y0, x1, y1)

    def _paths(self):
        """Track polylines for the current mode (picture coordinates)."""
        out = []
        for k, (py, vy) in enumerate(zip(PADS_Y, VIAS_Y)):
            dl = py - vy
            s = (PAD_X1 - 20, py)
            if self.mode == g.ROUTE_OFFSET:
                out.append([s, (BEND1_X, py), (BEND1_X + dl, vy), (VIA_X, vy)])
            elif self.mode == g.ROUTE_45_PAD:
                out.append([s, (PAD_X1, py), (PAD_X1 + dl, vy), (VIA_X, vy)])
            elif self.mode == g.ROUTE_STRAIGHT:
                out.append([s, (VIA_X, vy)])
            elif self.mode == g.ROUTE_AUTO:
                m = 250 + 30 * k
                out.append([s, (m, py), (m + dl, vy), (VIA_X, vy)])
            else:   # 45 deg bend at the via
                out.append([s, (VIA_X - dl, py), (VIA_X, vy)])
        return out

    def _label(self, gc, key, lab):
        t = self.ctrl[key]
        if not lab or not t.IsShown():
            return
        x, y = t.GetPosition()
        h = t.GetSize().height
        w, th = gc.GetTextExtent(lab)
        gc.DrawText(lab, x - w - 6, y + (h - th) / 2.0)

    def on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(COL_BG))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        bold = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        small = wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        off = self.mode == g.ROUTE_OFFSET

        # tracks, pads, vias
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
            gc.DrawRoundedRectangle(PAD_X0, py - 11, PAD_X1 - PAD_X0, 22, 6)
        for vy in VIAS_Y:
            gc.SetBrush(wx.Brush(COL_VIA))
            gc.DrawEllipse(VIA_X - VIA_R, vy - VIA_R, 2 * VIA_R, 2 * VIA_R)
            gc.SetBrush(wx.Brush(COL_BG))
            gc.DrawEllipse(VIA_X - DRILL_R, vy - DRILL_R, 2 * DRILL_R, 2 * DRILL_R)

        gc.SetFont(small, COL_EXT)
        gc.DrawText("drawn for direction: Right", 8, 6)
        gc.DrawText("pads", PAD_X0, PADS_Y[-1] + 16)

        # A / D along the bottom, B along the top
        y_low = PADS_Y[-1] + 45
        if off:
            self._dash(gc, PAD_X1, PADS_Y[-1] + 12, PAD_X1, y_low + 6)
            self._dash(gc, BEND1_X, PADS_Y[-1] + 6, BEND1_X, y_low + 6)
            self._arrow(gc, PAD_X1, y_low, BEND1_X, y_low)
            b2 = BEND1_X + PADS_Y[0] - VIAS_Y[0]
            y_top = VIAS_Y[0] - 30
            self._dash(gc, b2, VIAS_Y[0] - 6, b2, y_top - 6)
            self._dash(gc, VIA_X, VIAS_Y[0] - VIA_R, VIA_X, y_top - 6)
            self._arrow(gc, b2, y_top, VIA_X, y_top)
        else:
            self._dash(gc, PAD_X1, PADS_Y[-1] + 12, PAD_X1, y_low + 6)
            self._dash(gc, VIA_X, VIAS_Y[-1] + VIA_R, VIA_X, y_low + 6)
            self._arrow(gc, PAD_X1, y_low, VIA_X, y_low)
        # P and S as a chain on one vertical line
        self._dash(gc, VIA_X + VIA_R, VIAS_Y[0], X_DIM + 8, VIAS_Y[0])
        self._dash(gc, VIA_X + VIA_R, VIAS_Y[1], X_DIM + 8, VIAS_Y[1])
        self._dash(gc, PAD_X1 + 4, PADS_Y[1], X_DIM + 8, PADS_Y[1])
        self._arrow(gc, X_DIM, VIAS_Y[0], X_DIM, VIAS_Y[1])
        self._arrow(gc, X_DIM, VIAS_Y[1], X_DIM, PADS_Y[1])
        # W callout from the first (horizontal) part of the top track, via callouts
        wx_, wy_ = self.ctrl["width"].GetPosition()
        wh = self.ctrl["width"].GetSize().height
        gc.SetPen(wx.Pen(COL_DIM, 1))
        gc.StrokeLine(PAD_X1 + 30, PADS_Y[0] - 4, wx_ + 20, wy_ + wh)
        for key, r in (("via_d", VIA_R - 2), ("via_drill", DRILL_R - 2)):
            fx, fy = self.ctrl[key].GetPosition()
            fh = self.ctrl[key].GetSize().height
            a = math.radians(40)
            gc.StrokeLine(VIA_X + r * math.cos(a), VIAS_Y[-1] + r * math.sin(a),
                          fx - (40 if key == "via_drill" else 22), fy + fh / 2.0)

        gc.SetFont(bold, COL_DIM)
        for key, (lab, _x, _y, _tip) in self.FIELDS.items():
            self._label(gc, key, lab)
        px, py = self.pitch_mode.GetPosition()
        ph = self.pitch_mode.GetSize().height
        w, th = gc.GetTextExtent("P")
        gc.DrawText("P", px - w - 6, py + (ph - th) / 2.0)
        gc.SetFont(small, COL_EXT)
        sx, sy = self.ctrl["shift"].GetPosition()
        gc.DrawText("+ = up", sx + FIELD_W + 6, sy + 8)
        dx, dy = self.ctrl["via_drill"].GetPosition()
        gc.DrawText("empty = from netclass", dx, dy + self.ctrl["via_drill"].GetSize().height + 4)


class LogoPanel(wx.Panel):
    """Win95-style banner: grey 3D panel across the whole dialog with the logo on it."""

    def __init__(self, parent, path):
        self.bmp = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)
        super().__init__(parent, size=(-1, self.bmp.GetHeight() + 4))
        self.SetMinSize((self.bmp.GetWidth(), self.bmp.GetHeight() + 4))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda e: (self.Refresh(), e.Skip()))

    def on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()
        dc.SetBackground(wx.Brush(wx.Colour(192, 192, 192)))
        dc.Clear()
        dc.DrawBitmap(self.bmp, 2, 2, True)
        for col, y in ((wx.WHITE, 0), (wx.Colour(223, 223, 223), 1),
                       (wx.Colour(128, 128, 128), h - 2), (wx.BLACK, h - 1)):
            dc.SetPen(wx.Pen(col))
            dc.DrawLine(0, y, w, y)


# ---------------------------------------------------------------- dialog

class ViaDialog(wx.Dialog):
    """Modeless while it is open: the PCB Editor underneath stays usable (zoom, pan,
    selecting pads), and "Use current selection" re-reads what is selected."""

    def __init__(self, frame, defaults, summary, preview_cb, reselect_cb, here):
        # No parent on purpose: GNOME/Mutter attaches child dialogs to the parent window
        # (cannot be moved, parent dimmed). A parentless dialog stays movable and the
        # board stays visible; STAY_ON_TOP keeps it above the PCB Editor.
        super().__init__(None, title=NAME,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
                         | wx.STAY_ON_TOP | wx.DIALOG_NO_PARENT)
        self.preview_cb = preview_cb
        self.reselect_cb = reselect_cb
        self.result = False
        self._loop = None
        self._timer = None
        v = dict(DEFAULTS, **defaults)
        v.update(_last)
        try:
            self.SetIcon(wx.Icon(os.path.join(here, "via_o_tronic.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass

        box = wx.BoxSizer(wx.VERTICAL)
        logo = os.path.join(here, "via_o_tronic_logo.png")
        if os.path.exists(logo):
            box.Add(LogoPanel(self, logo), 0, wx.EXPAND)

        self.summary = wx.StaticText(self, label="Netclasses of the selection:\n" + summary)
        self.reselect = wx.Button(self, label="Use current selection")
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.summary, 1, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.reselect, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box.Add(top, 0, wx.ALL | wx.EXPAND, 10)

        self.pic = Pictogram(self, v, self.on_change)
        box.Add(self.pic, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, 10)

        # remaining options: two label/control pairs per row
        def choice(opts, key):
            c = wx.Choice(self, choices=[o if isinstance(o, str) else o[0] for o in opts])
            c.SetSelection(min(v.get(key, 0), len(opts) - 1))
            c.Bind(wx.EVT_CHOICE, self.on_change)
            return c

        def num(key, width=70):
            t = wx.TextCtrl(self, value="%g" % v[key], size=(width, -1))
            t.Bind(wx.EVT_TEXT, self.on_change)
            return t

        self.c = dict(
            dir=choice(DIRS + [("Custom angle", None)], "dir"),
            angle=num("angle"),
            route=choice(ROUTES, "route"),
            slack=choice(SLACKS, "slack"),
            line=choice(LINES, "line"),
            ref=choice(REFS, "ref"),
            align=choice(ALIGNS, "align"),
            profile=choice(PROFILES, "profile"),
            step=num("step"),
            custom=wx.TextCtrl(self, value=v.get("custom", "0; 0.5; 1.0")),
            vias_per=num("vias_per"),
            group_mode=choice(GROUPS, "group_mode"),
            group_spacing=num("group_spacing"),
            ar_grid=num("ar_grid"),
            ar_margin=num("ar_margin"),
        )
        self.c["custom"].Bind(wx.EVT_TEXT, self.on_change)
        rows = [
            ("Direction", "dir", "Custom angle [deg]", "angle"),
            ("Track routing", "route", "Extra length goes to", "slack"),
            ("Via line", "line", "D measured", "ref"),
            ("Row alignment", "align", "Length profile", "profile"),
            ("Profile step [mm]", "step", "Custom lengths [mm] (;)", "custom"),
            ("Vias per item", "vias_per", "Via group layout", "group_mode"),
            ("Group spacing [mm] (0 = auto)", "group_spacing", "Autoroute grid [mm]", "ar_grid"),
            ("Autoroute margin [mm]", "ar_margin", None, None),
        ]
        grid = wx.FlexGridSizer(cols=4, vgap=5, hgap=8)
        for l1, k1, l2, k2 in rows:
            for lab, key in ((l1, k1), (l2, k2)):
                if key is None:
                    grid.AddMany([(0, 0), (0, 0)])
                    continue
                grid.Add(wx.StaticText(self, label=lab), 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(self.c[key], 1, wx.EXPAND)
        grid.AddGrowableCol(1)
        grid.AddGrowableCol(3)
        opts = wx.StaticBoxSizer(wx.VERTICAL, self, "Options")
        opts.Add(grid, 1, wx.ALL | wx.EXPAND, 6)
        box.Add(opts, 0, wx.ALL | wx.EXPAND, 10)

        self.live = wx.CheckBox(self, label="Live preview on the board")
        self.live.SetValue(v.get("live", True))
        self.live.Bind(wx.EVT_CHECKBOX, self.on_change)
        self.status = wx.StaticText(self, label="")
        note = wx.StaticText(self, label="The board stays usable while this window is open: zoom, pan, select "
                                         "other pads.\nDo not edit the board until you press OK/Cancel.")
        box.Add(self.live, 0, wx.LEFT | wx.RIGHT, 10)
        box.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 10)
        box.Add(note, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        box.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(box)
        self.place(frame)

        self.reselect.Bind(wx.EVT_BUTTON, self.on_reselect)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(True), id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(False), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, lambda e: self.finish(False))
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
        """Last position if known, otherwise the right edge of the PCB Editor window."""
        pos = _last.get("pos")
        if pos is None and frame is not None:
            r = frame.GetScreenRect()
            w, _h = self.GetSize()
            pos = (r.GetRight() - w - 40, r.GetTop() + 80)
        if pos is not None:
            self.SetPosition(wx.Point(*pos))

    def remember(self):
        p = self.GetPosition()
        _last["pos"] = (p.x, p.y)

    def update_enabled(self):
        route = ROUTES[self.c["route"].GetSelection()][1]
        self.pic.set_mode(route)
        self.c["angle"].Enable(self.c["dir"].GetSelection() == len(DIRS))
        self.c["align"].Enable(self.pic.pitch_mode.GetSelection() != 1)
        self.c["slack"].Enable(route == g.ROUTE_OFFSET)
        self.c["ref"].Enable(route != g.ROUTE_OFFSET)
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
            self.summary.SetLabel("Netclasses of the selection:\n" + msg)
        self.refresh_preview()

    def refresh_preview(self):
        if not self.IsShown():
            return
        try:
            v = self.values()
        except ValueError:
            self.status.SetLabel("Invalid number.")
            return
        wx.BeginBusyCursor()
        try:
            msg = self.preview_cb(v if self.live.GetValue() else None)
        finally:
            wx.EndBusyCursor()
        self.status.SetLabel(msg)
        self.Layout()
        self.Fit()

    def values(self):
        def f(ctrl, optional=False):
            s = ctrl.GetValue().strip().replace(",", ".")
            if optional and s in ("", "auto", "nc", "netclass"):
                return 0.0
            return float(s)
        fc = lambda k: f(self.c[k])
        fp = lambda k: f(self.pic.ctrl[k], k in Pictogram.OPTIONAL)
        sel = lambda k: self.c[k].GetSelection()
        raw = dict(dir=sel("dir"), ref=sel("ref"), line=sel("line"), align=sel("align"),
                   route=sel("route"), slack=sel("slack"),
                   pitch_mode=self.pic.pitch_mode.GetSelection(),
                   angle=fc("angle"), dist=fp("dist"), pitch=fp("pitch"),
                   lead_pad=fp("lead_pad"), lead_via=fp("lead_via"), shift=fp("shift"),
                   via_d=fp("via_d"), via_drill=fp("via_drill"), width=fp("width"),
                   profile=sel("profile"), step=fc("step"),
                   vias_per=int(fc("vias_per")), group_mode=sel("group_mode"),
                   group_spacing=fc("group_spacing"),
                   ar_grid=fc("ar_grid"), ar_margin=fc("ar_margin"),
                   custom=self.c["custom"].GetValue(),
                   live=self.live.GetValue())
        if raw["vias_per"] < 1 or raw["group_spacing"] < 0:
            raise ValueError("vias per item >= 1, spacing >= 0")
        if raw["ar_grid"] < 0.01 or raw["ar_margin"] < 0:
            raise ValueError("autoroute grid >= 0.01 mm, margin >= 0")
        if raw["lead_pad"] < 0 or raw["lead_via"] < 0:
            raise ValueError("leads >= 0")
        if min(raw["via_d"], raw["via_drill"], raw["width"]) < 0:
            raise ValueError("sizes >= 0")
        if raw["via_d"] and raw["via_drill"] and raw["via_drill"] >= raw["via_d"]:
            raise ValueError("drill < via diameter")
        custom = [float(x) for x in raw["custom"].replace(",", ".").replace(";", " ").split()]
        _last.update(raw)
        angle = DIRS[raw["dir"]][1] if raw["dir"] < len(DIRS) else raw["angle"]
        return dict(raw, angle=angle, ref=REFS[raw["ref"]][1], line=LINES[raw["line"]][1],
                    align=ALIGNS[raw["align"]][1], route=ROUTES[raw["route"]][1],
                    slack_id=SLACKS[raw["slack"]][1],
                    profile_id=PROFILES[raw["profile"]][1], custom_list=custom)
