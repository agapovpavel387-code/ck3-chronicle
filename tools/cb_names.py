#!/usr/bin/env python3
"""Имена поводов войны из локализации игры — вместо ручного словаря.

    python tools/cb_names.py --game "D:\\Games\\Crusader Kings III\\game" --out _cache/cb-names.json
    python tools/cb_names.py --game "...\\game" --keys-from _cache/save-extra.json --check

Зачем: в игре у каждого повода есть своё имя — ключ повода совпадает с ключом
локализации (`county_conquest_cb: "Завоевание графства"`). Своя словарная догадка
расходится с игрой (например, `claim_cb` — «Претензия», а не «притязание на титул»).

Имена в локализации бывают с разметкой и переменными:
    minor_religious_war: "Малая [Concept( 'holy_war_holy', 'священная война' )|E]"
    chinese_consolidation_cb: "$CHINESE_CONSOLIDATION_WAR_NAME$"
Их надо раскрыть и вычистить, иначе строка хроники покажет `[Concept(…`.

Список поводов берётся не из головы: ключи верхнего уровня из
`common/casus_belli_types/*.txt` плюс всё, что встретилось в сейве.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LANGS = ("russian", "english")

CB_DEF_RE = re.compile(r"^([a-z][a-z0-9_]*)\s*=\s*\{", re.MULTILINE)
LOC_LINE_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s*"(.*)"\s*$')
VAR_RE = re.compile(r"\$([A-Za-z0-9_]+)\$")

CONCEPT_TEXT_RE = re.compile(r"\[Concept\(\s*'[^']*'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)\s*\|[Ee]l?\]")
CONCEPT_BARE_RE = re.compile(r"\[Concept\(\s*'[^']*'\s*\)\s*\|[Ee]l?\]")
# `[holy_war_holy|E]` — ссылка на другую строку локализации, а не на текст.
REF_RE = re.compile(r"\[([A-Za-z0-9_]+)\|[Ee]l?\]")
GENERIC_REF_RE = re.compile(r"\[[A-Za-z0-9_]+\|[Ee]l?\]")
# `#TOOLTIP:BUILDING,x #L текст#!` — подсказка; видимый текст идёт после #L.
TOOLTIP_RE = re.compile(r"#TOOLTIP:[^#]*#L?")
CODE_RE = re.compile(r"#[A-Za-z]+")
BANG_RE = re.compile(r"#!")
BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
COLOR_RE = re.compile(r"#[A-Za-z]+\s*(.*?)#!?", re.DOTALL)


PURE_REF_RE = re.compile(r"^\s*\[[A-Za-z0-9_]+\|[Ee]l?\]\s*$")


def clean(text: str, raw: dict[str, str] | None = None, depth: int = 0) -> str:
    """Разметка игры → обычный текст."""
    text = CONCEPT_TEXT_RE.sub(r"\1", text)
    text = CONCEPT_BARE_RE.sub("", text)
    if raw is not None and depth <= 3:
        text = REF_RE.sub(
            lambda match: clean(resolve(raw, match.group(1), depth + 1), raw, depth + 1)
            if match.group(1) in raw
            else "",
            text,
        )
    text = GENERIC_REF_RE.sub("", text)
    text = TOOLTIP_RE.sub("", text)
    text = BANG_RE.sub("", text)
    text = CODE_RE.sub("", text)
    text = BRACKET_RE.sub("", text)
    text = text.replace("\\n", " ").replace("\\t", " ")
    text = text.replace('\\"', '"')
    return re.sub(r"\s+", " ", text).strip(" .,")


def read_loc(folder: Path, wanted: set[str]) -> dict[str, str]:
    """Один проход по *.yml: только нужные ключи (файлов тысячи, значения короткие)."""
    found: dict[str, str] = {}
    if not folder.exists():
        return found
    for path in folder.rglob("*.yml"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if "$" not in line and ":" not in line:
                continue
            match = LOC_LINE_RE.match(line)
            if not match:
                continue
            key = match.group(1)
            if key in wanted and key not in found:
                found[key] = match.group(2)
    return found


def cbs_from_defs(folder: Path) -> set[str]:
    keys: set[str] = set()
    if not folder.exists():
        return keys
    for path in folder.glob("*.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        keys.update(CB_DEF_RE.findall(text))
    return keys


def resolve(raw: dict[str, str], key: str, depth: int = 0) -> str:
    """$VAR$ внутри имени раскрываем по той же локализации."""
    value = raw.get(key, "")
    if depth > 3:
        return value

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name in raw:
            return resolve(raw, name, depth + 1)
        return ""

    return VAR_RE.sub(replace, value)


OVERRIDES = {
    # Где игра отдаёт обрубок («Minor», «Священная») — берём человеческое имя.
    "minor_religious_war": {"english": "Minor Holy War"},
    "major_religious_war": {"english": "Great Holy War"},
    "religious_war": {"russian": "Священная война", "english": "Holy War"},
    "county_struggle_cb": {"russian": "Спор за графство", "english": "Struggle for the County"},
    "fp2_expel_interloper": {"russian": "Изгнание чужака", "english": "Expel the Interloper"},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", type=Path, required=True, help="папка game игры")
    parser.add_argument("--out", type=Path, default=None, help="куда сложить справочник")
    parser.add_argument("--keys-from", type=Path, default=None, help="save-extra.json: добавить поводы из сейва")
    parser.add_argument("--check", action="store_true", help="показать покрытие и примеры")
    args = parser.parse_args()

    keys = cbs_from_defs(args.game / "common" / "casus_belli_types")
    if args.keys_from and args.keys_from.exists():
        data = json.loads(args.keys_from.read_text(encoding="utf-8"))
        keys.update(war.get("cb") for war in (data.get("wars") or []) if war.get("cb"))

    # значения ссылаются на переменные — их тоже надо вытянуть
    wanted = set(keys)
    raw: dict[str, dict[str, str]] = {lang: {} for lang in LANGS}
    for _ in range(3):
        extra: set[str] = set()
        for lang in LANGS:
            found = read_loc(args.game / "localization" / lang, wanted - set(raw[lang]))
            raw[lang].update(found)
            for value in found.values():
                extra.update(VAR_RE.findall(value))
                extra.update(REF_RE.findall(value))
        if extra <= wanted:
            break
        wanted |= extra

    names: dict[str, dict[str, str]] = {}
    for key in sorted(keys):
        entry = {}
        for lang in LANGS:
            resolved = resolve(raw[lang], key)
            # `[holy_war_holy|E]` — это прилагательное из концепта («Священная»),
            # а не имя повода. Такое имя не берём: лучше свой словарь, чем обрубок.
            if PURE_REF_RE.match(resolved):
                continue
            value = clean(resolved, raw[lang])
            if value:
                entry[lang] = value
        if entry:
            names[key] = entry

    for key, langs in OVERRIDES.items():
        names.setdefault(key, {}).update(langs)

    covered = len(names)
    print(f"поводов в игре: {len(keys)}; с именем: {covered}; без имени: {len(keys) - covered}")
    if args.check:
        missing = sorted(set(keys) - set(names))
        if missing:
            print("без имени:", ", ".join(missing))
        for key in sorted(names)[:40]:
            print(f"  {key:42s} {names[key].get('russian', '—')}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nзаписано: {args.out} ({args.out.stat().st_size / 1024:.0f} КБ)")


if __name__ == "__main__":
    main()
