/* Список скриптов приложения — из index.html, чтобы проверки и страница
 * читали один и тот же порядок модулей.
 */
const fs = require('fs');
const path = require('path');

function localScripts(app) {
  const html = fs.readFileSync(path.join(app, 'index.html'), 'utf8');
  return [...html.matchAll(/<script\s+src="([^"]+)"/g)]
    .map((m) => m[1].replace(/[?#].*$/, ''))
    .filter((src) => !/^(https?:)?\/\//.test(src));
}

/* Вставляет скрипты в документ по порядку. i18n.js по умолчанию пропускается:
 * часть проверок работает без словаря, на русских запасных текстах. */
function inject(doc, app, { i18n = false } = {}) {
  for (const src of localScripts(app)) {
    if (!i18n && src === 'i18n.js') continue;
    const node = doc.createElement('script');
    node.textContent = fs.readFileSync(path.join(app, src), 'utf8');
    doc.body.append(node);
  }
  return localScripts(app);
}

module.exports = { localScripts, inject };
