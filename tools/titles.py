"""Титулы: одна модель поверх трёх свидетелей.

Титул в сохранении описан в трёх местах, и каждое знает своё:

* `titles[*].history` в дампе экстрактора — кто держал титул до старта партии;
  история обрывается на дате начала игры;
* `save-extra.json` из `tools/save_reader.py` — смены власти по ходу партии,
  прочитанные прямо из текстового `gamestate`;
* `memories` с `landed_title` — кто, когда и **почему** получил или потерял
  титул: `variables.reason` (`inheritance`, `granted`, `revoked`…),
  `participants.new_holder` у потери.

Модуль сводит три источника в одну запись титула: история получает причину и
пометку источника, а записи, которых в истории нет, добавляются из памяти.

Запись истории — список `[дата, держатель, причина, источник]`, где причина и
источник могут быть пустыми. Так её и читает `build_world.py`.

Проверить себя без игры: `python tools/titles.py --selftest`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date as Date, timedelta
from pathlib import Path

try:
    import ijson
except ImportError:  # без ijson работает только --selftest
    ijson = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

TIER_ORDER = {"Empire": 0, "Kingdom": 1, "Duchy": 2, "County": 3, "Barony": 4}
# Титры, о которых имеет смысл говорить в летописи. Баронства — нет:
# их в памяти 2 507 записей, и ни одна не про род.
LANDED_TIERS = ("Empire", "Kingdom", "Duchy", "County")

# Причина смены держателя так, как её называет игра (`variables.reason`).
# Ключ → (по-русски, по-английски). Список собран по сейву 913 года:
# других причин в памяти не встречается.
REASONS: dict[str, tuple[str, str]] = {
    "inheritance": ("по наследству", "by inheritance"),
    "granted": ("пожалован", "granted"),
    "revoked": ("отобран", "revoked"),
    "conquest": ("завоёван", "conquered"),
    "conquest_claim": ("завоёван по притязанию", "conquered by claim"),
    "conquest_populist": ("взят народной войной", "taken by popular war"),
    "conquest_holy_war": ("взят священной войной", "taken by holy war"),
    "created": ("создан", "created"),
    "appointment": ("по назначению", "by appointment"),
    "appointment_succession": ("перешёл по назначению", "passed by appointment"),
    "abdication": ("после отречения", "after abdication"),
    "migration": ("перешёл после переселения", "after migration"),
    "faction_demand": ("уступлен по требованию фракции", "yielded to a faction"),
    "swear_fealty": ("по присяге", "by oath of fealty"),
    "stepped_down": ("оставлен добровольно", "stepped down"),
    "independency": ("получил независимость", "became independent"),
    "usurped": ("узурпирован", "usurped"),
    "negotiated": ("передан по договору", "handed over by agreement"),
    "leased_out": ("сдан в лен", "leased out"),
    "lease_revoked": ("лен отозван", "lease revoked"),
    "destroyed": ("уничтожен", "destroyed"),
    "returned": ("возвращён", "returned"),
}

# Какие причины означают «титул появился» и «титул исчез».
CREATED = {"created"}
DESTROYED = {"destroyed"}
# Дамп пишет действие в CamelCase (`Inherited`), память — ключом (`inheritance`).
ACTION_ALIASES = {
    "inherited": "inheritance",
    "conquered": "conquest",
}


def normalize_action(action: str | None) -> str | None:
    """`Inherited` и `appointment_succession` → один вид ключа."""
    if not action:
        return None
    text = "".join(
        ("_" + char.lower()) if char.isupper() else char for char in str(action).strip()
    ).strip("_")
    if not text:
        return None
    return ACTION_ALIASES.get(text, text)


def reason_text(key: str | None, lang: str = "ru") -> str:
    """Причина словами. Незнакомый ключ не выдумываем — отдаём как есть."""
    if not key:
        return ""
    pair = REASONS.get(key)
    if not pair:
        return key.replace("_", " ")
    return pair[0] if lang == "ru" else pair[1]


GAME_MARKUP = re.compile(r"\$[^$]*\$")


def clean_name(name: str | None) -> str:
    """Имя без служебных подстановок.

    Игра иногда отдаёт вместо имени ключ: «Семья Пхёнсан $dynn_Bak_6734$».
    В летопись такой ключ не идёт — остаётся то, что читается.
    """
    if not name:
        return ""
    value = GAME_MARKUP.sub("", str(name))
    return re.sub(r"\s+", " ", value).strip()


def ref(value):
    """Ссылка вида `{"id": 12, "name": "…"}`, `{"Id": 12}` или число → 12.

    В памяти игра пишет ключ `Id` с большой буквы (`variables.landed_title`),
    в участниках — `id`. Без обоих написаний память о титулах читается впустую.
    """
    if isinstance(value, dict):
        ident = value.get("id")
        if ident is None:
            ident = value.get("Id")
        return int(ident) if isinstance(ident, (int, float)) and not isinstance(ident, bool) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def _source_add(row: list, source: str) -> None:
    """Дописывает источник к записи истории, не теряя прежние."""
    order = ["dump", "save", "memory"]
    parts = [p for p in (row[3] or "").split("+") if p]
    if source in parts:
        return
    parts.append(source)
    parts.sort(key=lambda p: order.index(p) if p in order else len(order))
    row[3] = "+".join(parts)


def read_titles(dump_path: Path) -> dict[int, dict]:
    """Титулы из дампа экстрактора. История — списком `[дата, держатель, причина, источник]`."""
    if ijson is None:
        raise SystemExit("Нужен ijson: pip install ijson")
    titles: dict[int, dict] = {}
    with Path(dump_path).open("rb") as handle:
        for ident, tile in ijson.kvitems(handle, "titles", use_float=False):
            capital = tile.get("capital") or {}
            faith = tile.get("faith") or {}
            culture = tile.get("culture") or {}
            history = []
            for row in tile.get("history") or []:
                if isinstance(row, list) and len(row) >= 3:
                    holder = row[1]
                    # В истории держатель — человек, а не титул. Иное отбрасываем.
                    holder_id = ref(holder) if isinstance(holder, dict) and holder.get("subdir") == "characters" else None
                    history.append([row[0], holder_id or None, row[2], "dump"])
            titles[int(ident)] = {
                "id": int(ident),
                "key": tile.get("key"),
                "name": clean_name(tile.get("name")),
                "tier": tile.get("tier") or "Other",
                "capital": ref(capital),
                "faith": faith.get("name") if isinstance(faith, dict) else None,
                "culture": culture.get("name") if isinstance(culture, dict) else None,
                # Держатель — человек, он ставится позже из characters[].titles.
                # de_facto — сюзерен-ТИТУЛ, а не владелец: все ссылки ведут в titles.
                "holder": None,
                "holderSince": None,
                "liege": ref(tile.get("de_facto")),
                # Прямой de jure-сюзерен: надёжнее обратной сборки через вассалов.
                "de_jure": ref(tile.get("de_jure")),
                "vassals": [ref(v) for v in (tile.get("de_jure_vassals") or []) if ref(v)],
                "history": history,
                "gone": False,
            }
    return titles


def attach_holders(titles: dict[int, dict], characters: dict[int, dict]) -> dict:
    """Ставит держателя-человека: из списка титулов персонажа, иначе из истории.

    `titles[].de_facto` — это сюзерен-ТИТУЛ (все 16 086 ссылок в сейве ведут
    в `titles`), поэтому владельца берём из `characters[].titles` — это 19 228
    связей «человек держит титул». Где списка нет, годится последняя запись
    истории с человеком.
    """
    stats = {"by_person": 0, "by_history": 0, "none": 0}
    for tile in titles.values():
        tile["holder"] = None
        tile["holderSince"] = None

    for cid, person in characters.items():
        for title_id in person.get("titles") or []:
            tile = titles.get(title_id)
            if tile is not None and tile["holder"] is None:
                tile["holder"] = cid
                stats["by_person"] += 1

    for tile in titles.values():
        if tile["holder"] is None:
            for row in reversed(tile["history"]):
                if row[1]:
                    tile["holder"] = row[1]
                    stats["by_history"] += 1
                    break
        if tile["holder"] is None:
            stats["none"] += 1
            continue
        # С какого года держит: последняя запись с этим человеком.
        for row in reversed(tile["history"]):
            if row[1] == tile["holder"]:
                tile["holderSince"] = row[0]
                break
    return stats


def read_save_titles(extra_path: Path) -> tuple[dict, dict]:
    """История титулов из `save-extra.json`: `({key: [[дата, держатель, действие]]}, {key: имя})`."""
    payload = json.loads(Path(extra_path).read_text(encoding="utf-8"))
    return payload.get("titles") or {}, payload.get("names") or {}


def merge_history(titles: dict[int, dict], save_titles: dict, save_names: dict | None = None) -> dict:
    """Склеивает историю дампа и сейва по `key` титула.

    id в двух источниках разные: `c_parsberg` — 863 в дампе и 951 в сейве,
    поэтому склейка только по ключу.
    """
    by_key = {tile["key"]: tile for tile in titles.values() if tile.get("key")}
    stats = {"titles": 0, "rows": 0, "added": 0, "orphans": 0}

    for key, rows in (save_titles or {}).items():
        tile = by_key.get(key)
        if tile is None:
            # Титул есть в сейве, но не в дампе: игра его уничтожила.
            stats["orphans"] += 1
            continue
        merged = {(row[0], row[1]): row for row in tile["history"]}
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            date, holder = row[0], row[1] or None
            action = row[2] if len(row) > 2 else None
            slot = merged.get((date, holder))
            if slot is None:
                fresh = [date, holder, action, "save"]
                merged[(date, holder)] = fresh
                stats["added"] += 1
            else:
                if action and not slot[2]:
                    slot[2] = action
                _source_add(slot, "save")
            stats["rows"] += 1
        # Пересобираем: в самом дампе бывают повторы одной и той же записи.
        tile["history"] = list(merged.values())
        stats["titles"] += 1

    for tile in titles.values():
        tile["history"].sort(key=lambda row: (row[0] or "", row[1] or 0))
    return stats


def dedupe(titles: dict[int, dict]) -> int:
    """Схлопывает повторы одной записи: одна дата и один держатель — одна строка."""
    dropped = 0
    for tile in titles.values():
        unique: dict[tuple, list] = {}
        for row in tile["history"]:
            slot = unique.get((row[0], row[1]))
            if slot is None:
                unique[(row[0], row[1])] = row
                continue
            dropped += 1
            if row[2] and not slot[2]:
                slot[2] = row[2]
            for part in (row[3] or "").split("+"):
                if part:
                    _source_add(slot, part)
        tile["history"] = list(unique.values())
    return dropped


def _row_rank(row: list) -> tuple:
    """Вес записи при выборе одной смены на дату: память → сейв → дамп."""
    source = row[3] or ""
    has_reason = 1 if row[2] else 0
    if "memory" in source:
        return (3, has_reason)
    if "save" in source:
        return (2, has_reason)
    return (1, has_reason)


def _nearest_known(history: list, when: str, action: str | None = None, window: int = 10):
    """Ближайшая запись с известным держателем — к ней подклеивается запись без него.

    Действие должно совпадать: иначе «учреждён» склеится с «по наследству» и соврёт.
    """
    if not when:
        return None
    want = normalize_action(action)

    def pick(rows: list[list]):
        for row in rows:
            if row[1] is None:
                continue
            if normalize_action(row[2]) == want:
                return row
        if want in (None, "inheritance"):
            for row in rows:
                if row[1] is not None:
                    return row
        return None

    same_day = [row for row in history if row[0] == when]
    found = pick(same_day)
    if found is not None:
        return found
    try:
        base = Date.fromisoformat(when)
    except (TypeError, ValueError):
        return None
    for shift in range(1, window + 1):
        for cand in ((base + timedelta(days=shift)).isoformat(), (base - timedelta(days=shift)).isoformat()):
            found = pick([row for row in history if row[0] == cand])
            if found is not None:
                return found
    return None


def reconcile(titles: dict[int, dict], window: int = 10) -> dict:
    """Убирает смены без держателя и оставляет одного держателя на дату.

    * Запись без держателя — либо та же смена, что уже есть с именем (тогда переносим
      источник и причину и дубль убираем), либо единственная запись о смене: её оставляем,
      летопись скажет «сменился государь» без имени. Историю не выбрасываем.
    * Две записи на одну дату с разными держателями — в сейве такое бывает буквально
      (`768.9.24=7705 768.9.24=7141`), и движок читает последнюю. Оставляем ту,
      что ближе к событию: память → сейв → дамп.
    """
    stats = {"no_holder_merged": 0, "no_holder_kept": 0, "same_day_dropped": 0}
    told_apart = CREATED | DESTROYED

    for tile in titles.values():
        history = tile["history"]
        known = [row for row in history if row[1] is not None]

        # 1. Записи без держателя.
        kept: list[list] = []
        for row in history:
            if row[1] is not None:
                kept.append(row)
                continue
            partner = _nearest_known(known, row[0], row[2], window)
            if partner is not None and partner is not row:
                for part in (row[3] or "").split("+"):
                    if part:
                        _source_add(partner, part)
                if row[2] and (not partner[2] or normalize_action(partner[2]) == "inheritance"):
                    partner[2] = row[2]
                stats["no_holder_merged"] += 1
                continue
            # Пары нет — запись остаётся: в летописи она станет «сменился государь»,
            # а счёт потерь от этого не врёт. Выбрасывать историю нельзя.
            kept.append(row)
            stats["no_holder_kept"] += 1

        # 2. Одна дата — один держатель.
        by_date: dict[str, list] = {}
        for row in kept:
            when = row[0]
            slot = by_date.get(when)
            if slot is None:
                by_date[when] = row
                continue
            if slot[1] is None and row[1] is not None:
                by_date[when] = row
                continue
            if row[1] is None:
                continue
            keep, drop = (row, slot) if _row_rank(row) > _row_rank(slot) else (slot, row)
            if drop[2] and (not keep[2] or normalize_action(keep[2]) == "inheritance"):
                keep[2] = drop[2]
            for part in (drop[3] or "").split("+"):
                if part:
                    _source_add(keep, part)
            by_date[when] = keep
            stats["same_day_dropped"] += 1

        tile["history"] = sorted(by_date.values(), key=lambda row: (row[0] or "", row[1] or 0))
    return stats


def _find_row(index: dict, history: list, when: str, holder: int | None, window: int = 10):
    """Ищет запись истории, к которой относится событие памяти.

    Память и история расходятся в дате: в сейве 913 года точно совпадают
    3 092 записи из 7 138, ещё 3 775 попадают в окно десяти дней.
    """
    if not when:
        return None
    same_day = index.get(when)
    if same_day:
        if holder is not None:
            for row in same_day:
                if row[1] == holder:
                    return row
        return same_day[0]
    try:
        base = Date.fromisoformat(when)
    except (TypeError, ValueError):
        return None
    for shift in range(1, window + 1):
        for cand in ((base + timedelta(days=shift)).isoformat(), (base - timedelta(days=shift)).isoformat()):
            rows = index.get(cand)
            if not rows:
                continue
            if holder is not None:
                for row in rows:
                    if row[1] == holder:
                        return row
            return rows[0]
    return None


def attach_memory(titles: dict[int, dict], memories: list[dict], owners: dict[int, int] | None = None,
                  window: int = 10) -> dict:
    """Ставит причину на смену власти из истории и добавляет пропущенные памятью.

    `memories` — записи о титулах: `{id, date, kind ("gain"/"loss"), title,
    reason, newHolder}`. `owners` — кому принадлежит воспоминание (`id → персонаж`):
    у получения держателем становится сам автор памяти, у потери — `new_holder`.
    """
    owners = owners or {}
    index = {tile_id: defaultdict(list) for tile_id in titles}
    for tile_id, tile in titles.items():
        for row in tile["history"]:
            index[tile_id][row[0]].append(row)

    stats = {"matched": 0, "added": 0, "no_title": 0, "no_holder": 0,
             "skipped_tier": 0, "reasoned": 0, "conflict": 0}

    for memory in memories:
        tile = titles.get(memory.get("title"))
        if tile is None:
            # Титул уничтожен — в дампе его уже нет, имени взять неоткуда.
            stats["no_title"] += 1
            continue
        if tile["tier"] not in LANDED_TIERS:
            stats["skipped_tier"] += 1
            continue

        owner = owners.get(memory.get("id"))
        holder = memory.get("newHolder") if memory.get("kind") == "loss" else owner
        if holder is None:
            holder = owner
        if holder is None:
            stats["no_holder"] += 1
            continue

        row = _find_row(index[tile["id"]], tile["history"], memory.get("date"), holder, window)
        if row is None:
            row = [memory.get("date"), holder, None, "memory"]
            tile["history"].append(row)
            index[tile["id"]][row[0]].append(row)
            stats["added"] += 1
        else:
            _source_add(row, "memory")
            stats["matched"] += 1

        if memory.get("reason"):
            why = normalize_action(memory["reason"])
            if row[2]:
                if normalize_action(row[2]) != why:
                    # Память ближе к событию: она помнит участников и повод,
                    # история лишь фиксирует смену держателя. Расхождение считаем,
                    # чтобы проверка видела, если его станет больше.
                    stats["conflict"] += 1
                    row[2] = why
            else:
                row[2] = why
                stats["reasoned"] += 1

    for tile in titles.values():
        tile["history"].sort(key=lambda row: (row[0] or "", row[1] or 0))
    return stats


def read_memory_titles(dump_path: Path) -> list[dict]:
    """Воспоминания, в которых назван титул. Нужны для CLI и проверки."""
    if ijson is None:
        raise SystemExit("Нужен ijson: pip install ijson")
    rows = []
    with Path(dump_path).open("rb") as handle:
        for ident, mem in ijson.kvitems(handle, "memories", use_float=False):
            variables = mem.get("variables") or {}
            landed = variables.get("landed_title")
            if not isinstance(landed, dict):
                continue
            reason = variables.get("reason")
            if isinstance(reason, dict):
                reason = reason.get("String") or reason.get("Id")
            participants = mem.get("participants") or {}
            new_holder = participants.get("new_holder")
            rows.append(
                {
                    "id": int(ident),
                    "date": mem.get("date"),
                    "type": (mem.get("type") or "").strip(),
                    "title": ref(landed),
                    "reason": str(reason) if reason is not None else None,
                    "newHolder": ref(new_holder),
                    "newHolderName": new_holder.get("name") if isinstance(new_holder, dict) else None,
                }
            )
    return rows


def read_memory_owners(dump_path: Path) -> dict[int, int]:
    """Кому принадлежит воспоминание: `id воспоминания → персонаж`."""
    if ijson is None:
        raise SystemExit("Нужен ijson: pip install ijson")
    owners: dict[int, int] = {}
    with Path(dump_path).open("rb") as handle:
        for ident, char in ijson.kvitems(handle, "characters", use_float=False):
            for mem in char.get("memories") or []:
                mem_id = mem.get("id") if isinstance(mem, dict) else mem
                if mem_id is not None:
                    owners[int(mem_id)] = int(ident)
    return owners


def title_kind(memory_type: str) -> str | None:
    """«Меня сделали правителем» — получение, «потерян важный титул» — потеря."""
    low = (memory_type or "").lower()
    if "потерян" in low or "lost an important title" in low:
        return "loss"
    if "сделали правителем" in low or "made me ruler" in low:
        return "gain"
    return None


def summary(titles: dict[int, dict]) -> dict:
    """Счётчики для отчёта и проверки."""
    by_tier: dict[str, int] = defaultdict(int)
    rows = 0
    reasons = 0
    sources: dict[str, int] = defaultdict(int)
    for tile in titles.values():
        by_tier[tile["tier"]] += 1
        rows += len(tile["history"])
        for row in tile["history"]:
            if row[2]:
                reasons += 1
            sources[row[3] or "unknown"] += 1
    return {
        "titles": len(titles),
        "rows": rows,
        "reasoned": reasons,
        "byTier": dict(sorted(by_tier.items(), key=lambda kv: TIER_ORDER.get(kv[0], 9))),
        "bySource": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
    }


def selftest() -> int:
    """Проверка слияния без дампа и без игры."""
    titles = {
        1: {"id": 1, "key": "k_test", "name": "Тест", "tier": "Kingdom", "history": [
            ["0900-01-01", 10, "Inherited", "dump"],
            ["0920-05-05", 11, None, "dump"],
        ], "gone": False},
        2: {"id": 2, "key": "b_small", "name": "Местечко", "tier": "Barony", "history": [], "gone": False},
    }
    memories = [
        # Память о получении: дата на день раньше истории — окно должно поймать.
        {"id": 100, "date": "0920-05-04", "kind": "gain", "title": 1, "reason": "granted", "newHolder": None},
        # Потеря: держателем становится новый владелец.
        {"id": 101, "date": "0900-01-02", "kind": "loss", "title": 1, "reason": "revoked", "newHolder": 10},
        # Баронство в летопись не идёт.
        {"id": 102, "date": "0910-01-01", "kind": "gain", "title": 2, "reason": "granted", "newHolder": None},
        # Титула нет в дампе.
        {"id": 103, "date": "0911-01-01", "kind": "gain", "title": 99, "reason": "created", "newHolder": None},
    ]
    owners = {100: 11, 101: 12, 102: 13, 103: 14}
    stats = attach_memory(titles, memories, owners)

    history = titles[1]["history"]
    assert stats["matched"] == 2, stats
    assert stats["skipped_tier"] == 1, stats
    assert stats["no_title"] == 1, stats
    # Причина встала на найденные записи, история не раздулась дублями.
    assert len(history) == 2, history
    # `Inherited` из дампа нормализован, но память о потере главнее.
    assert stats["conflict"] == 1, stats
    assert history[0][2] == "revoked", history[0]
    assert history[1][2] == "granted", history[1]
    assert "memory" in history[0][3], history[0]
    assert reason_text("inheritance") == "по наследству"
    assert reason_text("unknown_reason") == "unknown reason"
    assert normalize_action("Inherited") == "inheritance"
    assert normalize_action("appointment_succession") == "appointment_succession"
    # de_facto — сюзерен, а не держатель: держателя даёт characters[].titles.
    feudal = {
        1: {"id": 1, "key": "c_x", "name": "Икс", "tier": "County", "holder": None, "holderSince": None,
            "liege": 9, "de_jure": 9, "history": [["0900-01-01", 5, "inheritance", "dump"]], "vassals": [], "gone": False},
        2: {"id": 2, "key": "c_y", "name": "Игрек", "tier": "County", "holder": None, "holderSince": None,
            "liege": None, "de_jure": None, "history": [["0910-05-05", 6, "granted", "dump"]], "vassals": [], "gone": False},
    }
    people = {5: {"titles": [1]}, 6: {"titles": []}}
    stats = attach_holders(feudal, people)
    assert feudal[1]["holder"] == 5, feudal[1]
    assert feudal[1]["holderSince"] == "0900-01-01", feudal[1]
    assert feudal[2]["holder"] == 6, feudal[2]
    assert stats["by_person"] == 1 and stats["by_history"] == 1, stats

    # Имя с ключом династии читается без служебной подстановки.
    assert clean_name("Семья Пхёнсан $dynn_Bak_6734$") == "Семья Пхёнсан", clean_name("Семья Пхёнсан $dynn_Bak_6734$")
    assert clean_name(None) == ""
    assert clean_name("  Китай  ") == "Китай"

    merged = merge_history(
        {5: {"id": 5, "key": "d_x", "name": "Икс", "tier": "Duchy",
             "history": [["0901-01-01", 1, "inheritance", "dump"]], "gone": False}},
        {"d_x": [["0901-01-01", 1, "inheritance"], ["0930-02-02", 2, "granted"]], "d_gone": [["0902-01-01", 3, "created"]]},
        {"d_gone": "Пропавший"},
    )
    assert merged["added"] == 1, merged
    assert merged["orphans"] == 1, merged

    print("OK   слияние трёх свидетелей: причина встаёт на место, дублей нет")
    print(f"OK   строки истории: {stats}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Модель титулов: дамп + сейв + память")
    parser.add_argument("--dump", help="gamestate.json из экстрактора")
    parser.add_argument("--extra", help="save-extra.json из tools/save_reader.py")
    parser.add_argument("--out", help="куда положить модель (JSON)")
    parser.add_argument("--selftest", action="store_true", help="проверка без дампа")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.dump:
        parser.error("нужен --dump или --selftest")

    titles = read_titles(Path(args.dump))
    print(f"титулов в дампе: {len(titles)}", flush=True)
    if args.extra:
        rows, names = read_save_titles(Path(args.extra))
        stats = merge_history(titles, rows, names)
        print(f"история из сейва: титулов {stats['titles']}, записей {stats['rows']}, "
              f"новых {stats['added']}, без пары в дампе {stats['orphans']}", flush=True)
        dropped = dedupe(titles)
        if dropped:
            print(f"повторов одной записи схлопнуто: {dropped}", flush=True)
    memories = read_memory_titles(Path(args.dump))
    owners = read_memory_owners(Path(args.dump))
    for memory in memories:
        memory["kind"] = title_kind(memory.get("type", ""))
    memories = [m for m in memories if m["kind"]]
    stats = attach_memory(titles, memories, owners)
    print(f"память о титулах: найдено пары {stats['matched']}, добавлено {stats['added']}, "
          f"без причины {stats['no_holder']}, мимо тира {stats['skipped_tier']}", flush=True)
    cleanup = reconcile(titles)
    print(f"сверка: без держателя склеено {cleanup['no_holder_merged']}, "
          f"оставлено без имени {cleanup['no_holder_kept']}, "
          f"дублей на дату {cleanup['same_day_dropped']}", flush=True)
    report = summary(titles)
    print(f"итог: титулов {report['titles']}, записей истории {report['rows']}, "
          f"с причиной {report['reasoned']}", flush=True)
    print(f"по тирам: {report['byTier']}", flush=True)
    if args.out:
        payload = {
            "titles": {
                str(tile["id"]): {
                    "key": tile["key"],
                    "name": tile["name"],
                    "tier": tile["tier"],
                    "holder": tile["holder"],
                    "gone": tile["gone"],
                    "history": tile["history"],
                }
                for tile in titles.values()
            },
            "stats": report,
        }
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"записано: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
