# spacing-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Select the straight parts of several parallel tracks (a bus, at any angle; selecting
# whole tracks with their 45 deg leads is fine too), then run
# Tools -> External Plugins -> spacing-o-matic (or the toolbar button).
# The dialog shows the spacing measured now (pitch = centre to centre, gap = edge to
# edge) and sets it to one value (or one value per pair): every track is moved sideways,
# its neighbouring segments slide along (45 deg stays 45 deg) or get a 45 deg jog where
# the end cannot move (pad, via, junction). The dialog is modeless and every change is applied to the board at once;
# OK keeps the result, Cancel puts everything back. Everything is a single undo step
# (Ctrl+Z). Run DRC afterwards (zones are refilled by KiCad / with B).

import fnmatch
import json
import math
import os

import pcbnew
import wx

from . import geometry as g
from .dialog import SpacingDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))
IU = 1e6                     # KiCad internal units (nm) per mm


def mm(v):
    return v / IU


def xy(v):
    return (v.x / IU, v.y / IU)


def P(p):
    return pcbnew.VECTOR2I(int(round(p[0] * IU)), int(round(p[1] * IU)))


def _uuid(item):
    try:
        return item.m_Uuid.AsString()
    except Exception:
        return str(id(item))


# ---------------------------------------------------------------- netclass clearance

def _project_netclasses(board):
    try:
        pro = os.path.splitext(board.GetFileName())[0] + ".kicad_pro"
        with open(pro, encoding="utf-8") as f:
            ns = json.load(f)["net_settings"]
    except Exception:
        return None
    return dict(classes={c["name"]: c for c in ns.get("classes", [])},
                patterns=ns.get("netclass_patterns") or [],
                assignments=ns.get("netclass_assignments") or {})


def _clr_project(proj, netname):
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
    v = cls.get("clearance") or default.get("clearance")
    return (cls.get("name", "Default"), float(v)) if v else None


def _clr_api(item, board):
    for get in (lambda: item.GetEffectiveNetClass(),
                lambda: item.GetNet().GetNetClass(),
                lambda: board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(item.GetNetname())):
        try:
            nc = get()
            if nc is not None:
                c = nc.GetClearance()
                if c > 0:
                    return (str(nc.GetName()), mm(c))
        except Exception:
            pass
    return None


def clearance(item, board, proj):
    """(netclass name, clearance mm): KiCad API first; the project file wins when the API
    only knows 'Default' (composite netclasses in KiCad 9/10)."""
    api = _clr_api(item, board)
    pro = _clr_project(proj, item.GetNetname())
    if api and (api[0] not in ("Default", "") or not pro or pro[0] == "Default"):
        return api
    if pro:
        return pro
    if api:
        return api
    try:
        return ("(board)", mm(board.GetDesignSettings().m_MinClearance))
    except Exception:
        return ("(board)", 0.2)


# ---------------------------------------------------------------- copper around the bus

def _call(obj, name, layer):
    fn = getattr(obj, name)
    try:
        return fn(layer)
    except (TypeError, NotImplementedError):
        return fn()


def _pad_angle(pad):
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


def pad_shape(pad, layer):
    """('circle', (c, r)) or ('poly', corners) of the pad on layer (rounded corners are
    taken as square, i.e. slightly pessimistic)."""
    c = xy(pad.GetPosition())
    sz = _call(pad, "GetSize", layer)
    w, h = mm(sz.x), mm(sz.y)
    shape = _call(pad, "GetShape", layer)
    if shape == pcbnew.PAD_SHAPE_CIRCLE:
        return "circle", (c, w / 2.0)
    try:
        off = _call(pad, "GetOffset", layer)
        ox, oy = mm(off.x), mm(off.y)
    except Exception:
        ox = oy = 0.0
    a = -math.radians(_pad_angle(pad))         # KiCad angles are counter-clockwise, y down
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        x, y = dx + ox, dy + oy
        pts.append((c[0] + x * ca - y * sa, c[1] + x * sa + y * ca))
    return "poly", pts


