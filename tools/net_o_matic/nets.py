# Pure logic of net-o-matic (no pcbnew, no wx): net search ranking, copper contacts and
# connected growth on geo.Obstacle shapes.

import re

from . import geo

NO_NET = ""                       # the "no net" entry (net code 0)
NO_NET_LABEL = "<no net>"
TOL = 1e-4                        # mm: copper closer than this touches

TEXT = {
    "short": ("touches copper of another net", "pick that net, or move the copper away"),
    "nothing": ("nothing to change", "select tracks or vias (Pads / Zones in More)"),
    "other": ("other selected items are left as they are", ""),
    "zone": ("zone keeps its old fill until refilled", "press B (Refill all zones)"),
    "newnet": ("new net, not in the schematic", "add it there, or Update PCB from Schematic drops it"),
    "pad": ("pad nets come from the schematic", "Update PCB from Schematic sets them back"),
}


# ---------------------------------------------------------------- search

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


_WORD = re.compile(r"[/_\-.()+~ ,:]")


def _subsequence(q, s):
    i = 0
    for ch in s:
        if i < len(q) and ch == q[i]:
            i += 1
    return i == len(q)


def tier(name, token):
    """How well one lower-case token matches a net name: 0 exact, 1 prefix, 2 word
    prefix, 3 substring, 4 letters in order, None = no match. The hierarchical path
    ('/sheet/') and a leading '/' do not count."""
    s = name.lower()
    leaf = s.rsplit("/", 1)[-1]
    if token in (s, leaf):
        return 0
    if s.startswith(token) or leaf.startswith(token):
        return 1
    for m in _WORD.finditer(s):
        if s.startswith(token, m.end()):
            return 2
    if token in s:
        return 3
    if len(token) >= 2 and _subsequence(token, leaf):
        return 4
    return None


def rank(names, query, boost=None):
    """names (the board's nets, without the no-net entry) filtered and ordered for the
    query. boost: {name: rank} (lower first) for suggestions / recent nets; it orders
    nets inside one match tier, and the whole list when the query is empty."""
    boost = boost or {}
    toks = query.lower().split()
    out = []
    for n in names:
        if not n:
            continue
        if toks:
            ts = [tier(n, t) for t in toks]
            if None in ts:
                continue
            if len(toks) > 1 and 4 in ts:
                continue
            t = max(ts)
        else:
            t = 0
        out.append((t, boost.get(n, 99), natural_key(n), n))
    out.sort()
    return [x[3] for x in out]


def no_net_matches(query):
    q = query.strip().lower()
    return q == "" or "<no net>".startswith(q) or "no net".startswith(q) or q in ("none", "0", "-")


# ---------------------------------------------------------------- copper contacts

def gap(o1, o2):
    """Copper-to-copper distance of two geo.Obstacles (<= 0: they touch / overlap)."""
    k1, k2 = o1.kind, o2.kind
    if k1 == "poly" and k2 != "poly":
        o1, o2, k1, k2 = o2, o1, k2, k1
    if k1 == "seg":
        a, b, h = o1.data
        if k2 == "seg":
            c, d, h2 = o2.data
            return geo.seg_seg(a, b, c, d) - h - h2
        if k2 == "circle":
            c, r = o2.data
            return geo.pt_seg(c, a, b) - h - r
        return geo.seg_poly(a, b, o2.data) - h
    if k1 == "circle":
        c, r = o1.data
        if k2 == "circle":
            c2, r2 = o2.data
            return geo.dist(c, c2) - r - r2
        if k2 == "seg":
            a, b, h = o2.data
            return geo.pt_seg(c, a, b) - h - r
        return geo.pt_poly(c, o2.data) - r
    return geo.poly_poly(o1.data, o2.data)


def same_layer(o1, o2):
    return o1.layer is None or o2.layer is None or o1.layer == o2.layer


def touching(grid, obs, accept=None):
    """Obstacles in grid touching obs (same layer, gap <= TOL), filtered by accept(o)."""
    out = []
    bb = obs.bbox
    for o in grid.near((bb[0] - TOL, bb[1] - TOL, bb[2] + TOL, bb[3] + TOL)):
        if o is obs or not same_layer(o, obs):
            continue
        if accept is not None and not accept(o):
            continue
        b2 = o.bbox
        if b2[0] > bb[2] + TOL or b2[2] < bb[0] - TOL or b2[1] > bb[3] + TOL or b2[3] < bb[1] - TOL:
            continue
        if gap(obs, o) <= TOL:
            out.append(o)
    return out


def grow(grid, by_id, seeds, can_join):
    """Ids connected to the seed ids through copper of items with can_join(id) (tracks
    and vias of the same old net, not pads). -> set of ids incl. the seeds."""
    done = set(seeds)
    todo = list(seeds)
    while todo:
        u = todo.pop()
        for obs in by_id.get(u, ()):
            for o in touching(grid, obs, lambda o: o.id not in done and can_join(o.id)):
                if o.id not in done:
                    done.add(o.id)
                    todo.append(o.id)
    return done


def contacts(grid, by_id, ids, net_of, skip_net0=True):
    """Pairs (id, other id) where copper of the ids touches copper of another net
    (net_of(id) -> the net it has now). Net 0 (no net) on either side does not count."""
    out = set()
    for u in ids:
        n = net_of(u)
        if skip_net0 and not n:
            continue
        for obs in by_id.get(u, ()):
            for o in touching(grid, obs):
                if o.id == u:
                    continue
                m = net_of(o.id)
                if m != n and (m or not skip_net0) and m is not None and m >= 0:
                    out.add((u, o.id))
    return out
