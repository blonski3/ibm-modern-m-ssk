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

## Wymiary na piktogramie (rysunek dla kierunku „Right”)

| Pole | Znaczenie |
|---|---|
| A | prosty odcinek od krawędzi pada do załamania 45° (tryb „Lead / 45 deg / lead”) |
| B | prosty odcinek od drugiego załamania do środka przelotki |
| D | odległość pad → rząd przelotek (pozostałe tryby; sposób pomiaru: „D measured”) |
| P | raster przelotek: Auto (via + clearance z netclassu), As pins, Custom |
| S | przesunięcie rzędu przelotek w bok, środek rzędu padów → środek rzędu przelotek; + = w lewo od kierunku (dla Right: w górę) |
| W | szerokość ścieżki; puste = z netclassu każdej sieci |
| ⌀ / drill | średnica i wiercenie przelotki; puste = z netclassu |

Na wspólnej linii przelotek ścieżki z mniejszym przesunięciem w bok mają nadmiar długości;
„Extra length goes to” decyduje, czy dostaje go odcinek B (załamania w jednej linii przy
padach, jak na typowym fanoucie aQFN), czy A (załamania w jednej linii przy przelotkach).

Pozostałe opcje (profil długości, kilka przelotek na pad, autoroute) są pod piktogramem.
Okno jest niemodalne, podgląd na żywo, OK zostawia wynik, Cancel usuwa; całość to jeden
krok Ctrl+Z. Po użyciu puść DRC.

Pliki: `via_o_tronic.py` (KiCad), `dialog.py` (okno), `geometry.py` i `router.py`
(czysta geometria, testowalne bez KiCada), ikony i logo PNG.
