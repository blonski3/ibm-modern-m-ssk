# via-o-tronic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
# (formerly "Fanout Vias")
#
# Select pads and/or track segments (e.g. the inner pins of an aQFN), then run
# Tools -> External Plugins -> via-o-tronic (or the toolbar button).
# For every selected item that has a net, the plugin adds a track and one or more vias
# (several vias per pad: side by side, one behind another or a 2-row grid, joined by
# short tracks). Track routing modes:
#   - lead / 45 deg / lead: straight lead from the pad (A), 45 deg jog, straight lead
#     into the via (B); the via row can be shifted sideways (S) - the classic aQFN fanout;
#   - 45 deg bend at the via or at the pad, straight;
#   - autoroute: a grid router (router.py) finds a 0/45/90 deg path that keeps the
#     netclass clearance to pads, tracks, vias, NPTH holes and Edge.Cuts of other nets,
#     and moves a via that would collide to the nearest free spot. Zones are ignored.
# All dimensions are edited on a pictogram (dialog.py). Via size, drill and track width
# come from each net's netclass unless typed in. The dialog is modeless: the board stays
# usable (zoom, pan, select other pads and press "Use current selection"); the result is
# previewed live. OK keeps it, Cancel removes it. Everything is a single undo step
# (Ctrl+Z). Run DRC afterwards.

import fnmatch
import json
import math
import os

import pcbnew
import wx

from . import geometry as g
from . import router as rt
from .dialog import ViaDialog, GROUPS, NAME

HERE = os.path.dirname(os.path.abspath(__file__))

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


class ObstacleCache:
    """Obstacles per copper layer, collected once for a window and reused by every
    preview while the dialog is open (the board is not edited meanwhile; our own preview
    items are skipped). A request outside the cached window collects again, larger."""

    def __init__(self, board):
        self.board = board
        self.data = {}             # layer -> (window, obstacles)

    def get(self, layer, window, skip):
        w = self.data.get(layer)
        if w is not None:
            (x0, y0, x1, y1), obs = w
            if x0 <= window[0] and y0 <= window[1] and x1 >= window[2] and y1 >= window[3]:
                return obs
        big = (window[0] - 3, window[1] - 3, window[2] + 3, window[3] + 3)
        obs = collect_obstacles(self.board, layer, big, skip)
        self.data[layer] = (big, obs)
        return obs


def _near(obs, pts, pad):
    """Obstacles whose bounding box comes within pad of the bounding box of pts."""
    x0 = min(q[0] for q in pts) - pad
    y0 = min(q[1] for q in pts) - pad
    x1 = max(q[0] for q in pts) + pad
    y1 = max(q[1] for q in pts) + pad
    return [o for o in obs if not (o.bbox[2] < x0 or o.bbox[0] > x1 or o.bbox[3] < y0 or o.bbox[1] > y1)]


def _clear_path(obs, r, width, via_d, clr, res):
    pts = list(r["path"]) + list(r["vias"])
    local = _near(obs, pts, max(width, via_d) + clr + 0.5)
    step = max(0.01, min(res, width / 2.0))
    for a, b in list(zip(r["path"], r["path"][1:])) + list(r["bars"]):
        if not rt.segment_clear(local, a, b, width / 2.0, clr, step):
            return False
    return all(rt.clear_of(local, q[0], q[1], via_d / 2.0, clr) for q in r["vias"])


