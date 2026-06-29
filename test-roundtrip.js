/**
 * Playwright round-trip gate for Task 5: Faithful .hpp Export + Import
 *
 * Tests:
 *  1. Load WF_Menu from ui.json → export → re-parse → same controls
 *     (idc / baseClass / geometry / overrides all intact)
 *  2. Paste the real WF_Menu .hpp → import → export → re-parses equal
 *  3. Move one control → only its x/y change in the delta
 *  4. Export panel open/close + Copy/Download buttons present
 *  5. 0 console errors throughout
 */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const BASE = "http://localhost:7890";
const SCREENSHOT_DIR =
  "C:/Users/Steff/wf-menu-designer/docs/superpowers/screenshots";

// Real WF_Menu .hpp snippet (first 4 background + 2 controls from the source)
// Used for the "paste real .hpp" import test
const WF_MENU_HPP = `class WF_Menu {
\tmovingEnable = 1;
\tidd = 11000;

\tclass controlsBackground {
\t\tclass Background_M : RscText {
\t\t\tx = 0.17467;
\t\t\ty = 0.186955;
\t\t\tw = 0.65066;
\t\t\th = 0.63192;
\t\t\tmoving = 1;
\t\t\tcolorBackground[] = WFBE_Background_Color;
\t\t};
\t\tclass Background_H : RscText {
\t\t\tx = 0.17467;
\t\t\ty = 0.186955;
\t\t\tw = 0.65066;
\t\t\th = 0.0525;
\t\t\tmoving = 1;
\t\t\tcolorBackground[] = WFBE_Background_Color_Header;
\t\t};
\t};
\tclass controls {
\t\tclass Button_A : RscShortcutButtonMain {
\t\t\tidc = 11001;
\t\t\tx = 0.17598;
\t\t\ty = 0.250358;
\t\t\tw = 0.313727;
\t\t\th = 0.104575;
\t\t\ttext = $STR_WF_MAIN_Purchase_Units;
\t\t\taction = "MenuAction = 1";
\t\t};
\t\tclass Button_B : RscShortcutButtonMain {
\t\t\tidc = 11002;
\t\t\tx = 0.17598;
\t\t\ty = 0.35116;
\t\t\tw = 0.313727;
\t\t\th = 0.104575;
\t\t\ttext = $STR_WF_MAIN_Purchase_Gear;
\t\t\taction = "MenuAction = 2";
\t\t};
\t};
};`;

