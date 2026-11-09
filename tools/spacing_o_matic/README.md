# spacing-o-matic

Wtyczka KiCada 9/10 (PCB Editor, Action Plugin) do mierzenia i ustawiania odstępów między
równoległymi ścieżkami (bus). Działa dla busa pod dowolnym kątem. Siostra via-o-tronic.

## Instalacja

Folder `spacing_o_matic/` musi leżeć w katalogu wtyczek KiCada (albo być tam podlinkowany).
KiCad 10 z Flatpaka:

    ln -s ~/Documents/GitHub/ibm-modern-m-ssk/tools/spacing_o_matic \
          ~/.var/app/org.kicad.kicad/data/kicad/10.0/scripting/plugins/spacing_o_matic

Potem w PCB Editor: Tools → External Plugins → Refresh Plugins. Przycisk na pasku ma ikonę
trzech ścieżek ze strzałką.

## Użycie

Zaznacz proste odcinki dwóch lub więcej równoległych ścieżek (różne sieci) i uruchom wtyczkę.
Można zaznaczyć ramką całe ścieżki razem z odcinkami 45°: kierunek busa to dominujący kierunek
zaznaczenia, odcinki nierównoległe są pomijane przy pomiarze (ale przesuwają się razem z busem).

Zmiany dzieją się od razu na płytce (bez osobnego podglądu): każda zmiana wartości przesuwa
ścieżki w projekcie. **OK** zostawia wynik, **Cancel** przywraca dokładnie stan sprzed
otwarcia. Całość to jeden krok Ctrl+Z. Okno jest niemodalne (można zoomować i przesuwać widok).

Po otwarciu pole P/G ma średni odstęp zmierzony teraz, więc samo otwarcie **wyrównuje** bus
do średniej. **= now** wraca do średniej.

| Pole | Znaczenie |
|---|---|
| Pitch / Gap | co ustawiasz: P = środek–środek, G = krawędź miedzi–krawędź |
| P / G | wartość [mm] |
| W | szerokość wszystkich ścieżek busa; puste = każda zostaje swoja |
| S | przesunięcie całego busa w bok; + = w dół / w prawo (w stronę ostatniej ścieżki) |
| Keep first / centre / last | która ścieżka (albo oś busa) zostaje na miejscu; first = górna / lewa |
| P now, G now | odstępy zmierzone teraz (najmniejszy–największy) |
| Move | największe przesunięcie ścieżki dla bieżących ustawień |

**Końce ścieżek** (lista obok Keep):
- **Slide ends** (domyślnie): sąsiedni odcinek zachowuje kąt (45° zostaje 45°), wspólny punkt
  przesuwa się po nim. Gdy się nie da (pad, via, rozgałęzienie, prosta kontynuacja, sąsiad
  prawie równoległy albo za krótki) wstawiany jest skos 45°.
- **45° jogs**: końce zostają, krótki skos 45° łączy je z przesuniętą ścieżką.
- **Stretch**: końce sąsiednich odcinków jadą razem ze ścieżką (zmienia się ich kąt).

Sterowanie bez wpisywania: kółko myszy albo ↑/↓ (PgUp/PgDn = ×10) na polu zmienia wartość
o krok (0,005–0,25 mm, wybór na dole); Shift = ×10, Ctrl = ÷10. Przyciski **Spacing**:
ciaśniej / szerzej; **Bus**: cały bus w górę / w dół (S). Zmiana Pitch ↔ Gap przelicza wartość
tak, że ścieżki zostają na miejscu.

**Check** (domyślnie włączone): odstęp od padów, ścieżek i przelotek innych sieci oraz
gap między ścieżkami busa względem clearance z netclassu. Strefy (zones) i krawędź płytki nie są
sprawdzane. Przeszkody są zbierane raz na zaznaczenie, sprawdzenie trwa kilka–kilkadziesiąt ms.
Problemy: przycisk ⚠ N obok statusu otwiera log z podpowiedzią („→ raise P / G …”), po OK
dopisuje się `spacing_o_matic.log` obok pliku płytki.

More: **Snap** (oś / zachowana ścieżka na siatce, pitch zostaje dokładny), **Angle tol.**
(tolerancja równoległości), **Per pair** (różne odstępy dla kolejnych par, np. `0.4; 0.4; 0.6`).
↻ wczytuje bieżące zaznaczenie i mierzy je od nowa. Łuki (arcs) nie są przesuwane.
Po użyciu puść DRC i przelej strefy (B).

## Pliki

`spacing_o_matic.py` (KiCad), `dialog.py` (okno), `geometry.py` (czysta geometria, bez KiCada),
ikony i logo PNG (jasne/ciemne).

Testy (poza KiCadem):
- `python3 test_geometry.py`: geometria, 13 kątów, 300 losowych busów;
- `python3 test_pcbnew.py`: prawdziwy moduł pcbnew (KiCad 7+): kąty × tryby, ratsnest, dokładne
  cofanie, zgodność Check z DRC KiCada, szybkość;
- `xvfb-run -a python3 test_gui.py [katalog_zrzutów]`: okno klikane przez Run() wtyczki.
