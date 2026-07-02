/**
 * Screenshot tool — takes a 1440×900 screenshot of the WF Menu Designer.
 * Spins up a tiny static HTTP server (port 19876) to serve the project root
 * so that fetch('assets/data/ui.json') works under Chromium.
 * Usage: node tools/take-screenshot.js
 */
const { chromium } = require("playwright");
const http = require("http");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const PORT = 19876;

// Minimal static file server
const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".css": "text/css",
};

function serve(req, res) {
  const filePath = path.join(ROOT, req.url === "/" ? "index.html" : req.url);
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("Not found: " + req.url);
      return;
    }
    const ext = path.extname(filePath);
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream",
    });
    res.end(data);
  });
}

(async () => {
  const server = http.createServer(serve);
  await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));
  console.log("Static server on http://127.0.0.1:" + PORT);

  const errors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("http://127.0.0.1:" + PORT + "/");

  // Wait for ui.json to load and display picker to populate
  await page.waitForFunction(
    () => {
      const sel = document.getElementById("display-picker");
      return sel && sel.options.length > 1;
    },
    { timeout: 10000 },
  );

  // Load the first real display so the canvas is visible
  await page.evaluate(() => {
    const sel = document.getElementById("display-picker");
    for (const opt of sel.options) {
      if (opt.value) {
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change"));
        break;
      }
    }
  });

  // Wait for staggered load + controls to render
  await page.waitForTimeout(600);

  const outPath = path.resolve(
    __dirname,
    "..",
    "docs",
    "screenshots",
    "overhaul-2026-07-02.png",
  );
  await page.screenshot({ path: outPath, fullPage: false });
  await browser.close();
  server.close();

  console.log("Screenshot saved to:", outPath);
  if (errors.length) {
    console.error("Console errors during screenshot:", errors);
    process.exit(1);
  } else {
    console.log("No console errors.");
  }
})();