def route_around(board, result, sources, meta, sizes, ncv, v, skip, issues, cache,
                 only_colliding):
    """Autoroute (only_colliding=False) or obstacle avoidance (True): a planned track
    that would hit copper of another net (pads, tracks, vias, NPTH, board edge, the other
    planned vias) is rerouted on the grid router, and a colliding via is moved to the
    nearest free spot. Tracks that are clear keep their planned shape."""
    pts = [(s["x"], s["y"]) for s in sources] + [q for r in result for q in r["vias"]]
    m = v["ar_margin"] * 3.5 + 1.0
    window = (min(q[0] for q in pts) - m, min(q[1] for q in pts) - m,
              max(q[0] for q in pts) + m, max(q[1] for q in pts) + m)
    order = sorted(range(len(result)), key=lambda k: math.dist(
        (sources[k]["x"], sources[k]["y"]), result[k]["via"]))     # shortest first
    added = {}                  # layer -> obstacles created by this run
    rerouted = []
    for k in order:
        r, (net, layer), (via_d, _drill, width), n = result[k], meta[k], sizes[k], ncv[k]
        base = cache.get(layer, window, skip)
        code = net.GetNetCode()
        # vias planned for the other items count as obstacles too
        planned = [rt.Obstacle("circle", (q[0], q[1], sizes[j][0] / 2.0), meta[j][0].GetNetCode())
                   for j in range(len(result)) if j != k for q in result[j]["vias"]]
        obs = rt.blocking(base + added.get(layer, []) + planned, code)
        if only_colliding and _clear_path(obs, r, width, via_d, n["clearance"], v["ar_grid"]):
            pass
        else:
            start = (sources[k]["x"], sources[k]["y"])
            offs = [(q[0] - r["via"][0], q[1] - r["via"][1]) for q in r["vias"]]
            spot = rt.find_free_spot(obs, r["via"], offs, via_d / 2.0, n["clearance"],
                                     v["ar_grid"], v["ar_margin"])
            if spot is None:
                issues.add("no_spot", k + 1)
            elif spot != r["via"]:
                _shift(r, spot[0] - r["via"][0], spot[1] - r["via"][1])
            path, snap = rt.route(start, r["via"], obs, width, n["clearance"], res=v["ar_grid"],
                                  grows=(1.0,) if only_colliding else (1.0, 2.0, 3.5),
                                  margin=v["ar_margin"])
            if path is None:
                issues.add("no_route", k + 1)
            else:
                _shift(r, snap[0] - r["via"][0], snap[1] - r["via"][1])
                r["path"] = path
                rerouted.append(k + 1)
            for q in r["vias"]:
                if not rt.clear_of(rt.blocking(base, code), q[0], q[1], via_d / 2.0, n["clearance"]):
                    issues.add("via_clr", k + 1)
                    break
        new = added.setdefault(layer, [])
        for a, b in list(zip(r["path"], r["path"][1:])) + list(r["bars"]):
            new.append(rt.Obstacle("seg", (a[0], a[1], b[0], b[1], width / 2.0), code))
        for q in r["vias"]:
            for L in set(list(added.keys()) + [pcbnew.F_Cu, pcbnew.B_Cu]):
                added.setdefault(L, []).append(rt.Obstacle("circle", (q[0], q[1], via_d / 2.0), code))
    return sorted(rerouted)


def build(board, pads, tracks, ncv, v, skip=frozenset(), cache=None):
    """Create (but do not keep) tracks and vias for settings v. Returns (items, warnings)."""
    # 0 (empty field) = take the value from the item's netclass
    sizes = [(v["via_d"] or n["via_d"], v["via_drill"] or n["via_drill"], v["width"] or n["width"])
             for n in ncv]
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

    max_w = max(s[2] for s in sizes)
    up = lambda x: math.ceil(x * 100 - 1e-6) / 100.0          # round up to 0.01 mm
    zig = bool(v.get("zigzag"))
    if v["pitch_mode"] == 0:      # auto: smallest legal pitch
        if zig:                   # a track must pass between two near vias
            pitch = up(max(gwidth + max_via + 2 * max_clr + max_w, 0) / 2.0)
        else:
            pitch = up(gwidth + max_via + max_clr)
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

    stagger = 0.0
    if zig:
        if v.get("zig"):
            stagger = v["zig"]
        else:                     # auto: neighbouring vias just keep the clearance
            p_eff = pitch
            if p_eff <= 0:        # as pins: smallest spacing of the pins along the row
                _, pv = g.axes(v["angle"])
                ss = sorted(s_["x"] * pv[0] + s_["y"] * pv[1] for s_ in sources)
                p_eff = min([b - a for a, b in zip(ss, ss[1:]) if b - a > 1e-6] or [0.0])
            need = gwidth + max_via + max_clr
            stagger = up(math.sqrt(max(0.0, need * need - p_eff * p_eff)))
    issues = g.Issues()
    result, _w = g.plan(sources, v["angle"], v["dist"], pitch, max_via,
                              align=v["align"], ref=v["ref"], line=v["line"],
                              route=v["route"], min_gap=max_clr,
                              profile=v["profile_id"], step=v["step"], custom=v["custom_list"],
                              vias_per=count, group_spacing=gspace, group_mode=gmode,
                              lead_pad=v["lead_pad"], lead_via=v["lead_via"],
                              slack=v["slack_id"], shift=v["shift"],
                              stagger=stagger, track_w=max_w, issues=issues)
    rerouted = []
    if v["route"] == g.ROUTE_AUTO or v.get("avoid"):
        if cache is None:
            cache = ObstacleCache(board)
        rerouted = route_around(board, result, sources, meta, sizes, ncv, v, skip, issues,
                                cache, only_colliding=v["route"] != g.ROUTE_AUTO)
    warnings = issues.text()

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
    widths = sorted(set(round(z[2], 3) for z in sizes))
    info = "P %s, track %s mm" % ("as pins" if pitch == 0 else "%g" % pitch,
                                  "/".join("%g" % w for w in widths))
    if zig:
        info += ", Z %g mm%s" % (stagger, "" if v.get("zig") else " (auto)")
    if count > 1:
        info += ", group %g mm" % gspace
    lengths = [sum(math.dist(a, b) for a, b in zip(r["path"], r["path"][1:])) for r in result]
    lo, hi = min(lengths), max(lengths)
    info += (", L %.2f mm" % lo) if hi - lo < 0.005 else (", L %.2f\u2013%.2f mm" % (lo, hi))
    if rerouted and v["route"] != g.ROUTE_AUTO:
        info += ", avoided: %s" % ",".join(str(k) for k in rerouted)
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


