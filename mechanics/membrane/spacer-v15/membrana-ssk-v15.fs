// Membrana IBM Model M SSK, v15 (zatwierdzona przez jakuba 21.11.2026 22:47).
// Wklej WSZYSTKO PONIŻEJ do Feature Studio, POD dwiema linijkami nagłówka,
// które Onshape wstawia sam (FeatureScript ...; i import(... common.fs ...)).
// Źródło geometrii: mechanics/membrane/spacer-v15/spacer-v15-geometria.json
// (pomiar spacera na monitorze 1:1, ±0,1–0,15 mm). Ten sam rysunek co membrana-spacer-v15.dxf.
// Układ: mm, Y w górę, (0,0) = środek prostokąta 375,031 × 163,14 (jak w DXF).
// Otwory, sloty, otwory D i obrys to stałe liczby z pomiaru (bez grupowych przesunięć z v3).
// Parametry zostały dla siatki styków, globalnego przesunięcia otworów i ogonów.

// Klawisze: [nazwa, pozycja X w U od środka Esc]. Rząd 0 = F, rząd 1 = cyfry itd.
const KEY_ROWS = [
    [ ["Esc", 0], ["F1", 2], ["F2", 3], ["F3", 4], ["F4", 5], ["F5", 6.5], ["F6", 7.5], ["F7", 8.5], ["F8", 9.5], ["F9", 11], ["F10", 12], ["F11", 13], ["F12", 14], ["PrtSc", 15.5], ["ScrLk", 16.5], ["Pause", 17.5] ],
    [ ["Grave", 0], ["1", 1], ["2", 2], ["3", 3], ["4", 4], ["5", 5], ["6", 6], ["7", 7], ["8", 8], ["9", 9], ["0", 10], ["Minus", 11], ["Equal", 12], ["Bksp_L", 13], ["Bksp_R", 14], ["Ins", 15.5], ["Home", 16.5], ["PgUp", 17.5] ],
    [ ["Tab", 0.25], ["Q", 1.5], ["W", 2.5], ["E", 3.5], ["R", 4.5], ["T", 5.5], ["Y", 6.5], ["U", 7.5], ["I", 8.5], ["O", 9.5], ["P", 10.5], ["LBracket", 11.5], ["RBracket", 12.5], ["Backslash", 13.75], ["Del", 15.5], ["End", 16.5], ["PgDn", 17.5] ],
    [ ["Caps", 0.25], ["A", 1.75], ["S", 2.75], ["D", 3.75], ["F", 4.75], ["G", 5.75], ["H", 6.75], ["J", 7.75], ["K", 8.75], ["L", 9.75], ["Semicolon", 10.75], ["Quote", 11.75], ["ISO_Hash", 12.75], ["Enter", 13.875] ],
    [ ["LShift", 0.125], ["ISO_Backslash", 1.25], ["Z", 2.25], ["X", 3.25], ["C", 4.25], ["V", 5.25], ["B", 6.25], ["N", 7.25], ["M", 8.25], ["Comma", 9.25], ["Period", 10.25], ["Slash", 11.25], ["Extra_12_25", 12.25], ["RShift", 13.5], ["Up", 16.5] ],
    [ ["LCtrl", 0.25], ["LAlt", 2.75], ["Space", 7], ["RAlt", 11.25], ["RCtrl", 13.75], ["Left", 15.5], ["Down", 16.5], ["Right", 17.5] ]
];

