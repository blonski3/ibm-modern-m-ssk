#!/usr/bin/env python3
"""Sprawdza, czy sciezki modeli 3D w .kicad_pcb i .kicad_mod wskazuja istniejace pliki.

Uzycie:
    python3 tools/check_3d_paths.py <katalog_projektu> [<katalog_bibliotek> ...]

${KIPRJMOD} = katalog projektu. Zmienne systemowe KiCada (${KICAD<n>_3DMODEL_DIR})
i modele osadzone (kicad-embed://) sa pomijane. Inne zmienne ${X} sa brane ze
srodowiska; jesli nie sa ustawione, sciezka jest zglaszana jako nierozwiazana.
Kod wyjscia: 0 = wszystko OK, 1 = sa problemy.
"""
import glob
import os
import re
import sys

MODEL = re.compile(r'\(model\s+"([^"]+)"')
VAR = re.compile(r'\$\{([^}]+)\}')
SYSTEM = re.compile(r'\$\{KICAD\d*_3DMODEL_DIR\}')


def resolve(path, prj):
    def sub(m):
        if m.group(1) == "KIPRJMOD":
            return prj
        return os.environ.get(m.group(1), m.group(0))
    return VAR.sub(sub, path)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    prj = os.path.abspath(sys.argv[1])
    files = glob.glob(os.path.join(prj, "*.kicad_pcb"))
    for lib in sys.argv[2:] or [prj]:
        files += glob.glob(os.path.join(lib, "**", "*.kicad_mod"), recursive=True)
    ok, skipped, bad = 0, 0, []
    for f in sorted(set(files)):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for m in sorted(set(MODEL.findall(fh.read()))):
                if m.startswith("kicad-embed://") or SYSTEM.match(m):
                    skipped += 1
                    continue
                p = resolve(m, prj)
                if "${" in p:
                    bad.append((f, m, "nierozwiazana zmienna"))
                elif os.path.exists(p):
                    ok += 1
                else:
                    bad.append((f, m, "brak pliku"))
    print(f"OK={ok} pominiete={skipped} problemy={len(bad)}")
    for f, m, why in bad:
        print(f"  [{why}] {os.path.relpath(f)} -> {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
