#!/usr/bin/env python3
"""Названия форм правления из файлов игры.

Сейв хранит у правителя `government=celestial_government`, но название игры
лежит не в `government_l_russian.yml`, а в понятиях: `game_concept_celestial_government`
= «Мандатное правление». Поэтому ищем имя по трём ключам подряд:

    мандатное правление ← game_concept_celestial_government
                        ← celestial_government
                        ← ключ как есть

    python tools/government_names.py --game "…\\Crusader Kings III\\game" --out _cache/governments.json
    python tools/government_names.py --check
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GOV_RE = re.compile(r"^([a-z][a-z0-9_]*)\s*=\s*\{\s*$")
LOC_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s*"(.*)"\s*$')
LANGS = ("russian", "english")
# Порядок поиска имени: понятие игры читается лучше голого ключа.
FORMS = ("game_concept_{key}", "{key}", "{key}_realm")


def parse_governments(game: Path) -> list[str]:
    """Ключи форм правления из common\\governments\\*.txt."""
    out: list[str] = []
    folder = game / "common" / "governments"
    for path in sorted(folder.glob("*.txt")):
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            match = GOV_RE.match(line)
            if match:
                key = match.group(1)
                if key not in out:
                    out.append(key)
    return out


def parse_loc(game: Path, lang: str) -> dict[str, str]:
    out: dict[str, str] = {}
    folder = game / "localization" / lang
    if not folder.is_dir():
        return out
    for path in folder.rglob("*.yml"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            match = LOC_RE.match(line)
            if match:
                out.setdefault(match.group(1), match.group(2))
    return out


def clean(text: str) -> str:
    text = re.sub(r"#[A-Za-z]+\s*", "", text).replace("#!", "")
    return text.strip().strip('"')


GOV_KEY_RE = re.compile(r"^(?:game_concept_)?([a-z][a-z0-9_]*_government)$")


def build(game: Path) -> dict:
    locs = {lang: parse_loc(game, lang) for lang in LANGS}
    # Ключи берём из двух мест: определения в common\governments и локализация.
    # Часть форм (вануа) в common не лежит, а в сейве встречается.
    keys = list(parse_governments(game))
    for table in locs.values():
        for key in table:
            match = GOV_KEY_RE.match(key)
            if match and match.group(1) not in keys:
                keys.append(match.group(1))
    out: dict[str, dict] = {}
    for key in keys:
        row = {"names": {}}
        for lang, table in locs.items():
            for form in FORMS:
                found = table.get(form.format(key=key))
                if found:
                    row["names"][lang] = clean(found)
                    break
        out[key] = row
    return out


def check(game: Path, path: Path) -> int:
    fresh = build(game)
    if not path.exists():
        print(f"нет справочника: {path} — соберите --out")
        return 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in fresh if k not in saved]
    no_name = [k for k, v in fresh.items() if not v["names"].get("russian")]
    print(f"форм правления в игре: {len(fresh)} | в справочнике: {len(saved)}")
    print(f"без русского названия: {len(no_name)}")
    if no_name[:6]:
        print("   например:", ", ".join(no_name[:6]))
    if missing:
        print(f"не хватает: {len(missing)} — {', '.join(missing[:6])}")
    ok = not missing and not no_name
    print("OK   справочник сходится с игрой" if ok else "ПЛОХО справочник расходится с игрой")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Названия форм правления из файлов игры")
    parser.add_argument("--game", type=Path, default=None, help="папка game игры")
    parser.add_argument("--out", type=Path, default=None, help="куда писать справочник")
    parser.add_argument("--check", action="store_true", help="сверить справочник с игрой")
    args = parser.parse_args()

    game = args.game or (Path(os.environ["CK3_GAME"]) if os.environ.get("CK3_GAME") else None)
    if not game:
        parser.error("нужна папка игры: --game или переменная CK3_GAME")
    if not (game / "common" / "governments").is_dir():
        parser.error(f"в {game} нет common\\governments")

    out = args.out or Path("_cache/governments.json")
    if args.check:
        return check(game, out)

    data = build(game)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    named = sum(1 for v in data.values() if v["names"].get("russian"))
    print(f"форм правления: {len(data)}, с русским названием: {named} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
