# Fanout Vias - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Select pads and/or track segments (e.g. D+ and D- of a USB-C connector), then run
# Tools -> External Plugins -> Fanout Vias (or the toolbar button).
# For every selected item that has a net, the plugin adds a track and one or more vias
# (several vias per pad: side by side, one behind another or a 2-row grid, joined by
# short tracks). Tracks go straight, with a 45 deg bend, or are autorouted: a grid
# router (router.py) finds a 0/45/90 deg path that keeps the netclass clearance to
# pads, tracks, vias, NPTH holes and Edge.Cuts of other nets, and moves a via that
# would collide to the nearest free spot. Zones are ignored (they are refilled).
# Via size, drill, track width and clearance are taken from each net's netclass.
# The dialog is modeless: the board stays usable (zoom, pan, select other pads and
# press "Use current selection"); the result is previewed live. OK keeps it, Cancel
# removes it. Everything is a single undo step (Ctrl+Z). Run DRC afterwards.

import fnmatch
import json
import math
import os

import pcbnew
import wx

from . import geometry as g
from . import router as rt

HERE = os.path.dirname(os.path.abspath(__file__))

DIRS = [("Right", 0), ("Up-right 45", 45), ("Up", 90), ("Up-left 45", 135),
        ("Left", 180), ("Down-left 45", 225), ("Down", 270), ("Down-right 45", 315)]
ALIGNS = [("Centre of selection", g.ALIGN_CENTER), ("From first item", g.ALIGN_FIRST),
          ("From last item", g.ALIGN_LAST)]
REFS = [("Pad edge to via centre", g.REF_EDGE_CENTER),
        ("Pad edge to via edge (copper gap)", g.REF_EDGE),
        ("Pad centre to via centre", g.REF_CENTER)]
LINES = [("Common line (from farthest item)", g.LINE_COMMON), ("Separate for each item", g.LINE_EACH)]
ROUTES = [("45 deg bend at via", g.ROUTE_45_VIA), ("45 deg bend at pad", g.ROUTE_45_PAD),
          ("Straight (any angle)", g.ROUTE_STRAIGHT),
          ("Autoroute (avoid pads, tracks, vias, board edge)", g.ROUTE_AUTO)]
PITCHES = ["Auto (minimum from netclass)", "Same as pins", "Custom"]
SIZES = ["From netclass (per net)", "Custom"]
PROFILES = [("Constant", g.PROF_CONST), ("Increasing", g.PROF_INC), ("Decreasing", g.PROF_DEC),
            ("V: centre shortest", g.PROF_V), ("A: centre longest", g.PROF_A),
            ("Zigzag (every 2nd)", g.PROF_ZIGZAG), ("Custom list", g.PROF_CUSTOM)]
GROUPS = [("Side by side (across)", g.GROUP_ACROSS), ("One behind another (along)", g.GROUP_ALONG),
          ("Grid, 2 rows", g.GROUP_GRID)]

_last = {}   # last used settings, kept for this KiCad session


def mm(v):
    return pcbnew.ToMM(v)


# ---------------------------------------------------------------- netclasses

def _project_netclasses(board):
    """Netclasses and net patterns read from the .kicad_pro file (fallback)."""
    try:
        pro = os.path.splitext(board.GetFileName())[0] + ".kicad_pro"
        with open(pro, encoding="utf-8") as f:
            ns = json.load(f)["net_settings"]
    except Exception:
        return None
    classes = {c["name"]: c for c in ns.get("classes", [])}
    return dict(classes=classes,
                patterns=ns.get("netclass_patterns") or [],
                assignments=ns.get("netclass_assignments") or {})


