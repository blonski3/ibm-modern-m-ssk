# Pure geometry of align-o-matic (no KiCad): where a slave goes so that it sits on an
# axis through the master. mm, Y down (as on screen). Only one coordinate changes,
# except in ONTO mode (both, onto the master).

AX_X, AX_Y, AX_DIAG_UP, AX_DIAG_DOWN, AX_ONTO = range(5)
MOVE_X, MOVE_Y = range(2)
REF_ORIGIN, REF_PADS, REF_BODY = range(3)

TEXT = {
    "locked": ("locked, left where it is", "unlock it (or leave it)"),
    "master": ("the master itself is in the selection, left out", ""),
    "nothing": ("nothing to align in the selection", "select pads, footprints or vias"),
    "other": ("tracks / other items in the selection are not moved", ""),
}


def target(p, m, axis, move=MOVE_X, dx=0.0, dy=0.0):
    """New position of the reference point p for master point m.
    AX_X: same X as the master (+dx), Y kept: a vertical line.
    AX_Y: same Y (+dy), X kept: a horizontal line.
    AX_DIAG_UP: on the 45° line going up-right on screen through the master,
    AX_DIAG_DOWN: on the line going down-right; move = which coordinate changes
    (its offset dx or dy shifts the line). AX_ONTO: onto the master (+dx, +dy)."""
    x, y = p
    mx, my = m
    if axis == AX_X:
        return (mx + dx, y)
    if axis == AX_Y:
        return (x, my + dy)
    if axis == AX_ONTO:
        return (mx + dx, my + dy)
    s = -1.0 if axis == AX_DIAG_UP else 1.0       # up-right: y - my = -(x - mx)
    if move == MOVE_X:
        return (mx + s * (y - my) + dx, y)
    return (x, my + s * (x - mx) + dy)


def delta(p, m, axis, move=MOVE_X, dx=0.0, dy=0.0):
    t = target(p, m, axis, move, dx, dy)
    return (t[0] - p[0], t[1] - p[1])


def centre(points):
    xs = [q[0] for q in points]
    ys = [q[1] for q in points]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