def collect_copper(board, layers, window):
    """Pads, tracks, arcs and vias on the given copper layers inside window (mm)."""
    x0, y0, x1, y1 = window
    hit = lambda bb: not (bb[2] < x0 or bb[0] > x1 or bb[3] < y0 or bb[1] > y1)
    obs = []
    for fp in board.GetFootprints():
        fb = fp.GetBoundingBox()
        if not hit((mm(fb.GetLeft()), mm(fb.GetTop()), mm(fb.GetRight()), mm(fb.GetBottom()))):
            continue
        for pad in fp.Pads():
            net = pad.GetNetCode() or -1
            for L in layers:
                if not pad.IsOnLayer(L):
                    continue
                try:
                    kind, data = pad_shape(pad, L)
                except Exception:
                    continue
                o = g.Obstacle(kind, data, net, L, id=_uuid(pad))
                if hit(o.bbox):
                    obs.append(o)
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                try:
                    dr = pad.GetDrillSize()
                    o = g.Obstacle("circle", (xy(pad.GetPosition()), mm(max(dr.x, dr.y)) / 2.0),
                                   -1, None, id=_uuid(pad) + "h")
                    if hit(o.bbox):
                        obs.append(o)
                except Exception:
                    pass
    for t in board.GetTracks():
        cls = t.GetClass()
        net = t.GetNetCode() or -1
        if cls == "PCB_VIA":
            c = xy(t.GetPosition())
            r = mm(_call(t, "GetWidth", layers[0])) / 2.0
            o = g.Obstacle("circle", (c, r), net, None, id=_uuid(t))
            if hit(o.bbox):
                obs.append(o)
        elif t.GetLayer() in layers:
            h = mm(t.GetWidth()) / 2.0
            if cls == "PCB_ARC":
                pts = _arc_pts(xy(t.GetStart()), xy(t.GetMid()), xy(t.GetEnd()), 6)
            else:
                pts = [xy(t.GetStart()), xy(t.GetEnd())]
            for a, b in zip(pts, pts[1:]):
                o = g.Obstacle("seg", (a, b, h), net, t.GetLayer(), id=_uuid(t))
                if hit(o.bbox):
                    obs.append(o)
    return obs


# ---------------------------------------------------------------- model

