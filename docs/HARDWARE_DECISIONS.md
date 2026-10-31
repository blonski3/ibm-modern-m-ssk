# Hardware Decisions: baza do pracy inżynierskiej

2026-10-11 (treść decyzji) · od 2026-10-17 źródłem prawdy jest ten plik w repo; dokument w Claude Docs to archiwum ze stanu 11.10 (rev 25).

Wszystkie pięć domen przeszło pierwszy audyt: PMIC (nPM1300-QEAA, szyna 3,3 V z BUCK2), MCU i radio (nRF52840-QIAA), interfejsy, złącze rozszerzeń i ustawienia firmware'u. Zmiany są zatwierdzone, ale jeszcze nienaniesione w KiCadzie; mechanika i membrana są w toku.

> **Zasada prowadzenia:** wpis dla bloku/komponentu dodajemy po zatwierdzeniu: przyjęte parametry, uzasadnienie, wzór z dokumentacji, referencja ze stroną (nPM1300_PS_v1.3, nRF52840_PS_v1.5). Otwarte kwestie na końcu dokumentu.

## Założenia architektoniczne

Ramy zatwierdzone 11.10.2026.

| Obszar | Ustalenie |
| --- | --- |
| Podział na płytki | Motherboard i daughterboard projektowane i zamawiane jako jedna płytka, DB wyłamywany; membrana jako osobna płytka FPC |
| Projekty KiCada | `controller` (arkusze motherboard i daughterboard) oraz `membrane`; wspólna biblioteka `lib` |
| MCU | nRF52840-QIAA, VDD = VDDH = 3,3 V (tryb Normal Voltage), REG1 w trybie DC/DC |
| PMIC | nPM1300-QEAA, BUCK2 = 3,3 V, BUCK1 wyłączony, sterowanie przez I2C |
| USB-C | Gniazdo, bezpiecznik PTC i ESD na DB; CC1/CC2 bezpośrednio do nPM1300 (wewnętrzne Rd 5,1 kΩ), bez zewnętrznych rezystorów |
| Łącze MB ↔ DB | Listwa goldpin 1×10, raster 1 mm, piny lutowane do krawędzi DB i wchodzące pionowo w MB: 2× VBUS, 4× GND, D+, D−, CC1, CC2 |
| Matryca | Własna membrana FPC, 6 wierszy × 17 kolumn, 88 przełączników, dioda na klawisz (87 diod: Backspace ma dwa styki SW17 i SW31 równolegle na D34, jak w oryginale); złącza FFC 1,0 mm: J4 (18 pinów) i J7 (6 pinów) |
| Bateria | Li-Po ok. 1000 mAh (wymiary klasy LP803040), 4,2 V, z PCM, dwa przewody z wtykiem JST PH 2.0 (J2), bez NTC; w drukowanym koszyku, nieklejona do PCB |
| Ładowanie | Prąd i napięcie końcowe ustawiane przez firmware; sprzęt wymiarowany na 800 mA |
| Przyciski | Tylko RESET na MB; BT_PAIR i SHPHLD usunięte |
| Dioda RGB | Jedna WS2812B-2020-V6 na motherboardzie, zasilana z VSYS przez LOADSW1 |
| Programowanie | SWD przez złącze Tag-Connect TC2030 |
| Firmware | ZMK na Zephyr 4.1 (Hardware Model V2) |
| Smart features | Haptyka i akcelerometr na osobnych płytkach; na MB złącze rozszerzeń J3 2×3 (listwa SMD 1,27 mm) z VSYS, 3,3 V, I2C i przerwaniem |

## Blok PMIC: połączenia nPM1300-QEAA

Układ pracuje w konfiguracji 1 z datasheetu ograniczonej do jednej przetwornicy: BUCK2 daje 3,3 V dla nRF52840 i VDDIO, BUCK1 jest wyłączony. Wszystkie referencje dotyczą nPM1300 Product Specification v1.3.

| Pin | Połączenie | Uzasadnienie | Referencja |
| --- | --- | --- | --- |
| 21 VBUS | VBUS z DB, C27 1 µF do GND | Wejście zasilania, tolerancja do 22 V | Rys. 59, s. 161; tab. 4, s. 17 |
| 23 CC1, 24 CC2 | Bezpośrednio do gniazda USB-C (przez łącze MB ↔ DB) | Piny mają wewnętrzne Rd = 5,1 kΩ i komparatory wykrywające wydajność źródła; muszą być połączone bezpośrednio z gniazdem | Rozdz. 6.1.3, s. 20–21; tab. 9, s. 22 |
| 22 VBUSOUT | C32 1 µF do GND, pin VBUS nRF52840 z C21 4,7 µF | Chronione napięcie VBUS dla detekcji USB w nRF; kondensator wymagany | Rozdz. 6.1.5, s. 21 |
| 19 VBAT | C28 2,2 µF do GND, przez Q1 do złącza baterii J2 | Odsprzęganie wejścia baterii | Rys. 59, s. 161 |
| 18 NTC | Do GND | Termistor nieużywany; funkcję trzeba wyłączyć w rejestrze BCHGDISABLESET | Rozdz. 6.2.4, s. 29 |
| 20 VSYS + 4 PVDD | Połączone; C30 10 µF do PVSS2, C31 10 µF do GND | PVDD to wejście mocy przetwornic; kondensator wejściowy zamyka pętlę prądową BUCK2 | Rys. 59 (C3, C4), s. 161; rozdz. 9.3.4, s. 165 |
| 5 SW2 | L4 2,2 µH do VOUT2 | Cewka BUCK2 | Rys. 59 (L2), s. 161 |
| 32 VOUT2 | Szyna VDD_NRF 3,3 V, C29 10 µF do PVSS2 | Wyjście i sprzężenie zwrotne BUCK2 | Rys. 59 (C8), s. 161 |
| 6 PVSS2 | Net-tie do GND tuż przy pinie | Jeden punkt powrotu pętli mocy do warstwy GND | Rys. 59, s. 161 |
| 16 VSET2 | R10 470 kΩ do GND | Zakres 250–500 kΩ ustawia 3,3 V przy starcie; pin czytany tylko przy włączeniu | Tab. 18, s. 50 |
| 17 VSET1 | Do GND | Poniżej 100 Ω BUCK1 jest wyłączony | Tab. 17, s. 50 |
| 1 VOUT1, 3 SW1, 2 PVSS1 | VOUT1 do VSYS, SW1 niepodłączony, PVSS1 do GND | Zakończenie nieużywanej przetwornicy; wniosek przez symetrię, datasheet pokazuje tylko nieużywany BUCK2 | Rys. 61, s. 162 |
| 12 VDDIO | VDD_NRF, kondensator 100 nF do GND | Zasila TWI i GPIO; musi być obecny poza trybami Ship i Hibernate | Rozdz. 7.6, s. 125; rys. 59 (C13) |
| 13 SDA, 14 SCL | Do GPIO nRF52840 i złącza J3, pull-upy 4,7 kΩ do VDDIO | Magistrala konfiguracji i pomiarów, adres 7-bitowy 110 1011 | Rozdz. 7.6, s. 125; rys. 59 (R1, R2) |
| 7 GPIO0, 8 GPIO1 | GPIO0 do nRF52840 jako przerwanie; GPIO1 z nRF52840 jako włącznik LOADSW1 | Tryb GPOIRQ zgłasza zdarzenia VBUS, CC i ładowarki | Rozdz. 6.6, s. 89–92 |
| 15 SHPHLD | Niepodłączony, punkt testowy | Wewnętrzny pull-up 50 kΩ; bez przycisku z trybu Ship wychodzi się przez podłączenie VBUS | Rozdz. 7.4, s. 121; tab. 32, s. 122 |
| 28 LSIN1 | VSYS | Wejście przełącznika obciążenia, do 100 mA | Tab. 22, s. 75 |
| 29 LSOUT1 | C33 1 µF do GND, przełączane zasilanie diody WS2812C-2020 na MB | Firmware może odciąć zasilanie diody | Rys. 61 (C14), s. 162 |
| 30 LSIN2, 31 LSOUT2 | Do GND | Nieużywany przełącznik | Rys. 61, s. 162 |
| 25–27 LED0–LED2 | Niepodłączone | Wolne wyjścia 5 mA, wysoka impedancja w stanie wyłączonym | Rozdz. 6.2.7, s. 31 |
| 33 AVSS | GND | Pad termiczny i masa analogowa | Tab. 34, s. 155 |

