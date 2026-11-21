# Generuje DXF z zatwierdzonej geometrii spacera v15 (mm, Y w górę, środek obrysu = 0,0).
import json, math, sys, ezdxf
src = sys.argv[1]; out = sys.argv[2]
g = json.load(open(src))
doc = ezdxf.new("R2010", setup=True); doc.units = ezdxf.units.MM
msp = doc.modelspace()
for n, c in [("SPACER_OBRYS", 7), ("OGONY_ORYG", 8), ("OTWORY_H", 1), ("OTWORY_D", 3), ("SLOTY_S", 5), ("STYKI_SW", 9)]:
    doc.layers.add(n, color=c)
msp.add_lwpolyline(g["poly"], close=True, dxfattribs={"layer": "SPACER_OBRYS"})
for x, y, w, l in g["tails"]:
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + l), (x, y + l)], close=True, dxfattribs={"layer": "OGONY_ORYG"})
for x, y, r in [c[:3] for c in g["circ"]]:
    msp.add_circle((x, y), r, dxfattribs={"layer": "STYKI_SW"})
for h in g["hole"]:
    msp.add_circle((h[0], h[1]), h[2], dxfattribs={"layer": "OTWORY_H"})
for x, y, r, f, *_ in g["d"]:
    # otwór D: okrąg ścięty płaską krawędzią f mm pod środkiem
    hw = math.sqrt(r * r - f * f); a = math.degrees(math.atan2(-f, hw))
    msp.add_arc((x, y), r, a, 180 - a, dxfattribs={"layer": "OTWORY_D"})
    msp.add_line((x - hw, y - f), (x + hw, y - f), dxfattribs={"layer": "OTWORY_D"})
for x, y, L, w, *_ in g["slot"]:
    r = w / 2; l = L - w; x0, x1 = x - l / 2, x + l / 2
    msp.add_line((x0, y + r), (x1, y + r), dxfattribs={"layer": "SLOTY_S"})
    msp.add_line((x0, y - r), (x1, y - r), dxfattribs={"layer": "SLOTY_S"})
    msp.add_arc((x1, y), r, -90, 90, dxfattribs={"layer": "SLOTY_S"})
    msp.add_arc((x0, y), r, 90, 270, dxfattribs={"layer": "SLOTY_S"})
doc.saveas(out)
print("OK", out, len(msp))
