# Выкладка на GitHub / Publishing

Памятка: что проверяется само, а что делается руками при публикации.

## Что готово

- `VERSION` — единственный источник версии; `python tools/stamp.py --check` сверяет с ним
  `package.json`, `index.html`, шапки README и `RELEASE_NOTES`;
- `docs/facts.md` — числа мира, посчитанные из данных (`tools/facts.py --check`);
- `tools/check_docs.py` — ссылки, версия в шапке, запрет вписанных руками чисел;
- `tools/release.py` и `make.cmd` — архив по белому списку, манифест с sha256, распаковка и проверка;
- CI `.github/workflows/tests.yml` — те же гейты на каждый push;
- README на двух языках, `CONTRIBUTING.md`, шаблон issue, `LICENSE`, `NOTICE`.

## Шаг 1. Коммит и теги

```powershell
$v = (Get-Content VERSION -Raw).Trim()
git add -A
git commit -m "…"
git tag -a $v -m $v
git push origin main
git push origin --tags
```

## Шаг 2. Сборка архива

```powershell
.\make.cmd
```

Он прогонит тесты, пересчитает `docs/facts.md`, проверит документы, соберёт
`dist/chronicle-of-the-house-<версия>.zip` и рядом `.manifest.json` (список файлов, размеры,
sha256), распакует архив и проверит его: `index.html` на месте, `world.js` разбирается,
сейвов, токенов и личных путей нет. Архив, не прошедший самопроверку, выпускать нельзя.

## Шаг 3. Release

Тег → **Draft a new release** → заголовок = версия → в описание вставить `RELEASE_NOTES.md`
→ приложить два архива:

- `dist/chronicle-of-the-house-<версия>.zip` — приложение;
- `ck3_history_extractor-2.4.7-ck3-1.20-win64.zip` — экстрактор с патчем 1.20
  (в git не входит, поэтому прикладывается отдельно).

## Шаг 4. Проверка после публикации

1. Вкладка **Actions** — workflow `checks` зелёный.
2. Скачать архив из Release, распаковать, запустить `start.cmd` — приложение открывается.
3. В репозитории нет файлов больше 50 МБ (самый крупный — `world.js`).

## Чего в репозитории быть не должно

- `.ck3`, `gamestate.json`, `_cache/`, `import/`, `_export/`, `dist/`, `node_modules/`;
- личных путей вида `C:\Users\...`, `D:\Games\...`;
- токенов `tokens_1.tok`.

Проверка одна на всё: `python -X utf8 tools/release.py --skip-tests` — самопроверка архива
ловит и пути, и сейвы, и токены.