## Blok PMIC: dobrane elementy

Wszystkie elementy spełniają wymagania datasheetu.

| Element | Typ i parametry | Wymaganie | Referencja | Ocena |
| --- | --- | --- | --- | --- |
| L4 | APV APH252010T2R2M: 2,2 µH ±20%, Isat 3 A, Irms 2,1 A, DCR 70 mΩ, 1008 | 2,2 µH, tolerancja ≤ 20%, Isat > 350 mA, Imax > 200 mA, DCR ≤ 400 mΩ | Tab. 19, s. 51 | Spełnia |
| C29, C30, C31 | Yageo CC0603MRX5R8BB106: 10 µF ±20%, 25 V, X5R, 0603 | 10 µF X5R 25 V 0603; efektywnie ≥ 4 µF, ESR ≤ 50 mΩ na wyjściu BUCK | Tab. 20, s. 51; tab. 39, s. 162 | Spełnia; pojemność przy 3,3 V do potwierdzenia w krzywej DC-bias |
| C27 (VBUS) | Yageo CC0603KRX7R9BB105: 1 µF ±10%, 50 V, X7R | 1,0 µF | Tab. 39 (C1) | Spełnia, z zapasem napięciowym |
| C32 (VBUSOUT) | 1 µF, 50 V, X7R | 1,0 µF, wymagany także przy nieużywanym pinie | Tab. 39 (C5); rozdz. 6.1.5 | Spełnia |
| C28 (VBAT) | Yageo CC0603KRX5R8BB225: 2,2 µF ±10%, 25 V, X5R | 2,2 µF | Tab. 39 (C6) | Spełnia |
| C33 (LSOUT1) | 1 µF, 50 V, X7R | 1,0 µF w trybie przełącznika | Tab. 40 (C14), s. 163 | Spełnia |
| Kondensator VDDIO | 100 nF, nowy element | 100 nF | Tab. 39 (C13) | Do dodania |
| Pull-upy SDA/SCL | 2× 4,7 kΩ, nowe elementy | Zależne od prędkości i pojemności magistrali; referencja 10 kΩ | Tab. 39 (R1, R2) | Do dodania |
| R10 (VSET2) | 470 kΩ, 0402 | 250–500 kΩ, tolerancja ≤ 5% | Tab. 18, s. 50 | Spełnia |
| Q1 | Alpha & Omega AO3401A (LCSC C15127, JLC basic): P-MOSFET −30 V, VGS ±12 V, SOT-23; RDS(on) maks. 85 mΩ przy VGS = −2,5 V | Zabezpieczenie przed odwróconą baterią; dren od strony złącza, RDS(on) ≤ 100 mΩ przy VGS = −2,5 V, prąd ≥ 1 A | Wymaganie własne projektu | Spełnia; dren (pin 3) do J2.1, źródło (2) do VBAT, bramka (1) do GND; symbol `ibm_m:AO3401A`. W schemacie tymczasowo Q2 |
| J2 | JST PH `S2B-PH-SM4-TB`, 2,0 mm, SMD poziome | Decyzja 2026-10-25: ogniwo kupowane z wtykiem JST PH 2.0 zamiast PicoBlade z LP803040 | Karta JST PH | Spełnia; biegunowość wtyku względem J2.1 (plus) do sprawdzenia przy zakupie ogniwa |
| BT1 | Akyga LP803040: 1000 mAh, 3,7 V, ładowanie do 4,2 V, standardowo 0,2 C, maks. 1 C, 0–45 °C, PCM (4,30 V / 2,5 V) | Prąd ładowania w zakresie 32–800 mA układu | Karta LP803040; rozdz. 6.2.3, s. 28 | Założenie robocze |

## Blok PMIC: obliczenia

### Tętnienia prądu cewki BUCK2

Szczytowy prąd cewki wynosi 0,27 A, czyli 9% prądu nasycenia L4 (3 A). Liczone dla najgorszego przypadku: zasilanie z USB (5,0 V), pełne obciążenie 200 mA, częstotliwość PWM 3,6 MHz (podpisy rys. 37–38, s. 63–64).

```latex
\Delta I_L = \frac{V_{OUT}\left(1 - \frac{V_{OUT}}{V_{IN}}\right)}{L \cdot f_{SW}} = \frac{3{,}3 \cdot \left(1 - \frac{3{,}3}{5{,}0}\right)}{2{,}2\,\mu\mathrm{H} \cdot 3{,}6\,\mathrm{MHz}} = 0{,}142\,\mathrm{A}
```

```latex
I_{L,pk} = I_{OUT} + \frac{\Delta I_L}{2} = 0{,}200 + 0{,}071 = 0{,}271\,\mathrm{A}
```

Przy indukcyjności na dolnej granicy tolerancji (1,76 µH) szczyt rośnie do 0,289 A. Wymaganie datasheetu Isat > 350 mA jest spełnione z dużym zapasem.

### Obciążenie szyny 3,3 V

nRF52840 przy nadawaniu +8 dBm pobiera 16,4 mA (regulator DC/DC, nRF52840 PS v1.5, rozdz. 5.2.1.5, s. 61), czyli 8% wydajności BUCK2 (200 mA, tab. na s. 51). Haptyka i dioda RGB są zasilane z VSYS, nie z tej szyny.

### Zakres regulacji 3,3 V

Przetwornica utrzymuje 3,3 V, dopóki VSYS przekracza napięcie wyjściowe o spadek VDROP_OUT (100 mV przy 1 mA, s. 51), czyli do VBAT około 3,4 V. Poniżej VDD podąża za baterią. nRF52840 pracuje od 1,7 V, więc układ działa do odcięcia; ustawienie 3,0 V (150 kΩ na VSET2) utrzymałoby regulację w całym zakresie rozładowania.

### Straty w ładowarce liniowej

Przy maksymalnym prądzie 800 mA układ rozprasza do 1,6 W i nagrzewa się o około 39 K ponad otoczenie; przy 400 mA jest to 0,8 W i 19 K. RθJA = 24,2 °C/W dla QFN32 według JESD51-7 (tab. 7, s. 18); najgorszy przypadek to VBUS = 5,0 V i VBAT = 3,0 V.

```latex
P = (V_{BUS} - V_{BAT}) \cdot I_{CHG} = (5{,}0 - 3{,}0) \cdot 0{,}8 = 1{,}6\,\mathrm{W}, \qquad \Delta T = P \cdot R_{\theta JA} = 1{,}6 \cdot 24{,}2 \approx 39\,\mathrm{K}
```

Ładowanie zatrzymuje się samo przy 110 °C struktury i wznawia przy 100 °C (tab. 16, s. 34–35).

### Spadek napięcia na Q1

