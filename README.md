# WF Menu / HUD Designer

A browser-based, offline, single-file **WF Menu & HUD layout designer** for Arma 2 **WASP "Warfare"** — part of the [Miksuu's Warfare tools](https://miksuu.com/tools) suite (sibling to [WDDM](https://github.com/rayswaynl/WDDM), [Loadout Lab](https://github.com/rayswaynl/loadout-lab), [Garrison Editor](https://github.com/rayswaynl/garrison-editor), [Sector & Town Planner](https://github.com/rayswaynl/sector-planner), [Strategy & Economy](https://github.com/rayswaynl/strategy-economy)).

## What it does

Visually design the **WASP WF Menu dialogs and HUD overlays** — the 18 dialogs and 5 HUD titles defined in `Rsc/Dialogs.hpp` and `Rsc/Titles.hpp`:

- **Dialog canvas** — drag-and-drop controls on a scaled 4:3/16:9 preview pane. Positions are shown as 0..1 unit-square fractions (the coordinate system all WASP dialogs use).
- **HUD canvas** — SafeZone-aware overlay editor for the `RscTitles` entries (`RscOverlay`, `CaptureBar`, `OptionsAvailable`, etc.), rendered using runtime SafeZone approximations.
- **Control palette** — all WASP base classes (`RscShortcutButtonMain`, `RscButton_Main`, `RscText`, `RscText_Title`, `RscClickableText`, `RscListnBox`, `RscPicture`, …) with their real default dimensions and colors.
- **Inspector** — click any control to edit idc, x/y/w/h, text, action, and color properties.
- **Export** — regenerates `.hpp` class blocks ready to paste into `Dialogs.hpp` or `Titles.hpp`.

## Source of truth

Parsed from the live mission at `a2waspwarfare/Missions/[55-2hc]warfarev2_073v48co.chernarus/Rsc/`:

| File | Role |
|---|---|
| `Styles.hpp` | `WFBE_*` color macro definitions |
| `Ressources.hpp` | All base Rsc class definitions + CT_*/ST_* constants |
| `Dialogs.hpp` | 18 dialog classes |
| `Titles.hpp` | HUD overlays (SafeZone expressions) |

Run `tools/extract_dialogs.py` to regenerate `assets/data/dialogs.json` from the live source files.

## Target dialog — WF_Menu (idd 11000)

The first dialog targeted by this tool is `WF_Menu` — the main WF menu:

- 4 background panels (`controlsBackground`)
- 10 large `RscShortcutButtonMain` buttons in a 2-column grid
- 1 title label (`RscText_Title`)
- 4 small icon buttons (`RscClickableText`)
- 1 exit button (`RscButton_Exit`)

All positions use 0..1 unit-square fractions. The dialog is draggable in-game (`movingEnable = 1`), centered at roughly `x=0.17..0.82`, `y=0.19..0.82`.

## Coordinate systems

**Dialogs** use 0..1 unit-square fractions (x=0,y=0 = top-left; x=1,y=1 = bottom-right).

**HUD overlays** (Titles.hpp) use SafeZone expressions:
```
x = <fraction> * safezoneW + safezoneX
y = <fraction> * safezoneH + safezoneY
```
This tool renders HUD controls using `safezoneW=0.86, safezoneH=0.86, safezoneX=0.07, safezoneY=0.07` (16:9 approximation).

## License

Unofficial, non-commercial reference tool for mission development. Arma 2 / WASP config © **Bohemia Interactive** / WFBE authors.
