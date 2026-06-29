"""
extract_dialogs.py
==================
Parse the WASP Arma 2 mission RSC files and emit assets/data/dialogs.json.

Target dialog: WF_Menu (idd 11000) — the main WF menu.
Also emits: base_classes (palette), macros (WFBE_* color/numeric defs),
            coord_convention (documentation), and all dialog metadata stubs.

Usage:
    python tools/extract_dialogs.py [--src <mission_rsc_dir>] [--out <output_json>]

Defaults:
    --src  C:\\Users\\Steff\\a2waspwarfare\\Missions\\[55-2hc]warfarev2_073v48co.chernarus\\Rsc
    --out  assets/data/dialogs.json   (relative to repo root = parent of tools/)
"""

import re
import json
import os
import sys
import argparse
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = (
    Path(r"C:\Users\Steff\a2waspwarfare\Missions")
    / "[55-2hc]warfarev2_073v48co.chernarus"
    / "Rsc"
)
DEFAULT_OUT = REPO_ROOT / "assets" / "data" / "dialogs.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ARRAY_RE = re.compile(r"\{([^}]*)\}")
_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _parse_scalar(raw: str):
    """Try to coerce a raw string value to float/int/bool; fall back to str."""
    raw = raw.strip().strip('"')
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        v = float(raw)
        return int(v) if v == int(v) else v
    except (ValueError, OverflowError):
        return raw


def _parse_array(raw: str):
    """Parse `{0.25, 0.71, 1, 1}` → [0.25, 0.71, 1.0, 1.0]."""
    m = _ARRAY_RE.search(raw)
    if not m:
        return raw.strip()
    nums = _NUMBER_RE.findall(m.group(1))
    result = []
    for n in nums:
        try:
            v = float(n)
            result.append(int(v) if v == int(v) else v)
        except ValueError:
            result.append(n)
    return result


# ---------------------------------------------------------------------------
# Macro expansion  (Styles.hpp + numeric defines in Ressources.hpp)
# ---------------------------------------------------------------------------
_DEFINE_RE = re.compile(
    r"#define\s+(\w+)\s+(.*?)(?=\r?\n)",
    re.MULTILINE,
)


def load_macros(styles_text: str, ressources_text: str) -> dict:
    """Return dict of macro-name -> resolved value (color list or scalar)."""
    raw: dict[str, str] = {}
    for text in (styles_text, ressources_text):
        for name, value in _DEFINE_RE.findall(text):
            raw[name] = value.strip()

    resolved: dict[str, object] = {}
    for name, value in raw.items():
        if "{" in value:
            resolved[name] = _parse_array(value)
        else:
            try:
                v = float(value)
                resolved[name] = int(v) if v == int(v) else v
            except ValueError:
                resolved[name] = value
    return resolved


# ---------------------------------------------------------------------------
# Base class extraction (Ressources.hpp)
# ---------------------------------------------------------------------------
_BASE_CLASS_NAMES = [
    "RscText", "RscText_Title", "RscText_SubTitle", "RscText_Small",
    "RscButton", "RscButton_Main", "RscButton_Back", "RscButton_Exit",
    "RscShortcutButton", "RscShortcutButtonMain", "RscIGUIShortcutButton",
    "RscListBox", "RscListnBox", "RscListBoxA",
    "RscPicture", "RscPictureKeepAspect",
    "RscClickableText",
    "RscStructuredText",
    "RscEdit", "RscCombo", "RscFrame", "IGUIBack",
    "RscControlsGroup", "RscXSliderH", "RscMapControl",
]

_CT_MAP = {
    0: "CT_STATIC", 1: "CT_BUTTON", 2: "CT_EDIT", 4: "CT_COMBO",
    5: "CT_LISTBOX", 11: "CT_CLICKABLETEXT", 13: "CT_STRUCTUREDTEXT",
    15: "CT_CONTROLS_GROUP", 16: "RscShortcutButton", 43: "RscXSliderH",
    101: "RscMapControl", 102: "CT_LISTNBOX",
}


