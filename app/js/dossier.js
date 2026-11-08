/* Хроника рода · досье.
 *
 * Экран «Досье»: пакет фактов для рассказчика — род, дома, державы, карта словами.
 * Зависит: core, model, tree (названия линий), chronicle (сводка лет).
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
/* ---------- досье для рассказчика ---------- */

const TIER_RU = { Empire: 'империя', Kingdom: 'королевство', Duchy: 'герцогство', County: 'графство', Other: 'владение' };
const yr = (value) => String(value ?? '').replace(/^0+/, '') || '—';
// Владения с годом: «Сичуань с 887» — из истории титула (build_world.py, tenures).
function heldLine(p) {
  if (p && p.tenures && p.tenures.length) {
    return p.tenures.map(([name, year]) => (year ? `${name} с ${year}` : name)).join(', ');
  }
  return p && p.titles && p.titles.length ? p.titles.join(', ') : '';
}
function mapWords() {
  const realms = state.world.realms || [];
  const grid = state.world.mapGrid;
  const out = ['## Карта словами'];

  const dirs = ['север', 'северо-восток', 'восток', 'юго-восток', 'юг', 'юго-запад', 'запад', 'северо-запад'];
  const seen = new Set();
  for (const dir of dirs) {
    const list = realms
      .filter((r) => (r.direction || '') === dir)
      .sort((a, b) => (a.distance ?? 1e9) - (b.distance ?? 1e9))
      .filter((r) => (seen.has(r.name) ? false : seen.add(r.name)))
      .slice(0, 4);
    if (!list.length) continue;
    out.push(`- ${dir}: ${list.map((r) => `${r.name} (кольцо ${r.ring}, ${r.distance ?? '?'} px)`).join(', ')}`);
  }

  if (grid && grid.cells && grid.cells.length) {
    const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
    const order = [...realms].sort((a, b) => a.ring - b.ring || (a.distance ?? 1e9) - (b.distance ?? 1e9));
    const byId = new Map();
    order.slice(0, letters.length).forEach((realm, index) => byId.set(realm.id, letters[index]));
    out.push('', `Решётка ${grid.w}×${grid.h}: буква — держава, · — море или неведомое.`);
    const rows = grid.cells.map((row) => row.map((id) => byId.get(id) || '·').join(''));
    const firstFilled = rows.findIndex((row) => /[^·]/.test(row));
    const lastFilled = rows.length - 1 - [...rows].reverse().findIndex((row) => /[^·]/.test(row));
    const trimmed = rows.slice(Math.max(0, firstFilled), lastFilled + 1);
    for (const row of trimmed.length ? trimmed : rows) out.push(row);
    out.push('', 'Легенда:');
    for (const [id, letter] of byId) {
      const realm = realms.find((x) => x.id === id);
      if (realm) out.push(`  ${letter} — ${realm.name} (кольцо ${realm.ring})`);
    }
  }

  const withNeighbors = realms.filter((r) => r.ring <= 2 && r.neighbors && r.neighbors.length).slice(0, 12);
  if (withNeighbors.length) {
    out.push('', 'Соседи:');
    for (const realm of withNeighbors) out.push(`- ${realm.name}: ${realm.neighbors.join(', ')}`);
  }
  return out.join('\n');
}
function dossierText() {
  const { meta } = state.world;
  const people = state.world.people || [];
  const realms = [...(state.world.realms || [])];
  const out = [];

  out.push('# Досье для рассказчика');
  out.push('');
  out.push(`Мир на ${meta.year} год. Род: ${meta.player.house || '—'}${meta.player.dynasty ? `, династия ${meta.player.dynasty}` : ''}.`);
  out.push(`Правитель: ${meta.player.name || '—'}${meta.player.nick ? ' ' + meta.player.nick : ''}${meta.player.title ? `, ${meta.player.title}` : ', без земли'}.`);
  const homeRealm = (state.world.realms || []).find((r) => r.id === meta.player.realm);
  if (homeRealm && homeRealm.ruler && homeRealm.ruler !== meta.player.name) {
    out.push(`Главный титул дома — ${homeRealm.name}, его держит ${homeRealm.ruler}${homeRealm.house ? `, дом ${homeRealm.house}` : ''}. ${meta.player.name} — глава рода, но не держатель этого титула.`);
  }
  out.push(`Хроника охватывает ${state.settings.from}—${state.settings.to}.`);
  if (meta.dynastyFrom) {
    out.push(`Династия ведёт начало с ${meta.dynastyFrom} года; событий о роде ранее ${state.settings.from} в сейве нет.`);
  }
  out.push('');
  // Кого считать главными: владельцы титулов и участники важных дел.
  const owners = people.filter((p) => p.kin && (p.landed || p.held));
  if (owners.length) {
    out.push('## Кто держал титулы');
    for (const p of owners.sort((a, b) => (yearOf(a.birth) || 0) - (yearOf(b.birth) || 0))) {
      const what = heldLine(p) || 'титул в прошлом';
      out.push(`  - ${nameOf(p)} (${y0(p.birth) || '?'}—${p.death ? y0(p.death) : 'жив'}): ${what}`);
    }
    out.push('');
  }

  out.push('## Линии рода');
  const lin = state.world.lineage;
  if (lin && lin.lines.length) {
    const trunkPerson = state.world.people.find((x) => x.id === lin.trunk);
    out.push(`Ствол — ${trunkPerson ? nameOf(trunkPerson) : 'неизвестен'}${trunkPerson ? ` (${y0(trunkPerson.birth) || '?'})` : ''}. Линий: ${lin.lines.length}.`);
    for (const line of lin.lines) {
      const kind = lineKind(line.kind) || 'линия';
      out.push(`  - ${line.founder}${line.birth ? ` (${y0(line.birth)})` : ''}, ${kind}, ${line.size} ${plural(line.size, 'человек', 'человека', 'человек')}${line.house ? `, дом ${line.house}` : ''}`);
    }
    out.push('');
  }

  out.push('## Династия');
  for (const g of meta.generations || []) {
    const members = people.filter((p) => p.kin && (p.gen ?? 0) === g.gen);
    if (!members.length) continue;
    out.push(`Поколение ${g.gen + 1} (${g.from || '?'}—${g.to || '…'}):`);
    for (const p of members) {
      out.push(`  - ${nameOf(p)} — ${y0(p.birth) || '?'}—${p.death ? y0(p.death) : 'жив'}${p.title ? `, ${p.title}` : ''}${p.culture ? `; культура: ${p.culture}` : ''}${p.traits && p.traits.length ? `; черты: ${p.traits.slice(0, 3).join(', ')}` : ''}`);
    }
  }
  out.push('');
  out.push('Родство и браки:');
  for (const p of people.filter((x) => x.kin)) {
    const kids = (p.children || []).map((id) => ix.people.get(id)).filter((k) => k && k.kin);
    if (kids.length) out.push(`  - ${nameOf(p)} → дети: ${kids.map(nameOf).join(', ')}`);
    const spouses = (p.spouses || []).map((id) => ix.people.get(id)).filter(Boolean);
    if (spouses.length) out.push(`  - ${nameOf(p)} — брак: ${spouses.map(nameOf).join(', ')}`);
  }
  out.push('');

  out.push('## Ветви династии');
  for (const house of state.world.dynasty?.houses || []) {
    const years = house.from ? `${house.from}—${house.to ?? '…'}` : 'годы неизвестны';
    const role = house.senior ? 'старший дом' : 'кадетская ветвь';
    const mine = house.player ? ', ваш дом' : '';
    out.push(
      `- ${house.name}: ${house.members} ${plural(house.members, 'человек', 'человека', 'человек')}, ${role}${mine}, ${years}${house.founded ? `, основан ${String(house.founded).slice(0, 4)}` : ''}`
    );
  }
  out.push('');

  out.push('## Кто чем владеет');
  const holders = people
    .filter((p) => p.kin && p.titles && p.titles.length)
    .sort((a, b) => b.titles.length - a.titles.length);
  for (const person of holders.slice(0, 25)) {
    // Феодальный статус: кому служит держатель. В данных бывает «вассал сам себе».
    const liegeId = person.liege && person.liege !== person.id ? person.liege : null;
    const liegeRec = liegeId ? ix.names.get(Number(liegeId)) : null;
    const status = liegeRec && liegeRec.name
      ? ` — ${T('dossier.vassalOf', 'вассал')} ${liegeRec.name}`
      : ` — ${T('dossier.independent', 'независимый')}`;
    out.push(`- ${nameOf(person)}: ${heldLine(person)}${status}`);
  }
  const camps = people.filter((p) => p.kin && p.camp);
  if (camps.length) {
    out.push('');
    out.push('## Авантюристы');
    for (const person of camps.slice(0, 15)) {
      const where = person.campAt ? `, стоит в ${person.campAt}` : '';
      const name = person.campName ? `отряд «${person.campName}»` : 'вольный отряд';
      out.push(`- ${nameOf(person)}: ${name}${where}`);
    }
  }
  const landless = people.filter((p) => p.kin && (!p.titles || !p.titles.length) && !p.camp).length;
  if (landless) out.push(`- без земли и без отряда: ${landless} родичей`);
  out.push('');

  out.push('## Державы в поле зрения');
  const anyFaith = realms.some((r) => r.faith);
  if (!anyFaith) {
    out.push('Вера не привязана: в сейве 1.20 определения вер читаются (108 вер), но ни у людей, ни у графств нет ссылки на веру. Культура при этом есть.');
    out.push('');
  }
  realms.sort((a, b) => a.ring - b.ring || (a.distance ?? 1e9) - (b.distance ?? 1e9));
  for (const r of realms) {
    const head = [`${r.name} — ${TIER_RU[r.tier] || 'владение'}`, `кольцо ${r.ring}`, r.distance != null ? `${r.distance} px ${r.direction || ''}`.trim() : ''];
    if (r.ring <= 2 && r.ruler) head.push(`государь: ${r.ruler}${r.house ? `, дом ${r.house}` : ''}`);
    if (r.faith) head.push(`вера: ${r.faith}${r.faithShare ? ` (${Math.round(r.faithShare * 100)}%)` : ''}`);
    if (r.culture) head.push(`культура: ${r.culture}${r.cultureShare ? ` (${Math.round(r.cultureShare * 100)}%)` : ''}`);
    if (r.domain && r.domain.length > 1) {
      const base = r.domain.find((point) => point[1] > 0) || r.domain[0];
      const last = r.domain[r.domain.length - 1];
      head.push(`владений: ${last[1]} (в ${base[0]} — ${base[1]})`);
    }
    out.push(`- ${head.filter(Boolean).join('; ')}`);
    if (r.rulers && r.rulers.length > 1) {
      out.push(`    смена государей: ${r.rulers.map((x) => `${x.name || 'имени не сохранилось'} ${yr(x.from)}—${yr(x.to)}${x.faith ? ` (${x.faith})` : ''}`).join('; ')}`);
    }
  }
  out.push('');

  out.push(mapWords());
  out.push('');
  out.push('## События периода');
  out.push(chronicleMarkdown() || '(записей нет)');
  out.push('');
  out.push('---');
  out.push('Оговорки: вера и культура державы — по её графствам на дату сейва; смена государей — по истории главного титула; «владений» — число графств в державе на год.');
  return out.join('\n');
}
function viewDossier() {
  return `
      <div class="page-head"><h1>${T('dossier.title', 'Досье')}</h1>
        <p>${T('dossier.lead', 'Готовый пакет для рассказчика: династия, державы, вера и культура, владения и события периода.')}</p></div>
      <div class="doc-actions" style="margin:0 0 16px">
        <button class="btn" type="button" id="copyDossier">${T('dossier.copy', 'Скопировать досье')}</button>
        <button class="btn btn--ghost" type="button" id="downloadDossier">${T('common.downloadMd', 'Скачать .md')}</button>
      </div>
      <pre class="dossier" id="dossierText">${esc(dossierText())}</pre>`;
}
