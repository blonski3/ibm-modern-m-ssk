# net-o-matic - KiCad 9/10 action plugin (PCB Editor, Python/SWIG).
#
# Give selected tracks and/or vias (optionally pads and zones) another net, fast: type a
# few letters, the list narrows (nets the copper touches come first), Enter. The board
# follows the highlighted net live; OK keeps it, Cancel restores. ⇄ swaps two nets,
# "+ connected" also takes the copper connected to the selection, ↻ starts the next
# change with a new selection. One undo step (Ctrl+Z) for the whole window.

import collections
import os

import pcbnew
import wx

from . import geo
from . import kc
from . import nets as N
from .dialog import NetDialog, NAME

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ("track", "via", "pad", "zone")


def kind_of(item):
    c = item.GetClass()
    if c in ("PCB_TRACK", "PCB_ARC"):
        return "track"
    if c == "PCB_VIA":
        return "via"
    if c == "PAD":
        return "pad"
    if c == "ZONE":
        return "zone"
    return None


def is_rule_area(z):
    try:
        return z.GetIsRuleArea()
    except AttributeError:
        return z.GetIsKeepout()


def read_selection(board):
    """-> ({kind: [items]}, number of other selected items). Pads count only when picked
    on their own (a selected footprint marks its pads selected too)."""
    sel = {k: [] for k in KINDS}
    other = 0
    for t in board.GetTracks():
        if t.IsSelected():
            sel[kind_of(t)].append(t)
    for fp in board.GetFootprints():
        if fp.IsSelected():
            other += 1
            continue
        for p in fp.Pads():
            if p.IsSelected():
                sel["pad"].append(p)
    for z in board.Zones():
        if z.IsSelected():
            if is_rule_area(z) or not z.IsOnCopperLayer():
                other += 1
            else:
                sel["zone"].append(z)
    for d in board.GetDrawings():
        try:
            if d.IsSelected():
                other += 1
        except Exception:
            pass
    return sel, other


def copper_layers(board):
    out = []
    for L in range(pcbnew.PCB_LAYER_ID_COUNT):
        try:
            if pcbnew.IsCopperLayer(L) and board.IsLayerEnabled(L):
                out.append(L)
        except Exception:
            pass
    return out or [pcbnew.F_Cu, pcbnew.B_Cu]


class NetEdits:
    """Net changes of one step, undone exactly by restore()."""

    def __init__(self, board):
        self.board = board
        self.saved = {}            # uuid -> (item, old net code)
        self.created = []

    def set(self, item, code):
        u = kc.uuid(item)
        if u not in self.saved:
            self.saved[u] = (item, item.GetNetCode())
        item.SetNetCode(code)

    def new_net(self, name):
        ni = pcbnew.NETINFO_ITEM(self.board, name)
        self.board.Add(ni)
        self.created.append(ni)
        return ni

    def restore(self):
        for item, code in self.saved.values():
            try:
                item.SetNetCode(code)
            except Exception:
                pass
        for ni in self.created:
            try:
                self.board.Remove(ni)
            except Exception:
                pass
        self.saved, self.created = {}, []

    def __len__(self):
        return len(self.saved)


