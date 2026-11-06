# Как помочь проекту / Contributing

## По-русски

Проект в альфе. Полезнее всего:

1. **Сообщение об ошибке.** Откройте issue по шаблону: что делали, что ожидали, что получилось. Если падает импорт — приложите последние строки журнала со страницы «Своё сохранение».
2. **Сейв, на котором видно проблему.** Не публикуйте личные сохранения: достаточно сказать год, дом и что не сошлось.
3. **Правка кода.** Форк → ветка → изменение → `npm ci && npm test` → pull request. Все четыре набора проверок должны быть зелёными.

Что стоит знать перед правкой:

- приложение работает **без сборки**: `app/` — статические файлы, `index.html` подключает `i18n.js`, `notes.js` и модули `app/js/` (порядок проверки берут из самой страницы через `tools/app_scripts.js`);
- интерфейс двуязычный: новые подписи добавляйте в `app/i18n.js` (ru и en), в коде — через `T('ключ', 'запасной текст')`;
- текст летописи и досье идёт на языке сейва — его не переводят;
- «не выдумывать факты» — правило проекта: если сейв чего-то не хранит, интерфейс говорит об этом прямо.

## In English

The project is in alpha. The most useful contributions:

1. **A bug report.** Use the issue template: what you did, what you expected, what happened. For import failures attach the last lines of the log from the "Your save" page.
2. **A save that shows the problem.** Please do not publish personal saves: the year, the house and what looked wrong is enough.
3. **A code change.** Fork → branch → change → `npm ci && npm test` → pull request. All four check suites must be green.

Before you change code:

- the app runs **without a build**: `app/` is static, `index.html` loads `i18n.js`, `notes.js` and the modules in `app/js/` (the order is read from the page by `tools/app_scripts.js`);
- the interface is bilingual: add new labels to `app/i18n.js` (ru and en) and use `T('key', 'fallback')` in code;
- chronicle and dossier texts follow the save language and are never translated;
- "do not invent facts" is a project rule: when the save does not hold something, the interface says so.
