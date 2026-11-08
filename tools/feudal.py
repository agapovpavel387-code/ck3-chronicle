"""Феодальная система: кто кем владеет и кому подчиняется.

Два разных подчинения, и путать их нельзя:

* **на деле (de facto)** — человек `A` служит человеку `B` (`characters[].liege`);
  у независимого сюзерена `liege` пуст;
* **по праву (de jure)** — титул `c_x` входит в герцогство `d_y`, оно — в королевство
  `k_z` (`titles[].de_jure`), независимо от того, кто сидит на земле.

Владелец титула — человек из `characters[].titles`, а не `titles[].de_facto`:
последнее в сейве всегда указывает на другой титул.

Проверить себя без игры: `python tools/feudal.py --selftest`.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

MAX_CHAIN = 8


def person_chain(cid: int | None, characters: dict[int, dict], limit: int = MAX_CHAIN) -> list[dict]:
    """Вассал → его сюзерен → … → независимый.

    Останавливается на человеке без сюзерена, на пропуске в данных и на цикле:
    в сейве встречаются обрывы, и вечная петля тут хуже короткой цепочки.
    """
    out: list[dict] = []
    seen: set[int] = set()
    current = cid
    while current is not None and current not in seen and len(out) < limit:
        seen.add(current)
        person = characters.get(current)
        if not person:
            break
        out.append(
            {
                "id": current,
                "name": person.get("name") or "",
                "house": person.get("house_name") or "",
                "title": person.get("main_title") or "",
            }
        )
        current = person.get("liege")
    return out


def suzerain_of(cid: int | None, characters: dict[int, dict], limit: int = MAX_CHAIN) -> int | None:
    """Верхний сюзерен: последний в цепочке подчинения."""
    chain = person_chain(cid, characters, limit)
    return chain[-1]["id"] if chain else None


def vassals_map(characters: dict[int, dict]) -> dict[int, list[int]]:
    """Сюзерен → его прямые вассалы."""
    out: dict[int, list[int]] = defaultdict(list)
    for cid, person in characters.items():
        liege = person.get("liege")
        if liege:
            out[liege].append(cid)
    return dict(out)


def title_chain(title_id: int | None, titles: dict[int, dict], limit: int = MAX_CHAIN) -> list[dict]:
    """Титул → его de jure сюзерен → … → империя."""
    out: list[dict] = []
    seen: set[int] = set()
    current = title_id
    while current is not None and current not in seen and len(out) < limit:
        seen.add(current)
        tile = titles.get(current)
        if not tile:
            break
        out.append({"id": current, "key": tile.get("key"), "name": tile.get("name"), "tier": tile.get("tier")})
        current = tile.get("de_jure")
    return out


def check(chains: dict[int, list[dict]], characters: dict[int, dict]) -> dict:
    """Проверки цепочек: обрывы, петли, длина."""
    broken = [cid for cid, chain in chains.items() if not chain]
    loops = []
    for cid in chains:
        seen: set[int] = set()
        current = characters.get(cid, {}).get("liege")
        steps = 0
        while current and steps < MAX_CHAIN * 2:
            if current in seen:
                loops.append(cid)
                break
            seen.add(current)
            current = characters.get(current, {}).get("liege")
            steps += 1
    longest = max((len(c) for c in chains.values()), default=0)
    independent = sum(1 for c in chains.values() if len(c) == 1)
    return {
        "people": len(chains),
        "broken": len(broken),
        "loops": len(loops),
        "longest": longest,
        "independent": independent,
    }


def build(characters: dict[int, dict], titles: dict[int, dict]) -> dict:
    """Цепочки для всех персонажей и обратный индекс вассалов."""
    chains = {cid: person_chain(cid, characters) for cid in characters}
    vassals = vassals_map(characters)
    stats = check(chains, characters)
    stats["vassals"] = sum(len(v) for v in vassals.values())
    return {"chains": chains, "vassals": vassals, "stats": stats}


def selftest() -> int:
    """Проверка без игры: цепочка, независимый, петля, обрыв."""
    characters = {
        1: {"name": "Граф", "liege": 2, "house_name": "Дом"},
        2: {"name": "Герцог", "liege": 3, "house_name": "Дом"},
        3: {"name": "Король", "liege": None, "house_name": "Дом"},
        4: {"name": "Сам", "liege": None, "house_name": "Иной"},
        5: {"name": "Петля А", "liege": 6},
        6: {"name": "Петля Б", "liege": 5},
    }
    titles = {
        10: {"key": "c_x", "name": "Икс", "tier": "County", "de_jure": 11},
        11: {"key": "d_x", "name": "Игрек", "tier": "Duchy", "de_jure": 12},
        12: {"key": "k_x", "name": "Зет", "tier": "Kingdom", "de_jure": None},
    }

    chain = person_chain(1, characters)
    assert [p["name"] for p in chain] == ["Граф", "Герцог", "Король"], chain
    assert suzerain_of(1, characters) == 3, suzerain_of(1, characters)
    assert len(person_chain(4, characters)) == 1
    # Петля не зацикливает: цепочка обрывается на повторе.
    loop = person_chain(5, characters)
    assert len(loop) == 2, loop

    tchain = title_chain(10, titles)
    assert [t["key"] for t in tchain] == ["c_x", "d_x", "k_x"], tchain

    vassals = vassals_map(characters)
    assert vassals[2] == [1], vassals
    assert vassals[3] == [2], vassals

    stats = check({cid: person_chain(cid, characters) for cid in characters}, characters)
    assert stats["loops"] == 2, stats
    assert stats["independent"] == 2, stats  # Король и «Сам»

    print("OK   феодальная цепочка: вассал → сюзерен → независимый")
    print(f"OK   {stats}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Феодальные цепочки: кто кому подчиняется")
    parser.add_argument("--selftest", action="store_true", help="проверка без игры")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    parser.error("нужен --selftest: цепочки строятся при сборке мира")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