class Model:
    def __init__(self, board):
        self.board = board
        self.done = []                       # earlier steps of this window (kept)
        self.edits = NetEdits(board)
        self.applied = None
        self.recent = []
        self.log = []
        self.changed = collections.Counter()
        self.layers = copper_layers(board)
        self._index()
        self.read_nets()
        self.cur = dict(self.net0)
        self.select()

    # ---------------------------------------------------------- board data (once)
    def _index(self):
        """Copper shapes of pads, tracks and vias (geometry does not change here)."""
        self.items, self.by_id, self.kind = {}, {}, {}
        obs = []
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                u = kc.uuid(pad)
                self.items[u], self.kind[u] = pad, "pad"
                for L in self.layers:
                    if not pad.IsOnLayer(L):
                        continue
                    try:
                        k, data = kc.pad_shape(pad, L)
                    except Exception:
                        continue
                    obs.append(geo.Obstacle(k, data, None, L, id=u))
        for t in self.board.GetTracks():
            u = kc.uuid(t)
            k = kind_of(t)
            self.items[u], self.kind[u] = t, k
            if k == "via":
                r = kc.mm(kc.call(t, "GetWidth", self.layers[0])) / 2.0
                obs.append(geo.Obstacle("circle", (kc.xy(t.GetPosition()), r), None, None, id=u))
                continue
            h = kc.mm(t.GetWidth()) / 2.0
            if t.GetClass() == "PCB_ARC":
                pts = geo.arc_points(kc.xy(t.GetStart()), kc.xy(t.GetMid()), kc.xy(t.GetEnd()), 8)
            else:
                pts = [kc.xy(t.GetStart()), kc.xy(t.GetEnd())]
            for a, b in zip(pts, pts[1:]):
                obs.append(geo.Obstacle("seg", (a, b, h), None, t.GetLayer(), id=u))
        for o in obs:
            self.by_id.setdefault(o.id, []).append(o)
        self.grid = geo.Grid(obs, 1.0)
        self.net0 = {u: it.GetNetCode() for u, it in self.items.items()}

    def read_nets(self):
        self.code_of = {}
        try:
            for name, ni in self.board.GetNetsByName().items():
                code = ni.GetNetCode()
                if code > 0 and str(name):
                    self.code_of[str(name)] = code
        except Exception:
            for code in range(1, self.board.GetNetCount()):
                ni = self.board.FindNet(code)
                if ni is not None and ni.GetNetname():
                    self.code_of[str(ni.GetNetname())] = code
        self.name_of = {c: n for n, c in self.code_of.items()}
        self.names = sorted(self.code_of, key=N.natural_key)
        self.pads = collections.Counter(self.net0[u] for u, k in self.kind.items() if k == "pad")
        self.proj = kc.project_netclasses(self.board)

    def net_name(self, code):
        if not code:
            return N.NO_NET_LABEL
        return self.name_of.get(code) or (str(self.board.FindNet(code).GetNetname())
                                          if self.board.FindNet(code) is not None else "?")

    def netclass(self, name):
        if not name or name not in self.code_of:
            return ""
        try:
            nc = kc._nc_project(self.proj, name) if self.proj else None
            if nc and nc.get("name"):
                return nc["name"]
        except Exception:
            pass
        try:
            return str(self.board.FindNet(self.code_of[name]).GetNetClassName())
        except Exception:
            pass
        try:
            return str(self.board.FindNet(self.code_of[name]).GetNetClass().GetName())
        except Exception:
            return ""

    # ---------------------------------------------------------- selection
    def select(self):
        """Take the current selection for the next change (earlier changes stay)."""
        self.sel, self.other = read_selection(self.board)
        self.base = dict(self.cur)
        self._grown = None
        self.applied = None
        seeds = [kc.uuid(it) for k in ("track", "via") for it in self.sel[k]]
        self.now = collections.Counter(self.cur.get(kc.uuid(it), it.GetNetCode())
                                       for k in KINDS for it in self.sel[k])
        self.touch = self._touching(seeds + [kc.uuid(p) for p in self.sel["pad"]])

    def _touching(self, ids):
        """{net code: number of other items} of copper of another net that the selection
        touches (its own net does not count)."""
        ids = set(ids)
        out = collections.Counter()
        for u in ids:
            own = self.cur.get(u)
            for obs in self.by_id.get(u, ()):
                for o in N.touching(self.grid, obs, lambda o: o.id not in ids):
                    n = self.cur.get(o.id)
                    if n and n != own:
                        out[(n, o.id)] += 1
        res = collections.Counter()
        for (n, _o) in out:
            res[n] += 1
        return res

    def grown(self):
        """Tracks / vias connected to the selected ones through copper of the same old
        net (stops at pads). Cached per selection."""
        if self._grown is None:
            seeds = collections.defaultdict(list)
            for k in ("track", "via"):
                for it in self.sel[k]:
                    u = kc.uuid(it)
                    seeds[self.base.get(u)].append(u)
            out = set()
            for net, ids in seeds.items():
                out |= N.grow(self.grid, self.by_id, ids,
                              lambda u, net=net: self.kind.get(u) in ("track", "via") and self.base.get(u) == net)
            self._grown = out
        return self._grown

    def targets(self, v):
        want = {k for k in KINDS if v.get(k + "s")}
        out = [it for k in KINDS if k in want for it in self.sel[k]]
        if v.get("connected"):
            have = {kc.uuid(it) for it in out}
            for u in sorted(self.grown()):
                if u not in have and self.kind.get(u) in want:
                    out.append(self.items[u])
        return out

    def swap_pair(self):
        """The two nets of the selection when there are exactly two (no net excluded)."""
        codes = sorted(c for c in self.now if c)
        return tuple(codes) if len(codes) == 2 else None

    def summary(self):
        parts = []
        for k, word in (("track", "track"), ("via", "via"), ("pad", "pad"), ("zone", "zone")):
            n = len(self.sel[k])
            if n:
                parts.append("%d %s%s" % (n, word, "" if n == 1 else "s"))
        if not parts:
            return "Nothing selected: select tracks / vias, press ↻"
        now = ", ".join("%s ×%d" % (self.net_name(c), n) for c, n in self.now.most_common(3))
        if len(self.now) > 3:
            now += ", …"
        return " · ".join(parts) + "  (now " + now + ")"

    # ---------------------------------------------------------- changing
    def describe(self, u):
        it = self.items.get(u)
        k = self.kind.get(u)
        net = self.net_name(self.cur.get(u))
        if k == "pad":
            try:
                return "%s pad %s (%s)" % (it.GetParent().GetReference(), it.GetNumber(), net)
            except Exception:
                return "pad (%s)" % net
        return "%s (%s)" % (k or "item", net)

    def apply(self, v):
        """Redo the live change with the values v. -> geo.Issues"""
        iss = geo.Issues(N.TEXT)
        self.edits.restore()
        self.cur = dict(self.base)
        self.applied = dict(v)
        self.changed = collections.Counter()
        tg = self.targets(v)
        if self.other:
            iss.add("other", "%d other" % self.other)
        if not tg:
            if any(self.sel.values()) or self.other:
                iss.add("nothing")
            return iss
        if v.get("swap"):
            pair = self.swap_pair()
            if pair is None:
                return iss
            a, b = pair
            plan = [(it, b if it.GetNetCode() == a else a) for it in tg if it.GetNetCode() in pair]
        else:
            name = v.get("net")
            if name is None:
                return iss
            if name == N.NO_NET:
                code = 0
            elif name in self.code_of:
                code = self.code_of[name]
            else:
                code = self.edits.new_net(name).GetNetCode()
                self.name_of[code] = name
                iss.add("newnet", name)
            plan = [(it, code) for it in tg]
        ids = []
        for it, code in plan:
            if it.GetNetCode() == code:
                continue
            self.edits.set(it, code)
            u = kc.uuid(it)
            self.cur[u] = code
            ids.append(u)
            k = kind_of(it)
            self.changed[k] += 1
            if k == "zone":
                iss.add("zone", None)
            elif k == "pad":
                iss.add("pad", "%s.%s" % (it.GetParent().GetReference(), it.GetNumber()))
        for u, o in N.contacts(self.grid, self.by_id, ids, self.cur.get):
            iss.add("short", self.describe(o))
        return iss

    def keep(self):
        """The live change stays; the next one starts from here."""
        if len(self.edits):
            name = (self.applied or {}).get("net")
            if name is not None and not (self.applied or {}).get("swap"):
                if name in self.recent:
                    self.recent.remove(name)
                self.recent.insert(0, name)
                del self.recent[8:]
            v = self.applied or {}
            what = ("swap" if v.get("swap") else
                    N.NO_NET_LABEL if v.get("net") == N.NO_NET else v.get("net"))
            self.log.append("%s: %s" % (what, self.changed_text()))
            self.done.append(self.edits)
            self.edits = NetEdits(self.board)
            if any(e.created for e in self.done):
                self.read_nets()
        self.base = dict(self.cur)

    def restore_all(self):
        self.edits.restore()
        while self.done:
            self.done.pop().restore()
        self.cur = dict(self.net0)

    def shown(self):
        """What the board shows now (to skip a view rebuild when nothing changed)."""
        return frozenset((u, self.cur.get(u)) for u in self.edits.saved)

    def changed_text(self):
        if not self.changed:
            return "-"
        return ", ".join("%d %s%s" % (n, k, "" if n == 1 else "s") for k, n in self.changed.items())

    def done_text(self):
        n = len(self.done) + (1 if len(self.edits) else 0)
        items = sum(len(e) for e in self.done) + len(self.edits)
        return "%d change%s, %d item%s" % (n, "" if n == 1 else "s", items, "" if items == 1 else "s")


