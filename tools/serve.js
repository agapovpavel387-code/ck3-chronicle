/* Local server for the app plus a small import API.
 *
 *   node tools/serve.js --open
 *
 * Endpoints:
 *   GET  /api/env     — detected game folder, extractor, python, existing worlds
 *   GET  /api/saves   — *.ck3 files in the CK3 save folder
 *   POST /api/import  — { save, game, lang } → starts the import, returns { started: true }
 *   GET  /api/import  — progress: { running, ok, error, lines: [...] }
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const APP = path.join(ROOT, 'app');
const DATA = path.join(APP, '_data');
const WORK = path.join(ROOT, 'import');

const PORT = argValue('--port', Number(process.env.PORT) || 8778);
const OPEN = process.argv.includes('--open');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) return fallback;
  const value = Number(process.argv[index + 1]);
  return Number.isFinite(value) ? value : fallback;
}

const SAVE_DIR = path.join(os.homedir(), 'Documents', 'Paradox Interactive', 'Crusader Kings III', 'save games');

function detectGame() {
  const candidates = [process.env.CK3_GAME].filter(Boolean);
  const steam = 'steamapps/common/Crusader Kings III/game';
  const suffixes = [`Games/Crusader Kings III/game`, `SteamLibrary/${steam}`, `Steam/${steam}`, `Program Files (x86)/Steam/${steam}`, `Program Files/Steam/${steam}`];
  for (const letter of 'CDEFGHIJKLMNOPQRSTUVWXYZ') {
    for (const suffix of suffixes) candidates.push(`${letter}:/${suffix}`);
  }
  candidates.push(path.join(os.homedir(), 'AppData/Local/Programs/Steam/steamapps/common/Crusader Kings III/game'));
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, 'map_data', 'provinces.png'))) return candidate;
  }
  return '';
}

function findExe(dir, depth) {
  if (depth < 0) return '';
  let entries = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return '';
  }
  let fallback = '';
  for (const entry of entries) {
    if (!entry.isFile() || !/^ck3_history_extractor.*\.exe$/i.test(entry.name)) continue;
    if (entry.name.toLowerCase() === 'ck3_history_extractor.exe') return path.join(dir, entry.name);
    if (!fallback) fallback = path.join(dir, entry.name);
  }
  if (fallback) return fallback;
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (entry.name === 'node_modules' || entry.name === '.git') continue;
    const found = findExe(path.join(dir, entry.name), depth - 1);
    if (found) return found;
  }
  return '';
}

function detectExtractor() {
  const direct = [
    process.env.CK3_EXTRACTOR,
    path.join(ROOT, 'ck3_history_extractor.exe'),
    path.join(ROOT, 'tools', 'ck3_history_extractor.exe'),
    path.join(ROOT, 'vendor', 'ck3_history_extractor.exe'),
  ].filter(Boolean);
  for (const candidate of direct) {
    if (fs.existsSync(candidate)) return candidate;
  }
  // Рядом с проектом и чуть глубже: CK3-history-extractor*/**/ck3_history_extractor.exe
  for (const base of [path.dirname(ROOT), path.dirname(path.dirname(ROOT))]) {
    const found = findExe(base, 3);
    if (found) return found;
  }
  // Типичное место рядом с сохранениями.
  const documents = path.join(os.homedir(), 'Documents', 'Paradox Interactive', 'Crusader Kings III', 'mod');
  const found = findExe(documents, 3);
  if (found) return found;
  return '';
}

function detectPython() {
  const candidates = ['python.exe', 'python3.exe', 'python', 'py'];
  for (const candidate of candidates) {
    const found = which(candidate);
    if (found) return found;
  }
  return '';
}

