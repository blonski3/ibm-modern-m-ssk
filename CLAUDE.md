# CLAUDE.md: kontekst dla Claude Code

Repo pracy inzynierskiej (PWr, Inteligentna Elektronika): bezprzewodowa modernizacja
IBM Model M SSK. nRF52840-QIAA + nPM1300-QEAA, firmware ZMK (Zephyr 4.1, HWMv2).
Odpowiadaj po polsku, nazwy techniczne zostaw po angielsku. Nie zgaduj: jesli nie
wiesz, jak zachowa sie KiCad 10, powiedz to i sprawdz na kopii.

## Ustalenia zamkniete (nie dyskutuj ponownie)

- Dwa projekty KiCada: `controller` (motherboard + daughterboard na jednej plytce,
  DB wylamywany) i `membrane` (osobna plytka FPC, inny stackup). Wspolna biblioteka `lib`.
- Lacze MB <-> DB: goldpin 1x10, raster 1,0 mm; pinout 1-10: VBUS, VBUS, GND, CC1,
  GND, D+, D-, GND, CC2, GND.
- Biblioteka: zwykly katalog `hardware/lib/` w tym repo (nie submodul, nie zmienna
  srodowiskowa). Tabele bibliotek wskazuja `${KIPRJMOD}/../lib/...`. Nickow
  bibliotek (`easyeda2kicad`, `ibm_bs`, `nrf52840_qiaa`, ...) NIE zmieniamy.
- Firmware: osobne repo `zmk-config` (podlinkowane z README), nie katalog tutaj.
- Mechanika: Onshape; w repo tylko link i eksporty (`mechanics/`). Git LFS: nie teraz
  (najwiekszy plik ok. 12 MB, pack ok. 80 MiB).
- Produkcja: JLCPCB, Fabrication Toolkit generuje do `hardware/controller/production/`
  (ignorowane). Zamrozone paczki faktycznych zamowien: `/production/controller/<rev>-<data>/`.
- Praca: LaTeX w `thesis/` (zalozyc przy pierwszym rozdziale).

## Dokumenty projektu (zrodlo prawdy)

Changelog_Projektu i Hardware_Decisions_Baza_Pracy sa edytowane w Claude Docs, nie
w repo. W repo trzymamy ich eksport Markdown jako snapshot:
`docs/project/changelog.md`, `docs/project/hardware-decisions.md`.
Eksport robi wlasciciel recznie (nazwa doca -> Export -> Markdown). Nie edytuj tych
plikow; nowy snapshot = nowy eksport i osobny commit `docs: snapshot ...`.

## Zasady pracy w repo

1. Jeden krok = jeden commit. Przeniesienia (`git mv`) i edycje tresci w OSOBNYCH
   commitach (inaczej git gorzej wykrywa rename).
2. KiCad zamkniety podczas edycji plikow projektu poza KiCadem.
3. Po kazdym kroku dotykajacym plikow KiCada: ERC, DRC i netlista porownane z
   baseline (`.baseline/`, ignorowane). Liczy sie rownosc przed/po, nie zero bledow.
   Flagi `kicad-cli` sprawdz w `kicad-cli <cmd> --help` (KiCad 10).
4. Nie przepisuj historii (`filter-repo`, `rebase`, `push --force`) bez wyraznej prosby.
5. Nie pushuj bez prosby. Praca na galezi `restructure`, tag startowy `pre-restructure`.

## Stan migracji

- [x] Krok 1: `.gitignore` od nowa, usuniete smieci (fp-info-cache, locki, backupy,
      testowe `kicad/production`), `.kicad_prl` zdjete ze sledzenia.
- [x] Krok 2: `git mv` plikow spoza KiCada do `reference/`, `docs/`, `mechanics/`.
- [x] `tools/check_3d_paths.py` + ten plik.
- [ ] Krok 0a: baseline na formacie KiCad 9 (pliki sa w KiCad 9: sch 20250114,
      pcb 20241229):
      ```bash
      mkdir -p .baseline
      kicad-cli sch erc --output .baseline/erc_k9.rpt kicad/ibm-modern-m-ssk.kicad_sch
      kicad-cli pcb drc --output .baseline/drc_k9.rpt kicad/ibm-modern-m-ssk.kicad_pcb
      kicad-cli sch export netlist --output .baseline/k9.net kicad/ibm-modern-m-ssk.kicad_sch
      ```
- [ ] Krok 0b: wlasciciel otwiera projekt w KiCad 10, sprawdza okno brakujacych
      bibliotek i podglad 3D (C 0402/0603, zlacza FFC), zapisuje schemat i PCB.
      Ponownie ERC/DRC/netlista (`*_k10`), porownanie z k9 (netliste porownuj bez
      linii `source`/`date`/`tool`). Rowne -> commit
      `chore: upgrade project files to KiCad 10 format`.
      Jesli w 3D brakuje modeli z `${KICAD9_3DMODEL_DIR}` (35 odwolan w PCB):
      osobny commit z zamiana na `${KICAD10_3DMODEL_DIR}`.