_running = [False]


class NetOMatic(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = "Routing"
        self.description = "Give the selected tracks / vias another net: type, Enter (live, fast, one undo step)"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, "net_o_matic.png")
        self.dark_icon_file_name = os.path.join(HERE, "net_o_matic_dark.png")

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

        state = dict(shown=frozenset())

        def apply(v):
            iss = model.apply(v)
            now = model.shown()
            if now != state["shown"]:          # KiCad 9/10 rebuild the whole view: only when needed
                kc.refresh()
                state["shown"] = now
            n = sum(model.changed.values())
            if v.get("swap"):
                pair = model.swap_pair()
                info = ("Swapped %s ⇄ %s: %d" % (model.net_name(pair[0]), model.net_name(pair[1]), n)
                        if pair else "Swap needs exactly two nets in the selection")
            elif v.get("net") is None:
                info = "Type a net, ↑↓, Enter" if any(model.sel.values()) else "Select tracks / vias, press ↻"
            else:
                label = v["net"] if v["net"] != N.NO_NET else N.NO_NET_LABEL
                info = "→ %s: %d changed" % (label, n) if n else "→ %s: already on it" % label
            return dict(info=info, warnings=iss.text(),
                        ro=dict(changed=model.changed_text(), done=model.done_text()))

        def reselect():
            model.keep()
            model.select()
            state["shown"] = frozenset()
            return model.summary(), dict(model=model)

        dlg = NetDialog(kc.pcb_frame(), HERE, model.summary(), apply, reselect, dict(model=model))
        wx.CallAfter(dlg.refresh)
        ok = dlg.run()
        v = dlg.final_values()
        dlg.Destroy()
        if ok and v is not None:
            if v != model.applied:
                model.apply(v)
            model.keep()
            kc.write_log(board, "net_o_matic.log", model.done_text(), model.log)
        else:
            model.restore_all()
        # KiCad rebuilds the view and the connectivity itself after Run() returns
