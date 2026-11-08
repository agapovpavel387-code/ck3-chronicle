/* Хроника рода · мир.
 *
 * Экран «Мир»: две линзы, кольца знания, политическая карта, наведение.
 * Зависит: core, model.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
// Направления приходят из мира по-русски — это данные сборки, а не подписи.
const DIR_EN = {
  'север': 'north', 'северо-восток': 'north-east', 'восток': 'east', 'юго-восток': 'south-east',
  'юг': 'south', 'юго-запад': 'south-west', 'запад': 'west', 'северо-запад': 'north-west',
};
function dirText(value) {
  if (!value) return '';
  const lang = window.currentLang ? window.currentLang() : 'ru';
  return lang === 'en' ? (DIR_EN[value] || value) : value;
}

function viewWorld() {
  const { meta } = state.world;
  const realms = state.world.realms || [];
  const byRing = new Map();
  for (const r of realms) {
    if (!byRing.has(r.ring)) byRing.set(r.ring, []);
    byRing.get(r.ring).push(r);
  }

  const blocks = [0, 1, 2, 3]
    .filter((ring) => byRing.has(ring))
    .map((ring) => {
      const list = byRing.get(ring).sort((a, b) => (a.distance ?? 1e9) - (b.distance ?? 1e9));
      const title = [T('world.ring0', 'Своё'), T('world.ring1', 'Ближний круг'), T('world.ring2', 'Средний круг'), T('world.ring3', 'Дальний круг')][ring];
      return `<section class="ring-block">
          <div class="ring-block__head"><h2>${title}</h2><span class="small">${T('world.ringShort', 'кольцо')} ${ring} · ${list.length}</span></div>
          <div class="courts">
            ${list.map((r) => `<article class="court">
              <div class="court__top">
                <span class="court__name">${esc(r.name)}</span>
                <span class="court__dist">${r.distance != null ? r.distance + ' px' : ''}${r.bySea ? ` · ${T('world.bySea', 'морем')}` : ''}</span>
              </div>
              <p class="court__what${r.ring >= 3 ? ' court__what--faint' : ''}">${esc(knownLine(r))}</p>
              <p class="court__meta">${esc(dirText(r.direction || ''))}${r.size ? ` · ${T('world.holdings', 'владений')} ${r.size}` : ''}${r.prestige ? ` · ${T('world.prestigeShort', 'слава')} ${r.prestige}` : ''}</p>
              ${r.faith ? `<p class="court__meta">${T('world.faith', 'вера')} — ${esc(r.faith)}${r.faithShare ? ` (${Math.round(r.faithShare * 100)}%)` : ''}${r.culture ? ` · ${esc(r.culture)}` : ''}</p>` : ''}
            </article>`).join('')}
          </div>
        </section>`;
    })
    .join('');

  const camps = (state.world.people || []).filter((p) => p.kin && p.camp);
  const campsBlock = camps.length
    ? `<section class="ring-block">
           <div class="ring-block__head"><h2>${T('world.camps', 'Вольные отряды')}</h2><span class="small">${camps.length}</span></div>
           <p class="small muted">${T('world.campsNote', 'Родичи без надела, что живут войной и удачей. Двор знает о них по слухам и письмам.')}</p>
           <div class="courts">${camps.map((p) => `<article class="court">
             <div class="court__top"><span class="court__name">${esc(nameOf(p))}</span><span class="court__dist">${esc(p.campAt || '')}</span></div>
             <p class="court__what">${esc(p.campName ? `${T('world.camp', 'отряд')} «${p.campName}»` : T('world.freeCamp', 'вольный отряд'))}</p>
             <p class="court__meta">${esc(p.death ? `${T('world.diedIn', 'погиб в')} ${y0(p.death)}` : T('world.alive', 'жив'))}${p.branch ? ` · ${esc(p.branch)}` : ''}</p>
           </article>`).join('')}</div>
         </section>`
    : '';

  const rumors = meta.byRing[4] ?? 0;
  const political = state.world.mapIndex?.political || null;
  const houseLayer = political?.houses || null;
  const familyLayer = political?.family || null;
  const layer = state.mapLayer === 'family' && familyLayer ? 'family' : 'houses';
  const titlesLayer = state.world.mapIndex?.titles || null;
  const lens = state.lens === 'titles' && titlesLayer
    ? 'titles'
    : state.lens === 'political' && (houseLayer || familyLayer) ? 'political' : 'radius';

  const lensButtons = houseLayer || familyLayer || titlesLayer
    ? `<div class="lens-switch" role="tablist" aria-label="${T('world.lensAria', 'Линза карты')}">
           <button class="lens${lens === 'radius' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${lens === 'radius'}" data-lens="radius">${T('world.lens.radius', 'Радиус знания')}</button>
           <button class="lens${lens === 'political' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${lens === 'political'}" data-lens="political"${houseLayer || familyLayer ? '' : ' hidden'}>${T('world.lens.political', 'Политическая')}</button>
           ${titlesLayer ? `<button class="lens${lens === 'titles' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${lens === 'titles'}" data-lens="titles">${T('world.lensTitles', 'Титулы')}</button>` : ''}
         </div>`
    : '';

  const layerButtons = lens === 'political' && familyLayer
    ? `<div class="lens-switch lens-switch--layer" role="tablist" aria-label="${T('world.layerAria', 'Слой политической карты')}">
           <button class="lens lens--small${layer === 'houses' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${layer === 'houses'}" data-layer="houses">${T('world.layer.houses', 'По домам')}</button>
           <button class="lens lens--small${layer === 'family' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${layer === 'family'}" data-layer="family">${T('world.layer.family', 'Земли рода')}</button>
         </div>`
    : '';

  const ROLE_RU = { player: T('world.rolePlayer', 'ваш дом'), senior: T('world.roleSenior', 'старший дом'), cadet: T('world.roleCadet', 'кадетская ветвь') };
  const groups = familyLayer?.groups || [];
  const housesLegend = houseLayer?.houses || [];

  const houseLegend = layer === 'houses' && housesLegend.length
    ? `<figcaption class="map-legend map-legend--political"${lens === 'political' ? '' : ' hidden'}>
           ${housesLegend.map((h) => `<span><i style="background:${h.color}"></i>${esc(h.house || T('world.houseNoName', 'дом без имени'))}${h.player ? ` · ${T('world.yourHouse', 'ваш дом')}` : h.dynasty ? ' · ваша династия' : ''} · ${h.realms} ${plural(h.realms, 'держава', 'державы', 'держав')}</span>`).join('')}
           <span class="muted">${T('world.houseLayerNote', 'цвет — дом правителя; рубежи — по кольцу знания')}</span>
         </figcaption>`
    : '';

  const familyLegend = layer === 'family' && groups.length
    ? `<figcaption class="map-legend map-legend--political"${lens === 'political' ? '' : ' hidden'}>
           ${groups.map((g) => `<div class="lens-house">
              <p class="lens-house__head"><i style="background:${g.color}"></i><b>${esc(g.house || T('world.houseNoName', 'дом без имени'))}</b><span class="lens-house__role">${ROLE_RU[g.role] || 'ветвь'}</span><span class="lens-house__sum">${g.counties} ${plural(g.counties, 'графство', 'графства', 'графств')}, ${g.rulers.length} ${plural(g.rulers.length, 'правитель', 'правителя', 'правителей')}</span></p>
              <p class="lens-house__rulers">${g.rulers.map((r) => `<span><b class="lens-num">${r.num}</b>${esc(r.ruler || T('world.noName', 'без имени'))}<em>${r.counties}</em></span>`).join('')}</p>
            </div>`).join('')}
           <p class="lens-note">${T('world.foreignBorders', 'прочие державы — только границами')}</p>
         </figcaption>`
    : '';

  const noLandNote = lens === 'political' && layer === 'family' && !groups.length
    ? `<figcaption class="map-legend map-legend--political"><span>${T('world.noLand', 'Род не держит земли — смотрите слой «По домам».')}</span></figcaption>`
    : '';

  const emptyPolitical = lens === 'political' && !houseLayer && !familyLayer
    ? `<figcaption class="map-legend map-legend--political"><span>${T('world.noMap', 'Для этого мира политическая карта не собрана.')}</span></figcaption>`
    : '';

  const titlesLegend = titlesLayer
    ? `<figcaption class="map-legend map-legend--titles"${lens === 'titles' ? '' : ' hidden'}>
         <span><i class="tier-line tier-line--empire"></i>${T('world.tierEmpire', 'империя')}</span>
         <span><i class="tier-line tier-line--kingdom"></i>${T('world.tierKingdom', 'королевство')}</span>
         <span><i class="tier-line tier-line--duchy"></i>${T('world.tierDuchy', 'герцогство')}</span>
         <span><i class="tier-line tier-line--county"></i>${T('world.tierCounty', 'графство')}</span>
         <span class="muted">${T('world.titlesNote', 'все титулы, кроме баронств; щёлкните, чтобы увидеть цепочку')}</span>
         <span class="muted">${T('world.zoomHint', 'колесо — масштаб, перетаскивание — сдвиг')}</span>
       </figcaption>`
    : '';

  const build = meta.build || '';
  const v = build ? `?v=${build}` : '';
  const currentFile = lens === 'titles'
    ? (titlesLayer?.map || meta.map)
    : lens === 'political'
      ? (layer === 'family' ? familyLayer?.file : houseLayer?.file) || meta.map
      : meta.map;

  const map = meta.map
    ? `<figure class="map-figure" id="mapFigure">
           ${lensButtons}${layerButtons}
           <div class="map-wrap" id="mapWrap">
             <img id="worldMap" src="_data/${esc(currentFile)}${v}" alt="${T('world.mapAlt', 'Карта мира')}" loading="lazy" data-lens="${lens}" data-layer="${layer}" tabindex="0">
             <div class="map-tip" id="mapTip" hidden></div>
             <div class="map-zoom" role="group" aria-label="${T('world.zoomAria', 'Масштаб карты')}">
               <button type="button" data-zoom="in" aria-label="${T('world.zoomIn', 'Приблизить')}">+</button>
               <button type="button" data-zoom="out" aria-label="${T('world.zoomOut', 'Отдалить')}">−</button>
               <button type="button" data-zoom="reset" aria-label="${T('world.zoomReset', 'Сбросить масштаб')}">${T('world.zoomResetShort', 'Сброс')}</button>
             </div>
           </div>
           <figcaption class="map-legend"${lens !== 'radius' ? ' hidden' : ''}>
             <span><i style="background:#191713"></i>${T('world.legendOwn', 'своё')}</span>
             <span><i style="background:#4a4335"></i>${T('world.legendNear', 'ближний')}</span>
             <span><i style="background:#8a7f68"></i>${T('world.legendMiddle', 'средний')}</span>
             <span><i style="background:#bdb29a"></i>${T('world.legendFar', 'дальний')}</span>
             <span><i style="background:#e0d8c6"></i>${T('world.legendHearsay', 'молва')}</span>
           </figcaption>
           ${houseLegend}${familyLegend}${titlesLegend}${noLandNote}${emptyPolitical}
           <div class="map-detail" id="mapDetail" hidden></div>
         </figure>`
    : '';

  return `
      <div class="page-head"><h1>${T('world.title', 'Мир')}</h1>
        <p>${T('world.subtitle', 'Что род знает о других дворах. Чем дальше — тем меньше: имя, потом только титул, потом молва.')}</p></div>
      ${map}
      ${campsBlock}
      ${blocks}
      <div class="rumor"><b>${T('world.rumorTitle', 'Молва')}: ${rumors} ${T('world.rumorRealms', 'держав')}.</b> ${T('world.rumorNote', 'За третьим кольцом род знает только то, что где-то есть государи. Их имена не записываются — это не ошибка летописи, а её честность.')}</div>`;
}
/* ---------- карта: наведение ---------- */

