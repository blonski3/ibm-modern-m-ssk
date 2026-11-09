# Pure geometry of silk-o-matic (no KiCad): where a reference text goes around its
# footprint, and what it would hit there (pads, other silk, the board edge). mm, Y down.

from . import geo

TOP, BOTTOM, LEFT, RIGHT, CENTER, AUTO = range(6)
ANG_KEEP, ANG_0, ANG_90, ANG_ALONG = range(4)

TEXT = {
    "crowded": ("no free place, put where it touches the least ({v:.2f} mm overlap)",
                "a smaller text (H), a smaller gap, or move it by hand"),
    "pad": ("text on a pad / solder mask opening ({v:.2f} mm)", "Auto, or another side"),
    "silk": ("text on other silkscreen ({v:.2f} mm)", "Auto, or another side"),
    "edge": ("text over the board edge ({v:.2f} mm)", "Auto, or another side"),
    "hidden": ("reference is hidden, placed anyway", "show it in the footprint properties"),
}

SIDES = {TOP: (0, -1), BOTTOM: (0, 1), LEFT: (-1, 0), RIGHT: (1, 0)}
AUTO_ORDER = [TOP, BOTTOM, RIGHT, LEFT]


def issues():
    return geo.Issues(TEXT, ("", ""))


def angle_for(mode, body_w, body_h, current):
    """Absolute text angle (deg) for the angle mode."""
    if mode == ANG_0:
        return 0.0
    if mode == ANG_90:
        return 90.0
    if mode == ANG_ALONG:
        return 0.0 if body_w >= body_h else 90.0
    return current


def place(body, tw, th, gap, side, shift=0.0):
    """Centre of a text box tw x th (board extents) outside the body box (x0, y0, x1, y1)
    at gap, on side; corners for the diagonal sides used by Auto. shift = extra gap."""
    x0, y0, x1, y1 = body
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    g = gap + shift
    if side == TOP:
        return (cx, y0 - g - th / 2.0)
    if side == BOTTOM:
        return (cx, y1 + g + th / 2.0)
    if side == LEFT:
        return (x0 - g - tw / 2.0, cy)
    if side == RIGHT:
        return (x1 + g + tw / 2.0, cy)
    return (cx, cy)


def box(c, tw, th):
    return [(c[0] - tw / 2.0, c[1] - th / 2.0), (c[0] + tw / 2.0, c[1] - th / 2.0),
            (c[0] + tw / 2.0, c[1] + th / 2.0), (c[0] - tw / 2.0, c[1] + th / 2.0)]


class World:
    """What a text must keep away from: pads (mask openings, kind poly/circle), silk
    (lines as 'seg', texts as 'poly'), the board outlines. One per silk side."""

    def __init__(self, pads=(), silk=(), outlines=(), pad_gap=0.1, silk_gap=0.1, edge_gap=0.2):
        self.pads = geo.Grid(pads, 1.0)
        self.silk = geo.Grid(silk, 1.0)
        self.outlines = [ol for ol in outlines if len(ol) >= 3]
        self.pad_gap, self.silk_gap, self.edge_gap = pad_gap, silk_gap, edge_gap
        self.edges = geo.Grid(cell=2.0)
        for ol in self.outlines:
            for a, b in zip(ol, ol[1:] + ol[:1]):
                self.edges.add(geo.Obstacle("seg", (a, b, 0.0), -1, None))

    def add_text(self, poly, id=None):
        self.silk.add(geo.Obstacle("poly", poly, 0, None, id=id))

    def hits(self, poly, own=()):
        """{kind: worst overlap (mm, incl. the gap)} of a text box polygon."""
        out = {}
        bb = geo.bbox(poly)

        def worst(kind, v):
            if v > 1e-9:
                out[kind] = max(out.get(kind, 0.0), v)
        g = max(self.pad_gap, self.silk_gap) + 0.5
        q = (bb[0] - g, bb[1] - g, bb[2] + g, bb[3] + g)
        for o in self.pads.near(q):
            worst("pad", self.pad_gap - _dist(o, poly))
        for o in self.silk.near(q):
            if o.id is not None and o.id in own:
                continue
            worst("silk", self.silk_gap - _dist(o, poly))
        if self.outlines:
            if not any(all(geo.inside(p, ol) for p in poly) for ol in self.outlines):
                worst("edge", self.edge_gap + 0.01)
            else:
                for o in self.edges.near((bb[0] - 1, bb[1] - 1, bb[2] + 1, bb[3] + 1)):
                    worst("edge", self.edge_gap - geo.seg_poly(o.data[0], o.data[1], poly))
        return out


def _dist(o, poly):
    if o.kind == "seg":
        a, b, h = o.data
        return geo.seg_poly(a, b, poly) - h
    if o.kind == "circle":
        c, r = o.data
        return geo.pt_poly(c, poly) - r
    return geo.poly_poly(o.data, poly)


def choose(world, body, tw, th, gap, side, own=()):
    """-> (centre, side used, hits). Auto: the first side with nothing in the way, then
    the same with 0.5 / 1.0 mm more gap, else the one that overlaps least."""
    if side != AUTO:
        c = place(body, tw, th, gap, side)
        return c, side, world.hits(box(c, tw, th), own)
    best = None
    for shift in (0.0, 0.5, 1.0):
        for sd in AUTO_ORDER:
            c = place(body, tw, th, gap, sd, shift)
            h = world.hits(box(c, tw, th), own)
            if not h:
                return c, sd, h
            score = sum(h.values())
            if best is None or score < best[0] - 1e-9:
                best = (score, c, sd, h)
    return best[1], best[2], best[3]
