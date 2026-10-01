// Load check and screenshots of the GTA V sites built by v/build_v_sites.py.
//
// Opens every site of <base>/_sites.json in Chrome (puppeteer-core), one fresh browser per
// site with a single page (headless background tabs get no animation frames and Ruffle
// stops), waits until the in-game browser shows that site, and writes:
//   <out>/<domain>.png            the whole window (address bar + player + notes)
//   <out>/viewport/<domain>.png   the player only (python v/build_v_sites.py --stages thumbs,index)
//   <out>/manifest.json           [{domain, url, loaded, pageready, consoleErrors, httpErrors, ...}]
//
// "Loaded" = the in-game browser navigated to that domain, the host reported pageready, it
// did not end on eyefind's error page and the "loading" banner is gone. A failed site is
// retried once in a new browser.
//
//   node v/shoot/shoot.mjs --base http://127.0.0.1:8044/v --out shots
//        [--version 2013]   load the other version (?version=2013) of the sites that have two;
//                           the output goes to <out>/v2013/
//        [--only a,b]       only the domains that contain one of these texts
//        [--jobs 3]         browsers at the same time
//        [--settle 4000]    ms to wait after pageready (late textures and texts)
//        [--chrome PATH]    Chrome/Chromium/Edge (default: CHROME_PATH or the usual places)
//
// Exit code: 0 all loaded, 1 some failed, 2 bad arguments / server not reachable, 3 no Chrome.
// Needs Node.js 18+ and puppeteer-core (npm install at the repository root).
import fs from 'node:fs';
import path from 'node:path';

function parseArgs(argv) {
  const a = { jobs: 3, settle: 4000, timeout: 150000, only: '', version: '' };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--base') a.base = v().replace(/\/$/, '');
    else if (k === '--out') a.out = v();
    else if (k === '--version') a.version = v();
    else if (k === '--only') a.only = v();
    else if (k === '--jobs') a.jobs = Math.max(1, +v());
    else if (k === '--settle') a.settle = +v();
    else if (k === '--timeout') a.timeout = +v();
    else if (k === '--chrome') a.chrome = v();
    else if (k === '--help' || k === '-h') a.help = true;
    else { console.error('unknown argument: ' + k); process.exit(2); }
  }
  return a;
}

function findChrome(explicit) {
  const cands = [explicit, process.env.CHROME_PATH];
  if (process.platform === 'win32') {
    for (const root of [process.env.PROGRAMFILES, process.env['PROGRAMFILES(X86)'], process.env.LOCALAPPDATA]) {
      if (!root) continue;
      cands.push(path.join(root, 'Google/Chrome/Application/chrome.exe'),
        path.join(root, 'Chromium/Application/chrome.exe'),
        path.join(root, 'Microsoft/Edge/Application/msedge.exe'));
    }
  } else if (process.platform === 'darwin') {
    cands.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  } else {
    cands.push('/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium',
      '/usr/bin/chromium-browser', '/snap/bin/chromium', '/usr/bin/microsoft-edge');
  }
  return cands.find(c => c && fs.existsSync(c));
}

const A = parseArgs(process.argv.slice(2));
if (A.help || !A.base || !A.out) {
  console.log('usage: node v/shoot/shoot.mjs --base http://127.0.0.1:8044/v --out DIR '
    + '[--version 2013] [--only a,b] [--jobs 3] [--settle 4000] [--chrome PATH]');
  process.exit(A.help ? 0 : 2);
}
const CHROME = findChrome(A.chrome);
if (!CHROME) {
  console.error('no Chrome/Chromium/Edge found: pass --chrome or set CHROME_PATH');
  process.exit(3);
}
let puppeteer;
try {
  puppeteer = (await import('puppeteer-core')).default;
} catch (e) {
  console.error('puppeteer-core is not installed: run "npm install" at the repository root');
  process.exit(2);
}