class Model:
    """The selected bus and everything needed to move it in place and back.
    Items are edited in place (SetStart/SetEnd/SetWidth); originals are kept so a change
    can be undone exactly. New 45 deg jogs are separate PCB_TRACKs."""

    def __init__(self, board):
        self.board = board
        self.proj = _project_netclasses(board)
        self.orig = {}            # uuid -> (start, end, width) in IU
        self.created = []
        self.items = {}           # uuid -> PCB_TRACK
        self.bus = None
        self.grid = None
        self.window = None
        self.tol = None

    # -- selection
    def selected_tracks(self):
        made = set(_uuid(t) for t in self.created)
        tr, arcs = [], 0
        for t in self.board.GetTracks():
            if not t.IsSelected() or t.GetNetCode() <= 0 or _uuid(t) in made:
                continue
            if t.GetClass() == "PCB_TRACK":
                tr.append(t)
            elif t.GetClass() == "PCB_ARC":
                arcs += 1
        return tr, arcs

    def load(self, tracks, tol, arcs=0):
        """Analyse the tracks (KiCad items). Returns the bus."""
        self.restore()
        self.sel = list(tracks)
        self.arcs = arcs
        self.tol = tol
        board = self.board
        nets = set(t.GetNetCode() for t in tracks)
        self.netinfo = {t.GetNetCode(): t.GetNet() for t in tracks}
        self.netname = {t.GetNetCode(): t.GetNetname() for t in tracks}
        self.items = {}
        index, arc_ends, vias = {}, set(), {}
        segs = {}
        for t in board.GetTracks():
            net = t.GetNetCode()
            if net not in nets:
                continue
            cls = t.GetClass()
            if cls == "PCB_TRACK":
                u = _uuid(t)
                s = g.Seg(u, net, t.GetLayer(), xy(t.GetStart()), xy(t.GetEnd()), mm(t.GetWidth()))
                segs[u] = s
                self.items[u] = t
                for p in (s.a, s.b):
                    index.setdefault((net, s.layer, g.key(p)), []).append(s)
            elif cls == "PCB_ARC":
                for p in (xy(t.GetStart()), xy(t.GetEnd())):
                    arc_ends.add((net, t.GetLayer(), g.key(p)))
            elif cls == "PCB_VIA":
                vias.setdefault(net, []).append((xy(t.GetPosition()), mm(_call(t, "GetWidth", pcbnew.F_Cu)) / 2.0))
        pads = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() in nets:
                    pads.setdefault(pad.GetNetCode(), []).append(pad)

        def tracks_at(net, layer, p):
            return index.get((net, layer, g.key(p)), [])

        def anchored(net, layer, p):
            if (net, layer, g.key(p)) in arc_ends:
                return True
            for c, r in vias.get(net, []):
                if math.hypot(p[0] - c[0], p[1] - c[1]) <= r + 1e-6:
                    return True
            vp = P(p)
            for pad in pads.get(net, []):
                try:
                    if pad.IsOnLayer(layer) and pad.HitTest(vp):
                        return True
                except Exception:
                    pass
            return False

        sel = [segs[_uuid(t)] for t in tracks if _uuid(t) in segs]
        self.bus = g.analyze(sel, tracks_at, anchored, tol)
        self.clr, self.ncname = {}, {}
        for t in tracks:
            if t.GetNetCode() not in self.clr:
                name, c = clearance(t, board, self.proj)
                self.clr[t.GetNetCode()] = c
                self.ncname[t.GetNetCode()] = name
        # lane number of every item that may move (for the log)
        self.lane_of = {}
        self.lane_ids = set()
        for L in self.bus.lanes:
            for sg in L["segs"]:
                self.lane_of[sg.id] = L["no"]
                self.lane_ids.add(sg.id)
            for e in L["ends"]:
                if e.get("adj") is not None:
                    self.lane_of[e["adj"].id] = L["no"]
        self.grid = None
        return self.bus

    def copper(self):
        """Spatial grid of the copper around the bus, collected once per selection."""
        if self.grid is None:
            pts = [p for L in self.bus.lanes for sg in L["segs"] for p in (sg.a, sg.b)]
            pts += [e["F"] for L in self.bus.lanes for e in L["ends"] if "F" in e]
            m = 3.0 + 2 * max([abs(L["o"] - self.bus.lanes[0]["o"]) for L in self.bus.lanes] + [0])
            win = (min(p[0] for p in pts) - m, min(p[1] for p in pts) - m,
                   max(p[0] for p in pts) + m, max(p[1] for p in pts) + m)
            layers = sorted(set(L["layer"] for L in self.bus.lanes))
            self.grid = g.Grid(collect_copper(self.board, layers, win), 1.0)
        return self.grid

    # -- editing
    def restore(self):
        for it in self.created:
            try:
                self.board.Remove(it)
            except Exception:
                pass
        self.created = []
        for u, (s, e, w) in self.orig.items():
            t = self.items.get(u)
            if t is not None:
                t.SetStart(pcbnew.VECTOR2I(*s))
                t.SetEnd(pcbnew.VECTOR2I(*e))
                t.SetWidth(w)
        self.orig = {}

    def apply(self, res):
        self.restore()
        for u, (a, b, w) in res["moves"].items():
            t = self.items[u]
            st, en = t.GetStart(), t.GetEnd()
            self.orig[u] = ((st.x, st.y), (en.x, en.y), t.GetWidth())
            t.SetStart(P(a))
            t.SetEnd(P(b))
            t.SetWidth(int(round(w * IU)))
        for net, layer, a, b, w in res["new"]:
            tr = pcbnew.PCB_TRACK(self.board)
            tr.SetStart(P(a))
            tr.SetEnd(P(b))
            tr.SetWidth(int(round(w * IU)))
            tr.SetLayer(layer)
            tr.SetNet(self.netinfo[net])
            self.board.Add(tr)
            self.created.append(tr)

    # -- one evaluation of the settings
    def evaluate(self, v):
        """Plan for settings v, with checks. Returns (res, warnings, info dict)."""
        bus = self.bus
        res = g.plan(bus, dict(mode=v["mode"], value=v["value"], values=v.get("values") or None,
                               width=v["width"], keep=v["keep"], ends=v["ends"],
                               shift=v["shift"], snap=v["snap"]))
        issues = res["issues"]
        if len(bus.lanes) >= 2:
            g.check_gaps(bus.lanes, res["targets"], res["widths"], self.clr, issues)
            if v.get("check"):
                lane_no = dict(self.lane_of)
                segs = [(lane_no.get(u, 0), self.items[u].GetNetCode(), self.items[u].GetLayer(), a, b, w, u)
                        for u, (a, b, w) in res["moves"].items()]
                no_of_net = {L["net"]: L["no"] for L in bus.lanes}
                segs += [(no_of_net[net], net, layer, a, b, w, None) for net, layer, a, b, w in res["new"]]
                g.check_copper(segs, self.copper(), self.clr, set(res["moves"]), issues, self.lane_ids)
        return res, issues.text()


# ---------------------------------------------------------------- texts

def readouts(bus):
    p, gp = g.measure(bus.lanes)
    return dict(now_p=g.span_text(p) + (" mm" if p else ""),
                now_g=g.span_text(gp) + (" mm" if gp else ""),
                mean_p=round(sum(p) / len(p), 4) if p else 0.0,
                mean_g=round(sum(gp) / len(gp), 4) if gp else 0.0,
                width=round(sum(L["w"] for L in bus.lanes) / max(1, len(bus.lanes)), 4))


