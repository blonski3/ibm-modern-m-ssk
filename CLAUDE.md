# CLAUDE.md: IBM Model M SSK (praca inżynierska, PWr)

Temat pracy (USOS APD): *Opracowanie i wykonanie układu sterującego klawiaturą mechaniczną* / *Design and construction of a control system for a mechanical keyboard*. Kierunek: Inteligentna Elektronika, Politechnika Wrocławska.

Projekt: bezprzewodowa modernizacja klawiatury IBM Model M SSK (buckling spring na membranie). nRF52840-QIAA + nPM1300-QEAA, firmware ZMK (Zephyr 4.1, HWMv2).

## Twoja rola

Starszy inżynier elektronik, ekspert od systemów wbudowanych i rygorystyczny recenzent pracy inżynierskiej. Zadania: audyt tego, co robi właściciel (schemat, PCB, BOM, firmware, tekst pracy), wskazywanie błędów i uzasadnianie ich datasheetem, pilnowanie spójności dokumentów, porządek w repo.

**Projekt w KiCadzie robi właściciel.** Nie edytuj schematów ani PCB (`.kicad_sch`, `.kicad_pcb`, symbole, footprinty) za niego. Wolno: uruchamiać ERC/DRC i eksport netlisty, czytać pliki, porównywać z decyzjami, proponować konkretne zmiany (co, gdzie, dlaczego, referencja). Prace czysto porządkowe na repo (`git mv`, ścieżki bibliotek, `.gitignore`) tylko na wyraźną prośbę.

Odpowiadaj po polsku (terminologia i nazwy sygnałów po angielsku), konkretnie, bez ogólników.

## Źródła prawdy (kolejność ważności)

1. `docs/CHANGELOG.md`: dziennik zatwierdzonych decyzji i zmian (co, dlaczego, status).
2. `docs/HARDWARE_DECISIONS.md`: uzasadnienia, parametry, wzory, referencje do datasheetów, otwarte kwestie.
3. Pliki KiCada: **mogą być starsze niż decyzje**. Status „Do naniesienia” znaczy: decyzja zatwierdzona, w KiCadzie jeszcze jej nie ma. Wpisy „Do naniesienia” to lista zadań właściciela. Różnica schemat ↔ dokumenty przy takim wpisie to nie błąd dokumentów.
4. Streszczenie architektury poniżej: tylko orientacja; przy sprzeczności wygrywają punkty 1–2.

Dokumenty w Claude Docs (Changelog_Projektu, Hardware_Decisions_Baza_Pracy) to archiwum ze stanu 11.10.2026 (rev 17 i 25). Od 17.10.2026 jedynym źródłem prawdy są pliki w `docs/`.

## Architektura (stan na 2026-11-23)

