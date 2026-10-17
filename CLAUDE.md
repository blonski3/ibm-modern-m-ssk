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

## Architektura (stan po audycie z 11.10.2026)

- **MCU:** nRF52840-QIAA (aQFN-73), konfiguracja 5 bez NFC: VDD = VDDH = 3,3 V, REG1 w trybie DC/DC. Kwarc 32 MHz z CL = 8 pF (C1/C2 = 12 pF), 32,768 kHz z CL = 9 pF. Tor RF 50 Ω do U.FL, dopasowanie dwuelementowe (czteroelementowe DO USTALENIA). SWD przez Tag-Connect TC2030, reset na P0.18, SWO na P1.00.
- **PMIC:** nPM1300-QEAA (QFN-32). BUCK1 = OFF (VSET1 do GND), BUCK2 = 3,3 V (VSET2 = 470 kΩ). VDDIO = 3,3 V. I2C z pull-upami 4,7 kΩ. GPIO0 = przerwanie do nRF, GPIO1 = włącznik LOADSW1. NTC do GND. SHPHLD wolny.
- **Zasilanie:** Li-Po LP803040, 1000 mAh, PCM, dwa przewody, bez NTC; w drukowanym koszyku. Ładowanie ustawiane w firmware (start 400 mA, 4,20 V, limit VBUS 500 mA); sprzęt wymiarowany na 800 mA. Odwrotna polaryzacja: P-MOSFET, dren od strony złącza baterii.
- **Elektromechanika:** MB i DB jako jedna płytka (DB wyłamywany), membrana jako osobna płytka FPC; projekty KiCada `controller` i `membrane`, wspólna biblioteka `lib`. Na DB: USB-C, PTC i TVS ≥ 20 V, ESD. CC1/CC2 bezpośrednio do nPM1300 (wewnętrzne Rd), bez 5,1 kΩ. Łącze MB ↔ DB: goldpin 1×10, raster 1 mm; pinout 1–10: VBUS, VBUS, GND, CC1, GND, D+, D−, GND, CC2, GND. DB przykręcany do drukowanego uchwytu.
- **Matryca:** własna membrana FPC 6 × 17 z diodą na klawisz (NKRO), col2row; na MB złącza FFC 1,0 mm J4 (18 pin) i J7 (6 pin). Brak przycisków poza RESET. Jedna WS2812C-2020 na MB, zasilana z VSYS przez LOADSW1.
- **Smart features (opcjonalnie):** haptyka i akcelerometr na osobnych płytkach; na MB tylko J3 2×6 (VSYS, 3,3 V, GND, I2C, sześć GPIO).
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

## Stan migracji repo (gałąź `restructure`, tag startowy `pre-restructure`)

- [x] Krok 1: `.gitignore` od nowa, usunięte śmieci, `.kicad_prl` zdjęte ze śledzenia.
- [x] Krok 2: `git mv` plików spoza KiCada do `reference/`, `docs/`, `mechanics/`.
- [x] `tools/check_3d_paths.py`.
- [x] Krok 5 (część): `docs/CHANGELOG.md`, `docs/HARDWARE_DECISIONS.md`, ten plik.
- [x] Krok 0a (2026-10-17): baseline na formacie KiCad 9 (sch 20250114, pcb 20241229):
      ```bash
      mkdir -p .baseline
      kicad-cli sch erc --output .baseline/erc_k9.rpt kicad/ibm-modern-m-ssk.kicad_sch
      kicad-cli pcb drc --output .baseline/drc_k9.rpt kicad/ibm-modern-m-ssk.kicad_pcb
      kicad-cli sch export netlist --output .baseline/k9.net kicad/ibm-modern-m-ssk.kicad_sch
      ```
- [x] Krok 0b (2026-10-17, modele 3D widoczne, `${KICAD9_3DMODEL_DIR}` zostaje): właściciel otwiera projekt w KiCad 10, sprawdza okno brakujących bibliotek i podgląd 3D (C 0402/0603, FFC), zapisuje schemat i PCB. Ponownie ERC/DRC/netlista (`*_k10`), porównanie z k9 (netlistę bez linii `source`/`date`/`tool`). Równe → commit `chore: upgrade project files to KiCad 10 format`. Brak modeli z `${KICAD9_3DMODEL_DIR}` (35 odwołań w PCB) → osobny commit z `${KICAD10_3DMODEL_DIR}`.
- [x] Krok 3 (2026-10-17): `mkdir -p hardware && git mv kicad hardware/controller`. Usuń z `.gitignore` linię `/kicad/production/`.
- [x] Krok 4a (2026-10-17): `git mv hardware/controller/libraries hardware/lib`.
- [x] Krok 4b (2026-10-17): ścieżki (osobny commit):
      ```bash
      sed -i 's|\${KIPRJMOD}/libraries/|${KIPRJMOD}/../lib/|' \
          hardware/controller/fp-lib-table hardware/controller/sym-lib-table
      git grep -lzF -e '${KIPRJMOD}/libraries/' -e '${EASYEDA2KICAD}/' -- \
          'hardware/controller/*.kicad_pcb' 'hardware/lib/' \
        | xargs -0 sed -i -e 's|\${KIPRJMOD}/libraries/|${KIPRJMOD}/../lib/|g' \
                          -e 's|\${EASYEDA2KICAD}/|${KIPRJMOD}/../lib/|g'
      python3 tools/check_3d_paths.py hardware/controller hardware/lib
      ```
      Oczekiwane: 0 nierozwiązanych zmiennych, tylko 4 znane brakujące modele; ERC/DRC/netlista = baseline.
- [x] Podział na projekty (2026-10-17, gałąź `kicad-split`): projekt przemianowany na `controller` (`hardware/controller/controller.kicad_pro`), nowy `hardware/membrane/` z zawartością arkusza `matrix`, arkusz `matrix` usunięty z controllera. Netlista controllera = baseline.
- [x] Krok 5 (reszta, 2026-10-17): README z sekcją „Struktura repozytorium”.
- [x] Krok 6 (2026-10-17): tag `restructure-done`, fast-forward `kicad-split` → `main`, push.

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

## Znane problemy (nie naprawiać przy migracji)

- 4 footprinty wskazują nieistniejące modele 3D: `FC-135R_L3.2-W1.5`, `LED0603-RD`, `SOD-723_L1.0-W0.6-P1.4-RD`, `SW-SMD_L3.9-W3.0-P4.45`.
- Footprinty Nordica w `lib` różnią się od oryginałów w `reference/nordic/` (wersja robocza vs oryginał).

## Faza 2 (praca właściciela, audyt po każdym kroku)

- Naniesienie wpisów „Do naniesienia” z `docs/CHANGELOG.md` w schemacie.
- Łącze MB ↔ DB: w schemacie od 2026-10-17 (A10): J9 = strona MB, J8 = strona DB (poza BOM/CPL), sieci DB z prefiksem `DB_`. Do zrobienia: footprint krawędziowy J8, drugi obrys DB z mouse bites, sprawdzenie numeracji na modelu 3D.
- Membrana: ogony 18 i 6 styków (pinout lustrzany do J4/J7, 24. styk GND wg I5), stackup i reguły FPC, obrys z Onshape. Schemat matrycy już jest w projekcie.
