/* Хроника рода · род.
 *
 * Производные данные рода: линии, ветви, порядок поколений, родство.
 * Зависит: core.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
function lineage() {
  return state.world.lineage || { lines: [], trunk: null, playerLine: null };
}
function lineById(id) {
  return lineage().lines.find((l) => l.id === id) || null;
}
// Цвет линии: цвет её дома с политической карты, иначе — из общей палитры.
function lineColor(line) {
  if (!line) return 'var(--muted)';
  const groups = state.world.mapIndex?.political?.groups || [];
  const group = groups.find((g) => g.house && g.house === line.house);
  if (group) return group.color;
  const palette = ['#2f4a6b', '#6b7f3a', '#8a5a2b', '#5c3f66', '#2f6b63', '#7a3e3e'];
  return palette[line.id % palette.length];
}
// Порядок линий на полотне: ствол, старшая, кадетские по величине, отдельные ветви.
function orderedLines() {
  const rank = { trunk: 0, senior: 1, cadet: 2, detached: 3 };
  return [...lineage().lines].sort(
    (a, b) => (rank[a.kind] ?? 9) - (rank[b.kind] ?? 9) || b.size - a.size || a.id - b.id
  );
}
function treePeople() {
  return (state.world.people || []).filter((p) => p.kin && p.line != null);
}
function ancestorsAndDescendants(id) {
  const byId = new Map((state.world.people || []).map((p) => [p.id, p]));
  const set = new Set([id]);
  const stack = [id];
  while (stack.length) {
    const person = byId.get(stack.pop());
    if (!person) continue;
    for (const parentId of [person.father, person.mother]) {
      const parent = byId.get(parentId);
      if (parent && !set.has(parent.id)) {
        set.add(parent.id);
        stack.push(parent.id);
      }
    }
  }
  const down = [id];
  while (down.length) {
    const person = byId.get(down.pop());
    if (!person) continue;
    for (const childId of person.children || []) {
      const child = byId.get(childId);
      if (child && !set.has(child.id)) {
        set.add(child.id);
        down.push(child.id);
      }
    }
  }
  return set;
}
const ANCESTOR_TERM = (steps, female) => {
  if (steps === 1) return female ? T('kin.mother', 'мать') : T('kin.father', 'отец');
  if (steps === 2) return female ? T('kin.grandmother', 'бабка') : T('kin.grandfather', 'дед');
  if (steps === 3) return female ? T('kin.greatGrandmother', 'прабабка') : T('kin.greatGrandfather', 'прадед');
  return `${'пра'.repeat(Math.max(0, steps - 2))}${female ? 'бабка' : 'дед'}`;
};
const DESCENDANT_TERM = (steps, female) => {
  if (steps === 1) return female ? T('kin.daughter', 'дочь') : T('kin.son', 'сын');
  if (steps === 2) return female ? T('kin.granddaughter', 'внучка') : T('kin.grandson', 'внук');
  if (steps === 3) return female ? 'правнучка' : 'правнук';
  return `${'пра'.repeat(steps - 2)}${female ? 'внучка' : 'внук'}`;
};
// Кем человек приходится вам: по цепочке родителей, а не на глаз.
function relationTo(person) {
  if (!person) return '';
  const playerId = state.world.meta?.player?.id;
  if (!playerId) return '';
  const byId = ix.people;
  if (person.id === playerId) return T('kin.you', 'вы');
  const female = Boolean(person.female);

  const player = byId.get(playerId);
  if (player && (player.spouses || []).includes(person.id)) return female ? T('kin.spouseF', 'супруга') : T('kin.spouseM', 'супруг');
  if ((person.spouses || []).includes(playerId)) return female ? 'супруга' : 'супруг';

  const ancestors = (start) => {
    const map = new Map([[start, 0]]);
    const queue = [start];
    while (queue.length) {
      const current = queue.shift();
      const node = byId.get(current);
      if (!node) continue;
      for (const parentId of [node.father, node.mother]) {
        if (parentId && byId.has(parentId) && !map.has(parentId)) {
          map.set(parentId, map.get(current) + 1);
          queue.push(parentId);
        }
      }
    }
    return map;
  };

  const mine = ancestors(playerId);
  const theirs = ancestors(person.id);

  if (mine.has(person.id)) return ANCESTOR_TERM(mine.get(person.id), female);
  if (theirs.has(playerId)) return DESCENDANT_TERM(theirs.get(playerId), female);

  let best = null;
  for (const [ancestorId, mySteps] of mine) {
    if (!theirs.has(ancestorId)) continue;
    const total = mySteps + theirs.get(ancestorId);
    if (!best || total < best.total) best = { mySteps, theirSteps: theirs.get(ancestorId), total };
  }
  if (!best) {
    const myParents = [player?.father, player?.mother].filter((id) => id && byId.has(id));
    const theirParents = [person.father, person.mother].filter((id) => id && byId.has(id));
    if (myParents.some((id) => theirParents.includes(id))) return female ? T('kin.sister', 'сестра') : T('kin.brother', 'брат');
    return T('kin.inLaw', 'свойственник');
  }
  if (best.mySteps === 1 && best.theirSteps === 1) return female ? 'сестра' : 'брат';
  if (best.mySteps === 2 && best.theirSteps === 1) return female ? T('kin.aunt', 'тётка') : T('kin.uncle', 'дядя');
  if (best.mySteps === 1 && best.theirSteps === 2) return female ? T('kin.niece', 'племянница') : T('kin.nephew', 'племянник');
  if (best.mySteps === 2 && best.theirSteps === 2) return female ? T('kin.cousinF', 'двоюродная сестра') : T('kin.cousinM', 'двоюродный брат');
  if (best.mySteps === 3 && best.theirSteps === 1) return female ? 'двоюродная бабка' : 'двоюродный дед';
  return `родня в ${best.total} ${plural(best.total, 'шаге', 'шагах', 'шагах')}`;
}
/* ---------- мир ---------- */

// Кому подчиняется человек. `null` — независимый или сведений нет.
function liegeOf(id) {
  if (!id) return null;
  const rec = ix.names.get(Number(id));
  if (!rec) return null;
  const liege = rec.liege;
  // В сейве 227 человек числятся вассалами сами себе — это не подчинение.
  if (!liege || liege === id) return null;
  const lrec = ix.names.get(Number(liege));
  if (!lrec || !lrec.name) return null;
  const top = lrec.liege && lrec.liege !== liege ? ix.names.get(Number(lrec.liege)) : null;
  return { name: lrec.name, top: top && top.name ? top.name : '' };
}

// «Х» или «Х, тот — Y»: глубже двух не лезем, дальше это уже не про род.
function liegeTail(id, withTop = true) {
  const liege = liegeOf(id);
  if (!liege) return '';
  return withTop && liege.top ? `${liege.name}, тот — ${liege.top}` : liege.name;
}

function knownPerson(id) {
  return Boolean(id && ix.names.get(Number(id)));
}

function knownLine(r) {
  if (r.ring <= 1) {
    return [
      r.ruler ? nameOf({ name: r.ruler, nick: r.nick }) : '',
      r.house && !String(r.house).startsWith('House ') ? `${T('world.houseShort', 'дом')} ${r.house}` : '',
      r.name,
    ].filter(Boolean).join(', ');
  }
  if (r.ring === 2) return `${r.ruler || T('world.rulerNoName', 'государь без имени')}, ${r.name}`;
  return `${r.name}: ${T('world.rulerUnnamed', 'государь не назван')}`;
}
