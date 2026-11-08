#!/usr/bin/env python3
"""Diagnose a CK3 dump: houses, dynasties, characters, player.

Answers the question "why does the app show no dynasty" without guessing:

    python tools/doctor.py --dump out/gamestate.json

It reads an already-made dump. To make one from a save, run the importer first
(or pass --save and --extractor and the doctor will do it).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Консоль Windows бывает в cp1251: без этого любой не-кириллический знак роняет вывод.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from world_data import load_world  # noqa: E402


def count_map(path: Path, section: str) -> tuple[int, int]:
    """Возвращает (всего записей, записей с непустым именем)."""
    import ijson

    total = 0
    named = 0
    with path.open("rb") as handle:
        for _key, value in ijson.kvitems(handle, section, use_float=False):
            total += 1
            if isinstance(value, dict) and value.get("name"):
                named += 1
    return total, named


def house_dynasties(path: Path) -> dict:
    """Дом → династия: у персонажа династии нет, она у его дома."""
    import ijson

    mapping: dict[int, int] = {}
    with path.open("rb") as handle:
        for key, value in ijson.kvitems(handle, "houses", use_float=False):
            if not isinstance(value, dict):
                continue
            parent = value.get("parent") or {}
            dynasty_id = parent.get("id") if isinstance(parent, dict) else parent
            if dynasty_id:
                try:
                    mapping[int(key)] = int(dynasty_id)
                except (TypeError, ValueError):
                    continue
    return mapping


def character_stats(path: Path, dynasties: dict[int, int]) -> dict:
    import ijson

    total = 0
    with_house = 0
    with_dynasty = 0
    sample = None
    with path.open("rb") as handle:
        for _key, value in ijson.kvitems(handle, "characters", use_float=False):
            if not isinstance(value, dict):
                continue
            total += 1
            house = value.get("house")
            house_id = house.get("id") if isinstance(house, dict) else house
            if house_id:
                with_house += 1
                if house_id in dynasties:
                    with_dynasty += 1
            if sample is None and value.get("name") and value.get("house"):
                sample = {
                    "name": value.get("name"),
                    "house": (value.get("house") or {}).get("name") if isinstance(value.get("house"), dict) else value.get("house"),
                    "keys": sorted(value.keys())[:12],
                }
            if total >= 30000:
                break
    return {"total": total, "with_house": with_house, "with_dynasty": with_dynasty, "sample": sample}


def selftest() -> int:
    """Проверка без игры: разбор маленького дампа."""
    import json
    import tempfile

    dump = {
        "houses": {
            "1": {"name": "Дом", "parent": {"id": 10}},
            "2": {"name": "", "parent": {"id": 10}},
        },
        "dynasties": {"10": {"name": "Династия"}},
        "characters": {
            "1": {"name": "Первый", "house": {"id": 1, "name": "Дом"}},
            "2": {"name": "Второй", "house": {"id": 2}},
            "3": {"name": "Третий"},
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dump.json"
        path.write_text(json.dumps(dump), encoding="utf-8")

        total, named = count_map(path, "houses")
        assert (total, named) == (2, 1), (total, named)

        mapping = house_dynasties(path)
        assert mapping == {1: 10, 2: 10}, mapping

        stats = character_stats(path, mapping)
        assert stats["total"] == 3, stats
        assert stats["with_house"] == 2, stats
        assert stats["with_dynasty"] == 2, stats
        assert stats["sample"] and stats["sample"]["name"] == "Первый", stats["sample"]

    print("OK   доктор: дома, династии, персонажи")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a CK3 dump for the app.")
    parser.add_argument("--dump", type=Path, help="gamestate.json made by the extractor")
    parser.add_argument("--selftest", action="store_true", help="проверка без игры")
    parser.add_argument("--save", type=Path, help="a .ck3 save to dump first")
    parser.add_argument("--extractor", type=Path, help="ck3_history_extractor.exe (with --save)")
    parser.add_argument("--game", type=Path, help="game folder (for extraction and the map)")
    parser.add_argument("--lang", default="russian")
    args = parser.parse_args()
    if args.selftest:
        raise SystemExit(selftest())

    dump = args.dump
    if not dump and args.save:
        work = ROOT / "import"
        work.mkdir(parents=True, exist_ok=True)
        dump = work / "gamestate.json"
        extractor = args.extractor
        if not extractor:
            raise SystemExit("Pass --extractor with --save.")
        command = [str(extractor), str(args.save), "-o", str(work), "-n", "--no-vis", "--dump", str(dump)]
        if args.game:
            command += ["-g", str(args.game)]
        command += ["-l", args.lang]
        print("== Extracting ==")
        subprocess.run(command, cwd=extractor.parent, check=False)
    if not dump or not dump.exists():
        raise SystemExit("No dump to inspect. Pass --dump, or --save with --extractor.")

    print(f"Dump: {dump} ({dump.stat().st_size / 1048576:.1f} MB)")

    import ijson

    with dump.open("rb") as handle:
        current_date = next(ijson.items(handle, "current_date", use_float=False), None)
    print(f"Date: {current_date or 'unknown'}")

    dynasties_total, dynasties_named = count_map(dump, "dynasties")
    houses_total, houses_named = count_map(dump, "houses")
    print(f"Dynasties: {dynasties_total} (with a name: {dynasties_named})")
    print(f"Houses:    {houses_total} (with a name: {houses_named})")

    dynasties = house_dynasties(dump)
    print(f"Houses linked to a dynasty: {len(dynasties)}")
    stats = character_stats(dump, dynasties)
    print(f"Characters: {stats['total']} scanned, with a house: {stats['with_house']}, with a dynasty: {stats['with_dynasty']}")
    if stats["sample"]:
        sample = stats["sample"]
        print(f"Sample: {sample['name']} — house {sample['house']}")
        print(f"        fields: {', '.join(sample['keys'])}")

    # Что видит сборщик мира
    world_path = ROOT / "app" / "_data" / "world.js"
    if world_path.exists():
        world = load_world(world_path)
        player = world.get("meta", {}).get("player", {})
        dynasty = world.get("dynasty") or {}
        print("\nCurrent world in app/_data:")
        print(f"  player:  {player.get('name')} — house {player.get('house')}, dynasty {player.get('dynasty')}")
        print(f"  dynasty: {dynasty.get('name')} ({len(dynasty.get('houses') or [])} houses)")
        print(f"  people:  {len(world.get('people') or [])}, kin: {sum(1 for p in world.get('people') or [] if p.get('kin'))}")

    print("\nWhat to look at:")
    print("  dynasties = 0        → the save has no dynasty section the parser understands")
    print("  with a dynasty = 0   → characters carry no dynasty link (landless start)")
    print("  houses = 0           → houses failed to parse")


if __name__ == "__main__":
    main()