Pierwotny PMZB350UPE (450 mΩ) dawał 0,18 V spadku przy 400 mA i 0,36 V przy 800 mA. Ładowarka reguluje napięcie na pinie VBAT, więc ogniwo wchodziło w fazę stałego napięcia wcześniej i ładowało się dłużej. AO3401A (maks. 85 mΩ przy VGS = −2,5 V, typowo ok. 60 mΩ) daje najwyżej 34 mV przy 400 mA i 68 mV przy 800 mA. W fazie stałego napięcia prąd maleje, więc przy prądzie końcowym 40 mA różnica wynosi 3 mV i ogniwo dochodzi do 4,2 V. Przy pracy z baterii (kilkanaście mA) spadek jest poniżej 2 mV.

```latex
\Delta V_{Q1} = I_{CHG} \cdot R_{DS(on)} = 0{,}4 \cdot 0{,}085 = 0{,}034\,\mathrm{V}
```

Rozważany PMPB15XP (20 mΩ, 8 mV przy 400 mA) jest w JLC częścią extended, a AO3401A basic; różnica spadku nie ma praktycznego znaczenia, więc wybrano tańszy wariant (2026-10-25).

## Blok MCU i radio: nRF52840-QIAA

Układ pracuje w konfiguracji 5 z datasheetu bez NFC: VDD = VDDH (tryb Normal Voltage), przetwornica REG1 włączona, USB aktywne. Wszystkie referencje dotyczą nRF52840 Product Specification v1.5.

### Połączenia

| Pin | Połączenie | Uzasadnienie | Referencja |
| --- | --- | --- | --- |
| VDD (A22, AD14, AD23, B1, W1), VDDH (Y2) | Szyna VDD_NRF 3,3 V z BUCK2; C7, C8, C12 100 nF, C14 1 µF, C6 4,7 µF | VDDH zwarty z VDD wybiera tryb Normal Voltage, REG0 pominięty | Tab. 162, s. 598; rys. 217, s. 599 |
| DCC (B3) | L2 10 µH i L3 15 nH szeregowo do DEC4/DEC6; C15 1 µF, C16 47 nF | Filtr wyjściowy przetwornicy REG1 | Rys. 217, s. 599 |
| DCCH (AB2) | Niepodłączony | Przetwornica REG0 nieużywana | Rys. 217, s. 599 |
| DEC1, DEC3, DEC5, DECUSB | C5 100 nF, C11 100 pF, C9 820 pF, C20 4,7 µF | Odsprzęganie regulatorów wewnętrznych; C9 zbędny od wersji Fxx | Tab. 163, s. 600 |
| VBUS (AD2) | VBUSOUT z nPM1300, C21 4,7 µF | Detekcja USB i zasilanie regulatora USB 3,3 V z chronionego napięcia | Rozdz. 6.1.5 nPM1300 PS, s. 21 |
| D+ (AD6), D− (AD4) | Bezpośrednio do gniazda USB-C przez ESD | Pull-up D+ jest wewnętrzny; zewnętrznych elementów nie wolno dodawać | Rozdz. 6.35, opis USBPULLUP |
| XC1, XC2 | Y1 32 MHz, C1 i C2 12 pF | Zegar radia; wymagane ±40 ppm dla BLE | Rozdz. 5.4.4.2, s. 99 |
| XL1, XL2 (P0.00, P0.01) | Y2 32,768 kHz, C17 i C18 12 pF | Zegar niskiej częstotliwości dla stosu BLE i uśpienia | Rozdz. 5.4.4.3, s. 100 |
| ANT (H23) | C3 1,0 pF do GND, L1 4,7 nH szeregowo, C4 1,2 pF do GND, L5 2,2 nH szeregowo, złącze U.FL J6 | Dopasowanie do 50 Ω z referencji Nordica konfiguracja 7 (4 elementy); drugi stopień LC mocniej tłumi 2. i 3. harmoniczną | Referencja nRF52840-QIAA config 7 |
| P0.18/nRESET (AC13) | Sieć RESET: przycisk SW1 (XKB TS-1187A-B-A-B) do GND, pin 3 złącza J10 | Reset sprzętowy i wejście w bootloader | Tab. 145, s. 579; rozdz. 4.5.1.4, s. 45 |
| SWDIO (AC24), SWDCLK (AA24) | Piny 2 i 4 złącza J10 (Tag-Connect TC2030) | Programowanie i debug | Tab. 145, s. 579 |
| P1.00 (AD22) | SWO, pin 6 złącza J10 | Podgląd logów przez programator | Tab. 145, s. 580 |
| P0.09, P0.10 (NFC) | Niepodłączone | NFC nieużywane | Tab. 162, s. 598 |

### Przydział GPIO

Potrzeba 27 linii: 17 kolumn, 6 wierszy, SDA, SCL, przerwanie PMIC i dane diody RGB. Piny oznaczone w tab. 145 jako „standard drive, low frequency I/O only" przyjmują sygnały do 10 kHz; matryca skanowana około 1 kHz się w tym mieści, I2C i dioda RGB nie. Numery pinów zostaną ustalone przy routingu.

| Strona układu | Piny | Ograniczenie | Przeznaczenie |
| --- | --- | --- | --- |
| Górna | P0.02, P0.03, P0.28–P0.31, P1.10–P1.15 (12) | Tylko sygnały do 10 kHz | 12 kolumn matrycy |
| Lewa | P0.04–P0.08, P0.11, P0.12, P0.26, P0.27, P1.08, P1.09 (11) | Brak | 5 kolumn i 6 wierszy matrycy |
| Dolna | P0.13–P0.17, P0.19–P0.25, P1.00 (13) | Brak | SDA, SCL, dane diody, SWO, przerwanie EXT_INT złącza J3 (P0.19); 8 wolnych |
| Prawa | P1.01–P1.07, P0.09, P0.10 | Tylko sygnały do 10 kHz, sąsiedztwo anteny | Tylko sygnały statyczne: przerwanie PMIC (GPIO0) i włącznik diody (GPIO1) |

Diody matrycy mają katody na liniach ROW, więc kolumny są wyjściami, a wiersze wejściami (w ZMK kierunek `col2row`).

### Dobrane elementy

| Element | Typ i parametry | Wymaganie (tab. 163, s. 600) | Ocena |
| --- | --- | --- | --- |
| Y1 | NDK NX2016SA-32MHZ-EXS00A-CS06654 (LCSC C5441424): 32 MHz, CL 8 pF, ESR ≤ 60 Ω, 2016 | 32 MHz, CL = 8 pF, ±40 ppm; CL ≤ 12 pF, ESR ≤ 60 Ω (s. 99) | Spełnia; tolerancja i stabilność do potwierdzenia w karcie NDK. Zastąpił Epson Q22FA12800018 (CL 12 pF) |
| Y2 | Epson Q13FC13500003: 32,768 kHz, CL 9 pF, ±20 ppm, ESR 70 kΩ, 3215 | CL = 9 pF, ±50 ppm; ESR ≤ 100 kΩ (s. 100) | Spełnia |
| C1, C2, C17, C18 | Yageo CC0402GRNPO9BN120: 12 pF ±2%, NP0, 50 V | 12 pF, NP0, ±2% | Spełnia |
| L1 | Tai-Tech HCI1005LF-4N7S: 4,7 nH ±5%, SRF 4 GHz, 0402 | 4,7 nH ±5%, wysokoczęstotliwościowa | Spełnia; brak w magazynie LCSC |
| L2 | Murata LQM18FN100M00D: 10 µH ±20%, 50 mA, DCR 1,17 Ω, 0603 | 10 µH ±20%, prąd min. 50 mA | Spełnia bez zapasu |
| L3 | FH VHF100505H15NKT: 15 nH ±10%, SRF 2,3 GHz, 0402 | 15 nH ±10%, wysokoczęstotliwościowa | Spełnia |
| C6, C20, C21 | Yageo CC0603KRX5R7BB475: 4,7 µF ±10%, X5R, 16 V | 4,7 µF ±10%, X7R lub X7S | Odstępstwo: X5R zamiast X7R, akceptowalne do 85 °C |
| C3, C4, L5 | FH 0402CG1R0C500NT 1,0 pF (LCSC C1550), FH 0402CG1R2C500NT 1,2 pF (C1551), C0G, 0402; Chilisin CLH1005T-2N2S-S-NP 2,2 nH (C142238), SRF 8,1 GHz | Wartości z referencji config 7 | Spełnia; strojone pod płytkę Nordica, na prototypie pomiar VNA |

