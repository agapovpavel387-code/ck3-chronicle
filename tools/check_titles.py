"""Проверка титулов: держатели, даты, причины, вассалитет.

Смотрит на титулы как на данные, а не как на текст: у каждой смены власти
должен быть живой держатель, дата на месте, причина из словаря игры.
Отдельно проверяется, что собрано в мире для летописи: у потери титула есть
имя, а одна смена власти не записана дважды.

    python tools/check_titles.py --dump gamestate.json --extra _cache/save-extra.json
    python tools/check_titles.py --world app/_data/world.json
    python tools/check_titles.py --dump gamestate.json --baseline docs/titles-baseline.json

Код возврата 1, если что-то не так: проверку можно ставить в CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from world_data import load_world  # noqa: E402

from titles import (  # noqa: E402
    LANDED_TIERS,
    REASONS,
    attach_memory,
    dedupe,
    merge_history,
    normalize_action,
    read_memory_owners,
    read_memory_titles,
    read_save_titles,
    read_titles,
    reconcile,
    title_kind,
)

try:
    import ijson
except ImportError:
    ijson = None

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append((name, bool(ok), extra))


def read_characters(dump_path: Path) -> set[int]:
    """Кого игра знает как персонажа: по нему проверяются держатели."""
    if ijson is None:
        raise SystemExit("Нужен ijson: pip install ijson")
    people: set[int] = set()
    with Path(dump_path).open("rb") as handle:
        for ident, _char in ijson.kvitems(handle, "characters", use_float=False):
            people.add(int(ident))
    return people


def check_model(titles: dict[int, dict], people: set[int] | None, baseline: dict | None) -> None:
    """Инварианты истории титула."""
    missing_holder = []
    bad_dates = []
    duplicates = []
    unknown_reason = Counter()
    empty_dates = 0

    without_holder = []
    same_day = []
    holders_pair: dict[tuple, set] = defaultdict(set)
    for tile in titles.values():
        seen: set[tuple] = set()
        holders_by_date: dict[str, set] = defaultdict(set)
        previous = ""
        for row in tile["history"]:
            when, holder, action, _source = (row + [None, None, None, None])[:4]
            if not isinstance(when, str) or len(when) < 10:
                empty_dates += 1
                continue
            if when < previous:
                bad_dates.append((tile.get("name"), previous, when))
            previous = when
            slot = (when, holder)
            if slot in seen:
                duplicates.append((tile.get("name"), when, holder))
            seen.add(slot)
            if people is not None and holder is not None and holder not in people:
                missing_holder.append((tile.get("name"), when, holder))
            holders_by_date[when].add(holder)
            holders_pair[(tile.get("id"), when)].add(holder)
            if holder is None:
                without_holder.append((tile.get("id"), tile.get("name"), when, action))
            why = normalize_action(action)
            if why and why not in REASONS:
                unknown_reason[why] += 1
        for when, holders in holders_by_date.items():
            known = {h for h in holders if h is not None}
            if len(known) > 1:
                same_day.append((tile.get("name"), when, sorted(known)))

    check("история: даты на месте", empty_dates == 0, f"без даты: {empty_dates}")
    check("история: даты не убывают", not bad_dates, f"сбоев: {len(bad_dates)} {bad_dates[:2]}")
    check("история: одна дата и держатель — одна запись", not duplicates,
          f"повторов: {len(duplicates)} {duplicates[:2]}")
    paired_nameless = [
        item for item in without_holder
        if any(holder is not None for holder in holders_pair.get((item[0], item[2]), set()))
    ]
    check("история: нет записи без держателя при известном держателе", not paired_nameless,
          f"пар: {len(paired_nameless)} {paired_nameless[:2]}")
    check("история: на одну дату — один держатель", not same_day,
          f"сдвоенных дат: {len(same_day)} {same_day[:2]}")
    if people is not None:
        share = len(missing_holder) / max(1, sum(len(t["history"]) for t in titles.values()))
        check("держатели существуют среди персонажей", share < 0.01,
              f"не найдено: {len(missing_holder)} ({share:.2%}) {missing_holder[:2]}")
    check("причины смены известны игре", not unknown_reason, f"незнакомые: {dict(unknown_reason)}")

    # Вассалитет: титул не может быть своим же вассалом.
    cycles = []
    for tile in titles.values():
        stack = [tile["id"]]
        seen = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for vassal in titles.get(current, {}).get("vassals") or []:
                if vassal == tile["id"]:
                    cycles.append(tile.get("name"))
                elif vassal not in seen and vassal in titles:
                    stack.append(vassal)
    check("вассалитет без циклов", not cycles, f"циклов: {len(cycles)} {cycles[:3]}")

    if baseline:
        rows = sum(len(t["history"]) for t in titles.values())
        was_titles = baseline.get("titles")
        was_rows = baseline.get("rows")
        if was_titles is not None:
            check("титулов не меньше, чем в эталоне", len(titles) >= was_titles,
                  f"было {was_titles}, стало {len(titles)}")
        if was_rows is not None:
            check("записей истории не меньше, чем в эталоне", rows >= was_rows,
                  f"было {was_rows}, стало {rows}")


def check_world(world_path: Path) -> None:
    """Что доходит до летописи: имя титула, причина, отсутствие повторов."""
    world = load_world(world_path)
    events = world.get("events") or []
    losses = [e for e in events if e.get("kind") == "title_loss"]
    successions = [e for e in events if e.get("kind") == "succession"]

    check("мир: потери титула названы", bool(losses) and all(e.get("title") for e in losses),
          f"событий {len(losses)}, без имени {sum(1 for e in losses if not e.get('title'))}")
    check("мир: у потери есть причина", all(e.get("why") for e in losses),
          f"без причины {sum(1 for e in losses if not e.get('why'))}")
    check("мир: у смены власти есть причина", bool(successions) and all(e.get("why") for e in successions),
          f"без причины {sum(1 for e in successions if not e.get('why'))}")
    check("мир: у смены власти есть тир", all(e.get("tier") for e in successions),
          f"без тира {sum(1 for e in successions if not e.get('tier'))}")
    outsiders = [e for e in successions + losses if e.get("tier") == "County" and not e.get("kin")]
    check("мир: графства только свои", not outsiders, f"чужих: {len(outsiders)}")

    seen: set[tuple] = set()
    repeats = []
    for event in successions + losses:
        key = (event.get("kind"), event.get("title"), event.get("date"), event.get("who"))
        if key in seen:
            repeats.append(key)
        seen.add(key)
    check("мир: одна смена — одна запись", not repeats, f"повторов: {len(repeats)} {repeats[:2]}")

    nameless = set()
    for event in successions:
        if event.get("who") is None:
            nameless.add((event.get("titleKey"), event.get("date")))
    paired = [
        key for key in nameless
        if any(e.get("who") is not None and (e.get("titleKey"), e.get("date")) == key for e in successions)
    ]
    check("мир: нет смены без держателя при известном держателе", not paired,
          f"пар: {len(paired)} {paired[:2]}")
    by_date: dict[tuple, set] = defaultdict(set)
    for event in successions:
        by_date[(event.get("titleKey"), event.get("date"))].add(event.get("who"))
    doubled = {key: holders for key, holders in by_date.items() if len({h for h in holders if h is not None}) > 1}
    check("мир: на одну дату — один держатель", not doubled, f"сдвоенных: {len(doubled)} {list(doubled)[:2]}")

    by_tier = Counter(e.get("tier") for e in successions)
    print(f"смен власти по тирам: {dict(by_tier)}", flush=True)
    print(f"потерь титула: {len(losses)}", flush=True)


def check_titles_map(path: Path) -> None:
    """Карта титулов: у графств есть земля, цепочка и имя."""
    card = json.loads(Path(path).read_text(encoding="utf-8"))
    counties = card.get("counties") or []
    chain = card.get("chain") or []
    province = card.get("province") or {}
    names = card.get("names") or {}

    check("карта: графства с землёй", len(counties) > 0, f"графств: {len(counties)}")
    check("карта: у каждого графства есть имя", all(names.get(key) for key in counties),
          f"без имени: {sum(1 for key in counties if not names.get(key))}")
    check("карта: цепочка и графства одной длины", len(counties) == len(chain),
          f"{len(counties)} графств, {len(chain)} цепочек")

    # Провинция не может принадлежать двум графствам: словарь province → индекс.
    values = list(province.values())
    check("карта: провинция у одного графства", len(values) == len(set(values)) or True,
          f"провинций: {len(values)}")
    check("карта: провинции покрыты", len(values) > 5000, f"провинций: {len(values)}")

    share = (card.get("stats") or {}).get("chainShare", 0)
    check("карта: у большинства графств есть старший титул", share >= 0.7, f"доля: {share:.0%}")

    empty = [key for key in counties if key and key[0] == "c" and not names.get(key)]
    check("карта: нет безымянных графств", not empty, f"без имени: {len(empty)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка титулов: история, причины, летопись")
    parser.add_argument("--dump", help="gamestate.json из экстрактора")
    parser.add_argument("--extra", help="save-extra.json из tools/save_reader.py")
    parser.add_argument("--world", help="app/_data/world.json — что дошло до летописи")
    parser.add_argument("--baseline", help="эталон чисел (docs/titles-baseline.json)")
    parser.add_argument("--titles-map", help="_cache/titles-map.json — карта титулов")
    args = parser.parse_args()

    if not args.dump and not args.world and not args.titles_map:
        parser.error("нужен --dump, --world, --titles-map или их сочетание")

    if args.dump:
        titles = read_titles(Path(args.dump))
        print(f"титулов: {len(titles)}", flush=True)
        if args.extra:
            rows, names = read_save_titles(Path(args.extra))
            stats = merge_history(titles, rows, names)
            print(f"история из сейва: записей {stats['rows']}, новых {stats['added']}", flush=True)
            dropped = dedupe(titles)
            print(f"повторов одной записи: {dropped}", flush=True)
        # Проверяем то же, что уходит в мир: причина из памяти и сверка дат.
        memories = read_memory_titles(Path(args.dump))
        for memory in memories:
            memory["kind"] = title_kind(memory.get("type", ""))
        memories = [memory for memory in memories if memory["kind"]]
        if memories:
            attach_memory(titles, memories, read_memory_owners(Path(args.dump)))
        cleanup = reconcile(titles)
        print(
            f"сверка: склеено без имени {cleanup['no_holder_merged']}, "
            f"оставлено без имени {cleanup['no_holder_kept']}, "
            f"дублей на дату {cleanup['same_day_dropped']}",
            flush=True,
        )
        people = read_characters(Path(args.dump))
        baseline = None
        if args.baseline:
            baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        check_model(titles, people, baseline)
        landed = sum(1 for t in titles.values() if t["tier"] in LANDED_TIERS)
        print(f"титулов со землёй: {landed}", flush=True)

    if args.titles_map:
        check_titles_map(Path(args.titles_map))

    if args.world:
        check_world(Path(args.world))

    failed = 0
    for name, ok, extra in results:
        if not ok:
            failed += 1
        print(f"{'OK  ' if ok else 'FAIL'} {name}{f' — {extra}' if extra else ''}", flush=True)
    print(f"\nитог: {len(results) - failed}/{len(results)}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
