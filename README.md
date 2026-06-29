# WF Menu / HUD Designer — v2

A browser-based, offline, single-file **WYSIWYG multi-display editor** for every Arma 2 WASP Warfare dialog and HUD overlay — part of the [Miksuu's Warfare tools](https://miksuu.com/tools) suite (sibling to [WDDM](https://github.com/rayswaynl/WDDM), [Loadout Lab](https://github.com/rayswaynl/loadout-lab), [Sector & Town Planner](https://github.com/rayswaynl/sector-planner), [Strategy & Economy](https://github.com/rayswaynl/strategy-economy)).

## What it does

Load **any of the 24 WASP displays** and see it rendered exactly as it appears in-game — dark panels, WASP-blue accents, correct fonts and control sizing — then edit, rearrange, and export faithful `.hpp` ready to drop into the mission.

### Key capabilities (v2)

| Feature | Detail |
|---|---|
| **24 displays** | All dialogs from `Dialogs.hpp` (WF_Menu, BuyGear, BuyUnits, Command, Tactical, Upgrade, Team, Service, UnitCamera, Parameters, Economy, EASA, Help, RespawnMenu, TransferMenu, VoteMenus, ConstructionInterface…) + 5 HUD RscTitles (OptionsAvailable, RscOverlay, CaptureBar, EndOfGameStats, WFBE_ConstructionInterface) |
| **WYSIWYG rendering** | Each control renders with its real base-class styling: olive/blue/red buttons, black listboxes, translucent panels, WASP-blue tile borders, correct font sizing (sizeEx × screenH) |
| **SafeZone HUD eval** | HUD overlays (RscTitles) evaluate SafeZone string expressions so money/supply bars, icon strips, and capture progress land at correct screen positions |
| **Pro editing** | Marquee + shift/ctrl multi-select; align (L/R/T/B/center-H/V); distribute; duplicate; copy/paste; undo/redo history; arrow nudge (×10 with Shift); snap-to-grid + snap-to-control edges with guide lines; z-order raise/lower/front/back; group/ungroup; per-layer lock + hide; add control from palette |
| **Full property inspector** | Edits every prop for selected control(s): idc, name, baseClass (inherits from all parsed classes), x/y/w/h (float or SafeZone string), text, color pickers with WFBE_* macro assignment, font, sizeEx, style flags, shadow, action/event strings. Overridden props are highlighted; per-prop "reset to inherited" button. Multi-select edits common props. |
| **Faithful round-trip** | Export the whole display as valid `.hpp`: each control `: BaseClass` emitting only the delta (overridden props), keeping `WFBE_*` macro names, preserving sub-class blocks verbatim. Import: paste any display `.hpp` block → parse → load editable. Copy or download. |

## Source of truth

Parsed from the live mission at `a2waspwarfare/Missions/[55-2hc]warfarev2_073v48co.chernarus/Rsc/`:

| File | Role |
|---|---|
| `Styles.hpp` | `WFBE_*` color/style macro definitions (resolved to RGBA for rendering, kept as names in export) |
| `Ressources.hpp` | All base `Rsc*` class definitions (type, colors, font, sizeEx, shadow, sub-class blocks) |
| `Dialogs.hpp` | 18+ full-screen dialog classes with idd, controlsBackground, controls |
| `Titles.hpp` | HUD overlays using SafeZone coordinate expressions |

## Dev setup

```bash
# Regenerate ui.json from live source files (run after editing any .hpp in a2waspwarfare)
python tools/extract_dialogs.py          # writes assets/data/ui.json
python tools/extract_dialogs.py --test   # runs 26 unit tests (macro/baseClass/dialog/SafeZone parsing)

# Serve locally
python -m http.server 7890
# Open http://localhost:7890

# Run Playwright smoke tests (requires playwright npm package)
npm install
node test-smoke-v2.js     # full multi-display smoke (8 sections, 0 console errors gate)
node test-inspector.js    # inspector color/baseClass/multi-select/reset
node test-roundtrip.js    # export→import→re-export delta accuracy
```

## Coordinate systems

**Dialogs** (`unit_square` position system): plain 0..1 floats — `x=0,y=0` = top-left; `x=1,y=1` = bottom-right. Rendered as `v * screenW/H` pixels on the 16:9 stage.

**HUD overlays** (`safezone` position system): SafeZone string expressions, e.g. `0.2075 * safezoneH + safezoneY`. Evaluated with `safezoneX=0.07, safezoneY=0.07, safezoneW=0.86, safezoneH=0.86` (16:9 approximation).

## Export format

```cpp
class WF_Menu {
    idd = 11000;
    movingEnable = 1;
    class controlsBackground {
        class Background_M : RscText {
            x = 0.17467; y = 0.186955; w = 0.65066; h = 0.63192;
            colorBackground[] = WFBE_Background_Color;  // macro name preserved
        };
        // ...
    };
    class controls {
        class Button_A : RscShortcutButtonMain {
            idc = 11001;
            x = 0.17598; y = 0.250358; w = 0.313727; h = 0.104575;
            text = $STR_WF_MAIN_Purchase_Units;
            action = "MenuAction = 1";
        };
        // ... only overridden props emitted (delta vs baseClass)
    };
};
```

## License

Unofficial, non-commercial reference tool for WASP Warfare mission development. Arma 2 / WASP config © **Bohemia Interactive** / WFBE authors.
