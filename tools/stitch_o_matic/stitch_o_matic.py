# stitch-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Stitching vias, three ways:
#   Fence - select tracks: rows of vias on one or both sides (RF / guard fence).
#   Fill  - select zones: a square or hexagonal grid of vias inside them.
#   Ring  - select nothing (or one zone): vias along the board edge (or the zone edge).
# Vias that would break a rule are left out: clearance to other nets (netclass), pads,
# hole to hole, the board outline, optionally outside the zones of the net. Changes go
# straight to the board; OK keeps them, Cancel removes them. One undo step (Ctrl+Z).
# Selected free vias of the chosen net (an earlier fence) are replaced.

import os

import pcbnew
import wx

from . import geo
from . import geometry as g
from . import kc
from .dialog import StitchDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKS = ("PCB_TRACK", "PCB_ARC")


def poly_points(chain):
    return [kc.xy(chain.CPoint(k)) for k in range(chain.PointCount())]


def zone_areas(zone):
    """[(outline, [holes])] of a zone, mm."""
    out = []
    ps = zone.Outline()
    for i in range(ps.OutlineCount()):
        holes = []
        try:
            for j in range(ps.HoleCount(i)):
                holes.append(poly_points(ps.CHole(i, j)))
        except Exception:
            pass
        out.append((poly_points(ps.COutline(i)), holes))
    return out


def copper_layers(board):
    try:
        return [L for L in board.GetEnabledLayers().CuStack()]
    except Exception:
        return [pcbnew.F_Cu, pcbnew.B_Cu]


