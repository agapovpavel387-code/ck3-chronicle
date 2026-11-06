/* Хроника рода · хроника.
 *
 * Экран «Хроника»: записи по годам, главы, слои, выгрузка в markdown.
 * Зависит: core, model.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
/* ---------- хроника ---------- */

const KIND_RU = {
  death: 'смерть', succession: 'власть', war: 'война', war_win: 'победа', war_loss: 'поражение',
  birth: 'рождение', marriage: 'брак', friendship: 'дружба', rivalry: 'вражда', prison: 'темница',
  prison_free: 'воля', battle: 'битва', title_loss: 'утрата', journey: 'путь', ruler: 'правление',
  alliance: 'союз', romance: 'любовь', kin_death: 'утрата близкого', note: 'запись',
};
function entryText(e) {
  const p = who(e.who);
  const q = who(e.who2);
  const year = yearOf(e.date);
  const v = e.v || 0;
  const age = ageAt(p, e.date);
  const place = e.realm || e.title || 'дальние земли';
  const again = new Set(['prison', 'prison_free', 'rivalry', 'battle', 'war_loss', 'title_loss', 'romance', 'friendship']);
  let body = (() => {
    switch (e.kind) {
    case 'death': {
      if (e.grade === 0) {
        const dead = `${nameOf(p)}${age ? `, ${yearsRu(age)} от роду` : ''}`;
        const tail = `${e.title ? ` Держал «${e.title}».` : ''}${traitsPhrase(p)}`;
        return [
          `В лето ${year}-е преставил${p && p.female ? 'ась' : 'ся'} ${dead}.${tail}`,
          `На ${year}-й год не стало ${dead}.${tail}`,
          `В ${year} году ${died(p)} ${dead}.${tail}`,
        ][v % 3];
      }
      if (e.grade === 1) {
        const who = `${nameOf(p)}${e.title ? `, ${e.title}` : ''}`;
        return pickVariant(e, [
          `В том же году ${died(p)} ${who}.`,
          `${cap(died(p))} ${who}.`,
          `Не стало ${who}.`,
          `В тот год не стало ${who}.`,
          `Скончал${p && p.female ? 'ась' : 'ся'} ${who}.`,
        ]);
      }
      if (e.grade === 2) return `${cap(died(p))} ${nameOf(p)} (${place}).`;
      return [
        `${place}: умер государь; имени не называли.`,
        `Из дальних земель доносили: в ${e.title || 'тамошнем краю'} умер государь.`,
        `Тамошний владетель скончался — имени не записали.`,
      ][v % 3];
    }
    case 'succession': {
      if (e.grade === 0) return `${year} год. ${e.title || 'Власть'}: власть принял${p && p.female ? 'а' : ''} ${nameOf(p)}.`;
      if (e.grade === 1) return [`${e.title}: сменился государь — ${nameOf(p)}.`, `${e.title}: власть перешла к ${nameOf(p)}.`][v % 2];
      if (e.grade === 2) return `${e.title}: новый государь, ${nameOf(p)}.`;
      return [`${e.title}: сменился государь.`, `В ${e.title} — новый государь; кто он, не сказывали.`, `${e.title}: власть перешла к другому.`][v % 3];
    }
    case 'war': {
      if (e.grade <= 1) return [`Началась ${e.type || 'война'}.${q ? ` Противник — ${nameOf(q)}.` : ''}`, `Пошли войной${q ? ` на ${nameOf(q)}` : ''}: ${e.type || 'война'}.`][v % 2];
      if (e.grade === 2) return `Слышали о войне${q ? ` с ${nameOf(q)}` : ''}.`;
      return [`На границах неспокойно.`, `Сказывали о войне в дальних землях.`, `Из-за моря дошло: где-то воюют.`][v % 3];
    }
    case 'title_loss': {
      const taker = q && q.id !== p?.id ? nameOf(q) : '';
      const what = e.title ? `«${e.title}»` : 'титул';
      if (e.grade <= 1) {
        return taker
          ? `${nameOf(p)} потерял${p && p.female ? 'а' : ''} ${what}: он отошёл к ${taker}.`
          : `${nameOf(p)} потерял${p && p.female ? 'а' : ''} ${what}.`;
      }
      return `В ${place} сменился владетель${taker ? ` — им стал ${taker}` : ''}.`;
    }
    case 'war_win':
      return e.grade <= 1 ? `${nameOf(p)} вышел победителем из войны.` : `${e.title || 'Тамошний государь'} победил в войне.`;
    case 'war_loss':
      return e.grade <= 1 ? `${nameOf(p)} потерпел поражение.` : `Тамошний государь проиграл войну.`;
    case 'birth': {
      const spouse = q && p && (p.spouses || []).includes(q.id);
      if (e.grade === 0) {
        if (q && !spouse) return [`В лето ${year}-е ${born(q)} ${nameOf(q)}.`, `В ${year} году ${born(q)} ${nameOf(q)}.`][v % 2];
        return `В лето ${year}-е — пополнение в роду.`;
      }
      if (e.grade === 1) return q && !spouse ? `${cap(born(q))} ${nameOf(q)}.` : 'Пополнение в семье.';
      return `${place} — пополнение.`;
    }
    case 'marriage': {
      if (e.grade === 0) return [`${year} год. ${nameOf(p)} и ${nameOf(q)} сочетались браком.`, `${year} год. ${nameOf(p)} взял${p && p.female ? 'а' : ''} в род ${nameOf(q)}.`][v % 2];
      if (e.grade === 1) return `${nameOf(p)} и ${nameOf(q)} — новая семья.`;
      return `${place}: новый брак.`;
    }
    case 'friendship':
      return e.grade <= 1 ? `${nameOf(p)} и ${nameOf(q)} сошлись.` : 'В тамошних землях — новая дружба.';
    case 'rivalry':
      return e.grade <= 1 ? `${nameOf(p)} и ${nameOf(q)} стали врагами.` : 'В тамошних землях — вражда.';
    case 'prison':
      return e.grade <= 1 ? `${nameOf(p)} ${p && p.female ? 'попала' : 'попал'} в темницу.` : 'Тамошнего государя взяли под стражу.';
    case 'prison_free':
      return e.grade <= 1 ? `${nameOf(p)} ${p && p.female ? 'вышла' : 'вышел'} на волю.` : 'Тамошнего государя выпустили.';
    case 'battle':
      return e.grade <= 1 ? `${nameOf(p)} и ${nameOf(q)} сошлись в бою.` : 'На дальних полях было сражение.';
    case 'title_loss':
      return e.grade <= 1 ? `${nameOf(p)} ${p && p.female ? 'потеряла' : 'потерял'} титул${e.title ? ` «${e.title}»` : ''}.` : 'Тамошний государь лишился титула.';
    case 'journey':
      return e.grade <= 1 ? `${nameOf(p)} ${p && p.female ? 'вернулась' : 'вернулся'} из паломничества.` : 'Тамошний государь ходил на богомолье.';
    case 'ruler':
      if (e.grade <= 1) return `${nameOf(p)} ${p && p.female ? 'приняла' : 'принял'} власть.`;
    // Если край назван — называем его: строки перестают быть близнецами.
    const where = e.title || e.realm;
    if (where && !String(where).startsWith('держава ')) {
      return pickVariant(e, [
        `В ${where} — новый правитель.`,
        `${where}: власть перешла к другому.`,
        `Из ${where} доносили о смене власти.`,
      ]);
    }
    return pickVariant(e, [
      'В дальних землях — новый правитель.',
      'Из-за моря дошло: там сменился государь.',
      'В тамошних краях приняли нового владетеля.',
      'Сказывали, что в дальних землях власть перешла к другому.',
    ]);
    case 'alliance':
      return e.grade <= 1 ? `${nameOf(p)} ${p && p.female ? 'поддержала' : 'поддержал'} союзника.` : 'Дальние дворы заключили союз.';
    case 'romance':
      return e.grade <= 1 ? `${nameOf(p)} и ${nameOf(q)} сошлись в любви.` : 'В дальних землях — любовная история.';
    case 'kin_death':
      return e.grade <= 1 ? `${nameOf(p)} ${p && p.female ? 'потеряла' : 'потерял'} близкого — ${nameOf(q)}.` : 'В дальних землях оплакивают близкого.';
    case 'note': {
      const text = typeof window.noteText === 'function'
        ? window.noteText(e.type, { year, name: nameOf(p), female: Boolean(p && p.female), other: q ? nameOf(q) : '' })
        : '';
      if (text) return text;
      return `${cap(e.type || 'запись')}${p ? ` — ${nameOf(p)}` : ''}.`;
    }
    default:
      return `${e.type || 'Событие'}${p ? `: ${nameOf(p)}` : ''}.`;
    }
  })();
  // Нить войны и распри: строка не висит без начала.
  if (e.threadSince) body += ` Война начата в ${e.threadSince} году.`;
  if (e.feudSince) {
    const rival = e.feudWith ? ix.people.get(e.feudWith) : null;
    body += rival
      ? ` Распря с ${nameOf(rival)} шла с ${e.feudSince} года.`
      : ` Распря шла с ${e.feudSince} года.`;
  }

  // «Снова» уместно только там, где в строке есть имя: у безличных вестей оно даёт «Снова На…».
  if (e.repeat && again.has(e.kind) && body && /[А-ЯЁ][а-яё]+ [А-ЯЁ]/.test(body)) {
    // Имя в начале строки не трогаем: «Снова Йонэс», а не «Снова йонэс».
    return 'Снова ' + body;
  }
  return body;
}
function truthLine(e) {
  const p = who(e.who);
  if (!p) return '';
  const house = houseOf(p);
  const years = `${y0(p.birth) || '?'}—${p.death ? y0(p.death) : 'жив'}`;
  return [p.name + (p.nick ? ' ' + p.nick : ''), house ? `дом ${house}` : '', years, e.title || ''].filter(Boolean).join(', ');
}
function viewChronicle() {
  const s = state.settings;
  const years = ix.years;
  return `
      <div class="page-head"><h1>${T('chronicle.title', 'Хроника')}</h1>
        <p>Год за годом — только то, что дошло до рода. Чем дальше двор, тем короче запись.</p></div>
      <div class="chronicle">
        <form class="controls" id="chronicleForm">
          <div class="field-row">
            <label class="field"><span class="field__label">${T('chronicle.from', 'С года')}</span>
              <input type="number" id="fromYear" min="1" max="3000" value="${s.from ?? years[0] ?? 867}"></label>
            <label class="field"><span class="field__label">${T('chronicle.to', 'По год')}</span>
              <input type="number" id="toYear" min="1" max="3000" value="${s.to ?? years[years.length - 1] ?? 894}"></label>
          </div>
          <fieldset class="field" style="border:0;padding:0">
            <legend class="field__label">${T('chronicle.what', 'Что записывать')}</legend>
            <label class="check"><input type="checkbox" id="incDeaths"${s.deaths ? ' checked' : ''}> ${T('chronicle.deaths', 'Смерти')}</label>
            <label class="check"><input type="checkbox" id="incSucc"${s.successions ? ' checked' : ''}> ${T('chronicle.successions', 'Переходы власти')}</label>
            <label class="check"><input type="checkbox" id="incWars"${s.wars ? ' checked' : ''}> ${T('chronicle.wars', 'Войны')}</label>
            <label class="check"><input type="checkbox" id="incPrivate"${s.private ? ' checked' : ''}> ${T('chronicle.private', 'Родня')}: ${T('chronicle.privateHint', 'браки, рождения, темница')}</label>
            <label class="check"><input type="checkbox" id="incRumors"${s.rumors ? ' checked' : ''}> ${T('chronicle.rumors', 'Молва')} (${T('world.ring4', 'молва')})</label>
          </fieldset>
          <label class="check" style="margin-top:8px"><input type="checkbox" id="showTruth"${s.truth ? ' checked' : ''}> ${T('chronicle.truth', 'Показывать правду рядом')}</label>
          <div class="controls__actions">
            <button class="btn" type="submit">${T('chronicle.build', 'Собрать хронику')}</button>
            <button class="btn btn--ghost" type="button" id="copyDoc">${T('chronicle.copy', 'Скопировать')}</button>
            <button class="btn btn--ghost" type="button" id="downloadDoc">${T('chronicle.download', 'Скачать .md')}</button>
          </div>
          <p class="controls__hint">Родня — то, что видно только своим: браки, рождения, темницы.</p>
        </form>
        <section class="chronicle__doc" id="doc" aria-live="polite"></section>
      </div>`;
}
const PRIVATE = new Set(['birth', 'marriage', 'friendship', 'rivalry', 'prison', 'prison_free', 'romance', 'kin_death', 'alliance']);
// О безземельном родиче — только кровь и война; темницы и дружбы остаются в досье.
const QUIET_SKIP = new Set(['prison', 'prison_free', 'friendship', 'rivalry', 'romance', 'alliance', 'note']);
// В дальних землях имеет смысл писать только о власти и крови.
const SIGNIFICANT = new Set(['death', 'succession', 'war', 'battle', 'war_win', 'war_loss', 'title_loss']);
function readForm() {
  const s = state.settings;
  const from = Number(el('fromYear').value) || s.from;
  const to = Number(el('toYear').value) || s.to;
  s.from = Math.min(from, to);
  s.to = Math.max(from, to);
  s.deaths = el('incDeaths').checked;
  s.successions = el('incSucc').checked;
  s.wars = el('incWars').checked;
  s.private = el('incPrivate').checked;
  s.rumors = el('incRumors').checked;
  s.truth = el('showTruth').checked;
}
// Безземельные, которые ничем не отметились: о них одна строка за всю летопись.
function quietIds() {
  const set = new Set();
  for (const p of state.world.people || []) {
    // Старые миры не знают этих полей — тогда правило не применяется вовсе.
    if (p.landed === false && p.held === false && p.notable === false) set.add(p.id);
  }
  return set;
}
// Слой записи: своё, двор, издали.
function layerOf(e) {
  if (e.kin || e.grade === 0) return 'kin';
  if (e.grade <= 2) return 'court';
  return 'far';
}
// Ключ пары участников: по нему тянется нить войны или распри.
function pairKey(e) {
  const ids = [e.who, e.who2].filter(Boolean);
  if (!ids.length) return null;
  return ids.sort((a, b) => a - b).join('|');
}
function collect() {
  const s = state.settings;
  const out = [];
  const quiet = quietIds();
  const spokenFor = new Set();
  const warStart = new Map();     // участник -> год начала войны
  const feudStart = new Map();    // пара -> год начала распри

  for (const year of ix.years) {
    if (year < s.from || year > s.to) continue;
    const all = ix.byYear.get(year) || [];
    const relevant = all.filter((e) => {
      if (e.kind === 'death' && !s.deaths) return false;
      if (e.kind === 'succession' && !s.successions) return false;
      if ((e.kind === 'war' || e.kind === 'war_win' || e.kind === 'war_loss' || e.kind === 'battle') && !s.wars) return false;
      if (PRIVATE.has(e.kind) && !s.private) return false;
      return true;
    });

    const shown = [];
    const perKind = new Map();
    const seenPairs = new Set();
    let trimmed = 0;
    const missed = { kin: 0, court: 0, far: 0 };

    for (const e of relevant) {
      // Нить войны: помним, когда она началась, чтобы победа не висела без начала.
      const key = pairKey(e);
      if (e.kind === 'war') {
        for (const id of [e.who, e.who2]) if (id) warStart.set(id, year);
      }
      if (e.kind === 'war_win' || e.kind === 'war_loss') {
        const since = [e.who, e.who2]
          .map((id) => (id ? warStart.get(id) : null))
          .filter((value) => value != null && value < year)
          .sort((a, b) => a - b)[0];
        if (since != null) e.threadSince = since;
      }
      // Нить распри: от первой ссоры до смерти одного из двоих.
      if (e.kind === 'rivalry' && key) feudStart.set(key, year);
      if (e.kind === 'death' && key) {
        const since = feudStart.get(key);
        if (since != null && since < year) {
          e.feudSince = since;
          e.feudWith = e.who === e.who2 ? null : (e.who ? e.who2 : e.who);
        }
      }

      if (e.grade >= 4 && !s.rumors) { trimmed += 1; missed.far += 1; continue; }
      if (e.grade >= 2 && PRIVATE.has(e.kind)) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
      if (e.kind === 'note' && e.grade >= 2) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
      if (e.kind === 'note' && e.who) {
        const noteKey = `note|${e.type}|${e.who}`;
        if (seenPairs.has(noteKey)) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
        seenPairs.add(noteKey);
      }
      if (e.grade >= 3 && !SIGNIFICANT.has(e.kind)) { trimmed += 1; missed.far += 1; continue; }
      if (e.kind === 'succession') {
        const succKey = `succ|${e.title}|${String(e.date).slice(0, 4)}`;
        if (seenPairs.has(succKey)) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
        seenPairs.add(succKey);
      }
      if (e.who && e.who2) {
        const pair = [e.kind, e.date, Math.min(e.who, e.who2), Math.max(e.who, e.who2)].join('|');
        if (seenPairs.has(pair)) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
        seenPairs.add(pair);
      }
      const subjects = [e.who, e.who2].filter(Boolean);
      const quietHere = subjects.filter((id) => quiet.has(id));
      // Убийство — не бытовая заметка: о нём пишем, даже если оба без земли.
      const isMurder = e.kind === 'note' && /убий/i.test(e.type || '');
      if (quietHere.length === subjects.length && QUIET_SKIP.has(e.kind) && !isMurder) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
      if (quietHere.length) {
        const allQuiet = quietHere.length === subjects.length;
        if (allQuiet && !SIGNIFICANT.has(e.kind) && !isMurder) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
        const fresh = quietHere.filter((id) => !spokenFor.has(id));
        if (!fresh.length && !isMurder) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
        for (const id of fresh) spokenFor.add(id);
      }
      const sentence = entryText(e);
      if (seenPairs.has(`txt|${sentence}`)) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
      seenPairs.add(`txt|${sentence}`);
      const count = perKind.get(e.kind) || 0;
      const quietDeath = e.kind === 'death' && quietHere.length === subjects.length;
      const cap = e.kind === 'death'
        ? (quietDeath ? 2 : 6)
        : isMurder ? 2
        : QUIET_SKIP.has(e.kind) ? 1
        : e.kind === 'birth' ? 3
        : e.kind === 'marriage' ? 2
        : 4;
      if (count >= cap) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
      perKind.set(e.kind, count + 1);
      shown.push(e);
    }
    if (!shown.length) continue;

    const weightOf = (e) => {
      if (e.kind === 'note' && /убий/i.test(e.type || '')) return 0;
      const people2 = [e.who, e.who2].filter(Boolean).map((id) => ix.people.get(id));
      const landed = people2.some((p) => p && (p.landed || p.held));
      const notable = people2.some((p) => p && p.notable);
      if (landed) return 0;
      if (notable || SIGNIFICANT.has(e.kind)) return 1;
      return 2;
    };
    shown.sort(
      (a, b) =>
        weightOf(a) - weightOf(b) ||
        (KIND_WEIGHT[a.kind] ?? 10) - (KIND_WEIGHT[b.kind] ?? 10) ||
        a.grade - b.grade
    );

    const layers = { kin: [], court: [], far: [] };
    let quietShown = 0;
    for (const e of shown) {
      if (weightOf(e) === 2) {
        if (quietShown >= 2) { trimmed += 1; missed[layerOf(e)] += 1; continue; }
        quietShown += 1;
      }
      const layer = layerOf(e);
      if (layer === 'far') { missed.far += 1; continue; }   // издали — счётом, не строками
      if (layers[layer].length >= (layer === 'kin' ? 8 : 6)) { trimmed += 1; missed[layer] += 1; continue; }
      layers[layer].push(e);
    }
    if (!layers.kin.length && !layers.court.length) continue;

    const known = relevant.filter((e) => (e.grade <= 1 || e.kin) && (SIGNIFICANT.has(e.kind) || e.kin));
    // Дальние вести: не только счёт, но и кто именно мелькнул в них.
    const farNames = new Map();
    for (const e of relevant) {
      if ((e.grade ?? 4) < 3 || !e.realm) continue;
      if (e.realm.startsWith('держава ')) continue;
      farNames.set(e.realm, (farNames.get(e.realm) || 0) + 1);
    }
    const farTop = [...farNames.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([name]) => name);

    out.push({
      year,
      layers,
      total: known.length,
      trimmed,
      missed,
      far: state.world.rumors?.years?.[String(year)] || null,
      farNames: farTop,
    });
  }
  return out;
}
function prologue(chapters, s) {
  const meta = state.world.meta;
  const start = meta.dynastyFrom;
  const first = chapters[0]?.year;
  if (!start || !first || first - start < 3) return '';

  const houses = state.world.dynasty?.houses || [];
  const kin = (state.world.people || [])
    .filter((p) => p.kin && p.birth)
    .sort((a, b) => String(a.birth).localeCompare(String(b.birth)))
    .slice(0, 6);

  const houseNames = houses
    .map((h) => `${h.name}${h.senior ? ' (старший)' : ''}${h.player ? ' — ваш дом' : ''}`)
    .join(', ');
  const firstPeople = kin.map((p) => `${nameOf(p)} (${y0(p.birth) || '?'})`).join(', ');

  return `<section class="prologue">
      <h3>Пролог · ${start}—${first - 1}</h3>
      <p>Династия ${esc(meta.player.dynasty || meta.player.house || '')} ведёт начало с ${start} года.${houseNames ? ` Дома: ${esc(houseNames)}.` : ''}</p>
      ${firstPeople ? `<p>Первые, кого помнит источник: ${esc(firstPeople)}.</p>` : ''}
      <p class="muted">Записей за эти годы нет: в сейве не сохранилось ни одного свидетельства о роде за ${start}—${first - 1}.</p>
    </section>`;
}
const LAYER_RU = { kin: 'В роду', court: 'При дворе и рядом' };
function renderEntry(e) {
  const truth = state.settings.truth ? `<span class="truth">на самом деле: ${esc(truthLine(e))}</span>` : '';
  return `<p class="entry entry--${e.grade}">${esc(entryText(e))}${truth}</p>`;
}
function renderYear(chapter) {
  const { year, layers, missed } = chapter;
  const all = [...layers.kin, ...layers.court];
  const kinds = new Map();
  for (const e of all) kinds.set(e.kind, (kinds.get(e.kind) || 0) + 1);
  const summary = [...kinds.entries()]
    .sort((a, b) => (KIND_WEIGHT[a[0]] ?? 10) - (KIND_WEIGHT[b[0]] ?? 10))
    .slice(0, 4)
    .map(([k, n]) => `${KIND_RU[k] || k}${n > 1 ? ' ' + n : ''}`)
    .join(' · ');

  const block = (key) => {
    const list = layers[key];
    if (!list.length) return '';
    return `<div class="layer">
        <p class="layer__title">${LAYER_RU[key]}</p>
        ${list.map(renderEntry).join('')}
      </div>`;
  };

  const farLead = ['Издали доходило:', 'Из-за моря слышали:', 'Доходило из дальних земель:'][year % 3];
  const far = chapter.far && (chapter.far.wars || chapter.far.deaths || chapter.far.successions)
    ? `<p class="entry entry--far">${farLead} ${[
          chapter.far.wars ? `войн — ${chapter.far.wars}` : '',
          chapter.far.deaths ? `смертей — ${chapter.far.deaths}` : '',
          chapter.far.successions ? `смен власти — ${chapter.far.successions}` : '',
        ].filter(Boolean).join(', ')}.${chapter.farNames && chapter.farNames.length ? ` Мелькали: ${chapter.farNames.map((n) => esc(n)).join(', ')}.` : ''}</p>`
    : '';

  const missedParts = [];
  if (missed.court) missedParts.push(`при дворе — ${missed.court}`);
  if (missed.far) missedParts.push(`издали — ${missed.far}`);
  const honesty = missedParts.length
    ? `<span class="year__missed"> · мимо прошло: ${missedParts.join(', ')}</span>`
    : '';

  return `<section class="year">
      <div class="year__num">${year}</div>
      <div class="year__body">
        <p class="year__summary">${esc(summary)}${honesty}</p>
        ${block('kin')}${block('court')}${far}
      </div>
    </section>`;
}
function chapterStats(years) {
  const counts = { death: 0, war: 0, marriage: 0, birth: 0, succession: 0 };
  for (const chapter of years) {
    for (const e of [...chapter.layers.kin, ...chapter.layers.court]) {
      if (e.kind in counts) counts[e.kind] += 1;
    }
  }
  return counts;
}
function chronicleMarkdown() {
  const chapters = collect();
  if (!chapters.length) return '';
  const out = [];
  let lastEra = null;
  const periods = state.world.meta?.periods || [];
  for (const chapter of chapters) {
    const era = periods.find((p) => chapter.year >= p.from && chapter.year <= p.to);
    if (era && era !== lastEra) {
      out.push(`# ${era.name} · ${era.from}—${era.to}`, '');
      lastEra = era;
    }
    out.push(`## ${chapter.year}`, '');
    for (const e of [...chapter.layers.kin, ...chapter.layers.court]) out.push(entryText(e), '');
    const far = chapter.far;
    if (far && (far.wars || far.deaths || far.successions)) {
      out.push(`Издали: ${[far.wars ? `войн — ${far.wars}` : '', far.deaths ? `смертей — ${far.deaths}` : '', far.successions ? `смен власти — ${far.successions}` : ''].filter(Boolean).join(', ')}.`, '');
    }
  }
  return out.join('\n');
}
