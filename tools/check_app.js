/* Проверка приложения в jsdom: дерево, карта, хроника, свод, данные. */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const { inject } = require('./app_scripts');

const APP = process.argv[2] || '.';
const html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8');
const { readWorld } = require('./world_data');
const world = readWorld(APP);

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
    // Тесты проверяют русский интерфейс: в jsdom язык браузера английский.
    window.localStorage.setItem('chronicle.lang', 'ru');
    window.__WORLD__ = world;
    window.fetch = async () => ({ ok: true, json: async () => world, status: 200 });
    window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
    window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    window.HTMLDialogElement.prototype.close = function () { this.open = false; };
    window.Element.prototype.getBoundingClientRect = function () { return { width: 1200, height: 700, top: 0, left: 0, right: 1200, bottom: 700 }; };
    // карта: поддельные Image и canvas, чтобы проверить наведение без реального рендера
    window.Image = class FakeImage {
      constructor() { this.width = 2304; this.height = 1152; this.naturalWidth = 2304; this.naturalHeight = 1152; this._h = {}; }
      set src(value) { this._src = value; setTimeout(() => this._h.load?.({ type: 'load' }), 0); }
      addEventListener(type, fn) { this._h[type] = fn; }
      dispatchEvent(ev) { this._h[ev.type]?.(ev); return true; }
    };
    window.HTMLCanvasElement.prototype.getContext = function () {
      return { drawImage() {}, getImageData() { return { data: [0, 0, 5, 255] }; } };
    };  },
});

const { window } = dom;
const doc = window.document;
const wait = (ms = 120) => new Promise((r) => setTimeout(r, ms));
const click = (node) => node && node.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
const results = [];
const check = (name, ok, extra = '') => results.push({ name, ok, extra });

