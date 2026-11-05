/* Хроника рода · мир.
 *
 * Экран «Мир»: две линзы, кольца знания, политическая карта, наведение.
 * Зависит: core, model.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
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
      const title = ['Своё', 'Ближний круг', 'Средний круг', 'Дальний круг'][ring];
      return `<section class="ring-block">
          <div class="ring-block__head"><h2>${title}</h2><span class="small">кольцо ${ring} · ${list.length}</span></div>
          <div class="courts">
            ${list.map((r) => `<article class="court">
              <div class="court__top">
                <span class="court__name">${esc(r.name)}</span>
                <span class="court__dist">${r.distance != null ? r.distance + ' px' : ''}${r.bySea ? ' · морем' : ''}</span>
              </div>
              <p class="court__what${r.ring >= 3 ? ' court__what--faint' : ''}">${esc(knownLine(r))}</p>
              <p class="court__meta">${esc(r.direction || '')}${r.size ? ` · владений ${r.size}` : ''}${r.prestige ? ` · слава ${r.prestige}` : ''}</p>
              ${r.faith ? `<p class="court__meta">вера — ${esc(r.faith)}${r.faithShare ? ` (${Math.round(r.faithShare * 100)}%)` : ''}${r.culture ? ` · ${esc(r.culture)}` : ''}</p>` : ''}
            </article>`).join('')}
          </div>
        </section>`;
    })
    .join('');

  const camps = (state.world.people || []).filter((p) => p.kin && p.camp);
  const campsBlock = camps.length
    ? `<section class="ring-block">
           <div class="ring-block__head"><h2>Вольные отряды</h2><span class="small">${camps.length}</span></div>
           <p class="small muted">Родичи без надела, что живут войной и удачей. Двор знает о них по слухам и письмам.</p>
           <div class="courts">${camps.map((p) => `<article class="court">
             <div class="court__top"><span class="court__name">${esc(nameOf(p))}</span><span class="court__dist">${esc(p.campAt || '')}</span></div>
             <p class="court__what">${esc(p.campName ? `отряд «${p.campName}»` : 'вольный отряд')}</p>
             <p class="court__meta">${esc(p.death ? `погиб в ${y0(p.death)}` : 'жив')}${p.branch ? ` · ${esc(p.branch)}` : ''}</p>
           </article>`).join('')}</div>
         </section>`
    : '';

  const rumors = meta.byRing[4] ?? 0;
  const political = state.world.mapIndex?.political || null;
  const houseLayer = political?.houses || null;
  const familyLayer = political?.family || null;
  const layer = state.mapLayer === 'family' && familyLayer ? 'family' : 'houses';
  const lens = state.lens === 'political' && (houseLayer || familyLayer) ? 'political' : 'radius';

  const lensButtons = houseLayer || familyLayer
    ? `<div class="lens-switch" role="tablist" aria-label="Линза карты">
           <button class="lens${lens === 'radius' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${lens === 'radius'}" data-lens="radius">Радиус знания</button>
           <button class="lens${lens === 'political' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${lens === 'political'}" data-lens="political">Политическая</button>
         </div>`
    : '';

  const layerButtons = lens === 'political' && familyLayer
    ? `<div class="lens-switch lens-switch--layer" role="tablist" aria-label="Слой политической карты">
           <button class="lens lens--small${layer === 'houses' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${layer === 'houses'}" data-layer="houses">По домам</button>
           <button class="lens lens--small${layer === 'family' ? ' is-on' : ''}" type="button" role="tab" aria-selected="${layer === 'family'}" data-layer="family">Земли рода</button>
         </div>`
    : '';

  const ROLE_RU = { player: T('world.rolePlayer', 'ваш дом'), senior: T('world.roleSenior', 'старший дом'), cadet: T('world.roleCadet', 'кадетская ветвь') };
  const groups = familyLayer?.groups || [];
  const housesLegend = houseLayer?.houses || [];

  const houseLegend = layer === 'houses' && housesLegend.length
    ? `<figcaption class="map-legend map-legend--political"${lens === 'political' ? '' : ' hidden'}>
           ${housesLegend.map((h) => `<span><i style="background:${h.color}"></i>${esc(h.house || 'дом без имени')}${h.player ? ' · ваш дом' : h.dynasty ? ' · ваша династия' : ''} · ${h.realms} ${plural(h.realms, 'держава', 'державы', 'держав')}</span>`).join('')}
           <span class="muted">${T('world.houseLayerNote', 'цвет — дом правителя; рубежи — по кольцу знания')}</span>
         </figcaption>`
    : '';

  const familyLegend = layer === 'family' && groups.length
    ? `<figcaption class="map-legend map-legend--political"${lens === 'political' ? '' : ' hidden'}>
           ${groups.map((g) => `<div class="lens-house">
              <p class="lens-house__head"><i style="background:${g.color}"></i><b>${esc(g.house || 'дом без имени')}</b><span class="lens-house__role">${ROLE_RU[g.role] || 'ветвь'}</span><span class="lens-house__sum">${g.counties} ${plural(g.counties, 'графство', 'графства', 'графств')}, ${g.rulers.length} ${plural(g.rulers.length, 'правитель', 'правителя', 'правителей')}</span></p>
              <p class="lens-house__rulers">${g.rulers.map((r) => `<span><b class="lens-num">${r.num}</b>${esc(r.ruler || 'без имени')}<em>${r.counties}</em></span>`).join('')}</p>
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

  const currentFile = lens === 'political'
    ? (layer === 'family' ? familyLayer?.file : houseLayer?.file) || meta.map
    : meta.map;

  const map = meta.map
    ? `<figure class="map-figure" id="mapFigure">
           ${lensButtons}${layerButtons}
           <div class="map-wrap">
             <img id="worldMap" src="_data/${esc(lens === 'political' ? currentFile : meta.map)}" alt="Карта мира" loading="lazy" data-lens="${lens}" data-layer="${layer}">
             <div class="map-tip" id="mapTip" hidden></div>
           </div>
           <figcaption class="map-legend"${lens === 'political' ? ' hidden' : ''}>
             <span><i style="background:#191713"></i>${T('world.legendOwn', 'своё')}</span>
             <span><i style="background:#4a4335"></i>${T('world.legendNear', 'ближний')}</span>
             <span><i style="background:#8a7f68"></i>${T('world.legendMiddle', 'средний')}</span>
             <span><i style="background:#bdb29a"></i>${T('world.legendFar', 'дальний')}</span>
             <span><i style="background:#e0d8c6"></i>${T('world.legendHearsay', 'молва')}</span>
           </figcaption>
           ${houseLegend}${familyLegend}${noLandNote}${emptyPolitical}
           <div class="map-detail" id="mapDetail" hidden></div>
         </figure>`
    : '';

  return `
      <div class="page-head"><h1>${T('world.title', 'Мир')}</h1>
        <p>Что род знает о других дворах. Чем дальше — тем меньше: имя, потом только титул, потом молва.</p></div>
      ${map}
      ${campsBlock}
      ${blocks}
      <div class="rumor"><b>Молва: ${rumors} держав.</b> За третьим кольцом род знает только то, что где-то есть государи. Их имена не записываются — это не ошибка летописи, а её честность.</div>`;
}
/* ---------- карта: наведение ---------- */

