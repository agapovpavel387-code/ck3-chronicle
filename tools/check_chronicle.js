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
    // Тесты проверяют русский интерфейс: в jsdom язык браузера английский.
    window.localStorage.setItem('chronicle.lang', 'ru');
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
  // Число глав зависит от сейва: у короткой династии эпоха может быть одна.
  check('главы есть', chapters.length >= 1, `глав: ${chapters.length}`);
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

  // Повод войны и цель — часть строки, а не украшение карточки.
  const sampleWar = (world.events || []).find((e) => e.kind === 'war' && e.who);
  if (sampleWar && typeof window.entryText === 'function') {
    const line = window.entryText({ ...sampleWar, grade: 0, ring: 0, type: 'завоевание графства', title: 'Рей' });
    check('в строке войны есть цель', /Цель — Рей/.test(line), line.slice(0, 100));
    const card = typeof window.renderEntry === 'function'
      ? window.renderEntry({ ...sampleWar, kind: 'war', grade: 0, ring: 0, type: 'завоевание графства', cb: 'county_conquest_cb' })
      : '';
    check('у войны есть метка повода', card.includes('entry__cause') && card.includes('завоевание графства'), card.slice(0, 120));

    // Семейство повода меняет фразу: священная, дань, Поднебесная, фракция.
    const holy = window.entryText({ ...sampleWar, kind: 'war', family: 'holy', role: 'defend', grade: 0, who: null, who2: null, whoName: 'Панферий', who2Name: 'Вук', type: 'малая священная война', title: null });
    check('священная — за веру и от лица обороны', /за веру/.test(holy) && /на нас|на нас/i.test(holy), holy.slice(0, 110));

    const third = window.entryText({ ...sampleWar, kind: 'war', family: 'tribute', role: 'third', grade: 1, who: null, who2: null, whoName: 'Панферий', who2Name: 'Вук', type: 'обложить данью', title: 'Рей' });
    check('третья сторона называет обоих', /Панферий/.test(third) && /Вук/.test(third), third.slice(0, 110));
    check('в строке нет разметки игры', !/[\[\]#]/.test(third), third.slice(0, 110));

    const mandate = window.entryText({ ...sampleWar, kind: 'war', family: 'mandate', role: 'attack', grade: 0, who: null, who2: null, whoName: 'Будиман', who2Name: 'Саладу', type: 'война за объединение Китая', title: null });
    check('Поднебесная — за верховенство', /за верховенство/.test(mandate), mandate.slice(0, 110));

    // Воспоминание о войне: категория из сейва даёт причину, исход — свой значок.
    const memWar = window.entryText({ ...sampleWar, kind: 'war', family: 'holy', role: 'attack', grade: 0, who: null, who2: null, whoName: 'Цюаньчжун', who2Name: 'Диего', type: 'священная война', title: 'Рей', cb: 'war_memory_cb_holy_war' });
    check('война из памяти: за веру и по имени', /за веру/.test(memWar) && /Диего/.test(memWar), memWar.slice(0, 110));
    const winCard = typeof window.renderEntry === 'function'
      ? window.renderEntry({ ...sampleWar, kind: 'war_win', grade: 0, type: 'священная война', cb: 'war_memory_cb_holy_war' })
      : '';
    check('у победы тоже метка повода', winCard.includes('entry__cause'), winCard.slice(0, 120));
  }

  // Титулы: у потери есть имя и причина, одна смена — одна строка.
  const losses = (world.events || []).filter((e) => e.kind === 'title_loss');
  check('у потери титула есть имя', losses.length > 0 && losses.every((e) => e.title), `${losses.length} событий, без имени: ${losses.filter((e) => !e.title).length}`);
  check('у потери титула есть причина', losses.every((e) => e.why), `без причины: ${losses.filter((e) => !e.why).length}`);

  const successions = (world.events || []).filter((e) => e.kind === 'succession');
  check('у смены власти есть причина', successions.length > 0 && successions.every((e) => e.why), `без причины: ${successions.filter((e) => !e.why).length}`);
  check('у смены власти есть тир', successions.every((e) => e.tier), 'без тира: ' + successions.filter((e) => !e.tier).length);

  const seen = new Set();
  const repeats = [];
  for (const e of [...successions, ...losses]) {
    const key = `${e.kind}|${e.title}|${e.date}|${e.who}`;
    if (seen.has(key)) repeats.push(key);
    seen.add(key);
  }
  check('одна смена — одна запись', repeats.length === 0, repeats.slice(0, 2).join(' | '));

  if (losses.length && successions.length && typeof window.entryText === 'function') {
    const loss = losses.find((e) => e.grade <= 1 && e.who) || losses[0];
    const line = window.entryText({ ...loss, grade: 1, ring: 0 });
    check('строка потери называет титул и причину', line.includes(loss.title) && line.includes(loss.why), line.slice(0, 110));

    const succ = successions.find((e) => e.grade === 1 && e.who && e.action !== 'created') || successions.find((e) => e.action !== 'created') || successions[0];
    const succLine = window.entryText({ ...succ, grade: 1 });
    check('строка смены власти называет причину', succLine.includes(succ.why), succLine.slice(0, 110));

    const created = window.entryText({
      kind: 'succession', action: 'created', why: 'создан', grade: 0,
      title: 'Дэмбийя', who: succ.who, date: succ.date, v: 0,
    });
    check('созданный титул назван учреждённым', /учреждён титул/.test(created), created.slice(0, 110));
  }

  // Потеря титула — событие власти: она не должна тонуть в бытовых записях года.
  const lossLines = [...docEl.querySelectorAll('.entry')].filter((e) => /лишил/.test(e.textContent));
  check('потери титула видны в летописи', lossLines.length >= 3,
    `строк о потере: ${lossLines.length} из ${losses.length} событий`);

  // Разметка игры не должна просачиваться в летопись.
  const dirtyCause = (world.events || []).filter((e) => /\[|\]|Select_CString|\bL\s/.test(e.cause || ''));
  check('в причинах смерти нет разметки', dirtyCause.length === 0,
    `строк с разметкой: ${dirtyCause.length} ${dirtyCause[0]?.cause?.slice(0, 60) || ''}`);

  const dirtyTitle = (world.events || []).filter((e) => /\$/.test(e.title || '') || /\$/.test(e.realm || ''));
  check('в титулах и державах нет подстановок', dirtyTitle.length === 0, `строк: ${dirtyTitle.length}`);

  const numbered = (world.events || []).filter((e) => /^держава \d+$/.test(e.realm || ''));
  check('держава без имени не названа номером', numbered.length === 0, `событий: ${numbered.length}`);

  const namedRealms = (world.realms || []).flatMap((r) => r.rulers || []);
  const emptyNames = namedRealms.filter((x) => x.name === '');
  check('у правителей не пустое имя', emptyNames.length === 0, `пустых: ${emptyNames.length}`);

  if (typeof window.entryText === 'function') {
    const death = (world.events || []).find((e) => e.kind === 'death' && e.cause);
    if (death) {
      const line = window.entryText({ ...death, grade: 0, ring: 0 });
      check('в строке смерти нет разметки', !/\[|\]|Select_CString/.test(line), line.slice(0, 100));
    }
  }

  // Владения: мёртвые не держат землю, одно имя — одна строка, живой дом назван.
  const deadOwners = (world.people || []).filter((p) => p.death && p.titles && p.titles.length);
  check('мёртвые не владеют землёй', deadOwners.length === 0,
    `мёртвых с титулами: ${deadOwners.length} ${deadOwners[0]?.name || ''}`);

  const tenured = (world.people || []).filter((p) => p.tenures && p.tenures.length);
  const repeatedTenure = tenured.filter((p) => new Set(p.tenures.map((t) => t[0])).size !== p.tenures.length);
  check('владения без повторов имени', repeatedTenure.length === 0, `людей: ${repeatedTenure.length}`);

  const numericHouse = (world.people || []).filter((p) => /^(House|дом)\s+\d+$/.test(p.house || ''));
  check('дом не назван номером', numericHouse.length === 0, `людей: ${numericHouse.length}`);

  const gens = (world.meta && world.meta.generations) || [];
  const badGen = gens.filter((g) => {
    const alive = (world.people || []).filter((p) => p.gen === g.gen && !p.death);
    return alive.length > 0 && g.to != null;
  });
  check('поколение с живыми открыто', badGen.length === 0,
    `закрытых: ${badGen.length} ${badGen.map((g) => `${g.gen + 1}→${g.to}`).join(', ')}`);

  check('нет ошибок jsdom', errors.length === 0, errors.slice(0, 2).join(' | '));

  let failed = 0;
  for (const r of results) {
    if (!r.ok) failed += 1;
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
  }
  console.log(`\nитог: ${results.length - failed}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
