# place-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): rozstawia zaznaczone footprinty w rząd,
kolumnę, siatkę albo na okręgu z **dokładnym rastrem** (punkt–punkt) albo **odstępem**
(krawędź korpusu–krawędź). Odpowiedź na częste narzekanie z forum KiCada: Align/Distribute
rozkłada tylko „równo między skrajnymi”, Create Array tworzy nowe footprinty zamiast
przestawić istniejące, a Move Exactly działa na jednym elemencie naraz.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/place_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/place_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

Zaznacz co najmniej dwa footprinty i uruchom wtyczkę. Zmiany dzieją się od razu na płytce,
**OK** zostawia, **Cancel** przywraca wszystko dokładnie; jeden krok Ctrl+Z.
Ścieżki nie są ciągnięte za footprintem (jak w zwykłym Move).

| Pole | Znaczenie |
|---|---|
| ▪▪▪ / ⋮ / ▦ / ⁘ | rząd, kolumna, siatka, okrąg |
| Pitch / Gap | X, Y to raster (punkt odniesienia → punkt) albo odstęp między korpusami (courtyard, a bez niego pady + grafika) |
| Keep first / centre | pierwszy footprint zostaje na miejscu albo środek grupy |
| X, Y | raster / odstęp w rzędzie i kolumnie |
| N | ile w rzędzie (siatka) |
| R, A0, ΔA | okrąg: promień, kąt pierwszego (0 = w prawo, CCW), krok (puste = 360/n) |
| θ + Keep∠ / Set∠ / Follow | obrót: bez zmian, wszystkie na θ, albo θ względem kierunku rzędu / stycznej okręgu |
| DX, DY | przesunięcie całej grupy |
| Now | odległości między sąsiadami teraz (min–max) |

Startowe X/Y: jeśli footprinty już stoją mniej więcej w rzędzie, mediana obecnego rastra;
inaczej największy korpus + 0,5 mm. Kółko myszy / ↑↓ na polu zmienia o krok (wybór na dole,
także 1,27 i 2,54 mm), Shift ×10, Ctrl ÷10. Przyciski: ciaśniej / szerzej, przesuń grupę.

More: **Order** (Reference R1, R2 … R10 naturalnie / Position / Value, Reverse),
**Ref. point** (origin, środek padów, środek korpusu), **Row angle** (rząd pod kątem),
**Snap** (pierwszy na siatce), **Snake** (siatka wężykiem), **Clockwise** (okrąg).

**Check**: nachodzenie courtyardów (między ustawianymi i z resztą płytki) oraz wyjście poza
obrys płytki (prostokąt Edge.Cuts). Problemy pod przyciskiem ⚠, po OK w `place_o_matic.log`.

## Pliki i testy

`place_o_matic.py` (KiCad), `dialog.py`, `geometry.py` (czysta geometria), wspólne `w95.py`
(okno), `kc.py` (KiCad), `geo.py` (geometria), ikony i logo.
`python3 test_place.py` (prawdziwy pcbnew: wszystkie tryby, kąty, strony, dokładne cofanie,
szybkość), `xvfb-run -a python3 test_place.py gui [zrzuty]` (okno klikane przez Run()).
