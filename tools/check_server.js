/* Проверка сервера: отдаёт страницу, данные мира и отвечает по API.
 *
 * Сервер поднимается на свободном порту и гасится после проверки. Импорт не
 * запускается — только чтение: `/api/env`, `/api/saves`, `/api/import`.
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const http = require('http');

const APP = process.argv[2] || '.';
// Аргумент — папка приложения; корень репозитория ищем по tools/serve.js.
const ROOT = fs.existsSync(path.join(APP, 'tools', 'serve.js')) ? APP : path.resolve(APP, '..');
const PORT = 8899;
const results = [];
const check = (name, ok, extra = '') => results.push({ name, ok, extra });

const get = (url, method = 'GET') =>
  new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: PORT, path: url, method }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, body, type: res.headers['content-type'] || '' }));
    });
    req.on('error', reject);
    req.end();
  });

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const server = spawn(process.execPath, [path.join(ROOT, 'tools', 'serve.js'), '--port', String(PORT)], {
    cwd: ROOT,
    stdio: 'ignore',
  });

  let ready = false;
  for (let i = 0; i < 40 && !ready; i += 1) {
    await wait(150);
    try {
      const res = await get('/');
      ready = res.status === 200;
    } catch { /* сервер ещё поднимается */ }
  }

  try {
    check('сервер поднялся', ready, ready ? `порт ${PORT}` : 'нет ответа');
    if (ready) {
      const page = await get('/');
      check('страница отдаётся', page.status === 200 && page.body.includes('<html'), `статус ${page.status}`);
      check('страница — HTML', page.type.includes('text/html'), page.type);

      const world = await get('/_data/world.js');
      check('мир отдаётся', world.status === 200 && world.body.startsWith('window.__WORLD__'), `статус ${world.status}`);

      const env = await get('/api/env');
      let envJson = null;
      try { envJson = JSON.parse(env.body); } catch { /* не JSON */ }
      check('/api/env отвечает', env.status === 200 && Boolean(envJson), `статус ${env.status}`);
      check('/api/env знает про мир', Boolean(envJson) && 'hasWorld' in envJson, JSON.stringify(envJson || {}).slice(0, 80));

      const saves = await get('/api/saves');
      let savesJson = null;
      try { savesJson = JSON.parse(saves.body); } catch { /* не JSON */ }
      check('/api/saves отвечает', saves.status === 200 && Boolean(savesJson), `статус ${saves.status}`);

      const progress = await get('/api/import');
      let progressJson = null;
      try { progressJson = JSON.parse(progress.body); } catch { /* не JSON */ }
      check('/api/import читает прогресс', progress.status === 200 && Boolean(progressJson), `статус ${progress.status}`);

      const unknown = await get('/api/nothing-here');
      check('неизвестный API — 404', unknown.status === 404, `статус ${unknown.status}`);

      const missing = await get('/_data/no-such-file.png');
      check('отсутствующий файл — 404', missing.status === 404, `статус ${missing.status}`);
    }
  } catch (error) {
    check('проверка сервера без ошибок', false, String(error.message));
  } finally {
    server.kill();
  }

  let failed = 0;
  for (const r of results) {
    if (!r.ok) failed += 1;
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
  }
  console.log(`\nитог: ${results.length - failed}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
