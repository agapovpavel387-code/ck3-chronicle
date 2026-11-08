/* Хроника рода · свод.
 *
 * Экран «Свод» и сборка документа хроники: главы, годы, экспорт.
 * Зависит: core, tree (цвета и названия линий), chronicle (главы).
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
function buildDoc() {
  const doc = el('doc');
  if (!doc) return;
  const chapters = collect();
  const s = state.settings;

  if (!chapters.length) {
    doc.innerHTML = `<div class="empty-state"><h3>В этих годах записей нет</h3>
        <p>Расширьте период или включите молву — тогда дальние вести тоже попадут в летопись.</p></div>`;
    return;
  }

  const { meta } = state.world;
  const periods = meta.periods || [];
  const eraOf = (year) => periods.find((p) => year >= p.from && year <= p.to);

  const head = `<header class="doc-head">
      <h2>Хроника дома ${esc(meta.player.house || '')}</h2>
      <p>${chapters[0].year}—${chapters[chapters.length - 1].year} · ${chapters.length} ${chapters.length === 1 ? 'год' : 'лет'} · ${esc(meta.player.title || 'без земли')}</p>
      ${(() => {
        const home = (state.world.realms || []).find((r) => r.id === meta.player.realm);
        if (!home || !home.ruler || home.ruler === meta.player.name) return '';
        return `<p class="small muted">Глава рода — ${esc(meta.player.name || '')}; главный титул дома (${esc(home.name)}) держит ${esc(home.ruler)}.</p>`;
      })()}
    </header>
    <details class="source-note">
      <summary>О источнике</summary>
      <p>Хронику ведёт двор дома ${esc(meta.player.house || '')}. Своё он знает доподлинно, о соседях пишет по вестям, дальнее для него — молва.</p>
      <p>Запись года идёт тремя слоями: <b>в роду</b> — что случилось с семьёй, <b>при дворе и рядом</b> — соседи и войны, <b>издали</b> — счёт вестей за дальними землями.</p>
      <p>Годы без записей — не пропуск: значит, до двора не дошло ничего, что стоило бы строки.</p>
    </details>
    <details class="source-note">
      <summary>Как читать</summary>
      <p><b>Держал</b> — титул был у человека на тот год. <b>Принял</b> — власть перешла к нему. <b>Потерял</b> — титул ушёл другому, и назван тот, к кому он отошёл.</p>
      <p><b>Владения</b> — графства и герцогства, которыми человек владеет по сейву. <b>Без земли</b> — родич без титула; если он живёт войной, стоит пометка «вольный отряд».</p>
      <p><b>Ветви.</b> Старший дом — тот, от которого пошёл род; кадетские — младшие дома той же династии; ваш дом — тот, за который играете. Главный титул дома может держать не глава рода — тогда в шапке досье сказано, кто именно.</p>
      <p><b>Издали</b> — вести за третьим кольцом: счёт и несколько имён, что мелькнули в них. Имён самих государей сейв в этих краях не хранит.</p>
      <p><b>Заложники.</b> Игра записывает, что заложника взяли или вернули; условий и сроков в сейве нет.</p>
      <p><b>Почему</b> — в сейве не сказано: он хранит, что случилось (темница, ссора, потеря титула), но не причину. Хроника не досочиняет её.</p>
      <p><b>Рождения</b> записаны там, где о них дошла весть; в дереве родни детей может быть больше — это не пропуск летописца, а предел источника.</p>
    </details>`;

  // Главы: по эпохам, а годы вне эпох — отдельной главой.
  const groups = [];
  let prevYear = null;
  for (const chapter of chapters) {
    const era = eraOf(chapter.year);
    const key = era ? era.name : 'Вне эпох';
    let group = groups[groups.length - 1];
    if (!group || group.key !== key) {
      const gap = prevYear != null && chapter.year - prevYear > 1
        ? `<p class="quiet">${prevYear + 1 === chapter.year - 1 ? `Год ${prevYear + 1}` : `Годы ${prevYear + 1}—${chapter.year - 1}`}: тишина, записей нет.</p>`
        : '';
      group = { key, era, years: [], lead: gap };
      groups.push(group);
    }
    group.years.push(chapter);
    prevYear = chapter.year;
  }

  const chunks = groups.map((group) => {
    const stats = chapterStats(group.years);
    const first = group.years[0].year;
    const last = group.years[group.years.length - 1].year;
    const ruler = group.era?.ruler ? `Глава рода — ${esc(group.era.ruler)}.` : '';
    const causes = Object.entries(stats.causes || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([family, n]) => `${CAUSE_RU[family] || family}${n > 1 ? ` ${n}` : ''}`)
      .join(', ');
    const totals = [
      stats.death ? `смертей — ${stats.death}` : '',
      stats.war ? `войн — ${stats.war}${causes ? ` (${causes})` : ''}` : '',
      stats.marriage ? `браков — ${stats.marriage}` : '',
      stats.birth ? `рождений — ${stats.birth}` : '',
      stats.succession ? `смен власти — ${stats.succession}` : '',
    ].filter(Boolean).join(', ');
    const header = `<header class="chapter__head">
        <p class="chapter__era">${esc(group.era?.name || 'Вне эпох')}</p>
        <p class="chapter__years">${group.era ? `${group.era.from}—${group.era.to}` : `${first}—${last}`}${group.era && (first > group.era.from || last < group.era.to) ? ` · записи ${first}—${last}` : ''}${ruler ? ` · ${ruler}` : ''}</p>
      </header>`;
    const summary = totals ? `<p class="chapter__sum">За эти годы: ${totals}.</p>` : '';
    const withGaps = group.years
      .map((chapter, index) => {
        const prev = index ? group.years[index - 1].year : null;
        if (prev == null || chapter.year - prev <= 1) return renderYear(chapter);
        const from = prev + 1;
        const to = chapter.year - 1;
        const label = from === to ? `Год ${from}` : `Годы ${from}—${to}`;
        return `<p class="quiet">${label}: тишина, записей нет.</p>${renderYear(chapter)}`;
      })
      .join('');
    return `<section class="chapter">${header}${group.lead}${withGaps}${summary}</section>`;
  });

  doc.innerHTML = head + prologue(chapters, s) + chunks.join('');
  const first = doc.querySelector('.entry--0') || doc.querySelector('.entry');
  if (first) first.classList.add('dropcap');
}
function docText() {
  const doc = el('doc');
  if (!doc) return '';
  const out = [];
  for (const chapter of doc.querySelectorAll('.chapter')) {
    const title = chapter.querySelector('.chapter__era')?.textContent || '';
    const years = chapter.querySelector('.chapter__years')?.textContent || '';
    out.push(`# ${title}${years ? ` · ${years}` : ''}`, '');
  }
  for (const section of doc.querySelectorAll('.year')) {
    out.push(`## ${section.querySelector('.year__num').textContent}`, '');
    for (const entry of section.querySelectorAll('.entry')) {
      const clone = entry.cloneNode(true);
      clone.querySelector('.truth')?.remove();
      out.push(clone.textContent.trim(), '');
    }
  }
  return out.join('\n');
}
/* ---------- свод ---------- */

