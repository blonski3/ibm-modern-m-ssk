# tools/

Własne wtyczki KiCada i skrypty pomocnicze projektu.

## Wtyczki KiCada (PCB Editor, Action Plugin, KiCad 9/10)

| Wtyczka | Co robi |
| --- | --- |
| [`align-o-matic`](align_o_matic/README.md) | Wyrównuje pady, footprinty i przelotki do elementu wzorcowego |
| [`bus-o-matic`](bus_o_matic/README.md) | Prowadzi kilka równoległych ścieżek naraz ze stałym rozstawem |
| [`fillet-o-matic`](fillet_o_matic/README.md) | Zaokrągla, ścina albo wyostrza narożniki ścieżek (koncentrycznie dla busa) |
| [`net-o-matic`](net_o_matic/README.md) | Szybka zmiana sieci zaznaczonych ścieżek i przelotek |
| [`place-o-matic`](place_o_matic/README.md) | Rozstawia zaznaczone footprinty w rząd, kolumnę, siatkę lub okrąg |
| [`silk-o-matic`](silk_o_matic/README.md) | Ustawia opisy Reference/Value nad, pod, obok lub na środku footprintów |
| [`spacing-o-matic`](spacing_o_matic/README.md) | Mierzy i ustawia odstęp równoległych ścieżek |
| [`stitch-o-matic`](stitch_o_matic/README.md) | Przelotki zszywające: wzdłuż ścieżek, siatka w strefie (Fill/Fit), pierścień przy krawędzi |
| [`via-o-tronic`](via_o_tronic/README.md) | Fanout: przelotki dla zaznaczonych padów lub końców ścieżek z poprowadzeniem i omijaniem przeszkód |

Instalacja: skopiować katalog wtyczki do folderu wtyczek KiCada (Flatpak: `~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/`) i zrestartować KiCad. Folder wtyczek trzyma kopie, więc po każdej zmianie w repo trzeba skopiować pliki ponownie. Logi wtyczek trafiają do katalogu projektu (`*_o_matic.log`, ignorowane). Testy: `test_*.py` w katalogu wtyczki (geometria bez pcbnew).

## Skrypty

| Skrypt | Co robi |
| --- | --- |
| `kicad-check.sh` | ERC, netlista i PDF schematu oraz DRC z parity płytki controllera do `.baseline/` (kicad-cli) |
| `check_3d_paths.py` | Sprawdza ścieżki modeli 3D w footprintach: `python3 tools/check_3d_paths.py hardware/controller hardware/lib` |
