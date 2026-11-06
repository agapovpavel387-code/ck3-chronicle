# Выкладка на GitHub / Publishing

Памятка: что уже готово, что сделать руками при публикации.
A checklist: what is ready and what to do by hand when publishing.

## Что готово

- ветка `main`, рабочее дерево чистое; авторы коммитов — ваш аккаунт;
- тег `v0.1.0-alpha`;
- `VERSION`, `CHANGELOG.md`, `RELEASE_NOTES.md`;
- README на двух языках, `CONTRIBUTING.md`, шаблон issue;
- CI: `.github/workflows/tests.yml` — гоняет `npm test` на каждый push;
- `.gitattributes` (LF в репозитории), `.gitignore` (сейвы, дампы, кэш, `_export`, `import`);
- ни личных путей, ни токенов в файлах нет — проверено поиском.

## Шаг 1. Создать пустой репозиторий

Вариант с `gh` (если установлен):

```powershell
gh repo create ck3-chronicle --public --source . --remote origin --push
```

Вариант через сайт: github.com → **New repository** → имя `ck3-chronicle` →
**без** README, .gitignore и лицензии (они уже есть) → Create.

## Шаг 2. Подключить и запушить

```powershell
cd ck3-chronicle
git remote add origin https://github.com/agapovpavel387-code/ck3-chronicle.git
git push -u origin main
git push origin v0.1.0-alpha
```

## Шаг 3. Описание и темы репозитория

Description:

> Chronicle of the House — a local app that turns a Crusader Kings III save into a family chronicle: house lines, map lenses, a layered chronicle. Alpha, CK3 1.20.x.

Topics:

```
crusader-kings-3 ck3 paradox-interactive save-parser alfa alpha
javascript vanilla-js local-first offline rust-extractor game-tools history-visualization
```

## Шаг 4. Release

Тег `v0.1.0-alpha` → **Draft a new release** → выбрать тег → заголовок `0.1.0-alpha` →
в описание вставить раздел из `RELEASE_NOTES.md` → приложить архив
`chronicle-of-the-house-0.1.0-alpha.zip`.

## Шаг 5. Проверка после публикации

1. Открыть репозиторий в режиме инкогнито: README читается, картинок-заглушек нет.
2. Вкладка **Actions** — workflow `tests` прошёл.
3. Скачать архив из Release, распаковать, запустить `start.cmd` — приложение открывается.
4. Проверить, что в репозитории нет файлов больше 50 МБ (сейчас максимум — `world.js`, 7,5 МБ).

## Чего в репозитории быть не должно

- `.ck3`, `gamestate.json`, `_cache/`, `import/`, `_export/`, `node_modules/` — всё в `.gitignore`;
- личных путей вида `C:\Users\...`, `D:\Games\...`;
- токенов `tokens_1.tok`.

Проверка перед пушем:

```powershell
git ls-files | Select-String '_cache|_export|import/|\.ck3$|gamestate'
Select-String -Path (git ls-files) -Pattern 'C:\\Users\\|D:\\Games|ghp_'
```

Обе команды должны ничего не найти.
