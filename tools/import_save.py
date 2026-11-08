#!/usr/bin/env python3
"""Import a Crusader Kings III save into the app.

The save itself contains no map: CK3 keeps map geometry in the game folder
(map_data/provinces.png, common/landed_titles). So the importer needs two paths:

  1. the save file (.ck3)                    - your campaign
  2. the game folder (.../Crusader Kings III/game) - for the map

It runs the extractor, builds the world and puts it into app/_data/.
Everything can be passed as flags, so the wizard can also run unattended:

  python tools/import_save.py --save "C:/saves/autosave.ck3" \
      --game "C:/Steam/steamapps/common/Crusader Kings III/game" \
      --extractor "C:/tools/ck3_history_extractor.exe" --yes
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
APP_DATA = ROOT / "app" / "_data"
CACHE = ROOT / "_cache"
DEFAULT_WORK = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ck3-chronicle" / "import"


def ask(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip().strip('"')
    return answer or (default or "")


def find_game(explicit: str | None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("CK3_GAME"):
        candidates.append(Path(os.environ["CK3_GAME"]))
    suffixes = [
        "Games/Crusader Kings III/game",
        "SteamLibrary/steamapps/common/Crusader Kings III/game",
        "Steam/steamapps/common/Crusader Kings III/game",
        "Program Files (x86)/Steam/steamapps/common/Crusader Kings III/game",
        "Program Files/Steam/steamapps/common/Crusader Kings III/game",
    ]
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        for suffix in suffixes:
            candidates.append(Path(f"{letter}:/{suffix}"))
    candidates.append(Path.home() / "AppData/Local/Programs/Steam/steamapps/common/Crusader Kings III/game")
    for candidate in candidates:
        if (candidate / "map_data" / "provinces.png").exists():
            return candidate
    return None


def find_extractor(explicit: str | None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("CK3_EXTRACTOR"):
        candidates.append(Path(os.environ["CK3_EXTRACTOR"]))
    candidates.append(ROOT / "ck3_history_extractor.exe")
    candidates.append(ROOT / "vendor" / "ck3_history_extractor.exe")
    for pattern in ("CK3-history-extractor*/**/ck3_history_extractor*.exe", "**/ck3_history_extractor*.exe"):
        candidates.extend(sorted(ROOT.parent.glob(pattern)))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run(command: list[str], title: str, cwd: Path | None = None) -> None:
    print(f"\n== {title} ==")
    print("   " + " ".join(str(part) for part in command))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(command, cwd=cwd or ROOT, env=env)
    if result.returncode != 0:
        raise SystemExit(f"Step failed: {title} (exit {result.returncode})")


REQUIRED = {"ijson": "ijson", "numpy": "numpy", "PIL": "pillow"}


def check_packages() -> list[str]:
    """Какие пакеты не установлены — чтобы не падать с кодом 1 без объяснений."""
    missing = []
    for module, package in REQUIRED.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing



def dir_is_writable(path: Path) -> bool:
    """Проверяем запись делом: Desktop и OneDrive часто закрыты для сторонних программ."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def find_templates(extractor: Path) -> Path | None:
    """Папка templates/ для экстрактора: рядом с exe, выше по дереву или в проекте."""
    probes = [extractor.parent]
    parent = extractor.parent
    for _ in range(3):
        parent = parent.parent
        probes.append(parent)
    probes.append(ROOT)
    for probe in probes:
        if (probe / "templates" / "homeTemplate.html").is_file():
            return probe / "templates"
    return None


def stage_extractor(extractor: Path, work: Path) -> Path:
    """Копия экстрактора в рабочей папке — из Documents он писать не может.

    Экстрактор пишет рядом с собой и падает с «Отказано в доступе» (os error 5),
    если его папка лежит в Documents: Windows не пускает туда посторонние
    программы. Поэтому запускаем копию из рабочей папки, забрав tokens_1.tok
    и templates/ — без них он тоже не работает.
    """
    stage = work / "extractor"
    stage.mkdir(parents=True, exist_ok=True)
    staged_exe = stage / extractor.name
    if not staged_exe.exists() or staged_exe.stat().st_size != extractor.stat().st_size:
        shutil.copy2(extractor, staged_exe)
    tokens = stage / "tokens_1.tok"
    for candidate in (extractor.parent / "tokens_1.tok", ROOT / "vendor" / "tokens_1.tok"):
        if candidate.is_file():
            if not tokens.exists() or tokens.stat().st_size != candidate.stat().st_size:
                shutil.copy2(candidate, tokens)
            break
    if not (stage / "templates").exists():
        templates = find_templates(extractor)
        if templates:
            shutil.copytree(templates, stage / "templates")
    return stage