### Obliczenia: obciążenie kwarców

Kwarc 32 MHz z CL = 8 pF i kondensatorami 12 pF jest obciążony dokładnie nominalnie. Pojemność pinu XC1/XC2 wynosi 3 pF (s. 99), pojemność ścieżek przyjęto 1 pF.

```latex
C_L = \frac{C_1' \cdot C_2'}{C_1' + C_2'}, \qquad C_n' = C_n + C_{pcb} + C_{pin} = 12 + 1 + 3 = 16\,\mathrm{pF} \;\Rightarrow\; C_L = 8\,\mathrm{pF}
```

Dotychczasowy kwarc o CL = 12 pF w tym samym układzie był niedociążony o 4 pF. Dla typowej pojemności dynamicznej 2–3 fF i C0 = 1 pF (wartości założone, do weryfikacji w karcie) daje to odstrojenie 34–51 ppm w górę.

```latex
\frac{\Delta f}{f} = \frac{C_m}{2}\left(\frac{1}{C_0 + C_{L,rz}} - \frac{1}{C_0 + C_{L,nom}}\right) = \frac{3\,\mathrm{fF}}{2}\left(\frac{1}{9\,\mathrm{pF}} - \frac{1}{13\,\mathrm{pF}}\right) \approx 51\,\mathrm{ppm}
```

Kwarc 32,768 kHz (CL = 9 pF) z kondensatorami 12 pF i pinem 4 pF (s. 100) widzi 8,5 pF, czyli 0,5 pF poniżej nominału. Stos BLE wymaga ±500 ppm, kwarc daje ±20 ppm.

## Blok interfejsów: USB-C, łącze MB ↔ DB, matryca, dioda

Część elektryczna jest zatwierdzona; typ listwy, geometria membrany i uchwyt DB czekają na projekt mechaniczny w Onshape.

### Daughterboard

| Element | Połączenie i parametry | Uzasadnienie | Ocena |
| --- | --- | --- | --- |
| J1 | Korean Hroparts TYPE-C-31-D-06, 16 pinów, pionowe SMD; cztery piny VBUS razem, D+ i D− zmostkowane parami, CC1 i CC2 osobno, SBU wolne, ekran do GND | Gniazdo USB 2.0; osobne linie CC są warunkiem wykrycia orientacji i wydajności źródła | Bez zmian |
| U3 | TI TPD4E05U06 na CC1, D+, D−, CC2 w układzie przelotowym (piny 1/10, 2/9, 4/7, 5/6) | Ochrona ESD czterech linii sygnałowych tuż przy gnieździe | Bez zmian |
| F1 | TECHFUSE SMD1210-110-24V (LCSC C22436715): trzyma 1,1 A, wyzwala 2,2 A, 24 V, obudowa 1210 | Ogranicza prąd przy zwarciu za gniazdem | Spełnia (od 2026-10-25) |
| D1 | MDD SMF20A (LCSC C123788): jednokierunkowa, VRWM 20 V, VC 32,4 V, 200 W, SOD-123FL; katoda na DB_VBUS | Ochrona ESD i przepięć linii VBUS | Spełnia (od 2026-10-25) |
| SW89, SW91, D4, D92 | Usunięte z DB | Parowanie w ZMK, wyjście z trybu Ship przez VBUS, dioda przeniesiona na MB | Do usunięcia |

### Koordynacja zabezpieczeń toru VBUS

Po wymianie F1 i D1 każdy element na VBUS wytrzymuje co najmniej 20 V, a nPM1300 odłącza VBUS od układu powyżej 5,5 V; klawiatura pracuje wtedy z baterii. Źródło USB-C podaje więcej niż 5 V tylko po negocjacji Power Delivery, której klawiatura nie prowadzi, więc chodzi o przypadek wadliwej ładowarki.

| Element na VBUS | Wytrzymałość dziś | Wytrzymałość docelowa | Referencja |
| --- | --- | --- | --- |
| nPM1300, pin VBUS | 22 V, odłączenie powyżej 5,5 V (VBUSOVP) | Bez zmian | nPM1300 PS v1.3, tab. 4, s. 17; rozdz. 6.1.2, s. 20; tab. 9, s. 22 |
| C27 | 50 V | Bez zmian | Karta Yageo |
| F1 | 24 V, prąd podtrzymania 1,1 A (SMD1210-110-24V) | ≥ 24 V, prąd podtrzymania ≥ 1 A: spełnia | Karta elementu |
| D1 | VRWM 20 V (SMF20A) | VRWM ≥ 20 V: spełnia | Karta elementu |
| Pin VBUS nRF52840 | Zasilany z VBUSOUT, za zabezpieczeniem nPM1300 | Bez zmian | nPM1300 PS v1.3, rozdz. 6.1.5, s. 21 |

Dwa ograniczenia zostają. TVS o napięciu pracy 20 V ogranicza impuls ESD na poziomie około 30 V, czyli chwilowo powyżej 22 V. Linie CC wytrzymują 5,5 V (tab. 4, s. 17), więc zwarcie CC do VBUS przy 20 V wymagałoby osobnego układu ochrony portu.

### Łącze MB ↔ DB

Listwa goldpin 1×10, raster 1 mm, proste piny lutowane powierzchniowo do krawędzi DB i wchodzące pionowo w otwory MB. DB jest przykręcony do drukowanego uchwytu, a uchwyt do MB, więc siły od wtyczki nie obciążają lutów.

| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sygnał | VBUS | VBUS | CC1 | GND | D+ | D− | GND | CC2 | GND | GND |

Para D+/D− ma masę po obu stronach, VBUS ma dwa styki, GND cztery. Numeracja i lustrzane odbicie między płytkami do sprawdzenia na modelu 3D.

### Złącza matrycy

J4 (18 styków) i J7 (6 styków) to Jushuo AFB10, raster 1,0 mm, pionowe, bez zatrzasku, ze stykami po jednej stronie, na taśmę o grubości 0,3 mm, 0,5 A na styk. Matryca zajmuje 23 styki (17 kolumn, 6 wierszy); 24. styk proponowany na GND. Membrana musi mieć ogony o grubości 0,3 mm z usztywnieniem i styki po stronie zgodnej ze złączem. Złącze trzyma taśmę tylko tarciem, więc przy drganiach od sprężyn warto rozważyć wersję z zatrzaskiem.

### Dioda statusu

Jedna Worldsemi WS2812B-2020-V6 (LCSC C52917434) na MB, zasilana z VSYS przez przełącznik LOADSW1 nPM1300, z kondensatorem 100 nF przy diodzie i C33 1 µF na wyjściu przełącznika.

