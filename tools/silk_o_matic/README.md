# silk-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin): ustawia opisy (Reference albo Value)
zaznaczonych footprintów **nad / pod / obok / na środku** części, w zadanym odstępie od
courtyardu, jednym rozmiarem i czytelnym kątem. Tryb **Auto** sam szuka pierwszej strony,
gdzie tekst nie wchodzi na pady, inny silkscreen ani krawędź płytki. Odpowiedź na jedno
z najczęstszych narzekań z forum KiCada: po Update PCB opisy leżą na padach i na sobie,
a ręczne przestawianie setek R1…C80 (i ustawianie im tego samego rozmiaru) zajmuje godziny.

## Instalacja

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/silk_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/silk_o_matic

Tools → External Plugins → Refresh Plugins.

## Użycie

Zaznacz footprinty (np. wszystkie: Ctrl+A, albo tylko jedną grupę) i uruchom wtyczkę.
Zmiany dzieją się od razu na płytce, **OK** zostawia, **Cancel** przywraca wszystko
dokładnie (pozycję, kąt, rozmiar, grubość); jeden krok Ctrl+Z.

| Pole | Znaczenie |
|---|---|
| ▭ przyciski | góra, dół, lewo, prawo, środek (dla warstwy Fab), Auto |
| Reference / Value | który tekst przestawiać |
| G | odstęp od courtyardu do tekstu (bez courtyardu: od padów i grafiki); może być ujemny |
| H | wysokość = szerokość znaku, puste = każdy zostaje w swoim rozmiarze |
| T | grubość linii, puste = 15 % H (albo bez zmian, gdy H puste) |
| ∠ | Keep: jak jest; 0° / 90°: wszystkie tak samo; Along part: 0° dla szerokich, 90° dla wysokich |
| Now | rozmiar / grubość tekstów przed zmianą |
| Done | ile ustawionych, ile „crowded” (nigdzie nie było wolnego miejsca) |

Odstęp liczy się do **narysowanych kresek** tekstu (KiCad `GetEffectiveTextShape`), nie do
większej ramki z interlinią, więc G = 0,2 mm to naprawdę 0,2 mm od courtyardu. Kółko myszy /
↑↓ na polu zmienia o krok, Shift ×10, Ctrl ÷10; przyciski Gap: bliżej / dalej.

**Auto**: kolejno góra, dół, prawo, lewo; jeśli żadna nie jest wolna, to samo z odstępem
+0,5 i +1 mm, a na końcu miejsce, które nachodzi najmniej (ostrzeżenie „crowded”). Teksty
ustawione wcześniej (kolejność R1, R2 … R10) też są przeszkodą, więc sąsiednie opisy nie
wchodzą na siebie. Teksty na spodzie omijają tylko to, co jest na spodzie.

More: **Pad gap** (odstęp od padów, czyli otworów w masce), **Silk gap** (od innego
silkscreenu). Od krawędzi płytki zawsze 0,2 mm.

Ostrzeżenia (⚠, po OK w `silk_o_matic.log`): tekst na padzie, na innym silkscreenie, za
krawędzią płytki (dla wybranej strony), crowded (Auto), ukryty tekst ustawiony mimo to.

## Pliki i testy

`silk_o_matic.py` (KiCad), `dialog.py`, `geometry.py` (czysta geometria), wspólne `w95.py`
(okno), `kc.py` (KiCad), `geo.py` (geometria), ikony i logo.
`python3 test_silk.py` (prawdziwy pcbnew: każda strona przy kątach części 0/90/30/180 i na
spodzie, rozmiar i grubość, tryby kąta, Auto omija pady / silk / krawędź, Value, Fab,
gęsta kolumna bez nachodzenia, dokładne cofanie, losowe płytki sprawdzone DRC KiCada
(silk_over_copper, silk_overlap, silk_edge_clearance), szybkość: 300 części ≈ 50 ms),
`xvfb-run -a python3 test_silk.py gui [zrzuty]` (okno klikane przez Run()).