function which(command) {
  const envPath = process.env.PATH || '';
  const exts = process.platform === 'win32' ? ['', '.exe', '.bat', '.cmd'] : [''];
  for (const dir of envPath.split(path.delimiter)) {
    for (const ext of exts) {
      const candidate = path.join(dir, command + ext);
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return '';
}


let installState = { running: false, ok: null, lines: [] };

function checkPackages() {
  const python = detectPython();
  if (!python) return { python: false, ijson: false, numpy: false, pillow: false };
  const code = 'import importlib.util\n' +
    'mods={"ijson":"ijson","numpy":"numpy","pillow":"PIL"}\n' +
    'print(" ".join(k for k,v in mods.items() if importlib.util.find_spec(v)))\n';
  try {
    const out = require('child_process').execFileSync(python, ['-c', code], { encoding: 'utf8', timeout: 15000 });
    const found = new Set(out.trim().split(/\s+/));
    return { python: true, ijson: found.has('ijson'), numpy: found.has('numpy'), pillow: found.has('pillow') };
  } catch {
    return { python: true, ijson: false, numpy: false, pillow: false };
  }
}

function startInstall() {
  if (installState.running) return;
  const python = detectPython();
  installState = { running: true, ok: null, lines: [] };
  if (!python) {
    installState.running = false;
    installState.ok = false;
    installState.lines.push('Python не найден.');
    return;
  }
  const requirements = path.join(ROOT, 'requirements.txt');
  const child = spawn(python, ['-m', 'pip', 'install', '-r', requirements], {
    cwd: ROOT,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  });
  const push = (chunk) => String(chunk).split(/\r?\n/).filter(Boolean).forEach((line) => {
    installState.lines.push(line);
    if (installState.lines.length > 300) installState.lines.shift();
  });
  child.stdout.on('data', push);
  child.stderr.on('data', push);
  child.on('error', (error) => { installState.running = false; installState.ok = false; push(error.message); });
  child.on('close', (code) => {
    installState.running = false;
    installState.ok = code === 0;
    push(code === 0 ? 'Пакеты установлены.' : `pip завершился с кодом ${code}`);
  });
}


function isOutdated() {
  try {
    const source = fs.readFileSync(path.join(ROOT, 'tools', 'build_world.py'), 'utf8');
    // Старые копии печатали «×», которого нет в cp1251, и падали при импорте.
    return source.includes('\u00d7') || !source.includes('reconfigure(encoding=');
  } catch {
    return true;
  }
}

let job = { running: false, ok: null, error: '', lines: [], startedAt: 0, lastActivity: 0, save: '' };
let jobChild = null;

function pushLine(line) {
  const text = String(line).replace(/\s+$/, '');
  if (!text) return;
  job.lines.push(text);
  job.lastActivity = Date.now();
  if (job.lines.length > 400) job.lines.shift();
}

function listSaves() {
  try {
    return fs.readdirSync(SAVE_DIR)
      .filter((name) => name.toLowerCase().endsWith('.ck3'))
      .map((name) => {
        const full = path.join(SAVE_DIR, name);
        const stat = fs.statSync(full);
        return { name, path: full, size: stat.size, mtime: stat.mtimeMs };
      })
      .sort((a, b) => b.mtime - a.mtime);
  } catch {
    return [];
  }
}

function sendJson(res, code, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (chunk) => { data += chunk; if (data.length > 1e6) req.destroy(); });
    req.on('end', () => {
      try { resolve(JSON.parse(data || '{}')); } catch { resolve({}); }
    });
  });
}

function startImport(options) {
  if (job.running) return false;
  const python = options.python || detectPython();
  let extractor = options.extractor && fs.existsSync(options.extractor) ? options.extractor : detectExtractor();
  const game = options.game || detectGame();
  const save = options.save;

  job = { running: true, ok: null, error: '', lines: [], startedAt: Date.now(), save };
  if (!python) { job.running = false; job.ok = false; job.error = 'Python not found'; return true; }
  if (!extractor) {
    job.running = false;
    job.ok = false;
    job.error = 'Экстрактор не найден. Укажите путь к ck3_history_extractor.exe в поле «Экстрактор» или положите его в папку проекта.';
    return true;
  }
  if (!save || !fs.existsSync(save)) { job.running = false; job.ok = false; job.error = 'Save file not found'; return true; }

  fs.mkdirSync(WORK, { recursive: true });
  const args = [
    path.join(ROOT, 'tools', 'import_save.py'),
    '--save', save,
    '--extractor', extractor,
    '--yes',
    '--out', DATA,
    '--lang', options.lang || 'russian',
  ];
  if (game) args.push('--game', game);

  pushLine(`Starting: ${path.basename(save)}`);
  job.lastActivity = Date.now();
  const child = spawn(python, args, {
    cwd: ROOT,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  });
  jobChild = child;

  child.stdout.on('data', (chunk) => String(chunk).split(/\r?\n/).forEach(pushLine));
  child.stderr.on('data', (chunk) => String(chunk).split(/\r?\n/).forEach(pushLine));
  child.on('error', (error) => {
    job.running = false;
    job.ok = false;
    job.error = error.message;
    pushLine(`Error: ${error.message}`);
  });
  child.on('close', (code) => {
    jobChild = null;
    job.running = false;
    job.ok = code === 0;
    if (code !== 0) job.error = `Импорт завершился с кодом ${code}`;
    pushLine(code === 0 ? 'Готово.' : `Код выхода: ${code}`);
  });
  return true;
}

