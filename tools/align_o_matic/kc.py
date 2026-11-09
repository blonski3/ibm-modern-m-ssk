# Shared KiCad (pcbnew SWIG) helpers of the *-o-matic plugins: units, item snapshots for
# exact restore, netclass clearance, copper collection. KiCad 7-10. Copied into every
# plugin folder, so each plugin stays self-contained.

import fnmatch
import json
import math
import os

import pcbnew
import wx

from . import geo

IU = 1e6                     # KiCad internal units (nm) per mm


def mm(v):
    return v / IU


def xy(v):
    return (v.x / IU, v.y / IU)


def P(p):
    return pcbnew.VECTOR2I(int(round(p[0] * IU)), int(round(p[1] * IU)))


def iu(v):
    return int(round(v * IU))


def uuid(item):
    try:
        return item.m_Uuid.AsString()
    except Exception:
        return str(id(item))


def call(obj, name, *args):
    """KiCad 9/10 padstack getters take a layer; older ones do not."""
    fn = getattr(obj, name)
    try:
        return fn(*args)
    except (TypeError, NotImplementedError):
        return fn()


def pcb_frame():
    for w in wx.GetTopLevelWindows():
        try:
            if w.GetName() == "PcbFrame":
                return w
        except Exception:
            pass
    return None


def layer_name(board, layer):
    try:
        return board.GetLayerName(layer)
    except Exception:
        return str(layer)


def refresh():
    try:
        pcbnew.Refresh()
    except Exception:
        pass


# ---------------------------------------------------------------- snapshots / restore

def _angle_deg(get):
    v = get()
    try:
        return float(v.AsDegrees())
    except AttributeError:
        return float(v)


class Edits:
    """Everything a live change did to the board, so it can be undone exactly before the
    next change (and on Cancel). save(item) before changing an item, add(item) for new
    items, remove(item) for deleted ones."""

    def __init__(self, board):
        self.board = board
        self.saved = {}          # uuid -> (item, snapshot)
        self.created = []
        self.removed = []

    # snapshot of what the plugins change
    @staticmethod
    def snap(item):
        cls = item.GetClass()
        if cls in ("PCB_TRACK", "PCB_ARC"):
            s = dict(start=item.GetStart(), end=item.GetEnd(), width=item.GetWidth(),
                     layer=item.GetLayer())
            if cls == "PCB_ARC":
                s["mid"] = item.GetMid()
            return {k: (pcbnew.VECTOR2I(v.x, v.y) if hasattr(v, "x") else v) for k, v in s.items()}
        if cls == "PCB_VIA":
            return dict(pos=pcbnew.VECTOR2I(item.GetPosition().x, item.GetPosition().y))
        if cls == "FOOTPRINT":
            p = item.GetPosition()
            return dict(pos=pcbnew.VECTOR2I(p.x, p.y), angle=item.GetOrientationDegrees())
        # texts / fields
        p = item.GetPosition()
        s = dict(pos=pcbnew.VECTOR2I(p.x, p.y))
        for k, get in (("angle", lambda: item.GetTextAngleDegrees()),
                       ("size", lambda: item.GetTextSize()),
                       ("thick", lambda: item.GetTextThickness()),
                       ("hj", lambda: item.GetHorizJustify()),
                       ("vj", lambda: item.GetVertJustify()),
                       ("visible", lambda: item.IsVisible())):
            try:
                v = get()
                s[k] = pcbnew.VECTOR2I(v.x, v.y) if hasattr(v, "x") else v
            except Exception:
                pass
        return s

    @staticmethod
    def put(item, s):
        cls = item.GetClass()
        if cls in ("PCB_TRACK", "PCB_ARC"):
            item.SetStart(s["start"])
            if "mid" in s:
                item.SetMid(s["mid"])
            item.SetEnd(s["end"])
            item.SetWidth(s["width"])
            item.SetLayer(s["layer"])
            return
        if cls == "PCB_VIA":
            item.SetPosition(s["pos"])
            return
        if cls == "FOOTPRINT":
            item.SetOrientationDegrees(s["angle"])
            item.SetPosition(s["pos"])
            return
        item.SetPosition(s["pos"])
        for k, setter in (("angle", item.SetTextAngleDegrees), ("size", item.SetTextSize),
                          ("thick", item.SetTextThickness), ("hj", item.SetHorizJustify),
                          ("vj", item.SetVertJustify), ("visible", item.SetVisible)):
            if k in s:
                try:
                    setter(s[k])
                except Exception:
                    pass

    def save(self, item):
        u = uuid(item)
        if u not in self.saved:
            self.saved[u] = (item, self.snap(item))

    def add(self, item):
        self.board.Add(item)
        self.created.append(item)
        return item

    def remove(self, item):
        self.board.Remove(item)
        self.removed.append(item)

    def restore(self):
        for it in self.created:
            try:
                self.board.Remove(it)
            except Exception:
                pass
        for it in self.removed:
            try:
                self.board.Add(it)
            except Exception:
                pass
        for item, s in self.saved.values():
            try:
                self.put(item, s)
            except Exception:
                pass
        self.saved, self.created, self.removed = {}, [], []

    def changed(self):
        return bool(self.saved or self.created or self.removed)


