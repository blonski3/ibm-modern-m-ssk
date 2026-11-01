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

## Architektura (stan na 2026-11-01)

- **MCU:** nRF52840-QIAA (aQFN-73), konfiguracja 5 bez NFC: VDD = VDDH = 3,3 V, REG1 w trybie DC/DC. Kwarc 32 MHz z CL = 8 pF (C1/C2 = 12 pF), 32,768 kHz z CL = 9 pF. Tor RF 50 Ω do U.FL, dopasowanie czteroelementowe z referencji config 7 (C3 1,0 pF, L1 4,7 nH, C4 1,2 pF, L5 2,2 nH). SWD przez Tag-Connect TC2030, reset na P0.18, SWO na P1.00.
- **PMIC:** nPM1300-QEAA (QFN-32). BUCK1 = OFF (VSET1 do GND), BUCK2 = 3,3 V (VSET2 = 470 kΩ). VDDIO = 3,3 V. I2C z pull-upami 4,7 kΩ. GPIO0 = przerwanie do nRF, GPIO1 = włącznik LOADSW1. NTC do GND. SHPHLD wolny.
- **Zasilanie:** Li-Po ok. 1000 mAh (klasa LP803040), PCM, dwa przewody z wtykiem JST PH 2.0 (J2), bez NTC; w drukowanym koszyku. Ładowanie ustawiane w firmware (start 400 mA, 4,20 V, limit VBUS 500 mA); sprzęt wymiarowany na 800 mA. Odwrotna polaryzacja: P-MOSFET AO3401A, dren od strony złącza baterii.
- **Elektromechanika:** MB i DB jako jedna płytka (DB wyłamywany), membrana jako osobna płytka FPC; projekty KiCada `controller` i `membrane`, wspólna biblioteka `lib`. Na DB: USB-C, PTC i TVS ≥ 20 V, ESD. CC1/CC2 bezpośrednio do nPM1300 (wewnętrzne Rd), bez 5,1 kΩ. Łącze MB ↔ DB: goldpin 1×10, raster 1 mm; pinout 1–10 (I6): VBUS, VBUS, CC1, GND, D+, D−, GND, CC2, GND, GND. DB przykręcany do drukowanego uchwytu.
- **Matryca:** własna membrana FPC 6 × 17 z diodą na klawisz (NKRO), col2row; na MB złącza FFC 1,0 mm J4 (18 pin) i J7 (6 pin). Brak przycisków poza RESET. Jedna WS2812B-2020-V6 na MB, zasilana z VSYS przez LOADSW1.
- **Smart features (opcjonalnie):** haptyka i akcelerometr na osobnych płytkach; na MB tylko J3 2×3, listwa SMD 1,27 mm (VSYS, 3,3 V, GND, EXT_INT, SCL, SDA).
- **Firmware:** ZMK na Zephyr 4.1 (HWMv2). Pomiar baterii przez nPM1300.
- **PCB:** 4 warstwy (DO USTALENIA). Mechanika w Onshape.

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

Sprawdzenie po zmianach w KiCadzie: `tools/kicad-check.sh` (ERC, DRC z parity, netlista i PDF do `.baseline/`; kicad-cli tylko na maszynie właściciela). Modele 3D: `python3 tools/check_3d_paths.py hardware/controller hardware/lib`.

## Docelowe drzewo

```
hardware/lib/            jedyna biblioteka robocza (symbole, footprinty, 3dshapes)
hardware/controller/     MB + DB, jedna PCB
hardware/membrane/       membrana FPC: matryca 6 × 17 (SW1–SW88, D5–D91)
production/controller/   zamrożone paczki zamówień (<rev>-<data>/)
mechanics/               README z linkiem Onshape, exports/, measurements/
docs/                    CHANGELOG.md, HARDWARE_DECISIONS.md, datasheets/, diagrams/
thesis/                  LaTeX: main.tex, chapters/NN-nazwa.tex, figures/, bib/
reference/               cudze projekty i referencje: nordic/, fssk-v1.00/
tools/                   skrypty pomocnicze
```

Ustalenia porządkowe: `lib` to zwykły katalog (nie submoduł, nie zmienna środowiskowa), nicków bibliotek nie zmieniamy; firmware w osobnym repo `zmk-config` (jeszcze nie założone); Git LFS na razie nie (największy plik ok. 12 MB).

## Znane problemy

- 4 footprinty w `easyeda2kicad.pretty` wskazują nieistniejące modele 3D (`FC-135R_L3.2-W1.5`, `LED0603-RD`, `SOD-723_L1.0-W0.6-P1.4-RD`, `SW-SMD_L3.9-W3.0-P4.45`); na płytce controllera używany jest tylko `FC-135R` (stan 2026-11-01).
- Footprinty Nordica w `lib` różnią się od oryginałów w `reference/nordic/` (wersja robocza vs oryginał).

## Bieżący etap (2026-11-01)

Schemat controllera kompletny (CHANGELOG A1–A15), BOM pod JLC zamknięty (A14), plan testów w HARDWARE_DECISIONS. Teraz PCB: Board Setup pod JLC, obrys MB i DB, rozmieszczenie, routing. Membrana: ogony 18 i 6 styków (pinout lustrzany do J4/J7, 24. styk GND wg I5), stackup i reguły FPC, obrys z Onshape.