| Parametr | Wartość z karty | Warunek w projekcie | Ocena |
| --- | --- | --- | --- |
| Napięcie zasilania | 3,3–5,3 V (opis JLC; karta do potwierdzenia) | VSYS: 3,0–4,2 V z baterii, około 5 V z USB | W zakresie na USB i przy baterii powyżej 3,3 V; poniżej działanie niegwarantowane. WS2812C-2020 (3,7 V min.) zastąpiona 2026-10-26, bo niedostępna w JLC |
| Próg VIH wejścia DIN | min. 2,7 V (karta WS2812C; dla V6 do potwierdzenia) | Logika nRF52840 3,3 V | Spełniony bez konwersji poziomów, jeśli V6 ma ten sam próg |
| Prąd spoczynkowy | < 0,5 mA | Odcinany przez LOADSW1 | Uzasadnia przełącznik |
| Prąd kanału | 5 mA | LOADSW1 do 100 mA | Spełnia |
| Szybkość danych | 800 kb/s | Pin nRF bez ograniczenia częstotliwości (dolna strona) | Spełnia |
| Odsprzęganie | 100 nF | 100 nF przy diodzie | Spełnia |

Bez przełącznika sama dioda rozładowałaby ogniwo 1000 mAh w około 83 dni.

```latex
t = \frac{Q}{I_Q} = \frac{1000\,\mathrm{mAh}}{0{,}5\,\mathrm{mA}} = 2000\,\mathrm{h} \approx 83\,\mathrm{dni}
```

Przy wyłączonym przełączniku firmware musi trzymać linię DIN w stanie niskim, żeby nie zasilać diody przez wejście danych.

## Smart features: złącze rozszerzeń J3

Haptyka i akcelerometr nie są na motherboardzie; MB wyprowadza zasilanie, I2C i jedną linię przerwania na złącze 2×3 pod osobne płytki modułów. Złącze: listwa goldpin 2×3, raster 1,27 mm, SMD, pionowa (`Connector_PinHeader_1.27mm:PinHeader_2x03_P1.27mm_Vertical_SMD`), symbol `Conn_02x03_Odd_Even`; po stronie modułów gniazdo 1,27 mm albo tasiemka IDC.

| Pin | Sygnał | Pin | Sygnał |
| --- | --- | --- | --- |
| 1 | VSYS (3,0–5 V, nieregulowane) | 2 | 3,3 V z BUCK2 (VDD_NRF) |
| 3 | GND | 4 | EXT_INT: przerwanie akcelerometru, P0.19 |
| 5 | SCL | 6 | SDA |

| Decyzja | Uzasadnienie | Referencja |
| --- | --- | --- |
| Dwa zasilania: VSYS i 3,3 V | Sterownik haptyki pobiera prąd silnika z VSYS; BUCK2 ma 200 mA na cały układ, więc dla modułów na 3,3 V przyjęto budżet 100 mA | nPM1300 PS v1.3, tab. na s. 51; tab. 3, s. 16 |
| I2C wspólne z nPM1300 | Jedna magistrala; nPM1300 ma adres 7-bitowy 110 1011 (0x6B); adresy modułów do sprawdzenia w ich kartach | nPM1300 PS v1.3, rozdz. 7.6, s. 125 |
| Jedna linia przerwania (P0.19, dolna strona nRF52840); bez linii EN haptyki | Pin bez ograniczenia częstotliwości, może budzić układ, co wystarcza dla wake-on-motion. Sterownik haptyki usypiany przez I2C (tryb standby) zamiast osobnej linii EN; prąd uśpienia do sprawdzenia w karcie wybranego sterownika. Zmniejszenie z 2×6 do 2×3 na prośbę jakuba (2026-10-25) | nRF52840 PS v1.5, rozdz. 6.9, s. 152; tab. 145, s. 579–580 |
| Pull-upy I2C 4,7 kΩ | Magistrala wychodzi przewodem poza płytkę, więc jej pojemność rośnie | Obliczenie poniżej |

### Obliczenie: pull-upy I2C

Przy 4,7 kΩ tryb 400 kHz jest spełniony do pojemności magistrali około 75 pF; przy 10 kΩ i 100 pF czas narastania wynosiłby 847 ns wobec dopuszczalnych 300 ns. Wzory i limity według specyfikacji magistrali I2C (NXP UM10204), przytoczone z pamięci i do potwierdzenia w dokumencie.

```latex
R_{p,max} = \frac{t_r}{0{,}8473 \cdot C_b} = \frac{300\,\mathrm{ns}}{0{,}8473 \cdot 75\,\mathrm{pF}} \approx 4{,}7\,\mathrm{k\Omega}, \qquad R_{p,min} = \frac{V_{DD} - V_{OL}}{I_{OL}} = \frac{3{,}3 - 0{,}4}{3\,\mathrm{mA}} \approx 0{,}97\,\mathrm{k\Omega}
```

## Firmware: ZMK na Zephyr 4.1

Sprzęt nie wymaga przebudowy pod firmware; audyt dodał jedną linię (włącznik diody) i wskazał jedną niezgodność po stronie ZMK (raportowanie baterii).

### Ustalenia ze źródeł

| Temat | Ustalenie | Skutek dla projektu |
| --- | --- | --- |
| Brak NTC | Sterownik ładowarki nPM1300 w Zephyr 4.1 przy `thermistor-ohms = 0` sam wyłącza funkcję NTC | Pin NTC do GND wystarczy, bez własnego kodu |
| Limit prądu VBUS | Sterownik zapisuje limit startowy z `vbus-limit-microamp` przy inicjalizacji; nie czyta stanu CC i nie obsługuje przerwań | Stałe 500 mA działa bez własnego kodu; wyższy limit zależny od źródła wymaga własnego modułu |
| Procent baterii | ZMK czyta kanał `SENSOR_CHAN_GAUGE_STATE_OF_CHARGE` albo `SENSOR_CHAN_VOLTAGE`; sterownik nPM1300 udostępnia `SENSOR_CHAN_GAUGE_VOLTAGE` | Potrzebny moduł ZMK pośredniczący między sterownikiem a ZMK |
| Zasilanie diody | `zmk,ext-power-generic` steruje wyłącznie pinem GPIO | Pin nRF52840 do GPIO1 nPM1300, skonfigurowanego jako włącznik LOADSW1 |
| Przerwanie PMIC | Binding `nordic,npm1300` ma `host-int-gpios` i `pmic-int-pin` | GPIO0 nPM1300 do nRF52840; używane przez własny kod |
| Wskaźnik stanu baterii | Algorytm Nordica jest częścią nRF Connect SDK, nie ZMK | Liniowe przeliczenie napięcia w ZMK: 3,45 V = 0%, 4,20 V = 100% |

### Ustawienia startowe

Wartości dla ogniwa LP803040 i portu USB 2.0; zmienia się je w konfiguracji płytki, bez ingerencji w sprzęt.

| Ustawienie | Wartość | Uzasadnienie |
| --- | --- | --- |
| `term-microvolt` | 4 200 000 | Napięcie końca ładowania z karty ogniwa |
| `current-microamp` | 400 000 | 0,4 C; karta dopuszcza do 1 C, standard to 0,2 C; pełne ładowanie mieści się w limicie 7 h (nPM1300 PS v1.3, tab. 16, s. 35) |
| `term-current-percent` | 10 | 40 mA, blisko 0,05 C z karty ogniwa |
| `vbus-limit-microamp` | 500 000 | Bezpieczne dla portu USB 2.0; poniżej prądu podtrzymania bezpiecznika |
| `dischg-limit-microamp` | 1 000 000 | Wymagane przy haptyce; dozwolone wartości to 200 mA i 1 A |
| `thermistor-ohms` | 0 | Brak NTC |
| BUCK2 | `regulator-always-on` | Błąd w tym miejscu odcina zasilanie nRF52840 |
| REG1 nRF52840 | Tryb DC/DC | Na płytce są L2 i L3 |
| Matryca | `zmk,kscan-gpio-matrix`, `col2row`, 17 kolumn, 6 wierszy | Katody diod na liniach ROW |
| Reset | P0.18 jako nRESET | Przycisk SW90 i złącze J10 |
| Zegar LF | Kwarc 32,768 kHz, 20 ppm | Y2 |

