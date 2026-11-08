"""Карта титулов: заливка по графствам и границы четырёх тиров.

Рисуется по `provinces.png` игры: каждый пиксель знает свою провинцию, провинция —
своё графство, графство — герцогство, королевство и империю (по de jure). Поэтому
граница на карте — это не догадка по цвету, а смена титула между соседними пикселями.

Рядом с картой кладётся индексная: цвет пикселя — номер графства. По ней приложение
понимает, на какой титул навели мышь.

Толщина границ по тирам: империя 3 px, королевство 2 px, герцогство 1 px,
графство — тонкая светлая линия.
"""

from __future__ import annotations

from pathlib import Path


# Тона бумаги с едва заметным уклоном: карта не должна спорить с летописью.
# Соседние графства могут совпасть по тону — их разделяет линия, а не цвет.
_PAPER_TONES = [
    (214, 205, 185),
    (203, 209, 191),
    (207, 199, 210),
    (219, 203, 192),
    (196, 207, 210),
    (216, 210, 190),
    (201, 197, 179),
    (210, 194, 178),
]


def _palette(count: int) -> list[tuple[int, int, int]]:
    """Сдержанная палитра: тона бумаги с разным уклоном, без кислотных цветов."""
    tones = []
    for i in range(count):
        base = _PAPER_TONES[i % len(_PAPER_TONES)]
        shift = ((i * 7) % 5) - 2
        tones.append(tuple(max(0, min(255, channel + shift)) for channel in base))
    return tones


def _crop_box(points, width: int, height: int, margin: float = 0.06):
    """Рамка вокруг суши: пустой океан по краям не нужен."""
    if not points:
        return (0, 0, width, height)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    pad = span * margin
    left = int(max(0, min(xs) - pad))
    right = int(min(width, max(xs) + pad))
    top = int(max(0, min(ys) - pad))
    bottom = int(min(height, max(ys) + pad))
    return (left, top, right, bottom)


def edges(layer) -> "np.ndarray":
    """Границы: пиксель рядом с чужим титулом (или с водой)."""
    import numpy as np

    mask = np.zeros_like(layer, dtype=bool)
    mask[:, 1:] |= (layer[:, 1:] != layer[:, :-1]) & ((layer[:, 1:] != 0) | (layer[:, :-1] != 0))
    mask[:, :-1] |= (layer[:, :-1] != layer[:, 1:]) & ((layer[:, :-1] != 0) | (layer[:, 1:] != 0))
    mask[1:, :] |= (layer[1:, :] != layer[:-1, :]) & ((layer[1:, :] != 0) | (layer[:-1, :] != 0))
    mask[:-1, :] |= (layer[:-1, :] != layer[1:, :]) & ((layer[:-1, :] != 0) | (layer[1:, :] != 0))
    return mask


def thicken(mask, radius: int) -> "np.ndarray":
    """Утолщает линию: радиус 3 — три пикселя в поперечнике."""
    if radius <= 1:
        return mask
    grown = mask.copy()
    for _ in range(radius - 1):
        shifted = grown.copy()
        shifted[:, 1:] |= grown[:, :-1]
        shifted[:, :-1] |= grown[:, 1:]
        shifted[1:, :] |= grown[:-1, :]
        shifted[:-1, :] |= grown[1:, :]
        grown = shifted
    return grown


def selftest() -> int:
    """Проверка без игры: палитра, рамка, границы."""
    import numpy as np

    tones = _palette(12)
    assert len(tones) == 12, len(tones)
    assert all(0 <= c <= 255 for tone in tones for c in tone), tones[0]
    assert all(sum(tone) / 3 > 150 for tone in tones), tones[0]

    assert _crop_box([], 100, 50) == (0, 0, 100, 50)
    box = _crop_box([(10, 10), (90, 40)], 100, 50)
    assert 0 <= box[0] < box[2] <= 100 and 0 <= box[1] < box[3] <= 50, box

    layer = np.zeros((6, 6), dtype=np.int32)
    layer[:, :3] = 1
    layer[:, 3:] = 2
    mask = edges(layer)
    assert mask.any(), "нет границы между титулами"
    assert mask[:, 2].all() or mask[:, 3].all(), mask.astype(int).tolist()

    same = np.ones((6, 6), dtype=np.int32)
    assert not edges(same).any(), "граница там, где всё одно"

    thin = np.zeros((7, 7), dtype=bool)
    thin[3, 3] = True
    wide = thicken(thin, 3)
    assert wide.sum() > thin.sum(), (thin.sum(), wide.sum())
    assert wide.sum() <= 49, wide.sum()

    print("OK   карта титулов: палитра, рамка, границы")
    print(f"OK   тонов {len(tones)}, радиус 3 даёт {wide.sum()} пикселей")
    return 0