def write_log(board, v, info, warnings):
    """Append what was placed and what failed to via_o_tronic.log next to the board file."""
    try:
        import datetime
        path = os.path.join(os.path.dirname(board.GetFileName()) or ".", "via_o_tronic.log")
        keys = ("route", "slack_id", "zigzag", "zig", "dist", "lead_pad", "lead_via", "shift",
                "pitch_mode", "pitch", "width", "via_d", "via_drill", "angle", "avoid")
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   ", ".join("%s=%s" % (k, v.get(k)) for k in keys)))
            f.write("  %s\n" % info.split("\n")[0])
            for w in warnings:
                f.write("  ! %s\n" % w)
    except Exception:
        pass


def remove(board, items):
    for it in items:
        try:
            board.Remove(it)
        except Exception:
            pass


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
            lines.append("%s: via %g/%g, track %g, clr %g mm"
                         % (n["name"], n["via_d"], n["via_drill"], n["width"], n["clearance"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- plugin

_running = [False]


class ViaOTronic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Routing"
        self.description = "Fan out the selected pads or track ends to a row of vias (lead / 45 deg / lead, autoroute)"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "via_o_tronic.png")
        self.dark_icon_file_name = os.path.join(HERE, "via_o_tronic_dark.png")

    def Run(self):
        if _running[0]:
            wx.MessageBox(NAME + " is already open.", NAME)
            return
        _running[0] = True
        try:
            self._run()
        finally:
            _running[0] = False

    def _run(self):
        board = pcbnew.GetBoard()
        state = dict(items=[], warnings=[], key=None, skip=set(), cache=ObstacleCache(board))
        pads, tracks = selection(board, state["skip"])
        if not pads and not tracks:
            wx.MessageBox("Select pads or track segments that have a net.", NAME)
            return

        proj = _project_netclasses(board)
        sel = dict(pads=pads, tracks=tracks,
                   ncv=[netclass_values(it, board, proj) for it in pads + tracks])

        first = sel["ncv"][0]
        defaults = dict(pitch=round(first["via_d"] + first["clearance"], 3),
                        nc=dict(width=first["width"], via_d=first["via_d"],
                                via_drill=first["via_drill"]))

        def key_of(v):
            return (tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("live", "pos", "nudge", "more", "nc"))),
                    tuple(_uuid(p) for p in sel["pads"]) + tuple(_uuid(t) for t in sel["tracks"]))

        def clear_preview():
            remove(board, state["items"])
            state["items"], state["warnings"], state["key"] = [], [], None
            state["skip"] = set()

        def make(v):
            clear_preview()
            state["items"], state["warnings"], info = build(
                board, sel["pads"], sel["tracks"], sel["ncv"], v, cache=state["cache"])
            state["skip"] = set(_uuid(it) for it in state["items"])
            state["key"] = key_of(v)
            state["last_info"] = info
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
                return "(nothing with a net selected, kept the previous selection)"
            sel.update(pads=p, tracks=t, ncv=[netclass_values(it, board, proj) for it in p + t])
            state["key"] = None
            return summarize(sel["ncv"])

        dlg = ViaDialog(pcb_frame(), defaults, summarize(sel["ncv"]), preview, reselect, HERE)
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
            write_log(board, v, state.get("last_info", ""), state["warnings"])
            if state["warnings"]:
                wx.MessageBox("\n".join(state["warnings"]) + "\n\n(also in via_o_tronic.log next to the board)",
                              NAME + " - problems")
        else:
            clear_preview()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was added.", NAME)
        # no Refresh here: KiCad rebuilds the view and the connectivity itself right after
        # Run() returns (RebuildAndRefresh), a second full rebuild only costs time
