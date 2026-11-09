# Pure geometry of bus-o-matic (no KiCad): the open ends of N parallel tracks are
# continued together along one path (straight, bend, jog or U-turn) at a constant pitch,
# with a 45° fan first when the pitch changes. mm, Y down (as on screen); "left" is
# left as seen on screen when looking along the direction of travel.

import math

from . import geo

STRAIGHT, BEND, JOG, UTURN = range(4)
TURN_LEFT, TURN_RIGHT = range(2)
SHARP, CUT = range(2)
EPS = 1e-6
SQ2 = math.sqrt(2.0)
_H = math.sqrt(0.5)
DIRS = [(1.0, 0.0), (_H, _H), (0.0, 1.0), (-_H, _H), (-1.0, 0.0), (-_H, -_H), (0.0, -1.0), (_H, -_H)]

TEXT = {
    "short": ("path too short for the inner tracks ({v:.3f} mm missing)",
              "a longer L, a smaller C or pitch, or 45°"),
    "notpar": ("track ends not parallel ({v:.1f}° off)", "select the last segments of parallel tracks"),
    "clr": ("too close to other copper ({v:.3f} mm short)", "another path, length or pitch"),
    "connected": ("no open end, continued from a connected one", "select tracks that end in the open"),
}


def issues():
    return geo.Issues(TEXT, ("Net", "Nets"))


class Lane:
    """One track to continue: its open end, the direction out of it, width, layer, net.
    chain = ids of the selected pieces of this track (not obstacles to itself)."""

    def __init__(self, end, out, w, layer, net, name="", chain=(), seg=None):
        self.end, self.out, self.w, self.layer, self.net = end, geo.unit(out), w, layer, net
        self.name = name
        self.chain = set(chain)
        self.seg = seg                   # id of the piece that ends here (for extending it)


def left(d):
    """Normal pointing to the left of d on screen (y down): heading right -> up."""
    return (d[1], -d[0])