def summary(model):
    bus = model.bus
    n = len(bus.lanes)
    ang = math.degrees(math.atan2(-bus.u[1], bus.u[0])) % 180.0
    layers = sorted(set(model.board.GetLayerName(L["layer"]) for L in bus.lanes))
    ncs = {}
    for L in bus.lanes:
        ncs.setdefault(model.ncname.get(L["net"], "?"), model.clr.get(L["net"], 0))
    line = "%d track%s, %g°, %s" % (n, "" if n == 1 else "s", round(ang, 1), "/".join(layers))
    line += "\n" + ", ".join("%s clr %g" % (k, c) for k, c in ncs.items())
    extra = []
    if bus.ignored:
        extra.append("%d not parallel" % bus.ignored)
    if model.arcs:
        extra.append("%d arc%s skipped" % (model.arcs, "" if model.arcs == 1 else "s"))
    if extra:
        line += " (" + ", ".join(extra) + ")"
    return line


def write_log(board, v, info, warnings, model):
    try:
        import datetime
        path = os.path.join(os.path.dirname(board.GetFileName()) or ".", "spacing_o_matic.log")
        keys = ("mode", "value", "values", "width", "keep", "ends", "shift", "snap", "check")
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   ", ".join("%s=%s" % (k, v.get(k)) for k in keys)))
            nets = [model.netname.get(L["net"], "?") for L in model.bus.lanes]
            f.write("  tracks: %s\n" % ", ".join("%d=%s" % (k + 1, n) for k, n in enumerate(nets)))
            f.write("  %s\n" % info)
            for w in warnings:
                f.write("  ! %s\n" % w)
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


# ---------------------------------------------------------------- plugin

_running = [False]


class SpacingOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Routing"
        self.description = "Measure and set the spacing (pitch / gap) of the selected parallel tracks"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "spacing_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "spacing_o_matic_dark.png")

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
        model = Model(board)
        tracks, arcs = model.selected_tracks()
        if len(tracks) < 2:
            wx.MessageBox("Select the straight parts of two or more parallel tracks.", NAME)
            return
        tol = _last_tol()
        bus = model.load(tracks, tol, arcs)
        if len(bus.lanes) < 2:
            wx.MessageBox("Need at least two parallel tracks of different nets in the selection.\n"
                          "(found %d)" % len(bus.lanes), NAME)
            return
        state = dict(key=None, res=None, warnings=[], info="")

        def key_of(v):
            return tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("nudge", "more")))

        def run_settings(v):
            if abs(v["tol"] - model.tol) > 1e-9:          # new tolerance: analyse again
                model.load(model.sel, v["tol"], model.arcs)
            res, warnings = model.evaluate(v)
            model.apply(res)
            moved = max([abs(d) for d in res["deltas"]] + [0.0])
            info = "%s %s mm, moved ≤ %.3f mm" % (
                "P" if v["mode"] == g.MODE_PITCH else "G",
                "; ".join("%g" % x for x in v["values"]) if v.get("values") else "%g" % v["value"],
                moved)
            if res["new"]:
                info += ", %d jog%s" % (len(res["new"]), "" if len(res["new"]) == 1 else "s")
            state.update(key=key_of(v), res=res, warnings=warnings, info=info)
            return dict(info=info, warnings=warnings, move="%.3f mm" % moved)

        def preview(v):
            out = readouts(model.bus)
            if state["key"] == key_of(v):
                out.update(info=state["info"], warnings=state["warnings"])
                return out
            out.update(run_settings(v))
            pcbnew.Refresh()
            return out

        def reselect():
            model.restore()
            t, a = model.selected_tracks()
            if len(t) < 2:
                pcbnew.Refresh()
                state["key"] = None
                return ("(select two or more tracks, kept the previous selection)\n" + summary(model), None)
            model.load(t, model.tol, a)
            state["key"] = None
            r = readouts(model.bus)
            return (summary(model), dict(p=r["mean_p"], g=r["mean_g"]))

        r = readouts(bus)
        defaults = dict(mean_p=r["mean_p"], mean_g=r["mean_g"], avg_width=r["width"])
        dlg = SpacingDialog(pcb_frame(), defaults, summary(model), preview, reselect, HERE)
        dlg.set_status(dict(r, info="", warnings=[]))
        wx.CallAfter(dlg.refresh_preview)
        ok = dlg.run()
        try:
            v = dlg.values()
        except ValueError:
            v = None
        dlg.Destroy()

        if ok and v is not None and len(model.bus.lanes) >= 2:
            if state["key"] != key_of(v):            # last edit not applied yet: apply now
                run_settings(v)
            write_log(board, v, state["info"], state["warnings"], model)
            if state["warnings"]:
                wx.MessageBox("\n".join(state["warnings"]) +
                              "\n\n(also in spacing_o_matic.log next to the board)", NAME + " - problems")
        else:
            model.restore()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        pcbnew.Refresh()


def _last_tol():
    from .dialog import _last, DEFAULTS
    try:
        return float(_last.get("tol", DEFAULTS["tol"]))
    except Exception:
        return DEFAULTS["tol"]
