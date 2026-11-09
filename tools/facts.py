#!/usr/bin/env python3
"""Числа проекта считаются из артефактов, а не переписываются в текстах.

    python tools/facts.py --check                      # 0, если docs/facts.json свеж
    python tools/facts.py --write                      # пересчитать и записать
    python tools/facts.py --write --test-log _cache/test.log

Источники — только файлы данных: `app/_data/world.js` (мир из сейва) и
`app/_data/titles-map.json` (карта титулов). Версия — из `VERSION`.
Человеческая таблица `docs/facts.md` генерируется отсюда же, поэтому разойтись
с данными она не может: любое изменение `world.js` валит `--check`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world_data import load_world, world_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FACTS_JSON = DOCS / "facts.json"
FACTS_MD = DOCS / "facts.md"
TITLES_MAP = ROOT / "app" / "_data" / "titles-map.json"

# Порядок из npm test: по нему строки «итог: N/N» в журнале раскладываются по наборам.
# Если в `package.json` добавят набор, а сюда нет — test_facts упадёт, а не сдвинет счёт.
SUITES = [
    "check_app.js",
    "check_tree.js",
    "check_chronicle.js",
    "check_lens.js",
    "check_titles.py",
    "check_server.js",
]


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def world_facts() -> dict:
    world = load_world(world_path(ROOT / "app" / "_data"))
    meta = world.get("meta") or {}
    counts = meta.get("counts") or {}
    events = world.get("events") or []
    realms_list = world.get("realms") or []
    return {
        "date": meta.get("date") or "",
        "year": meta.get("year"),
        "build": meta.get("build") or "",
        "realms": counts.get("realms"),
        "known": counts.get("known"),
        "people": counts.get("people"),
        "dynasty": counts.get("dynasty"),
        "events": counts.get("events"),
        "eventsWithCause": sum(1 for e in events if e.get("why")),
        "byRing": {str(k): v for k, v in sorted((meta.get("byRing") or {}).items(), key=lambda kv: int(kv[0]))},
        "periods": len(meta.get("periods") or []),
        # Вера приходит из сейва через обряды: считаем, где она есть и сколько разных.
        "peopleWithFaith": sum(1 for p in (world.get("people") or []) if p.get("faith")),
        "realmsWithFaith": sum(1 for r in realms_list if r.get("faith")),
        "realmsInList": len(realms_list),
        "faiths": len({p["faith"] for p in (world.get("people") or []) if p.get("faith")}
                      | {r["faith"] for r in (world.get("realms") or []) if r.get("faith")}),
        # Двор: форма правления, наследование, министерства.
        "realmsWithGovernment": sum(1 for r in realms_list if r.get("governmentName")),
        "realmsWithSuccession": sum(1 for r in realms_list if r.get("succession")),
        "ministries": sum(len(r.get("ministers") or []) for r in realms_list),
    }


def titles_facts() -> dict:
    """Титулы считаются по реестру карты: `names` — всё, что карта умеет назвать.

    Считать по `chain` нельзя: цепочка заполнена у 74% графств, и "герцогств"
    получилось бы 914 вместо 1316 — это не титулы, а те, у кого есть графства.
    """
    data = json.loads(TITLES_MAP.read_text(encoding="utf-8"))
    names = data.get("names") or {}
    stats = data.get("stats") or {}
    by_prefix = {"c": 0, "d": 0, "k": 0, "e": 0}
    for key in names:
        if key[:1] in by_prefix:
            by_prefix[key[0]] += 1
    return {
        "counties": by_prefix["c"],
        "duchies": by_prefix["d"],
        "kingdoms": by_prefix["k"],
        "empires": by_prefix["e"],
        "landedChains": stats.get("counties"),
        "provinces": stats.get("provinces"),
        "chainShare": stats.get("chainShare"),
    }


def test_facts(log: Path | None) -> list[dict]:
    if not log or not log.exists():
        return []
    text = log.read_text(encoding="utf-8", errors="replace")
    found = [(int(a), int(b)) for a, b in re.findall(r"итог:\s*(\d+)\s*/\s*(\d+)", text)]
    if found and len(found) != len(SUITES):
        raise SystemExit(
            f"в журнале {len(found)} наборов, а в SUITES {len(SUITES)} — "
            "обновите список наборов, иначе счёт сдвинется"
        )
    suites = []
    for name, (passed, total) in zip(SUITES, found):
        suites.append({"name": name, "passed": passed, "total": total})
    return suites


def digest(payload: dict) -> str:
    body = {k: payload[k] for k in ("version", "world", "titles") if k in payload}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def collect(log: Path | None, previous_tests: list[dict] | None = None) -> dict:
    payload = {
        "version": version(),
        "world": world_facts(),
        "titles": titles_facts(),
        "tests": test_facts(log) or (previous_tests or []),
    }
    payload["digest"] = digest(payload)
    return payload


def num(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.0%}" if 0 <= value <= 1 else f"{value:g}"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return str(value)


def render_md(facts: dict) -> str:
    world, titles, tests = facts["world"], facts["titles"], facts.get("tests") or []
    lines = [
        "# Числа мира",
        "",
        "<!-- Сгенерировано tools/facts.py. Руками не править: правка не переживёт",
        "     `python tools/facts.py --write`, а `--check` её не пропустит. -->",
        "",
        f"Версия `{facts['version']}`, мир от {world['date']} (сборка `{world['build']}`).",
        "",
        "## Мир",
        "",
        "| Что | Значение |",
        "| --- | --- |",
        f"| Держав всего | {num(world['realms'])} |",
        f"| В поле зрения рода | {num(world['known'])} |",
        f"| Людей в родне | {num(world['people'])} |",
        f"| Родичей в династии | {num(world['dynasty'])} |",
        f"| Событий | {num(world['events'])} |",
        f"| Из них о власти — с причиной | {num(world['eventsWithCause'])} |",
        f"| Эпох рода | {num(world['periods'])} |",
        f"| Людей с верой | {num(world['peopleWithFaith'])} из {num(world['people'])} |",
        f"| Держав с верой | {num(world['realmsWithFaith'])} из {num(world['realmsInList'])} |",
        f"| Разных вер в мире | {num(world['faiths'])} |",
        f"| Держав с формой правления | {num(world['realmsWithGovernment'])} из {num(world['realmsInList'])} |",
        f"| Держав с очередью наследования | {num(world['realmsWithSuccession'])} из {num(world['realmsInList'])} |",
        f"| Министерств с титулом | {num(world['ministries'])} |",
        "",
        "| Кольцо знания | Держав |",
        "| --- | --- |",
    ]
    for ring, count in world["byRing"].items():
        lines.append(f"| {ring} | {num(count)} |")

    lines += [
        "",
        "## Титулы и карта",
        "",
        "| Что | Значение |",
        "| --- | --- |",
        f"| Графств на карте | {num(titles['counties'])} |",
        f"| Герцогств | {num(titles['duchies'])} |",
        f"| Королевств | {num(titles['kingdoms'])} |",
        f"| Империй | {num(titles['empires'])} |",
        f"| Провинций на карте | {num(titles['provinces'])} |",
        f"| Доля графств со старшим титулом | {num(titles['chainShare'])} |",
    ]

    if tests:
        total_passed = sum(s["passed"] for s in tests)
        total_all = sum(s["total"] for s in tests)
        lines += [
            "",
            "## Проверки",
            "",
            "| Набор | Прошло |",
            "| --- | --- |",
        ]
        for suite in tests:
            lines.append(f"| `{suite['name']}` | {suite['passed']} / {suite['total']} |")
        lines.append(f"| **всего** | **{total_passed} / {total_all}** |")

    lines += ["", f"Отпечаток данных: `{facts['digest'][:16]}`.", ""]
    return "\n".join(lines)


def describe_diff(old: dict, new: dict) -> list[str]:
    out = []
    for section in ("world", "titles"):
        a, b = old.get(section) or {}, new.get(section) or {}
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                out.append(f"{section}.{key}: было {a.get(key)!r}, стало {b.get(key)!r}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Числа из артефактов → docs/facts.md")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="сверить (по умолчанию)")
    group.add_argument("--write", action="store_true", help="пересчитать и записать")
    parser.add_argument("--test-log", type=Path, help="журнал npm test для строк «итог: N/N»")
    args = parser.parse_args()

    previous = {}
    if FACTS_JSON.exists():
        previous = json.loads(FACTS_JSON.read_text(encoding="utf-8"))
    facts = collect(args.test_log, previous.get("tests"))

    if args.write:
        FACTS_JSON.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
        FACTS_MD.write_text(render_md(facts), encoding="utf-8", newline="")
        print(f"записано: docs/facts.json и docs/facts.md (отпечаток {facts['digest'][:16]})")
        return 0

    if not previous:
        print("РАСХОЖДЕНИЕ: docs/facts.json ещё нет — выполните python tools/facts.py --write")
        return 1
    if previous.get("digest") != facts["digest"]:
        for line in describe_diff(previous, facts) or ["состав фактов изменился"]:
            print("РАСХОЖДЕНИЕ: " + line)
        print("\nданные разошлись с docs/facts.json — выполните python tools/facts.py --write")
        return 1
    if not FACTS_MD.exists() or FACTS_MD.read_text(encoding="utf-8") != render_md(previous):
        print("РАСХОЖДЕНИЕ: docs/facts.md не совпадает со своей моделью — выполните --write")
        return 1

    print(f"числа сходятся: {num(facts['world']['events'])} событий, "
          f"{num(facts['titles']['counties'])} графств, отпечаток {facts['digest'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
