# Pure geometry for the via-o-tronic plugin (no KiCad dependency, testable on its own).
# All values in mm, Y axis points down (as in KiCad).

import math

ALIGN_CENTER, ALIGN_FIRST, ALIGN_LAST = "center", "first", "last"
REF_EDGE, REF_EDGE_CENTER, REF_CENTER = "edge", "edge_center", "center"
LINE_COMMON, LINE_EACH = "common", "each"
ROUTE_STRAIGHT, ROUTE_45_PAD, ROUTE_45_VIA = "straight", "45_pad", "45_via"
ROUTE_OFFSET = "offset"   # straight lead from the pad, 45 deg jog, straight lead into the via
SLACK_VIA, SLACK_PAD = "via", "pad"   # offset mode: which lead absorbs the extra length
ROUTE_AUTO = "auto"   # handled by router.py; plan() uses the 45 deg path as a fallback
PROF_CONST, PROF_INC, PROF_DEC, PROF_V, PROF_A, PROF_ZIGZAG, PROF_CUSTOM = (
    "const", "inc", "dec", "v", "a", "zigzag", "custom")
GROUP_ACROSS, GROUP_ALONG, GROUP_GRID = "across", "along", "grid"


def group_offsets(count, spacing, mode):
    """Via positions of one item's group as (dt, ds) offsets from the group anchor:
    dt along the fanout direction, ds along the via row. The anchor is where the single
    via would be. across: side by side, centred on the anchor; along: one behind another,
    going outwards; grid: 2 rows (along), columns centred on the anchor."""
    if count <= 1:
        return [(0.0, 0.0)]
    if mode == GROUP_ALONG:
        return [(j * spacing, 0.0) for j in range(count)]
    if mode == GROUP_GRID:
        cols = (count + 1) // 2
        out = []
        for j in range(count):
            r, c = divmod(j, cols)
            out.append((r * spacing, (c - (cols - 1) / 2.0) * spacing))
        return out
    return [(0.0, (j - (count - 1) / 2.0) * spacing) for j in range(count)]


def group_width(count, spacing, mode):
    """Extent of a group along the via row, centre of first to centre of last via [mm]."""
    offs = group_offsets(count, spacing, mode)
    ss = [o[1] for o in offs]
    return max(ss) - min(ss)


def group_bars(offs):
    """Track segments (as pairs of offsets) joining the vias of one group: one bar per
    row (same dt) and one bar per column (same ds), so every via is connected."""
    bars = []
    for key, other in ((0, 1), (1, 0)):
        lines = {}
        for o in offs:
            lines.setdefault(round(o[key], 6), []).append(o)
        for pts in lines.values():
            if len(pts) > 1:
                pts = sorted(pts, key=lambda o: o[other])
                bars.append((pts[0], pts[-1]))
    return bars


def profile_offsets(n, profile, step, custom=None):
    """Extra length [mm] for each item in row order (sorted along the row).
    inc: +step per item; dec: reverse; v: centre shortest, edges longest;
    a: centre longest; zigzag: every second item +step; custom: explicit list."""
    c = (n - 1) / 2.0
    if profile == PROF_INC:
        return [j * step for j in range(n)]
    if profile == PROF_DEC:
        return [(n - 1 - j) * step for j in range(n)]
    if profile == PROF_V:
        return [abs(j - c) * step for j in range(n)]
    if profile == PROF_A:
        return [(c - abs(j - c)) * step for j in range(n)]
    if profile == PROF_ZIGZAG:
        return [(j % 2) * step for j in range(n)]
    if profile == PROF_CUSTOM:
        vals = list(custom or [])
        return [vals[j] if j < len(vals) else (vals[-1] if vals else 0.0) for j in range(n)]
    return [0.0] * n


def axes(angle_deg):
    a = math.radians(angle_deg)
    d = (math.cos(a), -math.sin(a))      # fanout direction
    p = (-d[1], d[0])                    # direction along the via row
    return d, p


