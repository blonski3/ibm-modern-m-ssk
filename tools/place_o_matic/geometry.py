# Pure geometry of place-o-matic (no KiCad): arrange footprints in a row, a column, a grid
# or on a circle with an exact pitch (centre to centre) or gap (body edge to body edge).
# mm, Y down. KiCad angles are counter-clockwise on screen: kr(p, deg) rotates a vector
# the way KiCad rotates a footprint by deg.


from . import geo

ROW, COLUMN, GRID, CIRCLE = "row", "column", "grid", "circle"
PITCH, GAP = "pitch", "gap"
ORDER_REF, ORDER_POS, ORDER_VALUE = "ref", "pos", "value"
KEEP_FIRST, KEEP_CENTER = "first", "center"
ROT_KEEP, ROT_SET, ROT_FOLLOW = "keep", "set", "follow"

TEXT = {
    "overlap": ("courtyards overlap ({v:.2f} mm)", "raise the pitch / gap, or use Gap mode"),
    "hits": ("overlaps a footprint that is not selected ({v:.2f} mm)", "move the group (DX / DY) or change Keep"),
    "outside": ("outside the board outline ({v:.2f} mm)", "move the group (DX / DY)"),
    "radius": ("radius is zero, all footprints on one spot", "raise R"),
    "one": ("need at least two footprints", "select more footprints"),
}


def kr(p, deg):
    """Rotate vector p the way KiCad rotates by deg (counter-clockwise on screen)."""
    return geo.rot(p, -deg)


class Item:
    """A footprint: ref, value, pos (origin), angle (deg), local = body outline points
    relative to the origin at angle 0, anchor_local = the reference point (origin, pads
    centre or body centre) relative to the origin at angle 0."""

    def __init__(self, id, ref, value, pos, angle, local, anchor_local=(0.0, 0.0)):
        self.id, self.ref, self.value, self.pos, self.angle = id, ref, value, pos, angle
        self.local = local or [(0.0, 0.0)]
        self.anchor_local = anchor_local

    def anchor(self, pos=None, angle=None):
        pos = self.pos if pos is None else pos
        angle = self.angle if angle is None else angle
        return geo.add(pos, kr(self.anchor_local, angle))

    def outline(self, pos=None, angle=None):
        pos = self.pos if pos is None else pos
        angle = self.angle if angle is None else angle
        return [geo.add(pos, kr(q, angle)) for q in self.local]

    def extent(self, angle, axis):
        """(min, max) of the body along unit vector axis, relative to the anchor."""
        a = kr(self.anchor_local, angle)
        vals = [geo.dot(geo.sub(kr(q, angle), a), axis) for q in self.local]
        return min(vals), max(vals)


def order(items, how, reverse=False, axis=(1.0, 0.0)):
    if how == ORDER_REF:
        out = sorted(items, key=lambda it: geo.natural_key(it.ref))
    elif how == ORDER_VALUE:
        out = sorted(items, key=lambda it: (geo.natural_key(it.value), geo.natural_key(it.ref)))
    else:
        n = geo.perp(axis)
        out = sorted(items, key=lambda it: (round(geo.dot(it.anchor(), axis), 3), geo.dot(it.anchor(), n)))
    return out[::-1] if reverse else out


def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def bbox_center(pts):
    b = geo.bbox(pts)
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def measure(items, axis):
    """Distances between neighbours along axis (items sorted by position along it)."""
    s = sorted(geo.dot(it.anchor(), axis) for it in items)
    return [b - a for a, b in zip(s, s[1:])]


