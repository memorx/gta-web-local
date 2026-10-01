// Visual/functional probe for GTA Web Local.
// Opens every page through a running server and reports, per page:
//   - failed requests (images, css, fonts, SWF) with their status
//   - <img> that did not load
//   - raw text keys (EYE_HOME_3...) left visible (GTA IV)
//   - script slots (.scriptobj) left empty (GTA IV fill layer)
//   - console errors / exceptions
// and saves a screenshot per page.
//
// Usage:
//   node tests/probe.mjs --base http://127.0.0.1:8044 --out <build out dir> --report <dir>
//                        [--iv] [--classic] [--states tests/iv_states.txt] [--list file]
//                        [--filter text] [--workers 6] [--chrome path/to/chrome]
//
//   --iv        every page under <out>/iv/<GTAIV|TBoGT|TLAD>/pc/html (served at /r0 /r1 /r2)
//   --classic   every HTML page under <out>/classic/<III|VC|SA> (served at /iii /vc /sa)
//   --states    extra URLs, one per line: "EP|path?query" (GTA IV page with parameters)
//               or "RAW|/absolute/path" (any URL of the server)
//   --list      same format as --states
// Writes <report>/report.json and one PNG per page. Needs puppeteer-core (npm install)
// and a Chrome/Chromium/Edge install (auto-detected, or --chrome / CHROME_PATH).
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const a = { workers: 6, lists: [] };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === "--base") a.base = v().replace(/\/$/, "");
    else if (k === "--out") a.out = v();
    else if (k === "--report") a.report = v();
    else if (k === "--iv") a.iv = true;
    else if (k === "--classic") a.classic = true;
    else if (k === "--states" || k === "--list") a.lists.push(v());
    else if (k === "--filter") a.filter = v();
    else if (k === "--workers") a.workers = +v();
    else if (k === "--chrome") a.chrome = v();
    else if (k === "--help" || k === "-h") a.help = true;
    else throw new Error(`unknown argument ${k}`);
  }
  return a;
}

const args = parseArgs(process.argv.slice(2));
if (args.help || !args.base || !args.report || ((args.iv || args.classic) && !args.out)) {
  console.log(fs.readFileSync(new URL(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 1);
}

const IV_ROOTS = { GTAIV: 0, TBoGT: 1, TLAD: 2 }; // the server numbers the roots in name order
const CLASSIC_EXT = [".html", ".htm", ".shtml", ".asp", ".php", ".cgi", ".cfm", ".jsp"];

function walk(dir, visit, skip) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((x, y) => (x.name < y.name ? -1 : 1))) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (!skip(e.name)) walk(p, visit, skip);
    } else visit(p, e.name);
  }
}

