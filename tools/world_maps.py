"""Карты и выгрузки мира: политическая линза, дома, карта знания, CSV.

Выделено из `build_world.py`, чтобы сборка мира не смешивалась с рисованием.
Всё, что здесь есть, работает на numpy и Pillow; в сборке это необязательная часть —
без папки игры мир собирается, а карты просто не рисуются.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = ROOT / "_cache"

# --- общие константы карт (одна палитра на все линзы) ---
MAP_PAPER = (239, 233, 219)
MAP_SEA = (221, 216, 202)
MAP_INK = {0: (25, 23, 19), 1: (52, 47, 39), 2: (86, 79, 65), 3: (124, 115, 96), 4: (156, 146, 124)}
HOUSE_TONES = [
    (47, 74, 107),
    (107, 127, 58),
    (138, 90, 43),
    (92, 63, 102),
    (47, 107, 99),
    (122, 62, 62),
]


def mix_with_paper(color: tuple[int, int, int], strength: float) -> tuple[int, int, int]:
    """Подмешивает бумагу: заливка не должна спорить с тушью."""
    return tuple(int(MAP_PAPER[i] * (1 - strength) + color[i] * strength) for i in range(3))


def province_assets(numpy):
    """Провинции и отсортированные ключи для поиска цвета пикселя."""
    map_cache = json.loads((CACHE / "map.json").read_text(encoding="utf-8"))
    provinces = {int(k): v for k, v in map_cache["provinces"].items()}
    keys = numpy.array(
        [(p["rgb"][0] << 16) | (p["rgb"][1] << 8) | p["rgb"][2] for p in provinces.values()],
        dtype=numpy.uint32,
    )
    ids = numpy.array(list(provinces.keys()), dtype=numpy.int32)
    order = numpy.argsort(keys)
    return provinces, keys[order], ids[order]


def province_pixels(image, keys, ids, step, max_prov, numpy):
    """Карта номеров провинций по пикселям изображения."""
    small = numpy.asarray(image.resize((max(1, image.size[0] // step), max(1, image.size[1] // step)), 0), dtype=numpy.uint16)
    r = small[:, :, 0].astype(numpy.uint32)
    g = small[:, :, 1].astype(numpy.uint32)
    b = small[:, :, 2].astype(numpy.uint32)
    flat = ((r << 16) | (g << 8) | b).ravel()
    pos = numpy.clip(numpy.searchsorted(keys, flat), 0, len(keys) - 1)
    prov = numpy.where(keys[pos] == flat, ids[pos], 0).astype(numpy.int32).reshape(small.shape[:2])
    return numpy.clip(prov, 0, max_prov)


def draw_coast_and_borders(canvas, prov, realm_px, ring_px, numpy):
    """Берег — тушью, рубежи держав — по кольцу знания."""
    coast = numpy.zeros(prov.shape, dtype=bool)
    coast[:, :-1] |= (prov[:, :-1] > 0) & (prov[:, 1:] == 0)
    coast[:, 1:] |= (prov[:, 1:] > 0) & (prov[:, :-1] == 0)
    coast[:-1, :] |= (prov[:-1, :] > 0) & (prov[1:, :] == 0)
    coast[1:, :] |= (prov[1:, :] > 0) & (prov[:-1, :] == 0)
    canvas[coast] = (52, 46, 37)

    edge_h = numpy.zeros(realm_px.shape, dtype=bool)
    edge_v = numpy.zeros(realm_px.shape, dtype=bool)
    edge_h[:, :-1] = (realm_px[:, :-1] != realm_px[:, 1:]) & (realm_px[:, :-1] > 0) & (realm_px[:, 1:] > 0)
    edge_v[:-1, :] = (realm_px[:-1, :] != realm_px[1:, :]) & (realm_px[:-1, :] > 0) & (realm_px[1:, :] > 0)
    ring_h = numpy.zeros(realm_px.shape, dtype=numpy.int16)
    ring_v = numpy.zeros(realm_px.shape, dtype=numpy.int16)
    ring_h[:, :-1] = numpy.minimum(ring_px[:, :-1], ring_px[:, 1:])
    ring_v[:-1, :] = numpy.minimum(ring_px[:-1, :], ring_px[1:, :])
    for mask, ringmap in ((edge_h, ring_h), (edge_v, ring_v)):
        for value, color in MAP_INK.items():
            canvas[mask & (ringmap == value)] = color


def realm_index_pixels(realms, province_realm, prov, max_prov, numpy):
    """Плотные индексы держав вместо больших номеров персонажей."""
    known = sorted(realms)
    realm_index = {rid: i + 1 for i, rid in enumerate(known)}
    rid_arr = numpy.zeros(max_prov + 1, dtype=numpy.int64)
    for pid, rid in province_realm.items():
        if 0 <= pid <= max_prov:
            rid_arr[pid] = rid
    rid_px = rid_arr[prov]
    known_rids = numpy.array(known, dtype=numpy.int64)
    known_vals = numpy.array([realm_index[r] for r in known], dtype=numpy.int32)
    pos = numpy.clip(numpy.searchsorted(known_rids, rid_px), 0, max(len(known_rids) - 1, 0))
    hit = known_rids[pos] == rid_px
    return realm_index, numpy.where(hit, known_vals[pos], 0).astype(numpy.int32)


def export_csv(payload: dict) -> None:
    """Три таблицы корпуса: события, персоны, державы. Excel открывает utf-8-sig без пляски."""
    import csv

    out = ROOT / "_export"
    out.mkdir(parents=True, exist_ok=True)
    names = payload.get("names", {})
    people = {str(p["id"]): p for p in payload.get("people", [])}

    def who_name(cid) -> str:
        if not cid:
            return ""
        person = people.get(str(cid)) or names.get(str(cid)) or {}
        return str(person.get("name") or "")

    with (out / "events.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["date", "year", "kind", "grade", "ring", "realm", "title", "who", "who2", "type", "kin", "repeat"])
        for event in payload.get("events", []):
            writer.writerow(
                [
                    event.get("date"),
                    str(event.get("date") or "")[:4],
                    event.get("kind"),
                    event.get("grade"),
                    event.get("ring"),
                    event.get("realm") or "",
                    event.get("title") or "",
                    who_name(event.get("who")),
                    who_name(event.get("who2")),
                    event.get("type") or "",
                    "1" if event.get("kin") else "",
                    event.get("repeat") or 0,
                ]
            )

    with (out / "persons.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id", "name", "nick", "house", "kin", "gen", "birth", "death", "titles", "traits", "prestige"])
        for person in payload.get("people", []):
            writer.writerow(
                [
                    person.get("id"),
                    person.get("name"),
                    person.get("nick") or "",
                    person.get("house") or "",
                    "1" if person.get("kin") else "",
                    person.get("gen"),
                    person.get("birth") or "",
                    person.get("death") or "",
                    ", ".join(person.get("titles") or []),
                    ", ".join(person.get("traits") or []),
                    person.get("prestige") or 0,
                ]
            )

    with (out / "realms.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["name", "tier", "ring", "political", "geo", "distance", "direction", "size", "ruler", "house", "faith", "faith_share", "culture", "culture_share"])
        for realm in payload.get("realms", []):
            writer.writerow(
                [
                    realm.get("name"),
                    realm.get("tier") or "",
                    realm.get("ring"),
                    realm.get("political") or "",
                    realm.get("geo") or "",
                    realm.get("distance") or "",
                    realm.get("direction") or "",
                    realm.get("size") or 0,
                    realm.get("ruler") or "",
                    realm.get("house") or "",
                    realm.get("faith") or "",
                    realm.get("faithShare") or "",
                    realm.get("culture") or "",
                    realm.get("cultureShare") or "",
                ]
            )

    print(f"таблицы: {out} (events, persons, realms)")


def render_political(out: Path, family_lands: dict[int, tuple[str, str]], realms: dict[int, dict],
                     province_realm: dict[int, int], image, width: int, height: int, centroids,
                     player_house: str | None, house_roles: dict[str, str] | None = None) -> dict | None:
    """Политическая линза: кадр вокруг земель рода, заливка по домам, чужие державы — границами.

    Кадр обрезан по владениям родичей с запасом: на карте мира род занимает угол, и
    разглядеть, кто где сидит, невозможно. Для обрезанной карты сохраняется своя карта
    индексов, иначе наведение мыши показывало бы не тот двор.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    if not family_lands:
        return None

    provinces, keys, ids = province_assets(np)

    paper = np.array(MAP_PAPER, dtype=np.uint8)
    sea = np.array(MAP_SEA, dtype=np.uint8)
    accent = (160, 44, 28)
    # Разные дома — разные тона: индиго, олива, охра, слива, бирюза. Не сепия на сепии.
    hues = [(47, 74, 107), (107, 127, 58), (138, 90, 43), (92, 63, 102), (47, 107, 99), (122, 62, 62)]
    quiet = {0: (25, 23, 19), 1: (74, 67, 53), 2: (138, 127, 104), 3: (176, 166, 144), 4: (201, 193, 172)}

    house_roles = house_roles or {}
    houses = sorted({house for house, _ruler in family_lands.values() if house})

    def house_weight(house: str) -> tuple[int, int]:
        role = house_roles.get(house, "")
        rank = 0 if role == "player" else 1 if role == "senior" else 2
        owned = sum(1 for hh, _r in family_lands.values() if hh == house)
        return rank, -owned

    house_color: dict[str, tuple[int, int, int]] = {}
    tint = 0
    for house in sorted(houses, key=house_weight):
        role = house_roles.get(house, "")
        if role == "player":
            house_color[house] = accent
        else:
            house_color[house] = hues[tint % len(hues)]
            tint += 1

    # Кадр вокруг владений рода.
    points = [centroids.get(pid) for pid in family_lands if centroids.get(pid)]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 * 1.5 + 620
    left = int(max(0, min(width - 200, cx - half)))
    right = int(max(left + 200, min(width, cx + half)))
    top = int(max(0, min(height - 200, cy - half)))
    bottom = int(max(top + 200, min(height, cy + half)))

    step = 1                                  # кадр в полном разрешении: номера должны читаться
    crop = image.crop((left, top, right, bottom))
    cw, ch = crop.size
    small = np.asarray(crop.resize((max(1, cw // step), max(1, ch // step)), Image.NEAREST), dtype=np.uint16)

    max_prov = max(provinces)
    fam_arr = np.zeros(max_prov + 1, dtype=np.int8)
    house_index = {house: i + 1 for i, house in enumerate(house_color)}
    for pid, (house, _ruler) in family_lands.items():
        if 0 <= pid <= max_prov and house in house_index:
            fam_arr[pid] = house_index[house]

    realm_index = {rid: i + 1 for i, rid in enumerate(sorted(realms))}
    rid_arr = np.zeros(max_prov + 1, dtype=np.int64)
    for pid, rid in province_realm.items():
        if 0 <= pid <= max_prov:
            rid_arr[pid] = rid

    r = small[:, :, 0].astype(np.uint32)
    g = small[:, :, 1].astype(np.uint32)
    b = small[:, :, 2].astype(np.uint32)
    flat = ((r << 16) | (g << 8) | b).ravel()
    pos = np.clip(np.searchsorted(keys, flat), 0, len(keys) - 1)
    prov = np.where(keys[pos] == flat, ids[pos], 0).astype(np.int32).reshape(small.shape[:2])
    prov = np.clip(prov, 0, max_prov)

    known_rids = np.array(sorted(realm_index), dtype=np.int64)
    known_vals = np.array([realm_index[x] for x in known_rids], dtype=np.int32)
    rid_px = rid_arr[prov]
    rid_pos = np.clip(np.searchsorted(known_rids, rid_px), 0, max(len(known_rids) - 1, 0))
    hit = known_rids[rid_pos] == rid_px
    realm_px = np.where(hit, known_vals[rid_pos], 0).astype(np.int32)

    tier_rank = {"County": 0, "Duchy": 1, "Kingdom": 2, "Empire": 3}
    tier_arr = np.zeros(len(realm_index) + 1, dtype=np.int16)
    ring_arr = np.full(len(realm_index) + 1, 4, dtype=np.int16)
    for rid, i in realm_index.items():
        realm = realms[rid]
        tier_arr[i] = tier_rank.get(realm.get("tier") or "", 0)
        ring_arr[i] = int(realm.get("ring", 4))

    canvas = np.zeros((prov.shape[0], prov.shape[1], 3), dtype=np.uint8)
    canvas[:] = paper
    canvas[prov == 0] = sea

    fam_px = fam_arr[prov]
    for house, color in house_color.items():
        canvas[fam_px == house_index[house]] = color

    # Рубежи: графства еле видны, герцогства светлее, королевства и империи — тушью.
    tier_px = tier_arr[realm_px]
    ring_px = ring_arr[realm_px]
    faint = np.array([212, 205, 189], dtype=np.uint8)
    duchy = np.array([196, 187, 168], dtype=np.uint8)

    edge_h = np.zeros(realm_px.shape, dtype=bool)
    edge_v = np.zeros(realm_px.shape, dtype=bool)
    edge_h[:, :-1] = (realm_px[:, :-1] != realm_px[:, 1:]) & (realm_px[:, :-1] > 0) & (realm_px[:, 1:] > 0)
    edge_v[:-1, :] = (realm_px[:-1, :] != realm_px[1:, :]) & (realm_px[:-1, :] > 0) & (realm_px[1:, :] > 0)

    class_h = np.zeros(realm_px.shape, dtype=np.int16)
    class_v = np.zeros(realm_px.shape, dtype=np.int16)
    class_h[:, :-1] = np.maximum(tier_px[:, :-1], tier_px[:, 1:])
    class_v[:-1, :] = np.maximum(tier_px[:-1, :], tier_px[1:, :])
    ring_h = np.zeros(realm_px.shape, dtype=np.int16)
    ring_v = np.zeros(realm_px.shape, dtype=np.int16)
    ring_h[:, :-1] = np.minimum(ring_px[:, :-1], ring_px[:, 1:])
    ring_v[:-1, :] = np.minimum(ring_px[:-1, :], ring_px[1:, :])

    for mask, klass, ringmap in ((edge_h, class_h, ring_h), (edge_v, class_v, ring_v)):
        canvas[mask & (klass == 0)] = faint
        canvas[mask & (klass == 1)] = duchy
        for ring, color in quiet.items():
            canvas[mask & (klass >= 2) & (ringmap == ring)] = color

    # Берег: силуэт суши, иначе кадр выглядит пустым листом.
    coast = np.zeros(prov.shape, dtype=bool)
    coast[:, :-1] |= (prov[:, :-1] > 0) & (prov[:, 1:] == 0)
    coast[:, 1:] |= (prov[:, 1:] > 0) & (prov[:, :-1] == 0)
    coast[:-1, :] |= (prov[:-1, :] > 0) & (prov[1:, :] == 0)
    coast[1:, :] |= (prov[1:, :] > 0) & (prov[:-1, :] == 0)
    canvas[coast] = (52, 46, 37)

    # Рубеж родовых земель — тушью, чтобы удел читался на чужом фоне.
    own_edge = np.zeros(fam_px.shape, dtype=bool)
    own_edge[:, :-1] |= (fam_px[:, :-1] > 0) & (fam_px[:, 1:] == 0)
    own_edge[:, 1:] |= (fam_px[:, 1:] > 0) & (fam_px[:, :-1] == 0)
    own_edge[:-1, :] |= (fam_px[:-1, :] > 0) & (fam_px[1:, :] == 0)
    own_edge[1:, :] |= (fam_px[1:, :] > 0) & (fam_px[:-1, :] == 0)
    canvas[own_edge] = (58, 50, 40)

    result = Image.fromarray(canvas).convert("RGB")
    draw = ImageDraw.Draw(result)
    from PIL import ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    try:
        house_font = ImageFont.truetype("arialbd.ttf", 26)
    except Exception:
        house_font = font

    rulers: dict[str, list[int]] = {}
    for pid, (_house, ruler) in family_lands.items():
        if ruler:
            rulers.setdefault(ruler, []).append(pid)

    legend = []
    placed_labels: list[tuple[float, float, float, float]] = []
    dot_boxes: list[tuple[float, float, float, float]] = []
    ordered_rulers = sorted(
        rulers.items(),
        key=lambda kv: (family_lands[kv[1][0]][0] != player_house, -len(kv[1])),
    )
    for number, (ruler, pids) in enumerate(ordered_rulers, start=1):
        house = family_lands[pids[0]][0]
        color = house_color.get(house, accent)
        pts = [centroids.get(pid) for pid in pids]
        pts = [((p[0] - left) / step, (p[1] - top) / step) for p in pts if p]
        if pts:
            px = sum(p[0] for p in pts) / len(pts)
            py = sum(p[1] for p in pts) / len(pts)
            dot_boxes.append((px - 12, py - 12, px + 12, py + 12))
            draw.ellipse([px - 9, py - 9, px + 9, py + 9], fill=(239, 233, 219), outline=color, width=3)
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(35, 31, 26))
            # Номер правителя: цифры рисуются любым шрифтом, кириллица в подписи не нужна.
            label = str(number)
            tx, ty = px + 12, py - 11
            # Сдвигаем подпись, если место занято: в тесном кадре точки стоят кучно.
            for shift in (0, -20, 20, -40, 40, -60, 60):
                box = (tx, ty + shift, tx + 11 * len(label) + 4, ty + shift + 18)
                clash = any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed_labels)
                if not clash:
                    ty += shift
                    placed_labels.append(box)
                    break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                draw.text((tx + dx, ty + dy), label, fill=(239, 233, 219), font=font)
            draw.text((tx, ty), label, fill=(35, 31, 26), font=font)
        legend.append(
            {
                "ruler": ruler,
                "house": house,
                "color": "#%02x%02x%02x" % color,
                "player": house == player_house,
                "counties": len(pids),
                "num": number,
            }
        )

    groups = []
    for house in sorted(house_color, key=house_weight):
        members = [item for item in legend if item["house"] == house]
        if not members:
            continue
        groups.append(
            {
                "house": house,
                "role": "player" if house == player_house else house_roles.get(house, "cadet"),
                "color": "#%02x%02x%02x" % house_color[house],
                "counties": sum(item["counties"] for item in members),
                "rulers": [{"num": item["num"], "ruler": item["ruler"], "counties": item["counties"]} for item in members],
            }
        )

    # Названия домов прямо на карте: подпись ставим в ядре владений дома, тушью с обводкой.
    def core_point(house_name: str):
        own = [(pid, centroids[pid]) for pid, (hh, _r) in family_lands.items() if hh == house_name and pid in centroids]
        if not own:
            return None
        # Гуща владений: графство, вокруг которого больше всего своих. Подпись ложится в плотное пятно,
        # а не на окраину и не в анклав.
        gx = sum(p[0] for _i, p in own) / len(own)
        gy = sum(p[1] for _i, p in own) / len(own)
        best = None
        best_score = None
        for _pid, point in own:
            near = sum(1 for _j, other in own if (point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2 < 150 ** 2)
            to_center = (point[0] - gx) ** 2 + (point[1] - gy) ** 2
            score = (-near, to_center)
            if best_score is None or score < best_score:
                best_score = score
                best = point
        return best

    for house in sorted(house_color, key=house_weight):
        point = core_point(house)
        if not point:
            continue
        hx, hy = point[0] - left, point[1] - top
        label = house
        text_width = draw.textlength(label, font=house_font)
        lx, ly = hx - text_width / 2, hy - 30
        for shift in (0, -34, 34, -68, 68):
            box = (lx - 8, ly + shift - 6, lx + text_width + 8, ly + shift + 34)
            clash = any(
                box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3]
                for b in placed_labels + dot_boxes
            )
            if not clash:
                ly += shift
                placed_labels.append(box)
                break
        # Подложка цвета бумаги: подпись читается и на заливке, и на границе.
        draw.rectangle([lx - 5, ly - 4, lx + text_width + 5, ly + 28], fill=(239, 233, 219))
        draw.text((lx, ly), label, fill=(35, 31, 26), font=house_font)

    path = out.with_name(out.stem + "-political.png")
    result.save(path, optimize=True)

    # Карта индексов для наведения: тот же кадр, цвет пикселя — номер державы.
    pick = np.zeros((prov.shape[0], prov.shape[1], 3), dtype=np.uint8)
    for rid, i in realm_index.items():
        pick[realm_px == i] = ((i >> 16) & 255, (i >> 8) & 255, i & 255)
    ids_path = out.with_name(out.stem + "-political-ids.png")
    Image.fromarray(pick).save(ids_path, optimize=True)

    print(f"политическая карта: {path.name} ({path.stat().st_size / 1024:.0f} КБ), "
          f"правителей рода: {len(legend)}, кадр {right - left}x{bottom - top}")
    return {"file": path.name, "index": ids_path.name, "houses": legend, "groups": groups}


def render_political_houses(out: Path, realms: dict[int, dict], province_realm: dict[int, int],
                            image, width: int, height: int, house_roles: dict[str, str] | None = None) -> dict | None:
    """Карта домов: каждая держава закрашена цветом дома своего правителя.

    Нужна именно тогда, когда род земли не держит: видно, кто где правит.
    Дома династии — акцент и сепия, остальные — приглушённые различимые тона.
    """
    import numpy as np
    from PIL import Image

    if not realms:
        return None

    provinces, keys, ids = province_assets(np)

    paper = np.array(MAP_PAPER, dtype=np.uint8)
    sea = np.array(MAP_SEA, dtype=np.uint8)
    ink = {0: (25, 23, 19), 1: (52, 47, 39), 2: (86, 79, 65), 3: (124, 115, 96), 4: (156, 146, 124)}

    roles = house_roles or {}
    dynasty_houses = [h for h, role in roles.items() if role in ("player", "senior", "cadet")]
    # Приглушённые тона: двенадцать оттенков, чтобы соседи реже совпадали, и всё в духе бумаги.
    tone = [
        (78, 96, 122), (112, 128, 84), (150, 116, 74), (110, 88, 116), (82, 118, 110), (140, 94, 88),
        (96, 108, 86), (124, 110, 92), (86, 106, 118), (128, 96, 110), (100, 118, 96), (118, 104, 78),
    ]

    def mix(color: tuple[int, int, int], strength: float = 0.55) -> tuple[int, int, int]:
        """Подмешиваем бумагу: заливка не должна спорить с тушью."""
        base = (239, 233, 219)
        return tuple(int(base[i] * (1 - strength) + color[i] * strength) for i in range(3))

    def house_color(name: str) -> tuple[int, int, int]:
        role = roles.get(name)
        if role == "player":
            return mix((160, 44, 28), 0.85)
        if role == "senior":
            return mix((47, 74, 107), 0.85)
        if role == "cadet":
            cadets = [h for h in dynasty_houses if roles.get(h) == "cadet"]
            index = cadets.index(name) if name in cadets else 0
            return mix(tone[(index + 1) % len(tone)], 0.8)
        # Чужой дом: тон по хешу имени — стабильно между сборками, но соседи различаются.
        digest = sum((index + 1) * ord(ch) for index, ch in enumerate(name)) if name else 0
        return mix(tone[digest % len(tone)], 0.65)

    realm_house: dict[int, str] = {}
    for rid, realm in realms.items():
        name = realm.get("house_name") or ""
        if name:
            realm_house[rid] = name

    step = 2
    small = np.asarray(image.resize((width // step, height // step), Image.NEAREST), dtype=np.uint16)
    r = small[:, :, 0].astype(np.uint32)
    g = small[:, :, 1].astype(np.uint32)
    b = small[:, :, 2].astype(np.uint32)
    flat = ((r << 16) | (g << 8) | b).ravel()
    pos = np.clip(np.searchsorted(keys, flat), 0, len(keys) - 1)
    prov = np.where(keys[pos] == flat, ids[pos], 0).astype(np.int32).reshape(small.shape[:2])
    max_prov = max(provinces)
    prov = np.clip(prov, 0, max_prov)

    known = sorted(realms)
    realm_index = {rid: i + 1 for i, rid in enumerate(known)}
    rid_arr = np.zeros(max_prov + 1, dtype=np.int64)
    for pid, rid in province_realm.items():
        if 0 <= pid <= max_prov:
            rid_arr[pid] = rid
    rid_px = rid_arr[prov]
    known_rids = np.array(known, dtype=np.int64)
    known_vals = np.array([realm_index[r_] for r_ in known], dtype=np.int32)
    hit_pos = np.clip(np.searchsorted(known_rids, rid_px), 0, max(len(known_rids) - 1, 0))
    hit = known_rids[hit_pos] == rid_px
    realm_px = np.where(hit, known_vals[hit_pos], 0).astype(np.int32)

    canvas = np.zeros((prov.shape[0], prov.shape[1], 3), dtype=np.uint8)
    canvas[:] = paper
    canvas[prov == 0] = sea

    house_index: dict[str, int] = {}
    for rid in known:
        house = realm_house.get(rid)
        if not house:
            continue
        if house not in house_index:
            house_index[house] = len(house_index) + 1
        canvas[realm_px == realm_index[rid]] = house_color(house)

    # Рубежи держав: чем ближе двор, тем темнее линия.
    tier = np.zeros(len(realm_index) + 1, dtype=np.int16)
    ring = np.full(len(realm_index) + 1, 4, dtype=np.int16)
    for rid, i in realm_index.items():
        ring[i] = int(realms[rid].get("ring", 4))
    ring_px = ring[realm_px]
    edge_h = np.zeros(realm_px.shape, dtype=bool)
    edge_v = np.zeros(realm_px.shape, dtype=bool)
    edge_h[:, :-1] = (realm_px[:, :-1] != realm_px[:, 1:]) & (realm_px[:, :-1] > 0) & (realm_px[:, 1:] > 0)
    edge_v[:-1, :] = (realm_px[:-1, :] != realm_px[1:, :]) & (realm_px[:-1, :] > 0) & (realm_px[1:, :] > 0)
    ring_h = np.zeros(realm_px.shape, dtype=np.int16)
    ring_v = np.zeros(realm_px.shape, dtype=np.int16)
    ring_h[:, :-1] = np.minimum(ring_px[:, :-1], ring_px[:, 1:])
    ring_v[:-1, :] = np.minimum(ring_px[:-1, :], ring_px[1:, :])
    for mask, ringmap in ((edge_h, ring_h), (edge_v, ring_v)):
        for value, color in ink.items():
            canvas[mask & (ringmap == value)] = color
    coast = np.zeros(prov.shape, dtype=bool)
    coast[:, :-1] |= (prov[:, :-1] > 0) & (prov[:, 1:] == 0)
    coast[:, 1:] |= (prov[:, 1:] > 0) & (prov[:, :-1] == 0)
    coast[:-1, :] |= (prov[:-1, :] > 0) & (prov[1:, :] == 0)
    coast[1:, :] |= (prov[1:, :] > 0) & (prov[:-1, :] == 0)
    canvas[coast] = (52, 46, 37)

    result = Image.fromarray(canvas).convert("RGB")
    path = out.with_name(out.stem + "-political-houses.png")
    result.save(path, optimize=True)

    pick = np.zeros((prov.shape[0], prov.shape[1], 3), dtype=np.uint8)
    for rid, i in realm_index.items():
        pick[realm_px == i] = ((i >> 16) & 255, (i >> 8) & 255, i & 255)
    ids_path = out.with_name(out.stem + "-political-houses-ids.png")
    Image.fromarray(pick).save(ids_path, optimize=True)

    counts: dict[str, int] = {}
    for rid in known:
        house = realm_house.get(rid)
        if house:
            counts[house] = counts.get(house, 0) + 1
    legend = [
        {
            "house": house,
            "color": "#%02x%02x%02x" % house_color(house),
            "realms": count,
            "player": roles.get(house) == "player",
            "dynasty": roles.get(house) in ("player", "senior", "cadet"),
        }
        for house, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]

    print(f"карта домов: {path.name} ({path.stat().st_size / 1024:.0f} КБ), домов в легенде: {len(legend)}")
    return {"file": path.name, "index": ids_path.name, "houses": legend}


def render_map(out: Path, province_realm: dict[int, int], realms: dict[int, dict], centroids, baronies, game: Path,
               family_lands: dict[int, tuple[str, str]] | None = None, player_house: str | None = None) -> dict:
    """Карта мира + карта индексов для наведения.

    Цвет — степень знания; рядом сохраняется карта, где цвет пикселя — номер державы.
    По ней приложение понимает, на какой двор навели мышь.
    """
    import numpy as np
    from PIL import Image

    provinces, keys, ids = province_assets(np)

    palette = {0: (25, 23, 19), 1: (74, 67, 53), 2: (138, 127, 104), 3: (189, 178, 154), 4: (224, 216, 198)}
    land = np.array([239, 233, 219], dtype=np.uint8)

    # индекс державы для карты наведения
    order_realms = sorted(realms)
    index_of = {rid: i + 1 for i, rid in enumerate(order_realms)}
    index_colors = {i + 1: ((i + 1) >> 16 & 255, (i + 1) >> 8 & 255, (i + 1) & 255) for i in range(len(order_realms))}

    image = Image.open(game / "map_data" / "provinces.png").convert("RGB")
    width, height = image.size
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = land
    pick = np.zeros((height, width, 3), dtype=np.uint8)

    realm_arr = np.zeros(max(provinces) + 1, dtype=np.int32)
    for pid, rid in province_realm.items():
        if 0 <= pid < len(realm_arr):
            realm_arr[pid] = rid
    ring_arr = np.full(max(provinces) + 1, -1, dtype=np.int32)
    idx_arr = np.zeros(max(provinces) + 1, dtype=np.int32)
    for rid, realm in realms.items():
        mask = realm_arr == rid
        ring_arr[mask] = realm["ring"]
        idx_arr[mask] = index_of[rid]

    strip = 256
    for top in range(0, height, strip):
        bottom = min(top + strip, height)
        block = np.asarray(image.crop((0, top, width, bottom)), dtype=np.uint16)
        r = block[:, :, 0].astype(np.uint32)
        g = block[:, :, 1].astype(np.uint32)
        b = block[:, :, 2].astype(np.uint32)
        flat = ((r << 16) | (g << 8) | b).ravel()
        pos = np.clip(np.searchsorted(keys, flat), 0, len(keys) - 1)
        prov = np.where(keys[pos] == flat, ids[pos], 0).astype(np.int32)
        prov = np.clip(prov, 0, len(ring_arr) - 1)

        rings = ring_arr[prov].reshape(block.shape[:2])
        idx = idx_arr[prov].reshape(block.shape[:2])

        out_block = canvas[top:bottom]
        for ring, color in palette.items():
            out_block[rings == ring] = color
        canvas[top:bottom] = out_block

        pick_block = pick[top:bottom]
        for rid, i in index_of.items():
            pick_block[idx == i] = index_colors[i]
        pick[top:bottom] = pick_block

    result = Image.fromarray(canvas).resize((width // 4, height // 4), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out, optimize=True)

    ids_path = out.with_name(out.stem + "-ids.png")
    Image.fromarray(pick).resize((width // 4, height // 4), Image.NEAREST).save(ids_path, optimize=True)

    mapping = {}
    for rid, i in index_of.items():
        realm = realms[rid]
        mapping[str(i)] = {
            "name": realm.get("name"),
            "ring": realm.get("ring"),
            "ruler": realm.get("ruler"),
            "house": realm.get("house_name"),
            "distance": realm.get("distance"),
            "direction": realm.get("direction"),
            "size": realm.get("size"),
        }

    print(f"карта: {out} ({out.stat().st_size / 1024:.0f} КБ), индексы: {ids_path.name} ({ids_path.stat().st_size / 1024:.0f} КБ)")
    return {"file": ids_path.name, "realms": mapping}
