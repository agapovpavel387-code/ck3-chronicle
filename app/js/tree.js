/* Хроника рода · род · экран.
 *
 * Экран «Род»: конспект по слоям, полотно с линиями, карточка человека.
 * Зависит: core, model.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
const lineKind = (kind) => ({
  trunk: T('tree.trunk', 'ствол'),
  senior: T('tree.lineSenior', 'старшая линия'),
  cadet: T('tree.lineCadet', 'кадетская линия'),
  detached: T('tree.lineDetached', 'отдельная ветвь'),
}[kind] || '');
function lineChips() {
  const lines = orderedLines();
  if (!lines.length) return '';
  const active = state.tree.activeLine ?? lineage().playerLine;
  const chips = lines.map((line) => {
    const on = line.id === active;
    return `<button class="line-chip${on ? ' is-on' : ''}" type="button" aria-pressed="${Boolean(on)}" data-line="${line.id}" title="${esc(lineKind(line.kind) || T('tree.line', 'линия'))}">
        <i style="background:${lineColor(line)}"></i>
        <span class="line-chip__name">${esc(line.founder)}</span>
        <span class="line-chip__meta">${esc(y0(line.birth) || '?')} · ${line.size}</span>
      </button>`;
  });
  return `<div class="line-chips" role="group" aria-label="${T('tree.linesAria', 'Линии рода')}">${chips.join('')}</div>`;
}
function viewTree() {
  const { meta } = state.world;
  const people = treePeople();
  const list = state.tree.list;
  const mode = state.tree.mode || 'outline';
  const trunk = (state.world.people || []).find((p) => p.id === lineage().trunk);
  const lines = lineage().lines;

  return `
      <div class="tree-toolbar">
        <div>
          <p class="eyebrow">${T('tree.dynasty', 'династия')} · ${esc(meta.player.dynasty || meta.player.house || '')}${trunk ? ` · ${T('tree.trunk', 'ствол')} ${esc(trunk.name)}` : ''}</p>
          <h1 class="tree-title">${esc(meta.player.dynasty || meta.player.house || 'Род')} <span class="tree-title__kind">${lines.length} ${plural(lines.length, 'линия', 'линии', 'линий', 'line', 'lines')} · ${people.length} ${plural(people.length, 'человек', 'человека', 'человек', 'person', 'people')}</span></h1>
        </div>
        <div class="tree-tools">
          <label class="search search--small">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m15.5 15.5 4 4"/></svg>
            <span class="sr-only">${T('tree.search', 'Поиск по имени')}</span>
            <input type="search" id="treeSearch" placeholder="${T('tree.searchShort', 'Имя')}" value="${esc(state.tree.query)}">
          </label>
          <button class="btn btn--ghost btn--small" type="button" id="treeMode">${mode === 'outline' ? T('tree.mode.canvas', 'Полотно') : T('tree.mode.outline', 'Конспект')}</button>
          ${mode === 'outline'
            ? `<button class="btn btn--ghost btn--small" type="button" id="treeExpand">${T('tree.expand', 'Развернуть')}</button>
               <button class="btn btn--ghost btn--small" type="button" id="treeCollapse">${T('tree.collapse', 'Свернуть')}</button>`
            : `<button class="btn btn--ghost btn--small" type="button" id="zoomOut" aria-label="${T('tree.zoomOut', 'Уменьшить')}">−</button>
               <button class="btn btn--ghost btn--small" type="button" id="zoomIn" aria-label="${T('tree.zoomIn', 'Увеличить')}">+</button>
               <button class="btn btn--ghost btn--small" type="button" id="zoomFit">${T('tree.fit', 'Весь род')}</button>`}
        </div>
      </div>
      <div class="tree-branches" id="treeBranches">${branchesText(meta)}</div>
      ${mode === 'outline' ? outlineLegend() : lineChips()}
      <p class="tree-hint small muted" id="treeFocusHint" hidden></p>
      <p class="tree-hint small muted" id="treeSearchHint" hidden></p>
      ${mode === 'outline'
        ? `<div class="outline" id="outlineRoot">${list ? treeList(people) : outlineHtml(people)}</div>`
        : `<div class="tree-canvas" id="treeCanvas">
             <div class="tree-stage" id="treeStage">${treeSvg(people, meta)}</div>
             <aside class="drawer" id="drawer" hidden></aside>
           </div>`}`;
}
function outlineLegend() {
  return `<div class="tree-legend tree-legend--marks">
      <span><b>◆</b> ${T('tree.ownsTitle', 'владеет титулом')}</span>
      <span><b>⚑</b> ${T('tree.warband', T('world.freeCamp', 'вольный отряд'))}</span>
      <span><b>◇</b> ${T('tree.newHouse', 'новый дом')}</span>
      <span><i class="mark-dot"></i> ${T('tree.noLand', T('tree.noLand', 'без земли'))}</span>
      <span class="muted">${T('tree.outlineHint', 'строка — человек, отступ — слой')}</span>
    </div>`;
}
// Дети по кровной линии: только те, кто в роду.
function childrenIndex(people) {
  const ids = new Set(people.map((p) => p.id));
  const index = new Map();
  for (const person of people) {
    const parent = person.blood && ids.has(person.blood) ? person.blood : null;
    if (!parent) continue;
    if (!index.has(parent)) index.set(parent, []);
    index.get(parent).push(person.id);
  }
  for (const list of index.values()) {
    list.sort((a, b) => (yearOf(ix.people.get(a)?.birth) ?? 9999) - (yearOf(ix.people.get(b)?.birth) ?? 9999));
  }
  return index;
}
function defaultOpen(people) {
  const open = new Set();
  const children = childrenIndex(people);
  for (const person of people) {
    const gen = person.gen ?? 0;
    if (gen <= 0 && children.has(person.id)) open.add(person.id);
  }
  // Путь до правителя всегда раскрыт: иначе его не найти.
  let cursor = state.world.meta?.player?.id;
  const guard = new Set();
  while (cursor && !guard.has(cursor)) {
    guard.add(cursor);
    const person = ix.people.get(cursor);
    if (!person) break;
    if (person.blood) open.add(person.blood);
    cursor = person.blood;
  }
  return open;
}
function openSet() {
  if (!state.tree.open) state.tree.open = defaultOpen(treePeople());
  return state.tree.open;
}
function personRow(person, children, open, depth) {
  const kids = children.get(person.id) || [];
  const isOpen = open.has(person.id);
  const line = lineById(person.line);
  const color = lineColor(line);
  const flags = [
    person.landed ? '◆' : '',
    person.camp ? '⚑' : '',
    person.newHouse ? '◇' : '',
  ].filter(Boolean).join(' ');
  const what = person.title || (person.camp ? (person.campName ? `${T('world.camp', T('world.camp', 'отряд'))} «${person.campName}»` : T('world.freeCamp', 'вольный отряд')) : '');
  const role = line && line.founderId === person.id ? (lineKind(line.kind) || '') : '';
  const isPlayer = person.id === state.world.meta?.player?.id;
  const q = (state.tree.query || '').trim().toLowerCase();
  const isMatch = q && nameOf(person).toLowerCase().includes(q);
  return `<li class="kin-item" data-depth="${depth}">
      <div class="kin-row${isPlayer ? ' is-main' : ''}${person.kin ? '' : ' is-foreign'}${isMatch ? ' is-match' : ''}" data-person="${person.id}">
        ${kids.length
          ? `<button class="kin-toggle" type="button" data-toggle="${person.id}" aria-expanded="${isOpen}" aria-label="${isOpen ? 'Свернуть' : 'Раскрыть'} потомков">${isOpen ? '▾' : '▸'}</button>`
          : '<span class="kin-toggle kin-toggle--none" aria-hidden="true">·</span>'}
        <span class="kin-dot" style="background:${color}"></span>
        <button class="kin-name" type="button" data-person="${person.id}">${esc(nameOf(person))}</button>
        <span class="kin-years num">${esc(y0(person.birth) || '?')}—${esc(person.death ? y0(person.death) : '…')}</span>
        ${what ? `<span class="kin-what">${esc(what)}</span>` : ''}
        ${flags ? `<span class="kin-flags">${flags}</span>` : ''}
        ${role ? `<span class="kin-role" style="color:${color}">${esc(role)}</span>` : ''}
        ${kids.length ? `<span class="kin-count">${kids.length}</span>` : ''}
      </div>
      ${kids.length && isOpen
        ? `<ul class="kin-children">${kids.map((id) => (ix.people.get(id) ? personRow(ix.people.get(id), children, open, depth + 1) : '')).join('')}</ul>`
        : ''}
    </li>`;
}
function outlineHtml(people) {
  const children = childrenIndex(people);
  const open = openSet();
  const roots = people
    .filter((p) => !p.blood || !people.some((x) => x.id === p.blood))
    .sort((a, b) => (a.gen ?? 0) - (b.gen ?? 0) || (yearOf(a.birth) ?? 9999) - (yearOf(b.birth) ?? 9999));
  const trunk = lineage().trunk;
  const main = roots.filter((p) => p.id === trunk || (p.gen ?? 0) === 0 && lineage().lines.find((l) => l.founderId === p.id)?.kind !== 'detached');
  const detached = roots.filter((p) => !main.includes(p));

  const block = (title, note, list) => `<section class="outline-block">
      <h2 class="outline-block__title">${esc(title)}${note ? ` <span class="small muted">${esc(note)}</span>` : ''}</h2>
      <ul class="kin-tree">${list.map((p) => personRow(p, children, open, p.gen ?? 0)).join('')}</ul>
    </section>`;

  return [
    block(T('tree.trunkBlock', 'Ствол'), `${main.length} ${plural(main.length, 'ветвь', 'ветви', 'ветвей', 'branch', 'branches')}`, main),
    detached.length ? block(T('tree.detached', 'Отдельные ветви'), T('tree.detachedNote', 'связь со стволом в сейве не сохранилась'), detached) : '',
  ].join('');
}
function treeList(people) {
  const parts = [];
  for (const line of orderedLines()) {
    const list = people.filter((p) => p.line === line.id);
    if (!list.length) continue;
    parts.push(`<section class="gen-block"><h3><span class="branch-dot" style="background:${lineColor(line)}"></span>${esc(line.founder)} · ${esc(lineKind(line.kind) || T('tree.line', 'линия'))} · ${line.size}</h3><ol class="gen-list">`);
    for (const person of list.sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0) || (yearOf(a.birth) ?? 9999) - (yearOf(b.birth) ?? 9999))) {
      const marks = [];
      if (person.landed) marks.push(T('tree.owns', 'владеет'));
      else if (person.camp) marks.push(`${T('card.camp', 'Отряд').toLowerCase()}${person.campName ? ` «${person.campName}»` : ''}`);
      else marks.push(T('tree.noLand', T('tree.noLand', 'без земли')));
      if (person.newHouse) marks.push(T('tree.newHouse', 'новый дом'));
      const titles = (person.titles || []).slice(0, 3).join(', ');
      parts.push(
        `<li><button class="linkish" type="button" data-person="${person.id}">${esc(nameOf(person))}</button>
            <span class="num">${esc(y0(person.birth) || '?')}—${esc(person.death ? y0(person.death) : '…')}</span>
            <span class="small muted">${titles ? `${esc(titles)} · ` : ''}${esc(marks.join(', '))}</span></li>`
      );
    }
    parts.push('</ol></section>');
  }
  return parts.join('');
}
// Раскладка одной линии: листья по порядку, родитель над серединой детей.
function layoutLine(members, founderDepth) {
  const byId = new Map(members.map((p) => [p.id, p]));
  const ids = new Set(members.map((p) => p.id));
  const baseDepth = founderDepth ?? 0;
  const childrenOf = new Map();
  for (const person of members) {
    const parent = person.blood && ids.has(person.blood) ? person.blood : null;
    if (!parent) continue;
    if (!childrenOf.has(parent)) childrenOf.set(parent, []);
    childrenOf.get(parent).push(person.id);
  }
  for (const list of childrenOf.values()) {
    list.sort((a, b) => (yearOf(byId.get(a)?.birth) ?? 9999) - (yearOf(byId.get(b)?.birth) ?? 9999));
  }

  const W = 172, H = 104;
  const pos = new Map();
  let cursor = 0;
  const placed = new Set();
  const walk = (id) => {
    if (placed.has(id)) return pos.get(id).x;
    placed.add(id);
    const kids = (childrenOf.get(id) || []).filter((kid) => !placed.has(kid));
    let x;
    if (!kids.length) {
      x = cursor;
      cursor += W;
    } else {
      const xs = kids.map((kid) => walk(kid));
      x = (Math.min(...xs) + Math.max(...xs)) / 2;
    }
    const person = byId.get(id);
    pos.set(id, { x, y: 34 + ((person?.depth ?? 0) - baseDepth) * H, w: 154, h: 58 });
    return x;
  };
  const roots = members
    .filter((p) => !p.blood || !ids.has(p.blood))
    .sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0) || (yearOf(a.birth) ?? 9999) - (yearOf(b.birth) ?? 9999));
  for (const root of roots) walk(root.id);

  let minX = Infinity, maxX = 0, maxY = 0;
  for (const value of pos.values()) {
    minX = Math.min(minX, value.x);
    maxX = Math.max(maxX, value.x + value.w);
    maxY = Math.max(maxY, value.y + value.h);
  }
  return { pos, width: Math.max(maxX - minX, 200), height: maxY, minX };
}
// Всё древо: ствол сверху, линии — полосами, кадетские подписаны.
function treeLayout(people) {
  const lines = orderedLines();
  const gutter = 128;
  const bandGap = 18;
  const headerH = 26;
  const pos = new Map();
  const bands = [];

  let y = 26;
  let widest = 900;
  for (const line of lines) {
    const members = people.filter((p) => p.line === line.id);
    if (!members.length) continue;
    const founder = members.find((p) => p.id === line.founderId) || members[0];
    const local = layoutLine(members, founder?.depth ?? 0);
    const bandX = gutter + 12;
    const bandY = y + headerH;
    for (const [id, value] of local.pos) {
      pos.set(id, {
        x: bandX + (value.x - local.minX),
        y: bandY + (value.y - 34),
        w: value.w,
        h: value.h,
        line: line.id,
      });
    }
    const width = Math.max(local.width, 320);
    bands.push({ line, y, height: headerH + local.height + 6, width, x: 0 });
    widest = Math.max(widest, bandX + width + 40);
    y += headerH + local.height + bandGap;
  }
  return { pos, width: widest, height: y + 20, bands, gutter };
}
function treeSvg(people, meta) {
  const { pos, width, height, bands, gutter } = treeLayout(people);
  const byId = new Map(people.map((p) => [p.id, p]));
  const edges = [];

  for (const p of people) {
    const to = pos.get(p.id);
    if (!to) continue;
    const parentId = p.blood && pos.has(p.blood) ? p.blood : null;
    if (!parentId) continue;
    const from = pos.get(parentId);
    const x1 = from.x + from.w / 2, y1 = from.y + from.h;
    const x2 = to.x + to.w / 2, y2 = to.y;
    const lane = Math.max(y1 + 8, y2 - 14);
    edges.push(`<path class="edge" d="M${x1} ${y1} V${lane} H${x2} V${y2}"/>`);
  }

  // Ствол: вертикальная линия слева и отвод к каждой линии.
  const trunkLine = bands[0];
  const trunkNode = trunkLine ? pos.get(trunkLine.line.founderId) : null;
  const spine = [];
  if (trunkNode) {
    spine.push(`<path class="trunk-spine" d="M${gutter} ${trunkNode.y + trunkNode.h / 2} V${bands[bands.length - 1].y + 8}"/>`);
    for (const band of bands.slice(1)) {
      const founder = pos.get(band.line.founderId);
      const ty = band.y + 8;
      spine.push(`<path class="trunk-tick" style="stroke:${lineColor(band.line)}" d="M${gutter} ${ty} H${gutter + 12}"/>`);
      if (founder) {
        spine.push(`<path class="trunk-link" style="stroke:${lineColor(band.line)}" d="M${gutter + 12} ${ty} V${founder.y + founder.h / 2} H${founder.x}"/>`);
      }
    }
  }

  const headers = bands
    .map((band) => {
      const color = lineColor(band.line);
      const kind = lineKind(band.line.kind) || T('tree.line', 'линия');
      const founderPerson = byId.get(band.line.founderId);
      const fatherOfFounder = founderPerson ? byId.get(founderPerson.father) : null;
      const parentLine = fatherOfFounder && fatherOfFounder.line != null ? lineById(fatherOfFounder.line) : null;
      const parentName = parentLine && parentLine.id !== band.line.id
        ? (parentLine.kind === 'trunk' ? T('tree.fromTrunk', 'от ствола') : `${T('tree.fromLine', 'от линии')} ${parentLine.founder}`)
        : '';
      const years = band.line.birth ? `${y0(band.line.birth)}` : '';
      return `<g class="line-band" data-line="${band.line.id}">
          <rect class="line-band__rule" x="${gutter + 4}" y="${band.y + 22}" width="${band.width + 10}" height="1" style="fill:${color}"/>
          <text class="line-band__name" x="${gutter + 4}" y="${band.y + 15}" style="fill:${color}">${esc(band.line.founder)}</text>
          <text class="line-band__meta" x="${gutter + 8 + Math.max(56, band.line.founder.length * 9)}" y="${band.y + 15}">${kind}${years ? ` · с ${years}` : ''} · ${band.line.size} ${plural(band.line.size, 'человек', 'человека', 'человек')}${parentName ? ` · ${esc(parentName)}` : ''}</text>
        </g>`;
    })
    .join('');

  const query = state.tree.query.trim().toLowerCase();
  const focus = state.tree.focus ? ancestorsAndDescendants(state.tree.focus) : null;

  const nodes = people
    .map((p) => {
      const at = pos.get(p.id);
      if (!at) return '';
      const line = lineById(p.line);
      const unknown = !p.kin && (p.ring ?? 4) >= 3 && !p.title;
      const match = query && !unknown && nameOf(p).toLowerCase().includes(query);
      const dim = focus && !focus.has(p.id);
      const cls = [
        'node',
        p.id === meta.player.id ? 'is-main' : '',
        p.line !== lineage().playerLine ? 'is-cadet' : '',
        p.newHouse ? 'is-newhouse' : '',
        unknown ? 'is-unknown' : '',
        match ? 'is-match' : '',
        dim ? 'is-dim' : '',
        !p.notable && p.kin ? 'is-quiet' : '',
      ].filter(Boolean).join(' ');
      const name = nameOf(p);
      const words = name.split(' ');
      const line1 = words[0] || name;
      const line2 = words.slice(1).join(' ');
      const status = p.landed ? '◆ ' : p.camp ? '⚑ ' : p.newHouse ? '◇ ' : '';
      const sub = [p.title || (p.camp ? T('world.camp', 'отряд') : T('tree.noLand', 'без земли')), p.birth ? `${y0(p.birth)}—${p.death ? y0(p.death) : '…'}` : '']
        .filter(Boolean).join(' · ') + (p.spouses && p.spouses.length ? ' · ⚭' : '');
      const color = lineColor(line);
      return `<g class="${cls}" data-person="${p.id}" data-name="${esc(name.toLowerCase())}" tabindex="0" role="button" aria-label="${esc(name)}">
          <rect x="${at.x}" y="${at.y}" width="${at.w}" height="${at.h}" rx="1.5" style="stroke:${color}"/>
          <text class="node-name" x="${at.x + 9}" y="${at.y + 21}">${esc(status + (line1.length > 14 ? line1.slice(0, 13) + '…' : line1))}</text>
          ${line2 ? `<text class="node-name2" x="${at.x + 9}" y="${at.y + 36}">${esc(line2.length > 16 ? line2.slice(0, 15) + '…' : line2)}</text>` : ''}
          <text class="node-sub" x="${at.x + 9}" y="${at.y + 51}">${esc(sub.slice(0, 22))}</text>
        </g>`;
    })
    .join('');

  return `<svg class="tree" width="100%" height="100%" data-w="${width}" data-h="${height}" role="img" aria-label="Древо династии по линиям">
      <g id="treeViewport">
        ${spine.join('')}
        ${edges.join('')}
        ${headers}
        ${nodes}
      </g>
    </svg>`;
}
function personCard(p) {
  if (!p) return '';
  const father = ix.people.get(p.father);
  const mother = ix.people.get(p.mother);
  const kids = (p.children || []).map((id) => ix.people.get(id)).filter(Boolean);
  const spouses = (p.spouses || []).map((id) => ix.people.get(id)).filter(Boolean);
  const hidden = !p.kin && (p.ring ?? 4) >= 3 && !p.title;
  const skills = p.skills && p.skills.length ? p.skills.join(' · ') : '';
  return `
      <button class="drawer__close" type="button" id="closeDrawer" aria-label="${T('common.close', 'Закрыть')}">×</button>
      <h3>${esc(hidden ? T('tree.nameUnknown', 'Имя неведомо') : nameOf(p))}</h3>
      <p class="small muted">${esc(houseOf(p) ? T('card.house', 'дом') + ' ' + houseOf(p) : T('card.noHouse', 'род не записан'))}${p.kin ? ' · ' + T('card.ownBlood', 'своя кровь') : ''}${relationTo(p) ? ` · ${esc(relationTo(p))}` : ''}</p>
      <dl>
        <dt>${T('card.years', 'Годы')}</dt><dd>${esc(y0(p.birth) || '?')} — ${esc(p.death ? y0(p.death) : T('card.alive', 'жив'))}</dd>
        <dt>${T('card.holdings', 'Владения')}</dt><dd>${esc((p.titles || []).join(', ') || '—')}</dd>
        ${p.camp ? `<dt>${T('card.camp', 'Отряд')}</dt><dd>${esc(p.campName ? `${p.campName}${p.campAt ? `, стоит в ${p.campAt}` : ''}` : `вольный отряд${p.campAt ? `, стоит в ${p.campAt}` : ''}`)}</dd>` : ''}
        ${skills ? `<dt>${T('card.skills', 'Навыки')}</dt><dd class="num">${esc(skills)}</dd>` : ''}
        ${p.traits && p.traits.length ? `<dt>${T('card.traits', 'Черты')}</dt><dd>${esc(p.traits.join(', '))}</dd>` : ''}
        ${p.culture ? `<dt>${T('card.culture', 'Культура')}</dt><dd>${esc(p.culture)}</dd>` : ''}
        <dt>${T('card.faith', 'Вера')}</dt><dd>${p.faith ? esc(p.faith) : `<span class="muted">${T('card.faithUnknown', 'в сейве 1.20 не привязана к людям')}</span>`}</dd>
        <dt>${T('card.father', 'Отец')}</dt><dd>${father ? esc(nameOf(father)) : '—'}</dd>
        <dt>${T('card.mother', 'Мать')}</dt><dd>${mother ? esc(nameOf(mother)) : '—'}</dd>
        <dt>${T('card.spouses', 'Супруги')}</dt><dd>${spouses.length ? spouses.map((s) => esc(nameOf(s))).join(', ') : '—'}</dd>
        <dt>${T('card.children', 'Дети')}</dt><dd>${kids.length ? kids.map((k) => esc(nameOf(k))).join(', ') : '—'}</dd>
      </dl>`;
}