### Ograniczenia

- Ogniwo wolno ładować w zakresie 0–45 °C, a bez NTC układ tego nie kontroluje; działa tylko ograniczenie temperatury struktury nPM1300 (110 °C).
- Domyślny próg odcięcia VSYSPOF to 2,7 V (nPM1300 PS v1.3, tab. 29, s. 114), a karta ogniwa podaje 3,0 V; podniesienie progu wymaga zapisu rejestru we własnym kodzie.
- Wyjście z trybu Ship jest możliwe tylko przez podłączenie USB.
- Bootloader UF2 trzeba raz wgrać przez SWD; kolejne aktualizacje idą przez USB.
- Sterowanie LOADSW1 przez GPIO1 i zachowanie limitu VBUS po ponownym wpięciu kabla nie były testowane i wymagają sprawdzenia na prototypie.

## BOM pod montaż JLC (2026-10-25)

Zasada: części JLC basic, gdzie nie tracą względem referencji Nordica (extended kosztuje ok. 3 USD za unikalną część na zamówienie). Porównanie z referencjami nRF52840-QIAA config 5 i 7 oraz nPM1300-QEAA config 2.

| Elementy | Część (LCSC) | Typ | Uwagi |
| --- | --- | --- | --- |
| C5, C7, C8, C12, C19, C35 (100 nF 0402) | C1525 CL05B104KO5NNNC, X7R | Basic | |
| C1, C2, C17, C18 (12 pF 0402) | C1547 0402CG120J500NT, C0G ±5% | Basic | ±5% przesuwa CL o ok. 0,3 pF, mieści się w budżecie ±40 ppm |
| C11 (100 pF 0402) | C1546, C0G ±5% | Basic | |
| C6, C20, C21 (4,7 µF 0603) | C19666, X5R 16 V | Basic | |
| C14, C15, C27, C32, C33 (1 µF 0603) | C15849, X5R 50 V | Basic | 50 V dla C27 na VBUS |
| C28 (2,2 µF 0603) | C23630, X5R 16 V | Basic | |
| C29, C30, C31 (10 µF 0603) | C19702, X5R 10 V | Basic | Jak w referencji nPM1300 |
| C16 (47 nF) | C1622, X7R, 0603 | Basic | Footprint zmieniony z 0402 na 0603 |
| R10 (470 kΩ) | C23178, 0603 | Basic | Poprzedni numer C25792 był 47 kΩ |
| R11, R12 (4,7 kΩ) | C25900, 0402 | Basic | |
| R1, R2, R3 (0 Ω) | C21189, 0603 | Basic | R1/R2 w SCL/SDA do J3, miejsce na 33–100 Ω; R3 rozcięcie szyny 3,3 V do pomiarów (A15). 0603 zamiast 0402 (2026-10-31): wygodniejsze ręczne przelutowanie |
| C9 (DEC5) | DNP | – | Niepotrzebny od rewizji Fxx |
| Q1 | AO3401A C15127 | Basic | |
| SW1 | XKB TS-1187A-B-A-B C318884, 5,1 × 5,1 × 1,5 mm | – | Pady A–B i C–D zwarte parami; w footprincie numeracja 1, 1, 2, 2 |
| D2 | WS2812B-2020-V6 C52917434 | Extended | WS2812C-2020 niedostępna |
| J6 | XUNPU U.FL-IPEX-1 C53433123 | Extended | Montaż JLC; sygnał na dolnym małym padzie (1), pozostałe 3 pady GND (2) |
| J2, J8, J9 | – | – | Lutowane ręcznie; na PCB „Exclude from position files” |

Extended zostają: U1, U2, U3, Y1, Y2, C3, C4, L1–L5, D1, D2, F1, J1, J4, J6, J7.

## Weryfikacja prototypu: punkty pomiarowe i plan testów (2026-10-31)

Zatwierdzone i naniesione w schemacie 2026-10-31. Opis funkcji TP na osobnej stronie schematu (do zrobienia).

### Punkty pomiarowe

| Element | Sieć | Po co | Referencja |
| --- | --- | --- | --- |
| R3 0 Ω 0603 (LCSC C21189) | Rozcina szynę 3,3 V: strona przetwornicy U2.32, L4.2, C29.1 (sieć bez nazwy, „VOUT2”) ↔ VDD_NRF (U1, C6–C8, C12, C14, C35, VDDIO U2.12, R11, R12, J3.2, J10.1) | Normalnie wlutowany. Wylutowany: start BUCK2 bez nRF (Z1), prąd samego nRF52840 przez PPK2 (E1), sprawność i tętnienia BUCK2 z obciążeniem zewnętrznym (Z2, Z3). Przewody wlutowane w pady R3 albo chwytaki; bez listwy i dodatkowych padów (decyzja jakuba: porządek na PCB). VOUT2 jest wejściem sprzężenia zwrotnego, więc regulacja się nie zmienia; C29 zostaje przy pinie 32 | nPM1300 PS v1.3, rys. 59, s. 161 |
| TP1 | SHPHLD | Tryb Ship | nPM1300 PS v1.3, rozdz. 7.4, s. 121 |
| TP2 | VDD_NRF | Napięcie szyny nRF (przy wylutowanym R3 napięcie przetwornicy mierzyć na padzie R3 od strony C29) | – |
| TP3 | PVSS2 | Masa do pomiaru tętnień na C29 (tętnienia względem PVSS2, nie odległego GND) | nPM1300 PS v1.3, s. 52 |
| TP4 | VBAT | Spadek na Q1 (z padem J2.1), porównanie z ADC PMIC | s. 104 |
| TP5 | VSYS | Rozładowanie, VSYSPOF | s. 51 |
| TP6 | VLED | LOADSW1 | – |
| TP7, TP8, TP9 | LED_EN, PMIC_INT, RGB_DIN | Analizator logiczny | – |
| TP10 | GND | Masa odniesienia | – |
| TP11, TP12 | P0.16 (AC11), P0.17 (AD12) | Znaczniki czasu z firmware'u (DBG0, DBG1): skan, wykrycie klawisza, wybudzenie; synchronizacja z wejściami cyfrowymi PPK2 | nRF52840 PS v1.5, tab. 145 |
| TP13, TP14 | COL0, ROW0 | Przebieg skanowania matrycy | – |

TP: footprint `ibm_bs:TestPoint_Pad` (exclude from BOM i position files), in_bom = no.

Bez shuntu w torze baterii: ADC nPM1300 mierzy IBAT 10-bitowo z pełną skalą 1,12 × limit rozładowania (przy 1 A ok. 1,1 mA na LSB) i 1,25 × prąd ładowania (nPM1300 PS v1.3, rozdz. 7.1.8, s. 104). Wystarcza do profilu ładowania, nie do prądów uśpienia (µA); te mierzy PPK2 podłączony do J2 zamiast ogniwa. Rezystor szeregowy przy J2 dokładałby tylko spadek przy 800 mA.

### Plan testów

Kolejność grup = kolejność uruchamiania prototypu. Warunki pomiarów prądu: J-Link odłączony od J10, moduły z J3 odłączone, DIN diody w stanie niskim, membrana podłączona.