function listPages() {
  const pages = [];
  if (args.iv) {
    for (const [ep, r] of Object.entries(IV_ROOTS)) {
      const root = path.join(args.out, "iv", ep, "pc", "html");
      if (!fs.existsSync(root)) continue;
      walk(root, (p, name) => {
        if (!name.endsWith(".html")) return;
        const rel = path.relative(root, p).split(path.sep).join("/");
        pages.push({ page: `${ep}/${rel}`, url: `${args.base}/r${r}/${rel}` });
      }, (name) => name.startsWith("_") || name === "ttf");
    }
  }
  if (args.classic) {
    for (const game of ["III", "VC", "SA"]) {
      const root = path.join(args.out, "classic", game);
      if (!fs.existsSync(root)) continue;
      walk(root, (p, name) => {
        if (!CLASSIC_EXT.includes(path.extname(name).toLowerCase())) return;
        const rel = path.relative(root, p).split(path.sep).join("/");
        pages.push({ page: `${game.toLowerCase()}/${rel}`, url: `${args.base}/${game.toLowerCase()}/${rel}` });
      }, (name) => name === "_raw" || name === "_manifest");
    }
  }
  for (const f of args.lists) {
    for (const line of fs.readFileSync(f, "utf8").split(/\r?\n/)) {
      const [ep, rel] = line.trim().split("|");
      if (!ep || !rel) continue;
      if (IV_ROOTS[ep] !== undefined) pages.push({ page: `${ep}/${rel}`, url: `${args.base}/r${IV_ROOTS[ep]}/${rel}` });
      else if (ep === "RAW") pages.push({ page: rel.replace(/^\//, ""), url: `${args.base}${rel}` });
    }
  }
  return args.filter ? pages.filter((p) => p.page.includes(args.filter)) : pages;
}

function findChrome() {
  const cands = [args.chrome, process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"];
  const hit = cands.find((c) => c && fs.existsSync(c));
  if (!hit) throw new Error("Chrome/Chromium not found: pass --chrome <path> or set CHROME_PATH");
  return hit;
}

const pages = listPages();
fs.mkdirSync(args.report, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: findChrome(),
  headless: true,
  // the workers' tabs are all in the background: without these flags Chrome throttles them
  // and a screenshot of a Flash page can wait minutes for a frame
  args: ["--no-first-run", "--disable-extensions", "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"],
  timeout: 180000,          // on a loaded machine Chrome is slow to start
  protocolTimeout: 240000,  // screenshots of heavy Flash pages
});

const results = [];
let next = 0;
// Screenshots are taken one at a time, with the tab in front: when several background
// tabs ask for one at once, Chrome can stall all of them for minutes.
let shotLock = Promise.resolve();
function exclusive(fn) {
  const run = shotLock.then(fn, fn);
  shotLock = run.catch(() => {});
  return run;
}
async function worker() {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  while (next < pages.length) {
    const p = pages[next++];
    const rec = { page: p.page, url: p.url, failed: [], console: [], brokenImg: [], rawKeys: [], emptySlots: [] };
    const strip = (u) => decodeURIComponent(u.replace(args.base, ""));
    const onResp = (r) => { if (r.status() >= 400) rec.failed.push(`${r.status()} ${strip(r.url())}`); };
    const onFail = (r) => rec.failed.push(`ERR ${strip(r.url())}`);
    const onCon = (m) => { if (m.type() === "error") rec.console.push(m.text()); };
    const onErr = (e) => rec.console.push("EXC " + e.message);
    page.on("response", onResp); page.on("requestfailed", onFail); page.on("console", onCon); page.on("pageerror", onErr);
    try {
      await page.goto(p.url, { waitUntil: "networkidle0", timeout: 45000 });
      // with Flash, Ruffle takes a while to load the wasm and the SWF
      const hasFlash = await page.evaluate(() => !!(window.RufflePlayer || document.querySelector("embed,object")));
      await new Promise((r) => setTimeout(r, hasFlash ? 4000 : 150));
      rec.flash = hasFlash;
      Object.assign(rec, await page.evaluate(() => {
        const brokenImg = [...document.images].filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.getAttribute("src"));
        const rawKeys = [];
        const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const keyRe = /^[A-Z][A-Z0-9]*_[A-Z0-9_]+$/;
        while (tw.nextNode()) { const t = tw.currentNode.nodeValue.trim(); if (keyRe.test(t)) rawKeys.push(t); }
        const emptySlots = [...document.querySelectorAll(".scriptobj:not(.lw-empty-ok)")].filter((e) => !e.textContent.trim() && !e.querySelector("img,table,div,a,textarea,button")).map((e) => e.dataset.name);
        return { brokenImg, rawKeys, emptySlots, height: document.documentElement.scrollHeight };
      }));
      const shot = path.join(args.report, rec.page.replace(/[\/:?&=*"<>|]/g, "__") + ".png");
      await exclusive(async () => {
        await page.bringToFront();
        await page.screenshot({ path: shot, clip: { x: 0, y: 0, width: 1280, height: Math.min(Math.max(rec.height || 900, 900), 3000) } });
      });
      rec.shot = shot;
    } catch (e) {
      rec.console.push("NAV " + e.message);
    }
    page.off("response", onResp); page.off("requestfailed", onFail); page.off("console", onCon); page.off("pageerror", onErr);
    results.push(rec);
    if (results.length % 50 === 0) console.error(`${results.length}/${pages.length}`);
  }
  await page.close();
}

await Promise.all(Array.from({ length: Math.max(1, args.workers) }, worker));
await browser.close();
results.sort((a, b) => a.page.localeCompare(b.page));
fs.writeFileSync(path.join(args.report, "report.json"), JSON.stringify(results, null, 1));
const bad = results.filter((r) => r.failed.length || r.brokenImg.length || r.rawKeys.length || r.emptySlots.length || r.console.length);
console.log(`pages: ${results.length} · with problems: ${bad.length}`);
const tally = (k) => results.reduce((n, r) => n + r[k].length, 0);
console.log(`failed requests: ${tally("failed")} · broken images: ${tally("brokenImg")} · raw keys: ${tally("rawKeys")} · empty slots: ${tally("emptySlots")} · console errors: ${tally("console")}`);
