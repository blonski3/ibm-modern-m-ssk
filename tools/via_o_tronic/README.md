# via-o-tronic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin) do fanoutu: zaznaczone pady lub końce
ścieżek dostają ścieżkę i przelotkę (albo grupę przelotek). Dawniej „Fanout Vias”.

## Instalacja

Folder `via_o_tronic/` musi leżeć w katalogu wtyczek KiCada (albo być tam podlinkowany).
KiCad 10 z Flatpaka:

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/via_o_tronic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/via_o_tronic

Jeśli był tam link/kopia `fanout_vias`, usuń ją. Potem w PCB Editor:
Tools → External Plugins → Refresh Plugins.

## Okno

Na górze: strzałki kierunku, tryb prowadzenia i (dla A / 45° / B) gdzie wyrównać załamania.
Wymiary wpisuje się na rysunku (rysunek dla kierunku →, opisy w podpowiedziach):

| Pole | Znaczenie |
|---|---|
| A | prosty odcinek od krawędzi pada do załamania 45° |
| B | prosty odcinek od załamania do środka przelotki |
| D | odległość pad → rząd przelotek (tryby bez A/B; sposób pomiaru w More) |
| P | raster przelotek: Auto (via + clearance z netclassu), As pins, Custom |
| S | przesunięcie rzędu przelotek w bok; + = w lewo od kierunku (dla → w górę) |
| W | szerokość ścieżki; puste = z netclassu |
| ⌀ / ○ | średnica / wiercenie przelotki; puste = z netclassu |

„Bends at pads”: ścieżki, które potrzebują mniej długości, dostają nadmiar na odcinku B
(załamania w jednej linii przy padach, typowy fanout aQFN); „Bends at vias”: na odcinku A.

Sterowanie bez wpisywania: kółko myszy albo ↑/↓ (PgUp/PgDn = ×10) na dowolnym polu
zmienia wartość o wybrany krok (0,01–1 mm, wybór obok „Move vias”); Shift = ×10, Ctrl = ÷10.
Puste pole (auto) startuje od wartości z netclassu. Przyciski „Move vias”: ← → przesuwają
rząd przelotek bliżej/dalej (B albo D), ↑ ↓ w bok (S). Na polu Angle kółko zmienia kąt o 5°
(Shift: 45°).

More (zwinięte): linia przelotek, pomiar D, wyrównanie rzędu, własny kąt, profil długości,
kilka przelotek na pad, parametry autoroute. ↻ wczytuje bieżące zaznaczenie.
Okno jest niemodalne, podgląd na żywo, OK zostawia wynik, Cancel usuwa; całość to jeden
krok Ctrl+Z. Ostrzeżenia: najedź na tekst statusu obok „Preview”. Po użyciu puść DRC.

Pliki: `via_o_tronic.py` (KiCad), `dialog.py` (okno), `geometry.py` i `router.py`
(czysta geometria, testowalne bez KiCada), ikony i logo PNG (jasne/ciemne).