def plan(items, s):
    """Settings s: mode, spacing (pitch/gap), x, y, cols, order, reverse, keep, rot (keep /
    set / follow), theta, axis_angle, radius, a0, da (0 = 360/n), cw, dx, dy, snap.
    Returns (placements [(item, pos, angle)], issues)."""
    issues = geo.Issues(TEXT, ("Footprint", "Footprints"))
    if len(items) < 2:
        issues.add("one")
        return [], issues
    mode = s["mode"]
    ax_ang = s.get("axis_angle", 0.0)
    ux = kr((1.0, 0.0), ax_ang)                       # along the row
    uy = kr((0.0, 1.0), ax_ang)                       # down the column
    axis = uy if mode == COLUMN else ux
    seq = order(items, s["order"], s.get("reverse", False), axis)
    n = len(seq)
    old_anchors = [it.anchor() for it in seq]

    # angles first: they change the body extents used by Gap mode
    def angle_for(k, it, phi=None):
        if s["rot"] == ROT_KEEP:
            return it.angle
        if s["rot"] == ROT_SET:
            return s.get("theta", 0.0) % 360
        # follow: along the row axis, or along the circle
        base = ax_ang if phi is None else phi
        return (base + s.get("theta", 0.0)) % 360

    rel = []                                          # anchor offsets of the new layout
    angles = []
    if mode in (ROW, COLUMN):
        t = 0.0
        prev = None
        for k, it in enumerate(seq):
            ang = angle_for(k, it)
            if prev is not None:
                step = s["x"] if mode == ROW else s["y"]
                if s["spacing"] == GAP:
                    lo, _hi = it.extent(ang, axis)
                    _plo, phi_ = prev[0].extent(prev[1], axis)
                    step = phi_ + step - lo
                t += step
            rel.append(geo.mul(axis, t))
            angles.append(ang)
            prev = (it, ang)
    elif mode == GRID:
        cols = max(1, int(s.get("cols", 1)))
        angs = [angle_for(k, it) for k, it in enumerate(seq)]
        px, py = s["x"], s["y"]
        if s["spacing"] == GAP:
            wx_ = max(e[1] - e[0] for e in (it.extent(a, ux) for it, a in zip(seq, angs)))
            wy_ = max(e[1] - e[0] for e in (it.extent(a, uy) for it, a in zip(seq, angs)))
            px, py = wx_ + px, wy_ + py
        for k in range(n):
            r_, c_ = divmod(k, cols)
            if s.get("snake") and r_ % 2:
                c_ = cols - 1 - c_
            rel.append(geo.add(geo.mul(ux, c_ * px), geo.mul(uy, r_ * py)))
        angles = angs
    else:                                             # circle
        R = s["radius"]
        da = s.get("da") or 360.0 / n
        sgn = -1.0 if s.get("cw") else 1.0
        for k, it in enumerate(seq):
            phi = s.get("a0", 0.0) + sgn * k * da    # KiCad degrees (CCW on screen)
            rel.append(kr((R, 0.0), phi))
            angles.append(angle_for(k, it, phi))
        if R <= 0:
            issues.add("radius")

    # where the layout goes: keep the first anchor, or the centre of the group
    if mode == CIRCLE:
        if s["keep"] == KEEP_FIRST:
            origin = geo.sub(old_anchors[0], rel[0])
        else:
            origin = bbox_center(old_anchors)
    else:
        if s["keep"] == KEEP_FIRST:
            origin = old_anchors[0]
        else:
            origin = geo.sub(bbox_center(old_anchors), bbox_center(rel))
    origin = geo.add(origin, (s.get("dx", 0.0), s.get("dy", 0.0)))
    snap = s.get("snap", 0.0)
    if snap > 0:
        ref = geo.add(origin, rel[0]) if mode != CIRCLE else origin
        sn = (round(ref[0] / snap) * snap, round(ref[1] / snap) * snap)
        origin = geo.add(origin, geo.sub(sn, ref))
    out = []
    for it, r_, ang in zip(seq, rel, angles):
        anchor = geo.add(origin, r_)
        pos = geo.sub(anchor, kr(it.anchor_local, ang))
        out.append((it, pos, ang))
    return out, issues


def check(placements, others, outline_bb, issues, gap=0.0):
    """Courtyard overlaps between the placed footprints, with footprints that are not
    selected (others: [(id, polygon)]) and the board outline bounding box."""
    polys = [(it, it.outline(pos, ang)) for it, pos, ang in placements]
    grid = geo.Grid(cell=2.0)
    for oid, poly in others:
        grid.add(geo.Obstacle("poly", poly, -2, None, id=oid))
    for k, (it, P) in enumerate(polys):
        bb = geo.bbox(P)
        for o in grid.near(bb):
            d = geo.poly_poly(P, o.data)
            if d <= 0:
                issues.add("hits", it.ref, _depth(P, o.data))
        for j in range(k + 1, len(polys)):
            jt, Q = polys[j]
            qb = geo.bbox(Q)
            if qb[0] > bb[2] or qb[2] < bb[0] or qb[1] > bb[3] or qb[3] < bb[1]:
                continue
            if geo.poly_poly(P, Q) <= 0 and _depth(P, Q) > 1e-4:
                issues.add("overlap", it.ref, _depth(P, Q))
                issues.add("overlap", jt.ref)
        if outline_bb is not None:
            out = max(outline_bb[0] - bb[0], outline_bb[1] - bb[1], bb[2] - outline_bb[2], bb[3] - outline_bb[3])
            if out > 1e-4:
                issues.add("outside", it.ref, out)


def _depth(P, Q):
    """Overlap depth of two polygons along x / y (bounding boxes, cheap and readable)."""
    a, b = geo.bbox(P), geo.bbox(Q)
    return max(0.0, min(min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])))