const ringLabel = (index) => [
  T('world.ring0', 'своё'),
  T('world.ring1', 'ближний круг'),
  T('world.ring2', 'средний круг'),
  T('world.ring3', 'дальний круг'),
  T('world.ring4', 'молва'),
][index] || T('world.ring4', 'молва');
function setupMap() {
  const mapIndex = state.world.mapIndex || state.world.meta.mapIndex;
  if (!mapIndex) return;
  const img = el('worldMap');
  const tip = el('mapTip');
  const detail = el('mapDetail');
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
  const layer = state.mapLayer === 'family' && political?.family ? 'family' : 'houses';
  const pickFile = state.lens === 'political'
    ? (political?.[layer]?.index || political?.houses?.index || mapIndex.file)
    : mapIndex.file;
  pick.src = '_data/' + pickFile;

  const realmAt = (ev) => {
    if (!ctx) return null;
    const rect = img.getBoundingClientRect();
    if (!rect.width) return null;
    const x = Math.floor(((ev.clientX - rect.left) / rect.width) * buffer.width);
    const y = Math.floor(((ev.clientY - rect.top) / rect.height) * buffer.height);
    if (x < 0 || y < 0 || x >= buffer.width || y >= buffer.height) return null;
    const d = ctx.getImageData(x, y, 1, 1).data;
    const index = (d[0] << 16) | (d[1] << 8) | d[2];
    return mapIndex.realms[String(index)] || null;
  };

  img.addEventListener('mousemove', (ev) => {
    const realm = realmAt(ev);
    if (!realm) { tip.hidden = true; img.style.cursor = 'default'; return; }
    img.style.cursor = 'pointer';
    const rect = img.getBoundingClientRect();
    const ring = ringLabel(realm.ring) || 'молва';
    tip.innerHTML = `<b>${esc(realm.name)}</b><span>${ring}${realm.distance != null ? ` · ${realm.distance} px` : ''}${realm.direction ? ` · ${esc(realm.direction)}` : ''}</span>`;
    tip.hidden = false;
    const left = Math.max(8, Math.min(ev.clientX - rect.left, rect.width - 170));
    tip.style.left = left + 'px';
    tip.style.top = Math.max(8, ev.clientY - rect.top - 12) + 'px';
  });

  img.addEventListener('mouseleave', () => { tip.hidden = true; });

  img.addEventListener('click', (ev) => {
    const realm = realmAt(ev);
    if (!realm) { detail.hidden = true; return; }
    const ring = ringLabel(realm.ring) || 'молва';
    const ruler = realm.ring <= 2 && realm.ruler ? `Государь — ${esc(realm.ruler)}${realm.house && !realm.house.startsWith('House') ? `, дом ${esc(realm.house)}` : ''}.` : '';
    const knows = realm.ring <= 1
      ? 'Род знает о нём подробно: имя, дом, годы, владения.'
      : realm.ring === 2
        ? 'Имя и титул известны, остальное — нет.'
        : realm.ring === 3
          ? 'Только титул; имени не записали.'
          : 'Только молва: где-то там есть государь.';
    detail.hidden = false;
    detail.innerHTML = `<b>${esc(realm.name)}</b> <span class="small muted">${ring}${realm.size ? ` · владений ${realm.size}` : ''}</span>
        <p class="small">${knows}${ruler ? ` ${ruler}` : ''}</p>`;
  });
}
