# Controller rev A, zamówienie JLC 2026-11-16

Paczka wysłana do JLCPCB 2026-11-16 (ok. 01:25), wygenerowana z commita `e38d708` przez Fabrication Toolkit. Decyzja: `docs/CHANGELOG.md`, A31.

| Plik | Zawartość |
| --- | --- |
| `controller.zip` | Gerbery i wiercenia (4 warstwy, MB + DB z mouse bites) |
| `bom.csv` | BOM dla montażu JLC |
| `positions.csv` | CPL (wszystkie elementy na TOP) |
| `designators.csv`, `netlist.ipc` | Lista oznaczeń i netlista IPC-D-356 do testu elektrycznego |

## Parametry zamówienia

- PCB: 4 warstwy, 1,2 mm, ENIG, stackup JLC04121H-3313, Impedance Control = Yes (A24, A30).
- Przelotki: min. 0,15 mm, POFV (Epoxy Filled & Capped) z uwagą z A25 w polu remarks.
- Panel: „2 designs per panel by customer” (MB i DB w jednym obrysie, mouse bites), X-out Not Accept.
- PCBA: 5 szt., Confirm Parts Placement = Yes.
- Koszt: 461 USD z VAT, DDP DHL; wysyłka najwcześniej 2026-11-23.

## Różnice względem plików

- **U2 (nPM1300-QEAA, C7466043) jest w `bom.csv`, ale JLC go nie montuje** (brak na stanie w dniu zamówienia). Lutowany ręcznie, 10 szt. z TME.
- Ręcznie lutowane (poza BOM i CPL już w plikach): J3, J5, J8, J9. R13 i C9 są DNP.

## Do uzupełnienia

- Numer zamówienia JLC: …
- Akceptacja zdjęcia rozmieszczenia (pin 1 U1): …