const ORIGIN = new URL(A.base).origin;
const OUT = A.version ? path.join(A.out, 'v' + A.version) : A.out;
const VP_OUT = path.join(OUT, 'viewport');
fs.mkdirSync(VP_OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

let sitesJson;
try {
  const r = await fetch(`${A.base}/_sites.json`);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  sitesJson = await r.json();
} catch (e) {
  console.error(`cannot read ${A.base}/_sites.json (${e.message}): is the server running?`);
  process.exit(2);
}
const SITES = sitesJson.story
  .filter(s => !A.version || (s.versions && s.versions[1] === A.version))
  .map(s => s.domain)
  .filter(d => !A.only || A.only.split(',').some(f => d.includes(f)))
  .sort();

const launch = () => puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  timeout: 180000,
  protocolTimeout: 240000,
  args: ['--autoplay-policy=no-user-gesture-required', '--mute-audio', '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'],
});
// two new frames: the screenshot shows what Ruffle paints now
const freshFrames = page => page.evaluate(() => new Promise(r =>
  requestAnimationFrame(() => requestAnimationFrame(() => r(document.visibilityState)))));

async function attempt(browser, domain) {
  const url = `${A.base}/${domain}/index.html` + (A.version ? `?version=${A.version}` : '');
  const page = await browser.newPage();
  for (const p of await browser.pages()) if (p !== page) await p.close().catch(() => {});
  await page.bringToFront();
  // 1312 = 1280 + 2 * 16 px of margin around the player
  await page.setViewport({ width: 1312, height: 800 });
  const consoleErrors = [], httpErrors = [];
  // the browser asks for /favicon.ico on its own; a server without one is not a page error
  const favicon = u => /\/favicon\.ico(\?|$)/.test(u || '');
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + String(e.message || e).slice(0, 300)));
  page.on('console', m => {
    if (m.type() !== 'error' || favicon(m.location() && m.location().url)) return;
    const loc = m.location() && m.location().url ? ' [' + m.location().url.replace(ORIGIN, '') + ']' : '';
    consoleErrors.push((m.text() + loc).slice(0, 400));
  });
  page.on('requestfailed', r => {
    const f = r.failure() && r.failure().errorText;
    if (f && f !== 'net::ERR_ABORTED') consoleErrors.push('requestfailed: ' + r.url().replace(ORIGIN, '') + ' ' + f);
  });
  page.on('response', r => { if (r.status() >= 400 && !favicon(r.url())) httpErrors.push(r.status() + ' ' + r.url().replace(ORIGIN, '')); });
  const t0 = Date.now();
  const rec = { domain, url, version: A.version || undefined, loaded: false };
  try {
    await page.goto(url, { waitUntil: 'load', timeout: A.timeout });
    // wait for pageready of a page that is not the error page, or for the error page to stay
    // 25 s (the host retries once when it lands there), or the time limit
    let errorSince = 0;
    while (Date.now() - t0 < A.timeout) {
      const st = await page.evaluate(() => {
        const h = window.gtavHost;
        if (!h || !h.log) return { host: false };
        const ready = h.log.filter(r => r.name === 'pageready');
        return { host: true, readyUrl: ready.length ? String(ready[ready.length - 1].args[0]) : null,
          fullURL: h.state && h.state.fullURL };
      });
      if (st.readyUrl && !/ERROR/.test(st.readyUrl) && !/ERROR/.test(st.fullURL || '')) break;
      if (/ERROR/.test(st.fullURL || '')) {
        if (!errorSince) errorSince = Date.now();
        else if (Date.now() - errorSince > 25000) break;
      } else errorSince = 0;
      await sleep(400);
    }
    rec.readyMs = Date.now() - t0;
    await sleep(A.settle);
    const fin = await page.evaluate(() => {
      const h = window.gtavHost;
      if (!h) return { host: false };
      const nav = h.log.filter(r => r.kind === 'event' && r.name === 'navigate');
      const s = document.getElementById('status');
      const note = document.getElementById('note');
      return {
        host: true,
        address: nav.length ? String(nav[nav.length - 1].args[0]) : null,
        pageready: h.log.some(r => r.name === 'pageready'),
        fullURL: h.state && h.state.fullURL,
        banner: s && s.classList.contains('on') ? s.textContent : null,
        note: note && !note.hidden ? note.textContent : null,
        missingLabels: [...(h.missing || [])],
        title: document.title,
      };
    });
    rec.address = fin.address;
    rec.pageready = !!fin.pageready;
    rec.errorPage = /ERROR/.test(fin.fullURL || '');
    rec.bannerStuck = fin.banner || null;
    rec.note = fin.note;
    rec.missingLabels = fin.missingLabels;
    rec.title = fin.title;
    const onSite = !!fin.address && fin.address.toLowerCase().startsWith(domain.toLowerCase());
    rec.loaded = !!fin.host && onSite && rec.pageready && !rec.errorPage && !rec.bannerStuck;
    if (!rec.loaded) {
      rec.failReason = !fin.host ? 'no host' : rec.errorPage ? 'eyefind error page'
        : !onSite ? 'the browser did not reach the site (address: ' + fin.address + ')'
          : !rec.pageready ? 'no pageready in ' + A.timeout / 1000 + ' s' : 'banner still shown: ' + rec.bannerStuck;
    }
    await page.bringToFront();
    rec.visibility = await Promise.race([freshFrames(page), sleep(15000).then(() => 'no frames in 15 s')]);
    rec.shot = path.join(OUT, domain + '.png');
    await page.screenshot({ path: rec.shot });
    const vp = await page.$('#viewport');
    if (vp) await vp.screenshot({ path: path.join(VP_OUT, domain + '.png') });
  } catch (e) {
    rec.failReason = 'probe: ' + String(e.message || e).slice(0, 300);
    try { rec.shot = path.join(OUT, domain + '.png'); await page.screenshot({ path: rec.shot }); } catch (e2) { /* */ }
  }
  rec.totalMs = Date.now() - t0;
  rec.consoleErrors = [...new Set(consoleErrors)];
  rec.httpErrors = [...new Set(httpErrors)];
  try { await page.close(); } catch (e) { /* */ }
  return rec;
}