function viewBook() {
  const { meta } = state.world;
  const gens = meta.generations || [];
  const blocks = gens
    .map((g) => {
      const kin = (state.world.people || []).filter((p) => p.kin && (p.gen ?? 0) === g.gen);
      const camps = kin.filter((p) => p.camp).map((p) => `${nameOf(p)} — отряд${p.campAt ? `, ${p.campAt}` : ''}`);
      const deaths = kin
        .filter((p) => p.death)
        .sort((a, b) => (yearOf(a.death) || 0) - (yearOf(b.death) || 0))
        .slice(0, 4)
        .map((p) => `${y0(p.death)} — умер(ла) ${nameOf(p)}${p.title ? `, ${p.title}` : ''}`)
        .join('; ');
      return `<article class="gen">
          <h3>${T('tree.generation', 'Поколение')} ${g.gen + 1}</h3>
          <p class="small muted">${g.from || '?'}—${g.to || '…'} · ${g.members} ${g.members === 1 ? 'человек' : 'человек'} · ${esc(g.names.join(', '))}</p>
          ${deaths ? `<p>${esc(deaths)}.</p>` : '<p class="muted">Сведений о смертях не сохранилось.</p>'}
          ${camps.length ? `<p class="small muted">Вольные отряды: ${esc(camps.join('; '))}.</p>` : ''}
        </article>`;
    })
    .join('');

  return `
      <div class="page-head"><h1>${T('book.title', 'Свод')}</h1>
        <p>Династия по поколениям: кто жил, когда и чем закончил. Это оглавление будущей книги.</p></div>
      <div id="bookRoot">
        ${(state.world.lineage?.lines || []).length
          ? `<section class="gen"><h3>Линии рода</h3><ol class="gen-list">${state.world.lineage.lines.map((line) => `<li><span class="branch-dot" style="background:${lineColor(line)}"></span><b>${esc(line.founder)}</b> <span class="small muted">${esc(lineKind(line.kind) || 'линия')} · ${line.size} ${plural(line.size, 'человек', 'человека', 'человек')}${line.birth ? ` · с ${esc(y0(line.birth))}` : ''}</span></li>`).join('')}</ol></section>`
          : ''}
        <div class="doc-actions" style="margin:0 0 18px">
          <button class="btn btn--ghost" type="button" id="downloadBook">${T('book.download', 'Скачать свод .md')}</button>
        </div>
        ${blocks || '<div class="empty-state"><h3>Поколений не видно</h3><p>В этом мире род слишком короток, чтобы делить его на поколения.</p></div>'}
      </div>`;
}
function bookText() {
  const { meta } = state.world;
  const out = [`# Свод дома ${meta.player.house || ''}`, '', `${meta.date}`, ''];
  for (const g of meta.generations || []) {
    out.push(`## Поколение ${g.gen + 1}`, `${g.from || '?'}—${g.to || '…'}, ${g.members} человек: ${g.names.join(', ')}`, '');
  }
  return out.join('\n');
}
