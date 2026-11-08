"""Карта титулов: какая земля какому титулу принадлежит по de jure.

Основа — три связи, которые уже есть в данных:

* баронство → провинция: `_cache/map.json`, словарь `baronies` (`b_aachen` → 822);
* графство → баронства: `titles[].vassals` (`c_aachen` → `b_aachen`, `b_limbourg`…);
* герцогство → графства, королевство → герцогства, империя → королевства: та же связь.

Отсюда провинция получает графство, графство — герцогство и выше. Ключи титулов
(`c_aachen`), а не имена: имя меняется с языком и переименованием, ключ — нет.

Модуль отдаёт компактную карту для приложения:

    {
      "counties": ["c_aachen", …],          # порядок = индекс в PNG
      "chain": [["d_julich", "k_germany", …], …],  # старшие титулы, по индексу
      "province": {"822": 1, …},           # провинция → индекс графства (с 1)
      "names": {"c_aachen": "Ахен", …},
      "owners": {"c_aachen": 14022, …},    # держатель на дату сейва
      "stats": {…}
    }

Проверить себя без игры: `python tools/title_map.py --selftest`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from titles import LANDED_TIERS, read_titles  # noqa: E402

MAX_DEPTH = 5


def provinces_of_baronies(titles: dict[int, dict], baronies: dict[str, int]) -> dict[int, int]:
    """id баронства → id провинции. Ключи баронства знает карта, тир — титулы."""
    out: dict[int, int] = {}
    for tile in titles.values():
        if tile["tier"] != "Barony":
            continue
        province = baronies.get(tile["key"])
        if province is not None:
            out[tile["id"]] = int(province)
    return out


def county_provinces(titles: dict[int, dict], barony_province: dict[int, int]) -> dict[int, set[int]]:
    """id графства → его провинции: все баронства, а если их нет — столица."""
    out: dict[int, set[int]] = {}
    for tile in titles.values():
        if tile["tier"] != "County":
            continue
        provinces = {barony_province[v] for v in tile["vassals"] if v in barony_province}
        if not provinces and tile.get("capital") is not None:
            provinces = {int(tile["capital"])}
        out[tile["id"]] = provinces
    return out


def parents(titles: dict[int, dict]) -> dict[int, int]:
    """id титула → id de jure-сюзерена.

    Игра сама пишет `de_jure` у каждого титула — это надёжнее, чем собирать
    связь обратным ходом по вассалам: у части герцогств список вассалов пуст,
    хотя графства на них ссылаются.
    """
    out: dict[int, int] = {}
    for tile in titles.values():
        parent = tile.get("de_jure")
        if parent and parent in titles:
            out[tile["id"]] = parent
    for tile in titles.values():
        for vassal in tile["vassals"]:
            if vassal in titles and vassal not in out:
                out[vassal] = tile["id"]
    return out


def provinces_of_titles(titles: dict[int, dict], base: dict[int, set[int]]) -> dict[int, set[int]]:
    """Провинции любого титула: свои у графства, у старших — от вассалов."""
    cache: dict[int, set[int]] = {}

    def walk(title_id: int, depth: int = 0) -> set[int]:
        if title_id in cache:
            return cache[title_id]
        tile = titles.get(title_id)
        if tile is None or depth > MAX_DEPTH:
            return set()
        if title_id in base:
            result = base[title_id]
        else:
            result = set()
            for vassal in tile["vassals"]:
                result |= walk(vassal, depth + 1)
            if not result and tile.get("capital") is not None:
                result = {int(tile["capital"])}
        cache[title_id] = result
        return result

    for title_id in titles:
        walk(title_id)
    return cache


def chain_for(county_id: int, titles: dict[int, dict], parent: dict[int, int]) -> list[str]:
    """Старшие титулы графства: герцогство, королевство, империя — по порядку."""
    out: list[str] = []
    current = parent.get(county_id)
    depth = 0
    while current and depth < MAX_DEPTH:
        tile = titles.get(current)
        if not tile:
            break
        if tile["tier"] in LANDED_TIERS and tile["tier"] != "County":
            out.append(tile["key"])
        current = parent.get(current)
        depth += 1
    return out


def build(titles: dict[int, dict], baronies: dict[str, int]) -> dict:
    """Собирает карту титулов: графства, их старшие титулы и провинции."""
    barony_province = provinces_of_baronies(titles, baronies)
    base = county_provinces(titles, barony_province)
    parent = parents(titles)
    all_provinces = provinces_of_titles(titles, base)

    counties = sorted(
        (tile for tile in titles.values() if tile["tier"] == "County" and base.get(tile["id"])),
        key=lambda tile: tile["key"] or "",
    )
    index_of: dict[int, int] = {tile["id"]: i + 1 for i, tile in enumerate(counties)}

    province_to_county: dict[str, int] = {}
    for tile in counties:
        idx = index_of[tile["id"]]
        for province in base[tile["id"]]:
            province_to_county[str(province)] = idx

    chain: list[list[str]] = [chain_for(tile["id"], titles, parent) for tile in counties]
    # У пары титулов в дампе нет имени вовсе: показываем ключ, а не пустое место.
    names = {tile["key"]: (tile["name"] or tile["key"]) for tile in counties if tile["key"]}
    names.update(
        {
            tile["key"]: (tile["name"] or tile["key"])
            for tile in titles.values()
            if tile["key"] and tile["tier"] in LANDED_TIERS and tile["tier"] != "County"
        }
    )
    owners = {tile["key"]: tile["holder"] for tile in counties if tile["key"]}

    covered = set(province_to_county)
    by_tier: dict[str, int] = Counter()
    empty: dict[str, int] = Counter()
    for tile in titles.values():
        if tile["tier"] not in ("Empire", "Kingdom", "Duchy", "County"):
            continue
        if all_provinces.get(tile["id"]):
            by_tier[tile["tier"]] += 1
        else:
            empty[tile["tier"]] += 1

    return {
        "counties": [tile["key"] for tile in counties],
        "chain": chain,
        "province": province_to_county,
        "names": names,
        "owners": owners,
        "stats": {
            "counties": len(counties),
            "provinces": len(covered),
            "withLand": dict(sorted(by_tier.items())),
            "withoutLand": dict(sorted(empty.items())),
            "chainShare": round(sum(1 for c in chain if c) / max(1, len(chain)), 3),
        },
    }


def load_baronies(map_path: Path) -> dict[str, int]:
    payload = json.loads(Path(map_path).read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in (payload.get("baronies") or {}).items()}


def selftest() -> int:
    """Проверка без дампа: графство, герцогство, провинции."""
    titles = {
        1: {"id": 1, "key": "e_test", "name": "Империя", "tier": "Empire", "holder": 10, "vassals": [2], "capital": None},
        2: {"id": 2, "key": "k_test", "name": "Королевство", "tier": "Kingdom", "holder": 11, "vassals": [3], "capital": None},
        3: {"id": 3, "key": "d_test", "name": "Герцогство", "tier": "Duchy", "holder": 12, "vassals": [4, 5], "capital": None},
        4: {"id": 4, "key": "c_one", "name": "Первое", "tier": "County", "holder": 13, "vassals": [6, 7], "capital": None},
        5: {"id": 5, "key": "c_two", "name": "Второе", "tier": "County", "holder": 14, "vassals": [], "capital": 90},
        6: {"id": 6, "key": "b_one_a", "name": "А", "tier": "Barony", "holder": 15, "vassals": [], "capital": None},
        7: {"id": 7, "key": "b_one_b", "name": "Б", "tier": "Barony", "holder": 16, "vassals": [], "capital": None},
    }
    baronies = {"b_one_a": 10, "b_one_b": 11}
    card = build(titles, baronies)

    assert card["counties"] == ["c_one", "c_two"], card["counties"]
    assert card["province"] == {"10": 1, "11": 1, "90": 2}, card["province"]
    assert card["chain"][0] == ["d_test", "k_test", "e_test"], card["chain"]
    # У графства без баронств остаётся столица, цепочка та же.
    assert card["chain"][1] == ["d_test", "k_test", "e_test"], card["chain"]
    assert card["names"]["c_one"] == "Первое"
    assert card["owners"]["c_one"] == 13
    assert card["stats"]["counties"] == 2
    print("OK   карта титулов: провинции, цепочка, имена")
    print(f"OK   {card['stats']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Карта титулов: провинция → графство → старшие титулы")
    parser.add_argument("--dump", help="gamestate.json из экстрактора")
    parser.add_argument("--map", default=str(ROOT / "_cache" / "map.json"), help="карта провинций и баронств")
    parser.add_argument("--out", help="куда положить карту титулов (JSON)")
    parser.add_argument("--selftest", action="store_true", help="проверка без дампа")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.dump:
        parser.error("нужен --dump или --selftest")

    titles = read_titles(Path(args.dump))
    baronies = load_baronies(Path(args.map))
    card = build(titles, baronies)
    stats = card["stats"]
    print(f"графств с землёй: {stats['counties']}", flush=True)
    print(f"провинций под титулами: {stats['provinces']}", flush=True)
    print(f"титулы с землёй: {stats['withLand']}", flush=True)
    print(f"без земли: {stats['withoutLand']}", flush=True)
    print(f"доля графств с цепочкой: {stats['chainShare']:.0%}", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(card, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"записано: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