def _from_project(proj, netname):
    if not proj:
        return None
    names = []
    a = proj["assignments"].get(netname)
    if a:
        names += a if isinstance(a, list) else [a]
    for p in proj["patterns"]:
        if fnmatch.fnmatchcase(netname, p["pattern"]) or netname == p["pattern"]:
            names.append(p["netclass"])
    default = proj["classes"].get("Default", {})
    cls = proj["classes"].get(names[0], default) if names else default

    def val(key):
        v = cls.get(key)
        return v if v not in (None, 0) else default.get(key)
    return dict(name=cls.get("name", "Default"), via_d=val("via_diameter"),
                via_drill=val("via_drill"), width=val("track_width"),
                clearance=val("clearance"), src=".kicad_pro")


def _from_api(item, board):
    nc = None
    for get in (lambda: item.GetEffectiveNetClass(),
                lambda: item.GetNet().GetNetClass(),
                lambda: board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(item.GetNetname())):
        try:
            nc = get()
            if nc is not None:
                break
        except Exception:
            nc = None
    if nc is None:
        return None
    try:
        vals = dict(name=str(nc.GetName()), via_d=nc.GetViaDiameter(), via_drill=nc.GetViaDrill(),
                    width=nc.GetTrackWidth(), clearance=nc.GetClearance())
    except Exception:
        return None
    if min(vals["via_d"], vals["via_drill"], vals["width"], vals["clearance"]) <= 0:
        return None
    return dict(name=vals["name"], via_d=mm(vals["via_d"]), via_drill=mm(vals["via_drill"]),
                width=mm(vals["width"]), clearance=mm(vals["clearance"]), src="KiCad")


def netclass_values(item, board, proj):
    """Effective netclass values (mm) for the item's net: KiCad API first, then the
    project file; if a name looks like a composite ('USB,Default') the project file wins."""
    api = _from_api(item, board)
    pro = _from_project(proj, item.GetNetname())
    if api and (api["name"] not in ("Default", "") or not pro or pro["name"] == "Default"):
        return api
    if pro and None not in pro.values():
        return pro
    if api:
        return api
    ds = board.GetDesignSettings()
    return dict(name="(board default)", via_d=mm(ds.GetCurrentViaSize()),
                via_drill=mm(ds.GetCurrentViaDrill()), width=mm(ds.GetCurrentTrackWidth()),
                clearance=mm(ds.m_MinClearance), src="board")


# ---------------------------------------------------------------- geometry -> items