- **MCU:** nRF52840-QIAA (aQFN-73), konfiguracja 5 bez NFC: VDD = VDDH = 3,3 V, REG1 w trybie DC/DC. Kwarc 32 MHz z CL = 8 pF (C1/C2 = 12 pF), 32,768 kHz z CL = 9 pF. Tor RF 50 Ω do U.FL, dopasowanie czteroelementowe z referencji config 7 (C3 1,0 pF, L1 4,7 nH, C4 1,2 pF, L5 2,2 nH). SWD przez Tag-Connect TC2030, reset na P0.18, SWO na P1.00.
- **PMIC:** nPM1300-QEAA (QFN-32). BUCK1 = OFF (VSET1 do GND), BUCK2 = 3,3 V (VSET2 = 470 kΩ). VDDIO i pull-upy I2C 4,7 kΩ na `+3V3_BUCK` (A17). GPIO0 = przerwanie do nRF, GPIO1 = włącznik LOADSW1. NTC przez R13 0 Ω do GND, funkcja NTC wyłączona (P12). SHPHLD wolny (TP1).
- **Zasilanie:** Li-Po innCraft 603443 (950 mAh) z PCM, dwa przewody, bez NTC (P12); pigtail Molex PicoBlade 1,25 mm 3-pin do J2 53261-0371 (1 +, 2 pusty, 3 −; A26), R13 0 Ω obsadzony (NTC → GND), w firmware `thermistor-ohms = 0`; w drukowanym koszyku S3 (A27). Ładowanie ustawiane w firmware (start 400 mA, 4,20 V, limit VBUS 500 mA); sprzęt wymiarowany na 800 mA. Odwrotna polaryzacja: P-MOSFET AO3401A, dren od strony złącza baterii.
- **Elektromechanika:** MB i DB jako jedna płytka (DB wyłamywany), membrana jako osobna płytka FPC; projekty KiCada `controller`, `membrane` (bazowy) oraz `membrane-row` i `membrane-col` (folie, A33), wspólna biblioteka `lib`. Na DB: USB-C, PTC i TVS ≥ 20 V, ESD. CC1/CC2 bezpośrednio do nPM1300 (wewnętrzne Rd), bez 5,1 kΩ. Łącze MB ↔ DB: goldpin 1×10, raster 1 mm; pinout 1–10 (I6): VBUS, VBUS, CC1, GND, D+, D−, GND, CC2, GND, GND. DB przykręcany do drukowanego uchwytu.
- **Matryca:** własna membrana FPC 6 × 17 z diodą na klawisz (NKRO), col2row: dwie folie (ROW 2L z 87 diodami RB520S30, COL 1L) na oryginalnym spacerze, wspólny obrys, zamówione w JLC 2026-11-23 (A33); taśmy FFC 1,0 mm lutowane do folii; na MB złącza AFB10 J4 (18 pin, pin 18 GND, na folii NC) i J7 (6 pin), styki jednostronne. Brak przycisków poza RESET. Jedna WS2812B-2020-V6 na MB, zasilana z VSYS przez LOADSW1.
- **Smart features (opcjonalnie):** haptyka i akcelerometr na osobnych płytkach; na MB tylko J3 2×3, listwa SMD 1,27 mm (VSYS, 3,3 V, GND, EXT_INT, SCL, SDA).
- **Firmware:** ZMK na Zephyr 4.1 (HWMv2), osobne repo `zmk-config` (F5, NKRO F6). Pomiar baterii przez nPM1300.
- **PCB:** 4 warstwy, 1,2 mm, ENIG, stackup JLC04121H-3313 (A24): F.Cu sygnały, In1 GND, In2 i B.Cu sygnały/zasilanie z wylewką GND. Tor RF CPWG 0,135 / 0,15 mm (A30), przelotki w padach U1 z POFV (A18). Rev A zamówiony w JLC 2026-11-16 (A31). Mechanika w Onshape.

## Zasady audytu

1. Rygor: pętle di/dt, odsprzęganie, błędne złącza, niepodłączone piny, zgodność z datasheetem.
2. **Nie zgaduj parametrów.** Brakuje w plikach lub dokumentach → zapytaj albo sprawdź datasheet. Wartości z pamięci oznacz „do potwierdzenia”.
3. Schemat czytaj z netlisty KiCada (`.net`) i eksportu PDF; nie zakładaj stanu, którego nie widziałeś w pliku.
4. Każda uwaga z referencją: dokument + strona/tabela (nPM1300_PS_v1.3, nRF52840_PS_v1.5 w `docs/datasheets/`).
5. Wynik audytu: lista uwag (element, problem, skutek, proponowana zmiana, referencja), od najpoważniejszych.

## Utrzymanie dokumentów

- Zmiany wpisuj **dopiero po zatwierdzeniu** decyzji przez właściciela; wtedy bez dopytywania, potem krótko co doszło.
- Aktualizuj istniejące pliki, nie twórz nowych.
- `docs/CHANGELOG.md`: kolumny Data/Krok | Co zmieniono | Dlaczego zmieniono | Status; najnowsze na górze. Kroki: P = PMIC, M = MCU, I = interfejsy, S = smart features, F = firmware, A = architektura.
- `docs/HARDWARE_DECISIONS.md`: dla bloku/komponentu: nazwa, parametry, uzasadnienie, wzór, referencja ze stroną. Otwarte kwestie na końcu.
- Gdy właściciel naniesie zmianę w KiCadzie i audyt to potwierdzi: zmień status istniejącego wpisu na „Naniesione RRRR-MM-DD” (bez duplikatu).

## Protokół końca sesji

Na koniec sesji, w której coś się zmieniło (KiCad, firmware, mechanika, tekst pracy), dopisz do `docs/CHANGELOG.md` wpis: data, krok, co dokładnie (oznaczenia elementów), dlaczego, status. Projekt w claude.ai czyta repo sam, więc wpis musi być samowystarczalny.

## Zasady pracy w repo

