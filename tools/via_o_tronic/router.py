# Small grid router for the via-o-tronic plugin (no KiCad dependency, testable on its own).
# Routes one track from a start point to a goal point on a square grid with 0/45/90 deg
# moves (A* with a turn penalty), keeping a clearance to obstacles of other nets.
# All values in mm, Y axis points down (as in KiCad).

import heapq
import math

# 8 directions: index -> (di, dj); 0 = +x, then counter-clockwise in screen terms
DIRS8 = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]
SQRT2 = math.sqrt(2.0)


# ---------------------------------------------------------------- obstacles

class Obstacle:
    """kind 'circle': (cx, cy, r); 'seg': (ax, ay, bx, by, half_width);
    'rect': (cx, cy, half_w, half_h, angle_deg). net: net code (-1 = blocks every net).
    clearance: extra clearance this obstacle demands (e.g. copper-to-edge), added to
    the router's own clearance as max(own, this)."""
    __slots__ = ("kind", "d", "net", "clearance", "bbox", "_cs")

    def __init__(self, kind, data, net=-1, clearance=0.0):
        self.kind, self.d, self.net, self.clearance = kind, tuple(data), net, clearance
        if kind == "circle":
            cx, cy, r = self.d
            self.bbox = (cx - r, cy - r, cx + r, cy + r)
        elif kind == "seg":
            ax, ay, bx, by, hw = self.d
            self.bbox = (min(ax, bx) - hw, min(ay, by) - hw, max(ax, bx) + hw, max(ay, by) + hw)
        else:
            cx, cy, hw, hh, ang = self.d
            a = math.radians(ang)
            c, s = math.cos(a), math.sin(a)
            self._cs = (c, s)
            ex = abs(hw * c) + abs(hh * s)
            ey = abs(hw * s) + abs(hh * c)
            self.bbox = (cx - ex, cy - ey, cx + ex, cy + ey)

    def dist(self, x, y):
        """Distance from (x, y) to the obstacle copper (0 inside)."""
        k, d = self.kind, self.d
        if k == "circle":
            return max(0.0, math.hypot(x - d[0], y - d[1]) - d[2])
        if k == "seg":
            ax, ay, bx, by, hw = d
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            return max(0.0, math.hypot(x - ax - t * vx, y - ay - t * vy) - hw)
        cx, cy, hw, hh, _ = d
        c, s = self._cs
        dx, dy = x - cx, y - cy
        lx = abs(dx * c - dy * s) - hw      # KiCad angles: Y down, positive = CCW on screen
        ly = abs(dx * s + dy * c) - hh
        if lx <= 0 and ly <= 0:
            return 0.0
        return math.hypot(max(lx, 0.0), max(ly, 0.0))


def blocking(obstacles, net):
    return [o for o in obstacles if o.net != net or o.net < 0]


def clear_of(obstacles, x, y, radius, clearance):
    """True if a circle (x, y, radius) keeps the clearance to all obstacles."""
    for o in obstacles:
        need = radius + max(clearance, o.clearance)
        b = o.bbox
        if x < b[0] - need or x > b[2] + need or y < b[1] - need or y > b[3] + need:
            continue
        if o.dist(x, y) < need - 1e-6:
            return False
    return True


def segment_clear(obstacles, a, b, half_width, clearance, step):
    n = max(1, int(math.dist(a, b) / step) + 1)
    for i in range(n + 1):
        t = i / n
        if not clear_of(obstacles, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                        half_width, clearance):
            return False
    return True


# ---------------------------------------------------------------- router

