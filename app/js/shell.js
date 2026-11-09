/* Хроника рода · оболочка.
 *
 * Загрузка мира, навигация по экранам, переключение языка, буфер и файлы.
 * Сюда же — общая обвязка экранов после отрисовки (afterRender).
 * Зависит: все экраны.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
async function boot() {
  bind();
  try {
    // Мир — один файл: `_data/world.js`. Он работает и через сервер, и с file://.
    // Если данные уже в странице (тесты, встраивание) — не грузим второй раз.
    // Метка времени: мир пересобирается, и браузер не должен держать старую копию.
    if (!window.__WORLD__) await loadScript(`_data/world.js?t=${Date.now()}`);
    if (!window.__WORLD__) throw new Error('в world.js нет данных');
    startWith(window.__WORLD__);
  } catch (err) {
    el('boot').hidden = true;
    el('app').hidden = false;
    if (location.protocol === 'http:' || location.protocol === 'https:') {
      // Открыто через start.cmd: предложим выбрать сохранение прямо здесь.
      setView('import');
    } else {
      el('main').innerHTML = `<div class="empty-state"><h3>Мир не загружен</h3>
          <p>Не удалось прочитать <code>_data/world.js</code>. Запустите <code>start.cmd</code> (Windows) или <code>./start.sh</code>, чтобы выбрать сохранение.</p>
          <p class="small muted">${esc(err.message)}</p></div>`;
    }
  }
}
function startWith(world) {
  if (!world || !world.meta) return;
  state.world = world;
  index(world);
  const s = state.settings;
  const years = ix.years;
  if (!s.from || !years.length) {
    const origin = world.meta.dynastyFrom;
    const firstEvent = years[0];
    s.from = origin && firstEvent ? Math.max(origin, firstEvent - 60) : origin || firstEvent || world.meta.year - 40;
  }
  if (!s.to || !years.length) s.to = years[years.length - 1] ?? world.meta.year;
  el('boot').hidden = true;
  el('app').hidden = false;
  state.tree = freshTree();
  renderMeta();
  renderRailFoot();
  // Ссылка вида #world должна открывать мир, а не дерево по умолчанию.
  const hashView = location.hash.replace('#', '');
  if (hashView) state.view = hashView;
  render();
}
function renderMeta() {
  const { meta } = state.world;
  el('topMeta').innerHTML = `
      <span class="chip">${esc(meta.player.house || 'род')}</span>
      <span class="chip">${esc(meta.year)}</span>
      <span class="chip">${meta.counts.known} дворов рядом</span>`;
}
function renderRailFoot() {
  const { meta } = state.world;
  el('railFoot').innerHTML = `
      <b>${esc(meta.player.name || 'род')}</b>
      <span>${esc(meta.player.title || 'без земли')}</span>
      <span>${meta.counts.dynasty} в династии · ${meta.counts.events} событий</span>`;
}
/* ---------- навигация ---------- */

