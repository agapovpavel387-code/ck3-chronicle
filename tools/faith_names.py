#!/usr/bin/env python3
"""Названия обрядов и вер из файлов игры.

Зачем. Дамп экстрактора не содержит веры: у людей и графств там `faith: null`.
Но в сейве 1.20 у каждого человека и графства есть `rite=<номер>`, а реестр
`rites` связывает номер с ключом обряда (`roman_rite`) и номером веры. Значит
веру можно прочитать, не трогая сторонний экстрактор:

    человек/графство → rite → обряд (ключ) → название из локализации
                                   ↓
                          common\\religion\\rite_types: faith = christian_faith

Здесь собирается справочник: ключ обряда → названия (RU/EN) и вера.

    python tools/faith_names.py --game "…\\Crusader Kings III\\game" --out _cache/rites.json
    python tools/faith_names.py --check

`--check` сверяет справочник с файлами игры и печатает покрытие.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# После «{» бывает комментарий: «ambrosian_rite = { # The rite of …».
RITE_RE = re.compile(r"^([a-z][a-z0-9_]*)\s*=\s*\{(?:\s*#.*)?$")
FAITH_RE = re.compile(r"^\s*faith\s*=\s*([a-z][a-z0-9_]*)\s*$")
LOC_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s*"(.*)"\s*$')

LANGS = ("russian", "english")
# Формы названия: прилагательное читается как имя веры («Римское христианство»),
# базовое имя часто обрубок («Римск»). Берём прилагательное, базовое — запасным.
FORMS = ("_adj", "", "_adherent")


def parse_rite_types(game: Path) -> dict[str, str]:
    """Обряд → вера (ключом): из common\\religion\\rite_types\\*.txt."""
    out: dict[str, str] = {}
    folder = game / "common" / "religion" / "rite_types"
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.txt")):
        rite = None
        depth = 0
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if rite is None:
                m = RITE_RE.match(line)
                if m:
                    rite = m.group(1)
                    depth = 1
                continue
            depth += line.count("{") - line.count("}")
            f = FAITH_RE.match(line)
            if f and rite not in out:
                out[rite] = f.group(1)
            if depth <= 0:
                rite = None
    return out


def parse_loc(game: Path, lang: str) -> dict[str, str]:
    """Ключ → строка локализации для одного языка."""
    out: dict[str, str] = {}
    folder = game / "localization" / lang
    if not folder.is_dir():
        return out
    for path in folder.rglob("*.yml"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = LOC_RE.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            if key.startswith("PROV") or not value:
                continue
            out.setdefault(key, value)
    return out


def clean_name(text: str) -> str:
    """Убрать разметку локализации: #bold … #!, кавычки-ёлочки оставить."""
    text = re.sub(r"#[A-Za-z]+\s*", "", text)
    text = text.replace("#!", "")
    return text.strip().strip('"')


def build(game: Path) -> dict:
    rites = parse_rite_types(game)
    locs = {lang: parse_loc(game, lang) for lang in LANGS}
    out: dict[str, dict] = {}
    for rite, faith in sorted(rites.items()):
        row = {"faith": faith, "names": {}}
        for lang, table in locs.items():
            for form in FORMS:
                key = rite + form
                if key in table:
                    row["names"][lang] = clean_name(table[key])
                    break
        out[rite] = row
    return out


def check(game: Path, path: Path) -> int:
    fresh = build(game)
    if not path.exists():
        print(f"нет справочника: {path} — соберите --out")
        return 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in fresh if k not in saved]
    extra = [k for k in saved if k not in fresh]
    no_name = [k for k, v in fresh.items() if not v["names"].get("russian")]
    print(f"обрядов в игре: {len(fresh)}")
    print(f"в справочнике: {len(saved)}")
    print(f"нет названия по-русски: {len(no_name)}")
    if no_name[:5]:
        print("   например:", ", ".join(no_name[:5]))
    ok = not missing and not extra and not no_name
    if missing:
        print(f"не хватает в справочнике: {len(missing)} — {', '.join(missing[:5])}")
    if extra:
        print(f"лишние в справочнике: {len(extra)} — {', '.join(extra[:5])}")
    print("OK   справочник сходится с игрой" if ok else "ПЛОХО справочник расходится с игрой")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Названия обрядов и вер из файлов игры")
    parser.add_argument("--game", type=Path, default=None, help="папка game игры")
    parser.add_argument("--out", type=Path, default=None, help="куда писать справочник")
    parser.add_argument("--check", action="store_true", help="сверить справочник с игрой")
    args = parser.parse_args()

    import os

    game = args.game or (Path(os.environ["CK3_GAME"]) if os.environ.get("CK3_GAME") else None)
    if not game:
        parser.error("нужна папка игры: --game или переменная CK3_GAME")
    if not (game / "common" / "religion" / "rite_types").is_dir():
        parser.error(f"в {game} нет common\\religion\\rite_types")

    out = args.out or Path("_cache/rites.json")
    if args.check:
        return check(game, out)

    data = build(game)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    named = sum(1 for v in data.values() if v["names"].get("russian"))
    print(f"обрядов: {len(data)}, с русским названием: {named} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
