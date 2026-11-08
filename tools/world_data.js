/* Чтение мира из `_data/world.js`.
 *
 * Мир лежит одним файлом: `window.__WORLD__={…};` — так он работает и через
 * `file://`, и через сервер, без второго дубля на десять мегабайт.
 * Проверки читают тот же файл, что и страница.
 */
const fs = require('fs');
const path = require('path');

function readWorld(appDir) {
  const file = path.join(appDir, '_data', 'world.js');
  const raw = fs.readFileSync(file, 'utf8');
  const start = raw.indexOf('{');
  const end = raw.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error(`в ${file} нет данных мира`);
  return JSON.parse(raw.slice(start, end + 1));
}

module.exports = { readWorld };