def _extract_class_body(text: str, class_name: str) -> str | None:
    """
    Find `class <class_name>` (optionally `: Parent`) and return its brace body.
    Handles nested braces.
    """
    # Match the class opener
    pat = re.compile(
        r"class\s+" + re.escape(class_name) + r"\s*(?::\s*\w+\s*)?\{",
        re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return None
    start = m.end() - 1  # position of opening {
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


_PROP_LINE_RE = re.compile(
    r"^\s*(\w+)\s*(?:\[\])?\s*=\s*(.+?)\s*;",
    re.MULTILINE,
)


def parse_class_props(body: str, macros: dict) -> dict:
    """Parse property lines from a class body (one level, no nested classes)."""
    # Strip nested class blocks first so we don't match their properties
    clean = re.sub(r"class\s+\w+\s*\{[^{}]*\}", "", body)
    props: dict[str, object] = {}
    for name, raw in _PROP_LINE_RE.findall(clean):
        raw = raw.strip()
        if raw.startswith("{"):
            value: object = _parse_array(raw)
        elif raw in macros:
            value = macros[raw]
        else:
            value = _parse_scalar(raw)
        props[name] = value
    return props


def extract_base_classes(ressources_text: str, macros: dict) -> dict:
    """Return dict of class_name -> {type_num, type_name, key props}."""
    result = {}
    for name in _BASE_CLASS_NAMES:
        body = _extract_class_body(ressources_text, name)
        if body is None:
            continue
        props = parse_class_props(body, macros)
        # Resolve type name
        type_num = props.get("type")
        if isinstance(type_num, (int, float)):
            type_num = int(type_num)
            props["type_name"] = _CT_MAP.get(type_num, f"type_{type_num}")
        result[name] = props
    return result


# ---------------------------------------------------------------------------
# Dialog extraction (Dialogs.hpp) — full WF_Menu parse
# ---------------------------------------------------------------------------

# Properties we care about for each control
_CONTROL_PROPS = {
    "idc", "type", "x", "y", "w", "h",
    "text", "action", "tooltip", "moving",
    "colorBackground", "colorText", "colorBackground",
    "sizeEx", "shadow", "style", "onButtonClick",
    "onLBDblClick", "onLBSelChanged", "columns", "rowHeight",
}

_ALL_DIALOG_RE = re.compile(
    r"//.*?\n\s*class\s+(\w+)\s*\{[^c]",
    re.MULTILINE,
)

_IDD_RE = re.compile(r"\bidd\s*=\s*([\d]+)")
_MOVING_RE = re.compile(r"\bmovingEnable\s*=\s*(\d)")


def extract_wf_menu(dialogs_text: str, macros: dict) -> dict:
    """
    Parse WF_Menu (idd 11000) in full, extracting controlsBackground and
    controls sections as structured lists.
    """
    body = _extract_class_body(dialogs_text, "WF_Menu")
    if body is None:
        raise ValueError("WF_Menu class not found in Dialogs.hpp")

    # Top-level dialog properties
    idd_m = _IDD_RE.search(body)
    moving_m = _MOVING_RE.search(body)

    dialog_info: dict = {
        "class": "WF_Menu",
        "idd": int(idd_m.group(1)) if idd_m else None,
        "movingEnable": bool(int(moving_m.group(1))) if moving_m else False,
        "coord_system": "unit_square_0_1",
        "controlsBackground": [],
        "controls": [],
    }

    # Find controlsBackground and controls sub-bodies
    for section_name in ("controlsBackground", "controls"):
        section_body = _extract_class_body(body, section_name)
        if section_body is None:
            continue
        controls_list = _parse_section_controls(section_body, macros)
        dialog_info[section_name] = controls_list

    return dialog_info


def _parse_section_controls(section_body: str, macros: dict) -> list:
    """
    Extract individual `class ControlName : ParentClass { ... }` entries
    from a controlsBackground or controls section body.
    """
    # Find all inner class definitions (one level deep)
    inner_class_re = re.compile(
        r"class\s+(\w+)\s*(?::\s*(\w+)\s*)?\{",
        re.MULTILINE,
    )
    controls = []
    for m in inner_class_re.finditer(section_body):
        ctrl_name = m.group(1)
        parent = m.group(2)
        start = m.end() - 1  # opening {
        # Extract just this control's brace body
        depth = 0
        for i, ch in enumerate(section_body[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    ctrl_body = section_body[start : i + 1]
                    break
        else:
            ctrl_body = ""

        props = parse_class_props(ctrl_body, macros)

        # Normalise idc
        idc = props.get("idc")
        if isinstance(idc, float):
            idc = int(idc)
            props["idc"] = idc

        # Infer type from parent if not explicit
        if "type" not in props and parent:
            _TYPE_FROM_PARENT = {
                "RscText": 0, "RscText_Title": 0, "RscText_SubTitle": 0,
                "RscText_Small": 0, "RscFrame": 0, "IGUIBack": 0,
                "RscButton": 1, "RscButton_Main": 1,
                "RscButton_Back": 1, "RscButton_Exit": 1,
                "RscEdit": 2, "RscCombo": 4, "RscListBox": 5,
                "RscClickableText": 11, "RscStructuredText": 13,
                "RscControlsGroup": 15,
                "RscShortcutButton": 16, "RscShortcutButtonMain": 16,
                "RscIGUIShortcutButton": 16,
                "RscListnBox": 102, "RscListBoxA": 102,
            }
            inferred = _TYPE_FROM_PARENT.get(parent)
            if inferred is not None:
                props["type"] = inferred

        type_num = props.get("type")
        if isinstance(type_num, (int, float)):
            type_num = int(type_num)
            props["type_name"] = _CT_MAP.get(type_num, f"type_{type_num}")

        control_entry = {
            "name": ctrl_name,
            "parent": parent,
        }
        # Pull only the interesting props (keep ordering clean)
        for key in ("idc", "type", "type_name", "x", "y", "w", "h",
                    "text", "action", "tooltip", "moving",
                    "colorBackground", "colorText", "sizeEx", "shadow",
                    "style", "onButtonClick", "columns", "rowHeight"):
            if key in props:
                control_entry[key] = props[key]
        controls.append(control_entry)

    return controls


# ---------------------------------------------------------------------------
# Dialog index  (stubs for all 18 dialogs)
# ---------------------------------------------------------------------------
_DIALOG_STUBS = [
    ("WFBE_UpgradeMenu", 504000, "Commander upgrade tree"),
    ("WFBE_VoteMenu", 500000, "Vote menu (generic)"),
    ("WFBE_Commander_VoteMenu", 500999, "Commander vote"),
    ("WFBE_RespawnMenu", 511000, "Respawn map (full-screen with RscMapControl)"),
    ("WFBE_TransferMenu", 505000, "Funds transfer (slider + edit + listbox)"),
    ("WFBE_BuyGearMenu", 503000, "Gear purchase (full-screen, most complex)"),
    ("WF_Menu", 11000, "Main WF menu — 10 RscShortcutButtonMain buttons in 2-col grid"),
    ("RscMenu_Team", 13000, "Team/squad management"),
    ("RscMenu_BuyUnits", 12000, "Unit purchase (listbox + minimap + factory tabs)"),
    ("RscMenu_Command", 17990, "Commander orders"),
    ("RscMenu_Tactical", 21710, "Tactical menu"),
    ("RscMenu_Upgrade", 24350, "Another upgrade view"),
    ("RscMenu_Service", 28800, "Service/repair"),
    ("RscMenu_UnitCamera", 30630, "Unit camera"),
    ("RscDisplay_Parameters", 31890, "Parameters display"),
    ("RscMenu_EASA", 32650, "EASA engineer menu"),
    ("RscMenu_Economy", 33430, "Economy menu"),
    ("RscMenu_Help", 34990, "Help screen"),
]

_HUD_STUBS = [
    ("RscOverlay", 10200, "Side HUD icons"),
    ("CaptureBar", 600100, "Capture-progress bar"),
    ("OptionsAvailable", 10200, "RUBHUD options overlay"),
    ("EndOfGameStats", 90000, "End-of-game stats screen"),
    ("WFBE_ConstructionInterface", 112200, "Construction build interface"),
]


def build_dialog_index() -> list:
    return [
        {"class": cls, "idd": idd, "description": desc, "coord_system": "unit_square_0_1"}
        for cls, idd, desc in _DIALOG_STUBS
    ]


def build_hud_index() -> list:
    return [
        {"class": cls, "idd": idd, "description": desc, "coord_system": "safezone"}
        for cls, idd, desc in _HUD_STUBS
    ]


# ---------------------------------------------------------------------------
# Coordinate convention doc
# ---------------------------------------------------------------------------
_COORD_CONVENTION = {
    "dialogs": {
        "system": "unit_square_0_1",
        "description": (
            "x=0,y=0 is top-left of screen; x=1,y=1 is bottom-right. "
            "All x/y/w/h are fractions of total screen dimensions."
        ),
        "example": {"x": 0.17467, "y": 0.186955, "w": 0.65066, "h": 0.63192},
    },
    "hud_overlays": {
        "system": "safezone",
        "description": (
            "Positions expressed as SafeZone expressions: "
            "x = <frac> * safezoneW + safezoneX. "
            "safezoneW/H/X/Y are runtime globals; 16:9 approximation: "
            "safezoneW=0.86, safezoneH=0.86, safezoneX=0.07, safezoneY=0.07."
        ),
        "example_expression": "x = 0.882604 * safezoneW + safezoneX",
        "runtime_approx_16x9": {
            "safezoneX": 0.07, "safezoneY": 0.07,
            "safezoneW": 0.86, "safezoneH": 0.86,
        },
    },
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(src_dir: Path, out_path: Path) -> dict:
    styles_path = src_dir / "Styles.hpp"
    ressources_path = src_dir / "Ressources.hpp"
    dialogs_path = src_dir / "Dialogs.hpp"

    for p in (styles_path, ressources_path, dialogs_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    styles_text = styles_path.read_text(encoding="utf-8", errors="replace")
    ressources_text = ressources_path.read_text(encoding="utf-8", errors="replace")
    dialogs_text = dialogs_path.read_text(encoding="utf-8", errors="replace")

    macros = load_macros(styles_text, ressources_text)
    base_classes = extract_base_classes(ressources_text, macros)
    wf_menu = extract_wf_menu(dialogs_text, macros)

    output = {
        "meta": {
            "generated_by": "tools/extract_dialogs.py",
            "source_dir": str(src_dir),
            "target_dialog": "WF_Menu",
            "target_idd": 11000,
        },
        "coord_convention": _COORD_CONVENTION,
        "macros": macros,
        "base_classes": base_classes,
        "dialogs_index": build_dialog_index(),
        "hud_index": build_hud_index(),
        "WF_Menu": wf_menu,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestExtractDialogs(unittest.TestCase):

    STYLES_SNIPPET = """
#define WFBE_Background_Color       {0, 0, 0, 0.7}
#define WFBE_Background_Border      {0.2588, 0.7137, 1, 1}
#define WFBE_Background_Border_Thick 0.001
#define WFBE_Menu_Button_Color      {0.258823529, 0.713725490, 1, 0.7}
#define WFBE_Menu_Title_Color       {0.258823529, 0.713725490, 1, 1}
"""

    RESSOURCES_SNIPPET = """
#define CT_STATIC   0
#define CT_BUTTON   1
#define CT_EDIT     2

class RscText {
    idc = -2;
    type = 0;
    x = 0;
    y = 0;
    h = 0.037;
    w = 0;
    sizeEx = 0.03;
    colorText[] = {0.9333, 0.8980, 0.5451, 0.9};
};
class RscText_Title : RscText {
    h = 0.04;
    sizeEx = 0.045;
};
class RscShortcutButtonMain : RscShortcutButton {
    type = 16;
    w = 0.313726;
    h = 0.104575;
};
"""

    DIALOGS_SNIPPET = """
class WF_Menu {
    movingEnable = 1;
    idd = 11000;
    onLoad = "ExecVM \\"test\\"";

    class controlsBackground {
        class Background_M : RscText {
            x = 0.17467;
            y = 0.186955;
            w = 0.65066;
            h = 0.63192;
            moving = 1;
            colorBackground[] = WFBE_Background_Color;
        };
    };
    class controls {
        class Button_A : RscShortcutButtonMain {
            idc = 11001;
            x = 0.17598;
            y = 0.250358;
            w = 0.313727;
            h = 0.104575;
            text = "$STR_WF_MAIN_Purchase_Units";
            action = "MenuAction = 1";
        };
        class TitleMenu : RscText_Title {
            idc = 11015;
            x = 0.178164;
            y = 0.19379;
            w = 0.800001;
            sizeEx = 0.035;
        };
    };
};
"""

    def _macros(self):
        return load_macros(self.STYLES_SNIPPET, self.RESSOURCES_SNIPPET)

    def test_load_macros_color(self):
        m = self._macros()
        self.assertIn("WFBE_Background_Color", m)
        color = m["WFBE_Background_Color"]
        self.assertIsInstance(color, list)
        self.assertEqual(len(color), 4)
        self.assertEqual(color[0], 0)

    def test_load_macros_scalar(self):
        m = self._macros()
        self.assertIn("WFBE_Background_Border_Thick", m)
        self.assertAlmostEqual(m["WFBE_Background_Border_Thick"], 0.001)

    def test_load_macros_ct_defines(self):
        m = self._macros()
        self.assertEqual(m["CT_STATIC"], 0)
        self.assertEqual(m["CT_BUTTON"], 1)

    def test_extract_class_body_found(self):
        body = _extract_class_body(self.RESSOURCES_SNIPPET, "RscText")
        self.assertIsNotNone(body)
        self.assertIn("sizeEx", body)

    def test_extract_class_body_missing(self):
        body = _extract_class_body(self.RESSOURCES_SNIPPET, "NonExistentClass")
        self.assertIsNone(body)

    def test_parse_class_props_basic(self):
        m = self._macros()
        body = _extract_class_body(self.RESSOURCES_SNIPPET, "RscText")
        self.assertIsNotNone(body)
        props = parse_class_props(body, m)
        self.assertEqual(props.get("type"), 0)
        self.assertAlmostEqual(props.get("h"), 0.037)

    def test_extract_wf_menu_idd(self):
        macros = self._macros()
        wf = extract_wf_menu(self.DIALOGS_SNIPPET, macros)
        self.assertEqual(wf["idd"], 11000)
        self.assertTrue(wf["movingEnable"])

    def test_extract_wf_menu_background_count(self):
        macros = self._macros()
        wf = extract_wf_menu(self.DIALOGS_SNIPPET, macros)
        bg = wf["controlsBackground"]
        self.assertEqual(len(bg), 1)
        self.assertEqual(bg[0]["name"], "Background_M")
        self.assertAlmostEqual(bg[0]["x"], 0.17467)

    def test_extract_wf_menu_controls(self):
        macros = self._macros()
        wf = extract_wf_menu(self.DIALOGS_SNIPPET, macros)
        ctrls = wf["controls"]
        self.assertEqual(len(ctrls), 2)
        btn = ctrls[0]
        self.assertEqual(btn["name"], "Button_A")
        self.assertEqual(btn["idc"], 11001)
        self.assertEqual(btn["parent"], "RscShortcutButtonMain")

    def test_extract_wf_menu_type_inferred(self):
        macros = self._macros()
        wf = extract_wf_menu(self.DIALOGS_SNIPPET, macros)
        # Button_A parent is RscShortcutButtonMain -> type 16
        btn = wf["controls"][0]
        self.assertEqual(btn.get("type"), 16)
        self.assertEqual(btn.get("type_name"), "RscShortcutButton")

    def test_macro_color_resolved_in_background(self):
        macros = self._macros()
        wf = extract_wf_menu(self.DIALOGS_SNIPPET, macros)
        bg_m = wf["controlsBackground"][0]
        # colorBackground should be resolved from macro
        self.assertIn("colorBackground", bg_m)
        color = bg_m["colorBackground"]
        self.assertIsInstance(color, list)
        self.assertEqual(len(color), 4)
        self.assertEqual(color[:3], [0, 0, 0])
        self.assertAlmostEqual(color[3], 0.7)  # {0,0,0,0.7}

    def test_base_classes_extracted(self):
        macros = self._macros()
        classes = extract_base_classes(self.RESSOURCES_SNIPPET, macros)
        self.assertIn("RscText", classes)
        self.assertIn("RscText_Title", classes)
        rsc_text = classes["RscText"]
        self.assertEqual(rsc_text.get("type"), 0)
        self.assertEqual(rsc_text.get("type_name"), "CT_STATIC")

    def test_parse_array(self):
        self.assertEqual(_parse_array("{0.25, 0.71, 1, 1}"), [0.25, 0.71, 1, 1])
        self.assertEqual(_parse_array("{0, 0, 0, 0.7}"), [0, 0, 0, 0.7])

    def test_parse_scalar(self):
        self.assertEqual(_parse_scalar("0.037"), 0.037)
        self.assertEqual(_parse_scalar('"Zeppelin32"'), "Zeppelin32")
        self.assertEqual(_parse_scalar("true"), True)
        self.assertEqual(_parse_scalar("2"), 2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if "--test" in sys.argv or "test" in sys.argv:
        sys.argv = [sys.argv[0]]
        unittest.main(exit=True)
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=str(DEFAULT_SRC), help="Path to Rsc/ directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")
    args = parser.parse_args()

    src_dir = Path(args.src)
    out_path = Path(args.out)

    print(f"[extract_dialogs] src  = {src_dir}")
    print(f"[extract_dialogs] out  = {out_path}")

    output = run(src_dir, out_path)

    wf = output["WF_Menu"]
    bg_count = len(wf.get("controlsBackground", []))
    ctrl_count = len(wf.get("controls", []))
    total = bg_count + ctrl_count

    print(f"\n[extract_dialogs] Target dialog : WF_Menu (idd {wf['idd']})")
    print(f"[extract_dialogs] controlsBackground : {bg_count} controls")
    print(f"[extract_dialogs] controls            : {ctrl_count} controls")
    print(f"[extract_dialogs] TOTAL               : {total} controls")
    print(f"[extract_dialogs] Written -> {out_path}")


if __name__ == "__main__":
    main()
