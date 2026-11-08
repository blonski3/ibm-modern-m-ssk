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
Rysunek (zawsze dla kierunku →) pokazuje wymiary literami, wartości wpisuje się w kolumnie
obok; najechanie na pole podświetla jego wymiar.

| Pole | Znaczenie |
|---|---|
| D | odległość pad → rząd przelotek (sposób pomiaru: More → D from) |
| A | „Bends at pads”: prosty odcinek od krawędzi pada do załamania 45° |
| B | „Bends at vias”: prosty odcinek od załamania do środka przelotki |
| S | przesunięcie rzędu przelotek w bok; + = w lewo od kierunku (dla → w górę) |
| P | raster przelotek: Auto (via + clearance z netclassu), As pins, Custom |
| W | szerokość ścieżki; puste = z netclassu |
| ⌀ / ○ | średnica / wiercenie przelotki; puste = z netclassu |
| Z | Zigzag: o ile dalej stoi co druga przelotka; puste = auto |
| L | odczyt: długość ścieżek pad → via (najkrótsza–najdłuższa) |

**Vias: Zigzag** — co druga przelotka stoi dalej o **Z**, więc ścieżki mogą mieć gęsty raster P
(Auto w zygzaku = (via + 2·clearance + ścieżka)/2, żeby ścieżka do dalszej via mieściła się
między bliższymi). Puste Z = najmniejsze, przy którym sąsiednie via trzymają clearance.

**Log**: problemy są grupowane („Items 1–6: …”) z podpowiedzią, co zmienić („→ raise D by at
least 0.40 mm”). Przycisk ⚠ N obok statusu otwiera okno logu (Copy kopiuje). Po OK wpis
(ustawienia, wynik, problemy) dopisuje się do `via_o_tronic.log` obok pliku płytki.

D i S ustawiają położenie busa; skos 45° dopasowuje się sam (zmiana S nie odsuwa rzędu).
Gdy S jest za duże względem D, ścieżka nie zmieści się w 45° i jest ostrzeżenie.

„Avoid” (domyślnie włączone): ścieżka, która wpadłaby na pad, ścieżkę albo przelotkę innej
sieci (także planowane przelotki sąsiadów, NPTH, krawędź płytki), jest prowadzona routerem
dookoła, a kolidująca przelotka przesuwana na najbliższe wolne miejsce. Numery takich
ścieżek pokazuje status („avoided: …”). Przeszkody są zbierane raz na otwarcie okna.

Sterowanie bez wpisywania: kółko myszy albo ↑/↓ (PgUp/PgDn = ×10) na dowolnym polu
zmienia wartość o wybrany krok (0,01–1 mm, wybór obok „Move vias”); Shift = ×10, Ctrl = ÷10.
Puste pole (auto) startuje od wartości z netclassu. Przyciski „Move vias”: ← → przesuwają
rząd przelotek bliżej/dalej (D), ↑ ↓ w bok (S). Na polu Angle kółko zmienia kąt o 5°
(Shift: 45°).

More (zwinięte): linia przelotek, pomiar D, wyrównanie rzędu, własny kąt, profil długości,
kilka przelotek na pad, parametry autoroute. ↻ wczytuje bieżące zaznaczenie.
Okno jest niemodalne, podgląd na żywo, OK zostawia wynik, Cancel usuwa; całość to jeden
krok Ctrl+Z. Ostrzeżenia: najedź na tekst statusu obok „Preview”. Po użyciu puść DRC.

Pliki: `via_o_tronic.py` (KiCad), `dialog.py` (okno), `geometry.py` i `router.py`
(czysta geometria, testowalne bez KiCada), ikony i logo PNG (jasne/ciemne).
