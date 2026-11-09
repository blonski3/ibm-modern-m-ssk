# Shared dialog kit of the *-o-matic KiCad plugins (wxPython, no pcbnew import): the
# Win95-flavoured look of via-o-tronic (logo, lettered pictogram, values in a column,
# mouse wheel stepping, compact window with "More", warning button with a log window).
# Every change is applied to the board at once through apply_cb; OK keeps it, Cancel
# puts the board back. Copied into every plugin folder (self-contained plugins).

import math
import os

import wx

COL_CU = wx.Colour(200, 52, 52)
COL_CU2 = wx.Colour(60, 110, 210)      # second copper layer (B.Cu) in sketches
COL_VIA = wx.Colour(226, 186, 40)
COL_HL = wx.Colour(255, 140, 0)
COL_SILK = wx.Colour(235, 235, 235)
COL_FAB = wx.Colour(150, 150, 150)
GREY = wx.Colour(140, 140, 140)


def is_dark(colour):
    return (0.299 * colour.Red() + 0.587 * colour.Green() + 0.114 * colour.Blue()) < 128


def dim_colour(dark):
    return wx.Colour(110, 190, 255) if dark else wx.Colour(0, 90, 190)


def _blank(size):
    img = wx.Image(size, size)
    img.InitAlpha()
    for x in range(size):
        for y in range(size):
            img.SetAlpha(x, y, 0)
    return wx.Bitmap(img)


def icon_bitmap(draw, size=16):
    """Small transparent bitmap drawn by draw(gc, size)."""
    bmp = _blank(size)
    dc = wx.MemoryDC(bmp)
    gc = wx.GraphicsContext.Create(dc)
    draw(gc, size)
    del gc
    dc.SelectObject(wx.NullBitmap)
    return bmp


def arrow_bitmap(angle, colour, size=16, double=False):
    """Arrow pointing at angle (0 = right, 90 = up); double = both ways."""
    def draw(gc, size):
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
    return icon_bitmap(draw, size)


def rotate_bitmap(colour, ccw=True, size=16):
    """Circular arrow (rotate)."""
    def draw(gc, size):
        c = size / 2.0
        r = 5.0
        gc.SetPen(wx.Pen(colour, 2))
        p = gc.CreatePath()
        a0, a1 = (math.radians(30), math.radians(300)) if ccw else (math.radians(150), math.radians(-120))
        p.AddArc(c, c, r, a0, a1, ccw is False)
        gc.StrokePath(p)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour))
        ex, ey = c + r * math.cos(a1), c + r * math.sin(a1)
        p = gc.CreatePath()
        d = -1 if ccw else 1
        p.MoveToPoint(ex + 4, ey + d * 0)
        p.AddLineToPoint(ex - 3, ey - 3)
        p.AddLineToPoint(ex - 3, ey + 4)
        p.CloseSubpath()
        gc.FillPath(p)
    return icon_bitmap(draw, size)


def squeeze_bitmap(colour, out=False, size=16):
    """Two bars with arrows towards each other (tighter) or apart (wider), horizontal."""
    def draw(gc, size):
        gc.SetPen(wx.Pen(colour, 2))
        gc.StrokeLine(2, 2, 2, 14)
        gc.StrokeLine(14, 2, 14, 14)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour))
        for sgn in (-1, 1):                     # left / right arrow
            d = sgn if out else -sgn            # direction it points (+ = right)
            tip = 8 + sgn * 4.5 if out else 8 + sgn * 1
            p = gc.CreatePath()
            p.MoveToPoint(tip, 8)
            p.AddLineToPoint(tip - d * 4, 4)
            p.AddLineToPoint(tip - d * 4, 12)
            p.CloseSubpath()
            gc.FillPath(p)
    return icon_bitmap(draw, size)


class _Mods:
    """Keyboard modifiers at the time of a button click (Shift = x10, Ctrl = /10)."""

    def __init__(self):
        st = wx.GetMouseState()
        self._s, self._c = st.ShiftDown(), st.ControlDown()

    def ShiftDown(self):
        return self._s

    def ControlDown(self):
        return self._c


# ---------------------------------------------------------------- pictogram base

