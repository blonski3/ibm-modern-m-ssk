# net-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): szybka zmiana sieci zaznaczonych ścieżek
i przelotek (opcjonalnie padów i stref). Zamiast okna Properties i rozwijanej listy sieci:
wpisujesz kilka liter, lista się zawęża, Enter. Płytka pokazuje wybraną sieć od razu.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/net_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/net_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

1. Zaznacz ścieżki, przelotki albo jedno i drugie (same przelotki też można) i uruchom
   wtyczkę (przycisk na pasku albo Tools → External Plugins).
2. Pisz nazwę sieci: `gnd`, `d+`, `3v3`, `u1 pa1` (kilka słów = wszystkie muszą pasować),
   litery po kolei też działają (`vbs` → VBUS). ↑↓ / PgUp / PgDn wybiera z listy.
3. **Enter** (albo dwuklik) = OK, **Esc** = Cancel (płytka wraca dokładnie do stanu sprzed).
   Cała sesja to jeden krok Ctrl+Z.

Na górze listy są sieci, których dotyka zaznaczona miedź (kolumna „touches”, np. ścieżka
bez sieci zaczynająca się na padzie GND), potem ostatnio używane („recent”) i obecne
(„now”). Jeśli zaznaczenie dotyka innej sieci, ta sieć jest od razu podświetlona, więc
często wystarczy uruchomić wtyczkę i nacisnąć Enter.

| Element | Znaczenie |
|---|---|
| Tracks N / Vias N | które zaznaczone elementy zmienić (przy mieszanym zaznaczeniu można wyłączyć ścieżki i zmienić tylko przelotki) |
| + connected | także ścieżki i przelotki połączone z zaznaczonymi (ta sama stara sieć, zatrzymuje się na padach, jak U w KiCadzie) |
| ⇄ Swap | gdy w zaznaczeniu są dokładnie dwie sieci: A → B i B → A |
| `<no net>` | bez sieci (wpisz `-` albo `none`) |
| + new net „…” | nazwa, której nie ma na płytce, tworzy nową sieć (nie ma jej w schemacie, Update PCB from Schematic ją usunie) |
| ↻ | zostawia tę zmianę i bierze to, co jest zaznaczone teraz, na następną (wiele zmian w jednym oknie) |
| To / Changed / Done | podświetlona sieć (netclass, liczba padów) / co zmieniła / wszystkie zmiany w oknie |
| ⚠ N | ostrzeżenia, np. zmieniona miedź dotyka padu albo ścieżki innej sieci (zwarcie) |

More: **Pads** (pady zaznaczone osobno, Alt+klik; ich sieć i tak pochodzi ze schematu),
**Zones** (zaznaczone strefy miedzi; wypełnienie odśwież klawiszem B), **Live** (wyłączone:
płytka zmienia się dopiero po Enter/OK, przydatne na bardzo dużej płytce).

Szybkość: lista jest wirtualna i filtruje się od razu (400 sieci < 1 ms); geometria płytki
jest czytana raz przy otwarciu (≈ 60 ms dla 960 padów i 3400 ścieżek/przelotek), zmiana
sieci to ≈ 2 ms. Widok KiCada przebudowuje się tylko wtedy, gdy płytka naprawdę się zmieniła,
i nie częściej niż trwa jedna przebudowa (KiCad 9/10 przy każdym odświeżeniu z Pythona
przebudowuje cały widok i połączenia).

## Pliki i testy

`net_o_matic.py` (KiCad), `dialog.py` (okno), `nets.py` (wyszukiwanie, styki miedzi,
„connected”, bez pcbnew), wspólne `w95.py`, `kc.py`, `geo.py`, ikony i logo.
`python3 test_net.py` (prawdziwy pcbnew: ranking wyszukiwania, ścieżki + przelotki, same
przelotki, + connected przez przelotkę i przelotkę w środku ścieżki, podpowiedzi „touches”
i ostrzeżenia o zwarciu, swap, nowa sieć i bez sieci, pady i strefy, kilka zmian i Cancel,
szybkość), `xvfb-run -a python3 test_net.py gui [zrzuty]` (okno klikane przez Run()).
