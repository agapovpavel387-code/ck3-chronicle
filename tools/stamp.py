#!/usr/bin/env python3
"""Версия проекта живёт в одном файле — `VERSION`.

    python tools/stamp.py --check     # 0, если везде одно и то же; 1, если разошлось
    python tools/stamp.py --write     # проставить версию по списку правил

Правила ниже — единственный список мест, где версия вписана в текст руками.
Появилось новое место — добавьте правило сюда, а не число в файл.

`CHANGELOG.md` не правится никогда: раздел под текущую версию пишет человек,
и обновление версии не должно оставлять в истории пустую заготовку.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+-[a-z]+$")

# (файл, [(регулярка, замена с {ver} / {short})])
# `{ver}` — как в VERSION (0.6.4-alpha), `{short}` — без суффикса (0.6.4).
RULES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "package.json",
        [(r'("version":\s*")[^"]+(")', r"\g<1>{ver}\g<2>")],
    ),
    (
        "app/index.html",
        [
            (r'(<meta name="app-version" content=")[^"]+(")', r"\g<1>{ver}\g<2>"),
            (r"(v)[0-9][^ ·]*( · Crusader Kings III)", r"\g<1>{ver}\g<2>"),
        ],
    ),
    (
        "README.md",
        [(r"(\*\*Альфа )([0-9][^*]*)(\*\*)", r"\g<1>{short}\g<3>")],
    ),
    (
        "README.en.md",
        [(r"(\*\*Alpha )([0-9][^*]*)(\*\*)", r"\g<1>{short}\g<3>")],
    ),
    (
        "RELEASE_NOTES.md",
        [
            (r"(# Хроника рода )([0-9][^\s]*)( — заметки)", r"\g<1>{ver}\g<3>"),
            (r"(# Chronicle of the House )([0-9][^\s]*)( — release notes)", r"\g<1>{ver}\g<3>"),
        ],
    ),
]


def read_version() -> str:
    if not VERSION_FILE.exists():
        raise SystemExit("нет файла VERSION — версию брать неоткуда")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not VERSION_RE.match(version):
        raise SystemExit(f"VERSION: «{version}» не похоже на 0.6.4-alpha")
    return version


def apply_rules(text: str, version: str, rules: list[tuple[str, str]]) -> str:
    short = version.split("-")[0]
    for pattern, template in rules:
        text = re.sub(pattern, template.format(ver=version, short=short), text)
    return text


def check_changelog(version: str) -> list[str]:
    file = ROOT / "CHANGELOG.md"
    if not file.exists():
        return ["нет CHANGELOG.md"]
    text = file.read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+?)\s*$", text, re.M)
    if not headings:
        return ["в CHANGELOG.md нет ни одного раздела «## версия»"]
    if headings[0] != version:
        return [
            f"CHANGELOG.md: первый раздел «{headings[0]}», а в VERSION «{version}» — "
            "допишите раздел под текущую версию"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Версия в одном месте: VERSION")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="только проверить (по умолчанию)")
    group.add_argument("--write", action="store_true", help="проставить версию в файлы")
    args = parser.parse_args()

    version = read_version()
    problems: list[str] = []

    for rel, rules in RULES:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: файла нет")
            continue
        # `newline` в read_text появился только в Python 3.13, а CI на 3.12.
        with path.open(encoding="utf-8", newline="") as handle:
            original = handle.read()
        updated = apply_rules(original, version, rules)
        if updated == original:
            continue
        if not args.write:
            # Показываем, что именно разошлось: старые значения в этом файле.
            old = sorted({m.group(0) for pattern, _ in rules
                          for m in re.finditer(pattern, original)})
            problems.append(f"{rel}: версия не «{version}» — найдено {', '.join(old[:3])}")
            continue
        path.write_text(updated, encoding="utf-8", newline="")
        print(f"обновлено: {rel}")

    problems.extend(check_changelog(version))

    if problems:
        for line in problems:
            print("РАСХОЖДЕНИЕ: " + line)
        if not args.write:
            print("\nисправить: python tools/stamp.py --write")
        return 1

    print(f"версия {version}: все {len(RULES)} файлов согласованы, CHANGELOG открывает её же")
    return 0


if __name__ == "__main__":
    sys.exit(main())