function setView(view) {
  state.view = view;
  for (const link of document.querySelectorAll('[data-nav]')) {
    if (link.dataset.nav === view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  render();
  el('main').focus({ preventScroll: true });
  try { window.scrollTo({ top: 0 }); } catch { /* jsdom */ }
}
function render() {
  if (!state.world) return;
  const main = el('main');
  main.classList.toggle('main--wide', state.view === 'tree');
  try {
    if (state.view === 'tree') main.innerHTML = viewTree();
    else if (state.view === 'world') main.innerHTML = viewWorld();
    else if (state.view === 'chronicle') main.innerHTML = viewChronicle();
    else if (state.view === 'book') main.innerHTML = viewBook();
    else if (state.view === 'dossier') main.innerHTML = viewDossier();
    else if (state.view === 'import') main.innerHTML = viewImport();
    else main.innerHTML = viewData();
    afterRender();
  } catch (error) {
    main.innerHTML = `<div class="empty-state"><h3>Не удалось собрать экран</h3>
        <p>${esc(error && error.message ? error.message : 'неизвестная ошибка')}</p></div>`;
    console.error(error);
  }
}
/* ---------- род ---------- */

function afterRender() {
  const form = el('chronicleForm');
  if (form) {
    form.addEventListener('submit', (ev) => { ev.preventDefault(); readForm(); saveSettings(); buildDoc(); });
    form.addEventListener('change', () => { readForm(); saveSettings(); buildDoc(); });
    const clearTitle = el('clearTitleFilter');
    if (clearTitle) clearTitle.addEventListener('click', () => { state.titleFilter = null; render(); });
    el('copyDoc').addEventListener('click', () => copy(docText()).then((ok) => toast(ok ? 'Скопировано' : 'Не удалось скопировать')));
    el('downloadDoc').addEventListener('click', () => download('hronika-roda.md', docText()));
    buildDoc();
  }

  // Линзы карты: переключатель перерисовывает экран с другим изображением.
  for (const button of document.querySelectorAll('.lens[data-lens]')) {
    button.addEventListener('click', () => {
      if (state.lens === button.dataset.lens) return;
      state.lens = button.dataset.lens;
      render();
    });
  }

  // Слой политической карты: дома всех держав или земли рода.
  for (const button of document.querySelectorAll('.lens[data-layer]')) {
    button.addEventListener('click', () => {
      if (state.mapLayer === button.dataset.layer) return;
      state.mapLayer = button.dataset.layer;
      render();
    });
  }

  const importer = el('importPanel');
  if (importer) setupImporter(importer);

  const canvas = el('treeCanvas');
  if (canvas) setupTree(canvas);
  const listRoot = el('treeListRoot');
  if (listRoot) setupTreeList(listRoot);
  const outline = el('outlineRoot');
  if (outline) setupOutline(outline);
  if (canvas || listRoot || outline) setupTreeToolbar();

  if (el('worldMap')) setupMap();
  const mapImg = el('worldMap');
  if (mapImg) {
    mapImg.addEventListener('error', () => {
      const wrap = mapImg.parentElement;
      if (!wrap) return;
      wrap.innerHTML =
        '<p class="map-fallback">Карта для этого мира не собрана. Пересоберите её: <code>build_world.py --map …</code></p>';
    });
  }

  const checkMap = el('checkMap');
  if (checkMap) {
    checkMap.addEventListener('click', async () => {
      const out = el('checkMapResult');
      out.textContent = T('data.checking', 'Проверяю…');
      try {
        const build = state.world.meta?.build ? `?v=${state.world.meta.build}` : '';
        const card = await loadTitlesCard();
        if (!card || !card.probe || !card.probe.length) {
          out.textContent = T('data.checkNoProbes', 'В данных нет контрольных точек — пересоберите мир.');
          return;
        }
        const img = new Image();
        img.src = (state.world.mapIndex?.titles?.file || 'world-map-titles-ids.png') + build;
        await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; });
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        let ok = 0;
        let tainted = false;
        try {
          ctx.getImageData(0, 0, 1, 1);
        } catch (error) {
          tainted = true;
        }
        if (tainted) {
          out.textContent = T('data.checkNeedServer', 'Откройте через start.cmd: браузер не даёт читать карту с диска.');
          return;
        }
        for (const point of card.probe) {
          const d = ctx.getImageData(point.x, point.y, 1, 1).data;
          const idx = (d[0] << 16) | (d[1] << 8) | d[2];
          if (card.counties[idx - 1] === point.key) ok += 1;
        }
        out.textContent = `${ok} / ${card.probe.length}`;
      } catch (error) {
        out.textContent = String(error && error.message ? error.message : error);
      }
    });
  }

  const book = el('bookRoot');
  if (book) {
    el('downloadBook')?.addEventListener('click', () => download('svod-roda.md', bookText()));
  }

  if (el('dossierText')) {
    el('copyDossier')?.addEventListener('click', () => copy(dossierText()).then((ok) => toast(ok ? 'Досье скопировано' : 'Не удалось скопировать')));
    el('downloadDossier')?.addEventListener('click', () => download('dosie.md', dossierText()));
  }

}
function branchesText(meta) {
  const houses = state.world.dynasty?.houses || [];
  if (!houses.length) return '';
  // Цвет дома тот же, что на политической карте: цвет значит одно и то же везде.
  const colors = new Map((state.world.mapIndex?.political?.groups || []).map((g) => [g.house, g.color]));
  const parts = houses.map((h) => {
    const color = colors.get(h.name);
    const chip = color ? `<i class="branch-dot" style="background:${color}"></i>` : '';
    const role = h.senior ? T('tree.seniorHouse', 'старший дом') : h.player ? T('tree.yourHouse', 'ваш дом') : T('tree.cadetHouse', 'кадетская');
    return `${chip}${esc(h.name)} — ${h.members}, ${role}${h.from ? `, ${h.from}—${h.to ?? '…'}` : ''}`;
  });
  return `<span class="eyebrow">${T('tree.branches', 'ветви')}</span> ${parts.join(' · ')}`;
}
/* ---------- данные ---------- */