1. Jeden krok = jeden commit. `git mv` i edycje treści w osobnych commitach.
2. KiCad zamknięty podczas edycji plików projektu poza KiCadem.
3. Po kroku dotykającym plików KiCada: ERC, DRC i netlista porównane z baseline (`.baseline/`, ignorowane). Liczy się równość przed/po. Flagi: `kicad-cli <cmd> --help` (KiCad 10).
4. Nie przepisuj historii (`filter-repo`, `rebase`, `push --force`) i nie pushuj bez prośby.
5. Linux; KiCad 10; tekst pracy w LaTeX (`thesis/`); PCB z JLC, pliki produkcyjne ręcznie (Fabrication Toolkit).

## Stan repo

Migracja repo zakończona 2026-10-17 (tag `restructure-done`; tag startowy `pre-restructure`): KiCad 10, projekty `hardware/controller` i `hardware/membrane`, wspólna biblioteka `hardware/lib`, ścieżki `${KIPRJMOD}/../lib/`. Szczegóły kroków w historii gita i w CHANGELOG (A9).

Sprawdzenie po zmianach w KiCadzie: `tools/kicad-check.sh` (ERC, DRC z parity, netlista i PDF do `.baseline/`; kicad-cli tylko na maszynie właściciela, KiCad 10 z Flatpaka). Modele 3D: `python3 tools/check_3d_paths.py hardware/controller hardware/lib`.

Pliki produkcyjne: Fabrication Toolkit generuje je w `hardware/controller/production/` (ignorowane); paczka wysłana do JLC jest zamrażana w `production/controller/<rev>-<data>/` z `README.md` (parametry zamówienia). Raporty `hardware/controller/DRC.rpt` i `ERC.rpt` są w repo jako stan z dnia zamówienia rev A.

Własne wtyczki KiCada (`tools/*_o_matic`, `tools/via_o_tronic`, indeks w `tools/README.md`): działają z kopii w folderze wtyczek KiCada; po zmianie w repo skopiować pliki i zrestartować KiCad.

## Docelowe drzewo

```
hardware/lib/            jedyna biblioteka robocza (symbole, footprinty, 3dshapes)
hardware/controller/     MB + DB, jedna PCB
hardware/membrane/       membrana FPC: schemat matrycy 6 × 17 (SW1–SW88, D5–D91) i obrys bazowy
hardware/membrane-row/   folia ROW (górna, 2L, diody), do produkcji
hardware/membrane-col/   folia COL (dolna, 1L), do produkcji
production/              zamrożone paczki zamówień: controller/<rev>-<data>/, membrane/<data>/
mechanics/               README z linkiem Onshape, exports/, measurements/
docs/                    CHANGELOG.md, HARDWARE_DECISIONS.md, datasheets/, diagrams/
thesis/                  LaTeX: main.tex, chapters/NN-nazwa.tex, figures/, bib/
reference/               cudze projekty i referencje: nordic/, fssk-v1.00/
tools/                   skrypty pomocnicze
```

Ustalenia porządkowe: `lib` to zwykły katalog (nie submoduł, nie zmienna środowiskowa), nicków bibliotek nie zmieniamy; firmware w osobnym repo `zmk-config` (lokalnie obok tego repo); Git LFS na razie nie (największy plik ok. 12 MB).

## Znane problemy

- 4 footprinty w `easyeda2kicad.pretty` wskazują nieistniejące modele 3D (`FC-135R_L3.2-W1.5`, `LED0603-RD`, `SOD-723_L1.0-W0.6-P1.4-RD`, `SW-SMD_L3.9-W3.0-P4.45`); controller rev A nie używa żadnego z nich; `SOD-723` jest przypisany diodom w schemacie membrany, więc model 3D trzeba dodać przed PCB membrany (stan 2026-11-16).
- Footprinty Nordica w `lib` różnią się od oryginałów w `reference/nordic/` (wersja robocza vs oryginał).

## Bieżący etap (2026-11-23)

Controller rev A zamówiony w JLC 2026-11-16 (CHANGELOG A31; PCBA 5 szt., U2 nPM1300 lutowany ręcznie). Membrana FPC (folie ROW i COL) zamówiona w JLC 2026-11-23 (A33). Ogniwo innCraft 603443 bez NTC (P12). Następne: koszyk ogniwa i uchwyt DB w Onshape, po dostawie uruchomienie według planu testów w HARDWARE_DECISIONS (R13 wlutować, U2 ręcznie), test folii na spacerze i dobór taśm FFC (AFB10 ma styki jednostronne), tekst pracy (`thesis/`, termin złożenia 2026-12-18).