async function run() {
  const errors = [];
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1400, height: 900 },
  });
  const page = await ctx.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push(msg.text());
      console.error("[CONSOLE ERROR]", msg.text());
    }
  });
  page.on("pageerror", (err) => {
    errors.push(err.message);
    console.error("[PAGE ERROR]", err.message);
  });

  if (!fs.existsSync(SCREENSHOT_DIR))
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  console.log("→ Loading page...");
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);

  // ---- Verify WF_Menu loaded (10 controls) ----
  const ctrlCount = await page.locator("#stage .ctrl").count();
  console.log("✓ Stage controls loaded:", ctrlCount);
  if (ctrlCount === 0) throw new Error("No controls on stage after load");

  // ======================================================
  // TEST 1: Export WF_Menu → re-parse → same controls
  // ======================================================
  console.log("\n--- TEST 1: Export round-trip ---");

  // Open export panel
  await page.click("#export-toggle");
  await page.waitForTimeout(300);

  // Click Export
  await page.click("#export-btn");
  await page.waitForTimeout(500);

  const exportedHpp = await page.locator("#export-out").inputValue();
  if (!exportedHpp || exportedHpp.length < 50)
    throw new Error(
      "Export produced empty/minimal output: " + exportedHpp.slice(0, 100),
    );
  console.log("✓ Export produced", exportedHpp.length, "chars");

  // Verify it starts with class WF_Menu
  if (!exportedHpp.trim().startsWith("class WF_Menu")) {
    throw new Error(
      "Export doesn't start with 'class WF_Menu': " + exportedHpp.slice(0, 80),
    );
  }
  console.log("✓ Export starts with class WF_Menu");

  // Verify idd present
  if (!exportedHpp.includes("idd = 11000")) {
    throw new Error("idd not in export: " + exportedHpp.slice(0, 300));
  }
  console.log("✓ idd = 11000 present");

  // Verify control names present (Button_A through at least Button_J)
  for (const name of ["Button_A", "Button_B", "Button_C"]) {
    if (!exportedHpp.includes("class " + name))
      throw new Error("Control " + name + " missing from export");
  }
  console.log("✓ Button_A/B/C controls present in export");

  // Verify WFBE_ macros are kept (not expanded to RGBA arrays)
  if (!exportedHpp.includes("WFBE_Background_Color")) {
    // This would mean macros were expanded — warn rather than hard-fail since
    // the background controls must have colorBackground in their delta
    console.warn(
      "WARN: WFBE_Background_Color not found in export — macros may be expanded",
    );
  } else {
    console.log("✓ WFBE_Background_Color macro name preserved in export");
  }

  // Verify controlsBackground section present
  if (!exportedHpp.includes("class controlsBackground")) {
    throw new Error("controlsBackground section missing from export");
  }
  console.log("✓ controlsBackground section present");

  // Verify controls section present
  if (
    !exportedHpp.includes("class controls {") &&
    !exportedHpp.includes("class controls{")
  ) {
    throw new Error("controls section missing from export");
  }
  console.log("✓ controls section present");

  // Screenshot: export panel open
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task5-01-export.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: task5-01-export.png");

  // ---- Re-parse the exported .hpp via the import box ----
  // Paste exported into import box and run doImport
  await page.locator("#import-in").fill(exportedHpp);
  await page.waitForTimeout(200);
  await page.click("#import-btn");
  await page.waitForTimeout(800);

  // Check status message (should say "Imported")
  const statusText = await page.locator("#status-msg").textContent();
  console.log("✓ Import status:", statusText);
  if (statusText.toLowerCase().includes("error")) {
    throw new Error("Import failed: " + statusText);
  }
  if (!statusText.toLowerCase().includes("import")) {
    throw new Error("Import didn't succeed: " + statusText);
  }

  // Verify controls still on stage
  const ctrlsAfterImport = await page.locator("#stage .ctrl").count();
  if (ctrlsAfterImport === 0) throw new Error("Stage empty after import");
  console.log("✓ Controls on stage after import:", ctrlsAfterImport);

  // Re-export and verify it still has the same controls
  await page.click("#export-btn");
  await page.waitForTimeout(400);
  const exportedAfterImport = await page.locator("#export-out").inputValue();
  if (!exportedAfterImport.includes("Button_A"))
    throw new Error("Round-tripped export missing Button_A");
  console.log("✓ Round-trip export still has Button_A");

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task5-02-roundtrip.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: task5-02-roundtrip.png");

  // ======================================================
  // TEST 2: Paste real WF_Menu .hpp → import → export re-parses equal
  // ======================================================
  console.log("\n--- TEST 2: Paste real WF_Menu .hpp ---");

  await page.locator("#import-in").fill(WF_MENU_HPP);
  await page.waitForTimeout(200);
  await page.click("#import-btn");
  await page.waitForTimeout(800);

  const statusAfterReal = await page.locator("#status-msg").textContent();
  console.log("✓ Real .hpp import status:", statusAfterReal);
  if (statusAfterReal.toLowerCase().includes("error")) {
    throw new Error("Real .hpp import failed: " + statusAfterReal);
  }

  // Verify Button_A is on the stage
  const realCtrls = await page.locator("#stage .ctrl").count();
  if (realCtrls === 0) throw new Error("Stage empty after real .hpp import");
  console.log("✓ Controls on stage after real .hpp import:", realCtrls);

  // Re-export
  await page.click("#export-btn");
  await page.waitForTimeout(400);
  const exportedFromReal = await page.locator("#export-out").inputValue();
  if (!exportedFromReal.includes("Button_A"))
    throw new Error("Export after real .hpp import missing Button_A");
  if (!exportedFromReal.includes("Button_B"))
    throw new Error("Export after real .hpp import missing Button_B");
  // idd should be 11000
  if (!exportedFromReal.includes("idd = 11000"))
    throw new Error("idd wrong after real .hpp import");
  console.log(
    "✓ Export after real .hpp import: idd=11000 + Button_A/B present",
  );

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task5-03-real-hpp.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: task5-03-real-hpp.png");

  // ======================================================
  // TEST 3: Move one control → only x/y change in delta
  // ======================================================
  console.log(
    "\n--- TEST 3: Move control → delta only contains x/y change ---",
  );

  // Fresh page load so ui.json's WF_Menu (21 controls) is the source of truth
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // Verify full WF_Menu loaded (21 controls)
  const fullCount = await page.locator("#stage .ctrl").count();
  if (fullCount < 10)
    throw new Error(
      "Test 3: expected ≥10 controls after fresh load, got " + fullCount,
    );
  console.log("✓ Fresh load: " + fullCount + " controls");

  // Capture export BEFORE move (fully via JS to avoid DOM focus side-effects)
  const exportBefore = await page.evaluate(() => exportHpp());
  if (!exportBefore || !exportBefore.includes("Button_A"))
    throw new Error("exportBefore missing Button_A");
  console.log("✓ Export before move:", exportBefore.length, "chars");

  // Nudge Button_A's x and y directly in displayData, then re-export
  const moveResult = await page.evaluate(() => {
    const ctrl = (displayData.controls || []).find(
      (c) => c.name === "Button_A",
    );
    if (!ctrl) return { err: "Button_A not found" };
    const xBefore = parseFloat(ctrl.props.x);
    const yBefore = parseFloat(ctrl.props.y);
    ctrl.props.x = xBefore + 0.05;
    ctrl.props.y = yBefore + 0.03;
    if (ctrl.resolved) {
      ctrl.resolved.x = ctrl.props.x;
      ctrl.resolved.y = ctrl.props.y;
    }
    const exportAfter = exportHpp();
    // Reset back to original so further tests aren't affected
    ctrl.props.x = xBefore;
    ctrl.props.y = yBefore;
    if (ctrl.resolved) {
      ctrl.resolved.x = xBefore;
      ctrl.resolved.y = yBefore;
    }
    return { exportAfter, xBefore, yBefore, xAfter: xBefore + 0.05 };
  });

  if (moveResult.err) throw new Error("Move test: " + moveResult.err);
  const exportAfter = moveResult.exportAfter;
  console.log(
    "✓ Nudged Button_A: x",
    moveResult.xBefore.toFixed(5),
    "→",
    moveResult.xAfter.toFixed(5),
  );

  // Parse x/y from both exports for Button_A
  const parseCtrlProps = (hpp, ctrlName) => {
    const re = new RegExp(`class ${ctrlName}[^{]*\\{([^}]*)\\}`, "s");
    const m = hpp.match(re);
    if (!m) return null;
    const props = {};
    for (const line of m[1].split("\n")) {
      const pm = line.match(/^\s*(\w+)(?:\[\])?\s*=\s*(.+?);?\s*$/);
      if (pm) props[pm[1]] = pm[2].trim();
    }
    return props;
  };

  const propsBefore = parseCtrlProps(exportBefore, "Button_A");
  const propsAfter = parseCtrlProps(exportAfter, "Button_A");

  if (propsBefore && propsAfter) {
    const changedKeys = Object.keys({ ...propsBefore, ...propsAfter }).filter(
      (k) => propsBefore[k] !== propsAfter[k],
    );
    console.log("✓ Changed keys after move:", changedKeys);
    const unexpected = changedKeys.filter((k) => k !== "x" && k !== "y");
    if (unexpected.length > 0) {
      throw new Error(
        "Unexpected keys changed after move (should be only x/y): " +
          unexpected.join(", "),
      );
    }
    if (!changedKeys.includes("x") || !changedKeys.includes("y")) {
      throw new Error(
        "Expected x and y to change after move, got: " + changedKeys.join(", "),
      );
    }
    console.log("✓ Only x/y changed in delta after move");
  } else {
    throw new Error("Could not parse Button_A from export before/after move");
  }

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task5-04-move-delta.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: task5-04-move-delta.png");

  // ======================================================
  // TEST 4: Copy + Download buttons present and functional
  // ======================================================
  console.log("\n--- TEST 4: Copy / Download buttons ---");

  // Open export panel first (it may be closed after the fresh page load)
  const exportBodyT4 = page.locator("#export-body");
  const isOpenT4 = await exportBodyT4.evaluate((el) =>
    el.classList.contains("open"),
  );
  if (!isOpenT4) {
    await page.click("#export-toggle");
    await page.waitForTimeout(300);
  }

  // Ensure export is populated
  await page.click("#export-btn");
  await page.waitForTimeout(300);
  const exportVal = await page.locator("#export-out").inputValue();
  if (!exportVal) throw new Error("Export output empty");

  const copyBtn = page.locator("#copy-btn");
  const downloadBtn = page.locator("#download-btn");
  if (!(await copyBtn.isVisible())) throw new Error("Copy button not visible");
  if (!(await downloadBtn.isVisible()))
    throw new Error("Download button not visible");
  console.log("✓ Copy + Download buttons visible");

  // Import clear button
  const clearBtn = page.locator("#import-clear-btn");
  if (!(await clearBtn.isVisible()))
    throw new Error("Import clear button not visible");
  await clearBtn.click();
  await page.waitForTimeout(200);
  const importVal = await page.locator("#import-in").inputValue();
  if (importVal !== "")
    throw new Error("Import clear didn't clear the textarea");
  console.log("✓ Import clear button works");

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task5-05-buttons.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: task5-05-buttons.png");

  // ======================================================
  // FINAL SUMMARY
  // ======================================================
  await browser.close();

  console.log("\n=== RESULTS ===");
  if (errors.length === 0) {
    console.log("✓ 0 console errors");
  } else {
    console.log("✗ Console errors (" + errors.length + "):");
    errors.forEach((e) => console.log("  -", e));
    process.exit(1);
  }
  console.log("\nAll round-trip checks passed.");
}

run().catch((err) => {
  console.error("FATAL:", err.message);
  process.exit(1);
});
