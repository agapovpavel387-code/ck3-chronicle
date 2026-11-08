/* Проверка рода: конспект по слоям, свёртывание, карточка, поиск и полотно. */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const { inject } = require('./app_scripts');

const APP = process.argv[2] || '.';
const html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8');
const world = JSON.parse(fs.readFileSync(path.join(APP, '_data/world.json'), 'utf8'));

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => { if (!/scrollTo|Could not load|scrollIntoView/.test(e.message)) errors.push(e.message); });
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
    window.Element.prototype.setPointerCapture = function () {};
    window.Element.prototype.scrollIntoView = function () {};
    window.Image = class FakeImage {
      constructor() { this.naturalWidth = 2304; this.naturalHeight = 1152; this._h = {}; }
      set src(value) { this._src = value; setTimeout(() => this._h.load?.({ type: 'load' }), 0); }
      addEventListener(type, fn) { this._h[type] = fn; }
      dispatchEvent(ev) { this._h[ev.type]?.(ev); return true; }
    };
    window.HTMLCanvasElement.prototype.getContext = function () {
      return { drawImage() {}, getImageData() { return { data: [0, 0, 5, 255] }; } };
    };
  },
});

const { window } = dom;
const doc = window.document;
const wait = (ms = 180) => new Promise((r) => setTimeout(r, ms));
const click = (node) => node && node.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
const pointer = (node, type, x, y) => node.dispatchEvent(new window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
const results = [];
const check = (name, ok, extra = '') => results.push({ name, ok, extra });

(async () => {
  await new Promise((r) => window.addEventListener('load', r, { once: true }));
  inject(doc, APP);
  await wait(700);

  // Конспект по умолчанию. Порог — от размера рода: демо-мир и малая династия проходят одинаково.
  const dynastyCount = (world.meta && world.meta.counts && world.meta.counts.dynasty) || 0;
  const minRows = Math.min(20, Math.max(2, Math.floor(dynastyCount / 3)));
  const rows = [...doc.querySelectorAll('.kin-row')];
  check('конспект открыт по умолчанию', rows.length >= minRows, `строк: ${rows.length} (в династии ${dynastyCount})`);

  const depths = [...new Set([...doc.querySelectorAll('.kin-item')].map((li) => Number(li.dataset.depth)))].sort();
  check('видны два слоя', depths.length === 2 && depths[0] === 0 && depths[1] === 1, `слои: ${depths.join(', ')}`);

  const genOf = new Map(world.people.map((p) => [p.id, p.gen]));
  const rowDepthOk = [...doc.querySelectorAll('.kin-item')].every((li) => {
    const row = li.querySelector(':scope > .kin-row');
    return row && genOf.get(Number(row.dataset.person)) === Number(li.dataset.depth);
  });
  check('отступ совпадает со слоем', rowDepthOk);

  // Свёртывание
  const toggles = [...doc.querySelectorAll('.kin-toggle[data-toggle]')];
  const before = doc.querySelectorAll('.kin-row').length;
  click(toggles[0]);
  await wait(200);
  const collapsed = doc.querySelectorAll('.kin-row').length;
  check('строка сворачивается', collapsed < before, `${before} → ${collapsed}`);

  click(doc.querySelector('.kin-toggle[data-toggle]'));
  await wait(200);
  check('строка раскрывается обратно', doc.querySelectorAll('.kin-row').length >= before);

  // Карточка в строке
  const nameButton = doc.querySelector('.kin-name');
  click(nameButton);
  await wait(200);
  const card = doc.querySelector('.gen-card');
  check('карточка открывается по имени', Boolean(card));
  const cardText = (card?.textContent || '').replace(/\s+/g, ' ');
  check('в карточке родство', /(вы|отец|мать|дед|бабка|прадед|сын|дочь|брат|сестра|дядя|тётка|племянник|внук|родня|супруг|свойственник)/.test(cardText), cardText.slice(0, 60));
  check('в карточке культура', /Культура/.test(cardText));
  check('в карточке вера', /Вера/.test(cardText));

  // Развернуть всё
  click(doc.getElementById('treeExpand'));
  await wait(300);
  const all = doc.querySelectorAll('.kin-row').length;
  const kin = world.people.filter((p) => p.kin).length;
  check('развернуть всё показывает весь род', all >= kin, `строк ${all}, родичей ${kin}`);

  // Свернуть
  click(doc.getElementById('treeCollapse'));
  await wait(300);
  check('свернуть возвращает два слоя', doc.querySelectorAll('.kin-row').length < all);

  // Поиск: раскрывает путь до человека
  const deep = world.people.filter((p) => p.kin).sort((a, b) => (b.gen ?? 0) - (a.gen ?? 0))[0];
  const search = doc.getElementById('treeSearch');
  search.value = deep.name;
  search.dispatchEvent(new window.Event('input', { bubbles: true }));
  await wait(300);
  const matches = doc.querySelectorAll('.kin-row.is-match');
  check('поиск находит глубокого человека', matches.length > 0, `${deep.name} (слой ${deep.gen}): ${matches.length}`);

  // Полотно как второй режим
  click(doc.getElementById('treeMode'));
  await wait(400);
  const nodes = doc.querySelectorAll('.tree .node');
  const minNodes = Math.min(200, Math.max(2, dynastyCount));
  check('полотно открывается', nodes.length >= minNodes, `узлов: ${nodes.length} (в династии ${dynastyCount})`);

  const canvas = doc.getElementById('treeCanvas');
  const target = nodes[4];
  pointer(target, 'pointerdown', 200, 200);
  pointer(canvas, 'pointermove', 202, 201);
  pointer(canvas, 'pointerup', 202, 201);
  await wait(200);
  const drawer = doc.getElementById('drawer');
  check('клик на полотне открывает панель', drawer && !drawer.hidden);

  check('нет ошибок jsdom', errors.length === 0, errors.slice(0, 2).join(' | '));

  let failed = 0;
  for (const r of results) {
    if (!r.ok) failed += 1;
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
  }
  console.log(`\nитог: ${results.length - failed}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