def route(start, goal, obstacles, width, clearance, res=0.05, margin=1.5,
          max_cells=90000, turn_penalty=0.35, free_radius=0.0, grows=(1.0, 2.0, 3.5)):
    """Route from start to goal. obstacles must already exclude the track's own net.
    The grid is anchored at start; goal is snapped to the nearest grid node, the snapped
    goal is returned so the caller can move the via there (keeps 45 deg angles).
    free_radius: cells closer than this to start or goal are never blocked (lets the
    track leave its own pad and reach its own via even when neighbours are tight).
    Returns (path [(x, y), ...] with only the corner points, snapped goal) or (None, goal)."""
    hw = width / 2.0
    sx, sy = start
    for grow in grows:
        m = margin * grow
        x0, x1 = min(sx, goal[0]) - m, max(sx, goal[0]) + m
        y0, y1 = min(sy, goal[1]) - m, max(sy, goal[1]) + m
        r = res
        while ((x1 - x0) / r + 1) * ((y1 - y0) / r + 1) > max_cells:
            r *= 1.25
        i0, i1 = int(math.floor((x0 - sx) / r)), int(math.ceil((x1 - sx) / r))
        j0, j1 = int(math.floor((y0 - sy) / r)), int(math.ceil((y1 - sy) / r))
        W, H = i1 - i0 + 1, j1 - j0 + 1
        gi, gj = int(round((goal[0] - sx) / r)), int(round((goal[1] - sy) / r))
        g_snap = (sx + gi * r, sy + gj * r)
        blocked = _rasterize(obstacles, sx, sy, r, i0, j0, W, H, hw, clearance)
        fr = max(free_radius, r)
        for (ci, cj, px, py) in ((0, 0, sx, sy), (gi, gj, g_snap[0], g_snap[1])):
            k = int(math.ceil(fr / r))
            for di in range(-k, k + 1):
                for dj in range(-k, k + 1):
                    if math.hypot(di * r, dj * r) <= fr:
                        ii, jj = ci + di - i0, cj + dj - j0
                        if 0 <= ii < W and 0 <= jj < H:
                            blocked[jj * W + ii] = 0
        cells = _astar(blocked, W, H, (0 - i0, 0 - j0), (gi - i0, gj - j0), turn_penalty)
        if cells is not None:
            corners = _smooth(_corners(cells), blocked, W, H)
            pts = [(sx + (ci + i0) * r, sy + (cj + j0) * r) for ci, cj in corners]
            pts[0] = (sx, sy)
            return pts, g_snap
    return None, goal


def find_free_spot(obstacles, anchor, offsets, radius, clearance, res, reach):
    """Nearest point to anchor (on a res grid, up to reach mm away) where every via of
    the group (anchor + offsets) keeps the clearance. Returns the point or None."""
    ext = reach + radius + max([clearance] + [o.clearance for o in obstacles]) + \
        max([math.hypot(dx, dy) for dx, dy in offsets] + [0.0])
    ax, ay = anchor
    obstacles = [o for o in obstacles if not (o.bbox[2] < ax - ext or o.bbox[0] > ax + ext or
                                              o.bbox[3] < ay - ext or o.bbox[1] > ay + ext)]

    def ok(x, y):
        return all(clear_of(obstacles, x + dx, y + dy, radius, clearance) for dx, dy in offsets)
    if ok(*anchor):
        return anchor
    n = int(reach / res)
    cand = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            d = math.hypot(i, j) * res
            if 0 < d <= reach:
                cand.append((d, anchor[0] + i * res, anchor[1] + j * res))
    cand.sort()
    for _d, x, y in cand:
        if ok(x, y):
            return (x, y)
    return None


def _line_cells(a, b):
    """Grid cells of a 0/45/90 deg line from a to b (inclusive), or None for other angles."""
    di, dj = b[0] - a[0], b[1] - a[1]
    if di and dj and abs(di) != abs(dj):
        return None
    n = max(abs(di), abs(dj))
    if n == 0:
        return [a]
    si, sj = (di > 0) - (di < 0), (dj > 0) - (dj < 0)
    return [(a[0] + k * si, a[1] + k * sj) for k in range(n + 1)]


def _smooth(corners, blocked, W, H):
    """Drop corners where a direct 0/45/90 deg line between farther corners is free."""
    out = [corners[0]]
    i = 0
    while i < len(corners) - 1:
        nxt = i + 1
        for j in range(len(corners) - 1, i + 1, -1):
            cells = _line_cells(corners[i], corners[j])
            if cells is None:
                continue
            free = True
            for (ci, cj), (pi, pj) in zip(cells[1:], cells):
                if blocked[cj * W + ci] or (ci != pi and cj != pj and
                                            (blocked[pj * W + ci] or blocked[cj * W + pi])):
                    free = False
                    break
            if free:
                nxt = j
                break
        out.append(corners[nxt])
        i = nxt
    return out


def _circle_span(cx, cy, r, y):
    d = r * r - (y - cy) ** 2
    if d < 0:
        return None
    h = math.sqrt(d)
    return (cx - h, cx + h)


def _poly_span(pts, y):
    """x-interval of a convex polygon on the horizontal line y (or None)."""
    xs = []
    n = len(pts)
    for k in range(n):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % n]
        if (y0 <= y <= y1) or (y1 <= y <= y0):
            if y1 == y0:
                xs += [x0, x1]
            else:
                xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
    return (min(xs), max(xs)) if xs else None


