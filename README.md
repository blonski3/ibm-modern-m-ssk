# IBM Model M SSK: bezprzewodowy kontroler

Praca inżynierska (Politechnika Wrocławska, Inteligentna Elektronika): *Opracowanie i wykonanie układu sterującego klawiaturą mechaniczną*. Bezprzewodowa modernizacja IBM Model M SSK: nRF52840 + nPM1300, własna membrana FPC z diodą na klawisz, firmware ZMK.

## Struktura repozytorium

```
hardware/controller/   projekt KiCad 10: motherboard + daughterboard (jedna PCB, DB wyłamywany)
hardware/membrane/     projekt KiCad 10: membrana FPC, matryca 6 × 17
hardware/lib/          wspólna biblioteka: symbole, footprinty, modele 3D
docs/                  CHANGELOG.md, HARDWARE_DECISIONS.md, datasheets/, diagrams/
mechanics/             pomiary i eksporty z Onshape
reference/             projekty referencyjne (Nordic, FSSK v1.00)
tools/                 skrypty pomocnicze (np. check_3d_paths.py)
```

Decyzje projektowe i ich uzasadnienia: `docs/HARDWARE_DECISIONS.md`; historia zmian: `docs/CHANGELOG.md`.

## Źródła

[Bolt Mod, A Comprehensive Tutorial: IBM Model M SSK 1991](https://imgur.com/gallery/bolt-mod-comprehensive-tutorial-ibm-model-m-ssk-1991-arUYken)

[FSSK v1.00 - Installation & Users Manual](https://deskthority.net/viewtopic.php?t=13551)

[Request for Permission to Integrate Zephyr PF1550 PMIC Drivers into ZMK #2958](https://github.com/zmkfirmware/zmk/issues/2958)

[nRF52840 Product Specification v1.5](https://docs.nordicsemi.com/viewer/book-attachment/de~7rocmcN70bRHnA4~zJA/H1GC97m6GZQEaMxKCN6OOg-de~7rocmcN70bRHnA4~zJA)

[nPM1300 Product Specification v1.3](https://docs.nordicsemi.com/viewer/book-attachment/ZO1FVHHS04YNNMSlbsZ0Kg/KbFbu1gXgIMOyTgBK7q46A-ZO1FVHHS04YNNMSlbsZ0Kg)

[Keyboard Layout Editor NG - IBM Model M](https://editor.keyboard-tools.xyz/#share=NobwRAhgrgLgFgewE5gFxgEYBsEDswA0YuEAtgKZpgCSAQgLIAEAyswNKP0IAm5WnhMAGcADhADGAS1wBzAPoBPNACYADADoAHABYAvgVCQ0q-WELgAHmgCMpwfaLmwV1BoCsdx17MFLx9R7eDj5+rgGePmYAugbgSqi2QUmRwanJDqHW4ekxhgDuNtkp6SXFZU4FCUVOLu4R9rnglVkA7IHlpWkdTSrqyu1gjWCVyn0DnRPFPVVtnqGjA0PN1b7ONkTL49Mtc8OFW2sJG-u7tSspQy7Wo21E8QC0AMy7y-12S4VvQUMPysdVi1ih2sekclxs2juaHuoOiUSAA)

[WR-PHD Pin Header drawing](https://www.we-online.com/components/products/datasheet/61300811021.pdf)