class Sketch(wx.Panel):
    """Pictogram with lettered dimensions. Subclasses implement paint(p) where p offers
    the drawing helpers below and the theme colours; self.state holds what the dialog
    told it (mode choices), self.hl the highlighted field key."""

    W, H = 300, 200

    def __init__(self, parent):
        super().__init__(parent, size=(self.W, self.H))
        self.SetMinSize((self.W, self.H))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.state = {}
        self.hl = None
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_state(self, hl=False, **kw):
        self.state.update(kw)
        if hl is not False:
            self.hl = hl
        self.Refresh()

    def _on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        bg = self.GetParent().GetBackgroundColour()
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        self.paint(_Painter(gc, bg, self.hl))

    def paint(self, p):
        pass


class _Painter:
    def __init__(self, gc, bg, hl):
        self.gc, self.bg, self.hl = gc, bg, hl
        self.dark = is_dark(bg)
        self.dim = dim_colour(self.dark)
        self.off = wx.Colour(100, 100, 100) if self.dark else wx.Colour(170, 170, 170)
        self.ext = wx.Colour(105, 105, 105) if self.dark else wx.Colour(175, 175, 175)
        self.body = wx.Colour(70, 70, 70) if self.dark else wx.Colour(205, 205, 205)
        self.silk = wx.Colour(230, 230, 230) if self.dark else wx.Colour(60, 60, 60)
        self.font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.small = wx.Font(7, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

    def col(self, key, on=True):
        if key is not None and (key == self.hl or (isinstance(key, tuple) and self.hl in key)):
            return COL_HL
        return self.dim if on else self.off

    def dash(self, x0, y0, x1, y1):
        self.gc.SetPen(wx.Pen(self.ext, 1, wx.PENSTYLE_SHORT_DASH))
        self.gc.StrokeLine(x0, y0, x1, y1)

    def letter(self, text, x, y, c, font=None):
        gc = self.gc
        gc.SetFont(font or self.font, c)
        w, h = gc.GetTextExtent(text)
        gc.SetBrush(wx.Brush(self.bg))
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawRectangle(x - w / 2 - 2, y - h / 2, w + 4, h)
        gc.DrawText(text, x - w / 2, y - h / 2)

    def arrow(self, x0, y0, x1, y1, key, text=None, tx=None, ty=None, on=True, heads=2):
        c = self.col(key, on)
        gc = self.gc
        gc.SetPen(wx.Pen(c, 2 if c == COL_HL else 1))
        gc.StrokeLine(x0, y0, x1, y1)
        gc.SetBrush(wx.Brush(c))
        gc.SetPen(wx.TRANSPARENT_PEN)
        ends = (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0)))[:heads] if heads != 1 else (((x1, y1), (x0, y0)),)
        for (ax, ay), (bx, by) in ends:
            L = math.hypot(bx - ax, by - ay) or 1
            ux, uy = (bx - ax) / L, (by - ay) / L
            p = gc.CreatePath()
            p.MoveToPoint(ax, ay)
            p.AddLineToPoint(ax + 6 * ux - 3 * uy, ay + 6 * uy + 3 * ux)
            p.AddLineToPoint(ax + 6 * ux + 3 * uy, ay + 6 * uy - 3 * ux)
            p.CloseSubpath()
            gc.FillPath(p)
        if text:
            self.letter(text, tx if tx is not None else (x0 + x1) / 2.0,
                        ty if ty is not None else (y0 + y1) / 2.0, c)

    def leader(self, x0, y0, x1, y1, key, text, on=True):
        c = self.col(key, on)
        self.gc.SetPen(wx.Pen(c, 1))
        self.gc.StrokeLine(x0, y0, x1, y1)
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        self.letter(text, x1 + 6 * dx / L, y1 + 6 * dy / L, c)

    def path(self, pts, colour, width, closed=False):
        gc = self.gc
        gc.SetPen(wx.Pen(colour, width))
        p = gc.CreatePath()
        p.MoveToPoint(*pts[0])
        for q in pts[1:]:
            p.AddLineToPoint(*q)
        if closed:
            p.CloseSubpath()
        gc.StrokePath(p)

    def rect(self, x, y, w, h, colour, r=0, outline=None):
        gc = self.gc
        gc.SetPen(wx.Pen(outline, 1) if outline else wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour) if colour else wx.TRANSPARENT_BRUSH)
        if r:
            gc.DrawRoundedRectangle(x, y, w, h, r)
        else:
            gc.DrawRectangle(x, y, w, h)

    def circle(self, x, y, r, colour, outline=None, width=1):
        gc = self.gc
        gc.SetPen(wx.Pen(outline, width) if outline else wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour) if colour else wx.TRANSPARENT_BRUSH)
        gc.DrawEllipse(x - r, y - r, 2 * r, 2 * r)

    def via(self, x, y, r=7, hole=3, colour=None):
        self.circle(x, y, r, colour or COL_VIA)
        self.circle(x, y, hole, self.bg)

    def text(self, s, x, y, colour, font=None, angle=0.0):
        gc = self.gc
        gc.SetFont(font or self.font, colour)
        w, h = gc.GetTextExtent(s)
        if angle:
            gc.PushState()
            gc.Translate(x, y)
            gc.Rotate(-math.radians(angle))
            gc.DrawText(s, -w / 2, -h / 2)
            gc.PopState()
        else:
            gc.DrawText(s, x - w / 2, y - h / 2)