(async () => {
  await new Promise((r) => window.addEventListener('load', r, { once: true }));
  inject(doc, APP, { i18n: true });
  await wait(400);

  check('приложение показано', doc.getElementById('boot').hidden && !doc.getElementById('app').hidden);

  // По умолчанию род открыт конспектом: строки, отступы по слоям.
  // Порог зависит от размера рода: демо-мир и маленькая династия должны проходить одинаково.
  const dynastyCount = (world.meta && world.meta.counts && world.meta.counts.dynasty) || 0;
  const minRows = Math.min(20, Math.max(2, Math.floor(dynastyCount / 3)));
  const rows = doc.querySelectorAll('.kin-row');
  check('конспект рода отрисован', rows.length >= minRows, `строк: ${rows.length} (в династии ${dynastyCount})`);

  // Полотно — второй режим, проверяем и его.
  click(doc.getElementById('treeMode'));
  await wait(250);
  const nodes = doc.querySelectorAll('.tree .node');
  const minNodes = Math.min(20, Math.max(2, Math.floor(dynastyCount / 2)));
  check('дерево отрисовано', nodes.length >= minNodes, `узлов: ${nodes.length} (в династии ${dynastyCount})`);
  check('поколения есть', new Set([...nodes].map((n) => n.querySelector('rect').getAttribute('y'))).size >= 2);

  const viewport = doc.getElementById('treeViewport');
  const before = viewport.getAttribute('transform');
  click(doc.getElementById('zoomIn'));
  await wait(60);
  check('зум работает', viewport.getAttribute('transform') !== before, viewport.getAttribute('transform'));

  const node = [...nodes].find((n) => !n.classList.contains('is-main'));
  click(node);
  await wait(80);
  const drawer = doc.getElementById('drawer');
  check('шторка открывается', drawer && !drawer.hidden && drawer.textContent.trim().length > 10, drawer.textContent.replace(/\s+/g, ' ').slice(0, 60));

  const search = doc.getElementById('treeSearch');
  const someName = world.people.find((p) => p.kin && p.name).name.split(' ')[0];
  search.value = someName;
  search.dispatchEvent(new window.Event('input', { bubbles: true }));
  await wait(120);
  check('поиск подсвечивает', doc.querySelectorAll('.tree .node.is-match').length > 0, `${someName}: ${doc.querySelectorAll('.tree .node.is-match').length}`);

  // мир
  click(doc.querySelector('[data-nav="world"]'));
  await wait(150);
  check('карта вставлена', !!doc.querySelector('.map-figure img'), doc.querySelector('.map-figure img')?.getAttribute('src') || 'нет');
  check('карта интерактивна', !!world.mapIndex, world.mapIndex?.file || 'нет индекса');
  const mapImg = doc.getElementById('worldMap');
  mapImg.dispatchEvent(new window.MouseEvent('mousemove', { bubbles: true, clientX: 400, clientY: 300 }));
  await wait(80);
  const tip = doc.getElementById('mapTip');
  check('наведение показывает двор', tip && !tip.hidden && tip.textContent.trim().length > 2, tip?.textContent.replace(/\s+/g, ' ').slice(0, 70));
  mapImg.dispatchEvent(new window.MouseEvent('click', { bubbles: true, clientX: 400, clientY: 300 }));
  await wait(60);
  check('клик раскрывает карточку', !doc.getElementById('mapDetail').hidden, doc.getElementById('mapDetail').textContent.replace(/\s+/g, ' ').slice(0, 80));
  const courts = doc.querySelectorAll('.court');
  check('дворы по кольцам', courts.length >= 10, `карточек: ${courts.length}`);
  check('молва посчитана', /Молва: \d+ держав/.test(doc.body.textContent));

  // хроника
  click(doc.querySelector('[data-nav="chronicle"]'));
  await wait(180);
  const years = doc.querySelectorAll('.year');
  check('главы собраны', years.length > 0, `глав: ${years.length}`);
  const entries = doc.querySelectorAll('.entry');
  check('записей много', entries.length > 20, `записей: ${entries.length}`);
  check('сводка года есть', !!doc.querySelector('.year__summary'));
  check('счётчик пропущенного', !!doc.querySelector('.year__missed'), doc.querySelector('.year__missed')?.textContent || 'нет');
  check('рубрика на своей записи', !!doc.querySelector('.entry--0.dropcap') || !!doc.querySelector('.dropcap'));

  const kinds = new Set([...entries].map((e) => e.className.match(/entry--(\d)/)?.[1]));
  check('разные регистры', kinds.size >= 2, [...kinds].join(','));

  // правда и молва
  const truth = doc.getElementById('showTruth');
  truth.checked = true;
  truth.dispatchEvent(new window.Event('change', { bubbles: true }));
  await wait(150);
  check('правда рядом', doc.querySelectorAll('.truth').length > 0);

  const rumors = doc.getElementById('incRumors');
  const beforeRumors = doc.querySelectorAll('.entry').length;
  rumors.checked = true;
  rumors.dispatchEvent(new window.Event('change', { bubbles: true }));
  await wait(150);
  check('молва расширяет хронику', doc.querySelectorAll('.entry').length >= beforeRumors, `${beforeRumors} → ${doc.querySelectorAll('.entry').length}`);

  // свод
  click(doc.querySelector('[data-nav="book"]'));
  await wait(120);
  check('свод по поколениям', doc.querySelectorAll('.gen').length > 0, `поколений: ${doc.querySelectorAll('.gen').length}`);
  check('экспорт свода', !!doc.getElementById('downloadBook'));

  // досье
  click(doc.querySelector('[data-nav="dossier"]'));
  await wait(150);
  const dossier = doc.getElementById('dossierText')?.textContent || '';
  check('досье собирается', dossier.length > 400, `символов: ${dossier.length}`);
  check('в досье есть династия', dossier.includes('## Династия') && dossier.includes('Родство'));
  const faithInWorld = (world.realms || []).some((r) => r.faith);
  if (faithInWorld) {
    check('в досье есть вера и культура', dossier.includes('вера:') && dossier.includes('культура:'));
  } else {
    check('досье честно говорит о вере', dossier.includes('Вера не привязана'));
  }
  check('в досье есть владения', dossier.includes('владений:'));
  check('кнопка копирования', !!doc.getElementById('copyDossier'));

  // данные
  click(doc.querySelector('[data-nav="data"]'));
  await wait(100);
  check('экран данных', doc.body.textContent.includes('build_world.py'));
  const countiesShown = (doc.body.textContent.match(/графств на карте:\s*(\d+|—)/) || [])[1];
  check('на экране данных видно число графств', Boolean(countiesShown) && countiesShown !== '—', countiesShown || 'нет строки');

  // импорт своего сохранения
  click(doc.querySelector('[data-nav="import"]'));
  await wait(220);
  check('экран импорта открыт', !!doc.getElementById('importPanel'));

  // Переключение языка интерфейса
  const en = doc.querySelector('.lang[data-lang="en"]');
  click(en);
  await wait(250);
  const worldLabel = [...doc.querySelectorAll('[data-nav="world"] span')].map((s) => s.textContent).join(' ');
  check('английский интерфейс включается', worldLabel.includes('World'), worldLabel);
  const ru = doc.querySelector('.lang[data-lang="ru"]');
  click(ru);
  await wait(250);
  const worldRu = [...doc.querySelectorAll('[data-nav="world"] span')].map((s) => s.textContent).join(' ');
  check('русский возвращается', worldRu.includes('Мир'), worldRu);

  // Подписи интерфейса на английском не должны содержать кириллицы.
  window.location.hash = '#tree'; window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  await wait(350);
  click(doc.querySelector('.lang[data-lang="en"]'));
  await wait(250);
  const cyr = /[А-Яа-яЁё]/;
  // Легенда есть только в режиме конспекта: если открыто полотно, вернёмся.
  const modeButton = doc.getElementById('treeMode');
  if (modeButton && /Конспект|Outline/.test(modeButton.textContent)) {
    click(modeButton);
    await wait(300);
  }
  const legendNode = doc.querySelector('.tree-legend--marks');
  const legend = legendNode?.textContent || '';
  check('легенда рода без кириллицы', legend.length > 5 && !cyr.test(legend),
    `hash=${window.location.hash} легенд=${doc.querySelectorAll('.tree-legend--marks').length} текст="${legend.replace(/\s+/g, ' ').slice(0, 40)}"`);
  window.location.hash = '#chronicle'; window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  await wait(350);
  const form = [...doc.querySelectorAll('.field__label, .check')].map((n) => n.textContent).join(' ');
  check('форма хроники без кириллицы', form.length > 5 && !cyr.test(form), form.replace(/\s+/g, ' ').slice(0, 70));
  window.location.hash = '#world'; window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  await wait(350);
  const rings = doc.querySelector('.map-legend')?.textContent || '';
  check('легенда карты без кириллицы', rings.length > 5 && !cyr.test(rings), rings.replace(/\s+/g, ' ').slice(0, 60));
  click(doc.querySelector('.lang[data-lang="ru"]'));
  await wait(200);
  window.location.hash = '#import'; window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  await wait(350);
  check('в импорте есть выбор сохранения', !!doc.getElementById('importSave'));
  check('в импорте есть кнопка запуска', !!doc.getElementById('importStart'));

  const failed = results.filter((r) => !r.ok);
  for (const r of results) console.log(`${r.ok ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? ' — ' + r.extra : ''}`);
  if (errors.length) { console.log('\nОшибки страницы:'); errors.slice(0, 6).forEach((e) => console.log('  ' + e)); }
  console.log(`\nитог: ${results.length - failed.length}/${results.length}`);
  process.exit(failed.length || errors.length ? 1 : 0);
})();
