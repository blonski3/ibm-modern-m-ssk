# bus-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): prowadzi **kilka ścieżek naraz** ze stałym
rozstawem. Zaznaczasz ścieżki, które kończą się „w powietrzu” (wystarczą ostatnie odcinki),
a wtyczka przedłuża je razem: prosto, z zakrętem 45° / 90°, z przesunięciem w bok (jog) albo
z nawrotem (U), z równym rozstawem w zakrętach. Odpowiedź na jedno z najstarszych życzeń
z forum i GitLaba KiCada („multi-track / bus routing”): interaktywny router prowadzi tylko
jedną ścieżkę albo parę różnicową, więc szynę danych trzeba ciągnąć ścieżka po ścieżce.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/bus_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/bus_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

Poprowadź ścieżki kawałek od padów (np. od złącza), zaznacz je (całe albo ostatnie odcinki)
i uruchom wtyczkę. Zmiany dzieją się od razu na płytce, **OK** zostawia, **Cancel** przywraca
wszystko dokładnie; jeden krok Ctrl+Z.

| Pole | Znaczenie |
|---|---|
| ═ ╝ ≈ ⊐ | prosto, zakręt, jog (zakręt i z powrotem), U (dwa zakręty w tę samą stronę) |
| ↰ / ↳ | zakręt w lewo / w prawo (tak jak widać na ekranie, patrząc w kierunku ścieżek) |
| 45° / 90° | kąt każdego zakrętu |
| L1, L2, L3 | długości odcinków osi szyny [mm]; L1 liczone od wyrównanych końców (po wachlarzu) |
| P | nowy raster (oś–oś) [mm]; puste = taki jak teraz; przy zmianie najpierw wachlarz 45° |
| ∟ Sharp / 45° cut | narożniki 90° ostre albo ścięte; przy ścięciu odstęp zostaje równy |
| C | długość ścięcia wewnętrznej ścieżki (zewnętrzne dłuższe, „koncentrycznie”) |
| Now | ile ścieżek i jaki raster teraz |
| Done | o ile każda ścieżka się wydłużyła |

Końce są najpierw **wyrównane** (krótsze ścieżki dochodzą do najdłuższej), a jeśli ostatni
odcinek idzie prosto dalej, jest po prostu wydłużany (bez dodatkowych kawałków). Wachlarz
przy zmianie rastra prowadzi sąsiednie ścieżki równolegle, więc nigdzie nie podchodzą
bliżej niż mniejszy z rastrów. Zaokrąglenia: potem **fillet-o-matic** (Concentric).

Kółko myszy / ↑↓ na polu zmienia o krok, Shift ×10, Ctrl ÷10; przyciski: raster ciaśniej /
szerzej (od obecnego, gdy P puste), L1 krócej / dłużej.

More: **Width** (szerokość nowych odcinków, puste = jak ostatni odcinek każdej ścieżki),
**Other end** (gdy ścieżki są otwarte z obu stron, prowadzi z drugiego końca).

**Check**: odstęp nowych odcinków od miedzi innych sieci i od siebie nawzajem (clearance
z netclassy), krawędź płytki. Inne ostrzeżenia: za krótka droga dla wewnętrznych ścieżek
(np. U za ciasne na tę szerokość szyny), końce nierównoległe, ścieżka bez wolnego końca.
Wszystko pod ⚠, po OK w `bus_o_matic.log`.

## Pliki i testy

`bus_o_matic.py` (KiCad), `dialog.py`, `geometry.py` (czysta geometria), wspólne `w95.py`
(okno), `kc.py` (KiCad), `geo.py` (geometria), ikony i logo.
`python3 test_bus.py` (prawdziwy pcbnew: każdy kształt w obie strony i pod 45°/90°, szyny
pod kątem 30/45/90/135°, ścięcia, wachlarz zwężający i rozszerzający, wykrywanie wolnych
końców, szerokość, dokładne cofanie, losowe szyny z przeszkodami sprawdzone DRC KiCada:
92/92 sieci zgodne, szybkość), `xvfb-run -a python3 test_bus.py gui [zrzuty]`.
