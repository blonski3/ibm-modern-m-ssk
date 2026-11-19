# Praca inżynierska (LaTeX)

Struktura:

- `main.tex`: preambuła i kolejność rozdziałów
- `title.tex`: strona tytułowa (TYMCZASOWA, do podmiany na szablon WEFiM)
- `chapters/NN-nazwa.tex`: rozdziały; w komentarzach `% -` jest plan treści każdej sekcji
- `figures/`: rysunki (PDF/PNG), `bib/bibliografia.bib`: bibliografia (biblatex + biber, styl IEEE)
- wynik: `build/main.pdf` (katalog `build/` jest ignorowany przez git)

## Kompilacja

```
cd thesis
latexmk
```

## Środowisko (Fedora)

1. TeX Live: `sudo dnf install texlive-scheme-full` (najprościej, kilka GB) albo `texlive-scheme-medium` plus brakujące pakiety (`texlive-biblatex-ieee`, `texlive-todonotes`, `biber`, `latexmk`, `texlive-polski`) doinstalowywane, gdy kompilacja zgłosi brak.
2. VS Code + rozszerzenie **LaTeX Workshop** (James-Yu.latex-workshop).
3. Otwórz folder repo w VS Code, plik `thesis/main.tex`, zapis = kompilacja, podgląd PDF: Ctrl+Alt+V (zakładka obok). Ctrl+klik w PDF przenosi do źródła.

Jedno ustawienie do zrobienia ręcznie (żeby PDF i pliki pośrednie trafiały do `thesis/build/`, a nie obok źródeł): w VS Code Ctrl+, → wyszukaj `latex-workshop.latex.outDir` → wpisz `%DIR%/build`. Reszta działa domyślnie (przepis latexmk czyta `latexmkrc`, kompilacja przy zapisie).

## Notatki robocze

`\todo{...}` wstawia żółtą notkę, lista wszystkich jest na początku PDF. Przed złożeniem: w `main.tex` `\usepackage[disable]{todonotes}`.
