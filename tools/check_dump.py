#!/usr/bin/env python3
"""Эталон дампа: что экстрактор отдал и не просело ли это после пересборки.

    python tools/check_dump.py --dump "%LOCALAPPDATA%/ck3-chronicle/import/gamestate.json"
    python tools/check_dump.py --dump dump.json --world app/_data/world.json
    python tools/check_dump.py --dump dump.json --baseline docs/dump-baseline.json

Зачем: экстрактор — сторонний бинарь. Любая его пересборка или смена сейва меняет
числа, и без эталона потеря половины предков выглядит как «хроника стала короче».
Скрипт печатает сводку и падает, если числа ниже порога.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import ijson

# Порог «ниже этого — уже регресс». Значения взяты по рабочему сейву 917 года (Шу)
# и по тестовому 995 года (Гондэрид); занижены с запасом, чтобы не ловить шум.
MINIMAL = {
    "titles": 15_000,
    "characters": 30_000,
    "memories": 1_500,
}

REQUIRED_SECTIONS = ("characters", "titles", "houses", "dynasties", "memories")

# Чего в дампе нет и что придётся брать из сейва (см. tools/save_reader.py).
KNOWN_GAPS = ("wars", "casus_belli", "title_history_after_start")


def scan(dump: Path) -> dict:
    sections: list[str] = []
    with dump.open("rb") as fh:
        for prefix, event, value in ijson.parse(fh, use_float=False):
            if event == "map_key" and prefix == "":
                sections.append(value)

    titles = 0
    titles_with_history = 0
    history_entries = 0
    history_last = ""
    tiers: Counter = Counter()

    with dump.open("rb") as fh:
        for _ident, tile in ijson.kvitems(fh, "titles", use_float=False):
            titles += 1
            tiers[str(tile.get("tier"))] += 1
            hist = tile.get("history") or []
            if hist:
                titles_with_history += 1
                for entry in hist:
                    if not (isinstance(entry, list) and len(entry) >= 3):
                        continue
                    history_entries += 1
                    date = entry[0]
                    if isinstance(date, str) and date > history_last:
                        history_last = date

    characters = 0
    dead = 0
    with_memories = 0
    reasons: Counter = Counter()
    former = 0
    with dump.open("rb") as fh:
        for _ident, ch in ijson.kvitems(fh, "characters", use_float=False):
            characters += 1
            if ch.get("dead"):
                dead += 1
                reason = ch.get("reason")
                if reason:
                    reasons[str(reason)] += 1
            if ch.get("memories"):
                with_memories += 1
            if ch.get("former"):
                former += 1

    memories = 0
    memory_types: Counter = Counter()
    with dump.open("rb") as fh:
        for _ident, mem in ijson.kvitems(fh, "memories", use_float=False):
            memories += 1
            memory_types[(mem.get("type") or "").strip()] += 1

    start = ""
    with dump.open("rb") as fh:
        start = next(ijson.items(fh, "current_date", use_float=False), "") or ""

    return {
        "dump": str(dump),
        "size_mb": round(dump.stat().st_size / 1048576, 1),
        "sections": sections,
        "missing_sections": [name for name in REQUIRED_SECTIONS if name not in sections],
        "gaps": [name for name in KNOWN_GAPS if name not in sections],
        "date": start,
        "titles": titles,
        "titles_with_history": titles_with_history,
        "history_entries": history_entries,
        "history_last_date": history_last,
        "tiers": dict(tiers),
        "characters": characters,
        "dead": dead,
        "characters_with_memories": with_memories,
        "characters_with_former_titles": former,
        "death_reasons": dict(reasons.most_common(12)),
        "memories": memories,
        "memory_types": dict(memory_types.most_common(20)),
    }


def world_summary(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("meta") or {}
    counts = meta.get("counts") or {}
    events = data.get("events") or []
    return {
        "world": str(path),
        "date": meta.get("date"),
        "counts": counts,
        "events": len(events),
        "event_kinds": dict(Counter(e.get("kind") for e in events).most_common()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--world", type=Path, default=None, help="app/_data/world.json для сверки")
    parser.add_argument("--baseline", type=Path, default=None, help="сохранить сводку как эталон")
    parser.add_argument("--compare", type=Path, default=None, help="сверить с сохранённым эталоном")
    parser.add_argument("--json", action="store_true", help="только машинный вывод")
    args = parser.parse_args()

    report = scan(args.dump)
    if args.world and args.world.exists():
        report["world"] = world_summary(args.world)

    failures = []
    for name, minimum in MINIMAL.items():
        value = report.get(name, 0)
        if value < minimum:
            failures.append(f"{name}: {value} < {minimum}")
    if report["missing_sections"]:
        failures.append("нет секций: " + ", ".join(report["missing_sections"]))
    if report["history_last_date"] and report["date"] and report["history_last_date"] < report["date"]:
        report.setdefault("warnings", []).append(
            f"история титулов кончается на {report['history_last_date']}, а сейв на {report['date']} — "
            "игровые смены власти в дампе не видны (их добавляет tools/save_reader.py)"
        )

    if args.compare and args.compare.exists():
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        for key in ("titles", "characters", "memories", "history_entries"):
            was = baseline.get(key)
            now = report.get(key)
            if isinstance(was, int) and isinstance(now, int) and now < was:
                failures.append(f"{key}: было {was}, стало {now}")

    if args.baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"дамп: {report['dump']} ({report['size_mb']} МБ), дата сейва: {report['date']}")
        print(f"секции ({len(report['sections'])}): {', '.join(report['sections'])}")
        print(f"титулов {report['titles']} (с историей {report['titles_with_history']}, записей {report['history_entries']}, последняя {report['history_last_date'] or '—'})")
        print(f"персонажей {report['characters']}, мёртвых {report['dead']}, с воспоминаниями {report['characters_with_memories']}, с бывшими титулами {report['characters_with_former_titles']}")
        print(f"воспоминаний {report['memories']}, типов {len(report['memory_types'])}")
        if report["death_reasons"]:
            print("причины смерти:", ", ".join(f"{k}={v}" for k, v in report["death_reasons"].items()))
        if "world" in report:
            world = report["world"]
            print(f"мир: дата {world['date']}, событий {world['events']}, counts {world['counts']}")
            print("виды событий:", ", ".join(f"{k}={v}" for k, v in world["event_kinds"].items()))
        if report["gaps"]:
            print("нет в дампе (берём из сейва):", ", ".join(report["gaps"]))
        for line in report.get("warnings", []):
            print("внимание:", line)

    if failures:
        print("\nПРОВАЛ:", file=sys.stderr)
        for line in failures:
            print("  -", line, file=sys.stderr)
        raise SystemExit(1)
    print("\nИТОГ: ок")


if __name__ == "__main__":
    main()