def pick_work(preferred: Path) -> Path:
    """Рабочая папка: сначала выбранная, потом запасные вне синхронизируемых мест."""
    candidates = [
        preferred,
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ck3-chronicle" / "import",
        ROOT / "import",
        Path(os.environ.get("TEMP", "/tmp")) / "ck3-chronicle" / "import",
    ]
    seen = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.append(candidate)
        if dir_is_writable(candidate):
            return candidate
        print(f"Папка недоступна для записи: {candidate}")
    raise SystemExit(
        "Не нашлось папки, куда можно писать. Укажите --work на обычную папку, "
        "например C:\\ck3-chronicle\\import"
    )


def selftest() -> int:
    """Проверка без игры: запись в папку, поиск шаблонов, копия экстрактора."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Запись проверяется делом.
        assert dir_is_writable(root / "work"), "временная папка должна быть доступна"

        # templates/ ищутся рядом с exe и выше по дереву.
        vendor = root / "vendor" / "extractor"
        vendor.mkdir(parents=True)
        exe = vendor / "ck3_history_extractor.exe"
        exe.write_bytes(b"fake")
        assert find_templates(exe) is None, "шаблонов ещё нет"
        (vendor / "templates").mkdir()
        (vendor / "templates" / "homeTemplate.html").write_text("x", encoding="utf-8")
        assert find_templates(exe) == vendor / "templates", find_templates(exe)

        # Копия экстрактора забирает и шаблоны, и токены.
        (vendor / "tokens_1.tok").write_bytes(b"tok")
        work = root / "work"
        work.mkdir(exist_ok=True)
        stage = stage_extractor(exe, work)
        assert (stage / exe.name).is_file(), "exe не скопирован"
        assert (stage / "templates" / "homeTemplate.html").is_file(), "шаблоны не скопированы"
        assert (stage / "tokens_1.tok").is_file(), "токены не скопированы"
        # Повторный вызов не падает и не дублирует.
        assert stage_extractor(exe, work) == stage

        # Рабочая папка выбирается из доступных.
        chosen = pick_work(work)
        assert chosen.is_dir(), chosen

    print("OK   импорт: запись, шаблоны, копия экстрактора")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a CK3 save into the app.")
    parser.add_argument("--save", help="path to a .ck3 save")
    parser.add_argument("--game", help="CK3 game folder (contains map_data/)")
    parser.add_argument("--extractor", help="path to ck3_history_extractor.exe")
    parser.add_argument("--work", default=str(DEFAULT_WORK), help="working folder for the dump")
    parser.add_argument("--lang", default="russian", help="save language: russian, english, french, …")
    parser.add_argument("--yes", action="store_true", help="do not ask anything, fail instead")
    parser.add_argument("--out", default=str(APP_DATA), help="where to put world.js and the map")
    parser.add_argument("--selftest", action="store_true", help="проверка без игры")
    args = parser.parse_args()
    if args.selftest:
        raise SystemExit(selftest())

    print("Chronicle of the House - import a save")
    print("The map is not inside the save: it is taken from the game folder.\n")

    # 1. Save
    save = Path(args.save).expanduser().resolve() if args.save else None
    if not save or not save.exists():
        if args.yes:
            raise SystemExit("Save file not found. Pass it with --save.")
        save = Path(ask("Path to the .ck3 save", str(save) if save else "")).expanduser()
    if not save.exists():
        raise SystemExit(f"Save not found: {save}")

    # 2. Game folder (map)
    game = find_game(args.game)
    local_map = CACHE / "map_data" / "provinces.png"
    if not game and local_map.exists():
        print("Game folder: not needed, the map is already cached inside the project.")
        game = CACHE
    if not game:
        if args.yes:
            raise SystemExit("Game folder not found. Pass it with --game or set CK3_GAME.")
        game = Path(ask("CK3 game folder (…/Crusader Kings III/game)")).expanduser()
        if not (game / "map_data" / "provinces.png").exists():
            raise SystemExit("That folder has no map_data/provinces.png. Point to the game folder, not the save folder.")

    # 3. Extractor
    extractor = find_extractor(args.extractor)
    if not extractor:
        if args.yes:
            raise SystemExit("Extractor not found. Pass it with --extractor or set CK3_EXTRACTOR.")
        extractor = Path(ask("Path to ck3_history_extractor.exe")).expanduser()
        if not extractor.exists():
            raise SystemExit(f"Extractor not found: {extractor}")

    work = pick_work(Path(args.work).expanduser().resolve())
    dump = work / "gamestate.json"
    if str(work) != str(Path(args.work)):
        print(f"Рабочая папка: {work}")

    # Экстрактор читает ./templates и пишет рядом с собой: и то и другое проходит
    # только когда он запущен из рабочей папки, а не из Documents.
    exe_cwd = stage_extractor(extractor, work)
    extractor = exe_cwd / extractor.name

    print(f"Save:      {save}")
    print(f"Game:      {game}")
    print(f"Extractor: {extractor}")
    print(f"Work:      {work}")

    # 4. Map cache — once per game install.
    if not (CACHE / "map.json").exists() or not (CACHE / "centroids.json").exists():
        run([sys.executable, "tools/knowledge_pilot.py", "map", "--game", str(game)], "Map cache")
        run([sys.executable, "tools/knowledge_pilot.py", "adjacency", "--game", str(game)], "Adjacency cache")
    else:
        print("\n== Map cache: already built ==")

    # 5. Dump the save.
    read_command = [
        str(extractor),
        str(save),
        "-g", str(game),
        "-l", args.lang,
        "-o", str(work),
        "-n", "--no-vis",
        "--dump", str(dump),
    ]
    if dump.exists():
        # Старый дамп с прошлого импорта прошёл бы проверку «файл есть» и хроника
        # собралась бы от чужого сейва. Поэтому — сносим перед запуском.
        dump.unlink()
    try:
        run(read_command, "Reading the save", cwd=exe_cwd)  # шаблоны лежат рядом с экстрактором
    except SystemExit:
        # Ошибка экстрактора (нет шаблонов, отказ в записи, битый сейв) — пробуем запасную папку.
        print("\nЭкстрактор завершился с ошибкой. Пробую другую рабочую папку.")
        work = pick_work(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ck3-chronicle" / "import")
        dump = work / "gamestate.json"
        if dump.exists():
            dump.unlink()
        read_command[read_command.index("-o") + 1] = str(work)
        read_command[read_command.index("--dump") + 1] = str(dump)
        try:
            run(read_command, "Reading the save (repeat)", cwd=exe_cwd)
        except SystemExit:
            pass
    if not dump.exists() or dump.stat().st_size < 1_000_000:
        # Последняя попытка: дамп рядом с экстрактором. Туда запись проходит даже
        # когда защита Windows не пускает стороннюю программу в выбранную папку.
        beside = extractor.parent / "gamestate.json"
        if beside.exists():
            beside.unlink()
        read_command[read_command.index("-o") + 1] = str(extractor.parent)
        read_command[read_command.index("--dump") + 1] = str(beside)
        try:
            run(read_command, "Reading the save (beside the extractor)", cwd=exe_cwd)
            if beside.exists():
                shutil.move(str(beside), str(dump))
        except SystemExit:
            pass
    if not dump.exists() or dump.stat().st_size < 1_000_000:
        raise SystemExit(
            f"Дамп не создан или слишком мал: {dump}. "
            "Проверьте, что экстрактор отработал без ошибок (журнал выше)."
        )
    print(f"Dump size: {dump.stat().st_size / 1048576:.1f} MB")

    # 6. Дополнение из сейва: войны с поводами и история титулов. Экстрактор их не отдаёт,
    #    а игра хранит в текстовом gamestate. Без этого в хронике нет причин войн.
    extra = work / "save-extra.json"
    try:
        run([sys.executable, "tools/save_reader.py", "--save", str(save), "--out", str(extra)], "Save additions")
        if not extra.exists():
            extra = None
    except SystemExit:
        print("Сейв-дополнение не собралось — собираю мир без войн и без новой истории титулов.")
        extra = None

    # Имена поводов — из локализации игры: ключ повода совпадает с ключом локализации.
    if game and (game / "localization").exists():
        try:
            run(
                [sys.executable, "tools/cb_names.py", "--game", str(game), "--out", str(CACHE / "cb-names.json")],
                "Casus belli names",
            )
        except SystemExit:
            print("Имена поводов не собрались — останутся свои названия из build_world.py.")

    # 7. Build the world and its map.
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    build_args = [
        sys.executable, "tools/build_world.py",
        "--dump", str(dump),
        "-o", str(out_dir / "world.js"),
        "--map", str(out_dir / "world-map.png"),
        "--game", str(game),
    ]
    if extra:
        build_args += ["--extra", str(extra)]
    # Разовые сбои чтения диска случаются: один повтор снимает большую часть.
    try:
        run(build_args, "Building the world")
    except SystemExit:
        print("\nСборка мира не удалась — повторяю один раз.")
        run(build_args, "Building the world (repeat)")

    meta = load_world(out_dir / "world.js")["meta"]
    print("\nDone.")
    print(f"  Date:    {meta.get('date')}")
    print(f"  Player:  {meta.get('player', {}).get('name')} ({meta.get('player', {}).get('house')})")
    print(f"  Realms:  {meta['counts'].get('realms')}")
    print(f"  People:  {meta['counts'].get('dynasty')} in the dynasty")
    print("\nStart the app with start.cmd (Windows) or ./start.sh (macOS, Linux).")


if __name__ == "__main__":
    main()
