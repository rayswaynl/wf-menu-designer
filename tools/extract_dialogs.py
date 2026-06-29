"""
extract_dialogs.py
==================
Parse ALL WASP Arma 2 mission RSC files and emit assets/data/ui.json.

Parses:
  Styles.hpp     — WFBE_* color/style macros -> macros{}
  Ressources.hpp — base control class definitions with inheritance -> baseClasses{}
  Dialogs.hpp    — all 18 full-screen dialogs -> displays{}
  Titles.hpp     — all 5 RscTitles HUD overlays -> displays{}

Output schema (assets/data/ui.json):
  {
    "meta": { generated_by, source_dir, display_count, generated_at },
    "macros": { "<MACRO_NAME>": <rgba_list_or_scalar> },
    "baseClasses": {
      "<ClassName>": {
        "parent": "<ParentClass> | null",
        "props": { <resolved top-level props> },
        "subClasses": { "<SubName>": { <verbatim sub-class props> } }
      }
    },
    "displays": {
      "<DisplayName>": {
        "idd": <int>,
        "category": "dialog" | "hud",
        "posSystem": "unit_square" | "safezone",
        "movingEnable": <bool>,
        "titlesArray": ["Name1", ...],   // RscTitles only
        "background": [
          { "name", "baseClass", "idc", "props": {raw overrides}, "resolved": {merged}, "subClasses": {} }
        ],
        "controls": [
          { "name", "baseClass", "idc", "props": {raw overrides}, "resolved": {merged}, "subClasses": {} }
        ]
      }
    }
  }

Usage:
    python tools/extract_dialogs.py [--src <rsc_dir>] [--out <output_json>] [--test]

Defaults:
    --src  C:\\Users\\Steff\\a2waspwarfare\\Missions\\[55-2hc]warfarev2_073v48co.chernarus\\Rsc
    --out  assets/data/ui.json   (relative to repo root = parent of tools/)
"""

import re
import json
import sys
import argparse
import unittest
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = (
    Path(r"C:\Users\Steff\a2waspwarfare\Missions")
    / "[55-2hc]warfarev2_073v48co.chernarus"
    / "Rsc"
)
DEFAULT_OUT = REPO_ROOT / "assets" / "data" / "ui.json"

# ---------------------------------------------------------------------------
# Known display metadata (source-verified IDDs + categories)
# ---------------------------------------------------------------------------

# Dialogs: plain 0..1 float coords
_DIALOG_NAMES = [
    "WFBE_UpgradeMenu",
    "WFBE_VoteMenu",
    "WFBE_Commander_VoteMenu",
    "WFBE_RespawnMenu",
    "WFBE_TransferMenu",
    "WFBE_BuyGearMenu",
    "WF_Menu",
    "RscMenu_Team",
    "RscMenu_BuyUnits",
    "RscMenu_Command",
    "RscMenu_Tactical",
    "RscMenu_Upgrade",
    "RscMenu_Service",
    "RscMenu_UnitCamera",
    "RscDisplay_Parameters",
    "RscMenu_EASA",
    "RscMenu_Economy",
    "RscMenu_Help",
]

# HUD RscTitles: use SafeZone expressions (unless overridden per-display)
_HUD_NAMES = [
    "b2zgroup",                  # loadscreen, idd=-2
    "RscOverlay",
    "CaptureBar",
    "OptionsAvailable",
    "EndOfGameStats",
    "WFBE_ConstructionInterface",
]

# IDD collisions documented in the plan:
# RscOverlay + OptionsAvailable both idd=10200
# RscMenu_EASA + RscMenu_Economy both idd=23000

# ---------------------------------------------------------------------------
# Type number -> string label
# ---------------------------------------------------------------------------
_CT_MAP = {
    0: "CT_STATIC",
    1: "CT_BUTTON",
    2: "CT_EDIT",
    4: "CT_COMBO",
    5: "CT_LISTBOX",
    11: "CT_CLICKABLETEXT",
    13: "CT_STRUCTUREDTEXT",
    15: "CT_CONTROLS_GROUP",
    16: "CT_SHORTCUTBUTTON",
    43: "CT_XSLIDERH",
    101: "CT_MAP",
    102: "CT_LISTNBOX",
}

# Infer control type from base-class name (for controls that inherit type)
_TYPE_FROM_PARENT = {
    "RscText": 0, "RscText_Title": 0, "RscText_SubTitle": 0,
    "RscText_Small": 0, "RscFrame": 0, "IGUIBack": 0,
    "RscPicture": 0, "RscPictureKeepAspect": 0,
    "RscStructuredText": 13, "RscStructuredTextB": 13,
    "RscButton": 1, "RscButton_Main": 1,
    "RscButton_Back": 1, "RscButton_Exit": 1,
    "RscEdit": 2,
    "RscCombo": 4,
    "RscListBox": 5, "RscListBoxA": 5,
    "RscClickableText": 11,
    "RscControlsGroup": 15,
    "RscShortcutButton": 16, "RscShortcutButtonMain": 16,
    "RscIGUIShortcutButton": 16,
    "RscListnBox": 102,
    "RscMapControl": 101,
    "RscXSliderH": 43,
}