const ringLabel = (index) => [
  T('world.ring0', 'своё'),
  T('world.ring1', 'ближний круг'),
  T('world.ring2', 'средний круг'),
  T('world.ring3', 'дальний круг'),
  T('world.ring4', 'молва'),
][index] || T('world.ring4', 'молва');
let titlesCard = null;
let titlesLoading = null;
// Карта титулов грузится один раз и только когда её открыли.
function loadTitlesCard() {
  if (titlesCard) return Promise.resolve(titlesCard);
  if (!titlesLoading) {
    const tag = state.world.meta?.build ? `?v=${state.world.meta.build}` : '';
    titlesLoading = fetch('_data/titles-map.json' + tag)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { titlesCard = data; return data; })
      .catch(() => null);
  }
  return titlesLoading;
}

const MAP_TIER_RU = () => ({ c: T('world.tierCounty', 'графство'), d: T('world.tierDuchy', 'герцогство'), k: T('world.tierKingdom', 'королевство'), e: T('world.tierEmpire', 'империя') });
const tierOfKey = (key) => (key ? (key[0] === 'c' ? 'c' : key[0] === 'd' ? 'd' : key[0] === 'k' ? 'k' : 'e') : null);

function setupMap() {
  const mapIndex = state.world.mapIndex || state.world.meta.mapIndex;
  if (!mapIndex) return;
  const img = el('worldMap');
  const tip = el('mapTip');
  const detail = el('mapDetail');
  const wrap = el('mapWrap');
  if (!img || !tip || !detail) return;
  const pick = new Image();
  const buffer = document.createElement('canvas');
  let ctx = null;

  pick.addEventListener('load', () => {
    buffer.width = pick.naturalWidth;
    buffer.height = pick.naturalHeight;
    ctx = buffer.getContext && buffer.getContext('2d', { willReadFrequently: true });
    if (ctx) ctx.drawImage(pick, 0, 0);
  });
  const political = state.world.mapIndex?.political;
  const titles = state.world.mapIndex?.titles;
  const layer = state.mapLayer === 'family' && political?.family ? 'family' : 'houses';
  const lens = state.lens === 'titles' && titles
    ? 'titles'
    : state.lens === 'political' && political
      ? 'political'
      : 'radius';
  const pickFile = lens === 'titles'
    ? (titles.index || titles.file)
    : lens === 'political'
      ? (political?.[layer]?.index || political?.houses?.index || mapIndex.file)
      : mapIndex.file;
  const buildTag = state.world.meta?.build || '';
  pick.src = '_data/' + pickFile + (buildTag ? `?v=${buildTag}` : '');

  if (lens === 'titles') loadTitlesCard();

  // --- масштаб ---
  const wrapEl = wrap || img.parentElement;
  let zoom = { s: 1, x: 0, y: 0 };
  let dragged = false;
  const applyZoom = () => {
    img.style.transform = `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.s})`;
    wrapEl.classList.toggle('is-zoomed', zoom.s > 1.01);
  };
  const clampZoom = () => {
    zoom.s = Math.min(4, Math.max(1, zoom.s));
    if (zoom.s <= 1.001) { zoom.x = 0; zoom.y = 0; }
    if (wrapEl) {
      const rect = wrapEl.getBoundingClientRect();
      const maxX = Math.max(0, (rect.width * (zoom.s - 1)) / 2);
      const maxY = Math.max(0, (rect.height * (zoom.s - 1)) / 2);
      zoom.x = Math.min(maxX, Math.max(-maxX, zoom.x));
      zoom.y = Math.min(maxY, Math.max(-maxY, zoom.y));
    }
    applyZoom();
  };
  const setZoom = (next, cx, cy) => {
    const prev = zoom.s;
    zoom.s = next;
    if (cx != null && wrapEl) {
      const rect = wrapEl.getBoundingClientRect();
      const dx = cx - rect.left - rect.width / 2;
      const dy = cy - rect.top - rect.height / 2;
      const ratio = zoom.s / prev - 1;
      zoom.x -= dx * ratio;
      zoom.y -= dy * ratio;
    }
    clampZoom();
  };

  if (wrapEl) {
    wrapEl.addEventListener('wheel', (ev) => {
      ev.preventDefault();
      setZoom(zoom.s * Math.exp(-ev.deltaY * 0.0015), ev.clientX, ev.clientY);
    }, { passive: false });

    let panning = false;
    let startX = 0;
    let startY = 0;
    let originX = 0;
    let originY = 0;
    wrapEl.addEventListener('pointerdown', (ev) => {
      if (zoom.s <= 1.001) return;
      panning = true;
      dragged = false;
      startX = ev.clientX; startY = ev.clientY;
      originX = zoom.x; originY = zoom.y;
      wrapEl.setPointerCapture?.(ev.pointerId);
    });
    wrapEl.addEventListener('pointermove', (ev) => {
      if (!panning) return;
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (Math.abs(dx) + Math.abs(dy) > 5) dragged = true;
      zoom.x = originX + dx;
      zoom.y = originY + dy;
      clampZoom();
    });
    const stopPan = () => { panning = false; };
    wrapEl.addEventListener('pointerup', stopPan);
    wrapEl.addEventListener('pointercancel', stopPan);
    wrapEl.addEventListener('pointerleave', stopPan);
  }

  for (const btn of document.querySelectorAll('[data-zoom]')) {
    btn.addEventListener('click', () => {
      if (btn.dataset.zoom === 'in') setZoom(zoom.s * 1.4);
      else if (btn.dataset.zoom === 'out') setZoom(zoom.s / 1.4);
      else { zoom = { s: 1, x: 0, y: 0 }; applyZoom(); }
    });
  }

  img.addEventListener('keydown', (ev) => {
    if (ev.key === '+' || ev.key === '=') { setZoom(zoom.s * 1.4); ev.preventDefault(); }
    else if (ev.key === '-' || ev.key === '_') { setZoom(zoom.s / 1.4); ev.preventDefault(); }
    else if (ev.key === '0' || ev.key === 'Home') { zoom = { s: 1, x: 0, y: 0 }; applyZoom(); ev.preventDefault(); }
    else if (ev.key === 'ArrowLeft') { zoom.x += 40; clampZoom(); ev.preventDefault(); }
    else if (ev.key === 'ArrowRight') { zoom.x -= 40; clampZoom(); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp') { zoom.y += 40; clampZoom(); ev.preventDefault(); }
    else if (ev.key === 'ArrowDown') { zoom.y -= 40; clampZoom(); ev.preventDefault(); }
  });

  const indexAt = (ev) => {
    if (!ctx) return 0;
    const rect = img.getBoundingClientRect();
    if (!rect.width) return 0;
    const x = Math.floor(((ev.clientX - rect.left) / rect.width) * buffer.width);
    const y = Math.floor(((ev.clientY - rect.top) / rect.height) * buffer.height);
    if (x < 0 || y < 0 || x >= buffer.width || y >= buffer.height) return 0;
    const d = ctx.getImageData(x, y, 1, 1).data;
    return (d[0] << 16) | (d[1] << 8) | d[2];
  };

  const realmAt = (ev) => {
    const index = indexAt(ev);
    return index ? mapIndex.realms[String(index)] || null : null;
  };

  // Цепочка титулов: графство → герцогство → королевство → империя.
  const UNTITLED = 0xffffff;
  const titleAt = async (ev) => {
    const index = indexAt(ev);
    if (!index) return null;
    if (index === UNTITLED) return { untitled: true };
    const card = await loadTitlesCard();
    if (!card || !card.counties) return null;
    // Карта и данные должны быть от одной сборки: иначе клик покажет чужой титул.
    const expected = state.world.mapIndex?.titles?.counties;
    if (expected && card.counties.length !== expected) {
      detail.hidden = false;
      detail.innerHTML = `<b>${T('world.mapMismatch', 'Карта и данные не совпадают')}</b>
          <p class="small muted">${T('world.mapMismatchNote', 'Пересоберите мир: build_world.py пишет карту и данные вместе.')}</p>`;
      return null;
    }
    const key = card.counties[index - 1];
    if (!key) return null;
    // Феодальная цепочка: держатель → его сюзерен → … → независимый.
    const lords = card.lords || {};
    const people = [];
    let cur = card.owners?.[key] ?? null;
    const seen = new Set();
    while (cur && !seen.has(cur) && people.length < 6) {
      seen.add(cur);
      const rec = lords[String(cur)];
      if (!rec) break;
      people.push({ id: cur, ...rec });
      cur = rec.liege;
    }
    return {
      key,
      name: card.names?.[key] || key,
      chain: (card.chain?.[index - 1] || []).map((k) => ({ key: k, name: card.names?.[k] || k })),
      owner: card.owners?.[key] ?? null,
      people,
    };
  };

  // Кому подчиняется: держатель → сюзерен → … → независимый.
  const vassalLine = (title) => {
    const people = title.people || [];
    if (!people.length) return '';
    if (people.length === 1) return T('world.independent', 'Никому не подчиняется: независимый правитель.');
    const names = people.slice(1).map((p) => esc(p.name)).join(' → ');
    return `${T('world.vassalOf', 'Сюзерены')}: ${names}${people[people.length - 1].liege ? ` → ${T('world.above', 'выше не записано')}` : ` (${T('world.topSuzerain', 'верхний — независимый')})`}.`;
  };

  const titleCard = (title) => {
    const owner = title.owner ? ix.people.get(title.owner) : null;
    // Держатель не всегда в дереве рода: имя берём из общего справочника.
    const ownerRec = title.owner ? ix.names.get(title.owner) : null;
    const ownerName = owner ? nameOf(owner) : (ownerRec && ownerRec.name ? ownerRec.name : '');
    const ownerHouse = (owner && owner.house) || (ownerRec && ownerRec.house) || '';
    const chain = title.chain.length
      ? title.chain.map((t) => `${(MAP_TIER_RU())[tierOfKey(t.key)] || T('world.tierFallback', 'титул')} — ${esc(t.name)}`).join(' · ')
      : T('world.noSeniors', 'старших титулов нет: вольное графство');
    detail.hidden = false;
    detail.innerHTML = `<b>${esc(title.name)}</b> <span class="small muted">${T('world.titleCounty', 'графство')}</span>
        <p class="small">${chain}</p>
        <p class="small muted">${ownerName
          ? `${T('world.holderIs', 'Держатель')} — ${esc(ownerName)}${ownerHouse ? `, ${T('world.houseShort', 'дом')} ${esc(ownerHouse)}` : ''}${ownerRec && ownerRec.birth ? ` (${String(ownerRec.birth).slice(0, 4)}—${ownerRec.death ? String(ownerRec.death).slice(0, 4) : '…'})` : ''}.`
          : T('world.holderUnknown', 'Держатель неизвестен.')}</p>
        <p class="small muted">${vassalLine(title)}</p>
        <p class="small"><a href="#chronicle" data-title-link="${esc(title.key)}">${T('world.openChronicle', 'Смотреть хронику по этому титулу')}</a></p>`;
    const link = detail.querySelector('[data-title-link]');
    if (link) {
      link.addEventListener('click', (ev2) => {
        ev2.preventDefault();
        state.titleFilter = title.key;
        window.location.hash = '#chronicle';
      });
    }
  };

  img.addEventListener('mousemove', (ev) => {
    if (dragged) { tip.hidden = true; return; }
    if (lens === 'titles') {
      if (!ctx) return;
      const index = indexAt(ev);
      if (!index) { tip.hidden = true; img.style.cursor = 'default'; return; }
      if (index === UNTITLED) {
        img.style.cursor = 'default';
        const rectU = img.getBoundingClientRect();
        tip.innerHTML = `<b>${T('world.untitledLand', 'Земля без титула')}</b>`;
        tip.hidden = false;
        tip.style.left = Math.max(8, Math.min(ev.clientX - rectU.left, rectU.width - 170)) + 'px';
        tip.style.top = Math.max(8, ev.clientY - rectU.top - 12) + 'px';
        return;
      }
      const card = titlesCard;
      const key = card?.counties?.[index - 1];
      if (!key) { tip.hidden = true; img.style.cursor = 'default'; return; }
      img.style.cursor = 'pointer';
      const rect = img.getBoundingClientRect();
      const chain = (card.chain?.[index - 1] || []).map((k) => card.names?.[k] || k);
      tip.innerHTML = `<b>${esc(card.names?.[key] || key)}</b><span>${esc(chain[0] || T('world.freeCounty', 'вольное графство'))}</span>`;
      tip.hidden = false;
      const left = Math.max(8, Math.min(ev.clientX - rect.left, rect.width - 190));
      tip.style.left = left + 'px';
      tip.style.top = Math.max(8, ev.clientY - rect.top - 12) + 'px';
      return;
    }
    const realm = realmAt(ev);
    if (!realm) { tip.hidden = true; img.style.cursor = 'default'; return; }
    img.style.cursor = 'pointer';
    const rect = img.getBoundingClientRect();
    const ring = ringLabel(realm.ring) || T('world.ring4', 'молва');
    tip.innerHTML = `<b>${esc(realm.name)}</b><span>${ring}${realm.distance != null ? ` · ${realm.distance} px` : ''}${realm.direction ? ` · ${esc(realm.direction)}` : ''}</span>`;
    tip.hidden = false;
    const left = Math.max(8, Math.min(ev.clientX - rect.left, rect.width - 170));
    tip.style.left = left + 'px';
    tip.style.top = Math.max(8, ev.clientY - rect.top - 12) + 'px';
  });

  img.addEventListener('mouseleave', () => { tip.hidden = true; });

  img.addEventListener('click', async (ev) => {
    if (dragged) { dragged = false; return; }
    if (lens === 'titles') {
      const title = await titleAt(ev);
      if (!title) { detail.hidden = true; return; }
      if (title.untitled) {
        detail.hidden = false;
        detail.innerHTML = `<b>${T('world.untitledLand', 'Земля без титула')}</b>
            <p class="small muted">${T('world.untitledLandNote', 'Провинция есть, но графства у неё в сейве нет — записывать нечего.')}</p>`;
        return;
      }
      titleCard(title);
      return;
    }
    const realm = realmAt(ev);
    if (!realm) { detail.hidden = true; return; }
    const ring = ringLabel(realm.ring) || T('world.ring4', 'молва');
    const ruler = realm.ring <= 2 && realm.ruler ? `${T('world.rulerIs', 'Государь —')} ${esc(realm.ruler)}${realm.house && !realm.house.startsWith('House') ? `, ${T('world.houseShort', 'дом')} ${esc(realm.house)}` : ''}.` : '';
    const knows = realm.ring <= 1
      ? T('world.knownDetailed', 'Род знает о нём подробно: имя, дом, годы, владения.')
      : realm.ring === 2
        ? T('world.knownNameTitle', 'Имя и титул известны, остальное — нет.')
        : realm.ring === 3
          ? T('world.knownTitleOnly', 'Только титул; имени не записали.')
          : T('world.knownHearsay', 'Только молва: где-то там есть государь.');
    detail.hidden = false;
    detail.innerHTML = `<b>${esc(realm.name)}</b> <span class="small muted">${ring}${realm.size ? ` · ${T('world.holdings', 'владений')} ${realm.size}` : ''}</span>
        <p class="small">${knows}${ruler ? ` ${ruler}` : ''}</p>`;
  });
}