function viewImport() {
  return importerMarkup();
}
function viewData() {
  const { meta } = state.world;
  return `
      <div class="page-head"><h1>${T('data.title', 'Данные')}</h1><p>${T('data.lead', 'Откуда взят мир и как пересобрать его для другого сейва.')}</p></div>
      <div class="grid grid--2">
        <section class="card">
          <div class="eyebrow">${T('data.current', 'Текущий мир')}</div>
          <div style="font-family:var(--font-display);font-size:var(--step-3);margin:8px 0 4px">${esc(dateText(meta.date))}</div>
          <p class="small muted">${T('data.file', 'Файл')}: <code>${esc(meta.source)}</code></p>
          <p class="small muted">${T('data.build', 'Сборка')}: <code>${esc(meta.build || '—')}</code> · ${T('data.counties', 'графств на карте')}: ${state.world.mapIndex?.titles?.counties ?? '—'}</p>
          <p><button class="btn btn--ghost btn--small" type="button" id="checkMap">${T('data.checkMap', 'Проверить карту')}</button>
             <span class="small muted" id="checkMapResult"></span></p>
          <div class="kv"><span>${T('data.realms', 'Держав')}</span><b class="num">${meta.counts.realms}</b></div>
          <div class="kv"><span>${T('data.known', 'В поле зрения')}</span><b class="num">${meta.counts.known}</b></div>
          <div class="kv"><span>${T('data.dynasty', 'Династия')}</span><b class="num">${meta.counts.dynasty}</b></div>
          <div class="kv"><span>${T('data.people', 'В дереве')}</span><b class="num">${meta.counts.people}</b></div>
          <div class="kv"><span>${T('data.events', 'Событий')}</span><b class="num">${meta.counts.events}</b></div>
          <p class="small muted" style="margin-top:10px">${T('data.importNote', 'Своё сохранение подключается на экране «Своё сохранение»: выберите файл .ck3 и папку игры — мир и карта соберутся сами.')}</p>
          <p><a class="btn btn--ghost btn--small" href="#import" data-nav="import">${T('data.toImport', 'Открыть импорт')}</a></p>
          <p class="small muted">${T('data.mapNote', 'Карты в сейве нет: игра хранит её отдельно, в папке game/map_data. Поэтому импортёр и спрашивает папку игры — без неё мир соберётся, но останется только «Карта словами».')}</p>
        </section>
        <section class="card">
          <div class="eyebrow">${T('data.how', 'Как пересобрать')}</div>
          <ol class="facts" style="padding-left:18px;margin-top:8px">
            <li>${T('data.step1', 'Дамп сейва экстрактором')}:
              <code class="code-block">ck3_history_extractor.exe "сейв.ck3" -g "…\\Crusader Kings III\\game" -l russian -o out -n --dump out\\gamestate.json</code></li>
            <li>${T('data.step2', 'Мир и карта')}:
              <code class="code-block">python tools/build_world.py --dump out\\gamestate.json -o app\\_data\\world.json --map app\\_data\\world-map.png</code></li>
            <li>${T('data.step3', 'Обновите страницу.')}</li>
          </ol>
          <p class="small muted" style="margin-top:10px">${T('data.cacheNote', 'Нужны кэши карты: knowledge_pilot.py map и adjacency.')}</p>
        </section>
      </div>`;
}
/* ---------- служебное ---------- */

function paintLang() {
  const lang = window.currentLang ? window.currentLang() : 'ru';
  for (const button of document.querySelectorAll('.lang[data-lang]')) {
    const on = button.dataset.lang === lang;
    button.classList.toggle('is-on', on);
    button.setAttribute('aria-pressed', String(on));
  }
}
function bind() {
  for (const button of document.querySelectorAll('.lang[data-lang]')) {
    button.addEventListener('click', () => {
      setLang(button.dataset.lang);
      applyI18n();
      paintLang();
      render();
    });
  }

  document.addEventListener('click', (ev) => {
    const nav = ev.target.closest('[data-nav]');
    if (nav) { ev.preventDefault(); setView(nav.dataset.nav); return; }
  });
  window.addEventListener('hashchange', () => {
    const view = location.hash.replace('#', '') || 'tree';
    if (view !== state.view) setView(view);
  });
  el('loadData').addEventListener('click', () => el('loadDialog').showModal());
  el('fileInput').addEventListener('change', (ev) => loadFile(ev.target.files?.[0]));
}
async function loadFile(file) {
  if (!file) return;
  const error = el('loadError');
  error.hidden = true;
  try {
    const data = JSON.parse(await file.text());
    if (!data.meta || !data.people) throw new Error('Это не world.json — соберите его через build_world.py.');
    el('loadDialog').close();
    state.settings.from = null;
    state.settings.to = null;
    startWith(data);
    toast('Мир загружен');
  } catch (err) {
    error.hidden = false;
    error.textContent = err.message.includes('JSON') ? 'Файл повреждён или это не JSON.' : err.message;
  }
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const area = document.createElement('textarea');
    area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.append(area); area.select();
    const ok = document.execCommand('copy'); area.remove();
    return ok;
  }
}
function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
let toastTimer = null;
function toast(message) {
  const node = el('toast');
  node.textContent = message;
  node.dataset.show = '1';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.dataset.show = '0'), 2400);
}