# ---------------------------------------------------------------- netclass clearance

def project_netclasses(board):
    try:
        pro = os.path.splitext(board.GetFileName())[0] + ".kicad_pro"
        with open(pro, encoding="utf-8") as f:
            ns = json.load(f)["net_settings"]
    except Exception:
        return None
    return dict(classes={c["name"]: c for c in ns.get("classes", [])},
                patterns=ns.get("netclass_patterns") or [],
                assignments=ns.get("netclass_assignments") or {})


def _nc_project(proj, netname):
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

    def val(k):
        v = cls.get(k)
        return v if v not in (None, 0) else default.get(k)
    return dict(name=cls.get("name", "Default"), clearance=val("clearance"), width=val("track_width"),
                via_d=val("via_diameter"), via_drill=val("via_drill"))


def _nc_api(item, board):
    for get in (lambda: item.GetEffectiveNetClass(),
                lambda: item.GetNet().GetNetClass(),
                lambda: board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(item.GetNetname())):
        try:
            nc = get()
            if nc is not None and nc.GetClearance() > 0:
                return dict(name=str(nc.GetName()), clearance=mm(nc.GetClearance()),
                            width=mm(nc.GetTrackWidth()), via_d=mm(nc.GetViaDiameter()),
                            via_drill=mm(nc.GetViaDrill()))
        except Exception:
            pass
    return None


def netclass(item, board, proj=None):
    """Netclass values (mm) of the item's net: KiCad API, the project file when the API
    only knows 'Default' (composite netclasses in KiCad 9/10), then board defaults."""
    api = _nc_api(item, board)
    pro = _nc_project(proj, item.GetNetname()) if proj else None
    if api and (api["name"] not in ("Default", "") or not pro or pro["name"] == "Default"):
        return api
    if pro and None not in pro.values():
        return pro
    if api:
        return api
    ds = board.GetDesignSettings()
    out = dict(name="(board)", clearance=0.2, width=0.2, via_d=0.6, via_drill=0.3)
    for k, get in (("clearance", lambda: ds.m_MinClearance), ("width", ds.GetCurrentTrackWidth),
                   ("via_d", ds.GetCurrentViaSize), ("via_drill", ds.GetCurrentViaDrill)):
        try:
            v = mm(get() if callable(get) else get)
            if v > 0:
                out[k] = v
        except Exception:
            pass
    return out


def net_by_name(board, name):
    try:
        n = board.FindNet(name)
        if n is not None:
            return n
    except Exception:
        pass
    try:
        return board.GetNetsByName()[name]
    except Exception:
        return None


def net_names(board):
    try:
        names = [str(k) for k in board.GetNetsByName().keys()]
    except Exception:
        names = []
    return sorted(n for n in names if n)


# ---------------------------------------------------------------- copper

def pad_shape(pad, layer):
    c = xy(pad.GetPosition())
    sz = call(pad, "GetSize", layer)
    w, h = mm(sz.x), mm(sz.y)
    if call(pad, "GetShape", layer) == pcbnew.PAD_SHAPE_CIRCLE:
        return "circle", (c, w / 2.0)
    try:
        off = call(pad, "GetOffset", layer)
        ox, oy = mm(off.x), mm(off.y)
    except Exception:
        ox = oy = 0.0
    ang = 0.0
    try:
        ang = float(pad.GetOrientationDegrees())
    except Exception:
        pass
    pts = geo.rect_poly((0.0, 0.0), w, h, 0.0)
    pts = [geo.rot((x + ox, y + oy), -ang) for x, y in pts]
    return "poly", [(c[0] + x, c[1] + y) for x, y in pts]


