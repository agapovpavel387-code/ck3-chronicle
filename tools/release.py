#!/usr/bin/env python3
"""Сборка релиза: один вход, проверенный результат.

    python tools/release.py              # тесты, факты, документы, архив, проверка архива
    python tools/release.py --skip-tests # без прогона npm test (быстро, для черновика)

Что делает по порядку:

1. `stamp.py --check`   — версия во всех файлах одна;
2. `npm test`           — все наборы проверок (журнал кладётся в `_cache/test.log`);
3. `facts.py --write`   — числа мира и счёт проверок пересчитаны в `docs/facts.md`;
4. `check_docs.py`      — ссылки живы, версий и чисел руками нет;
5. архив               — только по белому списку, без `__pycache__`, `save-extra.json`, `vendor/`;
6. манифест            — размер, sha256 и список файлов рядом с архивом;
7. самопроверка        — архив распакован во временную папку: `index.html` на месте,
   `world.js` разбирается, запрещённых строк нет.

Архив, который не прошёл шаг 7, не считается собранным.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

TOP_FILES = [
    "README.md",
    "README.en.md",
    "CHANGELOG.md",
    "RELEASE_NOTES.md",
    "CONTRIBUTING.md",
    "PUBLISHING.md",
    "LICENSE",
    "NOTICE",
    "VERSION",
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "start.cmd",
    "start.sh",
    "import.cmd",
    "import.sh",
    "make.cmd",
]

# `patches/` кладём в архив: на неё ссылаются README, CHANGELOG и docs.
DIRS = ["app", "docs", "tools", "patches"]

# Кэш карты нужен, чтобы мир собирался без папки игры. `save-extra.json` — нет:
# это выгрузка из сейва пользователя, в публичный архив она не идёт.
CACHE_FILES = ["map.json", "centroids.json", "adjacency.json", "cb-names.json"]

SKIP_PARTS = {"__pycache__", "node_modules", ".git", "dist", "_export", "vendor"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {"save-extra.json", ".DS_Store", "Thumbs.db"}

# Ищем именно значения с этой машины и настоящие секреты, а не упоминания:
# документация вправе говорить «положите tokens_1.tok рядом с экстрактором».
# Личный каталог не вписываем в код: он у каждого свой.
_HOME = str(Path.home())
FORBIDDEN_TEXT = [
    re.escape(_HOME),
    r"D:\\Games\\Crusader Kings III",
    r"ghp_[A-Za-z0-9]{20,}",
]
FORBIDDEN_SUFFIXES = {".ck3", ".tok", ".exe"}
# Сам проверяльщик содержит эти шаблоны как строки — его не сканируем.
SKIP_SCAN = {"tools/release.py"}


def say(message: str) -> None:
    print(message, flush=True)


def run(cmd: list[str], log: Path | None = None) -> None:
    say("→ " + " ".join(cmd))
    process = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    output = (process.stdout or "") + (process.stderr or "")
    if log:
        log.write_text(output, encoding="utf-8")
    if process.returncode != 0:
        say(output.strip()[-4000:])
        raise SystemExit(f"команда завершилась с кодом {process.returncode}: {' '.join(cmd)}")
    tail = [line for line in output.strip().splitlines() if line.strip()][-3:]
    for line in tail:
        say("  " + line.strip())


def python(*args: str) -> list[str]:
    return [sys.executable, "-X", "utf8", *args]


def npm() -> str:
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("npm не найден — без него не прогнать проверки")


def collected_files() -> list[Path]:
    files: list[Path] = []
    for name in TOP_FILES:
        path = ROOT / name
        if path.exists():
            files.append(path)
    for folder in DIRS:
        base = ROOT / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                files.append(path)
    cache = ROOT / "_cache"
    for name in CACHE_FILES:
        path = cache / name
        if path.exists():
            files.append(path)
    keep = []
    for path in files:
        parts = set(path.relative_to(ROOT).parts)
        if parts & SKIP_PARTS or path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
            continue
        keep.append(path)
    return sorted(keep, key=lambda p: p.relative_to(ROOT).as_posix())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_zip(files: list[Path], archive: Path, prefix: str) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            bundle.write(path, f"{prefix}/{rel}")


def verify_zip(archive: Path, expected: list[Path], prefix: str) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        names = [info.filename for info in bundle.infolist()]
        wanted = [f"{prefix}/{p.relative_to(ROOT).as_posix()}" for p in expected]
        if names != wanted:
            missing = sorted(set(wanted) - set(names))
            extra = sorted(set(names) - set(wanted))
            problems.append(f"состав архива не совпал: нет {missing[:3]}, лишнее {extra[:3]}")

        with tempfile.TemporaryDirectory() as tmp:
            bundle.extractall(tmp)
            root = Path(tmp) / prefix
            for required in ("app/index.html", "VERSION", "docs/facts.md", "tools/facts.py"):
                if not (root / required).exists():
                    problems.append(f"в архиве нет {required}")
            world = root / "app" / "_data" / "world.js"
            if world.exists():
                text = world.read_text(encoding="utf-8")
                try:
                    json.loads(text[text.index("{"): text.rindex("}") + 1])
                except ValueError as error:
                    problems.append(f"world.js в архиве не разбирается: {error}")
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix in FORBIDDEN_SUFFIXES:
                    problems.append(f"в архиве сейв: {path.relative_to(root).as_posix()}")
                if path.suffix in {".md", ".json", ".js", ".py", ".txt", ".cmd", ".sh"}:
                    rel = path.relative_to(root).as_posix()
                    if rel in SKIP_SCAN:
                        continue
                    body = path.read_text(encoding="utf-8", errors="ignore")
                    for pattern in FORBIDDEN_TEXT:
                        if re.search(pattern, body):
                            problems.append(f"в архиве личная строка {pattern!r}: {rel}")
                            break
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка проверенного релиза")
    parser.add_argument("--skip-tests", action="store_true", help="не прогонять npm test")
    parser.add_argument("--out", default="dist", help="папка для архива (по умолчанию dist)")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    out = ROOT / args.out
    out.mkdir(exist_ok=True)
    log = ROOT / "_cache" / "test.log"
    log.parent.mkdir(exist_ok=True)

    say(f"версия: {version}")
    run(python("tools/stamp.py", "--check"))

    if args.skip_tests:
        say("→ npm test пропущен (--skip-tests), счёт берётся из прошлого журнала")
    else:
        run([npm(), "test"], log=log)

    run(python("tools/facts.py", "--write", "--test-log", str(log)))
    run(python("tools/check_docs.py"))

    files = collected_files()
    prefix = f"chronicle-of-the-house-{version}"
    archive = out / f"{prefix}.zip"
    build_zip(files, archive, prefix)
    say(f"архив: {archive.relative_to(ROOT).as_posix()} — файлов {len(files)}, "
        f"{archive.stat().st_size / 1048576:.1f} МБ")

    problems = verify_zip(archive, files, prefix)

    commit = ""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8").stdout.strip()
    except OSError:
        pass

    manifest = {
        "version": version,
        "commit": commit,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archive": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": sha256_file(archive),
        "files": [
            {"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
            for p in files
        ],
        "excluded": ["_cache/save-extra.json", "_cache/titles.json",
                     "app/start.bat", "node_modules/", "vendor/", "dist/", "__pycache__/"],
    }
    manifest_path = out / f"{prefix}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="")

    if problems:
        for line in problems:
            say("ОШИБКА: " + line)
        say("архив не прошёл самопроверку — выпускать нельзя")
        return 1

    say(f"манифест: {manifest_path.relative_to(ROOT).as_posix()}")
    say(f"sha256: {manifest['sha256']}")
    say(f"проверка архива пройдена: файлов {len(files)}, личных строк и сейвов нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
