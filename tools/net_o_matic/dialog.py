# Dialog of net-o-matic (no pcbnew import, runs without KiCad).

import wx

from . import nets as N
from . import w95

NAME = "net-o-matic"
VERSION = "1.0"

ROW_NET, ROW_NONE, ROW_NEW = range(3)


class NetList(wx.ListCtrl):
    """Virtual list: thousands of nets filter without delay."""

    def __init__(self, parent, size):
        super().__init__(parent, size=size,
                         style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.InsertColumn(0, "Net", width=size[0] - 132)
        self.InsertColumn(1, "Pads", wx.LIST_FORMAT_RIGHT, width=44)
        self.InsertColumn(2, "", width=84)
        self.rows = []
        self.notes = {}
        self.pads = {}
        self.grey = wx.ItemAttr()
        self.grey.SetTextColour(w95.GREY)

    def set_rows(self, rows):
        self.rows = rows
        self.SetItemCount(len(rows))
        self.Refresh()

    def OnGetItemText(self, i, col):
        kind, name = self.rows[i]
        if col == 0:
            if kind == ROW_NONE:
                return N.NO_NET_LABEL
            if kind == ROW_NEW:
                return "+ new net “%s”" % name
            return name
        if col == 1:
            n = self.pads.get(name, 0) if kind == ROW_NET else 0
            return str(n) if n else ""
        return self.notes.get(name if kind == ROW_NET else "", "") if kind != ROW_NEW else ""

    def OnGetItemAttr(self, i):
        return self.grey if self.rows[i][0] != ROW_NET else None

    def selected(self):
        i = self.GetFirstSelected()
        return i if 0 <= i < len(self.rows) else -1

    def select(self, i):
        cur = self.selected()
        if cur == i:
            return
        if cur >= 0:
            self.SetItemState(cur, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
        if 0 <= i < len(self.rows):
            self.SetItemState(i, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                              wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
            self.EnsureVisible(i)


class NetDialog(w95.OMatic):
    NAME = NAME
    FILE = "net_o_matic"
    DEFAULTS = dict(tracks=True, vias=True, pads=False, zones=True, connected=False, live=True, more=False)
    NOT_REMEMBERED = {"tracks", "vias", "pads", "connected", "model"}
    HAS_CHECK = False
    LAST = {}
    DELAY = 150

    def build(self, box):
        self.model = self.v.get("model")
        self.pick = None                  # (kind, name) of the highlighted row
        self.swapping = False

        self.search = wx.TextCtrl(self, size=(330, -1), style=wx.TE_PROCESS_ENTER)
        try:
            self.search.SetHint("net name… (↑↓ pick, Enter = OK, Esc = Cancel)")
        except Exception:
            pass
        self.search.SetToolTip("Letters in any order of the net name; several words = all of them.\n"
                               "Nets the selection touches come first. '-' or 'none' = no net.\n"
                               "A name that does not exist offers a new net.")
        self.search.Bind(wx.EVT_TEXT, self.on_search)
        self.search.Bind(wx.EVT_TEXT_ENTER, lambda e: self.accept())
        self.search.Bind(wx.EVT_KEY_DOWN, self.on_search_key)
        box.Add(self.search, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        self.list = NetList(self, (330, 214))
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_list)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e: self.accept())
        box.Add(self.list, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        opts = wx.BoxSizer(wx.HORIZONTAL)
        for key, tip in (("tracks", "Change the selected tracks (and arcs)"),
                         ("vias", "Change the selected vias")):
            opts.Add(self.checkbox(self, key, key.capitalize(), tip), 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        opts.Add(self.checkbox(self, "connected", "+ connected",
                               "Also the tracks and vias connected to the selected ones\n"
                               "(same old net; stops at pads, like U in KiCad)"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        opts.AddStretchSpacer()
        self.swap = wx.ToggleButton(self, label="⇄ Swap", style=wx.BU_EXACTFIT)
        self.swap.SetToolTip("Swap the two nets of the selection: A → B and B → A")
        self.swap.Bind(wx.EVT_TOGGLEBUTTON, self.on_swap)
        opts.Add(self.swap, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(opts, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        fgs = wx.FlexGridSizer(cols=2, vgap=3, hgap=6)
        self.readout(fgs, "to", "To", "The highlighted net: netclass, number of pads")
        self.readout(fgs, "changed", "Changed", "What the highlighted net changed now")
        self.readout(fgs, "done", "Done", "All changes in this window (↻ keeps the change and takes a new selection)")
        for t in self.ro.values():
            t.SetMinSize((250, -1))
        box.Add(fgs, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        mp = self.more_pane(box)
        ps = wx.BoxSizer(wx.HORIZONTAL)
        ps.Add(self.checkbox(mp, "pads", "Pads", "Change the pads picked on their own (Alt+click);\n"
                                                 "pad nets normally come from the schematic"), 0, wx.ALL, 4)
        ps.Add(self.checkbox(mp, "zones", "Zones", "Change the selected copper zones (refill with B)"), 0, wx.ALL, 4)
        ps.Add(self.checkbox(mp, "live", "Live", "Show the highlighted net on the board at once.\n"
                                                 "Off: the board changes only on Enter / OK"), 0, wx.ALL, 4)
        mp.SetSizer(ps)
        self.reselect.SetToolTip("Keep this change and take what is selected now for the next one")
        self.update_labels()
        self.filter(first=True)
        wx.CallAfter(self.search.SetFocus)

    # ---------------------------------------------------------- list
    def update_labels(self):
        m = self.model
        for key, kind in (("tracks", "track"), ("vias", "via"), ("pads", "pad"), ("zones", "zone")):
            n = len(m.sel[kind]) if m else 0
            c = self.cb[key]
            c.SetLabel("%s %d" % (key.capitalize(), n) if n else key.capitalize())
            c.Enable(n > 0)
        pair = m.swap_pair() if m else None
        self.swap.Enable(pair is not None)
        if pair is None and self.swap.GetValue():
            self.swap.SetValue(False)
            self.swapping = False
        if m:
            self.list.pads = {n: m.pads.get(c, 0) for n, c in m.code_of.items()}
            notes = {}
            for c, k in m.now.items():
                notes[m.name_of.get(c, "") if c else ""] = "now %d" % k
            for name in m.recent:
                notes.setdefault(name, "recent")
            for c, k in m.touch.items():
                notes[m.name_of.get(c, "")] = "touches %d" % k
            self.list.notes = notes

    def boost(self):
        m = self.model
        b = {}
        if not m:
            return b
        for k, (c, _n) in enumerate(m.touch.most_common()):
            b.setdefault(m.name_of.get(c, ""), k)
        for k, name in enumerate(m.recent):
            b.setdefault(name, 20 + k)
        for c in m.now:
            if c:
                b.setdefault(m.name_of.get(c, ""), 40)
        return b

    def filter(self, first=False):
        m = self.model
        q = self.search.GetValue().strip()
        names = N.rank(m.names if m else [], q, self.boost())
        rows = [(ROW_NET, n) for n in names]
        if N.no_net_matches(q):
            if q in ("-", "0", "none") or q.startswith("<"):
                rows.insert(0, (ROW_NONE, N.NO_NET))
            elif not q:
                nb = sum(1 for n in names if n in self.boost())
                rows.insert(nb, (ROW_NONE, N.NO_NET))
            else:
                rows.append((ROW_NONE, N.NO_NET))
        exact = q and m and any(n.lower() == q.lower() or n.lower().rsplit("/", 1)[-1] == q.lower()
                                for n in m.names)
        if q and not exact and q not in ("-", "0", "none") and not q.startswith("<"):
            rows.append((ROW_NEW, q))
        self.list.set_rows(rows)
        # highlight: the best match while typing; at the start only a net the copper touches
        pick = None
        if q:
            if rows and rows[0][0] != ROW_NEW:
                pick = 0
        elif m and m.touch:
            best = m.name_of.get(m.touch.most_common(1)[0][0])
            if (ROW_NET, best) in rows:
                pick = rows.index((ROW_NET, best))
        self.set_pick(pick)

    def set_pick(self, i):
        self.list.select(i if i is not None else -1)
        new = self.list.rows[i] if i is not None and 0 <= i < len(self.list.rows) else None
        if new != self.pick:
            self.pick = new
            self.on_change()
        else:
            self.show_to()

    def on_search(self, _evt):
        if self.swapping:
            return
        self.filter()

    def on_search_key(self, evt):
        n = {wx.WXK_UP: -1, wx.WXK_DOWN: 1, wx.WXK_PAGEUP: -8, wx.WXK_PAGEDOWN: 8,
             wx.WXK_NUMPAD_UP: -1, wx.WXK_NUMPAD_DOWN: 1}.get(evt.GetKeyCode())
        if n is None or not self.list.rows:
            evt.Skip()
            return
        i = self.list.selected()
        i = 0 if i < 0 and n > 0 else max(0, min(len(self.list.rows) - 1, i + n))
        self.set_pick(i)

    def on_list(self, evt):
        i = evt.GetIndex()
        new = self.list.rows[i] if 0 <= i < len(self.list.rows) else None
        if new != self.pick:
            self.pick = new
            self.on_change()

    def on_swap(self, _evt):
        self.swapping = self.swap.GetValue()
        self.search.Enable(not self.swapping)
        self.list.Enable(not self.swapping)
        self.on_change()

    def accept(self):
        if self.pick is None and not self.swapping:
            self.set_status(dict(info="Pick a net first (type, ↑↓)", warnings=self.last.get("warnings", [])))
            return
        if self._timer is not None:
            self._timer.Stop()
        self.finish(True)

    # ---------------------------------------------------------- state
    def show_to(self):
        m = self.model
        if self.swapping and m and m.swap_pair():
            a, b = m.swap_pair()
            txt = "%s ⇄ %s" % (m.net_name(a), m.net_name(b))
        elif self.pick is None:
            txt = "–"
        elif self.pick[0] == ROW_NONE:
            txt = N.NO_NET_LABEL
        elif self.pick[0] == ROW_NEW:
            txt = "%s (new)" % self.pick[1]
        else:
            name = self.pick[1]
            cls = m.netclass(name) if m else ""
            pads = m.pads.get(m.code_of.get(name), 0) if m else 0
            txt = " · ".join(x for x in (name, cls, "%d pad%s" % (pads, "" if pads == 1 else "s")) if x)
        self.ro["to"].SetLabel(txt)

    def on_state(self):
        if hasattr(self, "search"):
            self.show_to()

    def on_change(self, _evt=None):
        self.update_enabled()
        if self._timer is not None:
            self._timer.Stop()
        if self.cb["live"].GetValue():
            self._timer = wx.CallLater(self.delay, self.refresh)
        else:
            self.set_status(dict(info="Live off: Enter / OK applies", warnings=[]))

    def on_reselected(self, defaults):
        self.model = defaults.get("model", self.model)
        self.pick = None
        self.swap.SetValue(False)
        self.swapping = False
        self.search.Enable(True)
        self.list.Enable(True)
        self.update_labels()
        self.search.ChangeValue("")
        self.filter(first=True)
        self.search.SetFocus()

    def convert(self, raw):
        v = {k: raw.get(k) for k in ("tracks", "vias", "pads", "zones", "connected")}
        v["swap"] = bool(self.swapping)
        if self.swapping or self.pick is None:
            v["net"] = None
        elif self.pick[0] == ROW_NONE:
            v["net"] = N.NO_NET
        else:
            v["net"] = self.pick[1]
        return v

    def final_values(self):
        try:
            return self.values()
        except ValueError:
            return None
