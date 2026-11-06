"""Сборка карты и держав для модели «радиуса знания».

Шаги (кэш в _cache/, чтобы не считать по минуте каждый раз):

    python tools/knowledge_pilot.py map         # провинции и баронства
    python tools/knowledge_pilot.py adjacency   # соседство провинций по provinces.png
    python tools/knowledge_pilot.py realms      # державы на дату сейва
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "_cache"

# Папку игры и дамп задаёт пользователь: аргументом или переменной окружения.
# CK3_GAME — папка game (там map_data/provinces.png и common/landed_titles)
# CK3_DUMP — дамп gamestate.json, снятый экстрактором
DEFAULT_GAME = Path(os.environ.get("CK3_GAME", "")) if os.environ.get("CK3_GAME") else None
DEFAULT_DUMP = Path(os.environ.get("CK3_DUMP", "")) if os.environ.get("CK3_DUMP") else None
GAME = DEFAULT_GAME or Path(".")
DUMP = DEFAULT_DUMP or Path("gamestate.json")


def require_game() -> Path:
    """Папка игры нужна для карты: без неё шаг не выполнить."""
    if not GAME or not (GAME / "map_data" / "provinces.png").exists():
        raise SystemExit(
            "Не найдена папка игры. Укажите её аргументом --game или переменной CK3_GAME,\n"
            "например: --game \"C:\\Steam\\steamapps\\common\\Crusader Kings III\\game\""
        )
    return GAME

KEY_OPEN = re.compile(r"^\s*([a-zA-Z0-9_.\-]+)\s*=\s*\{\s*$")
PROVINCE = re.compile(r"^\s*province\s*=\s*(\d+)")

TIER_RANK = {"Empire": 0, "Kingdom": 1, "Duchy": 2, "County": 3, "Barony": 4}


# ---------------------------------------------------------------- карта


def read_definition(path: Path) -> dict[int, dict]:
    provinces: dict[int, dict] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.strip().split(";")
            if len(parts) < 5 or not parts[0].isdigit():
                continue
            ident = int(parts[0])
            provinces[ident] = {
                "id": ident,
                "rgb": [int(parts[1]), int(parts[2]), int(parts[3])],
                "name": parts[4],
            }
    return provinces


def read_baronies(paths: list[Path]) -> dict[str, int]:
    """b_<key> = { province = N } — разбор с учётом вложенности блоков."""
    baronies: dict[str, int] = {}
    for path in paths:
        stack: list[str | None] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            opened = KEY_OPEN.match(line)
            if opened:
                stack.append(opened.group(1))
                continue
            if line.strip() == "{":
                stack.append(None)
                continue
            if line.strip().startswith("}"):
                for _ in range(line.count("}")):
                    if stack:
                        stack.pop()
                continue
            province = PROVINCE.match(line)
            if province and stack:
                owner = stack[-1]
                if owner and owner.startswith("b_"):
                    baronies.setdefault(owner, int(province.group(1)))
    return baronies


def build_map() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    provinces = read_definition(require_game() / "map_data" / "definition.csv")
    files = sorted((require_game() / "common" / "landed_titles").glob("*.txt"))
    baronies = read_baronies(files)
    payload = {
        "provinces": provinces,
        "baronies": baronies,
        "stats": {"provinces": len(provinces), "baronies": len(baronies)},
    }
    (CACHE / "map.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # Копия карты игры остаётся в проекте локально: дальше папка игры не нужна.
    # В репозиторий она не попадает (см. .gitignore) — это ассет Paradox.
    local_map = CACHE / "map_data"
    local_map.mkdir(parents=True, exist_ok=True)
    for name in ("provinces.png", "adjacencies.csv"):
        source = require_game() / "map_data" / name
        if source.exists():
            target = local_map / name
            if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
                target.write_bytes(source.read_bytes())
                print(f"карта: {name} скопирован в _cache/map_data")
    print(f"провинций {len(provinces)}, баронств {len(baronies)}")


def build_adjacency() -> None:
    """Соседство и центроиды провинций по provinces.png (только земля)."""
    import numpy as np
    from PIL import Image

    cache = json.loads((CACHE / "map.json").read_text(encoding="utf-8"))
    provinces = {int(k): v for k, v in cache["provinces"].items()}
    baronies = cache["baronies"]

    land_ids = {pid for pid in baronies.values() if pid in provinces}
    land_arr = np.array(sorted(land_ids), dtype=np.int64)
    print(f"земельных провинций: {len(land_ids)}")

    ids_sorted = np.array(sorted(provinces), dtype=np.int32)
    keys = np.array(
        [(provinces[pid]["rgb"][0] << 16) | (provinces[pid]["rgb"][1] << 8) | provinces[pid]["rgb"][2] for pid in ids_sorted],
        dtype=np.uint32,
    )
    order = np.argsort(keys)
    keys, ids_sorted = keys[order], ids_sorted[order]

    image = Image.open(require_game() / "map_data" / "provinces.png").convert("RGB")
    width, height = image.size

    pairs: set[tuple[int, int]] = set()
    sum_x = np.zeros(20000, dtype=np.float64)
    sum_y = np.zeros(20000, dtype=np.float64)
    count = np.zeros(20000, dtype=np.int64)

    strip = 128
    for top in range(0, height, strip):
        bottom = min(top + strip, height)
        block = np.asarray(image.crop((0, top, width, bottom)), dtype=np.uint16)
        r = block[:, :, 0].astype(np.uint32)
        g = block[:, :, 1].astype(np.uint32)
        b = block[:, :, 2].astype(np.uint32)
        flat = ((r << 16) | (g << 8) | b).ravel()
        pos = np.clip(np.searchsorted(keys, flat), 0, len(keys) - 1)
        ids_flat = np.where(keys[pos] == flat, ids_sorted[pos], 0).astype(np.int32).reshape(block.shape[:2])

        rows = np.repeat(np.arange(top, bottom), width).reshape(block.shape[:2])
        cols = np.tile(np.arange(width), (bottom - top, 1))
        mask = ids_flat > 0
        idx = ids_flat[mask]
        count += np.bincount(idx, minlength=20000)[:20000]
        sum_x += np.bincount(idx, weights=cols[mask], minlength=20000)[:20000]
        sum_y += np.bincount(idx, weights=rows[mask], minlength=20000)[:20000]

        for a, bside in ((ids_flat[:, :-1], ids_flat[:, 1:]), (ids_flat[:-1, :], ids_flat[1:, :])):
            diff = a != bside
            if not diff.any():
                continue
            left = a[diff].astype(np.int64)
            right = bside[diff].astype(np.int64)
            ok = (left > 0) & (right > 0)
            if not ok.any():
                continue
            left, right = left[ok], right[ok]
            low = np.minimum(left, right)
            high = np.maximum(left, right)
            land_mask = np.isin(low, land_arr) & np.isin(high, land_arr)
            if not land_mask.any():
                continue
            codes = np.unique(low[land_mask] * 20000 + high[land_mask])
            for code in codes.tolist():
                pairs.add((code // 20000, code % 20000))

    centroids = {}
    for pid in land_ids:
        if count[pid] > 0:
            centroids[pid] = [round(float(sum_x[pid] / count[pid]), 1), round(float(sum_y[pid] / count[pid]), 1)]

    (CACHE / "adjacency.json").write_text(json.dumps(sorted(pairs)), encoding="utf-8")
    (CACHE / "centroids.json").write_text(json.dumps(centroids), encoding="utf-8")
    print(f"соседств {len(pairs)}, центроидов {len(centroids)}")


# ---------------------------------------------------------------- державы


def build_realms(dump: Path) -> None:
    import ijson

    cache = json.loads((CACHE / "map.json").read_text(encoding="utf-8"))
    baronies = cache["baronies"]
    centroids = {int(k): v for k, v in json.loads((CACHE / "centroids.json").read_text(encoding="utf-8")).items()}

    titles: dict[int, dict] = {}
    characters: dict[int, dict] = {}

    print("читаю титулы…", flush=True)
    with dump.open("rb") as handle:
        for ident, tile in ijson.kvitems(handle, "titles", use_float=False):
            capital = tile.get("capital") or {}
            vassals = [v.get("id") for v in (tile.get("de_jure_vassals") or []) if v]
            titles[int(ident)] = {
                "id": int(ident),
                "key": tile.get("key"),
                "name": tile.get("name"),
                "tier": tile.get("tier"),
                "capital": capital.get("id"),
                "holder": (tile.get("de_facto") or {}).get("id"),
                "vassals": vassals,
                "history": [
                    [e[0], (e[1] or {}).get("id"), e[2]]
                    for e in (tile.get("history") or [])
                    if isinstance(e, list) and len(e) >= 3
                ],
            }

    print(f"титулов {len(titles)}; читаю персонажей…", flush=True)
    with dump.open("rb") as handle:
        for ident, char in ijson.kvitems(handle, "characters", use_float=False):
            cid = int(ident)
            house = char.get("house") or {}
            liege = char.get("liege") or {}
            characters[cid] = {
                "id": cid,
                "name": char.get("name") or "",
                "nick": char.get("nick") or "",
                "female": bool(char.get("female")),
                "birth": char.get("birth"),
                "death": char.get("date") if char.get("dead") else None,
                "house": house.get("id"),
                "house_name": house.get("name"),
                "liege": liege.get("id"),
                "titles": [(t or {}).get("id") for t in (char.get("titles") or []) if (t or {}).get("id")],
            }
    print(f"персонажей {len(characters)}", flush=True)

    def holder_at(title_id: int, date: str = "0923-12-31") -> int | None:
        tile = titles.get(title_id)
        if not tile:
            return None
        best = None
        for when, who, _action in tile["history"]:
            if isinstance(when, str) and when <= date:
                best = who
        return best or tile["holder"]

    def top_liege(cid: int | None) -> int | None:
        seen = set()
        while cid and cid not in seen:
            seen.add(cid)
            nxt = characters.get(cid, {}).get("liege")
            if not nxt or nxt not in characters:
                return cid
            cid = nxt
        return cid

    province_cache: dict[int, list[int]] = {}

    def provinces_of(title_id: int | None, depth: int = 0) -> list[int]:
        if not title_id or depth > 4:
            return []
        if title_id in province_cache:
            return province_cache[title_id]
        tile = titles.get(title_id)
        result: list[int] = []
        if tile:
            if tile["tier"] == "Barony":
                prov = baronies.get(tile.get("key") or "")
                result = [prov] if prov else []
            else:
                for vid in tile["vassals"]:
                    vassal = titles.get(vid)
                    if not vassal:
                        continue
                    if vassal["tier"] == "Barony":
                        prov = baronies.get(vassal.get("key") or "")
                        if prov:
                            result.append(prov)
                    else:
                        result.extend(provinces_of(vid, depth + 1))
        province_cache[title_id] = result
        return result

    def capital_province(title_id: int | None) -> int | None:
        """Столица титула: его capital → графство/баронство → провинция."""
        seen = set()
        current = title_id
        while current and current not in seen:
            seen.add(current)
            tile = titles.get(current)
            if not tile:
                return None
            if tile["tier"] == "Barony":
                return baronies.get(tile.get("key") or "")
            capital = tile.get("capital")
            if capital and capital in titles:
                capital_tier = titles[capital]["tier"]
                if capital_tier == "Barony":
                    return baronies.get(titles[capital].get("key") or "")
                own = provinces_of(capital)
                if own:
                    return own[0]
                current = capital
                continue
            own = provinces_of(current)
            return own[0] if own else None
        return None

    realms: dict[int, dict] = {}
    province_realm: dict[int, int] = {}
    for tile in titles.values():
        if tile["tier"] != "County":
            continue
        holder = holder_at(tile["id"])
        if not holder:
            continue
        realm_id = top_liege(holder)
        if not realm_id:
            continue
        provinces = provinces_of(tile["id"])
        realm = realms.setdefault(realm_id, {"id": realm_id, "counties": [], "provinces": []})
        realm["counties"].append(tile["id"])
        for prov in provinces:
            if prov in centroids:
                province_realm[prov] = realm_id
                realm["provinces"].append(prov)

    for realm_id, realm in realms.items():
        ruler = characters.get(realm_id, {})
        own = sorted(
            (titles[t] for t in ruler.get("titles", []) if t in titles),
            key=lambda t: TIER_RANK.get(t["tier"], 9),
        )
        best = own[0] if own else None
        realm["ruler"] = ruler.get("name")
        realm["house"] = ruler.get("house_name")
        realm["title"] = best["name"] if best else None
        realm["tier"] = best["tier"] if best else None
        province = capital_province(best["id"]) if best else None
        realm["capital"] = province
        realm["xy"] = centroids.get(province) if province else None
        realm["history"] = [
            [e[0], e[1], e[2], (characters.get(e[1]) or {}).get("name")]
            for e in (best["history"] if best else [])
            if isinstance(e[0], str) and e[0] >= "0880"
        ][-6:]

    payload = {
        "realms": {str(k): v for k, v in realms.items()},
        "province_realm": {str(k): v for k, v in province_realm.items()},
    }
    (CACHE / "realms.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def best_title(cid: int) -> dict | None:
        own = [titles[t] for t in characters.get(cid, {}).get("titles", []) if t in titles]
        own.sort(key=lambda t: TIER_RANK.get(t["tier"], 9))
        return own[0] if own else None

    rulers = {}
    for realm_id in realms:
        person = characters.get(realm_id, {})
        title = best_title(realm_id)
        rulers[str(realm_id)] = {
            "name": person.get("name"),
            "nick": person.get("nick"),
            "female": person.get("female"),
            "birth": person.get("birth"),
            "death": person.get("death"),
            "house": person.get("house_name"),
            "title": title["name"] if title else None,
            "tier": title["tier"] if title else None,
        }
    (CACHE / "rulers.json").write_text(json.dumps(rulers, ensure_ascii=False), encoding="utf-8")

    player_id = 47148
    with dump.open("rb") as handle:
        players = next(ijson.items(handle, "players", use_float=False), None) or []
    if players:
        player_id = players[0].get("character") or player_id
    player = characters.get(player_id, {})
    house_id = player.get("house")
    kin = []
    for person in characters.values():
        if person.get("house") != house_id or person.get("id") == player_id:
            continue
        title = best_title(person["id"])
        kin.append(
            {
                "id": person["id"],
                "name": person["name"],
                "female": person["female"],
                "birth": person["birth"],
                "death": person["death"],
                "title": title["name"] if title else None,
            }
        )
    vassals = []
    for person in characters.values():
        if person.get("liege") != player_id:
            continue
        title = best_title(person["id"])
        vassals.append(
            {
                "id": person["id"],
                "name": person["name"],
                "title": title["name"] if title else None,
                "tier": title["tier"] if title else None,
            }
        )
    court = {
        "player": {
            "id": player_id,
            "name": player.get("name"),
            "nick": player.get("nick"),
            "birth": player.get("birth"),
            "house": player.get("house_name"),
            "title": (best_title(player_id) or {}).get("name"),
            "realm": top_liege(player_id),
            "province": capital_province((best_title(player_id) or {}).get("id")),
        },
        "vassals": vassals,
        "kin": kin,
    }
    (CACHE / "court.json").write_text(json.dumps(court, ensure_ascii=False), encoding="utf-8")
    print(f"род: {len(kin)}, прямых вассалов: {len(vassals)}")
    with_capital = sum(1 for r in realms.values() if r.get("xy"))
    print(f"держав {len(realms)}, со столицей {with_capital}, провинций размечено {len(province_realm)}")


def read_straits() -> list[tuple[int, int]]:
    """Проливы и речные переправы из adjacencies.csv — без них острова выпадают."""
    path = require_game() / "map_data" / "adjacencies.csv"
    pairs: list[tuple[int, int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(";")
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        kind = parts[2].strip().lower()
        if kind not in ("sea", "river_large", "river_small", "lake"):
            continue
        pairs.append((int(parts[0]), int(parts[1])))
    return pairs


def build_rings() -> None:
    """Кольца знания от державы игрока + расстояния до столиц."""
    import math

    realms = json.loads((CACHE / "realms.json").read_text(encoding="utf-8"))
    centroid = {int(k): v for k, v in json.loads((CACHE / "centroids.json").read_text(encoding="utf-8")).items()}
    adjacency = json.loads((CACHE / "adjacency.json").read_text(encoding="utf-8"))
    rulers = json.loads((CACHE / "rulers.json").read_text(encoding="utf-8"))
    court = json.loads((CACHE / "court.json").read_text(encoding="utf-8"))

    realm_map = {int(k): v for k, v in realms["realms"].items()}
    province_realm = {int(k): v for k, v in realms["province_realm"].items()}

    player_id = court["player"]["id"]
    player_realm = court["player"].get("realm")
    if player_realm not in realm_map:
        player_realm = None

    # Якоря рода: провинции своей державы или, если земли нет, — стоянка лагеря.
    anchors: set[int] = set()
    if player_realm is not None:
        anchors = set(realm_map[player_realm].get("provinces") or [])
    camp = court["player"].get("province")
    if not anchors and camp:
        anchors = {camp}
    if not anchors:
        raise SystemExit("не нашёл ни державы, ни стоянки игрока")
    print(f"держава игрока: {player_realm or 'безземельный'} | провинций-якорей: {len(anchors)}")

    # --- граф соседства держав ------------------------------------------
    graph: dict[int, set[int]] = {}

    def link(pid_a: int, pid_b: int) -> None:
        ra, rb = province_realm.get(pid_a), province_realm.get(pid_b)
        if not ra or not rb or ra == rb:
            return
        graph.setdefault(ra, set()).add(rb)
        graph.setdefault(rb, set()).add(ra)

    for a, b in adjacency:
        link(a, b)
    for a, b in read_straits():
        link(a, b)

    # --- кольца ----------------------------------------------------------
    rings: dict[int, int] = {}
    # своё: державы, владеющие якорными провинциями (только если у рода есть земля)
    if player_realm is not None:
        for prov in anchors:
            realm = province_realm.get(prov)
            if realm:
                rings[realm] = 0
    # соседи: державы, чьи провинции касаются якорных
    neighbours: set[int] = set()
    for a, b in list(adjacency) + list(read_straits()):
        for x, y in ((a, b), (b, a)):
            if x in anchors:
                realm = province_realm.get(y)
                if realm and realm not in rings:
                    neighbours.add(realm)
    for realm in neighbours:
        rings[realm] = 1

    frontier = list(neighbours)
    while frontier:
        nxt = []
        for node in frontier:
            for other in graph.get(node, ()):
                if other not in rings:
                    rings[other] = rings[node] + 1
                    nxt.append(other)
        frontier = nxt

    base = None
    points = [centroid[p] for p in anchors if p in centroid]
    if points:
        base = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))

    def distance(realm: dict) -> float | None:
        if not base or not realm.get("xy"):
            return None
        return math.hypot(realm["xy"][0] - base[0], realm["xy"][1] - base[1])

    def direction(realm: dict) -> str:
        if not base or not realm.get("xy"):
            return ""
        dx = realm["xy"][0] - base[0]
        dy = realm["xy"][1] - base[1]
        angle = math.degrees(math.atan2(-dy, dx)) % 360
        names = ["восток", "северо-восток", "север", "северо-запад", "запад", "юго-запад", "юг", "юго-восток"]
        return names[int((angle + 22.5) // 45) % 8]

    def geo_ring(dist: float | None) -> int | None:
        """Геометрическое кольцо: то же расстояние, но в шагах знания."""
        if dist is None:
            return None
        if dist < 150:
            return 1
        if dist < 350:
            return 2
        if dist < 700:
            return 3
        return 4

    rows = []
    for rid, realm in realm_map.items():
        if rid == player_realm:
            continue
        political = rings.get(rid)
        ruler = rulers.get(str(rid), {})
        dist = distance(realm)
        geo = geo_ring(dist)
        if political is None and geo is None:
            continue
        rows.append(
            {
                "realm": rid,
                "political": political,
                "geo": geo,
                # если по суше не дойти — остаётся море, считаем по расстоянию
                "by_sea": political is None,
                "ring": min(political, geo) if political and geo else (political or geo),
                "distance": round(dist) if dist is not None else -1,
                "direction": direction(realm),
                "title": realm.get("title"),
                "tier": realm.get("tier"),
                "ruler": ruler.get("name"),
                "nick": ruler.get("nick"),
                "house": ruler.get("house"),
                "birth": ruler.get("birth"),
                "death": ruler.get("death"),
                "size": len(realm.get("counties") or []),
                "history": realm.get("history") or [],
            }
        )
    rows.sort(key=lambda r: (r["ring"], r["distance"] if r["distance"] >= 0 else 10**9))

    by_ring = {}
    for row in rows:
        by_ring[row["ring"]] = by_ring.get(row["ring"], 0) + 1

    payload = {
        "player_realm": player_realm,
        "rings": rings,
        "realm_ring": {str(row["realm"]): row["ring"] for row in rows},
        "rows": rows,
        "by_ring": by_ring,
    }
    (CACHE / "rings.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("дворов по кольцам:", dict(sorted(by_ring.items())))
    for row in rows[:20]:
        print(
            f"  {row['ring']}  {row['distance']:>5} px  {row['direction']:<12} {row['title'] or '—':<28} {row['ruler'] or '—'}"
        )


def age_of(birth: str | None, date: str = "0894-11-04") -> int | None:
    if not birth or len(str(birth)) < 4:
        return None
    try:
        delta = int(str(date)[:4]) - int(str(birth)[:4])
    except ValueError:
        return None
    return delta if 0 <= delta <= 110 else None


def year_plain(date: str | None) -> str:
    """0882 → 882: ведущие нули в летописи ни к чему."""
    if not date:
        return "—"
    try:
        return str(int(str(date)[:4]))
    except ValueError:
        return str(date)


def years_ru(n: int) -> str:
    tail, last = n % 100, n % 10
    if 11 <= tail <= 14:
        return f"{n} лет"
    if last == 1:
        return f"{n} год"
    if 2 <= last <= 4:
        return f"{n} года"
    return f"{n} лет"


def clean_house(name: str | None) -> str:
    """В дампе есть служебные имена вроде House british isles ivaring — их не показываем."""
    if not name or name.startswith("House "):
        return ""
    return name


RING_LABEL = {0: "своё", 1: "ближний", 2: "средний", 3: "дальний", 4: "молва"}


def known_line(row: dict) -> str:
    """Что род знает о дворе — по кольцу."""
    ring = row["ring"]
    name = row.get("ruler") or ""
    nick = row.get("nick") or ""
    house = clean_house(row.get("house"))
    title = row.get("title") or "двор без имени"
    age = age_of(row.get("birth"))
    if ring <= 1:
        parts = [f"{name}{(' ' + nick) if nick else ''}"]
        if house:
            parts.append(f"дом {house}")
        parts.append(title)
        if age:
            parts.append(years_ru(age))
        return ", ".join(parts)
    if ring == 2:
        return f"{name}, {title}"
    if ring == 3:
        return f"{title}, государь не назван"
    return f"на {row.get('direction') or 'стороне'} — чужой государь"


def true_line(row: dict) -> str:
    name = row.get("ruler") or "—"
    nick = row.get("nick") or ""
    house = clean_house(row.get("house"))
    birth = year_plain(row.get("birth"))
    death = year_plain(row.get("death")) if row.get("death") else "жив"
    tail = f"{birth} — {death}"
    return f"{name}{(' ' + nick) if nick else ''}" + (f", дом {house}" if house else "") + f", {tail}, владений {row.get('size')}"


def build_report() -> None:
    import datetime

    rings = json.loads((CACHE / "rings.json").read_text(encoding="utf-8"))
    court = json.loads((CACHE / "court.json").read_text(encoding="utf-8"))
    rows = rings["rows"]
    by_ring = rings["by_ring"]
    player = court["player"]

    sample = [r for r in rows if r["ring"] <= 3][:20]

    lines = []
    lines.append("# Пилот: радиус знания рода")
    lines.append("")
    lines.append(f"Сейв: **Король Лохине, Ирландская конфедерация, 4 ноября 894**. Род: **О’Мэлли**, двор: **{player.get('title') or '—'}**.")
    lines.append("")
    lines.append("Считано по дампу экстрактора: графства → держатели → верхний сюзерен → границы по провинциям → кольца и расстояния.")
    lines.append("")
    lines.append("## Своё (кольцо 0)")
    lines.append("")
    lines.append(f"**{player.get('name')} {player.get('nick') or ''}**, дом {player.get('house')}, {player.get('title')}.")
    lines.append("")
    vassals = [v for v in court["vassals"] if v.get("title")]
    lines.append(f"Прямых вассалов с титулами: {len(vassals)} — " + ", ".join(f"{v['name']} ({v['title']})" for v in vassals) + ".")
    kin = [k for k in court["kin"] if k.get("title")]
    if kin:
        lines.append("")
        lines.append("Родичи с владениями: " + ", ".join(f"{k['name']} ({k['title']})" for k in kin) + ".")
    lines.append("")
    lines.append("## Дворы в поле зрения")
    lines.append("")
    lines.append("Кольцо — сколько шагов от рода до двора: своё, сосед, сосед соседа, дальше. Итоговое кольцо — минимум из политического (по границам) и географического (по расстоянию).")
    lines.append("")
    lines.append("| Кольцо | Расстояние | Направление | Что знает род | Что было на самом деле |")
    lines.append("|---|---|---|---|---|")
    for row in sample:
        mark = "" if not row.get("by_sea") else "*"
        lines.append(
            f"| {row['ring']} — {RING_LABEL[row['ring']]} | {row['distance']} px{mark} | {row['direction']} | {known_line(row)} | {true_line(row)} |"
        )
    lines.append("")
    lines.append("Звёздочкой помечены дворы, до которых нет сухопутного пути: кольцо считается по морскому расстоянию.")
    lines.append("")
    lines.append("## Распределение")
    lines.append("")
    lines.append("| Кольцо | Дворов |")
    lines.append("|---|---|")
    for ring in sorted(by_ring):
        lines.append(f"| {ring} — {RING_LABEL.get(int(ring), '?')} | {by_ring[ring]} |")
    lines.append("")
    lines.append("## Три регистра")
    lines.append("")

    def first_event(ring: int) -> tuple[dict, list] | tuple[None, None]:
        best = (None, None)
        for row in rows:
            if row["ring"] != ring:
                continue
            for event in row.get("history") or []:
                if len(event) >= 4 and event[3]:
                    if best[1] is None or str(event[0]) > str(best[1][0]):
                        best = (row, event)
        return best

    def event_text(row: dict, event: list, register: str) -> str:
        date, _holder, action, name = event[0], event[1], event[2], event[3]
        year = year_plain(date)
        title = row.get("title") or "тамошнее королевство"
        house = clean_house(row.get("house"))
        age = age_of(row.get("birth"), date)
        tail = (f", дом {house}" if house else "") + (f", {years_ru(age)}" if age is not None else "")
        if action in ("Inherited", "inherited"):
            if register == "close":
                return f"{year} год. {title}: власть принял {name}{tail}. Сказывали, что прежний государь умер своей смертью."
            if register == "middle":
                return f"{title}: сменился государь — ныне там {name}. Года не запомнили."
            return f"{title}: сменился государь; имени не называли."
        if action in ("conquest_populist", "conquest", "conquest_claim"):
            if register == "close":
                return f"{year} год. {title} взяли силой: {name} поставил себя над ним."
            if register == "middle":
                return f"{title} перешёл под руку {name} — говорили, без большого кровопролития."
            return "На границах слышали о войне, но за что и кто — не разобрать."
        if action in ("created", "Created"):
            return f"{year} год. Учреждён титул {title}."
        if action in ("independency",):
            return f"{title} вышел из подчинения — так дошло до нас."
        return f"{title} — новые вести."

    focus = [(1, "Ближний двор (кольцо 1)", "close"), (2, "Средний двор (кольцо 2)", "middle"), (3, "Дальний двор (кольцо 3)", "far")]
    for ring, heading, register in focus:
        row, event = first_event(ring)
        lines.append(f"### {heading}")
        lines.append("")
        if row and event:
            lines.append(event_text(row, event, register))
            lines.append("")
            lines.append(f"*Что было на самом деле:* {true_line(row)}; событие — {event[0]}, {event[2]}.")
        else:
            lines.append("Нет события для примера.")
        lines.append("")
    lines.append("## Что показал пилот")
    lines.append("")
    lines.append("1. Политические кольца без моря врут: Уэльс в 248 px от Манстера оказывался дальше Лотиана в 418 px. Гибрид лечит это правилом «итоговое кольцо = минимум из политического и географического».")
    lines.append("2. Европа и Британия — разные компоненты связности: сухопутный граф обрывается на проливах. Без морского правила континент вообще выпадает из поля зрения.")
    lines.append("3. Порог расстояния (150 / 350 / 700 px) — грубый; его надо калибровать по игровым единицам (`MAXIMUM_DIPLOMATIC_RANGE = 1000`).")
    lines.append("4. Кольцо ещё не учитывает давность и каналы (брак, война, служба) — это следующий слой.")
    lines.append("5. На сейве 923 (текущая игра) правитель безземельный — у лагеря нет границ, поэтому политических колец там не будет вообще: только расстояние. Это отдельный случай, который надо описать явно.")
    lines.append("6. Из 767 держав в кольцах 1–3 оказались 19, остальные 747 — молва. Мир за пределами соседей почти невидим, и это правильная картина, а не баг.")
    lines.append("")

    out = ROOT / "chronicle_examples" / "пилот-894-манстер.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    meta = ROOT / "saves_meta" / "пилот-894-манстер.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(
        json.dumps({"generated": datetime.datetime.now().isoformat(timespec="minutes"), "player": player, "by_ring": by_ring, "rows": sample}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"→ {out}")
    print(f"→ {meta}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Карта и державы для «радиуса знания».",
        epilog="Папку игры и дамп можно задать переменными CK3_GAME и CK3_DUMP.",
    )
    parser.add_argument("step", choices=["map", "adjacency", "realms", "rings", "report"])
    parser.add_argument("--dump", type=Path, default=DUMP, help="дамп gamestate.json")
    parser.add_argument("--game", type=Path, default=GAME, help="папка game игры Crusader Kings III")
    args = parser.parse_args()
    globals()["GAME"] = args.game
    if args.step in ("map", "adjacency") and not args.dump.exists():
        pass  # дамп этим шагам не нужен
    if args.step in ("realms", "rings", "report") and not args.dump.exists():
        raise SystemExit(f"Не найден дамп: {args.dump}. Укажите --dump или переменную CK3_DUMP.")

    if args.step == "map":
        build_map()
    elif args.step == "adjacency":
        build_adjacency()
    elif args.step == "realms":
        build_realms(args.dump)
    elif args.step == "rings":
        build_rings()
    else:
        build_report()


if __name__ == "__main__":
    main()