def pad_edge(pad, d):
    """How far the pad outline reaches from its centre in direction d [mm] (bounding box)."""
    bb = pad.GetBoundingBox()
    c = pad.GetPosition()
    cx, cy = mm(c.x), mm(c.y)
    corners = [(bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
               (bb.GetLeft(), bb.GetBottom()), (bb.GetRight(), bb.GetBottom())]
    return max((mm(x) - cx) * d[0] + (mm(y) - cy) * d[1] for x, y in corners)


# ---------------------------------------------------------------- obstacles (autoroute)

def _call(obj, name, layer):
    """KiCad 9/10 padstacks take a layer argument; older versions do not. SWIG raises
    TypeError or NotImplementedError when the overload does not match."""
    fn = getattr(obj, name)
    try:
        return fn(layer)
    except (TypeError, NotImplementedError):
        return fn()


def _size(pad, layer):
    return _call(pad, "GetSize", layer)


def _angle(pad):
    try:
        return float(pad.GetOrientationDegrees())
    except Exception:
        try:
            return float(pad.GetOrientation().AsDegrees())
        except Exception:
            return 0.0


def _arc_pts(a, m, b, n=8):
    (ax, ay), (mx, my), (bx, by) = a, m, b
    d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-12:
        return [a, b]
    ux = ((ax * ax + ay * ay) * (my - by) + (mx * mx + my * my) * (by - ay) + (bx * bx + by * by) * (ay - my)) / d
    uy = ((ax * ax + ay * ay) * (bx - mx) + (mx * mx + my * my) * (ax - bx) + (bx * bx + by * by) * (mx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    t0, tm, t1 = (math.atan2(q[1] - uy, q[0] - ux) for q in (a, m, b))
    sweep = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > sweep:
        sweep -= 2 * math.pi
    return [(ux + r * math.cos(t0 + sweep * i / n), uy + r * math.sin(t0 + sweep * i / n)) for i in range(n + 1)]


def _xy(v):
    return (mm(v.x), mm(v.y))


def _edge_segments(shape):
    """Edge.Cuts shape -> list of ((x, y), (x, y)) segments (mm)."""
    t = shape.GetShape()
    if t == pcbnew.SHAPE_T_SEGMENT:
        return [(_xy(shape.GetStart()), _xy(shape.GetEnd()))]
    if t == pcbnew.SHAPE_T_ARC:
        pts = _arc_pts(_xy(shape.GetStart()), _xy(shape.GetArcMid()), _xy(shape.GetEnd()))
        return list(zip(pts, pts[1:]))
    if t == pcbnew.SHAPE_T_CIRCLE:
        cx, cy = _xy(shape.GetCenter())
        r = mm(shape.GetRadius())
        pts = [(cx + r * math.cos(k * math.pi / 12), cy + r * math.sin(k * math.pi / 12)) for k in range(25)]
        return list(zip(pts, pts[1:]))
    if t == pcbnew.SHAPE_T_RECT:
        (x0, y0), (x1, y1) = _xy(shape.GetStart()), _xy(shape.GetEnd())
        c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [(c[k], c[(k + 1) % 4]) for k in range(4)]
    if t == pcbnew.SHAPE_T_POLY:
        ol = shape.GetPolyShape().Outline(0)
        pts = [_xy(ol.CPoint(k)) for k in range(ol.PointCount())]
        return list(zip(pts, pts[1:] + pts[:1]))
    return []


def collect_obstacles(board, layer, window, skip):
    """Copper on `layer` (pads, tracks, arcs, vias), NPTH holes and Edge.Cuts that fall
    inside window = (x0, y0, x1, y1) [mm]. skip: set of UUID strings to ignore (preview).
    Zones are ignored on purpose: they are refilled around new tracks."""
    x0, y0, x1, y1 = window
    ds = board.GetDesignSettings()
    try:
        edge_clr = mm(ds.m_CopperEdgeClearance)
    except Exception:
        edge_clr = 0.2
    try:
        hole_clr = mm(ds.m_HoleClearance)
    except Exception:
        hole_clr = 0.2
    inside = lambda bb: not (bb[2] < x0 or bb[0] > x1 or bb[3] < y0 or bb[1] > y1)
    obs = []

    def add(o):
        if inside(o.bbox):
            obs.append(o)

    for fp in board.GetFootprints():
        fb = fp.GetBoundingBox()
        if not inside((mm(fb.GetLeft()), mm(fb.GetTop()), mm(fb.GetRight()), mm(fb.GetBottom()))):
            continue
        for pad in fp.Pads():
            c = _xy(pad.GetPosition())
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                dr = pad.GetDrillSize()
                add(rt.Obstacle("circle", (c[0], c[1], mm(max(dr.x, dr.y)) / 2.0), -1, hole_clr))
                continue
            if not pad.IsOnLayer(layer):
                continue
            net = pad.GetNetCode() or -1
            sz = _size(pad, layer)
            w, h = mm(sz.x), mm(sz.y)
            if _call(pad, "GetShape", layer) == pcbnew.PAD_SHAPE_CIRCLE:
                add(rt.Obstacle("circle", (c[0], c[1], w / 2.0), net))
            else:
                add(rt.Obstacle("rect", (c[0], c[1], w / 2.0, h / 2.0, _angle(pad)), net))
        for gi in fp.GraphicalItems():
            if gi.GetLayer() == pcbnew.Edge_Cuts:
                try:
                    for a, b in _edge_segments(gi):
                        add(rt.Obstacle("seg", (a[0], a[1], b[0], b[1], 0.0), -1, edge_clr))
                except Exception:
                    pass
    for t in board.GetTracks():
        try:
            if t.m_Uuid.AsString() in skip:
                continue
        except Exception:
            pass
        cls = t.GetClass()
        net = t.GetNetCode() or -1
        if cls == "PCB_VIA":
            w = mm(_call(t, "GetWidth", layer))
            c = _xy(t.GetPosition())
            add(rt.Obstacle("circle", (c[0], c[1], w / 2.0), net))
        elif t.GetLayer() == layer:
            w = mm(t.GetWidth()) / 2.0
            if cls == "PCB_ARC":
                pts = _arc_pts(_xy(t.GetStart()), _xy(t.GetMid()), _xy(t.GetEnd()), 6)
            else:
                pts = [_xy(t.GetStart()), _xy(t.GetEnd())]
            for a, b in zip(pts, pts[1:]):
                add(rt.Obstacle("seg", (a[0], a[1], b[0], b[1], w), net))
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            try:
                for a, b in _edge_segments(d):
                    add(rt.Obstacle("seg", (a[0], a[1], b[0], b[1], 0.0), -1, edge_clr))
            except Exception:
                pass
    return obs


def _shift(r, dx, dy):
    """Move a planned via group (anchor, vias, bars) by (dx, dy) mm."""
    mv = lambda q: (q[0] + dx, q[1] + dy)
    r["via"] = mv(r["via"])
    r["vias"] = [mv(q) for q in r["vias"]]
    r["bars"] = [(mv(a), mv(b)) for a, b in r["bars"]]


def autoroute(board, result, sources, meta, sizes, ncv, v, skip, warnings):
    """Replace the planned paths by routed ones; moves each via group onto the router grid."""
    pts = [(s["x"], s["y"]) for s in sources] + [q for r in result for q in r["vias"]]
    m = v["ar_margin"] * 3.5 + 1.0
    window = (min(q[0] for q in pts) - m, min(q[1] for q in pts) - m,
              max(q[0] for q in pts) + m, max(q[1] for q in pts) + m)
    cache = {}
    order = sorted(range(len(result)), key=lambda k: math.dist(
        (sources[k]["x"], sources[k]["y"]), result[k]["via"]))     # shortest first
    added = {}                  # layer -> obstacles created by this run
    for k in order:
        r, (net, layer), (via_d, _drill, width), n = result[k], meta[k], sizes[k], ncv[k]
        if layer not in cache:
            cache[layer] = collect_obstacles(board, layer, window, skip)
        code = net.GetNetCode()
        obs = rt.blocking(cache[layer] + added.get(layer, []), code)
        start = (sources[k]["x"], sources[k]["y"])
        offs = [(q[0] - r["via"][0], q[1] - r["via"][1]) for q in r["vias"]]
        spot = rt.find_free_spot(obs, r["via"], offs, via_d / 2.0, n["clearance"],
                                 v["ar_grid"], v["ar_margin"])
        if spot is None:
            warnings.append("Item %d: no free place for the via within the search margin." % (k + 1))
        elif spot != r["via"]:
            _shift(r, spot[0] - r["via"][0], spot[1] - r["via"][1])
        path, snap = rt.route(start, r["via"], obs, width, n["clearance"], res=v["ar_grid"],
                              margin=v["ar_margin"])
        if path is None:
            warnings.append("Item %d: autoroute found no path, used the 45 deg route." % (k + 1))
        else:
            _shift(r, snap[0] - r["via"][0], snap[1] - r["via"][1])
            r["path"] = path
        for q in r["vias"]:
            if not rt.clear_of(rt.blocking(cache[layer], code), q[0], q[1], via_d / 2.0, n["clearance"]):
                warnings.append("Item %d: a via is closer than the clearance to another net (check DRC)." % (k + 1))
                break
        new = added.setdefault(layer, [])
        for a, b in list(zip(r["path"], r["path"][1:])) + list(r["bars"]):
            new.append(rt.Obstacle("seg", (a[0], a[1], b[0], b[1], width / 2.0), code))
        for q in r["vias"]:
            for L in set(list(added.keys()) + [pcbnew.F_Cu, pcbnew.B_Cu]):
                added.setdefault(L, []).append(rt.Obstacle("circle", (q[0], q[1], via_d / 2.0), code))


def build(board, pads, tracks, ncv, v, skip=frozenset()):
    """Create (but do not keep) tracks and vias for settings v. Returns (items, warnings)."""
    n_items = len(pads) + len(tracks)
    if v["sizes"] == 0:
        sizes = [(n["via_d"], n["via_drill"], n["width"]) for n in ncv]
    else:
        sizes = [(v["via_d"], v["via_drill"], v["width"])] * n_items
    max_via = max(s[0] for s in sizes)
    max_drill = max(s[1] for s in sizes)
    max_clr = max(n["clearance"] for n in ncv)

    count = max(1, int(v["vias_per"]))
    gmode = GROUPS[v["group_mode"]][1]
    if v["group_spacing"] > 0:
        gspace = v["group_spacing"]
    else:                          # auto: vias of one net may touch, holes keep hole-to-hole
        gspace = math.ceil(max(max_via, max_drill + hole_to_hole(board)) * 100 - 1e-6) / 100.0
    gwidth = g.group_width(count, gspace, gmode)

    if v["pitch_mode"] == 0:      # auto: smallest legal pitch, rounded up to 0.01 mm
        pitch = math.ceil((gwidth + max_via + max_clr) * 100 - 1e-6) / 100.0
    elif v["pitch_mode"] == 1:    # same as pins
        pitch = 0.0
    else:
        pitch = v["pitch"]

    d, _ = g.axes(v["angle"])
    sources, meta = [], []
    for p in pads:
        c = p.GetPosition()
        sources.append(dict(x=mm(c.x), y=mm(c.y), edge=pad_edge(p, d)))
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        meta.append((p.GetNet(), layer))
    for t in tracks:
        # start from the track end that lies farther in the fanout direction
        e = max([t.GetStart(), t.GetEnd()], key=lambda q: q.x * d[0] + q.y * d[1])
        sources.append(dict(x=mm(e.x), y=mm(e.y), edge=0.0))
        meta.append((t.GetNet(), t.GetLayer()))

    result, warnings = g.plan(sources, v["angle"], v["dist"], pitch, max_via,
                              align=v["align"], ref=v["ref"], line=v["line"],
                              route=v["route"], min_gap=max_clr,
                              profile=v["profile_id"], step=v["step"], custom=v["custom_list"],
                              vias_per=count, group_spacing=gspace, group_mode=gmode)
    if v["route"] == g.ROUTE_AUTO:
        autoroute(board, result, sources, meta, sizes, ncv, v, skip, warnings)

    P = lambda xy: pcbnew.VECTOR2I(pcbnew.FromMM(xy[0]), pcbnew.FromMM(xy[1]))
    created = []
    for r, (net, layer), (via_d, via_drill, width) in zip(result, meta, sizes):
        segs = list(zip(r["path"], r["path"][1:])) + list(r["bars"])
        for a, b in segs:
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(P(a))
            tr.SetEnd(P(b))
            tr.SetWidth(pcbnew.FromMM(width))
            tr.SetLayer(layer)
            tr.SetNet(net)
            board.Add(tr)
            created.append(tr)
        for pos in r["vias"]:
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetPosition(P(pos))
            via.SetWidth(pcbnew.FromMM(via_d))
            via.SetDrill(pcbnew.FromMM(via_drill))
            via.SetNet(net)
            board.Add(via)
            created.append(via)
    info = "Pitch: %s, via %.3f mm, clearance %.3f mm" % (
        "as pins" if pitch == 0 else "%.3f mm" % pitch, max_via, max_clr)
    if count > 1:
        info += "\n%d vias per item, spacing %.3f mm%s" % (
            count, gspace, "" if v["group_spacing"] > 0 else " (auto)")
    return created, warnings, info


def hole_to_hole(board):
    """Minimum hole-to-hole distance from Board Setup [mm], 0.25 if unavailable."""
    try:
        h = mm(board.GetDesignSettings().m_HoleToHoleMin)
        if h > 0:
            return h
    except Exception:
        pass
    return 0.25


def remove(board, items):
    for it in items:
        try:
            board.Remove(it)
        except Exception:
            pass


# ---------------------------------------------------------------- dialog

class FanoutDialog(wx.Dialog):
    """Modeless while it is open: the PCB Editor underneath stays usable (zoom, pan,
    selecting pads), and "Use current selection" re-reads what is selected."""

    def __init__(self, frame, defaults, summary, preview_cb, reselect_cb):
        # No parent on purpose: GNOME/Mutter attaches child dialogs to the parent window
        # (cannot be moved, parent dimmed). A parentless dialog stays movable and the
        # board stays visible; STAY_ON_TOP keeps it above the PCB Editor.
        super().__init__(None, title="Fanout Vias",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
                         | wx.STAY_ON_TOP | wx.DIALOG_NO_PARENT)
        self.preview_cb = preview_cb
        self.reselect_cb = reselect_cb
        self.result = False
        self._loop = None
        v = dict(defaults, **_last)
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)

        def choice(opts, key):
            c = wx.Choice(self, choices=[o if isinstance(o, str) else o[0] for o in opts])
            c.SetSelection(min(v.get(key, 0), len(opts) - 1))
            return c

        def num(key):
            return wx.TextCtrl(self, value="%g" % v[key])

        self.c = dict(
            dir=choice(DIRS + [("Custom angle", None)], "dir"),
            angle=num("angle"),
            ref=choice(REFS, "ref"),
            line=choice(LINES, "line"),
            dist=num("dist"),
            pitch_mode=choice(PITCHES, "pitch_mode"),
            pitch=num("pitch"),
            align=choice(ALIGNS, "align"),
            route=choice(ROUTES, "route"),
            ar_grid=num("ar_grid"),
            ar_margin=num("ar_margin"),
            profile=choice(PROFILES, "profile"),
            step=num("step"),
            custom=wx.TextCtrl(self, value=v.get("custom", "0; 0.5; 1.0")),
            vias_per=num("vias_per"),
            group_mode=choice(GROUPS, "group_mode"),
            group_spacing=num("group_spacing"),
            sizes=choice(SIZES, "sizes"),
            via_d=num("via_d"),
            via_drill=num("via_drill"),
            width=num("width"),
        )
        rows = [
            ("Direction", "dir"),
            ("Custom angle [deg] (0 = right, 90 = up)", "angle"),
            ("Distance measured", "ref"),
            ("Via line", "line"),
            ("Distance [mm]", "dist"),
            ("Via pitch", "pitch_mode"),
            ("Custom pitch [mm]", "pitch"),
            ("Row alignment", "align"),
            ("Track routing", "route"),
            ("Autoroute grid [mm]", "ar_grid"),
            ("Autoroute search margin [mm]", "ar_margin"),
            ("Track length profile", "profile"),
            ("Length step [mm] (+/-)", "step"),
            ("Custom extra lengths [mm] (separate with ;)", "custom"),
            ("Vias per item", "vias_per"),
            ("Via group layout", "group_mode"),
            ("Via spacing in group [mm] (0 = auto)", "group_spacing"),
            ("Via / track sizes", "sizes"),
            ("Custom via diameter [mm]", "via_d"),
            ("Custom via drill [mm]", "via_drill"),
            ("Custom track width [mm]", "width"),
        ]
        for label, key in rows:
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(self.c[key], 1, wx.EXPAND)
        grid.AddGrowableCol(1)

        self.summary = wx.StaticText(self, label="Netclasses of the selection:\n" + summary)
        self.reselect = wx.Button(self, label="Use current selection")
        self.live = wx.CheckBox(self, label="Live preview on the board")
        self.live.SetValue(v.get("live", True))
        self.status = wx.StaticText(self, label="")
        note = wx.StaticText(self, label="The board stays usable while this window is open: zoom, pan,\n"
                                         "select other pads. Do not edit the board until you press OK/Cancel.")

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.summary, 1, wx.ALIGN_CENTER_VERTICAL)
        top.Add(self.reselect, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(top, 0, wx.ALL | wx.EXPAND, 10)
        box.Add(grid, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        box.Add(self.live, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        box.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 10)
        box.Add(note, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        box.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(box)
        self.place(frame)

        self._timer = None
        for key, ctrl in self.c.items():
            evt = wx.EVT_CHOICE if isinstance(ctrl, wx.Choice) else wx.EVT_TEXT
            ctrl.Bind(evt, self.on_change)
        self.live.Bind(wx.EVT_CHECKBOX, self.on_change)
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
            w, h = self.GetSize()
            pos = (r.GetRight() - w - 40, r.GetTop() + 120)
        if pos is not None:
            self.SetPosition(wx.Point(*pos))

    def remember(self):
        p = self.GetPosition()
        _last["pos"] = (p.x, p.y)

    def update_enabled(self):
        self.c["angle"].Enable(self.c["dir"].GetSelection() == len(DIRS))
        self.c["pitch"].Enable(self.c["pitch_mode"].GetSelection() == 2)
        self.c["align"].Enable(self.c["pitch_mode"].GetSelection() != 1)
        auto = ROUTES[self.c["route"].GetSelection()][1] == g.ROUTE_AUTO
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
        custom = self.c["sizes"].GetSelection() == 1
        for k in ("via_d", "via_drill", "width"):
            self.c[k].Enable(custom)

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
        f = lambda k: float(self.c[k].GetValue().replace(",", "."))
        sel = lambda k: self.c[k].GetSelection()
        raw = dict(dir=sel("dir"), ref=sel("ref"), line=sel("line"), align=sel("align"),
                   route=sel("route"), pitch_mode=sel("pitch_mode"), sizes=sel("sizes"),
                   angle=f("angle"), dist=f("dist"), pitch=f("pitch"),
                   via_d=f("via_d"), via_drill=f("via_drill"), width=f("width"),
                   profile=sel("profile"), step=f("step"),
                   vias_per=int(f("vias_per")), group_mode=sel("group_mode"),
                   group_spacing=f("group_spacing"),
                   ar_grid=f("ar_grid"), ar_margin=f("ar_margin"),
                   custom=self.c["custom"].GetValue(),
                   live=self.live.GetValue())
        if raw["vias_per"] < 1 or raw["group_spacing"] < 0:
            raise ValueError("vias per item >= 1, spacing >= 0")
        if raw["ar_grid"] < 0.01 or raw["ar_margin"] < 0:
            raise ValueError("autoroute grid >= 0.01 mm, margin >= 0")
        custom = [float(x) for x in raw["custom"].replace(",", ".").replace(";", " ").split()]
        _last.update(raw)
        angle = DIRS[raw["dir"]][1] if raw["dir"] < len(DIRS) else raw["angle"]
        return dict(raw, angle=angle, ref=REFS[raw["ref"]][1], line=LINES[raw["line"]][1],
                    align=ALIGNS[raw["align"]][1], route=ROUTES[raw["route"]][1],
                    profile_id=PROFILES[raw["profile"]][1], custom_list=custom)


def pcb_frame():
    for w in wx.GetTopLevelWindows():
        try:
            if w.GetName() == "PcbFrame":
                return w
        except Exception:
            pass
    return None


def _uuid(item):
    try:
        return item.m_Uuid.AsString()
    except Exception:
        return str(id(item))


def selection(board, skip):
    """Selected pads and track segments that have a net (preview items excluded)."""
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()
            if p.IsSelected() and p.GetNetCode() > 0]
    tracks = [t for t in board.GetTracks()
              if t.IsSelected() and t.GetClass() == "PCB_TRACK" and t.GetNetCode() > 0
              and _uuid(t) not in skip]
    return pads, tracks


def summarize(ncv):
    seen, lines = set(), []
    for n in ncv:
        if n["name"] not in seen:
            seen.add(n["name"])
            lines.append("  %s: via %.3f / drill %.3f, track %.3f, clearance %.3f mm  [%s]"
                         % (n["name"], n["via_d"], n["via_drill"], n["width"],
                            n["clearance"], n["src"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- plugin

_running = [False]


class FanoutVias(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Fanout Vias"
        self.category = "Routing"
        self.description = "Place an even row of vias for the selected pads or track ends"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "fanout_vias.png")
        self.dark_icon_file_name = os.path.join(HERE, "fanout_vias_dark.png")

    def Run(self):
        if _running[0]:
            wx.MessageBox("Fanout Vias is already open.", "Fanout Vias")
            return
        _running[0] = True
        try:
            self._run()
        finally:
            _running[0] = False

    def _run(self):
        board = pcbnew.GetBoard()
        state = dict(items=[], warnings=[], key=None, skip=set())
        pads, tracks = selection(board, state["skip"])
        if not pads and not tracks:
            wx.MessageBox("Select pads or track segments that have a net.", "Fanout Vias")
            return

        proj = _project_netclasses(board)
        sel = dict(pads=pads, tracks=tracks,
                   ncv=[netclass_values(it, board, proj) for it in pads + tracks])

        first = sel["ncv"][0]
        defaults = dict(dir=0, angle=0, ref=0, line=0, align=0, route=0, pitch_mode=0, sizes=0,
                        profile=0, step=0.5, custom="0; 0.5; 1.0",
                        vias_per=1, group_mode=0, group_spacing=0, ar_grid=0.05, ar_margin=1.5,
                        dist=0.3, pitch=round(first["via_d"] + first["clearance"], 3),
                        via_d=first["via_d"], via_drill=first["via_drill"], width=first["width"])

        def key_of(v):
            return (tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("live", "pos"))),
                    tuple(_uuid(p) for p in sel["pads"]) + tuple(_uuid(t) for t in sel["tracks"]))

        def clear_preview():
            remove(board, state["items"])
            state["items"], state["warnings"], state["key"] = [], [], None
            state["skip"] = set()

        def make(v):
            clear_preview()
            state["items"], state["warnings"], info = build(
                board, sel["pads"], sel["tracks"], sel["ncv"], v)
            state["skip"] = set(_uuid(it) for it in state["items"])
            state["key"] = key_of(v)
            return info

        def preview(v):
            if v is not None and state["key"] == key_of(v):
                return state.get("info", "")         # nothing changed, keep the preview
            if v is None:
                clear_preview()
                info = "Preview off."
            else:
                info = "\n".join([make(v)] + state["warnings"])
            state["info"] = info
            pcbnew.Refresh()
            return info

        def reselect():
            p, t = selection(board, state["skip"])
            if not p and not t:
                return "  (nothing with a net selected, keeping the previous selection)"
            sel.update(pads=p, tracks=t, ncv=[netclass_values(it, board, proj) for it in p + t])
            state["key"] = None
            return summarize(sel["ncv"])

        dlg = FanoutDialog(pcb_frame(), defaults, summarize(sel["ncv"]), preview, reselect)
        wx.CallAfter(dlg.refresh_preview)
        ok = dlg.run()
        try:
            v = dlg.values()
        except ValueError:
            v = None
        dlg.Destroy()

        if ok and v is not None:
            if state["key"] != key_of(v):            # preview off or stale: build once now
                make(v)
            if state["warnings"]:
                wx.MessageBox("\n".join(state["warnings"]), "Fanout Vias - warnings")
        else:
            clear_preview()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was added.", "Fanout Vias")
        pcbnew.Refresh()
