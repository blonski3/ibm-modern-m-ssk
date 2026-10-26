#!/usr/bin/env bash
# ERC + netlista + PDF schematu oraz DRC plytki controllera do .baseline/ (do porownan, poza gitem).
# Uzycie: tools/kicad-check.sh  (z dowolnego katalogu w repo)
set -euo pipefail
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SCH="$ROOT/hardware/controller/controller.kicad_sch"
PCB="$ROOT/hardware/controller/controller.kicad_pcb"
OUT="$ROOT/.baseline"
mkdir -p "$OUT"
kicad-cli sch erc --format json --severity-all --units mm -o "$OUT/erc.json" "$SCH" || true
kicad-cli sch erc --severity-all --units mm -o "$OUT/erc.rpt" "$SCH" || true
kicad-cli sch export netlist --format kicadsexpr -o "$OUT/controller.net" "$SCH"
kicad-cli sch export pdf -o "$OUT/controller.pdf" "$SCH"
# DRC z porownaniem do schematu (brakujace/nadmiarowe footprinty, rozne sieci)
kicad-cli pcb drc --format json --severity-all --schematic-parity --units mm -o "$OUT/drc.json" "$PCB" || true
kicad-cli pcb drc --severity-all --schematic-parity --units mm -o "$OUT/drc.rpt" "$PCB" || true
echo "Gotowe: $OUT/{erc.json,erc.rpt,controller.net,controller.pdf,drc.json,drc.rpt}"
