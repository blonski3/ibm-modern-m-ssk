#!/usr/bin/env bash
# ERC + netlista + PDF schematu controllera do .baseline/ (do porownan, poza gitem).
# Uzycie: tools/kicad-check.sh  (z dowolnego katalogu w repo)
set -euo pipefail
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SCH="$ROOT/hardware/controller/controller.kicad_sch"
OUT="$ROOT/.baseline"
mkdir -p "$OUT"
kicad-cli sch erc --format json --severity-all --units mm -o "$OUT/erc.json" "$SCH" || true
kicad-cli sch erc --severity-all --units mm -o "$OUT/erc.rpt" "$SCH" || true
kicad-cli sch export netlist --format kicadsexpr -o "$OUT/controller.net" "$SCH"
kicad-cli sch export pdf -o "$OUT/controller.pdf" "$SCH"
echo "Gotowe: $OUT/{erc.json,erc.rpt,controller.net,controller.pdf}"