| ID | Test | Kryterium | Referencja |
| --- | --- | --- | --- |
| Z1 | Start BUCK2 bez nRF (R3 niewlutowany, 3,7 V z limitem 50 mA na J2) | Napięcie przetwornicy 3,3 V ±5% | nPM1300 PS v1.3, s. 51; tab. 18, s. 50 |
| Z2 | Tętnienia na C29 (sonda na C29.1, sprężynka masy na C29.2/PVSS2), tryb histerezowy i PWM | ≤ 50 mVpp / ≤ 5 mVpp; progi trybów 90 / 40 mA | s. 52 |
| Z3 | Sprawność BUCK2 w funkcji prądu (PPK2 na J2, obciążenie na padach R3) | Porównanie z rys. 34 (s. 62) i rys. 3 (s. 14); 93% przy 200 mA PWM | s. 52 |
| Z4 | Odwrotna polaryzacja ogniwa; spadek na Q1 przy 400 mA (J2.1 − TP4) | Prąd ≈ 0; ≤ 34 mV | „Spadek napięcia na Q1” |
| Z5 | LOADSW1 sterowany LED_EN (TP6, TP7) | VLED ≈ VSYS / ≈ 0 V | – |
| Z6 | Tryb Ship, wyjście przez VBUS | ≈ 370 nA | nPM1300 PS v1.3, s. 16 |
| Z7 | Rampa VBAT 4,2 → 2,8 V | Napięcie 3,3 V do VSYS ok. 3,4 V; odcięcie na VSYSPOF; zachowanie diody | s. 51 |
| Ł1 | Profil ładowania CC/CV 400 mA / 4,20 V / 10% (log ADC + multimetr) | ICHG ±10%, VTERM ±1%, czas < 7 h, VBAT z ADC ±1% | s. 34–35, s. 104 |
| Ł2 | Temperatura nPM1300 przy 400 i 800 mA | Porównanie z 19 K i 39 K | tab. 7, s. 18; s. 34 |
| Ł3 | Detekcja źródła przez CC (różne źródła, obie orientacje) i limit VBUS | Poprawny typ źródła; ≤ 500 mA | s. 22, s. 25 |
| Ł4 | Nadnapięcie VBUS 5 → 6 V (opcjonalnie) | Odłączenie powyżej 5,5 V | s. 22 |
| Ł5 | Enumeracja USB HID | W obu orientacjach | – |
| R1 | SWD, UF2, RESET, SWO | Działa; pin 3 TC2030 = nRESET | – |
| R2 | Częstotliwość nośnej (radio_test/DTM, analizator widma na J6) | ≤ ±40 ppm | nRF52840 PS v1.5, s. 99 |
| R3 | Moc i harmoniczne na J6 (0 i +8 dBm) | ±4 dB; harmoniczne wobec config 7 | s. 359 |
| R4 | S11 toru RF (opcjonalnie, VNA) | Wobec config 7 | – |
| R5 | Zasięg BLE i RSSI w obudowie (stalowa płyta) | Stabilne łącze na odległości biurka | – |
| K1 | Wszystkie 88 klawiszy | Właściwe kody | – |
| K2 | NKRO, test ghostingu (3 rogi prostokąta, ≥ 10 klawiszy) | Brak fantomów | – |
| K3 | Debounce | 0 podwójnych zdarzeń na N naciśnięć | – |
| K4 | Okres skanu i opóźnienie wewnętrzne (TP11/TP12 + TP14) | Wynik do pracy; USB vs BLE | – |
| K5 | USB/BLE, parowanie, profile, wybudzenie | Przejścia bez resetu | – |
| K6 | Dioda statusu przy USB i baterii | Poprawne kolory przy VSYS ≥ 3,3 V | – |
| K7 | Procent baterii w ZMK wobec multimetru na TP4 | Liniowo 3,45–4,20 V | s. 104 |
| E1 | Prąd w stanach pracy (PPK2 na J2: cały układ; PPK2 na padach R3: sam nRF) | System OFF 0,40 µA, System ON z RAM 2,35 µA (nRF s. 59), TX +8 dBm 14,8 mA (s. 358), IQ PMIC 800 nA (s. 16) | jw. |
| E2 | Szacowany czas pracy na 1000 mAh z E1 i profilu użycia | Wynik do wniosków | – |
| E3 | Prąd diody (LOADSW1 wł./wył.) | Brak prądu przy wyłączonym | „Dioda statusu” |

Oznaczenie testów radiowych R1–R5 nie ma związku z rezystorami R1–R3 na schemacie.

## Otwarte kwestie

- [x] Typ nowego Q1: AO3401A (C15127, basic), pinout sprawdzony z kartą (2026-10-25; wcześniej PMPB15XP)
- [x] Typ nowego kwarcu Y1: NDK NX2016SA-32MHZ-EXS00A-CS06654 (2026-10-25); tolerancja i stabilność do potwierdzenia w karcie
- [x] Typ nowego F1 (PTC ≥ 24 V, prąd podtrzymania ≥ 1 A) i nowego D1 (TVS z VRWM ≥ 20 V): SMD1210-110-24V i SMF20A (2026-10-25)
- [ ] Limit prądu wejściowego VBUS w firmware nie wyższy niż prąd podtrzymania F1 (1,1 A), czyli 1 A
- [ ] Typ listwy goldpin 1×10, obciążalność styku, numeracja pinów między płytkami na modelu 3D
- [ ] Membrana: geometria ogonów (0,3 mm, raster 1,0 mm, strona styków), miejsce na diody w stosie, typ diod, 24. styk na GND
- [ ] Złącza matrycy: wersja bez zatrzasku czy z zatrzaskiem
- [x] Dopasowanie RF: czteroelementowe z konfiguracji 7 (2026-10-25, M5)
- [ ] Karta WS2812B-2020-V6: próg VIH, prąd spoczynkowy, minimalne VDD
- [ ] Footprint NT1 (net-tie PVSS2 → GND) do narysowania przy PCB
- [ ] Linia 50 Ω od dopasowania do złącza U.FL policzona dla docelowego stackupu; pomiar toru analizatorem
- [ ] Numery pinów nRF52840 dla matrycy, SDA, SCL, przerwania i diody (przy routingu)
- [ ] Pinout kabla Tag-Connect: potwierdzenie, że pin 3 to nRESET
- [ ] Czy wewnętrzne Rd na CC działa przy całkowicie rozładowanej baterii (pytanie do Nordica)
- [ ] Obsługa detekcji CC i braku NTC (`thermistor-ohms = 0`) w sterowniku Zephyra używanym przez ZMK (blok Firmware)
- [ ] Prąd ładowania, napięcie końcowe i próg VSYSPOF dla ogniwa LP803040 (blok Firmware)
- [ ] Sterowanie LOADSW1 i linią DIN diody w ZMK (blok Firmware)
- [ ] Rzeczywista pojemność C29 przy 3,3 V z krzywej DC-bias Yageo
- [ ] Biegunowość wtyku ogniwa względem pinu 1 złącza J2
- [ ] Typ złącza rozszerzeń J3 i sposób połączenia z płytką modułu (mechanika)
- [ ] Układy na płytkach modułów (sterownik haptyki, akcelerometr): adresy I2C, napięcia, pobór prądu
- [ ] Limit prądu rozładowania nPM1300: 1 A, jeśli haptyka będzie używana (blok Firmware)
- [ ] Moduł ZMK udostępniający napięcie baterii z nPM1300 w kanale czytanym przez ZMK
- [ ] Prototyp: sterowanie LOADSW1 przez GPIO1 i zachowanie limitu VBUS po ponownym wpięciu kabla
- [ ] Próg VSYSPOF podniesiony do 3,0 V własnym zapisem rejestru
- [ ] Bootloader UF2: konfiguracja dla płytki i wgranie przez SWD