// Otwory okrągłe H: [x, y, średnica] w mm. Kolejność H1..H20.
const HOLE_NAMES = [ "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12", "H13", "H14", "H15", "H16", "H17", "H18", "H19", "H20" ];
const HOLES = [ [-176.213, 69.759, 6.35], [-100.013, 69.759, 6.35], [-52.515, 69.759, 6.35], [32.703, 69.759, 6.35], [89.853, 69.759, 6.35], [175.39, 69.99, 6.35], [-157.163, 48.931, 6.35], [-119.063, 48.931, 6.35], [-62.167, 48.931, 6.35], [-5.017, 48.931, 6.35], [52.007, 48.931, 6.35], [89.218, 48.931, 6.35], [156.29, 48.94, 6.35], [-157.163, 28.079, 6.35], [-100.013, 28.079, 6.35], [-42.862, 28.079, 6.35], [14.034, 28.079, 6.35], [89.98, 28.079, 6.35], [156.28, 28, 6.35], [175.75, -14.15, 3.81] ];
// Otwory D (płaski dół): [x środka okręgu, y, promień, środek->płaska krawędź] w mm. D1..D7.
const D_HOLES = [ [-176.4, -76.92, 3.175, 1.981], [-133.44, -76.92, 3.175, 1.981], [-57.07, -76.92, 3.175, 1.981], [13.97, -76.92, 3.175, 1.981], [59.41, -76.92, 3.175, 1.981], [118.19, -76.99, 3.175, 1.981], [175.34, -76.92, 3.175, 1.981] ];
// Sloty: [x środka, y środka, długość całkowita, szerokość] w mm. S1..S24.
const SLOT_NAMES = [ "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17", "S18", "S19", "S20", "S21", "S22", "S23", "S24" ];
const SLOTS = [ [-173.927, 7.251, 6.096, 3.937], [-109.792, 7.251, 6.096, 3.937], [-33.592, 7.04, 6.096, 3.937], [42.609, 7.251, 6.096, 3.937], [117.792, 6.92, 6.096, 3.937], [-173.99, -13.958, 6.096, 2.667], [-104.775, -13.958, 6.096, 3.937], [-85.725, -13.958, 6.096, 3.937], [-28.575, -13.958, 6.096, 3.937], [47.625, -13.958, 6.096, 3.937], [117.792, -14.31, 6.096, 3.937], [-133.35, -34.786, 6.096, 3.937], [-57.15, -34.786, 6.096, 3.937], [-19.05, -34.786, 6.096, 3.937], [57.15, -34.786, 6.096, 3.937], [117.792, -35.16, 6.096, 3.937], [-152.241, -55.614, 6.096, 3.937], [-81.121, -55.614, 6.096, 3.937], [-23.971, -56.05, 6.096, 3.937], [18.574, -56.02, 6.096, 3.937], [85.47, -55.614, 6.096, 3.937], [117.792, -55.98, 6.096, 3.937], [156.147, -56.13, 6.096, 3.937], [156.06, -14.29, 5.969, 3.175] ];
// Obrys spacera (wielokąt, wierzchołki po kolei): [x, y] w mm.
const OUTLINE = [ [-185.316, -81.57], [187.129, -81.57], [189.929, -78.77], [189.929, 77.76], [186.119, 81.57], [148.3, 81.57], [140.3, 89.57], [70.6, 89.57], [70.6, 81.57], [44.4, 81.57], [44.4, 85.52], [34, 85.52], [34, 89.57], [-45.2, 89.57], [-45.2, 85.12], [-65.05, 85.12], [-65.05, 79.04], [-89.05, 79.04], [-89.05, 89.57], [-115.3, 89.57], [-123.3, 81.57], [-184.516, 81.57], [-187.516, 78.57], [-187.516, -79.37] ];

// Poprawki pojedynczych styków: "nazwa" : [dx, dy] w mm.
const CORRECTIONS = {
    "Enter" : [-0.635, 0]  // 20.11: zdjęcia, -0.025"
};

export const PITCH_X_BOUNDS = { (meter) : [0.001, 0.01905, 0.1], (millimeter) : 19.05, (inch) : 0.75 } as LengthBoundSpec;
export const PITCH_Y_BOUNDS = { (meter) : [0.001, 0.02084, 0.1], (millimeter) : 20.84, (inch) : 0.8205 } as LengthBoundSpec;
export const ESC_X_BOUNDS = { (meter) : [-1, -0.166688, 1], (millimeter) : -166.688, (inch) : -6.5625 } as LengthBoundSpec;
export const ESC_Y_BOUNDS = { (meter) : [-1, 0.06252, 1], (millimeter) : 62.52, (inch) : 2.4614 } as LengthBoundSpec;
export const SW_DIA_BOUNDS = { (meter) : [0.0001, 0.011113, 0.05], (millimeter) : 11.113, (inch) : 0.4375 } as LengthBoundSpec;
export const NAV_DX_BOUNDS = { (meter) : [-0.02, -0.000762, 0.02], (millimeter) : -0.762, (inch) : -0.03 } as LengthBoundSpec;
export const SHIFT_BOUNDS = { (meter) : [-0.02, 0, 0.02], (millimeter) : 0, (inch) : 0 } as LengthBoundSpec;
export const GROW_BOUNDS = { (meter) : [-0.005, 0, 0.005], (millimeter) : 0, (inch) : 0 } as LengthBoundSpec;
// Ogony: ORYGINALNE ogony zmierzone 20.11, od lewej krawędzi prostokąta (x = -187,516).
export const COL_X0_BOUNDS = { (meter) : [0, 0.142875, 0.4], (millimeter) : 142.875, (inch) : 5.625 } as LengthBoundSpec;
export const COL_W_BOUNDS = { (meter) : [0.001, 0.043307, 0.1], (millimeter) : 43.307, (inch) : 1.705 } as LengthBoundSpec;
export const ROW_X0_BOUNDS = { (meter) : [0, 0.198882, 0.4], (millimeter) : 198.882, (inch) : 7.83 } as LengthBoundSpec;
export const ROW_W_BOUNDS = { (meter) : [0.001, 0.02286, 0.1], (millimeter) : 22.86, (inch) : 0.9 } as LengthBoundSpec;
export const TAIL_LEN_BOUNDS = { (meter) : [0.001, 0.06477, 0.3], (millimeter) : 64.77, (inch) : 2.55 } as LengthBoundSpec;
export const ROW_GAP_BOUNDS = { (unitless) : [1, 2, 4] } as IntegerBoundSpec;