function serveStatic(req, res) {
  const url = decodeURIComponent((req.url || '/').split('?')[0]);
  const rel = url === '/' ? 'index.html' : url.replace(/^\/+/, '');
  const file = path.resolve(APP, rel);
  if (!file.startsWith(APP)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Forbidden');
    return;
  }
  fs.readFile(file, (error, data) => {
    if (error) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Not found: ' + rel);
      return;
    }
    // Приложение локальное: свежесть важнее кэша. Иначе браузер держит старый
  // index.html и старые карты, а данные приходят новые — и титулы «съезжают».
  res.writeHead(200, {
    'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream',
    'Cache-Control': 'no-store, must-revalidate',
  });
    res.end(data);
  });
}

const server = http.createServer(async (req, res) => {
  const url = (req.url || '/').split('?')[0];

  if (url === '/api/env') {
    sendJson(res, 200, {
      game: detectGame(),
      extractor: detectExtractor(),
      python: detectPython(),
      saveDir: SAVE_DIR,
      hasWorld: fs.existsSync(path.join(DATA, 'world.js')),
      packages: checkPackages(),
      outdated: isOutdated(),
    });
    return;
  }

  if (url === '/api/install' && req.method === 'POST') {
    startInstall();
    sendJson(res, 200, { started: true, install: installState });
    return;
  }

  if (url === '/api/install') {
    sendJson(res, 200, installState);
    return;
  }

  if (url === '/api/saves') {
    const saves = listSaves();
    sendJson(res, 200, { dir: SAVE_DIR, saves });
    return;
  }

  if (url === '/api/import' && req.method === 'POST') {
    const body = await readBody(req);
    if (job.running) {
      // Импорт уже идёт — не ошибка: пусть панель продолжит показывать прогресс.
      sendJson(res, 200, { started: false, running: true, job });
      return;
    }
    const started = startImport(body);
    sendJson(res, 200, { started, running: job.running, job });
    return;
  }

  if (url === '/api/import/cancel' && req.method === 'POST') {
    if (jobChild) {
      try { jobChild.kill(); } catch { /* уже завершился */ }
      pushLine('Импорт остановлен пользователем.');
    }
    job.running = false;
    job.ok = false;
    job.error = 'Импорт остановлен.';
    sendJson(res, 200, { stopped: true });
    return;
  }

  if (url === '/api/import') {
    if (job.running && job.lastActivity && Date.now() - job.lastActivity > 10 * 60 * 1000) {
      if (jobChild) { try { jobChild.kill(); } catch { /* уже мёртв */ } }
      job.running = false;
      job.ok = false;
      job.error = 'Импорт завис: десять минут без ответа. Попробуйте ещё раз.';
      pushLine(job.error);
    }
    sendJson(res, 200, { ...job, elapsed: job.running ? Date.now() - job.startedAt : 0 });
    return;
  }

  if (url.startsWith('/api/')) {
    sendJson(res, 404, { error: 'unknown endpoint' });
    return;
  }

  serveStatic(req, res);
});

server.on('error', (error) => {
  if (error.code === 'EADDRINUSE') {
    console.error(`Port ${PORT} is busy. Try: node tools/serve.js --port ${PORT + 1} --open`);
  } else {
    console.error(error.message);
  }
  process.exit(1);
});

server.listen(PORT, '127.0.0.1', () => {
  const address = `http://127.0.0.1:${PORT}/`;
  console.log(`Chronicle of the House — ${address}`);
  console.log(`Saves: ${SAVE_DIR}`);
  console.log('Press Ctrl+C to stop.');
  if (OPEN) openBrowser(address);
});

function openBrowser(url) {
  const command = process.platform === 'win32' ? 'cmd' : process.platform === 'darwin' ? 'open' : 'xdg-open';
  const args = process.platform === 'win32' ? ['/c', 'start', '', url] : [url];
  try {
    spawn(command, args, { detached: true, stdio: 'ignore' }).unref();
  } catch {
    /* адрес напечатан выше */
  }
}