def collect_copper(board, layers, window=None, skip=(), holes=True, edge=False):
    """Obstacles (geo.Obstacle) of pads, tracks, arcs and vias on `layers` inside window
    (mm; None = whole board). NPTH holes count as copper of no net (net -1); with
    edge=True the Edge.Cuts outline too (net -1, clr = copper-to-edge clearance)."""
    if window is not None:
        x0, y0, x1, y1 = window
        hit = lambda bb: not (bb[2] < x0 or bb[0] > x1 or bb[3] < y0 or bb[1] > y1)
    else:
        hit = lambda bb: True
    layers = list(layers)
    obs = []
    ds = board.GetDesignSettings()
    for fp in board.GetFootprints():
        fb = fp.GetBoundingBox()
        if not hit((mm(fb.GetLeft()), mm(fb.GetTop()), mm(fb.GetRight()), mm(fb.GetBottom()))):
            continue
        for pad in fp.Pads():
            u = uuid(pad)
            if u in skip:
                continue
            net = pad.GetNetCode() or -1
            for L in layers:
                if not pad.IsOnLayer(L):
                    continue
                try:
                    kind, data = pad_shape(pad, L)
                except Exception:
                    continue
                o = geo.Obstacle(kind, data, net, L, id=u)
                if hit(o.bbox):
                    obs.append(o)
            if holes and pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                try:
                    dr = pad.GetDrillSize()
                    o = geo.Obstacle("circle", (xy(pad.GetPosition()), mm(max(dr.x, dr.y)) / 2.0),
                                     -1, None, id=u + "h")
                    if hit(o.bbox):
                        obs.append(o)
                except Exception:
                    pass
    for t in board.GetTracks():
        u = uuid(t)
        if u in skip:
            continue
        cls = t.GetClass()
        net = t.GetNetCode() or -1
        if cls == "PCB_VIA":
            c = xy(t.GetPosition())
            r = mm(call(t, "GetWidth", layers[0] if layers else pcbnew.F_Cu)) / 2.0
            o = geo.Obstacle("circle", (c, r), net, None, id=u)
            if hit(o.bbox):
                obs.append(o)
        elif t.GetLayer() in layers:
            h = mm(t.GetWidth()) / 2.0
            if cls == "PCB_ARC":
                pts = geo.arc_points(xy(t.GetStart()), xy(t.GetMid()), xy(t.GetEnd()), 6)
            else:
                pts = [xy(t.GetStart()), xy(t.GetEnd())]
            for a, b in zip(pts, pts[1:]):
                o = geo.Obstacle("seg", (a, b, h), net, t.GetLayer(), id=u)
                if hit(o.bbox):
                    obs.append(o)
    if edge:
        try:
            eclr = mm(ds.m_CopperEdgeClearance)
        except Exception:
            eclr = 0.3
        for d in list(board.GetDrawings()) + [g for fp in board.GetFootprints() for g in fp.GraphicalItems()]:
            try:
                if d.GetLayer() != pcbnew.Edge_Cuts:
                    continue
                for a, b in edge_segments(d):
                    o = geo.Obstacle("seg", (a, b, 0.0), -1, None, id="edge", clr=eclr)
                    if hit(o.bbox):
                        obs.append(o)
            except Exception:
                pass
    return obs


def edge_segments(shape):
    t = shape.GetShape()
    if t == pcbnew.SHAPE_T_SEGMENT:
        return [(xy(shape.GetStart()), xy(shape.GetEnd()))]
    if t == pcbnew.SHAPE_T_ARC:
        pts = geo.arc_points(xy(shape.GetStart()), xy(shape.GetArcMid()), xy(shape.GetEnd()))
        return list(zip(pts, pts[1:]))
    if t == pcbnew.SHAPE_T_CIRCLE:
        cx, cy = xy(shape.GetCenter())
        r = mm(shape.GetRadius())
        pts = [(cx + r * math.cos(k * math.pi / 12), cy + r * math.sin(k * math.pi / 12)) for k in range(25)]
        return list(zip(pts, pts[1:]))
    if t == pcbnew.SHAPE_T_RECT:
        (x0, y0), (x1, y1) = xy(shape.GetStart()), xy(shape.GetEnd())
        c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [(c[k], c[(k + 1) % 4]) for k in range(4)]
    if t == pcbnew.SHAPE_T_POLY:
        ol = shape.GetPolyShape().Outline(0)
        pts = [xy(ol.CPoint(k)) for k in range(ol.PointCount())]
        return list(zip(pts, pts[1:] + pts[:1]))
    return []


def board_outline(board):
    """Edge.Cuts as a list of segments (mm)."""
    out = []
    for d in board.GetDrawings():
        try:
            if d.GetLayer() == pcbnew.Edge_Cuts:
                out += edge_segments(d)
        except Exception:
            pass
    return out


def write_log(board, filename, header, lines):
    """Append a block to <filename> next to the board file (ignored if not writable)."""
    try:
        import datetime
        path = os.path.join(os.path.dirname(board.GetFileName()) or ".", filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), header))
            for ln in lines:
                f.write("  %s\n" % ln)
        return path
    except Exception:
        return None
