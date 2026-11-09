#!/usr/bin/env python3
"""Документы против факта: ссылки, версия, числа.

    python tools/check_docs.py          # 0 — всё сходится, 1 — есть расхождения

Три проверки:

1. **Ссылки.** Каждая относительная ссылка в `.md` ведёт на существующий файл.
2. **Версия.** В `README.md` и `README.en.md` в шапке стоит версия из `VERSION`
   (это же делает `stamp.py`, здесь — вторая линия).
3. **Числа.** Крупные числа мира и «N проверок» живут только в `docs/facts.md`.
   В остальных документах их быть не должно: они меняются при каждой пересборке
   и потому обязаны быть ссылкой, а не текстом.

`CHANGELOG.md` исключён: это история, её числа — свидетели прошлых версий.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FACTS = DOCS / "facts.json"

ALLOWED_NUMBERS = {"docs/facts.md", "CHANGELOG.md"}
SKIP_LINKS = ("http://", "https://", "mailto:", "#", "tel:")

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Числа пишутся и слитно (22651), и с пробелом (22 651). Перед сравнением
# приводим строку к слитному виду, иначе «270» найдётся внутри «13 270».
GROUP_SPACE = re.compile(r"(?<=\d) (?=\d{3}(?!\d))")
COUNT_WORDS = [
    (re.compile(r"\b\d+\s+проверок\b"), "число проверок"),
    (re.compile(r"\b\d+\s+checks\b", re.I), "number of checks"),
    (re.compile(r"«итог:\s*\d+/\d+»"), "итог проверок"),
]


def documents() -> list[Path]:
    files = sorted(ROOT.glob("*.md")) + sorted(DOCS.rglob("*.md"))
    return [p for p in files if "node_modules" not in p.parts]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def number_variants(value: int) -> set[str]:
    """Слитная форма: сравнение идёт по строке без разделителей разрядов."""
    return {str(value)}


def token_re(token: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\d){re.escape(token)}(?!\d)")


def world_numbers() -> set[str]:
    """Числа из фактов, которые нельзя писать в текстах руками.

    Меньше ста не берём: «89» и «43» слишком часто встречаются как обычные слова
    (годы, проценты, номера строк) — на них проверка давала бы шум.
    """
    if not FACTS.exists():
        return set()
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    out: set[str] = set()
    for section in ("world", "titles"):
        for key, value in (facts.get(section) or {}).items():
            # Год и дату мира оставляем в прозе: «на сейве 917 года» — это часть
            # названия партии, а не пересчитываемая цифра.
            if key in ("year", "date", "build"):
                continue
            if isinstance(value, int) and not isinstance(value, bool) and value >= 100:
                out |= number_variants(value)
    return out


def check_links(path: Path) -> list[str]:
    problems = []
    text = path.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith(SKIP_LINKS):
            continue
        clean = target.split("#")[0]
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            line = text[: match.start()].count("\n") + 1
            problems.append(f"{rel(path)}:{line}: ссылка ведёт в никуда — {target}")
    return problems


def check_version_headers(path: Path, version: str) -> list[str]:
    short = version.split("-")[0]
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"\*\*(?:Альфа|Alpha) ([0-9][^*]*)\*\*", text):
        if match.group(1).strip() != short:
            line = text[: match.start()].count("\n") + 1
            return [f"{rel(path)}:{line}: в шапке «{match.group(1)}», а в VERSION «{short}»"]
    return []


def check_numbers(path: Path, numbers: set[str]) -> list[str]:
    problems = []
    text = path.read_text(encoding="utf-8")
    patterns = [(token_re(token), token) for token in numbers]
    for line_no, line in enumerate(text.splitlines(), 1):
        flat = GROUP_SPACE.sub("", line)
        for pattern, what in COUNT_WORDS:
            if pattern.search(flat):
                problems.append(f"{rel(path)}:{line_no}: {what} в тексте — это живёт в docs/facts.md")
        for pattern, token in patterns:
            if pattern.search(flat):
                problems.append(
                    f"{rel(path)}:{line_no}: число «{token}» вписано руками — "
                    "ссылайтесь на docs/facts.md"
                )
                break
    return problems


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    numbers = world_numbers()
    problems: list[str] = []
    files = documents()

    for path in files:
        problems += check_links(path)
        if rel(path) in ("README.md", "README.en.md"):
            problems += check_version_headers(path, version)
        if rel(path) not in ALLOWED_NUMBERS:
            problems += check_numbers(path, numbers)

    if problems:
        for line in problems:
            print("РАСХОЖДЕНИЕ: " + line)
        print(f"\nпроверено документов: {len(files)}, расхождений: {len(problems)}")
        return 1

    print(f"документы сходятся: {len(files)} файлов, ссылки живы, чисел руками нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