async function fresh(domain) {
  const browser = await launch();
  try { return await attempt(browser, domain); } finally { await browser.close().catch(() => {}); }
}

async function probe(domain) {
  const first = await fresh(domain);
  if (first.loaded) return { ...first, attempts: 1 };
  console.log(`  retry ${domain}: ${first.failReason}`);
  const second = await fresh(domain);
  return { ...second, attempts: 2, firstAttempt: { failReason: first.failReason, consoleErrors: first.consoleErrors } };
}

const queue = SITES.slice();
const results = [];
async function worker() {
  while (queue.length) {
    const d = queue.shift();
    const r = await probe(d);
    results.push(r);
    console.log(`${String(results.length).padStart(2)}/${SITES.length} ${r.loaded ? 'OK  ' : 'FAIL'} ${d.padEnd(40)} `
      + `ready ${String(r.readyMs).padStart(6)} ms${r.attempts > 1 ? ' (2nd attempt)' : ''}`
      + `${r.consoleErrors.length ? ' console=' + r.consoleErrors.length : ''}`
      + `${r.httpErrors.length ? ' http=' + r.httpErrors.join(',') : ''}${r.failReason ? ' REASON=' + r.failReason : ''}`);
  }
}
const tStart = Date.now();
await Promise.all(Array.from({ length: Math.min(A.jobs, SITES.length || 1) }, worker));

const manifestPath = path.join(OUT, 'manifest.json');
let merged = results;
if (A.only && fs.existsSync(manifestPath)) {       // a partial run updates the previous manifest
  const byDom = Object.fromEntries(JSON.parse(fs.readFileSync(manifestPath, 'utf8')).map(r => [r.domain, r]));
  results.forEach(r => { byDom[r.domain] = r; });
  merged = Object.values(byDom);
}
merged.sort((a, b) => a.domain.localeCompare(b.domain));
fs.writeFileSync(manifestPath, JSON.stringify(merged, null, 1));
const failed = merged.filter(r => !r.loaded);
console.log(`\n${merged.length - failed.length}/${merged.length} loaded in ${Math.round((Date.now() - tStart) / 1000)} s; `
  + `failed: ${failed.map(r => r.domain + ' (' + r.failReason + ')').join('; ') || 'none'}; `
  + `with console errors: ${merged.filter(r => r.consoleErrors.length).map(r => r.domain).join(', ') || 'none'}`);
console.log('manifest: ' + manifestPath);
process.exit(failed.length ? 1 : 0);