def plan(sources, angle_deg, dist, pitch, via_d,
         align=ALIGN_CENTER, ref=REF_EDGE, line=LINE_COMMON, route=ROUTE_45_VIA, min_gap=0.0,
         profile=PROF_CONST, step=0.0, custom=None,
         vias_per=1, group_spacing=0.0, group_mode=GROUP_ACROSS,
         lead_pad=0.3, lead_via=0.3, slack=SLACK_VIA, shift=0.0):
    """sources: list of dict(x, y, edge): start point, and 'edge' = how far the item (pad)
    extends from the start point in the fanout direction, in mm (>= 0).
    pitch <= 0 keeps the pins' own positions along the row.
    min_gap: required copper gap between vias (for the overlap warning).
    profile/step/custom: per-item extra track length, see profile_offsets().
    vias_per/group_spacing/group_mode: several vias per item, see group_offsets();
    the track from the pad ends at the group anchor, bars join the vias of the group.
    route=ROUTE_OFFSET: the via row is placed like in the other modes (dist, ref, shift);
    each track is pad -> straight lead -> 45 deg jog -> straight lead -> via. With
    slack=SLACK_VIA the bends start lead_pad after the pad edge (lead into the via takes
    the rest); with SLACK_PAD the jog ends lead_via before the via centre.
    shift: moves the whole via row sideways [mm], + = to the left of the fanout direction
    (for "Right" that is up on the screen).
    Returns (list of dict(path=[(x,y),...], via=(x,y), vias=[(x,y),...],
    bars=[((x,y),(x,y)),...]), list of warnings)."""
    quiet = route == ROUTE_AUTO      # the router replaces the paths: no bend warnings
    if quiet:
        route = ROUTE_45_VIA
    d, p = axes(angle_deg)
    proj = lambda x, y, v: x * v[0] + y * v[1]
    items = []
    for i, s in enumerate(sources):
        t0 = proj(s["x"], s["y"], d)
        items.append(dict(i=i, t0=t0, tE=t0 + s.get("edge", 0.0), s=proj(s["x"], s["y"], p)))

    # positions along the row
    order = sorted(items, key=lambda it: it["s"])
    n = len(order)
    if pitch <= 0:
        for it in order:
            it["sv"] = it["s"]
    else:
        smin, smax = order[0]["s"], order[-1]["s"]
        if align == ALIGN_FIRST:
            start = smin
        elif align == ALIGN_LAST:
            start = smax - (n - 1) * pitch
        else:
            start = (smin + smax) / 2.0 - (n - 1) * pitch / 2.0
        for j, it in enumerate(order):
            it["sv"] = start + j * pitch
    for it in order:
        it["sv"] -= shift

    # distance along the fanout direction
    # pad edge to via edge (copper gap), pad edge to via centre, or centre to centre
    k = dist + (via_d / 2.0 if ref == REF_EDGE else 0.0)
    base = [(it["t0"] if ref == REF_CENTER else it["tE"]) for it in items]
    if line == LINE_COMMON:
        t_line = max(base) + k
        for it in items:
            it["tv"] = t_line
    else:
        for it, b in zip(items, base):
            it["tv"] = b + k

    # variable via placement: extra length per item, in row order
    for it, extra in zip(order, profile_offsets(n, profile, step, custom)):
        it["tv"] += extra

    to_xy = lambda t, s: (t * d[0] + s * p[0], t * d[1] + s * p[1])
    offs = group_offsets(max(1, int(vias_per)), group_spacing, group_mode)
    for it in items:
        it["vias"] = [to_xy(it["tv"] + dt, it["sv"] + ds) for dt, ds in offs]
        it["bars"] = [(to_xy(it["tv"] + a[0], it["sv"] + a[1]), to_xy(it["tv"] + b[0], it["sv"] + b[1]))
                      for a, b in group_bars(offs)]
    warnings, out = [], [None] * n
    for ia in range(n):
        for ib in range(ia + 1, n):
            a_, b_ = order[ia], order[ib]
            gap = min(math.dist(va, vb) for va in a_["vias"] for vb in b_["vias"])
            if gap < via_d + min_gap - 1e-6:
                warnings.append("Vias of items %d and %d too close: centre distance %.3f mm < via %.3f + clearance %.3f mm."
                                % (a_["i"] + 1, b_["i"] + 1, gap, via_d, min_gap))
    for it in items:
        L = it["tv"] - it["t0"]
        dl = it["sv"] - it["s"]
        a = it["tE"] - it["t0"]           # length needed to leave the pad outline
        if L < a + via_d / 2.0 - 1e-6:
            warnings.append("Item %d: via overlaps its pad (track too short); increase distance or step." % (it["i"] + 1))
        S = to_xy(it["t0"], it["s"])
        V = to_xy(it["tv"], it["sv"])
        mode = route
        if abs(dl) < 1e-6:
            mode = ROUTE_STRAIGHT
        if mode == ROUTE_OFFSET:
            jog = abs(dl)
            if jog > it["tv"] - it["tE"] + 1e-6:
                warnings.append("Item %d: S too large for D (no room for 45 deg), track is steeper."
                                % (it["i"] + 1))
                path = [S, to_xy(it["tE"], it["s"]), V]
                clean = [path[0]]
                for q in path[1:]:
                    if math.dist(q, clean[-1]) > 1e-6:
                        clean.append(q)
                out[it["i"]] = dict(path=clean, via=V, vias=it["vias"], bars=it["bars"])
                continue
            if slack == SLACK_PAD:
                t1 = it["tv"] - max(0.0, lead_via) - jog
            else:
                t1 = it["tE"] + max(0.0, lead_pad)
            t1 = min(max(t1, it["tE"]), it["tv"] - jog)
            path = [S, to_xy(t1, it["s"]), to_xy(t1 + abs(dl), it["sv"]), V]
            clean = [path[0]]
            for q in path[1:]:
                if math.dist(q, clean[-1]) > 1e-6:
                    clean.append(q)
            out[it["i"]] = dict(path=clean, via=V, vias=it["vias"], bars=it["bars"])
            continue
        if mode == ROUTE_45_VIA and L - abs(dl) < a - 1e-6:
            if not quiet:
                warnings.append("Item %d: not enough room for the 45 deg bend at the via, bending at the pad instead." % (it["i"] + 1))
            mode = ROUTE_45_PAD
        if mode == ROUTE_45_PAD and a + abs(dl) > L + 1e-6:
            if not quiet:
                warnings.append("Item %d: not enough room for a 45 deg bend (increase the distance), routed straight." % (it["i"] + 1))
            mode = ROUTE_STRAIGHT
        if mode == ROUTE_45_VIA:
            path = [S, to_xy(it["tv"] - abs(dl), it["s"]), V]
        elif mode == ROUTE_45_PAD:
            path = [S, to_xy(it["t0"] + a, it["s"]), to_xy(it["t0"] + a + abs(dl), it["sv"]), V]
        else:
            path = [S, V]
        clean = [path[0]]
        for q in path[1:]:
            if math.dist(q, clean[-1]) > 1e-6:
                clean.append(q)
        out[it["i"]] = dict(path=clean, via=V, vias=it["vias"], bars=it["bars"])
    return out, warnings
