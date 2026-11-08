/* Проверка карты: линзы и два слоя политической карты. */
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

  const titleCard = {
    counties: ['c_one', 'c_two', 'c_three', 'c_four', 'c_five'],
    chain: [['d_one', 'k_one', 'e_one'], ['d_one', 'k_one', 'e_one'], [], ['d_two', 'k_two'], ['d_two', 'k_two', 'e_two']],
    province: { '1': 1, '2': 2, '3': 3, '4': 4, '5': 5 },
    names: { c_one: 'Первое', c_two: 'Второе', c_three: 'Третье', c_four: 'Четвёртое', c_five: 'Пятое', d_one: 'Герцогство', k_one: 'Королевство', e_one: 'Империя' },
    owners: { c_one: 1 },
  };

const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:8779/',
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(window) {
    // Тесты проверяют русский интерфейс: в jsdom язык браузера английский.
    window.localStorage.setItem('chronicle.lang', 'ru');
    window.fetch = async (url) => {
      if (String(url).includes('titles-map')) return { ok: true, json: async () => titleCard, status: 200 };
      return { ok: true, json: async () => world, status: 200 };
    };
    window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
    window.Element.prototype.getBoundingClientRect = function () { return { width: 1200, height: 700, top: 0, left: 0, right: 1200, bottom: 700 }; };
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
const wait = (ms = 250) => new Promise((r) => setTimeout(r, ms));
const click = (node) => node && node.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
const results = [];
const check = (name, ok, extra = '') => results.push({ name, ok, extra });

(async () => {
  await new Promise((r) => window.addEventListener('load', r, { once: true }));
  inject(doc, APP);
  await wait(600);

  window.location.hash = '#world';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  await wait(600);

  const political = world.mapIndex?.political;
  const hasHouses = Boolean(political?.houses);
  const hasFamily = Boolean(political?.family);

  const buttons = [...doc.querySelectorAll('.lens[data-lens]')];
  check('переключатель линз есть', buttons.length === 3, `кнопок: ${buttons.length}`);

  const titles = world.mapIndex?.titles;
  check('карта титулов собрана', Boolean(titles?.map), titles?.map || 'нет');

  const img = doc.getElementById('worldMap');
  check('по умолчанию радиус знания', !(img.getAttribute('src') || '').includes('political'), img.getAttribute('src'));

  check('карта домов собрана', hasHouses, political?.houses?.file || 'нет');
  if (hasHouses) {
    click(buttons.find((b) => b.dataset.lens === 'political'));
    await wait(400);
    const img2 = doc.getElementById('worldMap');
    check('политическая линза открылась', (img2.getAttribute('src') || '').includes('political-houses'), img2.getAttribute('src'));

    const legend = doc.querySelector('.map-legend--political');
    check('легенда домов видна', Boolean(legend) && legend.textContent.trim().length > 10, legend?.textContent.trim().slice(0, 60) || 'нет');
    const firstHouse = political.houses.houses[0]?.house;
    check('в легенде имена домов', Boolean(firstHouse) && (legend.textContent || '').includes(firstHouse), firstHouse || 'нет');

    check('у карты домов своя карта индексов', (political.houses.index || '').includes('political-houses-ids'), political.houses.index);
  }

  if (hasFamily) {
    const layer = [...doc.querySelectorAll('.lens[data-layer]')];
    check('переключатель слоёв есть', layer.length === 2, `кнопок слоёв: ${layer.length}`);
    click(layer.find((b) => b.dataset.layer === 'family'));
    await wait(400);
    const img3 = doc.getElementById('worldMap');
    check('слой земель рода открылся', (img3.getAttribute('src') || '').includes('political.png'), img3.getAttribute('src'));
    const groups = doc.querySelectorAll('.lens-house');
    check('в легенде дома с правителями', groups.length > 0, `групп: ${groups.length}`);
    check('у слоя земель своя карта индексов', (political.family.index || '').includes('political-ids'), political.family.index);
  }

  // Линза титулов: своя карта, свой индекс, зум и цепочка по клику.
  if (titles) {
    click(buttons.find((b) => b.dataset.lens === 'titles'));
    await wait(400);
    const imgT = doc.getElementById('worldMap');
    check('линза титулов открылась', (imgT.getAttribute('src') || '').includes('titles'), imgT.getAttribute('src'));
    const titlesIndex = titles.index || titles.file || '';
    check('у карты титулов своя карта индексов', titlesIndex.includes('titles-ids'), titlesIndex);

    const zoomButtons = [...doc.querySelectorAll('[data-zoom]')];
    check('кнопки масштаба есть', zoomButtons.length === 3, `кнопок: ${zoomButtons.length}`);
    const before = imgT.style.transform || '';
    click(zoomButtons.find((b) => b.dataset.zoom === 'in'));
    await wait(100);
    const after = imgT.style.transform || '';
    check('масштаб меняется', after !== before && /scale\(/.test(after), after || 'нет transform');
    click(zoomButtons.find((b) => b.dataset.zoom === 'reset'));
    await wait(100);
    check('сброс возвращает масштаб', /scale\(1\)/.test(imgT.style.transform || '') || !imgT.style.transform, imgT.style.transform);

    // Клик по карте: canvas в jsdom отдаёт индекс 5 — пятое графство с цепочкой.
    imgT.dispatchEvent(new window.MouseEvent('click', { bubbles: true, clientX: 400, clientY: 300 }));
    await wait(300);
    const detail = doc.getElementById('mapDetail');
    check('клик по титулу даёт панель', Boolean(detail) && !detail.hidden, detail ? detail.textContent.slice(0, 80) : 'нет');
    check('в панели цепочка титулов', Boolean(detail) && /герцогство|вольное графство/.test(detail.textContent || ''), (detail?.textContent || '').slice(0, 120));

    const legendTitles = doc.querySelector('.map-legend--titles');
    check('легенда тиров видна', Boolean(legendTitles) && legendTitles.textContent.includes('империя'), legendTitles?.textContent.slice(0, 60) || 'нет');
  }

  check('нет ошибок jsdom', errors.length === 0, errors.slice(0, 2).join(' | '));

  let failed = 0;
  for (const r of results) {
    if (!r.ok) failed += 1;
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
  }
  console.log(`\nитог: ${results.length - failed}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
