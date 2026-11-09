# stitch-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): via zszywające na trzy sposoby. Odpowiedź na
częste pytania z forum KiCada („jak zrobić via fence wzdłuż ścieżki RF”, „stitching vias
dookoła płytki”, „wypełnić strefę GND via”): KiCad nie ma tego wbudowanego, a stare wtyczki
(Via Fence Generator, ViaStitching) przestają działać z nowymi wersjami, sypią via na pady
i w clearance, i nie da się ich łatwo przerobić.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/stitch_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/stitch_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

Tryb wybiera się sam po zaznaczeniu:

* **Fence** (zaznaczone ścieżki, także łuki i załamania): rzędy via po obu stronach albo
  po jednej, w odległości O od osi ścieżki, co P. Na zewnątrz zakrętów via idą po łuku,
  w środku zakrętu nie wchodzą bliżej niż O.
* **Fill** (zaznaczona strefa): siatka via co P (kwadratowa albo heksagonalna), M od krawędzi
  strefy; siatka na pełnych wielokrotnościach P, więc ponowne uruchomienie daje te same miejsca.
* **Ring** (nic nie zaznaczone albo jedna strefa): via wzdłuż krawędzi płytki (Edge.Cuts,
  także zaokrąglone rogi) albo strefy, O od krawędzi, rozłożone równo dookoła.

Zmiany dzieją się od razu na płytce, **OK** zostawia, **Cancel** usuwa; jeden krok Ctrl+Z.
Sieć wybierasz z listy (domyślnie GND). D i d puste = z netclassa sieci.

Via, które złamałyby regułę, są pomijane (lista pod obrazkiem, np. „left out: 5 too close to
other copper, 2 on a pad”): clearance do innych sieci (netclass), via na padzie, hole to hole
(także z istniejącymi via), krawędź płytki, odstęp między nowymi via. Wynik bez błędów DRC
KiCada w testach.

Ponowna zmiana płotu: zaznacz ścieżkę razem ze starymi via (ramką) i uruchom znowu: zaznaczone
„wolne” via tej sieci (bez ścieżek) zostaną zastąpione nowymi.

More: **Rows** i **Row gap** (kilka rzędów), **Ends** (bez via przy końcach), **Fit** (równo od
końca do końca), **Stagger** (druga strona / rząd przesunięta o P/2), **Hex grid** (Fill),
**Inside zone** (tylko tam, gdzie jest strefa tej sieci, bez wiszących via).

Kółko myszy / ↑↓ na polu zmienia o krok, Shift ×10, Ctrl ÷10; przyciski: gęściej / rzadziej,
bliżej / dalej.

## Pliki i testy

`stitch_o_matic.py` (KiCad), `dialog.py`, `geometry.py` (czysta geometria), wspólne `w95.py`,
`kc.py`, `geo.py`, ikony i logo. `python3 test_stitch.py` (prawdziwy pcbnew: płot prosty, z
zakrętami i łukiem, pady i istniejące via, zamiana starego płotu, siatka w strefie, pierścień po
prostokącie i zaokrąglonym obrysie, Inside zone, 25 losowych płytek sprawdzonych DRC KiCada,
szybkość: 3000 via w ~0,1 s), `xvfb-run -a python3 test_stitch.py gui [zrzuty]`.
