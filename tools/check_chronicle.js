/* Проверка хроники: главы, слои, нити, зачины, честный счёт. */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const { inject } = require('./app_scripts');

const APP = process.argv[2] || '.';
const html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8');
const world = JSON.parse(fs.readFileSync(path.join(APP, '_data/world.json'), 'utf8'));

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => { if (!/scrollTo|Could not load/.test(e.message)) errors.push(e.message); });
vc.on('error', (m) => errors.push(String(m)));

const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:8779/',
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(window) {
    window.fetch = async () => ({ ok: true, json: async () => world, status: 200 });
    window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
    window.Element.prototype.getBoundingClientRect = function () { return { width: 1200, height: 700, top: 0, left: 0, right: 1200, bottom: 700 }; };
    window.Element.prototype.scrollIntoView = function () {};
    window.Image = class { constructor() { this.naturalWidth = 10; this.naturalHeight = 10; } addEventListener() {} };
    window.HTMLCanvasElement.prototype.getContext = function () { return { drawImage() {}, getImageData() { return { data: [0, 0, 5, 255] }; } }; };
  },
});

const { window } = dom;
const doc = window.document;
const wait = (ms = 250) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, extra = '') => results.push({ name, ok, extra });

(async () => {
  await new Promise((r) => window.addEventListener('load', r, { once: true }));
  inject(doc, APP);
  await wait(600);

  window.location.hash = '#chronicle';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  await wait(900);

  const docEl = doc.getElementById('doc');
  check('хроника собрана', Boolean(docEl));

  const chapters = [...docEl.querySelectorAll('.chapter')];
  check('главы есть', chapters.length >= 2, `глав: ${chapters.length}`);
  const withSum = chapters.filter((c) => c.querySelector('.chapter__sum')).length;
  check('у глав есть итоги', withSum === chapters.length, `${withSum} из ${chapters.length}`);
  check('у главы есть заглавие и годы', chapters.every((c) => c.querySelector('.chapter__era') && c.querySelector('.chapter__years')));

  const years = [...docEl.querySelectorAll('.year')];
  check('годы на месте', years.length > 20, `лет: ${years.length}`);
  const layered = years.filter((y) => y.querySelectorAll('.layer').length > 0).length;
  check('в каждом году есть слои', layered === years.length, `со слоями: ${layered} из ${years.length}`);

  const layerTitles = [...docEl.querySelectorAll('.layer__title')].map((t) => t.textContent.trim());
  const kinds = new Set(layerTitles);
  check('слои названы по-разному', kinds.size >= 2 && kinds.has('В роду'), [...kinds].join(' / '));

  const far = [...docEl.querySelectorAll('.entry--far')];
  check('издали идёт счётом', far.length > 10, `строк: ${far.length}`);
  check('издали без списка имён', far.every((f) => f.textContent.length < 220), far[0]?.textContent.slice(0, 80) || '');

  const threaded = [...docEl.querySelectorAll('.entry')].filter((e) => /Война начата в|Распря с/.test(e.textContent));
  check('нити войн и распрь есть', threaded.length >= 20, `записей с нитью: ${threaded.length}`);

  const texts = [...docEl.querySelectorAll('.entry')].map((e) => e.textContent.replace(/\s+/g, ' ').trim());
  const unique = new Set(texts);
  const ratio = texts.length ? unique.size / texts.length : 0;
  check('повторов мало', ratio > 0.9, `${Math.round(ratio * 100)}% уникальных из ${texts.length}`);

  const openers = new Set(texts.map((t) => t.split(' ').slice(0, 2).join(' ')));
  check('строки начинаются по-разному', openers.size >= 60, `разных зачинов: ${openers.size}`);

  const missed = docEl.querySelector('.year__missed');
  check('честный счёт на месте', Boolean(missed), missed?.textContent?.trim().slice(0, 60) || 'нет');

  check('нет ошибок jsdom', errors.length === 0, errors.slice(0, 2).join(' | '));

  let failed = 0;
  for (const r of results) {
    if (!r.ok) failed += 1;
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
  }
  console.log(`\nитог: ${results.length - failed}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