def turn(d, deg):
    """d turned by deg, positive = to the left on screen."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    v = (d[0] * c + d[1] * s, -d[0] * s + d[1] * c)
    return _snap(v)


def _snap(v, tol=1e-9):
    for d in DIRS:
        if abs(v[0] - d[0]) < tol and abs(v[1] - d[1]) < tol:
            return d
    return geo.unit(v)


def angle_between(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, geo.dot(a, b)))))


def frame(lanes):
    """Common direction of the lanes (the average, snapped to a multiple of 45° when
    within 2°) and the largest angle of one lane end against it."""
    sx = sum(ln.out[0] for ln in lanes)
    sy = sum(ln.out[1] for ln in lanes)
    d = geo.unit((sx, sy))
    if d == (0.0, 0.0):
        d = lanes[0].out
    a = math.degrees(math.atan2(d[1], d[0]))
    k = int(round(a / 45.0))
    if abs(a - 45.0 * k) < 2.0:
        d = DIRS[k % 8]
    dev = max(angle_between(ln.out, d) for ln in lanes)
    return d, dev


def guide_dirs(d0, shape, ang, side):
    s = ang if side == TURN_LEFT else -ang
    d1 = turn(d0, s)
    if shape == STRAIGHT:
        return [d0]
    if shape == BEND:
        return [d0, d1]
    if shape == JOG:
        return [d0, d1, d0]
    return [d0, d1, turn(d1, s)]


def fan_starts(o_old, o_new, q):
    """Where (forward, from the squared front) each lane starts its 45° move from o_old to
    o_new, so that the moving neighbours stay q apart (perpendicular) and nobody starts
    before the front. Lanes sorted by o (ascending). -> {index: start}."""
    n = len(o_old)
    mid = (n - 1) // 2 if n % 2 else n // 2
    starts = {}
    for idx, sign in ((list(range(mid, n)), 1.0), (list(range(mid - 1, -1, -1)), -1.0)):
        prev = None                                  # (sigma, c, start) of the inner neighbour
        for k in idx:
            y0, y1 = sign * o_old[k], sign * o_new[k]
            dl = y1 - y0
            if abs(dl) < EPS:
                prev = None
                continue
            sg = 1.0 if dl > 0 else -1.0
            if prev is not None and prev[0] == sg:
                c = prev[1] + SQ2 * q                # parallel line, q further out
                s = sg * (y0 - c)
            else:
                s = prev[2] if prev is not None else 0.0
                c = y0 - sg * s
            starts[k] = s
            prev = (sg, c, s)
    if starts:
        m = min(starts.values())
        starts = {k: s - m for k, s in starts.items()}
    return starts


class Plan:
    def __init__(self):
        self.paths = []          # per lane (sorted): list of points from its end
        self.lanes = []
        self.issues = issues()
        self.stats = {}


def _cross_lines(L1, L2):
    """Intersection point of two lines (point, dir), None when parallel."""
    r = geo.line_cross(L1[0], L1[1], L2[0], L2[1])
    if r is None:
        return None
    return geo.add(L1[0], geo.mul(L1[1], r[0]))


def _same_line(L1, L2):
    return (abs(geo.cross(L1[1], L2[1])) < 1e-9 and geo.dot(L1[1], L2[1]) > 0 and
            abs(geo.cross(L1[1], geo.sub(L2[0], L1[0]))) < 1e-7)


def pitch_of(os_):
    gaps = sorted(b - a for a, b in zip(os_, os_[1:]))
    return gaps


def plan(lanes, v):
    """v: shape, side, ang (45 / 90), l1, l2, l3, pitch (None = keep), corner, c."""
    P = Plan()
    if not lanes:
        return P
    d0, dev = frame(lanes)
    n0 = left(d0)
    if dev > 1.0:
        P.issues.add("notpar", None, dev)
    lanes = sorted(lanes, key=lambda ln: geo.dot(ln.end, n0))
    P.lanes = lanes
    N = len(lanes)
    F = max(geo.dot(ln.end, d0) for ln in lanes)

    def world(x, y):
        return geo.add(geo.mul(d0, F + x), geo.mul(n0, y))

    o_old = [geo.dot(ln.end, n0) for ln in lanes]
    mid = (o_old[0] + o_old[-1]) / 2.0
    pitch = v.get("pitch")
    gaps = pitch_of(o_old)
    if pitch is None or N < 2:
        o_new = list(o_old)
    else:
        o_new = [mid + (k - (N - 1) / 2.0) * pitch for k in range(N)]
    q = min([pitch] + gaps[:1]) if (pitch is not None and gaps) else (gaps[0] if gaps else 0.0)
    starts = fan_starts(o_old, o_new, q) if N > 1 else {}
    x_end = max([starts[k] + abs(o_new[k] - o_old[k]) for k in starts] + [0.0])

    # the guide (centre line of the bus): lines (point, dir) and its end point
    dirs = guide_dirs(d0, v["shape"], v["ang"], v["side"])
    Ls = [v["l1"], v["l2"], v["l3"]][:len(dirs)]
    pts = [world(x_end, mid)]
    for d, L in zip(dirs, Ls):
        pts.append(geo.add(pts[-1], geo.mul(d, L)))
    rs = [o - mid for o in o_new]
    lines = [(pts[0], dirs[0])]
    for i in range(1, len(dirs)):
        din, dout = dirs[i - 1], dirs[i]
        phi = angle_between(din, dout)
        if v.get("corner") == CUT and phi > 60.0:
            leftturn = geo.cross(din, dout) < 0           # y down: left turn has cross < 0
            o_in = max(0.0, max(rs) if leftturn else max(-r for r in rs))
            cg = v.get("c", 0.0) + 2.0 * o_in * math.tan(math.radians(phi / 4.0))
            a = cg / (2.0 * math.sin(math.radians(phi / 2.0)))
            lines.append((geo.sub(pts[i], geo.mul(din, a)), _snap(geo.unit(geo.add(din, dout)))))
        lines.append((pts[i], dout))
    gend = pts[-1]
    if v["shape"] == UTURN and v["ang"] >= 90 and N > 1:
        # the way back must not run into the way out
        sp = min([pitch] + gaps[:1]) if pitch is not None else (gaps[0] if gaps else 0.0)
        gap = v["l2"] - (rs[-1] - rs[0])
        if gap < sp - EPS:
            P.issues.add("short", None, sp - gap)

    total = []
    for k, ln in enumerate(lanes):
        r = rs[k]
        own = [(ln.end, d0)]
        if k in starts:
            dl = o_new[k] - o_old[k]
            sg = 1.0 if dl > 0 else -1.0
            own.append((world(starts[k], o_old[k]), _snap(geo.unit(geo.add(d0, geo.mul(n0, sg))))))
        lane_lines = own + [(geo.add(p, geo.mul(left(d), r)), d) for p, d in lines]
        merged = [lane_lines[0]]
        for L in lane_lines[1:]:
            if not _same_line(merged[-1], L):
                merged.append(L)
        end = geo.add(gend, geo.mul(left(lines[-1][1]), r))
        verts = [ln.end]
        short = 0.0
        for i in range(len(merged)):
            p_in = verts[-1]
            if i + 1 < len(merged):
                x = _cross_lines(merged[i], merged[i + 1])
                if x is None:                         # parallel but offset: should not happen
                    x = p_in
            else:
                x = end
            d = merged[i][1]
            run = geo.dot(geo.sub(x, p_in), d)
            if run < -EPS:
                short = max(short, -run)
            if geo.dist(x, p_in) > EPS:
                verts.append(x)
        if short > 0:
            P.issues.add("short", ln.name or None, short)
        P.paths.append(verts)
        total.append(sum(geo.dist(a, b) for a, b in zip(verts, verts[1:])))
    P.stats = dict(n=N, gaps=gaps, pitch=pitch, added=total, dir=d0, fan=x_end, guide=pts)
    return P


def check(plan, static, clr_of, iss, width_of):
    """Clearance of the new segments to other copper (static grid, untouched board) and
    to the new segments of the other lanes."""
    dyn = geo.Grid(cell=1.0)
    segs = []
    for k, (ln, verts) in enumerate(zip(plan.lanes, plan.paths)):
        w = width_of(ln)
        for a, b in zip(verts, verts[1:]):
            dyn.add(geo.Obstacle("seg", (a, b, w / 2.0), ln.net, ln.layer, id=k))
            segs.append((k, ln, a, b, w))
    worst = {}
    for k, ln, a, b, w in segs:
        clr = clr_of(ln)
        short = max(geo.seg_clear(static, a, b, w, ln.net, ln.layer, clr, skip=ln.chain),
                    geo.seg_clear(dyn, a, b, w, ln.net, ln.layer, clr, skip={k}))
        if short > 1e-4:
            worst[k] = max(worst.get(k, 0.0), short)
    for k, s in worst.items():
        iss.add("clr", plan.lanes[k].name or None, s)
    return worst


def describe(lanes):
    """'3 tracks, pitch 0.5' for the readout."""
    if not lanes:
        return "-"
    d0, _ = frame(lanes)
    os_ = sorted(geo.dot(ln.end, left(d0)) for ln in lanes)
    gaps = pitch_of(os_)
    txt = "%d track%s" % (len(lanes), "" if len(lanes) == 1 else "s")
    if gaps:
        lo, hi = gaps[0], gaps[-1]
        txt += ", P %.3f" % lo if hi - lo < 5e-4 else ", P %.3f–%.3f" % (lo, hi)
    return txt