- [ ] Krok 3: `mkdir -p hardware && git mv kicad hardware/controller`.
      Biblioteki jada razem, `${KIPRJMOD}/libraries` dalej dziala. Weryfikacja:
      projekt sie otwiera, ERC/DRC/netlista = baseline. Usun z `.gitignore` linie
      `/kicad/production/` (osobny commit lub ten sam, to nie jest plik KiCada).
- [ ] Krok 4a: `git mv hardware/controller/libraries hardware/lib` (sam rename, commit).
- [ ] Krok 4b: edycja sciezek (osobny commit):
      ```bash
      sed -i 's|\${KIPRJMOD}/libraries/|${KIPRJMOD}/../lib/|' \
          hardware/controller/fp-lib-table hardware/controller/sym-lib-table
      git grep -lzF -e '${KIPRJMOD}/libraries/' -e '${EASYEDA2KICAD}/' -- \
          'hardware/controller/*.kicad_pcb' 'hardware/lib/' \
        | xargs -0 sed -i -e 's|\${KIPRJMOD}/libraries/|${KIPRJMOD}/../lib/|g' \
                          -e 's|\${EASYEDA2KICAD}/|${KIPRJMOD}/../lib/|g'
      python3 tools/check_3d_paths.py hardware/controller hardware/lib
      ```
      Oczekiwane po 4b: 0 nierozwiazanych zmiennych, tylko 4 znane brakujace pliki
      (ponizej). Przed 4b ten sam skrypt z `EASYEDA2KICAD=$PWD/hardware/lib` daje
      OK=51, problemy=4. Potem: brak okna "missing library", modele 3D widoczne,
      ERC/DRC/netlista = baseline, `git log --follow` na pliku z `hardware/lib` widzi
      stara historie.
- [ ] Krok 5: wlasciciel wrzuca eksporty dokumentow do `docs/project/`; README
      dostaje sekcje "Struktura repozytorium" (zgodna z drzewem ponizej).
- [ ] Krok 6: tag `restructure-done`, merge do `main` (na prosbe wlasciciela).

## Docelowe drzewo

```
hardware/lib/            jedyna biblioteka robocza (symbole, footprinty, 3dshapes)
hardware/controller/     MB + DB, jedna PCB
hardware/membrane/       nowy projekt od zera (NIE kopia controller: UUID/instances)
production/controller/   zamrozone paczki zamowien
mechanics/               README z linkiem Onshape, exports/, measurements/
docs/                    project/ (snapshoty), datasheets/, diagrams/
thesis/                  LaTeX: main.tex, chapters/NN-nazwa.tex, figures/, bib/
reference/               cudze projekty i referencje: nordic/, fssk-v1.00/
tools/                   skrypty pomocnicze
```

## Znane problemy (nie naprawiac przy okazji migracji)

- 4 footprinty wskazuja nieistniejace modele 3D: `FC-135R_L3.2-W1.5`, `LED0603-RD`,
  `SOD-723_L1.0-W0.6-P1.4-RD`, `SW-SMD_L3.9-W3.0-P4.45` (-> `SW-SMD_L3.9-W2.9-H2.0-LS4.8.wrl`).
- `${EASYEDA2KICAD}` w 30 footprintach to zmienna z lokalnej konfiguracji KiCada,
  nie z repo; krok 4b ja usuwa.
- `matrix.kicad_sch`: 174 instancje `(project "matrix")`, w matrix/motherboard 5
  instancji `(project "")`: pozostalosci po dawnym osobnym projekcie. Nie ruszac
  przed rename projektu; rename testowac tylko na kopii.
- Footprinty Nordica w `hardware/lib` roznia sie od oryginalow w `reference/nordic/`:
  lib = wersja robocza, reference = oryginal producenta. To nie duplikaty.

## Faza 2 (po migracji, osobne zadania)

- Nanoszenie zmian z Changelogu do schematu (stan: zatwierdzone, nienaniesione).
- Lacze MB <-> DB, propozycja DO ZATWIERDZENIA przez wlasciciela: dwa symbole
  (`J_MB` w arkuszu MB, `J_DB` w arkuszu DB), sieci po stronie DB z prefiksem
  `DB_` (`DB_VBUS`, `DB_GND`, `DB_D+`, `DB_D-`, `DB_CC1`, `DB_CC2`), identyczne
  mapowanie pin->siec; `J_DB` wykluczony z BOM i pozycji; brak footprintu 1x10
  P1.00 w lib (jest tylko 1x08 SMD), trzeba go dodac. Weryfikacja mapowania
  skryptem na netliscie.
- Projekt `hardware/membrane/`.