def _shapes(o, need):
    """The obstacle grown by `need`, as a list of convex pieces (circles and polygons)
    whose union is the blocked area."""
    k, d = o.kind, o.d
    if k == "circle":
        return [("c", (d[0], d[1], d[2] + need))]
    if k == "seg":
        ax, ay, bx, by, hw = d
        r = hw + need
        L = math.hypot(bx - ax, by - ay)
        out = [("c", (ax, ay, r)), ("c", (bx, by, r))]
        if L > 1e-9:
            nx, ny = -(by - ay) / L * r, (bx - ax) / L * r
            out.append(("p", [(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]))
        return out
    cx, cy, hw, hh, _ang = d
    c, s = o._cs

    def corner(u, v):          # local (u, v) -> board, same rotation as Obstacle.dist
        return (cx + u * c + v * s, cy - u * s + v * c)
    out = []
    for w, h in ((hw + need, hh), (hw, hh + need)):
        out.append(("p", [corner(-w, -h), corner(w, -h), corner(w, h), corner(-w, h)]))
    for u in (-hw, hw):
        for v in (-hh, hh):
            px, py = corner(u, v)
            out.append(("c", (px, py, need)))
    return out


def _rasterize(obstacles, sx, sy, r, i0, j0, W, H, hw, clearance):
    """Grid of blocked cells: a cell is blocked when a track of half width hw centred
    there would come closer than the clearance to an obstacle. Row spans are computed
    analytically per convex piece (much faster than a distance test per cell)."""
    blocked = bytearray(W * H)
    wx0, wy0 = sx + i0 * r, sy + j0 * r
    wx1, wy1 = sx + (i0 + W - 1) * r, sy + (j0 + H - 1) * r
    eps = 1e-6
    for o in obstacles:
        need = hw + max(clearance, o.clearance) - eps
        b = o.bbox
        bx0, by0, bx1, by1 = b[0] - need, b[1] - need, b[2] + need, b[3] + need
        if bx1 < wx0 or bx0 > wx1 or by1 < wy0 or by0 > wy1:
            continue
        pieces = _shapes(o, need)
        ja = max(0, int(math.floor((by0 - sy) / r)) - j0)
        jb = min(H - 1, int(math.ceil((by1 - sy) / r)) - j0)
        for jj in range(ja, jb + 1):
            y = sy + (jj + j0) * r
            lo, hi = None, None
            for kind, data in pieces:
                sp = _circle_span(data[0], data[1], data[2], y) if kind == "c" else _poly_span(data, y)
                if sp is not None:
                    lo = sp[0] if lo is None else min(lo, sp[0])
                    hi = sp[1] if hi is None else max(hi, sp[1])
            if lo is None:
                continue
            ia = max(0, int(math.ceil((lo - sx) / r - 1e-9)) - i0)
            ib = min(W - 1, int(math.floor((hi - sx) / r + 1e-9)) - i0)
            if ia <= ib:
                row = jj * W
                blocked[row + ia:row + ib + 1] = b"\x01" * (ib - ia + 1)
    return blocked


def _astar(blocked, W, H, s, t, turn_penalty):
    si, sj = s
    ti, tj = t
    if not (0 <= ti < W and 0 <= tj < H):
        return None

    def h(i, j):
        dx, dy = abs(i - ti), abs(j - tj)
        return (dx + dy) + (SQRT2 - 2.0) * min(dx, dy)

    start_key = (sj * W + si) * 9 + 8          # direction 8 = "no direction yet"
    g = {start_key: 0.0}
    came = {}
    heap = [(h(si, sj), 0.0, si, sj, 8)]
    while heap:
        f, gc, i, j, d = heapq.heappop(heap)
        key = (j * W + i) * 9 + d
        if gc > g.get(key, 1e18) + 1e-9:
            continue
        if i == ti and j == tj:
            out = [(i, j)]
            while key in came:
                key = came[key]
                c = key // 9
                out.append((c % W, c // W))
            return out[::-1]
        for nd, (di, dj) in enumerate(DIRS8):
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= W or nj >= H or blocked[nj * W + ni]:
                continue
            if di and dj and (blocked[j * W + ni] or blocked[nj * W + i]):
                continue                       # no corner cutting past an obstacle
            step = SQRT2 if di and dj else 1.0
            if d != 8 and nd != d:
                turn = min((nd - d) % 8, (d - nd) % 8)
                if turn > 2:
                    continue                   # no sharp (> 90 deg) turns
                step += turn_penalty * turn
            ng = gc + step
            nkey = (nj * W + ni) * 9 + nd
            if ng < g.get(nkey, 1e18) - 1e-9:
                g[nkey] = ng
                came[nkey] = key
                heapq.heappush(heap, (ng + h(ni, nj), ng, ni, nj, nd))
    return None


def _corners(cells):
    if len(cells) <= 2:
        return cells
    out = [cells[0]]
    for a, b, c in zip(cells, cells[1:], cells[2:]):
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            out.append(b)
    out.append(cells[-1])
    return out