### Dopisane 2026-10-17 (porządki, do rozstrzygnięcia)

- [ ] Ładowanie bez NTC: nPM1300_PS_v1.3 rozdz. 3.4 wymaga wtedy bezpiecznika termicznego w pakiecie; karta LP803040 wymienia tylko PCM (4,30 V / 2,5 V). Potwierdzić bezpiecznik w ogniwie albo wrócić do NTC 10 kΩ przy ogniwie (dotyczy P7)
- [x] WS2812C-2020 z LSOUT1/VSYS: VSYS nie jest regulowane i przy VBUS ma ok. 5 V (nPM1300_PS_v1.3 rozdz. 6.1.1); przy VIH = 0,7·VDD próg ok. 3,5 V > 3,3 V z nRF. Sprawdzić VIH w karcie WS2812C-2020; ewentualnie translator lub inne zasilanie diody (dotyczy I2). Rozstrzygnięte: karta podaje VIH min. 2,7 V niezależnie od VDD, translator niepotrzebny (tabela „Dioda statusu”)
- [ ] Tętnienia BUCK2: obliczenie ΔI_L dotyczy trybu PWM, a przy obciążeniu ok. 16 mA przetwornica pracuje w trybie histerezowym (PWM od ok. 90 mA wg raportu wykonalności z 11.10, do potwierdzenia w datasheecie); przeliczyć lub zmierzyć do rozdziału pracy
- [ ] VSET2: zostaje 3,3 V czy 3,0 V (sugestia z raportu wykonalności z 11.10)
- [ ] Zakres pracy: czy haptyka i akcelerometr powstają w ramach pracy, czy tylko złącze J3 jako kierunek rozwoju
- [ ] Membrana FPC: jeden arkusz czy segmenty; potrzebny obrys z ogonami (limit JLC 234 × 490 mm, do 250 × 600 mm po uzgodnieniu). Bolt-mod wykonany, rysunki membrany istnieją
- [ ] BOM sprzed audytu: brak J4 przy obecnym J7, J5 726386-2 bez opisu w dokumentach, C10 = NC a dokumenty mówią o nieobsadzonym C22
- [ ] Harmonogram: raport wykonalności z 11.10 zakładał zamówienie rev A do 2026-11-09 i działającą SSK bez kabla do 2026-12-08; nie jest zatwierdzony

### Dopisane 2026-10-31 (weryfikacja prototypu)

- [ ] Strona schematu z opisem TP1–TP14 i R3
- [ ] Zakresy PPK2 (amperomierz, źródło, wejścia cyfrowe) potwierdzone w dokumentacji Nordica
- [ ] Dostęp do analizatora widma i VNA na PWr (testy R2–R4)

## Źródła

- nPM1300 Product Specification v1.3 (4490_483, 2026-03-02), w bazie wiedzy projektu
- nRF52840 Product Specification v1.5 (4413_417), w bazie wiedzy projektu
- Netlista, raport ERC i schemat projektu z 11.10.2026
- [APV APH252010T2R2M, LCSC C5349606](https://www.lcsc.com/product-detail/C5349606.html)
- [Yageo CC0603MRX5R8BB106, LCSC C596327](https://www.lcsc.com/product-detail/C596327.html)
- [Yageo CC0603KRX7R9BB105, LCSC C559769](https://www.lcsc.com/product-detail/C559769.html)
- [Yageo CC0603KRX5R8BB225, LCSC C309478](https://www.lcsc.com/product-detail/C309478.html)
- [Alpha & Omega AO3401A, LCSC C15127](https://www.lcsc.com/product-detail/C15127.html)
- [Nexperia PMPB15XP,115, LCSC C513107](https://www.lcsc.com/product-detail/C513107.html)
- [Nexperia PMZB350UPE, LCSC C478140](https://www.lcsc.com/product-detail/C478140.html)
- [Karta PMZB670UPE (pinout obudowy DFN1006B-3)](https://docs.rs-online.com/c225/0900766b812e057d.pdf)
- [Karta ogniwa Akyga LP803040](https://www.tme.eu/Document/8518e6f80c7c95dc96792c6f2286ce95/aky2417.pdf)
- [Nordic DevZone: nPM1300 hardware](https://devzone.nordicsemi.com/f/nordic-q-a/127900/npm1300-hardware)
- [Zephyr: binding nordic,npm1300-charger](https://docs.zephyrproject.org/latest/build/dts/api/bindings/sensor/nordic,npm1300-charger.html)
- [ZMK: Zephyr 4.1 Update](https://zmk.dev/blog/2025/12/09/zephyr-4-1)

Karty elementów bloku MCU:

- [NDK NX2016SA-32MHZ-EXS00A-CS06654, LCSC C5441424](https://www.lcsc.com/product-detail/C5441424.html)
- [Epson Q22FA12800018, LCSC C255896](https://www.lcsc.com/product-detail/C255896.html)
- [Epson Q13FC13500003, LCSC C99010](https://www.lcsc.com/product-detail/C99010.html)
- [Murata LQM18FN100M00D, LCSC C86083](https://www.lcsc.com/product-detail/C86083.html)
- [Tai-Tech HCI1005LF-4N7S, LCSC C304335](https://www.lcsc.com/product-detail/C304335.html)
- [FH VHF100505H15NKT, LCSC C381880](https://www.lcsc.com/product-detail/C381880.html)
- [Yageo CC0402GRNPO9BN120, LCSC C526985](https://www.lcsc.com/product-detail/C526985.html)
- [Yageo CC0603KRX5R7BB475, LCSC C277476](https://www.lcsc.com/product-detail/C277476.html)

Karty elementów bloku interfejsów:

- [Worldsemi WS2812B-2020-V6, LCSC C52917434](https://jlcpcb.com/partdetail/C52917434)
- [Karta WS2812C-2020](https://akizukidenshi.com/goodsaffix/ws2812c-2020.pdf)
- [XKB TS-1187A-B-A-B, LCSC C318884](https://jlcpcb.com/partdetail/C318884)
- [XUNPU U.FL-IPEX-1, LCSC C53433123](https://jlcpcb.com/partdetail/C53433123)
- [MDD SMF20A, LCSC C123788](https://www.lcsc.com/product-detail/C123788.html)
- [TECHFUSE SMD1210-110-24V, LCSC C22436715](https://www.lcsc.com/product-detail/C22436715.html)
- [Korean Hroparts TYPE-C-31-D-06, LCSC C2689964](https://www.lcsc.com/product-detail/C2689964.html)
- [Jushuo AFB10-S18LCA-00, LCSC C7499267](https://www.lcsc.com/product-detail/C7499267.html)

Źródła bloku firmware:

- [ZMK: konfiguracja baterii](https://zmk.dev/docs/config/battery)
- [ZMK: battery.c](https://raw.githubusercontent.com/zmkfirmware/zmk/main/app/src/battery.c)
- [Zephyr v4.1.0: npm1300_charger.c](https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/v4.1.0/drivers/sensor/nordic/npm1300_charger/npm1300_charger.c)
- [Zephyr: binding nordic,npm1300-regulator](https://docs.zephyrproject.org/latest/build/dts/api/bindings/regulator/nordic,npm1300-regulator.html)
- [Zephyr: binding nordic,npm1300](https://docs.zephyrproject.org/latest/build/dts/api/bindings/mfd/nordic,npm1300.html)
- [ZMK: konfiguracja zasilania](https://zmk.dev/docs/config/power)