# Base classes to extract from Ressources.hpp
_BASE_CLASS_NAMES = [
    "RscControlsGroup",
    "RscPicture", "RscPictureKeepAspect",
    "IGUIBack",
    "RscButton", "RscButton_Main", "RscButton_Back", "RscButton_Exit",
    "RscShortcutButton", "RscIGUIShortcutButton", "RscShortcutButtonMain",
    "RscListBox", "RscListnBox", "RscListBoxA",
    "RscText", "RscText_Title", "RscText_SubTitle", "RscText_Small",
    "RscEdit",
    "RscStructuredText", "RscStructuredTextB",
    "RscFrame",
    "RscXSliderH",
    "RscCombo",
    "RscClickableText",
    "RscMapControl",
]

# Inheritance chain for base classes (parent -> child)
_BASE_CLASS_PARENTS = {
    "RscPictureKeepAspect": "RscPicture",
    "RscButton_Main": "RscButton",
    "RscButton_Back": "RscButton",
    "RscButton_Exit": "RscButton",
    "RscIGUIShortcutButton": "RscShortcutButton",
    "RscShortcutButtonMain": "RscShortcutButton",
    "RscListnBox": "RscListBox",
    "RscListBoxA": "RscListBox",
    "RscText_Title": "RscText",
    "RscText_SubTitle": "RscText",
    "RscText_Small": "RscText",
    "RscEdit": "RscText",
    "RscStructuredTextB": "RscStructuredText",
}

# ---------------------------------------------------------------------------
# Low-level parsers
# ---------------------------------------------------------------------------

_ARRAY_RE = re.compile(r"\{([^}]*)\}")
_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_DEFINE_RE = re.compile(r"#define\s+(\w+)\s+(.*?)(?=\r?\n)", re.MULTILINE)


def _parse_scalar(raw: str):
    """Coerce to float/int/bool; fall back to str (preserves SafeZone expressions)."""
    s = raw.strip().strip('"')
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        v = float(s)
        return int(v) if v == int(v) else v
    except (ValueError, OverflowError):
        return s


def _parse_array(raw: str):
    """Parse `{0.25, 0.71, 1, 1}` -> [0.25, 0.71, 1.0, 1.0]."""
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


# Property name normalisation: case-insensitive HPP -> canonical camelCase
_PROP_NORMALISE = {
    "colorbackground": "colorBackground",
    "colorbackground2": "colorBackground2",
    "colorbackgroundactive": "colorBackgroundActive",
    "colorbackgrounddisabled": "colorBackgroundDisabled",
    "colortext": "colorText",
    "colordisabled": "colorDisabled",
    "colorselected": "colorSelected",
    "colorborder": "colorBorder",
    "colorfocused": "colorFocused",
    "colorshadow": "colorShadow",
    "colorselect": "colorSelect",
    "colorselectbackground": "colorSelectBackground",
    "colorselectbackground2": "colorSelectBackground2",
    "colorscrollbar": "colorScrollbar",
    "coloractive": "colorActive",
    "colorselect2": "colorSelect2",
}

_PROP_LINE_RE = re.compile(
    r"^\s*(\w+)\s*(?:\[\])?\s*=\s*(.+?)\s*;",
    re.MULTILINE,
)