const LEFT_EDGE = -187.5155;  // lewa krawędź prostokąta 375,031 (odniesienie ogonów)
const TOP_EDGE = 81.57;       // górna krawędź prostokąta 163,14 (początek ogonów)

function mmv(x is number, y is number) returns Vector
{
    return vector(x * millimeter, y * millimeter);
}

annotation { "Feature Type Name" : "Membrana SSK v15" }
export const membraneSSKv15 = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Rozstaw X (1U)" }
        isLength(definition.pitchX, PITCH_X_BOUNDS);

        annotation { "Name" : "Rozstaw Y (rzad)" }
        isLength(definition.pitchY, PITCH_Y_BOUNDS);

        annotation { "Name" : "Odstep rzedu F (w rzedach)" }
        isInteger(definition.fRowGap, ROW_GAP_BOUNDS);

        annotation { "Name" : "Styki nav (od 15U): przesuniecie X" }
        isLength(definition.navDX, NAV_DX_BOUNDS);

        annotation { "Name" : "Srodek Esc X" }
        isLength(definition.escX, ESC_X_BOUNDS);

        annotation { "Name" : "Srodek Esc Y" }
        isLength(definition.escY, ESC_Y_BOUNDS);

        annotation { "Name" : "Srednica otworu styku" }
        isLength(definition.switchDia, SW_DIA_BOUNDS);

        annotation { "Name" : "Otwory i sloty: przesuniecie X (wszystkie)" }
        isLength(definition.holesDX, SHIFT_BOUNDS);

        annotation { "Name" : "Otwory i sloty: przesuniecie Y (wszystkie)" }
        isLength(definition.holesDY, SHIFT_BOUNDS);

        annotation { "Name" : "Otwory i sloty: poszerzenie (dodaje do srednicy/szerokosci)" }
        isLength(definition.holeGrow, GROW_BOUNDS);

        annotation { "Name" : "Rysuj obrys spacera", "Default" : true }
        definition.drawOutline is boolean;

        annotation { "Name" : "Rysuj ogony (oryginalne)", "Default" : true }
        definition.drawTails is boolean;

        annotation { "Name" : "Ogon COL: lewa krawedz od lewej krawedzi prostokata" }
        isLength(definition.colX0, COL_X0_BOUNDS);

        annotation { "Name" : "Ogon COL: szerokosc" }
        isLength(definition.colWidth, COL_W_BOUNDS);

        annotation { "Name" : "Ogon ROW: lewa krawedz od lewej krawedzi prostokata" }
        isLength(definition.rowX0, ROW_X0_BOUNDS);

        annotation { "Name" : "Ogon ROW: szerokosc" }
        isLength(definition.rowWidth, ROW_W_BOUNDS);

        annotation { "Name" : "Ogon: dlugosc od gornej krawedzi prostokata" }
        isLength(definition.tailLen, TAIL_LEN_BOUNDS);

        annotation { "Name" : "Rysuj styki", "Default" : true }
        definition.drawSwitches is boolean;

        annotation { "Name" : "Rysuj otwory i sloty", "Default" : true }
        definition.drawHoles is boolean;
    }
    {
        const px = definition.pitchX / millimeter;
        const py = definition.pitchY / millimeter;
        const ex = definition.escX / millimeter;
        const ey = definition.escY / millimeter;
        const gap = definition.fRowGap;
        const nav = definition.navDX / millimeter;
        const hdx = definition.holesDX / millimeter;
        const hdy = definition.holesDY / millimeter;
        const grow = definition.holeGrow / millimeter;

        var sk = newSketchOnPlane(context, id + "membrane", {
                "sketchPlane" : plane(vector(0, 0, 0) * meter, vector(0, 0, 1), vector(1, 0, 0))
            });

        if (definition.drawSwitches)
        {
            const r = definition.switchDia / millimeter / 2;
            for (var row = 0; row < size(KEY_ROWS); row += 1)
            {
                const rowIndex = row == 0 ? 0 : gap + row - 1;
                for (var k = 0; k < size(KEY_ROWS[row]); k += 1)
                {
                    const name = KEY_ROWS[row][k][0];
                    var x = ex + KEY_ROWS[row][k][1] * px;
                    var y = ey - rowIndex * py;
                    if (KEY_ROWS[row][k][1] >= 15)
                    {
                        x += nav;
                    }
                    const corr = CORRECTIONS[name];
                    if (corr != undefined)
                    {
                        x += corr[0];
                        y += corr[1];
                    }
                    skCircle(sk, "sw_" ~ name, { "center" : mmv(x, y), "radius" : r * millimeter });
                    skPoint(sk, "pt_" ~ name, { "position" : mmv(x, y) });
                }
            }
        }

        if (definition.drawHoles)
        {
            for (var i = 0; i < size(HOLES); i += 1)
            {
                skCircle(sk, "hole_" ~ HOLE_NAMES[i], { "center" : mmv(HOLES[i][0] + hdx, HOLES[i][1] + hdy), "radius" : (HOLES[i][2] + grow) / 2 * millimeter });
            }

            for (var i = 0; i < size(D_HOLES); i += 1)
            {
                const cx = D_HOLES[i][0] + hdx;
                const cy = D_HOLES[i][1] + hdy;
                const rb = D_HOLES[i][2] + grow / 2;
                const f = D_HOLES[i][3] + grow / 2;
                const hw = sqrt(rb * rb - f * f);
                skArc(sk, "darc_D" ~ (i + 1), { "start" : mmv(cx - hw, cy - f), "mid" : mmv(cx, cy + rb), "end" : mmv(cx + hw, cy - f) });
                skLineSegment(sk, "dline_D" ~ (i + 1), { "start" : mmv(cx - hw, cy - f), "end" : mmv(cx + hw, cy - f) });
            }

            for (var i = 0; i < size(SLOTS); i += 1)
            {
                const cx = SLOTS[i][0] + hdx;
                const cy = SLOTS[i][1] + hdy;
                const rs = (SLOTS[i][3] + grow) / 2;
                const hl = (SLOTS[i][2] - SLOTS[i][3]) / 2;
                const n = SLOT_NAMES[i];
                skLineSegment(sk, "stop_" ~ n, { "start" : mmv(cx - hl, cy + rs), "end" : mmv(cx + hl, cy + rs) });
                skLineSegment(sk, "sbot_" ~ n, { "start" : mmv(cx - hl, cy - rs), "end" : mmv(cx + hl, cy - rs) });
                skArc(sk, "sl_" ~ n, { "start" : mmv(cx - hl, cy + rs), "mid" : mmv(cx - hl - rs, cy), "end" : mmv(cx - hl, cy - rs) });
                skArc(sk, "sr_" ~ n, { "start" : mmv(cx + hl, cy - rs), "mid" : mmv(cx + hl + rs, cy), "end" : mmv(cx + hl, cy + rs) });
            }
        }

        if (definition.drawOutline)
        {
            const n = size(OUTLINE);
            for (var i = 0; i < n; i += 1)
            {
                const a = OUTLINE[i];
                const b = OUTLINE[(i + 1) % n];
                skLineSegment(sk, "out_" ~ i, { "start" : mmv(a[0], a[1]), "end" : mmv(b[0], b[1]) });
            }
        }

        if (definition.drawTails)
        {
            const L = definition.tailLen / millimeter;
            const tails = [ ["col", definition.colX0 / millimeter, definition.colWidth / millimeter],
                            ["row", definition.rowX0 / millimeter, definition.rowWidth / millimeter] ];
            for (var t in tails)
            {
                const x0 = LEFT_EDGE + t[1];
                skRectangle(sk, "tail_" ~ t[0], { "firstCorner" : mmv(x0, TOP_EDGE), "secondCorner" : mmv(x0 + t[2], TOP_EDGE + L) });
            }
        }

        skSolve(sk);
    });