# ---------------------------------------------------------------- log window

class LogWindow(wx.Frame):
    def __init__(self, parent, name):
        super().__init__(parent, title=name + " – log", size=(580, 260),
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


# ---------------------------------------------------------------- dialog base

class OMatic(wx.Dialog):
    """Base dialog. Subclasses set NAME, FILE (icon/logo base name), DEFAULTS, STEPS,
    MINIMUM, OPTIONAL ({key: hint}), TEXTS (text fields), NOT_REMEMBERED, LAST (a dict
    kept for the KiCad session) and implement build(box) and convert(raw) -> values.
    apply_cb(values) -> dict(info=str, warnings=[...], ro={key: text}, nc={key: value});
    reselect_cb() -> (summary, defaults dict or None) or None."""

    NAME = "o-matic"
    FILE = "o_matic"
    DEFAULTS = {}
    STEPS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
    STEP_DEFAULT = 2
    MINIMUM = {}
    OPTIONAL = {}
    TEXTS = set()
    INTEGERS = set()
    ANGLES = set()
    NOT_REMEMBERED = set()
    LAST = None
    HAS_CHECK = True
    CHECK_TIP = "Check the clearance to copper of other nets"
    DELAY = 120

    def __init__(self, frame, here, summary, apply_cb, reselect_cb, defaults=None):
        super().__init__(None, title=self.NAME,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP | wx.DIALOG_NO_PARENT)
        if self.LAST is None:
            type(self).LAST = {}
        self.apply_cb, self.reselect_cb = apply_cb, reselect_cb
        self.here = here
        self.result = False
        self.log_win = None
        self.last = {}
        self._loop = None
        self._timer = None
        defaults = defaults or {}
        v = dict(self.DEFAULTS)
        v.update({k: x for k, x in self.LAST.items() if k not in self.NOT_REMEMBERED})
        v.update({k: x for k, x in defaults.items() if k in self.NOT_REMEMBERED or k not in self.LAST})
        self.v = v
        self.nc = dict(defaults.get("nc", {}))
        self.f, self.c, self.ch, self.cb, self.rows, self.ro = {}, {}, {}, {}, {}, {}
        self.dark = is_dark(self.GetBackgroundColour())
        self.dimc = dim_colour(self.dark)
        self.fg = self.GetForegroundColour()
        icon = os.path.join(here, self.FILE + ".png")
        if os.path.exists(icon):
            try:
                quiet = wx.LogNull()
                self.SetIcon(wx.Icon(icon, wx.BITMAP_TYPE_PNG))
                quiet.__class__     # keep the log silenced until here
            except Exception:
                pass
        self.draw = None

        box = wx.BoxSizer(wx.VERTICAL)
        head = wx.BoxSizer(wx.HORIZONTAL)
        logo = os.path.join(here, self.FILE + ("_logo_dark.png" if self.dark else "_logo.png"))
        if os.path.exists(logo):
            head.Add(wx.StaticBitmap(self, bitmap=wx.Bitmap(logo, wx.BITMAP_TYPE_PNG)), 0,
                     wx.ALIGN_CENTER_VERTICAL)
        head.AddStretchSpacer()
        self.reselect = wx.Button(self, label="↻", style=wx.BU_EXACTFIT)
        self.reselect.SetToolTip("Use what is selected now")
        head.Add(self.reselect, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(head, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)
        self.summary = wx.StaticText(self, label=summary)
        self.summary.SetForegroundColour(GREY)
        box.Add(self.summary, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        self.build(box)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        if self.HAS_CHECK:
            self.cb["check"] = wx.CheckBox(self, label="Check")
            self.cb["check"].SetValue(bool(v.get("check", True)))
            self.cb["check"].SetToolTip(self.CHECK_TIP)
            self.cb["check"].Bind(wx.EVT_CHECKBOX, self.on_change)
            bottom.Add(self.cb["check"], 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.warn = wx.Button(self, label="⚠ 0", style=wx.BU_EXACTFIT)
        self.warn.SetToolTip("Show the log: what failed and what to change")
        self.warn.Bind(wx.EVT_BUTTON, lambda e: self.show_log())
        self.warn.Hide()
        bottom.Add(self.warn, 0, wx.ALIGN_CENTER_VERTICAL)
        self.status = wx.StaticText(self, label="", size=(170, -1),
                                    style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE)
        bottom.Add(self.status, 1, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        bottom.Add(wx.Button(self, wx.ID_CANCEL), 0, wx.RIGHT, 4)
        ok = wx.Button(self, wx.ID_OK)
        ok.SetDefault()
        bottom.Add(ok, 0)
        box.Add(bottom, 0, wx.ALL | wx.EXPAND, 8)

        self.SetSizerAndFit(box)
        self.place(frame)
        self.reselect.Bind(wx.EVT_BUTTON, self.on_reselect)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(True), id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, lambda e: self.finish(False), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, lambda e: self.finish(False))
        for store in (self.f, self.c):
            for key, t in store.items():
                if key not in self.TEXTS:
                    self.spinnable(t, key)
        self.update_enabled()

    # ---------------------------------------------------------- building blocks
    def bold(self, parent, text):
        lbl = wx.StaticText(parent, label=text)
        lbl.SetForegroundColour(self.dimc)
        lbl.SetFont(lbl.GetFont().Bold())
        return lbl

    def grey(self, parent, text):
        lbl = wx.StaticText(parent, label=text)
        lbl.SetForegroundColour(GREY)
        return lbl

    def _fmt(self, key, val):
        if key in self.TEXTS:
            return str(val)
        if key in self.OPTIONAL and not val:
            return ""
        if key in self.INTEGERS:
            return "%d" % int(val)
        return "%g" % round(float(val), 4)

    def textctrl(self, parent, key, tip, width=64, store=None):
        t = wx.TextCtrl(parent, value=self._fmt(key, self.v.get(key, 0)), size=(width, -1),
                        style=wx.TE_PROCESS_ENTER)
        t.SetToolTip(tip)
        hint = self.OPTIONAL.get(key)
        if hint:
            try:
                t.SetHint(hint)
            except Exception:
                pass
        t.Bind(wx.EVT_TEXT, self.on_change)
        (self.f if store is None else store)[key] = t
        return t

    def hover(self, key, *ws):
        for w in ws:
            w.Bind(wx.EVT_ENTER_WINDOW, lambda e, k=key: (self._hl(k), e.Skip()))
            w.Bind(wx.EVT_LEAVE_WINDOW, lambda e: (self._hl(self._focus_key()), e.Skip()))

    def _hl(self, key):
        if self.draw is not None:
            self.draw.set_state(hl=key)

    def field(self, fgs, key, label, tip, tail=None, width=64):
        """Lettered value row in a 2-column FlexGridSizer (label | control [tail])."""
        t = self.textctrl(self, key, tip, width)
        lbl = self.bold(self, label)
        fgs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        if tail is None:
            fgs.Add(t, 0)
        else:
            h = wx.BoxSizer(wx.HORIZONTAL)
            h.Add(t, 0)
            for w in (tail if isinstance(tail, (list, tuple)) else [tail]):
                h.Add(w, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 3)
            fgs.Add(h, 0)
        self.rows[key] = (lbl, t)
        self.hover(key, t, lbl)
        t.Bind(wx.EVT_SET_FOCUS, lambda e, k=key: (self._hl(k), e.Skip()))
        return t

    def readout(self, fgs, key, label, tip):
        lbl = self.bold(self, label)
        t = wx.StaticText(self, label="–")
        t.SetToolTip(tip)
        fgs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        fgs.Add(t, 0, wx.ALIGN_CENTER_VERTICAL)
        self.ro[key] = t
        self.rows[key] = (lbl, t)
        return t

    def choice(self, parent, key, labels, tip, store=None):
        c = wx.Choice(parent, choices=list(labels))
        c.SetSelection(max(0, min(int(self.v.get(key, 0)), len(labels) - 1)))
        c.SetToolTip(tip)
        c.Bind(wx.EVT_CHOICE, self.on_change)
        (self.ch if store is None else store)[key] = c
        return c

    def checkbox(self, parent, key, label, tip):
        c = wx.CheckBox(parent, label=label)
        c.SetValue(bool(self.v.get(key, False)))
        c.SetToolTip(tip)
        c.Bind(wx.EVT_CHECKBOX, self.on_change)
        self.cb[key] = c
        return c

    def toggles(self, parent, key, bitmaps, tips):
        """Row of bitmap toggle buttons acting as one choice (value = index)."""
        row = wx.BoxSizer(wx.HORIZONTAL)
        btns = []
        for k, (bmp, tip) in enumerate(zip(bitmaps, tips)):
            b = wx.ToggleButton(parent, label="", style=wx.BU_EXACTFIT)
            b.SetBitmap(bmp)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_TOGGLEBUTTON, lambda e, k=k: self._toggle(key, k))
            btns.append(b)
            row.Add(b, 0, wx.RIGHT, 1)
        self.tg = getattr(self, "tg", {})
        self.tg[key] = [btns, int(self.v.get(key, 0))]
        return row

    def _toggle(self, key, k):
        self.tg[key][1] = k
        self.on_change()

    def step_choice(self, parent):
        self.step_ch = wx.Choice(parent, choices=["%g mm" % st for st in self.STEPS])
        self.step_ch.SetSelection(min(int(self.v.get("nudge", self.STEP_DEFAULT)), len(self.STEPS) - 1))
        self.step_ch.SetToolTip("Step for the buttons and for the mouse wheel / ↑↓ on any value.\n"
                                "Shift = ×10, Ctrl = ÷10")
        return self.step_ch

    def nudge_button(self, parent, bmp, tip, key, sign):
        b = wx.BitmapButton(parent, bitmap=bmp, style=wx.BU_EXACTFIT)
        b.SetToolTip(tip)
        b.Bind(wx.EVT_BUTTON, lambda e: self.nudge(key, sign))
        return b

    def more_pane(self, box):
        self.more = wx.CollapsiblePane(self, label="More", style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE)
        self.more.Collapse(not self.v.get("more", False))
        self.more.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_more)
        box.Add(self.more, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)
        return self.more.GetPane()

    def num(self, pane, key, tip, width=64):
        return self.textctrl(pane, key, tip, width, store=self.c)

    # ---------------------------------------------------------- running
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
        pos = self.LAST.get("pos")
        if pos is None and frame is not None:
            r = frame.GetScreenRect()
            w, _h = self.GetSize()
            pos = (r.GetRight() - w - 30, r.GetTop() + 110)
        if pos is not None:
            self.SetPosition(wx.Point(*pos))

    def remember(self):
        p = self.GetPosition()
        self.LAST["pos"] = (p.x, p.y)
        if hasattr(self, "more"):
            self.LAST["more"] = self.more.IsExpanded()

    # ---------------------------------------------------------- stepping
    def step_size(self, evt=None):
        st = self.STEPS[self.step_ch.GetSelection()] if hasattr(self, "step_ch") else 0.1
        if evt is not None:
            if evt.ShiftDown():
                st *= 10
            elif evt.ControlDown():
                st /= 10.0
        return st

    def bump(self, ctrl, key, n, evt=None):
        s = ctrl.GetValue().strip().replace(",", ".")
        try:
            if s == "" or s == self.OPTIONAL.get(key):
                val = float(self.nc.get(key, 0.0))
            else:
                val = float(s)
        except ValueError:
            return
        if key in self.INTEGERS:
            val = int(round(val)) + n * (10 if evt is not None and evt.ShiftDown() else 1)
            lo = self.MINIMUM.get(key)
            if lo is not None:
                val = max(int(lo), val)
            txt = "%d" % val
        elif key in self.ANGLES:
            val = (val + n * (45.0 if evt is not None and evt.ShiftDown() else
                              (1.0 if evt is not None and evt.ControlDown() else 5.0))) % 360
            txt = "%g" % round(val, 3)
        else:
            val = round(val + n * self.step_size(evt), 4)
            lo = self.MINIMUM.get(key)
            if lo is not None:
                val = max(lo, val)
            txt = "%g" % val
        ctrl.SetValue(txt)            # fires EVT_TEXT -> apply
        ctrl.SetInsertionPointEnd()

    def spinnable(self, ctrl, key):
        def wheel(evt):
            if ctrl.IsEnabled():
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
        ctrl = self.f.get(key) or self.c.get(key)
        self.bump(ctrl, key, sign, _Mods())

    def _focus_key(self):
        w = wx.Window.FindFocus()
        for store in (self.f, self.c):
            for k, t in store.items():
                if t is w:
                    return k
        return None

    def on_more(self, _evt=None):
        self.LAST["more"] = self.more.IsExpanded()
        self.Layout()
        self.Fit()

    def show_rows(self, shown):
        """shown: {key: bool} for rows made with field()/readout()."""
        changed = False
        for key, show in shown.items():
            for w in self.rows.get(key, ()):
                if w.IsShown() != show:
                    w.Show(show)
                    changed = True
        if changed:
            self.Layout()
            self.Fit()

    def update_enabled(self):
        if hasattr(self, "tg"):
            for key, (btns, sel) in self.tg.items():
                for k, b in enumerate(btns):
                    b.SetValue(k == sel)
        self.on_state()

    def on_state(self):
        """Subclass: enable/disable and tell the pictogram the current choices."""

    def on_change(self, _evt=None):
        self.update_enabled()
        if self._timer is not None:
            self._timer.Stop()
        self._timer = wx.CallLater(self.DELAY, self.refresh)

    def on_reselect(self, _evt=None):
        res = self.reselect_cb()
        if res is not None:
            text, defaults = res
            self.summary.SetLabel(text)
            if defaults:
                self.on_reselected(defaults)
        self.Layout()
        self.Fit()
        self.refresh()

    def on_reselected(self, defaults):
        self.nc.update(defaults.get("nc", {}))

    def refresh(self):
        if not self.IsShown():
            return
        try:
            v = self.values()
        except ValueError as e:
            self.set_status(dict(info="Invalid value" + (": %s" % e if str(e) else ""), warnings=[]))
            return
        wx.BeginBusyCursor()
        try:
            res = self.apply_cb(v)
        except Exception as e:                      # never leave the dialog in a broken state
            import traceback
            traceback.print_exc()
            res = dict(info="Error: %s" % e, warnings=["Internal error: %s → report it, "
                                                       "Cancel restores the board" % e])
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
        for key, text in self.last.get("ro", {}).items():
            if key in self.ro:
                self.ro[key].SetLabel(text)
        self.nc.update(self.last.get("nc", {}))
        if self.log_win:
            self.log_win.update(self.log_text())

    def log_text(self):
        out = [self.last.get("info", "").split("\n")[0], ""]
        warn = self.last.get("warnings", [])
        out += ["⚠ " + w for w in warn] if warn else ["No problems."]
        return "\n".join(out)

    def show_log(self):
        if not self.log_win:
            self.log_win = LogWindow(self, self.NAME)
            self.log_win.Bind(wx.EVT_CLOSE, self._log_closed)
        self.log_win.update(self.log_text())
        self.log_win.Show()
        self.log_win.Raise()

    def _log_closed(self, _evt):
        self.log_win.Destroy()
        self.log_win = None

    # ---------------------------------------------------------- values
    def raw_values(self):
        raw = {}
        for store in (self.f, self.c):
            for key, t in store.items():
                s = t.GetValue().strip().replace(",", ".")
                if key in self.TEXTS:
                    raw[key] = t.GetValue()
                elif s == "" or s == self.OPTIONAL.get(key):
                    if key in self.OPTIONAL:
                        raw[key] = 0
                    else:
                        raise ValueError(key)
                else:
                    try:
                        raw[key] = int(s) if key in self.INTEGERS else float(s)
                    except ValueError:
                        raise ValueError(key)
        for key, c in self.ch.items():
            raw[key] = c.GetSelection()
        for key, c in self.cb.items():
            raw[key] = c.GetValue()
        for key, (_b, sel) in getattr(self, "tg", {}).items():
            raw[key] = sel
        if hasattr(self, "step_ch"):
            raw["nudge"] = self.step_ch.GetSelection()
        return raw

    def values(self):
        raw = self.raw_values()
        out = self.convert(dict(raw))
        self.LAST.update(raw)
        return out

    def convert(self, raw):
        return raw

    def build(self, box):
        raise NotImplementedError
