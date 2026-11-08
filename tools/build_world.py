"""Мир для «Хроники рода»: династия, кольца знания, события, молва и карта.

    python tools/build_world.py --dump _source/gamestate_923.json -o app/_data/world.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

# Консоль Windows бывает в cp1251: без этого любой не-кириллический знак роняет сборку.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import math
from collections import Counter, defaultdict
from pathlib import Path

import ijson

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = ROOT / "_cache"

# Модель титулов живёт отдельно: три свидетеля, история с причиной и источником.
sys.path.insert(0, str(HERE))
from titles import attach_memory, dedupe, merge_history, normalize_action, reason_text, read_titles, reconcile  # noqa: E402
from feudal import person_chain, suzerain_of  # noqa: E402
from world_maps import (  # noqa: E402
    HOUSE_TONES,
    MAP_INK,
    MAP_PAPER,
    MAP_SEA,
    export_csv,
    mix_with_paper,
    province_assets,
    province_pixels,
    realm_index_pixels,
    render_map,
)

# Имена поводов из локализации игры — собирает tools/cb_names.py.
CB_NAMES: dict[str, dict[str, str]] = {}
try:
    CB_NAMES = json.loads((CACHE / "cb-names.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    CB_NAMES = {}

# --- общие константы карт (одна палитра на все линзы) ---












RANK = {"Empire": 0, "Kingdom": 1, "Duchy": 2, "County": 3, "Barony": 4}
GEO_BANDS = (600, 1350, 2250)

# Тип воспоминания → вид события. Порядок важен: первое совпадение выигрывает.
# Тип в сейве — уже локализованная строка, поэтому иголки нужны на обоих языках.
MEMORY_KINDS = [
    ("рождение первенца", "birth"),
    ("родились близнецы", "birth"),
    ("недоношенное", "birth"),
    ("рождение ребенка", "birth"),
    ("в браке", "marriage"),
    ("стали друзьями", "friendship"),
    ("стали побратимами", "friendship"),
    ("стали соперниками", "rivalry"),
    ("стали заклятыми врагами", "rivalry"),
    ("лелеет обиду", "rivalry"),
    ("заключение в тюрьму", "prison"),
    ("освобождение из тюрьмы", "prison_free"),
    ("в заключении", "prison"),
    ("сражение в провинции", "battle"),
    ("победа в войне", "war_win"),
    ("поражение в войне", "war_loss"),
    ("оборонительная война", "war"),
    ("наступательная война", "war"),
    ("потерян важный титул", "title_loss"),
    ("завершенное паломничество", "journey"),
    ("посещение коронации", "journey"),
    ("меня сделали правителем", "ruler"),
    ("поддержан союзник", "alliance"),
    ("стали любовниками", "romance"),
    ("стали родственными душами", "romance"),
    ("возникла влюбленность", "romance"),
    ("мертворожденное", "birth"),
    ("супруг умер", "kin_death"),
    ("смерть друга", "kin_death"),
    ("смерть соперника", "kin_death"),
    # английская локализация сейва
    ("firstborn", "birth"),
    ("twins", "birth"),
    ("stillborn", "birth"),
    ("birth of a child", "birth"),
    ("married", "marriage"),
    ("became friends", "friendship"),
    ("sworn brother", "friendship"),
    ("became rivals", "rivalry"),
    ("nemesis", "rivalry"),
    ("bears a grudge", "rivalry"),
    ("imprisoned", "prison"),
    ("released from prison", "prison_free"),
    ("battle in", "battle"),
    ("war won", "war_win"),
    ("victory in a war", "war_win"),
    ("war lost", "war_loss"),
    ("defeat in a war", "war_loss"),
    ("defensive war", "war"),
    ("offensive war", "war"),
    ("lost an important title", "title_loss"),
    ("pilgrimage", "journey"),
    ("coronation", "journey"),
    ("made me a ruler", "ruler"),
    ("supported an ally", "alliance"),
    ("became lovers", "romance"),
    ("soulmate", "romance"),
    ("spouse died", "kin_death"),
    ("friend died", "kin_death"),
    ("rival died", "kin_death"),
]

# Служебный шум и то, что в летопись не годится.
MEMORY_NOISE = (
    "секс", "пытк", "изнасил", "онанизм", "детское образование", "экзамен",
    "sex", "torture", "rape", "masturbat", "childhood education", "exam",
)


def memory_kind(text: str) -> str | None:
    low = text.lower()
    for needle, kind in MEMORY_KINDS:
        if needle in low:
            return kind
    if any(bad in low for bad in MEMORY_NOISE):
        return None
    # Ключ локализации (`memory_birth_1`) — не текст: в летопись такое не пускаем.
    if "_" in low and " " not in text.strip():
        return None
    # Незнакомая фраза на любом языке: лучше запись без вида, чем потеря события.
    return "note" if " " in text.strip() else None


# Повод войны: ключ сейва → как это звучит в летописи. Незнакомый повод не выдумываем.
CB_RU = {
    "claim_cb": "притязание на титул",
    "individual_county_de_jure_cb": "возврат графства по праву",
    "de_jure_cb_nomadic": "возврат де-юре владения",
    "county_conquest_cb": "завоевание графства",
    "duchy_conquest_cb": "завоевание герцогства",
    "county_struggle_cb": "спор за графство",
    "nomadic_conquest_cb": "кочевое завоевание",
    "mpo_nomad_duchy_invasion_cb": "кочевое вторжение в герцогство",
    "clan_invasion_war": "вторжение клана",
    "fp3_turkic_invasion_cb": "тюркское вторжение",
    "fp1_scandi_adventurer_conquest": "завоевание скандинава-искателя приключений",
    "fp2_expel_interloper": "изгнание чужака",
    "ep3_laamp_apprehend_adventurer_cb": "поимка искателя приключений",
    "chinese_consolidation_cb": "объединение Китая",
    "mandala_raze_capital_structure_cb": "разорение столицы мандалы",
    "major_religious_war": "великая священная война",
    "minor_religious_war": "священная война",
    "make_tributary_cb": "принуждение к дани",
    "liberty_faction_war": "война за вольности",
    "claimant_faction_war": "война за права претендента",
    "refused_liege_demand_war": "война против тирании",
    "independence_war": "война за независимость",
    "subjugation_war": "покорение",
    "conquest_cb": "завоевание",
    "holy_war_cb": "священная война",
    "great_holy_war_cb": "великий крестовый поход",
    "peasant_uprising": "крестьянский мятеж",
    "populist_uprising": "мятеж простолюдинов",
}


def cb_label(key: str, lang: str = "russian") -> str:
    """Повод человеческим языком: имя из игры, затем свой словарь, затем ключ."""
    if not key:
        return "война"
    from_game = (CB_NAMES.get(key) or {}).get(lang)
    if from_game and ":" not in from_game and len(from_game) <= 60:
        # Имя из игры — с заглавной; в строке оно стоит серединой фразы.
        return from_game[:1].lower() + from_game[1:] if from_game[:1].isupper() else from_game
    label = CB_RU.get(key)
    if label:
        return label
    plain = key.replace("_cb", "").replace("_war", "").replace("_", " ").strip()
    return f"повод «{plain}»"


# Категория повода из воспоминаний (`war_cb`): игра хранит её для всех войн, включая давно
# закончившиеся. Тип повода там грубее, чем в `active_wars`, но причина названа.
WAR_MEMORY_CB = {
    "war_memory_cb_holy_war": ("священная война", "holy"),
    "war_memory_cb_conquest": ("завоевание", "conquest"),
    "war_memory_cb_ducal_conquest": ("завоевание герцогства", "conquest"),
    "war_memory_cb_claim": ("притязание", "claim"),
    "war_memory_cb_de_jure": ("возврат по праву", "claim"),
    "war_memory_cb_border": ("пограничный спор", "claim"),
    "war_memory_cb_tyranny": ("война против тирании", "faction"),
    "war_memory_cb_liberty": ("война за вольности", "faction"),
    "war_memory_cb_independence": ("война за независимость", "faction"),
    "war_memory_cb_peasant": ("крестьянский мятеж", "faction"),
    "war_memory_cb_populist": ("мятеж простолюдинов", "faction"),
    "war_memory_cb_vassalization": ("подчинение вассала", "faction"),
    "war_memory_cb_fracture": ("раскол", "faction"),
    "war_memory_cb_government": ("спор о власти", "faction"),
    "war_memory_cb_subjugation": ("покорение", "conquest"),
    "war_memory_cb_invasion": ("вторжение", "conquest"),
    "war_memory_cb_varangian": ("набег варягов", "conquest"),
    "war_memory_cb_flower": ("набег за пленными", "conquest"),
    "war_memory_cb_expel": ("изгнание", "other"),
    "war_memory_cb_artifact": ("спор за реликвию", "other"),
    "war_memory_cb_fallback": ("война", "other"),
}


def memory_role(type_text: str) -> str | None:
    """Наступательная или оборонительная — по тексту воспоминания."""
    low = (type_text or "").lower()
    if "наступательн" in low or "offensive" in low:
        return "attack"
    if "оборонительн" in low or "defensive" in low:
        return "defend"
    return None


def cb_family(key: str) -> str:
    """Семейство повода — от него зависит, как строка звучит в летописи."""
    low = (key or "").lower()
    if "religious" in low or "holy_war" in low or low.startswith("crusade") or "crusading" in low:
        return "holy"
    if "tribut" in low:
        return "tribute"
    if any(word in low for word in ("consolidation", "reunification", "mandate", "hegemon", "mandala")):
        return "mandate"
    if "faction" in low or low in (
        "liberty_faction_war",
        "independence_war",
        "peasant_war",
        "populist_war",
        "nomadic_war",
        "refused_liege_demand_war",
    ):
        return "faction"
    if any(word in low for word in ("conquest", "invasion", "subjugation", "seize")):
        return "conquest"
    if any(word in low for word in ("claim", "de_jure", "struggle")):
        return "claim"
    return "other"


def year_of(date) -> int | None:
    if not date or len(str(date)) < 4:
        return None
    try:
        year = int(str(date)[:4])
    except ValueError:
        return None
    return year if 0 < year < 9000 else None


def ref(value):
    """Ссылка вида `{"id": 12}` или число → 12.

    Игра пишет ключ по-разному: в участниках `id`, в переменных памяти `Id`
    (`variables.landed_title`). Оба написания обязательны: без `Id` память
    о титулах читается впустую.
    """
    if isinstance(value, dict):
        ident = value.get("id")
        if ident is None:
            ident = value.get("Id")
        return ident if isinstance(ident, int) and not isinstance(ident, bool) else (
            int(ident) if isinstance(ident, float) else None
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def house_title(name: str | None) -> str | None:
    """Имя дома, если игра его действительно знает.

    Непереведённый сейв пишет `House 12319`, русский — `дом 12319`.
    Числовой дом в карточке хуже пустого места: там и так сказано «род не записан».
    """
    if not name:
        return None
    value = str(name).strip()
    if re.fullmatch(r"(?i)(house|дом)\s+\d+", value):
        return None
    return value or None


CAUSE_WORDS = {
    "consumption": "чахотка",
    "tuberculosis": "чахотка",
    "smallpox": "оспа",
    "measles": "корь",
    "plague": "чума",
    "leprosy": "проказа",
    "dysentery": "дизентерия",
    "typhus": "тиф",
    "pneumonia": "воспаление лёгких",
    "malaria": "малярия",
    "cholera": "холера",
    "cancer": "рак",
}


def clean_cause(text: str | None) -> str | None:
    """Причина смерти без разметки игры.

    Игра отдаёт её готовой строкой, но иногда с остатками локализации:
    `[Select_CString(CHARACTER.IsFemale, 'умерла', 'умер' )] в плену` и
    `от L чахотки`, где `L` — маркер конца цвета. В летопись такое не пускаем.
    """
    if not text:
        return None
    value = re.sub(r"\[[^\]]*\]", " ", str(text))
    value = re.sub(r"\bL\s+", "", value)
    # Английский сейв иногда оставляет английское слово в русской строке:
    # «Consumption проникает в тело». Читаем по-русски, не выдумывая нового смысла.
    for word, russian in CAUSE_WORDS.items():
        value = re.sub(rf"\b{word}\b", russian, value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ,;:—-\t")
    return value or None


def variant(*parts) -> int:
    """Детерминированный выбор формулировки: одинаковые события читаются одинаково."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.md5(key).hexdigest(), 16) % 7


