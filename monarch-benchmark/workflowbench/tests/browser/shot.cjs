// One page of the Studio, as a picture and as measured facts (feature 023, the weekly adversary).
//
//   node tests/browser/shot.cjs --base http://127.0.0.1:8766 --view runs --theme light \
//        --out .../shots [--selector "#history-rows"]
//
// Writes <out>/<view>-<theme>.png and prints one JSON line: where the file is, the page errors, and
// a layout record the critic cannot argue with — overflow, the smallest text, contrast on the ink
// pairs, the widest table. A crop is taken as well when --selector names one, because a full page
// at 1440px will not show a critic that a padding changed.
//
// This is deliberately not part of suite.cjs: that writes the review snapshots, and the critic must
// never overwrite them.
'use strict';
const path = require('node:path');
const fs = require('node:fs');

const arg = (name, fallback) => { const i = process.argv.indexOf('--' + name); return i > 0 ? process.argv[i + 1] : fallback; };
const BASE = arg('base', 'http://127.0.0.1:8766');
const VIEW = arg('view', 'runs');
const THEME = arg('theme', 'light');
const OUT = arg('out', path.join(__dirname, 'shots'));
const SELECTOR = arg('selector', null);
const HASH = arg('hash', '#' + VIEW);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, 'playwright',
    'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) { try { return require(c); } catch { /* next */ } }
  throw new Error('Playwright not found. Set PLAYWRIGHT_MODULE to its node_modules path.');
}

// Relative luminance and contrast, the WCAG definitions, so the number is the standard one.
const MEASURE = () => {
  const parse = c => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  const lum = rgb => {
    const [r, g, b] = rgb.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const behind = el => {
    for (let node = el; node; node = node.parentElement) {
      const c = getComputedStyle(node).backgroundColor;
      if (c && !c.startsWith('rgba(0, 0, 0, 0)') && c !== 'transparent') return parse(c);
    }
    return parse(getComputedStyle(document.body).backgroundColor) || [255, 255, 255];
  };
  // Over 2px in both directions: a screen-reader-only element is a clipped 1x1 box on purpose, and
  // reporting it as clipped text is the kind of noise that makes a review worth ignoring.
  const shown = [...document.querySelectorAll('body *')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && getComputedStyle(el).visibility !== 'hidden';
  });
  const texts = shown.filter(el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1));
  const small = texts.map(el => ({ px: parseFloat(getComputedStyle(el).fontSize),
                                   text: el.textContent.trim().slice(0, 60) }))
    .sort((a, b) => a.px - b.px).slice(0, 5);
  const contrast = texts.map(el => {
    const s = getComputedStyle(el);
    return { ratio: Math.round(ratio(parse(s.color), behind(el)) * 100) / 100,
             px: parseFloat(s.fontSize), weight: s.fontWeight, text: el.textContent.trim().slice(0, 60) };
  }).sort((a, b) => a.ratio - b.ratio).slice(0, 8);
  const widest = [...document.querySelectorAll('table')].map(t => ({
    columns: t.querySelector('tr') ? t.querySelector('tr').children.length : 0,
    width: Math.round(t.getBoundingClientRect().width), scroll: t.scrollWidth > t.clientWidth + 1 })).slice(0, 6);
  return {
    overflow_px: Math.max(0, document.documentElement.scrollWidth - innerWidth),
    clipped: shown.filter(el => el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflow !== 'visible')
      .slice(0, 8).map(el => ({ tag: el.tagName.toLowerCase(), id: el.id || null,
                                class: (el.className || '').toString().slice(0, 40),
                                text: el.textContent.trim().slice(0, 50) })),
    smallest_text: small, lowest_contrast: contrast, tables: widest,
    headings: [...document.querySelectorAll('h1,h2,h3,h4')].slice(0, 20)
      .map(h => h.tagName.toLowerCase() + ': ' + h.textContent.trim().slice(0, 70)),
  };
};

(async () => {
  const { chromium } = loadPlaywright();
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.addInitScript(t => localStorage.setItem('ailabs-theme', t), THEME);
  const p = await context.newPage();
  const errors = [];
  p.on('pageerror', e => errors.push(e.message));
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('response', r => { if (r.status() >= 400 && r.url().includes('/api/')) errors.push('HTTP ' + r.status() + ' ' + r.url().replace(BASE, '')); });
  const out = { view: VIEW, theme: THEME };
  try {
    await p.goto(BASE + '/' + HASH, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector('#connection[data-status=connected]', { timeout: 20000 });
    await p.waitForTimeout(1200);                         // the panel's own fetches
    const full = path.join(OUT, `${VIEW}-${THEME}.png`);
    await p.screenshot({ path: full, fullPage: true });
    out.image = full;
    if (SELECTOR) {
      const found = await p.$(SELECTOR);
      if (found) {
        const crop = path.join(OUT, `${VIEW}-${THEME}-crop.png`);
        await found.screenshot({ path: crop });
        out.crop = crop;
      } else { out.crop_missing = SELECTOR; }
    }
    out.layout = await p.evaluate(MEASURE);
    out.errors = errors.slice(0, 10);
  } catch (e) {
    out.error = String(e && e.message || e);
  } finally {
    await context.close(); await browser.close();
  }
  process.stdout.write(JSON.stringify(out) + '\n');
  process.exit(out.error ? 1 : 0);
})();
