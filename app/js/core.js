/* Хроника рода · ядро.
 *
 * Состояние, настройки, индексы мира и общие помощники: даты, имена, числа.
 * Зависит: нет — загружается первым.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
const DATA_URL = '_data/world.json';
const STORE = 'chronicle.knowledge.v2';
// Свёрнутость и камера рода: одно начальное состояние для загрузки и сброса.
function freshTree() {
  return { scale: 1, x: 0, y: 0, query: '', list: false, kinOnly: true, focus: null, line: null, mode: 'outline', open: null };
}
const state = {
  world: null,
  view: 'tree',
  personId: null,
  settings: loadSettings(),
  tree: freshTree(),
  lens: 'radius',
  mapLayer: 'houses',
};
// i18n.js может отсутствовать (например, в тестах) — тогда берём русский текст.
const T = (key, fallback) => (typeof window.t === 'function' ? window.t(key, fallback) : fallback);
const el = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function loadSettings() {
  const fallback = { from: null, to: null, deaths: true, successions: true, wars: true, private: true, rumors: false, truth: false };
  try {
    const raw = localStorage.getItem(STORE);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}
const saveSettings = () => { try { localStorage.setItem(STORE, JSON.stringify(state.settings)); } catch { /* приватный режим */ } };
/* ---------- индексы ---------- */

const ix = { people: new Map(), names: new Map(), byYear: new Map(), years: [], totals: new Map() };
const KIND_WEIGHT = { death: 0, succession: 1, title_loss: 2, war: 3, battle: 4, war_win: 5, war_loss: 6, birth: 7, marriage: 9, prison: 10, note: 12 };
function index(world) {
  ix.people.clear(); ix.names.clear(); ix.byYear.clear(); ix.totals.clear(); ix.years = [];
  for (const p of world.people || []) ix.people.set(p.id, p);
  for (const [id, n] of Object.entries(world.names || {})) ix.names.set(Number(id), n);
  for (const e of world.events || []) {
    const y = yearOf(e.date);
    if (!y) continue;
    if (!ix.byYear.has(y)) ix.byYear.set(y, []);
    ix.byYear.get(y).push(e);
    ix.totals.set(y, (ix.totals.get(y) || 0) + 1);
  }
  ix.years = [...ix.byYear.keys()].sort((a, b) => a - b);
  for (const list of ix.byYear.values())
    list.sort((a, b) => a.grade - b.grade || (KIND_WEIGHT[a.kind] ?? 10) - (KIND_WEIGHT[b.kind] ?? 10) || String(a.date).localeCompare(String(b.date)));
}
const yearOf = (d) => {
  if (!d) return null;
  const y = Number(String(d).slice(0, 4));
  return Number.isFinite(y) && y > 0 && y < 9000 ? y : null;
};
const y0 = (d) => (d ? String(yearOf(d) ?? '') : '');
const who = (id) => (id ? ix.people.get(Number(id)) || ix.names.get(Number(id)) || null : null);
// Выбор формулировки: детерминированный по событию, чтобы соседние записи не повторялись.
const eventHash = (e) => {
  const key = `${e.date || ''}|${e.who || ''}|${e.who2 || ''}|${e.kind || ''}|${e.title || ''}`;
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash;
};
const pickVariant = (e, variants) => variants[eventHash(e) % variants.length];
const nameOf = (p) => (p ? `${p.name}${p.nick ? ' ' + p.nick : ''}` : 'безымянный');
const houseOf = (p) => {
  if (!p) return '';
  const raw = p.house_name || (typeof p.house === 'string' ? p.house : '');
  return String(raw).startsWith('House ') ? '' : String(raw);
};
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
function ageAt(p, date) {
  if (!p || !p.birth) return null;
  const b = yearOf(p.birth);
  const d = yearOf(date);
  const age = b && d ? d - b : null;
  return age !== null && age >= 0 && age < 110 ? age : null;
}
function plural(n, one, few, many, enOne, enMany) {
  const lang = window.currentLang ? window.currentLang() : 'ru';
  if (lang === 'en' && enOne) return n === 1 ? enOne : (enMany || `${enOne}s`);
  const tail = n % 100, last = n % 10;
  if (tail >= 11 && tail <= 14) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}
function yearsRu(n) {
  const t = n % 100, l = n % 10;
  if (t >= 11 && t <= 14) return `${n} лет`;
  if (l === 1) return `${n} год`;
  if (l >= 2 && l <= 4) return `${n} года`;
  return `${n} лет`;
}
const dateRu = (d) => {
  const y = yearOf(d);
  if (!y) return '';
  const [, m, day] = String(d).split('-').map(Number);
  if (!m || !day) return `${y}`;
  const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  return `${day} ${months[m - 1]} ${y}`;
};
const MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
function dateText(d) {
  const lang = window.currentLang ? window.currentLang() : 'ru';
  if (lang !== 'en') return dateRu(d);
  const y = yearOf(d);
  if (!y) return '';
  const [, m, day] = String(d).split('-').map(Number);
  if (!m || !day) return `${y}`;
  return `${day} ${MONTHS_EN[m - 1]} ${y}`;
}
const died = (p) => (p && p.female ? 'умерла' : 'умер');
const born = (p) => (p && p.female ? 'родилась' : 'родился');
function traitsPhrase(p) {
  if (!p || !p.traits || !p.traits.length) return '';
  const t = p.traits.slice(0, 2).map((x) => x.toLowerCase());
  const who = p.female ? 'ней' : 'нём';
  return t.length > 1 ? ` При ${who} — ${t[0]} и ${t[1]}.` : ` При ${who} — ${t[0]}.`;
}
/* ---------- загрузка ---------- */

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`не удалось прочитать ${src}`));
    document.head.append(s);
  });
}