def is_shown(tile: dict | None) -> bool:
    """Служебные титулы лагерей и кочевников («X d laamp 551») в тексте не показываем."""
    if not tile:
        return False
    name = (tile.get("name") or "").strip()
    if not name:
        return False
    low = name.lower()
    return not (name.startswith("X ") or "laamp" in low or "script" in low or "nomad" in low)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("-o", "--out", type=Path, default=ROOT / "world.js", help="куда писать мир (.js)")
    parser.add_argument("--json", action="store_true", help="дописать ещё и .json — для отладки")
    parser.add_argument(
        "--game",
        type=Path,
        default=Path(os.environ["CK3_GAME"]) if os.environ.get("CK3_GAME") else None,
        help="папка game игры Crusader Kings III (нужна для карты); можно задать переменной CK3_GAME",
    )
    parser.add_argument("--map", type=Path, default=None, help="куда сохранить карту мира")
    parser.add_argument(
        "--extra",
        type=Path,
        default=None,
        help="save-extra.json из tools/save_reader.py: войны с поводами и история титулов из сейва",
    )
    args = parser.parse_args()

    extra: dict = {"wars": [], "titles": {}, "title_keys": {}, "date": None}
    if args.extra:
        if args.extra.exists():
            extra.update(json.loads(args.extra.read_text(encoding="utf-8")))
            print(f"сейв-дополнение: войн {len(extra.get('wars') or [])}, титулов с историей {len(extra.get('titles') or {})}", flush=True)
        else:
            print(f"сейв-дополнение не найдено: {args.extra} — собираю без войн и новой истории", flush=True)

    if not args.dump.exists():
        raise SystemExit(
            f"Не найден дамп: {args.dump}\n"
            "Сначала снимите его экстрактором (см. README, раздел «Свой мир из своего сейва»)."
        )
    missing = [name for name in ("map.json", "centroids.json", "adjacency.json") if not (CACHE / name).exists()]
    if missing:
        raise SystemExit(
            "Не хватает кэша карты: " + ", ".join(missing) + "\n"
            "Постройте его один раз, указав папку игры:\n"
            "  python tools/knowledge_pilot.py map --game \"...\\Crusader Kings III\\game\"\n"
            "  python tools/knowledge_pilot.py adjacency --game \"...\\Crusader Kings III\\game\""
        )

    map_data = json.loads((CACHE / "map.json").read_text(encoding="utf-8"))
    baronies = map_data["baronies"]
    centroids = {int(k): v for k, v in json.loads((CACHE / "centroids.json").read_text(encoding="utf-8")).items()}
    adjacent = json.loads((CACHE / "adjacency.json").read_text(encoding="utf-8"))

    # Проливы нужны только если игра под рукой: без неё работаем без них.
    straits = []
    adj_csv = (args.game / "map_data" / "adjacencies.csv") if args.game else None
    if adj_csv and adj_csv.exists():
        for line in adj_csv.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split(";")
            if len(parts) > 2 and parts[0].isdigit() and parts[1].isdigit() and parts[2].strip().lower() in ("sea", "river_large", "river_small", "lake"):
                straits.append((int(parts[0]), int(parts[1])))

    titles: dict[int, dict] = {}
    characters: dict[int, dict] = {}
    houses: dict[int, dict] = {}
    dynasties: dict[int, dict] = {}
    memories: list[dict] = []
    current_date = None
    players = []

    print("читаю дамп…", flush=True)
    # Титулы: история, имя, тир, держатель — из общей модели.
    titles = read_titles(args.dump)
    with args.dump.open("rb") as handle:
        current_date = next(ijson.items(handle, "current_date", use_float=False), None)
        if isinstance(current_date, str):
            current_date = current_date.strip('"')
    with args.dump.open("rb") as handle:
        players = next(ijson.items(handle, "players", use_float=False), []) or []
    with args.dump.open("rb") as handle:
        for ident, house in ijson.kvitems(handle, "houses", use_float=False):
            parent = house.get("parent") or {}
            houses[int(ident)] = {
                "id": int(ident),
                "name": house.get("name") or "",
                "dynasty": parent.get("id"),
                "leaders": [ref(l) for l in (house.get("leaders") or []) if ref(l)],
                "found": house.get("found_date"),
            }
    with args.dump.open("rb") as handle:
        for ident, dyn in ijson.kvitems(handle, "dynasties", use_float=False):
            dynasties[int(ident)] = {"id": int(ident), "name": dyn.get("name") or "", "prestige": dyn.get("prestige_tot")}
    with args.dump.open("rb") as handle:
        for ident, char in ijson.kvitems(handle, "characters", use_float=False):
            house = char.get("house") or {}
            liege = char.get("liege") or {}
            characters[int(ident)] = {
                "id": int(ident),
                "name": char.get("name") or "",
                "nick": char.get("nick") or "",
                "female": bool(char.get("female")),
                "birth": char.get("birth"),
                "death": char.get("date") if char.get("dead") else None,
                "house": ref(house),
                "house_name": house.get("name") or "",
                "liege": ref(liege),
                "parents": [ref(p) for p in (char.get("parents") or []) if ref(p)],
                "children": [ref(c) for c in (char.get("children") or []) if ref(c)],
                "spouses": [ref(s) for s in (char.get("spouses") or []) if ref(s)],
                "titles": [ref(t) for t in (char.get("titles") or []) if ref(t)],
                "faith": (char.get("faith") or {}).get("name"),
                "culture": (char.get("culture") or {}).get("name"),
                "traits": [str(t) for t in (char.get("traits") or []) if t][:6],
                "skills": [int(s) for s in (char.get("skills") or []) if isinstance(s, (int, float))][:6],
                "prestige": round(char.get("prestige") or 0),
                "piety": round(char.get("piety") or 0),
                "kills": len(char.get("kills") or []),
                "memories": [ref(m) for m in (char.get("memories") or []) if ref(m)],
                # Игра пишет причину смерти уже локализованной строкой ("во сне", "в сражении"),
                # но иногда с разметкой — чистим её здесь, а не в летописи.
                "cause": clean_cause(char.get("reason")),
            }
    # Держатель титула — человек, а не de_facto (это сюзерен-титул).
    from titles import attach_holders

    holder_stats = attach_holders(titles, characters)
    print(
        f"держатели: по списку персонажа {holder_stats['by_person']}, "
        f"по истории {holder_stats['by_history']}, без держателя {holder_stats['none']}",
        flush=True,
    )

    with args.dump.open("rb") as handle:
        for ident, mem in ijson.kvitems(handle, "memories", use_float=False):
            mtype = (mem.get("type") or "").strip()
            kind = memory_kind(mtype)
            if not kind:
                continue
            participants = mem.get("participants") or {}
            variables = mem.get("variables") or {}
            # Память о титуле: что за титул, почему сменился держатель и кто новый.
            # Без этих трёх полей строка «потерян важный титул» идёт без имени.
            landed = variables.get("landed_title")
            reason = variables.get("reason")
            if isinstance(reason, dict):
                reason = reason.get("String") or reason.get("Id")
            memories.append(
                {
                    "id": int(ident),
                    "date": mem.get("date"),
                    "type": mtype,
                    "kind": kind,
                    "p": {role: ref(v) for role, v in participants.items() if ref(v)},
                    # Имена приходят уже готовыми — не теряем их при переходе на числа.
                    "pNames": {
                        role: (v.get("name") if isinstance(v, dict) else None)
                        for role, v in participants.items()
                    },
                    "cbKind": (variables.get("war_cb") or {}).get("String")
                    if isinstance(variables.get("war_cb"), dict)
                    else None,
                    "warTitle": ref(variables.get("war_title"))
                    if isinstance(variables.get("war_title"), dict)
                    else None,
                    "titleId": ref(landed) if isinstance(landed, dict) else None,
                    "titleReason": normalize_action(str(reason)) if reason is not None else None,
                    "titleHolder": ref(participants.get("new_holder")) if isinstance(participants.get("new_holder"), dict) else None,
                    "role": memory_role(mtype),
                }
            )

    # История титулов из сейва: в дампе она обрывается на дате старта партии.
    title_stats = merge_history(titles, extra.get("titles") or {}, extra.get("names") or {})
    if title_stats["rows"]:
        print(
            f"история титулов: склеено {title_stats['titles']} из сейва, "
            f"записей {title_stats['rows']}, новых {title_stats['added']}",
            flush=True,
        )
    repeated = dedupe(titles)
    if repeated:
        print(f"история титулов: повторов схлопнуто {repeated}", flush=True)

    # Память знает причину, история — факт: сводим их в одну запись.
    memory_owners = {
        mem_id: cid
        for cid, person in characters.items()
        for mem_id in person.get("memories") or []
    }
    title_memories = [
        {
            "id": mem["id"],
            "date": mem.get("date"),
            "kind": "loss" if mem["kind"] == "title_loss" else "gain",
            "title": mem.get("titleId"),
            "reason": mem.get("titleReason"),
            "newHolder": mem.get("titleHolder"),
        }
        for mem in memories
        if mem.get("titleId") and mem["kind"] in ("title_loss", "ruler")
    ]
    if title_memories:
        evidence = attach_memory(titles, title_memories, memory_owners)
        print(
            f"память о титулах: найдено пары {evidence['matched']}, "
            f"добавлено {evidence['added']}, причин проставлено {evidence['reasoned']}, "
            f"расхождений с историей {evidence['conflict']}",
            flush=True,
        )

    # Смены без держателя и по две записи на дату: в сейве такое бывает буквально.
    cleanup = reconcile(titles)
    if cleanup["no_holder_merged"] or cleanup["no_holder_dropped"] or cleanup["same_day_dropped"]:
        print(
            f"история титулов: склеено без имени {cleanup['no_holder_merged']}, "
            f"оставлено без имени {cleanup['no_holder_kept']}, "
            f"схлопнуто дублей на дату {cleanup['same_day_dropped']}",
            flush=True,
        )
    print(f"титулов {len(titles)}, персонажей {len(characters)}, домов {len(houses)}, воспоминаний {len(memories)}", flush=True)

    key_index = {tile.get("key"): tile["id"] for tile in titles.values() if tile.get("key")}
    # id титула в сейве → имя в мире: id в дампе переиндексированы, склейка по key.
    save_title_names: dict[str, str] = {}
    for save_id, title_key in (extra.get("title_keys") or {}).items():
        tile = titles.get(key_index.get(title_key, -1))
        if tile and tile.get("name"):
            save_title_names[str(save_id)] = tile["name"]
    date = current_date or "0894-01-01"
    now_year = year_of(date) or 894

    # ------------------------------------------------------------- державы
    def holder_at(title_id: int, when: str) -> int | None:
        tile = titles.get(title_id)
        if not tile:
            return None
        best = None
        for t_date, t_holder, _action, _source in tile["history"]:
            if isinstance(t_date, str) and t_date <= when:
                best = t_holder
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
                if titles[capital]["tier"] == "Barony":
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
        holder = holder_at(tile["id"], date)
        if not holder:
            continue
        realm_id = top_liege(holder)
        if not realm_id:
            continue
        realm = realms.setdefault(realm_id, {"id": realm_id, "counties": [], "provinces": []})
        realm["counties"].append(tile["id"])
        for prov in provinces_of(tile["id"]):
            if prov in centroids:
                province_realm[prov] = realm_id
                realm["provinces"].append(prov)

    for realm_id, realm in realms.items():
        ruler = characters.get(realm_id, {})
        own = sorted(
            (titles[t] for t in ruler.get("titles", []) if t in titles and is_shown(titles[t])),
            key=lambda t: RANK.get(t["tier"], 9),
        )
        best = own[0] if own else None
        realm["ruler"] = ruler.get("name")
        realm["nick"] = ruler.get("nick")
        realm["house"] = ruler.get("house")
        realm["house_name"] = ruler.get("house_name")
        realm["title"] = best["name"] if best else None
        realm["tier"] = best["tier"] if best else None
        prov = capital_province(best["id"]) if best else None
        realm["capital"] = prov
        realm["xy"] = centroids.get(prov) if prov else None
        realm["birth"] = ruler.get("birth")
        realm["death"] = ruler.get("death")
        realm["prestige"] = ruler.get("prestige") or 0
        realm["traits"] = ruler.get("traits") or []
        realm["titleId"] = best["id"] if best else None

    # Вера и культура державы — по её графствам на дату сейва.
    realm_faiths: dict[int, Counter] = defaultdict(Counter)
    realm_cultures: dict[int, Counter] = defaultdict(Counter)
    for tile in titles.values():
        if tile["tier"] != "County":
            continue
        holder = holder_at(tile["id"], date)
        if not holder:
            continue
        realm_id = top_liege(holder)
        if not realm_id:
            continue
        if tile.get("faith"):
            realm_faiths[realm_id][tile["faith"]] += 1
        if tile.get("culture"):
            realm_cultures[realm_id][tile["culture"]] += 1

    for realm_id, realm in realms.items():
        faiths_here = realm_faiths.get(realm_id)
        cultures_here = realm_cultures.get(realm_id)
        realm["faith"] = faiths_here.most_common(1)[0][0] if faiths_here else None
        realm["faithShare"] = round(faiths_here.most_common(1)[0][1] / sum(faiths_here.values()), 2) if faiths_here else None
        realm["faiths"] = faiths_here.most_common(3) if faiths_here else []
        realm["culture"] = cultures_here.most_common(1)[0][0] if cultures_here else None
        realm["cultureShare"] = round(cultures_here.most_common(1)[0][1] / sum(cultures_here.values()), 2) if cultures_here else None

    # Соседство держав — для рассказа о том, кто с кем граничит.
    realm_adjacency: dict[int, set[int]] = defaultdict(set)
    for a, b in adjacent:
        ra, rb = province_realm.get(a), province_realm.get(b)
        if ra and rb and ra != rb:
            realm_adjacency[ra].add(rb)
            realm_adjacency[rb].add(ra)
    for a, b in straits:
        ra, rb = province_realm.get(a), province_realm.get(b)
        if ra and rb and ra != rb:
            realm_adjacency[ra].add(rb)
            realm_adjacency[rb].add(ra)

    # ------------------------------------------------------------- кольца
    player_id = (players[0] or {}).get("character") if players else None
    player = characters.get(player_id or -1, {})
    player_realm = top_liege(player_id) if player_id else None
    anchor = realms.get(player_realm or -1, {}).get("xy")
    if not anchor:
        for tid in player.get("titles", []):
            prov = capital_province(tid)
            if prov and prov in centroids:
                anchor = centroids[prov]
                break

    graph: dict[int, set[int]] = defaultdict(set)

    def link(a: int, b: int) -> None:
        ra, rb = province_realm.get(a), province_realm.get(b)
        if ra and rb and ra != rb:
            graph[ra].add(rb)
            graph[rb].add(ra)

    for a, b in adjacent:
        link(a, b)
    for a, b in straits:
        link(a, b)

    political = {player_realm: 0} if player_realm else {}
    frontier = [player_realm] if player_realm else []
    while frontier:
        nxt = []
        for node in frontier:
            for other in graph.get(node, ()):
                if other not in political:
                    political[other] = political[node] + 1
                    nxt.append(other)
        frontier = nxt

    def geo_ring(dist: float | None) -> int | None:
        if dist is None:
            return None
        for index, band in enumerate(GEO_BANDS, start=1):
            if dist < band:
                return index
        return 4

    def distance(xy) -> float | None:
        if not anchor or not xy:
            return None
        return math.hypot(xy[0] - anchor[0], xy[1] - anchor[1])

    def direction(xy) -> str:
        if not anchor or not xy:
            return ""
        angle = math.degrees(math.atan2(-(xy[1] - anchor[1]), xy[0] - anchor[0])) % 360
        names = ["восток", "северо-восток", "север", "северо-запад", "запад", "юго-запад", "юг", "юго-восток"]
        return names[int((angle + 22.5) // 45) % 8]

    for realm_id, realm in realms.items():
        dist = distance(realm.get("xy"))
        pol = political.get(realm_id)
        geo = geo_ring(dist)
        realm["distance"] = round(dist) if dist is not None else None
        realm["direction"] = direction(realm.get("xy"))
        realm["political"] = pol
        realm["geo"] = geo
        realm["by_sea"] = pol is None and geo is not None
        realm["ring"] = min([r for r in (pol, geo) if r is not None], default=4)
        realm["size"] = len(realm["counties"])
        # Без титула держава остаётся без имени: номер вместо названия в летопись не идёт.
        # Называем по правителю — это то, что о ней известно.
        ruler_name = characters.get(realm.get("ruler") or -1, {}).get("name")
        realm["name"] = realm.get("title") or (f"владение {ruler_name}" if ruler_name else "дальняя держава")

    # Владения по годам и смена государей — материал для досье рассказчика.
    county_histories = [
        (tile["id"], [(d, h) for d, h, _a, _s in tile["history"] if isinstance(d, str)], tile["holder"])
        for tile in titles.values()
        if tile["tier"] == "County"
    ]

    def county_holder_at(tile_id: int, year: int, hist: list, current):
        best = current
        for when, who in hist:
            try:
                stamp = int(when[:4])
            except ValueError:
                continue
            if stamp <= year:
                best = who
        return best

    known_realm_ids = [rid for rid, realm in realms.items() if realm["ring"] <= 3]
    sample_years = list(range(now_year - 60, now_year + 1, 5))
    domain_series: dict[int, list] = {rid: [] for rid in known_realm_ids}
    for year in sample_years:
        counts: Counter = Counter()
        for tile_id, hist, current in county_histories:
            holder = county_holder_at(tile_id, year, hist, current)
            if not holder:
                continue
            realm_id = top_liege(holder)
            if realm_id in domain_series:
                counts[realm_id] += 1
        for rid in known_realm_ids:
            domain_series[rid].append([year, counts.get(rid, 0)])

    for rid, series in domain_series.items():
        realms[rid]["domain"] = series

    # Соседи и грубая карта клетками — чтобы рассказать о мире текстом.
    for rid, realm in realms.items():
        neighbors = sorted(
            realms[n]["name"] for n in realm_adjacency.get(rid, ()) if n in realms and realms[n]["ring"] <= 3
        )
        realm["neighbors"] = neighbors[:8]

    GW, GH = 44, 22
    xs = [xy[0] for xy in centroids.values()]
    ys = [xy[1] for xy in centroids.values()]
    minx, maxx = (min(xs), max(xs)) if xs else (0, 1)
    miny, maxy = (min(ys), max(ys)) if ys else (0, 1)
    cell_counts: dict[tuple[int, int], Counter] = defaultdict(Counter)
    for pid, xy in centroids.items():
        rid = province_realm.get(pid)
        if not rid or realms.get(rid, {}).get("ring", 4) > 3:
            continue
        gx = int((xy[0] - minx) / max(maxx - minx, 1) * (GW - 1))
        gy = int((xy[1] - miny) / max(maxy - miny, 1) * (GH - 1))
        cell_counts[(gy, gx)][rid] += 1
    grid = [[0] * GW for _ in range(GH)]
    for (gy, gx), counter in cell_counts.items():
        grid[gy][gx] = counter.most_common(1)[0][0]

    for rid, realm in realms.items():
        tile = titles.get(realm.get("titleId") or -1)
        if not tile:
            continue
        entries = [(d, h) for d, h, _a, _s in tile["history"] if isinstance(d, str)]
        rulers = []
        for index, (when, who) in enumerate(entries):
            end = entries[index + 1][0] if index + 1 < len(entries) else date
            person = characters.get(who or -1, {})
            if not person:
                continue
            rulers.append(
                {
                    "from": when[:4],
                    "to": end[:4],
                    # Имя бывает пустым (безымянный ребёнок или заглушка в дампе):
                    # лучше честное «имени не сохранилось», чем пустая строка.
                    "name": person.get("name") or None,
                    "faith": person.get("faith"),
                    "culture": person.get("culture"),
                }
            )
        realm["rulers"] = rulers[-5:]

    # Второй проход: у державы без титула имя появляется только теперь, когда известен правитель.
    for _rid, realm in realms.items():
        if (realm.get("name") or "") in ("дальняя держава",) or re.fullmatch(r"держава \d+", realm.get("name") or ""):
            if realm.get("ruler"):
                realm["name"] = f"владение {realm['ruler']}"

    def realm_name_of(cid: int | None) -> str | None:
        """Название державы, к которой принадлежит человек — вместо «дальнего двора».

        Держава без титула зовётся «держава 55493»: это номер, а не имя.
        В летопись номер не идёт — там будет «дальние земли».
        """
        if not cid:
            return None
        realm_id = top_liege(cid)
        name = realms.get(realm_id, {}).get("name") if realm_id else None
        if not name or re.fullmatch(r"держава \d+", str(name)):
            return None
        return name

    # ------------------------------------------------------------- династия
    house_id = player.get("house")
    house = houses.get(house_id or -1, {})
    dynasty_id = house.get("dynasty")
    dynasty = dynasties.get(dynasty_id or -1, {"id": dynasty_id, "name": house.get("name") or ""})
    dynasty_houses = {hid for hid, h in houses.items() if h.get("dynasty") == dynasty_id and dynasty_id} or {house_id}

    members = [cid for cid, c in characters.items() if c["house"] in dynasty_houses]
    member_set = set(members)

    def person_ring(cid: int | None) -> int:
        if not cid or cid not in characters:
            return 4
        if characters[cid]["house"] in dynasty_houses:
            return 0
        realm = top_liege(cid)
        return realms.get(realm, {}).get("ring", 4) if realm else 4

    # поколения династии
    gen: dict[int, int] = {}
    by_parent: dict[int, list[int]] = defaultdict(list)
    for cid in members:
        for parent in characters[cid]["parents"]:
            if parent in member_set:
                by_parent[parent].append(cid)

    roots = [cid for cid in members if not any(p in member_set for p in characters[cid]["parents"])]
    queue = [(cid, 0) for cid in roots]
    while queue:
        cid, depth = queue.pop(0)
        if gen.get(cid, -1) >= depth:
            continue
        gen[cid] = depth
        for child in by_parent.get(cid, []):
            queue.append((child, depth + 1))

    # пришлые супруги встают на поколение своей половины
    spouses_of_members = set()
    for cid in members:
        for sid in characters[cid]["spouses"]:
            spouses_of_members.add(sid)
    for sid in spouses_of_members:
        if sid in gen:
            continue
        partners = [p for p in characters.get(sid, {}).get("spouses", []) if p in gen]
        if partners:
            gen[sid] = max(gen[p] for p in partners)

    tree_ids = member_set | {sid for sid in spouses_of_members if sid in characters}
    for cid in list(tree_ids):
        for parent in characters[cid]["parents"]:
            tree_ids.add(parent)
        for child in characters[cid]["children"]:
            tree_ids.add(child)

    def titles_of(cid: int) -> list[dict]:
        return sorted(
            (titles[t] for t in characters[cid]["titles"] if t in titles and is_shown(titles[t])),
            key=lambda t: RANK.get(t["tier"], 9),
        )

    def tenure_of(cid: int, tile: dict) -> str | None:
        """С какого года держит титул — по истории, а не по догадке."""
        since = None
        for when, holder, _action, _source in tile["history"]:
            if not isinstance(when, str):
                continue
            if holder == cid:
                since = since or when
            elif holder:
                # Титул перешёл к другому — отсчёт начинается заново.
                since = None
        return since

    def _tenures(cid: int, own: list[dict]) -> list[list]:
        """Владения для досье: одно имя — одна строка, год может быть пустым."""
        seen: dict[str, int | None] = {}
        for tile in own[:6]:
            name = tile["name"]
            if name in seen:
                continue
            seen[name] = year_of(tenure_of(cid, tile))
            if len(seen) >= 4:
                break
        return [[name, year] for name, year in seen.items()]

    # Кто когда-либо держал титул — по истории владений, а не только по текущему списку.
    ever_held: set[int] = set()
    for tile in titles.values():
        for _d, h, _a, _s in tile["history"]:
            if h:
                ever_held.add(h)
        if tile.get("holder"):
            ever_held.add(tile["holder"])

    people = []
    provinces = map_data["provinces"]
    for cid in sorted(tree_ids):
        person = characters.get(cid)
        if not person:
            continue
        own = titles_of(cid)
        own_all = [titles[t] for t in person["titles"] if t in titles]
        camp_titles = [t for t in own_all if "laamp" in ((t.get("key") or "") + (t.get("name") or "")).lower()]
        camp_title = camp_titles[0] if camp_titles else None
        camp_province = capital_province(camp_title["id"]) if camp_title else None
        camp_at = provinces.get(str(camp_province), {}).get("name") if camp_province else None
        # Названия провинций иногда приходят ключом ("GETEINA") — берём подпись из титула.
        if camp_at and camp_at.isupper():
            camp_at = (titles.get((camp_title or {}).get("capital")) or {}).get("name") or None
        camp_name = None
        if camp_title:
            raw_name = (camp_title.get("name") or "").strip()
            if raw_name and not raw_name.startswith("X ") and "laamp" not in raw_name.lower():
                camp_name = raw_name
        people.append(
            {
                "id": cid,
                "name": person["name"],
                "nick": person["nick"],
                "female": person["female"],
                "birth": person["birth"],
                "death": person["death"],
                "house": person["house_name"],
                "houseId": person["house"],
                "culture": person.get("culture"),
                "faith": person.get("faith"),
                "branch": person["house_name"],
                "cadet": person["house"] != house_id,
                "kin": person["house"] in dynasty_houses,
                "landed": bool(own),
                "camp": bool(camp_titles) and not own,
                "campName": camp_name,
                "campAt": camp_at,
                "gen": gen.get(cid, 0),
                "father": person["parents"][0] if person["parents"] else None,
                "mother": person["parents"][1] if len(person["parents"]) > 1 else None,
                "spouses": person["spouses"],
                "children": person["children"],
                "traits": person["traits"],
                "skills": person["skills"],
                "prestige": person["prestige"],
                "piety": person["piety"],
                "kills": person["kills"],
                "title": own[0]["name"] if own else None,
                "tier": own[0]["tier"] if own else None,
                # Мёртвый землёй не владеет: в дампе его титул остаётся, но в «Кто чем
                # владеет» ему не место — он только «держал», и это видно по held.
                "titles": [] if person.get("death") else list(dict.fromkeys(t["name"] for t in own))[:4],
                # Владения с годом: «Сичуань с 887» — из истории титула, не из догадки.
                # Год известен не у всех титулов: пустой год — титул всё равно показываем,
                # иначе из «Кто чем владеет» пропадают целые владения. Одно имя — одна строка:
                # графство и герцогство с одним названием не должны двоиться.
                "tenures": [] if person.get("death") else _tenures(cid, own),
                # Феодальное подчинение: прямой сюзерен и верхний, кому служит.
                "liege": person.get("liege"),
                "suzerain": suzerain_of(cid, characters),
                "ring": 0 if person["house"] in dynasty_houses or cid in spouses_of_members else person_ring(cid),
            }
        )

    # Ветви династии: каждый дом — отдельная ветвь, со своими годами и главой.
    branches = []
    for hid in sorted(dynasty_houses):
        members_branch = [p for p in people if p["houseId"] == hid]
        if not members_branch:
            continue
        births = [year_of(p["birth"]) for p in members_branch if p.get("birth")]
        deaths = [year_of(p["death"]) for p in members_branch if p.get("death")]
        info = houses.get(hid, {})
        leaders = [characters[i]["name"] for i in (info.get("leaders") or []) if i in characters][:3]
        if not leaders:
            leaders = [p["name"] for p in sorted(members_branch, key=lambda p: -(p.get("prestige") or 0))[:2]]
        branches.append(
            {
                "id": hid,
                "name": info.get("name") or members_branch[0].get("house") or "дом",
                "main": hid == house_id,
                "members": len(members_branch),
                "alive": sum(1 for p in members_branch if not p.get("death")),
                "from": min(births) if births else year_of(info.get("found") or ""),
                "to": max(deaths) if deaths else None,
                "prestige": sum(p.get("prestige") or 0 for p in members_branch),
                "leaders": leaders,
            }
        )
    branches.sort(key=lambda b: (not b["main"], -b["members"]))

    # ------------------------------------------------------------- события
    # Кому принадлежит воспоминание — уже собрано, когда сводили память о титулах.
    owners = memory_owners

    def fade(grade: int, when: str | None, ring: int) -> int:
        if ring == 0:
            return 0
        year = year_of(when)
        if not year:
            return grade
        age = now_year - year
        limit = {1: 60, 2: 40, 3: 20, 4: 8}.get(ring, 8)
        if age <= limit // 2:
            return grade
        if age <= limit:
            return min(4, grade + 1)
        return 4

    events: list[dict] = []

    for cid, person in characters.items():
        death = person["death"]
        if not death:
            continue
        ring = person_ring(cid)
        if ring == 4 and not (person["house"] in dynasty_houses):
            continue
        own = titles_of(cid)
        events.append(
            {
                "kind": "death",
                "date": death,
                "ring": ring,
                "grade": fade(ring, death, ring),
                "who": cid,
                "title": own[0]["name"] if own else None,
                "tier": own[0]["tier"] if own else None,
                "realm": realm_name_of(cid),
                "kin": person["house"] in dynasty_houses,
                "cause": person.get("cause"),
                "v": variant(cid, death),
            }
        )

    for tile in titles.values():
        if tile["tier"] not in ("Empire", "Kingdom", "Duchy", "County"):
            continue
        for when, holder, action, source in tile["history"]:
            year = year_of(when)
            if not year or year < now_year - 150:
                continue
            is_kin = characters.get(holder or -1, {}).get("house") in dynasty_houses
            # графства — только свои: чужие графства в хронику не идут
            if tile["tier"] == "County" and not is_kin:
                continue
            realm = top_liege(holder) if holder else None
            ring = realms.get(realm, {}).get("ring", 4) if realm else person_ring(holder)
            if ring == 4 and tile["tier"] not in ("Empire", "Kingdom"):
                continue
            events.append(
                {
                    "kind": "succession",
                    "date": when,
                    "ring": ring,
                    "grade": fade(ring, when, ring),
                    "who": holder,
                    "title": tile["name"],
                    "titleKey": tile["key"],
                    "tier": tile["tier"],
                    "action": normalize_action(action),
                    "why": reason_text(normalize_action(action), "ru"),
                    "source": source,
                    "realm": realm_name_of(holder),
                    "kin": characters.get(holder or -1, {}).get("house") in dynasty_houses,
                    "v": variant(holder, when, tile["id"]),
                }
            )

    # Потеря титула: память знает и титул, и того, кому он отошёл.
    # Раньше это событие шло без имени титула — теперь имя есть.
    title_by_id = titles
    seen_loss: set[tuple] = set()
    for mem in title_memories:
        if mem["kind"] != "loss":
            continue
        tile = title_by_id.get(mem["title"] or -1)
        if not tile or tile["tier"] not in ("Empire", "Kingdom", "Duchy", "County"):
            continue
        owner = memory_owners.get(mem["id"])
        if not owner:
            continue
        is_kin = characters.get(owner, {}).get("house") in dynasty_houses
        if tile["tier"] == "County" and not is_kin:
            continue
        taker = mem.get("newHolder")
        slot = (tile["id"], mem.get("date"), owner)
        if slot in seen_loss:
            continue
        seen_loss.add(slot)
        realm = top_liege(owner) or owner
        ring = realms.get(realm, {}).get("ring", 4)
        if ring == 4 and tile["tier"] not in ("Empire", "Kingdom") and not is_kin:
            continue
        events.append(
            {
                "kind": "title_loss",
                "date": mem.get("date"),
                "ring": ring,
                "grade": fade(ring, mem.get("date"), ring),
                "who": owner,
                "who2": taker,
                "whoName": characters.get(owner, {}).get("name"),
                "who2Name": characters.get(taker or -1, {}).get("name"),
                "title": tile["name"],
                "titleKey": tile["key"],
                "tier": tile["tier"],
                "action": mem.get("reason"),
                "why": reason_text(mem.get("reason"), "ru"),
                "source": "memory",
                "realm": realm_name_of(owner),
                "kin": is_kin,
                "v": variant(owner, mem.get("date"), tile["id"]),
            }
        )

    # Войны, у которых есть повод из сейва, пишем по сейву; воспоминание о том же
    # столкновении только повторяет факт без причины.
    save_war_pairs = {
        (war.get("attacker"), war.get("defender"))
        for war in (extra.get("wars") or [])
        if war.get("attacker")
    }

    for mem in memories:
        owner = owners.get(mem["id"])
        kind = mem["kind"]
        # Потерю титула собирает отдельный проход: там есть имя титула и новый держатель.
        if kind == "title_loss":
            continue
        ring = person_ring(owner) if owner else 4
        year = year_of(mem["date"])
        if not year:
            continue
        if ring == 4 and kind not in ("war", "war_win", "war_loss"):
            continue
        # личные заметки пишем только о своих
        if kind == "note" and ring > 1:
            continue
        if year < now_year - 60:
            continue
        other = None
        for role, pid in mem["p"].items():
            if pid != owner:
                other = pid
                break
        other_role = next((role for role, pid in mem["p"].items() if pid == other), None)
        other_name = mem.get("pNames", {}).get(other_role) if other_role else None
        if kind == "war" and ((owner, other) in save_war_pairs or (other, owner) in save_war_pairs):
            continue
        # Незнакомое воспоминание — запись, но только о своих: чужие бытовые заметки летопись засоряют.
        if kind == "note" and characters.get(owner or -1, {}).get("house") not in dynasty_houses:
            continue
        # Категория повода из памяти: причина есть и у давно закончившейся войны.
        cb_kind = mem.get("cbKind")
        label, family = WAR_MEMORY_CB.get(cb_kind, (None, None)) if cb_kind else (None, None)
        is_war = kind in ("war", "war_win", "war_loss")
        # Война без владельца никому не принадлежит: в летописи ей нечего делать.
        if is_war and not owner:
            continue
        # Получение титула: память знает, какого именно, и почему.
        mem_title = titles.get(mem.get("titleId") or -1) if mem.get("titleId") else None
        if mem_title and mem_title["tier"] not in ("Empire", "Kingdom", "Duchy", "County"):
            mem_title = None
        events.append(
            {
                "kind": kind,
                "date": mem["date"],
                "ring": ring,
                "grade": fade(ring, mem["date"], ring),
                "who": owner,
                "who2": other,
                "whoName": characters.get(owner or -1, {}).get("name"),
                "who2Name": other_name or characters.get(other or -1, {}).get("name"),
                "title": save_title_names.get(str(mem.get("warTitle"))) if mem.get("warTitle") else (mem_title["name"] if mem_title else None),
                "titleKey": mem_title["key"] if mem_title else None,
                "tier": mem_title["tier"] if mem_title else None,
                "action": mem.get("titleReason"),
                "why": reason_text(mem.get("titleReason"), "ru"),
                "source": "memory" if mem_title else None,
                "type": (label or ("война" if kind == "war" else mem["type"])) if is_war else mem["type"],
                "family": family if is_war else None,
                "cb": cb_kind if is_war else None,
                "role": mem.get("role") if kind == "war" else None,
                "realm": realm_name_of(owner),
                "kin": characters.get(owner or -1, {}).get("house") in dynasty_houses,
                "v": variant(mem["id"]),
            }
        )

    # ------------------------------------------------------------- войны из сейва
    # Воспоминания дают «где-то воевали»; сейв даёт повод, цель и стороны.
    wars_added = 0
    for war in extra.get("wars") or []:
        # Имя переменной не `date`: цикл в Python не создаёт области видимости,
        # и одна война подменяла дату сейва в meta.
        war_date = war.get("start")
        attacker = war.get("attacker")
        defender = war.get("defender")
        if not war_date or not attacker:
            continue
        target_key = (war.get("targets") or [None])[0]
        tile = titles.get(key_index.get(target_key, -1), {})
        target_name = tile.get("name") or (extra.get("names") or {}).get(target_key or "")
        family = cb_family(war.get("cb") or "")
        kin_attacker = characters.get(attacker, {}).get("house") in dynasty_houses
        kin_defender = characters.get(defender or -1, {}).get("house") in dynasty_houses
        role = "attack" if kin_attacker else "defend" if kin_defender else "third"

        # Исход: менялся ли держатель цели с начала войны к дате сейва.
        outcome = None
        outcome_holder = None
        if tile:
            before = holder_at(tile["id"], war_date)
            after = holder_at(tile["id"], war_date)
            if after and before != after:
                outcome = "attacker" if after == attacker else "other"
                outcome_holder = characters.get(after, {}).get("name")
            else:
                outcome = "none"
        ring = person_ring(attacker)
        events.append(
            {
                "kind": "war",
                "date": war_date,
                "ring": ring,
                "grade": fade(ring, war_date, ring),
                "who": attacker,
                "who2": defender,
                # Имена нужны и для тех, кого нет в дереве рода: в событиях их нет.
                "whoName": characters.get(attacker, {}).get("name"),
                "who2Name": characters.get(defender or -1, {}).get("name"),
                "title": target_name,
                "tier": tile.get("tier"),
                "type": cb_label(war.get("cb") or ""),
                "cb": war.get("cb") or "",
                "family": family,
                "role": role,
                "outcome": outcome,
                "outcomeHolder": outcome_holder,
                "allies": max(len(war.get("attackers") or []) - 1, 0) + max(len(war.get("defenders") or []) - 1, 0),
                "realm": realm_name_of(attacker),
                "kin": characters.get(attacker, {}).get("house") in dynasty_houses,
                "v": variant(attacker, war_date, war.get("id")),
            }
        )
        wars_added += 1
    if wars_added:
        print(f"войны из сейва: {wars_added} — с поводом и целью", flush=True)

    # Один человек в один день получил три титула — в летописи это одна весть.
    best_succession: dict[tuple, dict] = {}
    for event in events:
        if event["kind"] != "succession" or not event.get("who"):
            continue
        key = (event["date"], event["who"])
        current = best_succession.get(key)
        if current is None or RANK.get(event.get("tier"), 9) < RANK.get(current.get("tier"), 9):
            best_succession[key] = event
    events = [
        e
        for e in events
        if e["kind"] != "succession" or not e.get("who") or best_succession[(e["date"], e["who"])] is e
    ]

    events.sort(key=lambda e: (e["date"], e["kind"]))

    # Повторы: «снова в темнице» — это отдельные случаи, но читаются легче с пометкой.
    seen: dict[tuple, int] = {}
    for event in events:
        key = (event["kind"], event.get("who"))
        year = year_of(event["date"])
        if key[1] and year:
            previous = seen.get(key)
            event["repeat"] = event.get("repeat", 0) + 1 if previous and year - previous <= 8 else 0
            seen[key] = year
        else:
            event["repeat"] = 0

    print(f"событий собрано {len(events)}", flush=True)

    # ------------------------------------------------------------- молва
    rumors: dict[int, dict] = defaultdict(lambda: {"wars": 0, "deaths": 0, "successions": 0, "kin": 0})
    big = []
    for event in events:
        year = year_of(event["date"])
        if not year:
            continue
        if event["ring"] >= 4:
            key = {"war": "wars", "war_win": "wars", "war_loss": "wars", "death": "deaths", "succession": "successions"}.get(event["kind"])
            if key:
                rumors[year][key] += 1
        if event["kind"] == "succession" and event.get("tier") in ("Empire", "Kingdom") and event["ring"] >= 3:
            if len(big) < 40:
                big.append({"date": event["date"], "title": event.get("title"), "ring": event["ring"]})

    # ------------------------------------------------------------- имена
    names: dict[int, dict] = {}
    for event in events:
        for cid in (event.get("who"), event.get("who2")):
            if not cid or cid in names or cid not in characters:
                continue
            person = characters[cid]
            if not person["name"]:
                # Пустышка из дампа: имя не разрешилось. Лучше «сменился государь»,
                # чем строка с пустым именем.
                continue
            own = titles_of(cid)
            names[cid] = {
                "name": person["name"],
                "nick": person["nick"],
                "female": person["female"],
                "house": house_title(person["house_name"]) or "",
                "birth": person["birth"],
                "death": person["death"],
                "title": own[0]["name"] if own else None,
                "traits": person["traits"][:3],
                # Феодальное подчинение — нужно и карте, и хронике.
                "liege": person.get("liege"),
                "suzerain": suzerain_of(cid, characters),
            }
    for realm in realms.values():
        rid = realm["id"]
        if rid and rid not in names and realm.get("ruler"):
            names[rid] = {
                "name": realm.get("ruler"),
                "nick": realm.get("nick") or "",
                "female": False,
                "house": house_title(realm.get("house_name")) or "",
                "birth": realm.get("birth"),
                "death": realm.get("death"),
                "title": realm.get("title"),
                "traits": realm.get("traits") or [],
            }

    # ------------------------------------------------------------- сборка
    all_realms = list(realms.values())
    known = sorted(
        [r for r in all_realms if r["ring"] <= 3],
        key=lambda r: (r["ring"], r["distance"] if r["distance"] is not None else 10**9),
    )[:260]
    by_ring = defaultdict(int)
    for realm in all_realms:
        by_ring[realm["ring"]] += 1

    generations = []
    for g in sorted(set(gen.values())):
        members_g = [cid for cid, value in gen.items() if value == g and cid in member_set]
        if not members_g:
            continue
        births = [year_of(characters[c]["birth"]) for c in members_g if characters[c]["birth"]]
        deaths = [year_of(characters[c]["death"]) for c in members_g if characters[c]["death"]]
        # Поколение с живым членом не закрыто: смерть части не должна ставить точку
        # всему поколению — иначе в досье «899—936», хотя трое ещё живы.
        still_alive = any(not characters[c]["death"] for c in members_g)
        generations.append(
            {
                "gen": g,
                "members": len(members_g),
                "from": min(births) if births else None,
                "to": None if still_alive else (max(deaths) if deaths else None),
                "names": [characters[c]["name"] for c in members_g][:6],
            }
        )

    # Эпохи — по главе рода: кто в этом году старший и самый знатный.
    def head_at(year: int) -> int | None:
        alive = []
        for cid in member_set:
            birth = year_of(characters[cid]["birth"])
            death = year_of(characters[cid]["death"])
            if birth and birth <= year and (death is None or death >= year):
                alive.append(cid)
        if not alive:
            return None

        def weight(cid: int):
            own = titles_of(cid)
            best = RANK.get(own[0]["tier"], 9) if own else 9
            return (best, -(characters[cid]["prestige"] or 0))

        return sorted(alive, key=weight)[0]

    periods = []
    birth_years = [year_of(characters[cid]["birth"]) for cid in member_set]
    birth_years = [y for y in birth_years if y]
    start_year = min(birth_years) if birth_years else now_year - 40
    current = None
    for year in range(start_year, now_year + 1):
        head = head_at(year)
        if head != current:
            if current is not None and periods:
                periods[-1]["to"] = year - 1
            periods.append({"name": f"Эпоха {characters[head]['name']}" if head else "Междуцарствие", "ruler": characters[head]["name"] if head else None, "from": year, "to": now_year})
            current = head
    periods = [p for p in periods if p["ruler"]]
    # Короткие междуцарствия не плодим: сглаживаем в предыдущую эпоху.
    merged: list[dict] = []
    for period in periods:
        if merged and (period["to"] - period["from"] < 8 or merged[-1]["to"] - merged[-1]["from"] < 8):
            merged[-1]["to"] = period["to"]
        else:
            merged.append(dict(period))
    periods = merged

    # Ветви династии: свой дом и кадетские.
    # Ветви династии: старший дом и кадетские.
    def founded_year(hid: int) -> int:
        value = (houses.get(hid, {}).get("found") or "")
        try:
            year = int(str(value)[:4])
        except ValueError:
            return 9999
        return year if 0 < year < 9000 else 9999

    senior_house = min(dynasty_houses, key=founded_year, default=house_id)
    for hid in dynasty_houses:
        info = houses.get(hid, {})
        if (info.get("name") or "") == (dynasty.get("name") or ""):
            senior_house = hid
            break

    branch_stats = []
    for hid in dynasty_houses:
        members_of = [cid for cid in member_set if characters[cid]["house"] == hid]
        if not members_of:
            continue
        births = [y for y in (year_of(characters[c]["birth"]) for c in members_of) if y]
        deaths = [y for y in (year_of(characters[c]["death"]) for c in members_of) if y]
        info = houses.get(hid, {})
        branch_stats.append(
            {
                "id": hid,
                "name": info.get("name") or "",
                "senior": hid == senior_house,
                "player": hid == house_id,
                "cadet": hid != senior_house,
                "members": len(members_of),
                "from": min(births) if births else None,
                "to": max(deaths) if deaths else None,
                "founded": info.get("found") or "",
            }
        )
    branch_stats.sort(key=lambda b: (not b["senior"], not b["player"], -b["members"]))

    origin_years = [y for y in (founded_year(h) for h in dynasty_houses) if y < 9999]
    dynasty_from = min(origin_years) if origin_years else None
    if not dynasty_from:
        kin_births = [y for y in (year_of(characters[c]["birth"]) for c in member_set) if y]
        dynasty_from = min(kin_births) if kin_births else None

    # ---------- родословная ----------
    # Кровный родитель — тот, чей дом в династии: мать или отец. В CK3 ребёнок от
    # матрилинейного брака носит дом матери, поэтому идти только по отцу нельзя:
    # 69 родичей из 255 оказались бы «неродными».
    kin_by_id = {p["id"]: p for p in people if p.get("kin")}

    def blood_parent(person):
        parents = [ix for ix in (person.get("father"), person.get("mother")) if ix in kin_by_id]
        if not parents:
            return None
        same = [ix for ix in parents if kin_by_id[ix].get("house") == person.get("house")]
        return (same or parents)[0]

    children = {}
    for person in kin_by_id.values():
        parent = blood_parent(person)
        if parent:
            children.setdefault(parent, []).append(person["id"])

    def subtree(pid):
        seen, stack = [], [pid]
        while stack:
            current = stack.pop()
            for child in children.get(current, []):
                seen.append(child)
                stack.append(child)
        return seen

    roots = [pid for pid in kin_by_id if blood_parent(kin_by_id[pid]) is None]
    roots.sort(key=lambda pid: (-len(subtree(pid)), kin_by_id[pid].get("birth") or "9999"))
    trunk_id = roots[0] if roots else None
    player_id = player.get("id")

    lines = []
    line_of: dict[int, int] = {}
    depth_of: dict[int, int] = {}

    def add_line(founder_id: int, kind: str, members: list[int], index: int):
        for member in members:
            line_of[member] = index
        # Глубина — шаги вниз от основателя линии, а не вверх по родителям.
        member_set = set(members)
        depths = {founder_id: 0}
        queue = [founder_id]
        while queue:
            current = queue.pop(0)
            for child in children.get(current, []):
                if child in member_set and child not in depths:
                    depths[child] = depths[current] + 1
                    queue.append(child)
        for member in members:
            depth_of[member] = depths.get(member, 0)
        founder = kin_by_id[founder_id]
        lines.append(
            {
                "id": index,
                "founderId": founder_id,
                "founder": founder["name"],
                "house": founder.get("house"),
                "birth": founder.get("birth"),
                "size": len(members),
                "kind": kind,
                "senior": player_id in members,
            }
        )

    index = 0
    if trunk_id is not None:
        # Ствол — сам родоначальник: один узел, от которого расходятся линии сыновей.
        add_line(trunk_id, "trunk", [trunk_id], index)
        index += 1
        sons = sorted(children.get(trunk_id, []), key=lambda cid: kin_by_id[cid].get("birth") or "9999")
        for son in sons:
            if not children.get(son):
                continue                      # сын без потомства — узел в стволе, не линия
            add_line(son, "cadet", [son] + subtree(son), index)
            index += 1

    # Остальные корни — отдельные ветви: связь с общим стволом в сейве не сохранилась.
    for root_id in roots:
        if root_id == trunk_id:
            continue
        add_line(root_id, "detached", [root_id] + subtree(root_id), index)
        index += 1

    # Сыновья без потомства не стали отдельными линиями — приписываем их к линии отца,
    # иначе они пропадут из рода.
    for person in kin_by_id.values():
        pid = person["id"]
        if pid in line_of:
            continue
        parent = blood_parent(person)
        if parent and parent in line_of:
            line_of[pid] = line_of[parent]
            depth_of[pid] = depth_of.get(parent, 0) + 1
        elif trunk_id is not None and trunk_id in line_of:
            line_of[pid] = line_of[trunk_id]
            depth_of[pid] = 1

    for line in lines:
        line["size"] = sum(1 for value in line_of.values() if value == line["id"])

    player_line = None
    for line in lines:
        if line["senior"]:
            line["kind"] = "senior"
            player_line = line["id"]

    # Кто чей предок: цепочка от игрока вверх по кровному родителю.
    ancestry = set()
    cursor = player_id if player_id in kin_by_id else None
    while cursor:
        ancestry.add(cursor)
        cursor = blood_parent(kin_by_id[cursor])

    for person in people:
        pid = person["id"]
        if pid in line_of:
            person["line"] = line_of[pid]
            person["depth"] = depth_of.get(pid, 0)
            person["ancestor"] = pid in ancestry
            person["seniorLine"] = bool(lines and lines[line_of[pid]]["senior"])
        else:
            person["line"] = None
            person["depth"] = None
            person["ancestor"] = False
            person["seniorLine"] = False
        parent_id = blood_parent(person) if person.get("kin") else None
        person["blood"] = parent_id
        # Сквозной слой: сколько шагов от корня рода по кровной линии. Это то, что видно
        # в конспекте как отступ — дети на слой глубже, внуки ещё на слой.
        steps = 0
        walker = person
        guard = set()
        while walker.get("kin") and blood_parent(walker) and blood_parent(walker) not in guard and steps < 40:
            guard.add(blood_parent(walker))
            walker = kin_by_id[blood_parent(walker)]
            steps += 1
        person["gen"] = steps if person.get("kin") else None
        # Новый дом в середине рода — точка, где начинается кадетская ветвь.
        person["newHouse"] = bool(parent_id and kin_by_id[parent_id].get("house") != person.get("house"))

    lineage = {
        "trunk": trunk_id,
        "playerLine": player_line,
        "lines": sorted(
            lines,
            key=lambda item: (item["kind"] != "trunk", item["kind"] != "senior", -item["size"]),
        ),
    }

    # Кто «отметился»: владеет титулом или был участником важных дел.
    significant = {"war", "battle", "war_win", "war_loss", "title_loss", "title_gain", "succession", "prison", "ruler"}
    notable_ids = {p["id"] for p in people if p.get("landed") or p.get("held")}
    for event in events:
        if event.get("kind") in significant:
            for cid in (event.get("who"), event.get("who2")):
                if cid:
                    notable_ids.add(cid)
    for person in people:
        person["notable"] = person["id"] in notable_ids
        person["held"] = person["id"] in ever_held

    payload = {
        "meta": {
            "date": date,
            "year": now_year,
            "source": args.dump.name,
            "player": {
                "id": player_id,
                "name": player.get("name"),
                "nick": player.get("nick"),
                "house": player.get("house_name"),
                "houseId": house_id,
                "dynasty": dynasty.get("name"),
                "realm": player_realm,
                "title": realms.get(player_realm or -1, {}).get("title"),
                "birth": player.get("birth"),
                "landless": anchor is not None and not realms.get(player_realm or -1, {}).get("xy"),
            },
            "counts": {
                "realms": len(all_realms),
                "known": len(known),
                "people": len(people),
                "dynasty": len(members),
                "events": len(events),
            },
            "byRing": dict(sorted(by_ring.items())),
            "generations": generations,
            "periods": periods,
            "dynastyFrom": dynasty_from,
            "map": args.map.name if args.map else None,
        },
        "realms": [
            {
                "id": r["id"],
                "name": r["name"],
                "title": r.get("title"),
                "tier": r.get("tier"),
                "ruler": r.get("ruler"),
                "nick": r.get("nick"),
                "house": r.get("house_name"),
                "ring": r["ring"],
                "political": r.get("political"),
                "geo": r.get("geo"),
                "bySea": r.get("by_sea", False),
                "distance": r.get("distance"),
                "direction": r.get("direction"),
                "size": r.get("size"),
                "prestige": r.get("prestige"),
                "birth": r.get("birth"),
                "death": r.get("death"),
                "faith": r.get("faith"),
                "faithShare": r.get("faithShare"),
                "faiths": r.get("faiths"),
                "culture": r.get("culture"),
                "cultureShare": r.get("cultureShare"),
                "domain": r.get("domain"),
                "rulers": r.get("rulers"),
                "neighbors": r.get("neighbors"),
            }
            for r in known
        ],
        "people": people,
        "events": events,
        "rumors": {
            "years": {str(y): v for y, v in sorted(rumors.items())},
            "big": big,
        },
        "branches": branches,
        "names": {str(k): v for k, v in names.items()},
        "mapGrid": {"w": GW, "h": GH, "cells": grid},
        "dynasty": {"id": dynasty_id, "name": dynasty.get("name"), "prestige": float(dynasty.get("prestige") or 0), "houses": branch_stats},
        "lineage": lineage,
    }

    # Земли рода: графства, которые держат родичи, — где бы они ни служили.
    dynasty_people = {cid for cid, ch in characters.items() if ch.get("house") in dynasty_houses}
    family_lands: dict[int, tuple[str, str]] = {}
    for cid in dynasty_people:
        person = characters[cid]
        for title_id in person.get("titles", []):
            tile = titles.get(title_id)
            if not tile or tile.get("tier") != "County":
                continue
            for prov in provinces_of(title_id):
                if prov in centroids:
                    family_lands[prov] = (person.get("house_name") or "", person.get("name") or "")

    if args.map:
        # Папки игры может не быть: карта берётся из локального кэша проекта.
        if args.game is None and (CACHE / "map_data" / "provinces.png").exists():
            args.game = CACHE
        player_house_name = (houses.get(house_id) or {}).get("name")
        if args.game is None or not (args.game / "map_data" / "provinces.png").exists():
            raise SystemExit(
                "Для карты нужна папка игры. Укажите --game или переменную CK3_GAME "
                "(например, .../Crusader Kings III/game)."
            )
        payload["mapIndex"] = render_map(args.map, province_realm, realms, centroids, baronies, args.game)
        from PIL import Image as _Image
        _provinces_png = _Image.open(args.game / "map_data" / "provinces.png").convert("RGB")
        house_roles: dict[str, str] = {}
        for branch in branch_stats:
            role = "player" if branch.get("player") else "senior" if branch.get("senior") else "cadet"
            house_roles[branch.get("name") or ""] = role
        # Политическая карта и земли рода слились в одну «Власть»:
        # заливка по держателю уже есть на карте титулов.

        # Карта титулов: все тиры, кроме баронства. Клик даёт графство,
        # а через de jure — герцогство, королевство и империю.
        from title_map import build as build_title_card
        from titles_render import render_title_map

        title_card = build_title_card(titles, baronies)
        titles_out = args.map.with_name("world-map-titles.png")

        # Заливка по владельцу: карта власти, а не просто титулов.
        # Цвет дома — стабильный хеш имени, иначе между сборками он бы менялся.
        accent = (160, 44, 28)
        quiet_fill = (206, 198, 180)
        family_names = {name for name in (player_house_name, *((houses.get(h) or {}).get("name") for h in dynasty_houses)) if name}

        def house_fill(name: str | None) -> tuple[int, int, int]:
            if not name:
                return quiet_fill
            if name in family_names:
                return mix_with_paper(accent, 0.35)
            digest = hashlib.md5(name.encode("utf-8")).digest()
            # Тона домов приглушаем к бумаге: карта не должна спорить с летописью.
            return mix_with_paper(HOUSE_TONES[digest[0] % len(HOUSE_TONES)], 0.62)

        fills: dict[int, tuple[int, int, int]] = {}
        owners = title_card.get("owners") or {}
        for position, key in enumerate(title_card["counties"], start=1):
            holder = owners.get(key)
            # Красим по державе, а не по каждому дому: иначе карта рябая.
            realm_id = top_liege(holder) if holder else None
            realm = realms.get(realm_id or -1) or {}
            fills[position] = house_fill(realm.get("house_name"))

        payload["mapIndex"]["titles"] = render_title_map(
            titles_out, args.game, title_card, centroids, scale=2, fills=fills
        )
        # Справочник держателей для панели: имя, дом, сюзерен, верхний сюзерен.
        # Только те, кто нужен панели: держатели графств и их сюзерены.
        needed = {cid for cid in (title_card.get("owners") or {}).values() if cid}
        for cid in list(needed):
            for step in person_chain(cid, characters):
                needed.add(step["id"])
        lords = {}
        for cid in needed:
            person = characters.get(cid)
            if not person:
                continue
            lords[str(cid)] = {
                "name": person.get("name") or "",
                "house": person.get("house_name") or "",
                "liege": person.get("liege"),
                "suzerain": suzerain_of(cid, characters),
                "since": person.get("birth"),
            }
        title_card["lords"] = lords
        # Контрольные точки: пиксель карты → ожидаемый титул. По ним приложение
        # само видит, совпала ли карта с данными, и говорит об этом.
        meta_map = payload["mapIndex"]["titles"]
        crop = meta_map.get("crop") or [0, 0]
        scale = meta_map.get("scale") or 2
        probe = []
        for position, key in enumerate(title_card["counties"], start=1):
            if len(probe) >= 12:
                break
            provinces = [int(p) for p, v in title_card["province"].items() if v == position]
            point = next((centroids.get(p) for p in provinces if centroids.get(p)), None)
            if not point:
                continue
            probe.append({
                "key": key,
                "x": round((point[0] - crop[0]) / scale),
                "y": round((point[1] - crop[1]) / scale),
            })
        title_card["probe"] = probe

        card_text = json.dumps(title_card, ensure_ascii=False, separators=(",", ":"))
        (args.out.parent / "titles-map.json").write_text(card_text, encoding="utf-8")
        # Та же карта скриптом: с file:// fetch не работает, а <script> — работает.
        (args.out.parent / "titles-map.js").write_text(
            "window.__TITLES__=" + card_text + ";\n", encoding="utf-8"
        )
        print(
            f"карта титулов: графств {title_card['stats']['counties']}, "
            f"провинций {title_card['stats']['provinces']}",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Метка сборки: по ней приложение сбрасывает кэш карт. Иначе браузер держит
    # старую карту рядом с новыми данными — и клик показывает чужие титулы.
    from datetime import datetime, timezone
    payload["meta"]["build"] = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Мир живёт одним файлом: `.js` работает и через сервер, и с file://.
    # Второй копии в JSON не держим — это десять мегабайт дубля.
    js_path = args.out.with_suffix(".js")
    js_path.write_text("window.__WORLD__=" + text + ";\n", encoding="utf-8")
    if args.json:
        args.out.with_suffix(".json").write_text(text, encoding="utf-8")
    print(
        f"держав {len(all_realms)}, известно {len(known)}, род {len(members)} (дерево {len(people)}), "
        f"событий {len(events)}; {args.out.stat().st_size / 1e6:.2f} МБ"
    )

    export_csv(payload)









if __name__ == "__main__":
    main()
