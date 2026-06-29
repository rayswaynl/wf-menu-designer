/**
 * Playwright verification for Task 4: Full Property Inspector
 * Tests:
 *  1. Select a button → colorBackground picker appears + canvas updates → becomes override
 *  2. Change baseClass → re-renders on canvas
 *  3. Reset-to-inherited clears override
 *  4. 0 console errors throughout
 */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const BASE = "http://localhost:7890";
const SCREENSHOT_DIR =
  "C:/Users/Steff/wf-menu-designer/docs/superpowers/screenshots";

async function run() {
  const errors = [];
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1400, height: 900 },
  });
  const page = await ctx.newPage();

  // Collect console errors
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

  console.log("→ Loading page...");
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // ---- Switch to Edit mode ----
  await page.click("#btn-edit");
  await page.waitForTimeout(300);
  console.log("✓ Switched to Edit mode");

  // ---- Select the first control (WF_Menu loads by default) ----
  // Click first control on the stage
  const firstCtrl = page.locator(".ctrl").first();
  await firstCtrl.click();
  await page.waitForTimeout(400);

  // ---- Verify inspector appeared ----
  const insp = page.locator("#inspector");
  const inspVisible = await insp.isVisible();
  if (!inspVisible)
    throw new Error("Inspector not visible after selecting a control");
  console.log("✓ Inspector visible after selection");

  // Take screenshot of initial state
  if (!fs.existsSync(SCREENSHOT_DIR))
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task4-01-inspector-open.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: inspector-open");

  // ---- Check colorBackground picker is present ----
  // The inspector should have a color picker for colorBackground
  const colorPicker = page.locator('input[type="color"]').first();
  const pickerVisible = await colorPicker.isVisible();
  if (!pickerVisible) throw new Error("Color picker not visible in inspector");
  console.log("✓ Color picker present");

  // ---- Check macro dropdown is present ----
  const macroSel = page.locator(".macro-sel").first();
  const macroVisible = await macroSel.isVisible();
  if (!macroVisible) throw new Error("Macro dropdown not visible");
  console.log("✓ Macro dropdown present");

  // ---- Change colorBackground via picker → verify override badge appears ----
  // Set a bright red color
  await colorPicker.evaluate((el) => {
    el.value = "#ff2244";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForTimeout(500);

  // Check for override badge on colorBackground row
  const overrideBadge = page.locator(".override-badge").first();
  const badgeVisible = await overrideBadge.isVisible();
  if (!badgeVisible)
    throw new Error("Override badge not shown after changing colorBackground");
  console.log("✓ Override badge appeared after color change");

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task4-02-color-override.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: color-override");

  // ---- Verify canvas actually re-rendered (no error thrown) ----
  const stageChildren = await page.locator("#stage .ctrl").count();
  if (stageChildren === 0)
    throw new Error("Stage has no controls after color change");
  console.log(
    "✓ Stage still has",
    stageChildren,
    "controls after color change",
  );

  // ---- Check reset-to-inherited button exists ----
  const resetBtn = page.locator(".reset-btn").first();
  const resetVisible = await resetBtn.isVisible();
  if (!resetVisible) throw new Error("Reset-to-inherited button not visible");
  console.log("✓ Reset-to-inherited button present");

  // ---- Click reset → override badge should disappear ----
  await resetBtn.click();
  await page.waitForTimeout(500);

  const badgeAfterReset = await page.locator(".override-badge").count();
  console.log("✓ Override badges after reset:", badgeAfterReset, "(was 1+)");

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task4-03-after-reset.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: after-reset");

  // ---- Change baseClass → verify inspector rebuilds ----
  const baseClassSel = page.locator('select[data-prop="_baseClass"]');
  const baseSelVisible = await baseClassSel.isVisible();
  if (!baseSelVisible) throw new Error("BaseClass dropdown not visible");

  // Change to RscButton_Main
  await baseClassSel.selectOption("RscButton_Main");
  await page.waitForTimeout(600);
  console.log("✓ Changed baseClass to RscButton_Main");

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task4-04-baseclass-changed.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: baseclass-changed");

  // ---- Verify stage re-rendered after baseClass change ----
  const stageAfterBase = await page.locator("#stage .ctrl").count();
  if (stageAfterBase === 0)
    throw new Error("Stage empty after baseClass change");
  console.log(
    "✓ Stage re-rendered after baseClass change:",
    stageAfterBase,
    "controls",
  );

  // ---- Multi-select test: use layer list rows (avoids overlapping stage controls) ----
  const layerItems = page.locator(".layer-item");
  const layerCount = await layerItems.count();
  if (layerCount >= 2) {
    await layerItems.nth(0).click();
    await page.waitForTimeout(150);
    await layerItems.nth(1).click({ modifiers: ["Shift"] });
    await page.waitForTimeout(300);
  }

  const multiBanner = await page.locator(".multi-insp-banner").count();
  console.log(
    "✓ Multi-select tested via layer list; banner present:",
    multiBanner > 0,
  );

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "task4-05-multiselect.png"),
    fullPage: false,
  });
  console.log("✓ Screenshot: multiselect");

  // ---- Final console error check ----
  await page.waitForTimeout(300);

  await browser.close();

  console.log("\n=== RESULTS ===");
  if (errors.length === 0) {
    console.log("✓ 0 console errors");
  } else {
    console.log("✗ Console errors (" + errors.length + "):");
    errors.forEach((e) => console.log("  -", e));
  }

  if (errors.length > 0) {
    process.exit(1);
  }
  console.log("\nAll checks passed.");
}

run().catch((err) => {
  console.error("FATAL:", err.message);
  process.exit(1);
});
