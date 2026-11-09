# Хроника рода 0.6.6-alpha — заметки к выпуску

**Что это.** Локальное приложение, которое читает сохранение Crusader Kings III и показывает мир глазами одной семьи: что до рода дошло — своим знанием, вестями и молвой. Ничего не отправляется в сеть, аккаунт не нужен.

**Совместимость.** Crusader Kings III 1.20.x, формат сейва 1.20. Проверено на сохранении 917 года с русской локализацией. Более ранние форматы (1.19 и ниже) разбираются экстрактором, но приложение проверено на 1.20.

## Как запустить

1. Распакуйте архив.
2. **Windows:** `start.cmd`. **macOS/Linux:** `./start.sh`.
3. Откроется `http://127.0.0.1:8778/`.

Нужен Node.js (рекомендуется, без зависимостей) или Python 3. Для импорта своих сохранений нужны пакеты `ijson`, `numpy`, `pillow` — страница импорта проверит их и предложит установить.

## Экстрактор

Импорт своего сохранения идёт через сторонний CK3-history-extractor с патчем под 1.20 — он лежит в [Releases](https://github.com/agapovpavel387-code/ck3-chronicle/releases): `ck3_history_extractor-2.4.7-ck3-1.20-win64.zip` (8,8 МБ, exe + `templates/` + лицензия TCA).

1. Скачайте архив и распакуйте в `vendor/` рядом с приложением.
2. Больше ничего настраивать не нужно: приложение ищет `ck3_history_extractor.exe` там само.

Бинарным сейвам (автосейвы, ironman) дополнительно нужны токены — их снимает `tools/tokens.ps1`.
Контрольная сумма exe: `e9d60eef57c1d8e659041460080d5d32d9b730c9ae6c74ee89afe82dbe307e6e`.

## Что внутри альфы

- шесть экранов: Род, Мир, Хроника, Свод, Досье и «Своё сохранение»;
- род конспектом по слоям и полотном с панорамой;
- две линзы карты, у политической два слоя: по домам и земли рода;
- хроника главами, тремя слоями и нитями войн и распрь;
- **титулы:** у смены власти есть причина (по наследству, пожалован, отобран, завоёван…), у потери — имя титула и новый держатель;
- **войны:** повод из локализации игры и цель войны, исход по истории титула;
- **смерти:** причина из данных игры без разметки («во сне», «от старости», «от чахотки»);
- импорт своего сохранения из панели, с журналом и отменой;
- интерфейс на русском и английском: переключатель RU/EN, выбор запоминается;
- **проверенная сборка:** версия, числа и документы сверяются одной командой, архив собирается `make.cmd` с манифестом и самопроверкой.

## Чего в альфе нет

- **Веры.** Сейв 1.20 хранит определения вер, но не привязку к людям и графствам. Приложение пишет об этом прямо, а не угадывает.
- **Мотивов у части событий.** Причина смены титула известна там, где её записала память персонажа; у смен до начала партии её нет.
- **Завершённых войн.** Игра хранит только идущие; причина у давно закончившихся есть только там, где осталась память.
- **Имён за третьим кольцом.** Там известна только держава: это кольцо молвы, а не пробел летописца.
- **Полной генеалогии.** Записи о рождениях есть там, где о них дошла весть; в дереве детей может быть больше.

## Что сообщать

Если что-то падает — пришлите строки из журнала импорта (они видны на странице «Своё сохранение») и `python tools/doctor.py --dump out/gamestate.json`. По ним видно, на каком шаге и почему.

---

# Chronicle of the House 0.6.6-alpha — release notes

**What it is.** A local app that reads a Crusader Kings III save and shows the world through one family's eyes: what actually reached the house — its own records, messages, and hearsay. Nothing is sent over the network, no account needed.

**Compatibility.** Crusader Kings III 1.20.x, save format 1.20. Tested on a 917 save with the Russian localization. Older formats (1.19 and below) are handled by the extractor, but the app is verified on 1.20.

## How to start

1. Unpack the archive.
2. **Windows:** `start.cmd`. **macOS/Linux:** `./start.sh`.
3. The browser opens `http://127.0.0.1:8778/`.

Either Node.js (recommended, no dependencies) or Python 3 is enough. Importing your own saves needs `ijson`, `numpy`, `pillow` — the import page checks them and offers a one-click install.

## What is in this alpha

- six screens: House, World, Chronicle, Compendium, Dossier, and "Your save";
- the house as a layered outline and as a pannable canvas;
- two map lenses, the political one with two layers: by house and family lands;
- a chronicle in chapters, three layers per year, with threads for wars and feuds;
- **titles:** every change of power names its cause (inherited, granted, revoked, conquered…), every loss names the title and the new holder;
- **wars:** the casus belli from the game's own localization and the war goal;
- **deaths:** the cause as the game recorded it;
- importing your own save from the page, with a live log and a stop button;
- the interface in Russian and English, with a RU/EN switch that remembers the choice;
- **a verified build:** version, numbers and documents are checked by one command; the archive is built by `make.cmd` with a manifest and a self-check.

## What is not here

- **Faith.** The 1.20 save keeps faith definitions but no link to people or counties. The app says so instead of guessing.
- **Motives for every event.** A title change has a cause where a character's memory recorded it; changes before the campaign have none.
- **Finished wars.** The game stores only ongoing ones; a cause for long-finished wars exists only where a memory survived.
- **Names beyond the third ring.** Only the realm is known there: that is the ring of hearsay, not a gap in the chronicler's work.
- **Complete genealogy.** Births are recorded where a message arrived; the tree may hold more children.

## What to report

If something fails, send the lines from the import log (visible on the "Your save" page) and `python tools/doctor.py --dump out/gamestate.json`. They show the step and the reason.
