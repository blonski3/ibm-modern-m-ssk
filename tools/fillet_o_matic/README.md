# fillet-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): zaokrągla, ścina albo z powrotem
wyostrza narożniki zaznaczonych ścieżek. Odpowiedź na narzekania z forum KiCada na
wbudowane **Fillet Tracks**: nie da się zmienić promienia już zaokrąglonych ścieżek ani
cofnąć zaokrąglenia, równoległe ścieżki busa dostają ten sam promień (raster w zakręcie się
rozjeżdża), a za krótkie odcinki są po cichu pomijane.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/fillet_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/fillet_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

Zaznacz ścieżki (odcinki i łuki, np. U na całej trasie) i uruchom wtyczkę. Zmiany dzieją się
od razu na płytce, **OK** zostawia, **Cancel** przywraca wszystko dokładnie; jeden krok Ctrl+Z.
Istniejące łuki są najpierw zamieniane z powrotem na ostry narożnik, więc wtyczka działa też
jako „zmień promień” i „usuń zaokrąglenia”.

| Pole | Znaczenie |
|---|---|
| ╯ / ⌟ / ┘ | Round (łuk styczny), Chamfer (ścięcie), Sharp (łuki → ostre narożniki) |
| Concentric / Same R | bus: wspólny środek łuków, raster zostaje; albo każdy ten sam R (jak KiCad) |
| mm / × W | R i C w mm albo jako wielokrotność szerokości ścieżki (np. R = 3 × W) |
| R | promień na osi ścieżki (Concentric: ścieżki wewnętrznej, patrz More) |
| C | ścięcie: odległość od narożnika wzdłuż każdego odcinka |
| Now | promienie łuków i liczba ostrych narożników przed zmianą |
| Done | ile narożników zrobiono, ile zmniejszono, ile zostawiono |

Kółko myszy / ↑↓ na polu zmienia o krok (wybór na dole), Shift ×10, Ctrl ÷10.

More: **R of** (który tor busa ma dokładnie R: wewnętrzny, środkowy, zewnętrzny),
**Min angle** (mniejsze załamania zostają ostre; łuki są przerabiane zawsze),
**Too short** (Shrink: największy promień, jaki się mieści; Skip: zostaw ostry).

Nie rusza narożników, w których jest trzecia ścieżka, via albo pad (żeby niczego nie
rozłączyć), ani łuków ≥ 178°. Końce odcinków i łuków są tymi samymi liczbami, więc po
zaokrągleniu do nm wszystko zostaje połączone (sprawdzane w testach).

**Check**: odstęp nowych łuków / ścięć od miedzi innych sieci (clearance z netclass,
krawędź płytki), zgodny z DRC KiCada (±2 µm na łukach). Problemy pod przyciskiem ⚠, po OK
w `fillet_o_matic.log`.

## Pliki i testy

`fillet_o_matic.py` (KiCad), `dialog.py`, `geometry.py` (czysta geometria), wspólne `w95.py`
(okno), `kc.py` (KiCad), `geo.py` (geometria), ikony i logo.
`python3 test_fillet.py` (prawdziwy pcbnew: pojedynczy narożnik w obu kierunkach, ponowne
zaokrąglanie, bus koncentryczny pod różnymi kątami i obrotami, za krótkie odcinki,
węzły / via / pady, 150 losowych płytek, porównanie z DRC KiCada, szybkość),
`xvfb-run -a python3 test_fillet.py gui [zrzuty]` (okno klikane przez Run()).