class Model:
    def __init__(self, board):
        self.board = board
        self.edits = kc.Edits(board)
        self.proj = kc.project_netclasses(board)
        self.pool, self.spare = [], []
        self.grids = None
        self.ncs = {}

    # -------------------------------------------------------- selection
    def load(self):
        self.clear()
        b = self.board
        self.tracks = [t for t in b.GetTracks() if t.IsSelected() and t.GetClass() in TRACKS]
        self.sel_vias = [t for t in b.GetTracks() if t.IsSelected() and t.GetClass() == "PCB_VIA"]
        self.zones = [z for z in b.Zones() if z.IsSelected()]
        self.pieces = []
        for t in self.tracks:
            a, c = kc.xy(t.GetStart()), kc.xy(t.GetEnd())
            if geo.dist(a, c) < 1e-6:
                continue
            if t.GetClass() == "PCB_ARC":
                self.pieces.append(g.Piece(kc.uuid(t), "arc", a, c, kc.mm(t.GetWidth()), kc.xy(t.GetMid())))
            else:
                self.pieces.append(g.Piece(kc.uuid(t), "seg", a, c, kc.mm(t.GetWidth())))
        ends = set()
        for t in b.GetTracks():
            if t.GetClass() in TRACKS:
                ends.add(geo.key(kc.xy(t.GetStart())))
                ends.add(geo.key(kc.xy(t.GetEnd())))
        # free vias: no track ends on them (an earlier fence / stitching)
        self.free = [v for v in self.sel_vias if geo.key(kc.xy(v.GetPosition())) not in ends]
        self.outlines = g.outline_polys(kc.board_outline(b))
        self.zone_polys = {}
        for z in b.Zones():
            try:
                if z.GetIsRuleArea() if hasattr(z, "GetIsRuleArea") else z.GetIsKeepout():
                    continue
            except Exception:
                pass
            self.zone_polys.setdefault(z.GetNetname(), []).extend(zone_areas(z))
        self.grids = None

    def default_mode(self):
        if self.pieces:
            return g.FENCE
        if self.zones:
            return g.FILL
        return g.RING

    def summary(self):
        parts = []
        if self.pieces:
            parts.append("%d tracks" % len(self.pieces))
        if self.zones:
            parts.append("%d zone%s" % (len(self.zones), "" if len(self.zones) == 1 else "s"))
        if self.free:
            parts.append("%d old vias to replace" % len(self.free))
        if not parts:
            parts.append("nothing selected: Ring along the board edge")
        return ", ".join(parts)

    # -------------------------------------------------------- board state
    def clear(self):
        """Take the new vias off the board and put the replaced ones back."""
        for v in self.pool:
            try:
                self.board.Remove(v)
            except Exception:
                pass
        self.spare += self.pool
        self.pool = []
        self.edits.restore()

    def build_grids(self):
        """Copper, pads and holes of the board without the vias that may be replaced."""
        if self.grids is not None:
            return self.grids
        b = self.board
        layers = copper_layers(b)
        skip = {kc.uuid(v) for v in self.free}
        cu = kc.collect_copper(b, layers, None, skip=skip, holes=True, edge=True)
        pads, holes = [], []
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                u = kc.uuid(pad)
                for L in layers:
                    if pad.IsOnLayer(L):
                        try:
                            kind, data = kc.pad_shape(pad, L)
                        except Exception:
                            continue
                        pads.append(geo.Obstacle(kind, data, pad.GetNetCode(), L, id=u))
                try:
                    dr = pad.GetDrillSize()
                    if dr.x > 0:
                        holes.append(geo.Obstacle("circle", (kc.xy(pad.GetPosition()), kc.mm(max(dr.x, dr.y)) / 2.0),
                                                  0, None, id=u))
                except Exception:
                    pass
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA" and kc.uuid(t) not in skip:
                holes.append(geo.Obstacle("circle", (kc.xy(t.GetPosition()), kc.mm(t.GetDrillValue()) / 2.0),
                                          0, None, id=kc.uuid(t)))
        ds = b.GetDesignSettings()
        try:
            h2h = kc.mm(ds.m_HoleToHoleMin)
        except Exception:
            h2h = 0.25
        self.grids = dict(copper=geo.Grid(cu, 1.0), pads=geo.Grid(pads, 1.0), holes=geo.Grid(holes, 1.0),
                          h2h=h2h)
        return self.grids

    def netclass(self, name):
        if name not in self.ncs:
            net = kc.net_by_name(self.board, name)
            v = pcbnew.PCB_VIA(self.board)
            if net is not None:
                v.SetNet(net)
            self.ncs[name] = kc.netclass(v, self.board, self.proj)
        return self.ncs[name]

    def track_clearance(self):
        out = 0.0
        for t in self.tracks:
            out = max(out, kc.netclass(t, self.board, self.proj)["clearance"])
        return out

    # -------------------------------------------------------- one change
    def apply(self, v):
        self.clear()
        name = v["netname"]
        net = kc.net_by_name(self.board, name)
        code = net.GetNetCode() if net is not None else -1
        nc = self.netclass(name)
        s = dict(v)
        s["d"] = v["d"] or nc["via_d"]
        s["drill"] = v["drill"] or nc["via_drill"]
        iss = g.issues()
        mode = v["mode"]
        # replaced: selected free vias of this net
        for old in self.free:
            if old.GetNetCode() == code:
                self.edits.remove(old)
        gr = self.build_grids()
        extra_cu, extra_holes = geo.Grid(cell=1.0), geo.Grid(cell=1.0)
        for old in self.free:
            if old.GetNetCode() != code:          # stays: its copper and hole count
                c = kc.xy(old.GetPosition())
                extra_cu.add(geo.Obstacle("circle", (c, kc.mm(kc.call(old, "GetWidth", pcbnew.F_Cu)) / 2.0),
                                          old.GetNetCode(), None))
                extra_holes.add(geo.Obstacle("circle", (c, kc.mm(old.GetDrillValue()) / 2.0), 0, None))
        if mode == g.FENCE:
            s.update(pitch=v["pitch"], offset=v["offset"])
            cands = g.fence(self.pieces, s) if self.pieces else []
        elif mode == g.FILL:
            areas = [a for z in self.zones for a in zone_areas(z)]
            s.update(pitch=v["fpitch"], offset=v["margin"], stagger=v["hexa"])
            cands = g.fill(areas, s, s["d"] / 2.0)
        else:
            polys = [a[0] for z in self.zones[:1] for a in zone_areas(z)] or self.outlines
            if not polys:
                iss.add("nooutline")
            s.update(pitch=v["rpitch"], offset=v["inset"])
            cands = g.ring(polys, s)
        zone = None
        if v.get("inside"):
            areas = self.zone_polys.get(name, [])
            if not areas:
                iss.add("nozone")
            zone = (lambda p, A=areas: any(geo.inside(p, ol) and not any(geo.inside(p, h) for h in hs)
                                           for ol, hs in A))
        rules = g.Rules(copper=(gr["copper"], extra_cu), pads=gr["pads"], holes=(gr["holes"], extra_holes),
                        outlines=self.outlines or None, zone=zone, h2h=gr["h2h"])
        pts, skipped = g.accept(cands, rules, s, code, nc["clearance"])
        if cands and not pts:
            iss.add("none")
        gap = None
        if mode == g.FENCE and self.pieces:
            wmax = max(p.w for p in self.pieces)
            gap = v["offset"] - s["d"] / 2.0 - wmax / 2.0
            need = max(nc["clearance"], self.track_clearance())
            if gap < need - 1e-9 and any(t.GetNetCode() != code for t in self.tracks):
                iss.add("close", None, need - gap)
        pitch = s["pitch"]
        if pitch < s["d"]:
            iss.add("small", None, pitch)
        self.place(pts, net, s)
        return dict(points=pts, skipped=skipped, issues=iss, gap=gap, nc=nc, cands=len(cands))

    def place(self, pts, net, s):
        while len(self.pool) < len(pts):
            if self.spare:
                via = self.spare.pop()
            else:
                via = pcbnew.PCB_VIA(self.board)
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            self.board.Add(via)
            self.pool.append(via)
        for via, p in zip(self.pool, pts):
            via.SetPosition(kc.P(p))
            via.SetWidth(kc.iu(s["d"]))
            via.SetDrill(kc.iu(s["drill"]))
            if net is not None:
                via.SetNet(net)
            try:
                via.SetIsFree(True)
            except Exception:
                pass


