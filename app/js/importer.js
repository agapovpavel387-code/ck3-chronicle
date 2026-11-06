/* Хроника рода · импорт сохранения.
 *
 * Экран «Своё сохранение»: список сейвов, окружение, запуск и журнал импорта.
 * Зависит: core, shell.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
/* Панель импорта: выбор сохранения, запуск конвертации, прогресс. */

const IMPORTER_CSS = `
.import { max-width: 720px; }
.import__row { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; margin: 14px 0; }
.import__row label { display: flex; flex-direction: column; gap: 4px; font-size: .8125rem; color: var(--muted); }
.import__row select, .import__row input { min-width: 280px; padding: 7px 9px; border: 1px solid var(--rule-strong); background: var(--surface); font-family: var(--font-body); font-size: .875rem; color: var(--ink); }
.import__hint { font-size: .8125rem; color: var(--muted); margin: 6px 0 0; }
.import__log { margin-top: 16px; padding: 10px 12px; background: var(--surface-2); border-left: 2px solid var(--rule-strong); font-family: var(--font-mono); font-size: .75rem; line-height: 1.5; max-height: 260px; overflow: auto; white-space: pre-wrap; }
.import__status { margin-top: 12px; font-size: .875rem; }
.import__status.is-error { color: var(--accent); }
`;
function importerMarkup() {
return `<div class="page-head"><h1>Своё сохранение</h1>
      <p>Выберите файл <code>.ck3</code> — утилита сама снимет дамп, соберёт мир и карту, после чего хроника откроется заново.</p></div>
    <section class="card import" id="importPanel">
      <p class="import__hint" id="importEnv">Ищу сохранения…</p>
      <div class="import__row">
        <label>Сохранение<select id="importSave"><option value="">— выберите файл —</option></select></label>
        <button class="btn btn--ghost btn--small" type="button" id="importRefresh">Обновить список</button>
      </div>
      <div class="import__row">
        <label>Папка игры (для карты)<input type="text" id="importGame" placeholder="…/Crusader Kings III/game"></label>
      </div>
      <div class="import__row">
        <label>Экстрактор (если не найден)<input type="text" id="importExtractor" placeholder="…/ck3_history_extractor.exe"></label>
      </div>
      <div class="import__row">
        <label>Язык имён<select id="importLang">
          <option value="russian">русский</option>
          <option value="english">english</option>
          <option value="french">français</option>
          <option value="german">deutsch</option>
          <option value="spanish">español</option>
        </select></label>
        <button class="btn" type="button" id="importStart">Импортировать</button>
        <button class="btn btn--ghost btn--small" type="button" id="importCancel" hidden>Остановить</button>
      </div>
      <p class="import__hint">Карты в сейве нет: игра хранит её в папке <code>game/map_data</code>. Если папка уже известна, поле заполнится само.</p>
      <div class="import__deps" id="importDeps" hidden>
        <p class="import__hint">Для конвертации нужны Python-пакеты <code>ijson</code>, <code>numpy</code>, <code>pillow</code>.</p>
        <button class="btn btn--ghost btn--small" type="button" id="importInstall">Установить зависимости</button>
        <pre class="import__log" id="importDepsLog" hidden></pre>
      </div>
      <div class="import__status" id="importStatus" hidden></div>
      <pre class="import__log" id="importLog" hidden></pre>
    </section>`;
}
async function setupImporter(root) {
if (!root) return;
const style = document.createElement('style');
style.textContent = IMPORTER_CSS;
document.head.append(style);

const saveSelect = root.querySelector('#importSave');
const gameInput = root.querySelector('#importGame');
const extractorInput = root.querySelector('#importExtractor');
const langSelect = root.querySelector('#importLang');
const startButton = root.querySelector('#importStart');
const cancelButton = root.querySelector('#importCancel');
const status = root.querySelector('#importStatus');
const log = root.querySelector('#importLog');
const envNote = root.querySelector('#importEnv');
const refresh = root.querySelector('#importRefresh');
const depsBlock = root.querySelector('#importDeps');
const depsButton = root.querySelector('#importInstall');
const depsLog = root.querySelector('#importDepsLog');

const api = async (url, options) => {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const showStatus = (text, isError) => {
  status.hidden = !text;
  status.textContent = text || '';
  status.classList.toggle('is-error', Boolean(isError));
};

const loadSaves = async () => {
  try {
    const data = await api('/api/saves');
    saveSelect.innerHTML = '<option value="">— выберите файл —</option>';
    for (const save of data.saves || []) {
      const option = document.createElement('option');
      option.value = save.path;
      const size = Math.round(save.size / 1048576);
      const when = new Date(save.mtime).toLocaleDateString('ru-RU');
      option.textContent = `${save.name} · ${size} МБ · ${when}`;
      saveSelect.append(option);
    }
    envNote.textContent = data.saves?.length
      ? `Найдено сохранений: ${data.saves.length}. Папка: ${data.dir}`
      : `Сохранений не найдено в ${data.dir}. Укажите файл вручную, положив его в папку игры.`;
  } catch (error) {
    envNote.textContent = 'Список сохранений недоступен: приложение открыто не через start.cmd.';
  }
};

const loadEnv = async () => {
  try {
    const env = await api('/api/env');
    if (env.game) gameInput.value = env.game;
    if (env.outdated) {
      showStatus('Копия проекта устарела: в ней старый сборщик мира, который падает при импорте. Скачайте свежий архив или обновите папку tools.', true);
    }
    const packages = env.packages || {};
    const missing = ['ijson', 'numpy', 'pillow'].filter((name) => !packages[name]);
    if (missing.length) {
      depsBlock.hidden = false;
      depsBlock.dataset.missing = missing.join(', ');
      showStatus(`Не хватает пакетов: ${missing.join(', ')}. Нажмите «Установить зависимости».`, true);
    }
    if (env.extractor) {
      extractorInput.value = env.extractor;
    } else {
      showStatus('Экстрактор не найден автоматически. Укажите путь к ck3_history_extractor.exe ниже — он запомнится на этот запуск.', true);
    }
  } catch {
    /* без API поле останется пустым */
  }
};

refresh?.addEventListener('click', loadSaves);

depsButton?.addEventListener('click', async () => {
  depsButton.disabled = true;
  depsLog.hidden = false;
  depsLog.textContent = 'Установка пакетов…';
  try {
    await api('/api/install', { method: 'POST' });
    const pollInstall = async () => {
      const state = await api('/api/install');
      if (state.lines?.length) {
        depsLog.textContent = state.lines.join('\n');
        depsLog.scrollTop = depsLog.scrollHeight;
      }
      if (state.running) { setTimeout(pollInstall, 1500); return; }
      depsButton.disabled = false;
      if (state.ok) {
        depsBlock.hidden = true;
        showStatus('Пакеты установлены. Можно импортировать.');
        loadEnv();
      } else {
        showStatus('Установка не удалась — смотрите журнал.', true);
      }
    };
    pollInstall();
  } catch (error) {
    depsButton.disabled = false;
    showStatus(`Не удалось запустить установку: ${error.message}`, true);
  }
});

startButton?.addEventListener('click', async () => {
  const save = saveSelect.value;
  if (!save) { showStatus('Сначала выберите сохранение.', true); return; }
  startButton.disabled = true;
  log.hidden = false;
  log.textContent = '';
  showStatus('Идёт импорт: сначала дамп сейва, затем сборка мира. Это минута-две.');
  try {
    const reply = await api('/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        save,
        game: gameInput.value.trim(),
        extractor: extractorInput.value.trim(),
        lang: langSelect.value,
      }),
    });
    if (reply && reply.started === false) showStatus('Импорт уже идёт — показываю его прогресс.');
    cancelButton.hidden = false;
    poll();
  } catch (error) {
    startButton.disabled = false;
    showStatus(`Не удалось начать импорт: ${error.message}`, true);
  }
});

cancelButton?.addEventListener('click', async () => {
  cancelButton.disabled = true;
  try {
    await api('/api/import/cancel', { method: 'POST' });
    showStatus('Импорт остановлен.');
    startButton.disabled = false;
    cancelButton.hidden = true;
  } catch (error) {
    showStatus(`Не удалось остановить: ${error.message}`, true);
  } finally {
    cancelButton.disabled = false;
  }
});

const poll = async () => {
  try {
    const job = await api('/api/import');
    if (job.lines?.length) {
      log.textContent = job.lines.join('\n');
      log.scrollTop = log.scrollHeight;
    }
    if (job.running) {
      setTimeout(poll, 1200);
      return;
    }
    startButton.disabled = false;
    cancelButton.hidden = true;
    if (job.ok) {
      showStatus('Готово. Открываю хронику…');
      setTimeout(() => window.location.reload(), 900);
    } else {
      const tail = (job.lines || []).slice(-6).join(' · ');
      showStatus(`Импорт не удался: ${job.error || 'смотрите журнал ниже'}${tail ? ` — ${tail}` : ''}`, true);
    }
  } catch {
    setTimeout(poll, 2000);
  }
};

await loadEnv();
await loadSaves();
}