def _extract_class_body(text: str, class_name: str) -> "str | None":
    """
    Find `class <class_name>` (optionally `: Parent`) and return its brace body
    (including outer braces). Handles nested braces.
    """
    pat = re.compile(
        r"class\s+" + re.escape(class_name) + r"\b[^{]*\{",
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
                return text[start: i + 1]
    return None


def _strip_nested_classes(body: str) -> str:
    """Remove all nested class blocks so property parsing is unambiguous."""
    result = []
    depth = 0
    in_class = False
    i = 0
    while i < len(body):
        # Detect 'class <word>' opener
        if not in_class and body[i:i+5] == "class":
            # Check that it's actually a class keyword
            rest = body[i:]
            cm = re.match(r"class\s+\w+\b[^{]*\{", rest)
            if cm:
                # Skip this whole nested class
                in_class = True
                depth = 0
                i += cm.end() - 1  # move to opening {
        if in_class:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
                if depth == 0:
                    in_class = False
        else:
            result.append(body[i])
        i += 1
    return "".join(result)


def _parse_props(body: str, macros: dict) -> dict:
    """
    Parse property lines from a class body, resolving macro references.
    Returns a dict of prop_name -> value.
    """
    clean = _strip_nested_classes(body)
    props: dict = {}
    for name, raw in _PROP_LINE_RE.findall(clean):
        canonical = _PROP_NORMALISE.get(name.lower(), name)
        raw = raw.strip()
        # Strip inline // comments
        raw = re.sub(r"\s*//.*", "", raw).strip()
        if raw.startswith("{"):
            value = _parse_array(raw)
        elif raw in macros:
            value = macros[raw]
        else:
            value = _parse_scalar(raw)
        props[canonical] = value
    return props


def _extract_sub_classes(body: str, macros: dict) -> dict:
    """
    Extract direct child class blocks (e.g. HitZone, TextPos, Attributes, ScrollBar)
    and return their properties verbatim. Does NOT recurse.
    """
    sub: dict = {}
    inner_re = re.compile(r"class\s+(\w+)\b[^{]*\{", re.MULTILINE)
    pos = 0
    while True:
        m = inner_re.search(body, pos)
        if not m:
            break
        sub_name = m.group(1)
        sub_start = m.end() - 1  # opening {
        depth = 0
        end_pos = sub_start
        for i, ch in enumerate(body[sub_start:], sub_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        sub_body = body[sub_start: end_pos + 1]
        sub[sub_name] = _parse_props(sub_body, macros)
        pos = end_pos + 1
    return sub


# ---------------------------------------------------------------------------
# Macro loading
# ---------------------------------------------------------------------------

def load_macros(styles_text: str, ressources_text: str) -> dict:
    """Parse #define directives from both files -> macro name -> resolved value."""
    raw: dict = {}
    for text in (styles_text, ressources_text):
        for name, value in _DEFINE_RE.findall(text):
            raw[name] = value.strip()

    resolved: dict = {}
    for name, value in raw.items():
        # Strip inline comments
        value = re.sub(r"\s*//.*", "", value).strip()
        if "{" in value:
            resolved[name] = _parse_array(value)
        else:
            try:
                v = float(value)
                resolved[name] = int(v) if v == int(v) else v
            except (ValueError, OverflowError):
                resolved[name] = value
    return resolved


# ---------------------------------------------------------------------------
# Base class extraction
# ---------------------------------------------------------------------------

def extract_base_classes(ressources_text: str, macros: dict) -> dict:
    """
    Parse each known base class from Ressources.hpp.
    Returns dict of class_name -> {
        parent: str|null,
        props: {resolved},
        subClasses: { sub_name: {props} }
    }
    Also resolves inherited props by walking the parent chain.
    """
    raw_classes: dict = {}
    for name in _BASE_CLASS_NAMES:
        body = _extract_class_body(ressources_text, name)
        if body is None:
            continue
        props = _parse_props(body, macros)
        subs = _extract_sub_classes(body, macros)
        parent = _BASE_CLASS_PARENTS.get(name)
        raw_classes[name] = {
            "parent": parent,
            "props": props,
            "subClasses": subs,
        }

    # Resolve type_name for each class
    for name, cls in raw_classes.items():
        t = cls["props"].get("type")
        if t is None:
            # Try to inherit from parent
            p = cls["parent"]
            if p and p in raw_classes:
                t = raw_classes[p]["props"].get("type")
        if isinstance(t, (int, float)):
            cls["props"]["type_name"] = _CT_MAP.get(int(t), f"type_{int(t)}")

    return raw_classes


def _resolve_props(raw_props: dict, base_class_name: "str | None",
                   base_classes: dict, macros: dict) -> dict:
    """
    Build resolved props by starting from the base class chain and overlaying
    raw_props on top. Returns merged dict.
    """
    # Walk inheritance chain to build base props (lowest ancestor first)
    chain = []
    current = base_class_name
    seen = set()
    while current and current not in seen:
        seen.add(current)
        if current in base_classes:
            chain.append(base_classes[current]["props"])
            current = base_classes[current].get("parent")
        else:
            break

    # Merge: ancestor first, then each child overrides
    resolved: dict = {}
    for ancestor_props in reversed(chain):
        resolved.update(ancestor_props)

    # Also infer type from parent name if missing
    if "type" not in resolved and base_class_name:
        inferred = _TYPE_FROM_PARENT.get(base_class_name)
        if inferred is not None:
            resolved["type"] = inferred

    # Overlay the raw (override) props
    resolved.update(raw_props)

    # Resolve type_name
    t = resolved.get("type")
    if isinstance(t, (int, float)):
        resolved["type_name"] = _CT_MAP.get(int(t), f"type_{int(t)}")

    return resolved


# ---------------------------------------------------------------------------
# Control parsing (shared for dialogs + HUD)
# ---------------------------------------------------------------------------

def _parse_section_controls(section_body: str, macros: dict,
                             base_classes: dict) -> list:
    """
    Extract `class Name : Parent { ... }` entries from a controlsBackground
    or controls section body. Returns list of control dicts.
    """
    inner_re = re.compile(r"class\s+(\w+)\s*(?::\s*(\w+)\s*)?\{", re.MULTILINE)
    controls = []
    pos = 0
    while True:
        m = inner_re.search(section_body, pos)
        if not m:
            break
        ctrl_name = m.group(1)
        parent_name = m.group(2)
        ctrl_start = m.end() - 1  # opening {
        depth = 0
        end_pos = ctrl_start
        for i, ch in enumerate(section_body[ctrl_start:], ctrl_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        ctrl_body = section_body[ctrl_start: end_pos + 1]
        pos = end_pos + 1

        raw_props = _parse_props(ctrl_body, macros)
        sub_classes = _extract_sub_classes(ctrl_body, macros)

        # Normalise idc to int
        if "idc" in raw_props and isinstance(raw_props["idc"], float):
            raw_props["idc"] = int(raw_props["idc"])

        # Resolved props: start from base class (known Rsc* base, not local parent)
        # Walk local display-side parent chain to find first known Rsc* base class
        rsc_base = _find_rsc_base(parent_name, base_classes)
        resolved = _resolve_props(raw_props, rsc_base, base_classes, macros)

        # Also inherit from local display-side parent by merging its raw_props
        # (We can't fully resolve local-parent chains without multi-pass, so we
        #  store the immediate parent name and the rsc_base separately)
        idc = raw_props.get("idc") or resolved.get("idc")

        control_entry = {
            "name": ctrl_name,
            "baseClass": parent_name,
            "rscBase": rsc_base,
            "idc": idc if idc is not None else -1,
            "props": raw_props,
            "resolved": resolved,
            "subClasses": sub_classes,
        }
        controls.append(control_entry)

    return controls


def _find_rsc_base(name: "str | None", base_classes: dict) -> "str | None":
    """
    Given a class name (possibly a local alias like CA_Background), return
    the first name in the hierarchy that exists in base_classes (i.e., is a
    real Rsc* or IGUI* base class we know about). If name itself is in
    base_classes, return it. Otherwise return None (caller handles unknown parents).
    """
    if name is None:
        return None
    if name in base_classes:
        return name
    # If not known, it might be a local class defined elsewhere; return None.
    # The renderer will fall back to guessing from the name prefix.
    return None


# ---------------------------------------------------------------------------
# Display parsing
# ---------------------------------------------------------------------------

def _parse_display(source_text: str, display_name: str, macros: dict,
                   base_classes: dict, category: str,
                   pos_system: str) -> "dict | None":
    """
    Parse a single display class from source_text and return its structured dict.
    Returns None if the class is not found.

    Handles two control layouts:
      (a) Structured: controls inside a `class controls { ... }` sub-block (dialogs, most HUD).
      (b) Flat: controls as direct class children with a `controls[] = {...}` name array
          (e.g. OptionsAvailable, RscOverlay in Titles.hpp).
    """
    body = _extract_class_body(source_text, display_name)
    if body is None:
        return None

    # Top-level scalar props
    idd_m = re.search(r"\bidd\s*=\s*(\d+)", body)
    moving_m = re.search(r"\bmovingEnable\s*=\s*(\d)", body)

    idd = int(idd_m.group(1)) if idd_m else -1
    moving_enable = bool(int(moving_m.group(1))) if moving_m else False

    # RscTitles controls[] name array (flat layout uses this as the control registry)
    # Match multi-line controls[] = { "A","B",... } — allow newlines inside braces
    titles_array_m = re.search(
        r"\bcontrols\s*\[\s*\]\s*=\s*\{([^}]*)\}", body, re.DOTALL
    )
    titles_array = None
    if titles_array_m:
        raw_names = titles_array_m.group(1)
        names = [n.strip().strip('"') for n in raw_names.split(",") if n.strip()]
        if names:
            titles_array = names

    # controlsBackground section
    bg_body = _extract_class_body(body, "controlsBackground")
    bg_controls = []
    if bg_body:
        bg_controls = _parse_section_controls(bg_body, macros, base_classes)

    # Try structured `class controls { ... }` sub-block first
    ctrl_body_text = _extract_class_body(body, "controls")
    ctrl_controls = []
    if ctrl_body_text:
        ctrl_controls = _parse_section_controls(ctrl_body_text, macros, base_classes)
    elif titles_array:
        # Flat layout: controls are direct class children, named in titles_array.
        # Parse the whole body but only pick up classes whose names are in titles_array
        # (or any class that has a valid base class — avoids picking up sub-classes
        # of sub-classes).
        all_direct = _parse_section_controls(body, macros, base_classes)
        name_set = set(titles_array)
        ctrl_controls = [c for c in all_direct if c["name"] in name_set]
        # If we couldn't match any by name, fall back to all direct children that
        # look like controls (have idc or x/y/w/h props)
        if not ctrl_controls:
            ctrl_controls = [
                c for c in all_direct
                if any(k in c.get("props", {}) for k in ("idc", "x", "y", "w", "h"))
            ]

    result = {
        "idd": idd,
        "category": category,
        "posSystem": pos_system,
        "movingEnable": moving_enable,
        "background": bg_controls,
        "controls": ctrl_controls,
    }
    if titles_array is not None:
        result["titlesArray"] = titles_array

    return result


def parse_all_dialogs(dialogs_text: str, macros: dict,
                      base_classes: dict) -> dict:
    """Parse all 18 full-screen dialogs from Dialogs.hpp."""
    displays = {}
    for name in _DIALOG_NAMES:
        d = _parse_display(dialogs_text, name, macros, base_classes,
                           category="dialog", pos_system="unit_square")
        if d is not None:
            displays[name] = d
        else:
            # Record a stub so we know it was searched but not found
            displays[name] = {
                "idd": -1,
                "category": "dialog",
                "posSystem": "unit_square",
                "movingEnable": False,
                "background": [],
                "controls": [],
                "_parseError": f"{name} not found in Dialogs.hpp",
            }
    return displays


def parse_all_hud(titles_text: str, macros: dict,
                  base_classes: dict) -> dict:
    """
    Parse HUD RscTitles from Titles.hpp.
    Each HUD class lives inside the outer `class RscTitles { ... }` block.
    """
    # Get the RscTitles container body
    rsc_titles_body = _extract_class_body(titles_text, "RscTitles")
    if rsc_titles_body is None:
        # Fall back to searching the whole file
        rsc_titles_body = titles_text

    displays = {}
    for name in _HUD_NAMES:
        d = _parse_display(rsc_titles_body, name, macros, base_classes,
                           category="hud", pos_system="safezone")
        if d is None:
            # Try whole file
            d = _parse_display(titles_text, name, macros, base_classes,
                                category="hud", pos_system="safezone")
        if d is not None:
            displays[name] = d
        else:
            displays[name] = {
                "idd": -1,
                "category": "hud",
                "posSystem": "safezone",
                "movingEnable": False,
                "background": [],
                "controls": [],
                "_parseError": f"{name} not found in Titles.hpp",
            }

    # EndOfGameStats uses plain 0..1 coords despite being a RscTitle
    if "EndOfGameStats" in displays:
        displays["EndOfGameStats"]["posSystem"] = "unit_square"
    # b2zgroup uses SafeZone too (it's a loadscreen overlay, already safezone)
    # (no override needed; it inherits safezone from _HUD_NAMES default)

    return displays


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(src_dir: Path, out_path: Path) -> dict:
    styles_path = src_dir / "Styles.hpp"
    ressources_path = src_dir / "Ressources.hpp"
    dialogs_path = src_dir / "Dialogs.hpp"
    titles_path = src_dir / "Titles.hpp"

    for p in (styles_path, ressources_path, dialogs_path, titles_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    styles_text = styles_path.read_text(encoding="utf-8", errors="replace")
    ressources_text = ressources_path.read_text(encoding="utf-8", errors="replace")
    dialogs_text = dialogs_path.read_text(encoding="utf-8", errors="replace")
    titles_text = titles_path.read_text(encoding="utf-8", errors="replace")

    macros = load_macros(styles_text, ressources_text)
    base_classes = extract_base_classes(ressources_text, macros)

    dialog_displays = parse_all_dialogs(dialogs_text, macros, base_classes)
    hud_displays = parse_all_hud(titles_text, macros, base_classes)

    all_displays = {}
    all_displays.update(dialog_displays)
    all_displays.update(hud_displays)

    total_displays = len(all_displays)
    total_controls = sum(
        len(d.get("background", [])) + len(d.get("controls", []))
        for d in all_displays.values()
    )

    output = {
        "meta": {
            "generated_by": "tools/extract_dialogs.py",
            "schema_version": "2",
            "source_dir": str(src_dir),
            "display_count": total_displays,
            "total_controls": total_controls,
            "dialog_count": len(dialog_displays),
            "hud_count": len(hud_displays),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "coordConvention": {
            "unit_square": {
                "description": (
                    "Plain 0..1 floats. x=0,y=0 is top-left; x=1,y=1 is bottom-right. "
                    "Pixel coords: px_x = v * screenW, px_y = v * screenH."
                ),
                "usedBy": "dialogs",
            },
            "safezone": {
                "description": (
                    "SafeZone expression strings. "
                    "x = <frac> * safezoneW + safezoneX. "
                    "16:9 preview constants: safezoneX=0.07, safezoneY=0.07, "
                    "safezoneW=0.86, safezoneH=0.86."
                ),
                "previewConstants": {
                    "safezoneX": 0.07, "safezoneY": 0.07,
                    "safezoneW": 0.86, "safezoneH": 0.86,
                },
                "usedBy": "hud (RscTitles)",
            },
        },
        "macros": macros,
        "baseClasses": base_classes,
        "displays": all_displays,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestExtractDialogs(unittest.TestCase):

    # --- Fixtures ---

    STYLES_FIXTURE = """
#define WFBE_Background_Color           {0, 0, 0, 0.7}
#define WFBE_Background_Color_Header    {0, 0, 0, 0.4}
#define WFBE_Background_Border          {0.2588, 0.7137, 1, 1}
#define WFBE_Background_Border_Thick    0.001
#define WFBE_Menu_Button_Color          {0.258823529, 0.713725490, 1, 0.7}
#define WFBE_Menu_Button_Text_Color     {1, 1, 1, 0.8}
#define WFBE_Menu_Button_Focused_Color  {0.258823529, 0.713725490, 1, 1}
#define WFBE_Menu_Button_Sub_Color      {0.388235294, 0.925490196, 0.494117647, 0.7}
#define WFBE_Menu_Text_Color            {0.258823529, 0.713725490, 1, 1}
#define WFBE_Menu_Title_Color           {0.258823529, 0.713725490, 1, 1}
"""

    RESSOURCES_FIXTURE = """
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
    style = 256;
    font = "Zeppelin32";
    sizeEx = 0.03;
    shadow = 2;
    colorText[] = {0.9333, 0.8980, 0.5451, 0.9};
    colorBackground[] = {0, 0, 0, 0};
};
class RscText_Title : RscText {
    h = 0.04;
    sizeEx = 0.045;
    colorText[] = {0.2588, 0.7137, 1, 1};
    shadow = 1;
};
class RscButton {
    type = 1;
    idc = -2;
    h = 0.036;
    sizeEx = 0.035;
    colorText[] = {1, 1, 1, 0.8};
    colorBackground[] = {0.5882, 0.5882, 0.3529, 0.7};
    colorFocused[] = {0.5882, 0.5882, 0.3529, 0.7};
};
class RscButton_Main : RscButton {
    colorBackground[] = WFBE_Menu_Button_Color;
    colorFocused[] = WFBE_Menu_Button_Focused_Color;
    colorText[] = WFBE_Menu_Button_Text_Color;
};
class RscShortcutButton {
    type = 16;
    idc = -2;
    w = 0.183825;
    h = 0.104575;
    color[] = {0.543, 0.5742, 0.4102, 1.0};
    class HitZone {
        left = 0.004;
        top = 0.029;
        right = 0.004;
        bottom = 0.029;
    };
    class TextPos {
        left = 0.05;
        top = 0.034;
        right = 0.005;
        bottom = 0.005;
    };
};
class RscShortcutButtonMain : RscShortcutButton {
    w = 0.313726;
    h = 0.104575;
    color[] = {0.2588, 0.7137, 1, 1};
    class HitZone {
        left = 0.0;
        top = 0.0;
        right = 0.0;
        bottom = 0.0;
    };
};
class RscListBox {
    idc = -2;
    type = 5;
    colorText[] = {1, 1, 1, 0.75};
    colorBackground[] = {0, 0, 0, 1};
    class ScrollBar {
        color[] = {1, 1, 1, 0.6};
    };
};
class RscListnBox : RscListBox {
    type = 102;
    sizeEx = 0.029;
    rowHeight = 0.03;
};
"""

    DIALOG_FIXTURE = """
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
        class Button_B : RscShortcutButtonMain {
            idc = 11002;
            x = 0.49066;
            y = 0.250358;
            w = 0.313727;
            h = 0.104575;
            text = "$STR_WF_MAIN_Purchase_Gear";
            action = "MenuAction = 2";
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

    HUD_FIXTURE = """
class RscTitles {
    class CaptureBar {
        idd = 600100;
        duration = 15000;
        name = "Capture Bar";
        controls[] = {"CA_Progress_Bar_Background","CA_Progress_Bar","CA_Progress_Label"};

        class controls {
            class CA_Progress_Bar_Background : RscText {
                idc = 601000;
                x = 0.3;
                y = "((SafeZoneH + SafeZoneY) - (1 + 0.165))*-1";
                w = 0.4;
                h = 0.06;
                colorBackground[] = {0,0,0,0.001};
            };
            class CA_Progress_Label : RscText {
                idc = 601002;
                x = 0.31;
                w = 0.38;
                y = "((SafeZoneH + SafeZoneY) - (1 + 0.177))*-1";
            };
        };
    };
};
"""

    # OptionsAvailable has FLAT controls (direct class children, no class controls{} wrapper)
    SAFEZONE_FIXTURE = """
class RscTitles {
    class OptionsAvailable {
        idd = 10200;
        controls[] = {"RUBHUD_Health","RUBHUD_Health_Value"};
        controlsBackground[] = {};

        class RUBHUD_Health : RscText {
            idc = 1346;
            x = 0.881728 * safezoneW + safezoneX;
            y = 0.18626 * safezoneH + safezoneY;
            w = 0.7977083 * safezoneW;
            h = 0.0228518 * safezoneH;
            sizeEx = 0.030;
        };
        class RUBHUD_Health_Value : RscText {
            idc = 1347;
            x = 0.921958 * safezoneW + safezoneX;
            y = 0.18626 * safezoneH + safezoneY;
            w = 0.7977083 * safezoneW;
            h = 0.0228518 * safezoneH;
            sizeEx = 0.030;
        };
    };
};
"""

    def _macros(self):
        return load_macros(self.STYLES_FIXTURE, self.RESSOURCES_FIXTURE)

    def _base_classes(self):
        return extract_base_classes(self.RESSOURCES_FIXTURE, self._macros())

    # --- Macro tests ---

    def test_macro_color_rgba(self):
        m = self._macros()
        self.assertIn("WFBE_Background_Color", m)
        color = m["WFBE_Background_Color"]
        self.assertIsInstance(color, list)
        self.assertEqual(len(color), 4)
        self.assertEqual(color[:3], [0, 0, 0])
        self.assertAlmostEqual(color[3], 0.7)

    def test_macro_scalar(self):
        m = self._macros()
        self.assertIn("WFBE_Background_Border_Thick", m)
        self.assertAlmostEqual(m["WFBE_Background_Border_Thick"], 0.001)

    def test_macro_ct_defines(self):
        m = self._macros()
        self.assertEqual(m["CT_STATIC"], 0)
        self.assertEqual(m["CT_BUTTON"], 1)

    def test_macro_button_color_present(self):
        """WFBE_Menu_Button_Color must be in macros (sanity check from plan)."""
        m = self._macros()
        self.assertIn("WFBE_Menu_Button_Color", m)
        c = m["WFBE_Menu_Button_Color"]
        self.assertIsInstance(c, list)
        self.assertAlmostEqual(c[3], 0.7, places=2)  # alpha 0.7

    # --- Base class tests ---

    def test_base_classes_has_rsc_button(self):
        bc = self._base_classes()
        self.assertIn("RscButton", bc)
        self.assertEqual(bc["RscButton"]["props"].get("type"), 1)

    def test_base_classes_has_rsc_shortcut_button(self):
        bc = self._base_classes()
        self.assertIn("RscShortcutButton", bc)
        self.assertEqual(bc["RscShortcutButton"]["props"].get("type"), 16)

    def test_base_classes_has_rsc_listbox(self):
        bc = self._base_classes()
        self.assertIn("RscListBox", bc)
        self.assertEqual(bc["RscListBox"]["props"].get("type"), 5)

    def test_base_class_subclasses_extracted(self):
        bc = self._base_classes()
        # RscShortcutButton has HitZone + TextPos sub-classes
        subs = bc.get("RscShortcutButton", {}).get("subClasses", {})
        self.assertIn("HitZone", subs)
        self.assertIn("TextPos", subs)

    def test_rscshortcutbuttonmain_parent(self):
        bc = self._base_classes()
        self.assertIn("RscShortcutButtonMain", bc)
        self.assertEqual(bc["RscShortcutButtonMain"]["parent"], "RscShortcutButton")

    def test_base_class_type_name(self):
        bc = self._base_classes()
        self.assertEqual(bc["RscButton"]["props"].get("type_name"), "CT_BUTTON")
        self.assertEqual(bc["RscShortcutButton"]["props"].get("type_name"), "CT_SHORTCUTBUTTON")
        self.assertEqual(bc["RscListBox"]["props"].get("type_name"), "CT_LISTBOX")

    # --- Dialog parsing tests ---

    def test_dialog_idd_and_moving(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_dialogs(self.DIALOG_FIXTURE, m, bc)
        wf = displays.get("WF_Menu")
        self.assertIsNotNone(wf)
        self.assertEqual(wf["idd"], 11000)
        self.assertTrue(wf["movingEnable"])

    def test_dialog_background_controls(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_dialogs(self.DIALOG_FIXTURE, m, bc)
        bg = displays["WF_Menu"]["background"]
        self.assertEqual(len(bg), 1)
        self.assertEqual(bg[0]["name"], "Background_M")
        self.assertEqual(bg[0]["baseClass"], "RscText")
        self.assertAlmostEqual(bg[0]["props"]["x"], 0.17467)

    def test_dialog_shortcutbutton_controls(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_dialogs(self.DIALOG_FIXTURE, m, bc)
        ctrls = displays["WF_Menu"]["controls"]
        # 2 ShortcutButtonMain + 1 TitleMenu = 3
        self.assertEqual(len(ctrls), 3)
        btn = ctrls[0]
        self.assertEqual(btn["name"], "Button_A")
        self.assertEqual(btn["baseClass"], "RscShortcutButtonMain")
        self.assertEqual(btn["idc"], 11001)

    def test_dialog_macro_resolved_in_background(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_dialogs(self.DIALOG_FIXTURE, m, bc)
        bg0 = displays["WF_Menu"]["background"][0]
        # Raw props should show macro resolved to RGBA
        color = bg0["props"].get("colorBackground")
        self.assertIsInstance(color, list)
        self.assertEqual(len(color), 4)
        self.assertEqual(color[:3], [0, 0, 0])
        self.assertAlmostEqual(color[3], 0.7)

    def test_dialog_resolved_includes_base_props(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_dialogs(self.DIALOG_FIXTURE, m, bc)
        # Button_A : RscShortcutButtonMain -> resolved should have type=16
        btn = displays["WF_Menu"]["controls"][0]
        self.assertEqual(btn["resolved"].get("type"), 16)

    def test_dialog_posystem_unit_square(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_dialogs(self.DIALOG_FIXTURE, m, bc)
        self.assertEqual(displays["WF_Menu"]["posSystem"], "unit_square")

    # --- HUD / SafeZone tests ---

    def test_hud_parsed_from_rsc_titles(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_hud(self.HUD_FIXTURE, m, bc)
        self.assertIn("CaptureBar", displays)
        cb = displays["CaptureBar"]
        self.assertEqual(cb["idd"], 600100)
        self.assertEqual(cb["posSystem"], "safezone")

    def test_hud_titles_array(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_hud(self.HUD_FIXTURE, m, bc)
        cb = displays["CaptureBar"]
        self.assertIn("titlesArray", cb)
        self.assertIn("CA_Progress_Bar_Background", cb["titlesArray"])

    def test_hud_safezone_x_stored_as_string(self):
        """SafeZone expressions must be stored as strings, not evaluated."""
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_hud(self.HUD_FIXTURE, m, bc)
        ctrls = displays["CaptureBar"]["controls"]
        progress_bar = next((c for c in ctrls
                             if c["name"] == "CA_Progress_Bar_Background"), None)
        self.assertIsNotNone(progress_bar)
        y_val = progress_bar["props"].get("y")
        # Should be stored as a string expression, not a float
        self.assertIsInstance(y_val, str)
        self.assertIn("SafeZone", y_val)

    def test_hud_options_available_safezone_coords(self):
        m = self._macros()
        bc = self._base_classes()
        displays = parse_all_hud(self.SAFEZONE_FIXTURE, m, bc)
        self.assertIn("OptionsAvailable", displays)
        oa = displays["OptionsAvailable"]
        ctrls = oa["controls"]
        health = next((c for c in ctrls if c["name"] == "RUBHUD_Health"), None)
        self.assertIsNotNone(health)
        # x should be a string expression (contains safezoneW)
        x_val = health["props"].get("x")
        self.assertIsInstance(x_val, str)
        self.assertIn("safezoneW", x_val)

    # --- Array / scalar parsing tests ---

    def test_parse_array(self):
        self.assertEqual(_parse_array("{0.25, 0.71, 1, 1}"), [0.25, 0.71, 1, 1])
        self.assertEqual(_parse_array("{0, 0, 0, 0.7}"), [0, 0, 0, 0.7])

    def test_parse_scalar_float(self):
        self.assertAlmostEqual(_parse_scalar("0.037"), 0.037)

    def test_parse_scalar_string(self):
        self.assertEqual(_parse_scalar('"Zeppelin32"'), "Zeppelin32")

    def test_parse_scalar_bool(self):
        self.assertEqual(_parse_scalar("true"), True)
        self.assertEqual(_parse_scalar("false"), False)

    def test_parse_scalar_int(self):
        self.assertEqual(_parse_scalar("2"), 2)

    def test_parse_scalar_safezone_expr(self):
        """Safezone expressions must survive as strings."""
        expr = "0.882604 * safezoneW + safezoneX"
        result = _parse_scalar(expr)
        self.assertIsInstance(result, str)
        self.assertIn("safezoneW", result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if "--test" in sys.argv or "test" in sys.argv:
        sys.argv = [sys.argv[0]]
        unittest.main(exit=True)
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=str(DEFAULT_SRC),
                        help="Path to Rsc/ directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="Output JSON path (default: assets/data/ui.json)")
    args = parser.parse_args()

    src_dir = Path(args.src)
    out_path = Path(args.out)

    print(f"[extract_dialogs] src  = {src_dir}")
    print(f"[extract_dialogs] out  = {out_path}")

    output = run(src_dir, out_path)

    meta = output["meta"]
    displays = output["displays"]

    print(f"\n[extract_dialogs] Displays parsed : {meta['display_count']}")
    print(f"[extract_dialogs]   Dialogs       : {meta['dialog_count']}")
    print(f"[extract_dialogs]   HUD           : {meta['hud_count']}")
    print(f"[extract_dialogs] Total controls  : {meta['total_controls']}")
    print(f"[extract_dialogs] Base classes    : {len(output['baseClasses'])}")
    print(f"[extract_dialogs] Macros          : {len(output['macros'])}")
    print()

    # Sanity checks
    errors = []

    total = meta["display_count"]
    if total < 24:
        errors.append(f"FAIL: Expected >=24 displays, got {total}")
    else:
        print(f"[sanity] display count {total} >= 24 : PASS")

    wf = displays.get("WF_Menu", {})
    wf_tiles = [c for c in wf.get("controls", [])
                if c.get("baseClass") == "RscShortcutButtonMain"]
    if len(wf_tiles) != 10:
        errors.append(
            f"FAIL: WF_Menu expected 10 RscShortcutButtonMain tiles, "
            f"got {len(wf_tiles)}"
        )
    else:
        print(f"[sanity] WF_Menu has 10 RscShortcutButtonMain tiles : PASS")

    bc = output["baseClasses"]
    for expected in ("RscButton", "RscShortcutButton", "RscListBox"):
        if expected in bc:
            print(f"[sanity] baseClasses contains {expected} : PASS")
        else:
            errors.append(f"FAIL: baseClasses missing {expected}")

    if "WFBE_Menu_Button_Color" in output["macros"]:
        print(f"[sanity] macros contains WFBE_Menu_Button_Color : PASS")
    else:
        errors.append("FAIL: macros missing WFBE_Menu_Button_Color")

    print()
    for name, d in sorted(displays.items()):
        bg_n = len(d.get("background", []))
        ctrl_n = len(d.get("controls", []))
        cat = d.get("category", "?")
        idd = d.get("idd", "?")
        err = " *** PARSE ERROR ***" if "_parseError" in d else ""
        print(
            f"  [{cat:6s}] idd={idd:<8}  bg={bg_n:3d}  ctrl={ctrl_n:3d}  {name}{err}"
        )

    print()
    if errors:
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print(f"[extract_dialogs] Written -> {out_path}")
        print("[extract_dialogs] All sanity checks PASSED.")


if __name__ == "__main__":
    main()