_running = [False]


class StitchOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Routing"
        self.description = "Stitching vias: a fence along tracks, a grid in zones, a ring along the board edge"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "stitch_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "stitch_o_matic_dark.png")

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
        model.load()
        nets = kc.net_names(board)
        if not nets:
            wx.MessageBox("The board has no nets: stitching vias need one (GND).", NAME)
            return
        default_net = "GND" if "GND" in nets else (model.zones[0].GetNetname() if model.zones else nets[0])
        state = dict(key=None, info="", warnings=[], left="")

        def key_of(v):
            return tuple(sorted((k, str(x)) for k, x in v.items() if k not in ("nudge", "more")))

        def apply(v):
            if state["key"] == key_of(v):
                return dict(info=state["info"], warnings=state["warnings"], left=state["left"])
            r = model.apply(v)
            n = len(r["points"])
            info = "%d vias, %s" % (n, v["netname"])
            sk = g.skipped_text(r["skipped"])
            left = ("left out: " + sk) if sk else ""
            warnings = r["issues"].text()
            state.update(key=key_of(v), info=info, warnings=warnings, left=left)
            kc.refresh()
            ro = dict(count="%d of %d" % (n, r["cands"]), gap="–" if r["gap"] is None else "%.3f mm" % r["gap"])
            return dict(info=info, warnings=warnings, left=left, ro=ro,
                        nc=dict(d=r["nc"]["via_d"], drill=r["nc"]["via_drill"]))

        def reselect():
            model.load()
            state["key"] = None
            return (model.summary(), None)

        defaults = dict(nets=nets, net_default=default_net, mode=model.default_mode(), nc={})
        dlg = StitchDialog(kc.pcb_frame(), HERE, model.summary(), apply, reselect, defaults)
        dlg.tg["mode"][1] = model.default_mode()
        dlg.update_enabled()
        wx.CallAfter(dlg.refresh)
        ok = dlg.run()
        try:
            v = dlg.values()
        except ValueError:
            v = None
        dlg.Destroy()
        if ok and v is not None:
            if state["key"] != key_of(v):
                apply(v)
            kc.write_log(board, "stitch_o_matic.log",
                         ", ".join("%s=%s" % (k, v.get(k)) for k in sorted(v) if k not in ("nudge", "more", "nets")),
                         [state["info"], state["left"]] + ["! " + w for w in state["warnings"]])
            if state["warnings"]:
                wx.MessageBox("\n".join(state["warnings"]) + "\n\n(also in stitch_o_matic.log next to the board)",
                              NAME + " - problems")
        else:
            model.clear()
            if ok:
                wx.MessageBox("Invalid number in the dialog, nothing was changed.", NAME)
        kc.refresh()
