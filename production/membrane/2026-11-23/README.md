# Membrana FPC (folie ROW i COL), zamówienie JLC 2026-11-23

Paczki wysłane do JLCPCB 2026-11-23 (ok. 02:25), wygenerowane z projektów `hardware/membrane-row` i `hardware/membrane-col` (commit 58d6e45). Decyzja: `docs/CHANGELOG.md`, A33.

| Plik | Zawartość |
| --- | --- |
| `membrane-row-jlc.zip` | Folia ROW (górna): F.Cu, B.Cu, F/B.Mask (coverlay), F.Silkscreen, Edge.Cuts, PTH.drl (99 przelotek 0,3 mm) |
| `membrane-col-jlc.zip` | Folia COL (dolna): F.Cu, F.Mask (coverlay), Edge.Cuts |

## Parametry zamówienia

| | ROW | COL |
| --- | --- | --- |
| Warstwy | 2 | 1 |
| Poliimid | 25 µm | 25 µm |
| Grubość | 0,12 mm | 0,11 mm |
| Wykończenie | ENIG | ENIG |
| Coverlay | żółty | żółty |
| Ilość | 5 szt. | 5 szt. |

Confirm Production File = Yes. Razem z wysyłką 219,54 USD (890,38 PLN). Obie folie mają wspólny obrys (373,4 × 172,1 mm, decyzja właściciela); każda ma tylko swój ogonek FFC.

Pliki produkcyjne JLC (Y29 = COL, Y30 = ROW) porównane z wysłanymi Gerberami 2026-11-23: obrys i 52 kontury zgodne, miedź względem obrysu ±0,001 mm, JLC dodał tylko teardropy; wszystkie pady odsłonięte w coverlayu (COL: 88 styków, 18 padów FFC; ROW: 88 styków od spodu, 174 pady diod, 6 padów FFC), przelotki zakryte z obu stron. Zaakceptowane.

## Różnice względem plików

- Diody (87 × RB520S30, SOD-523) i taśmy FFC lutowane ręcznie; JLC robi tylko gołe folie (bez PCBA).
- COL J1 pin 18 = NC na folii; na controllerze J4.18 = GND (I5).
