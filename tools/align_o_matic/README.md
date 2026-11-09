# align-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): wyrównuje pady, footprinty i przelotki do
elementu **master**. Zmienia się tylko jedna współrzędna (X albo Y), więc część zostaje na
swojej „drugiej” osi. Okno zostaje otwarte: można zrobić dowolnie wiele wyrównań po kolei,
zmieniając mastera i oś, bez ponownego uruchamiania.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/align_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/align_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

1. Zaznacz mastera (jeden pad, footprint albo przelotkę) i uruchom wtyczkę; jeśli przy
   starcie zaznaczony jest dokładnie jeden element, od razu zostaje masterem. Później
   nowego mastera ustawia **⌖ Master** (zaznacz go samego i kliknij).
2. Zaznacz elementy do wyrównania (slaves) i kliknij **⇥ Align**.
3. Zmiana osi, DX/DY albo punktu odniesienia zaraz po Align poprawia to ostatnie
   wyrównanie na żywo. Następne zaznaczenie + **⇥ Align** to nowa akcja, poprzednie
   zostają. **↶ Undo** cofa akcje po kolei.
4. **OK** zostawia wszystko, **Cancel** przywraca płytkę dokładnie sprzed uruchomienia;
   cała sesja to jeden krok Ctrl+Z.

| Przycisk / pole | Znaczenie |
|---|---|
| X | X jak master (pionowa linia), zmienia się tylko X |
| Y | Y jak master (pozioma linia), zmienia się tylko Y |
| XY ↗ / YX ↘ | linia 45° przez mastera (w górę w prawo / w dół w prawo); **Move X / Move Y** mówi, która współrzędna się zmienia |
| Onto | na mastera (X i Y), np. przelotka na środek pada |
| Origin / Pads centre / Body centre | który punkt całego footprintu idzie na linię (master i slaves); zaznaczony pad to zawsze środek pada, kilka padów jednego footprintu: środek między nimi |
| DX, DY | przesunięcie linii względem mastera [mm] |
| Master | master i jego punkt |
| Last / Done | ostatnie wyrównanie (ile, największe przesunięcie) / wszystkie akcje w oknie |

Pad jako slave przesuwa cały swój footprint (bez obrotu), tak żeby ten pad stanął na
linii. Pojedynczy pad zaznaczysz w PCB Editorze np. przez Alt+klik (lista do wyboru) albo
filtr zaznaczenia z samymi „Pads”. Zablokowane elementy zostają na miejscu (ostrzeżenie
⚠), master w zaznaczeniu jest pomijany, ścieżki w zaznaczeniu się nie ruszają.

More: **Drag track ends**: końce ścieżek tej samej sieci leżące na przesuwanych padach i
przelotkach jadą razem z nimi (domyślnie wyłączone, jak zwykłe Align w KiCadzie).

## Pliki i testy

`align_o_matic.py` (KiCad), `dialog.py`, `geometry.py` (czysta geometria), wspólne `w95.py`
(okno), `kc.py` (KiCad), `geo.py`, ikony i logo.
`python3 test_align.py` (prawdziwy pcbnew: osie X/Y/45° z Move X i Y, Onto z offsetami,
punkty odniesienia, części obrócone i na spodzie, wiele akcji, poprawianie na żywo,
cofanie po kolei i całości, zablokowane, ciągnięcie ścieżek, szybkość: 300 części ≈ 15 ms),
`xvfb-run -a python3 test_align.py gui [zrzuty]` (okno klikane przez Run()).