def render_title_map(out: Path, game: Path, card: dict, centroids: dict, scale: int = 2) -> dict:
    """Рисует карту титулов и индексную карту. Возвращает описание для мира."""
    import numpy as np
    from PIL import Image

    counties = card["counties"]
    province_index = {int(k): int(v) for k, v in card["province"].items()}
    chain = card["chain"]

    # Номер графства (1..N) → номера старших титулов. 0 — земли без титула.
    county_arr = np.zeros(max(province_index) + 2, dtype=np.int32)
    for pid, idx in province_index.items():
        if 0 <= pid < len(county_arr):
            county_arr[pid] = idx

    # Для старших тиров номер тот же, что у графства: цепочка идёт по порядку.
    has_tier = np.zeros((3, len(counties) + 2), dtype=bool)
    for idx, steps in enumerate(chain, start=1):
        for level in range(min(3, len(steps))):
            has_tier[level][idx] = True
    duchy_arr = np.where(has_tier[0][county_arr], county_arr, 0)
    kingdom_arr = np.where(has_tier[1][county_arr], county_arr, 0)
    empire_arr = np.where(has_tier[2][county_arr], county_arr, 0)

    image = Image.open(game / "map_data" / "provinces.png").convert("RGB")
    width, height = image.size
    box = _crop_box(list(centroids.values()), width, height)
    left, top, right, bottom = box
    cw, ch = right - left, bottom - top

    from world_maps import MAP_PAPER

    paper = np.array(MAP_PAPER, dtype=np.uint8)
    # Море заметно холоднее бумаги, иначе суша и вода сливаются в одно поле.
    sea = np.array((205, 199, 184), dtype=np.uint8)
    untitled_land = np.array((232, 225, 210), dtype=np.uint8)
    tones = _palette(max(1, len(counties)))
    tone_map = np.zeros((len(counties) + 2, 3), dtype=np.uint8)
    for idx in range(1, len(counties) + 1):
        tone_map[idx] = tones[(idx - 1) % len(tones)]

    county_ink = np.array((208, 198, 178), dtype=np.uint8)
    duchy_ink = np.array((150, 139, 116), dtype=np.uint8)
    kingdom_ink = np.array((88, 80, 66), dtype=np.uint8)
    empire_ink = np.array((32, 30, 25), dtype=np.uint8)

    layer_province = np.zeros((ch, cw), dtype=np.int32)
    layer_county = np.zeros((ch, cw), dtype=np.int32)
    layer_duchy = np.zeros((ch, cw), dtype=np.int32)
    layer_kingdom = np.zeros((ch, cw), dtype=np.int32)
    layer_empire = np.zeros((ch, cw), dtype=np.int32)

    provinces, keys, ids = province_assets_cached(game)

    strip = 256
    pad = 4
    for y0 in range(0, ch, strip):
        y1 = min(ch, y0 + strip)
        y_from = max(0, y0 - pad)
        y_to = min(ch, y1 + pad)
        block = image.crop((left, top + y_from, right, top + y_to))
        prov = province_of_pixels(block, keys, ids, provinces)
        offset = y0 - y_from
        height_needed = y1 - y0
        layer_province[y0:y1] = prov[offset:offset + height_needed]
        layer_county[y0:y1] = county_arr[prov][offset:offset + height_needed]
        layer_duchy[y0:y1] = duchy_arr[prov][offset:offset + height_needed]
        layer_kingdom[y0:y1] = kingdom_arr[prov][offset:offset + height_needed]
        layer_empire[y0:y1] = empire_arr[prov][offset:offset + height_needed]

    canvas = np.zeros((ch, cw, 3), dtype=np.uint8)
    canvas[:] = paper
    # Море — провинция 0. Земля без титула — отдельный случай: она есть, но графства
    # у неё нет, и путать её с водой нельзя.
    water = layer_province == 0
    canvas[water] = sea
    land = ~water
    untitled = land & (layer_county == 0)
    canvas[untitled] = untitled_land
    titled = land & (layer_county > 0)
    canvas[titled] = tone_map[layer_county[titled]]

    canvas[edges(layer_county)] = county_ink
    canvas[edges(layer_duchy)] = duchy_ink
    canvas[thicken(edges(layer_kingdom), 2)] = kingdom_ink
    canvas[thicken(edges(layer_empire), 3)] = empire_ink

    out_size = (max(1, cw // scale), max(1, ch // scale))
    result = Image.fromarray(canvas).resize(out_size, Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out, optimize=True)

    # Индексная карта: цвет пикселя — номер графства.
    index_rgb = np.zeros((len(counties) + 2, 3), dtype=np.uint8)
    for idx in range(1, len(counties) + 1):
        index_rgb[idx] = ((idx >> 16) & 255, (idx >> 8) & 255, idx & 255)
    pick = index_rgb[layer_county]
    ids_path = out.with_name(out.stem + "-ids.png")
    Image.fromarray(pick).resize(out_size, Image.NEAREST).save(ids_path, optimize=True)

    return {
        "file": ids_path.name,
        "counties": len(counties),
        "size": list(out_size),
        "map": out.name,
    }


_PROVINCE_CACHE: dict[str, tuple] = {}


def province_assets_cached(game: Path):
    """province_assets из build_world — один раз на процесс."""
    key = str(game)
    if key not in _PROVINCE_CACHE:
        import numpy as np

        from build_world import province_assets

        _PROVINCE_CACHE[key] = province_assets(np)
    return _PROVINCE_CACHE[key]


def province_of_pixels(block, keys, ids, provinces):
    """Пиксели файла → номера провинций (0 — вода)."""
    import numpy as np

    data = np.asarray(block, dtype=np.uint16)
    r = data[:, :, 0].astype(np.uint32)
    g = data[:, :, 1].astype(np.uint32)
    b = data[:, :, 2].astype(np.uint32)
    flat = (r << 16) | (g << 8) | b
    pos = np.clip(np.searchsorted(keys, flat), 0, len(keys) - 1)
    prov = np.where(keys[pos] == flat, ids[pos], 0).astype(np.int32)
    return np.clip(prov, 0, max(provinces))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Карта титулов: рендер")
    parser.add_argument("--selftest", action="store_true", help="проверка без игры")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    parser.error("нужен --selftest: рендер вызывается из build_world.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
