#!/usr/bin/env python3
"""Что есть в сейве, чего нет в дампе экстрактора: войны с поводами и история титулов.

    python tools/save_reader.py --save "…/last_save.ck3" --out _cache/save-extra.json
    python tools/save_reader.py --save "…/last_save.ck3" --check

Зачем отдельный читатель. Экстрактор CK3-history-extractor — сторонний проект под MIT,
его дамп содержит 14 секций и не содержит `wars`. А история титулов в дампе обрывается
на дате старта партии: экстрактор берёт её из файлов игры, а не из сейва.

Сейв CK3 1.20 (обычный и автосейв) — это zip с текстовым `gamestate` внутри. Здесь он
читается потоком, строка за строкой, и берутся только две секции:

  * `wars.active_wars` — идущие войны: повод (`casus_belli.type`), цели-титулы, стороны,
    даты вступления участников, дата начала;
  * `landed_titles.<id>.history` — история держателей, включая смены власти во время игры.

Наружу отдаётся маленький JSON: его подмешивает `build_world.py --extra`.

Ограничения, о которых честно:
  * завершённых войн игра в сейве не хранит (только `active_wars`);
  * бинарные сейвы (ironman) так не читаются — там нет текстового gamestate;
  * id титулов в сейве и в дампе разные, склейка только по `key` (`c_parsberg`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WANTED = ("wars", "landed_titles")

# Вера в 1.20: у человека и графства есть номер обряда (`rite=54`), а реестр
# `rites` связывает номер с ключом обряда и номером веры. Отсюда вера берётся
# без экстрактора — он её не отдаёт вовсе.
CHAR_SECTIONS = ("living", "characters", "dead_unprunable", "character_lookup")
RITE_ID_RE = re.compile(r"^(\d+)=\{\s*$")
# Записи персонажей начинаются с нулевой колонки; вложенные числовые блоки — с отступа.
CHAR_ID_RE = re.compile(r"^(\d+)=\{\s*$")
# Поля обряда бывают на одной строке через табуляцию: «rite_type=roman_rite\t\t\tfaith=13».
RITE_TYPE_RE = re.compile(r"rite_type=([a-z0-9_]+)")
RITE_FAITH_RE = re.compile(r"\bfaith=(\d+)")
RITE_KEY_RE = re.compile(r"\brite=(\d+)")
COUNTY_RE = re.compile(r"^\s*(c_[a-z0-9_]+)=\{\s*$")

SECTION_RE = re.compile(r"^([a-z_0-9]+)=\{\s*$")
NESTED_RE = re.compile(r"^\s*landed_titles=\{\s*$")
TITLE_RE = re.compile(r"^\s*(\d+)=\{\s*$")
KEY_RE = re.compile(r"^\s*key=([a-z0-9_]+)\s*$", re.MULTILINE)
HISTORY_OPEN_RE = re.compile(r"^(\t)history=\{\s*$", re.MULTILINE)
HISTORY_INLINE_RE = re.compile(r"^\thistory=\{(.*)\}\s*$", re.MULTILINE)

# `548.1.1=2081` — запись из файлов истории игры; `914.10.24={ … holder=… }` — запись партии.
# Одна дата может встретиться дважды (`768.9.24=7705 768.9.24=7141`): движок читает последнюю,
# поэтому и мы берём последнюю, а не две записи на день.
ENTRY_RE = re.compile(r"(\d{1,4})\.(\d{1,2})\.(\d{1,2})=(?:(\d+)|\{([^{}]*)\})")
MAP_ENTRY_RE = re.compile(r"(\d{1,4})\.(\d{1,2})\.(\d{1,2})=(\d+)")
# `914.10.24={ … holder=50354377 … }` — запись, сделанная игрой во время партии.
BLOCK_ENTRY_RE = re.compile(r"(\d{1,4})\.(\d{1,2})\.(\d{1,2})=\{([^{}]*)\}", re.DOTALL)
HOLDER_RE = re.compile(r"holder=(\d+)")
TYPE_RE = re.compile(r"type=([a-z_0-9]+)")
NAME_RE = re.compile(r'title_name_data=\{\s*\n\s*name="((?:[^"\\]|\\.)*)"')

TOP_DATE_RE = re.compile(r"^date=(\d{1,4})\.(\d{1,2})\.(\d{1,2})\s*$")
META_DATE_RE = re.compile(r"^\tmeta_date=(\d{1,4})\.(\d{1,2})\.(\d{1,2})\s*$")


def iso(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def brace_delta(line: str) -> int:
    """Сколько открывающих скобок минус закрывающих, не считая кавычек."""
    delta = 0
    quoted = False
    escaped = False
    for ch in line:
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1
    return delta


# --------------------------------------------------------------------------- разбор блоков

TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|[{}]|=|[^\s{}=]+')


def parse_block(tokens: list[str], pos: int = 0) -> tuple[dict | list, int]:
    """Разбирает блок в dict; блок из одних анонимных элементов — в list."""
    result: dict[str, object] = {}
    items: list[object] = []
    while pos < len(tokens):
        token = tokens[pos]
        if token == "}":
            return (result if result else items), pos + 1
        if token == "{":
            value, pos = parse_block(tokens, pos + 1)
            items.append(value)
            continue
        key = token
        following = tokens[pos + 1] if pos + 1 < len(tokens) else None
        if following == "=":
            pos += 2
            if pos >= len(tokens):
                break
            if tokens[pos] == "{":
                value, pos = parse_block(tokens, pos + 1)
            else:
                value = tokens[pos].strip('"')
                pos += 1
        elif following == "{":
            # форма `key={` — без знака равенства
            pos += 1
            value, pos = parse_block(tokens, pos + 1)
        else:
            items.append(token)
            pos += 1
            continue
        if key in result:
            previous = result[key]
            if isinstance(previous, list):
                previous.append(value)
            else:
                result[key] = [previous, value]
        else:
            result[key] = value
        continue
    return (result if result else items), pos


def parse_wars(text: str) -> dict:
    tokens = TOKEN_RE.findall(text)
    block, _ = parse_block(tokens)
    return block if isinstance(block, dict) else {}


def history_body(text: str) -> str:
    """Содержимое блока `history={…}` внутри блока титула (обе формы записи)."""
    start = text.find("history={")
    if start < 0:
        return ""
    index = start + len("history={")
    depth = 1
    quoted = False
    escaped = False
    begin = index
    while index < len(text):
        ch = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[begin:index]
        index += 1
    return text[begin:]


def parse_history(block_lines: list[str]) -> list[list]:
    """История титула: и карта `548.1.1=2081`, и блоки `914.10.24={ holder=… type=… }`.

    Одна дата может быть записана дважды — движок берёт последнюю запись. Так же делаем и мы,
    иначе в летопись попадают две смены власти на один день у одного титула.
    """
    body = history_body("\n".join(block_lines))
    if not body:
        return []
    seen: dict[str, list] = {}

    for match in ENTRY_RE.finditer(body):
        year, month, day, plain_holder, inner = match.groups()
        when = iso(year, month, day)
        if plain_holder:
            seen[when] = [when, int(plain_holder), "Inherited"]
            continue
        holder_match = HOLDER_RE.search(inner or "")
        if not holder_match:
            continue
        type_match = TYPE_RE.search(inner or "")
        seen[when] = [when, int(holder_match.group(1)), type_match.group(1) if type_match else "Inherited"]

    return [seen[when] for when in sorted(seen)]


def title_name(block_lines: list[str]) -> str:
    """Подпись титула из `title_name_data`: нужна для целей войн, которых нет в дампе."""
    match = NAME_RE.search("\n".join(block_lines))
    return match.group(1).replace('\\"', '"') if match else ""


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def participants(side) -> list[int]:
    """Кто участвовал в войне на этой стороне: и лидер, и призванные."""
    if not isinstance(side, dict):
        return []
    out: list[int] = []
    for entry in as_list(side.get("participants")):
        if isinstance(entry, dict) and entry.get("character"):
            out.append(int(entry["character"]))
    if str(side.get("leader", "")).isdigit():
        leader = int(side["leader"])
        if leader not in out:
            out.append(leader)
    return out


def read_faith(path: Path) -> dict:
    """Обряды и вера: реестр обрядов, обряд у людей и у графств.

    Отдельный проход по gamestate: разбор войн и титулов не трогаем, он проверен.
    Глубину вложенности не считаем — секция `rites` внутри себя бывает вложенной,
    а нужные строки узнаются по форме: `54={` задаёт запись, `rite_type=` и
    `rite=` её наполняют.
    """
    rites: dict[str, dict] = {}
    char_rites: dict[str, int] = {}
    county_rites: dict[str, int] = {}

    with zipfile.ZipFile(path) as archive, archive.open("gamestate") as raw:
        depth = 0
        section = None
        rite_id = None
        county = None
        person = None
        for raw_line in raw:
            line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
            delta = brace_delta(line)
            stripped = line.strip()

            if depth == 0:
                match = SECTION_RE.match(line)
                section = match.group(1) if match else None
                rite_id = county = person = None
                depth += delta
                continue

            if section == "rites":
                match = RITE_ID_RE.match(stripped)
                if match:
                    rite_id = match.group(1)
                    rites.setdefault(rite_id, {})
                elif rite_id:
                    match = RITE_TYPE_RE.search(line)
                    if match:
                        rites[rite_id]["type"] = match.group(1)
                    match = RITE_FAITH_RE.search(line)
                    if match:
                        rites[rite_id]["faith"] = int(match.group(1))
                depth += delta
                continue

            if section == "county_manager":
                match = COUNTY_RE.match(stripped)
                if match:
                    county = match.group(1)
                else:
                    match = RITE_KEY_RE.search(line)
                    if match and county:
                        county_rites[county] = int(match.group(1))
                depth += delta
                continue

            if section in CHAR_SECTIONS:
                match = RITE_KEY_RE.search(line)
                if match and person:
                    char_rites[person] = int(match.group(1))
                else:
                    match = CHAR_ID_RE.match(line)
                    if match:
                        person = match.group(1)
                depth += delta
                continue

            depth += delta

    return {"rites": rites, "char_rites": char_rites, "county_rites": county_rites}


def read_save(path: Path) -> dict:
    names = ""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise SystemExit(f"{path.name}: это не zip с текстовым gamestate ({error}) — вероятно, ironman/бинарный сейв")

    with archive:
        names = ", ".join(archive.namelist())
        if "gamestate" not in archive.namelist():
            raise SystemExit(f"В архиве нет gamestate (есть: {names}) — это не сейв CK3?")

        titles: dict[str, list] = {}
        title_keys: dict[str, str] = {}
        title_names: dict[str, str] = {}
        wars_block = ""
        save_date = ""
        meta_date = ""

        with archive.open("gamestate") as raw:
            depth = 0
            section = None
            container_depth = None
            collected: list[str] = []
            title_block: list[str] | None = None
            title_id = ""
            block_depth = 0

            for raw_line in raw:
                line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
                delta = brace_delta(line)

                if depth == 0:
                    match = TOP_DATE_RE.match(line)
                    if match and not save_date:
                        save_date = iso(*match.groups())
                    match = META_DATE_RE.match(line)
                    if match and not meta_date:
                        meta_date = iso(*match.groups())
                    match = SECTION_RE.match(line)
                    if match and match.group(1) in WANTED:
                        section = match.group(1)
                        container_depth = None
                        collected = []
                    depth += delta
                    continue

                if section == "wars":
                    if depth + delta > 0:
                        collected.append(line)
                    depth += delta
                    if depth == 0:
                        wars_block = "\n".join(collected)
                        section = None
                    continue

                if section == "landed_titles":
                    # 1.20: титулы лежат во вложенной `landed_titles={` (глубина 2). 1.19: сразу на глубине 1.
                    if container_depth is None and NESTED_RE.match(line):
                        container_depth = depth + 1
                        depth += delta
                        continue
                    wanted_depth = container_depth if container_depth is not None else 1
                    if title_block is None:
                        match = TITLE_RE.match(line) if depth == wanted_depth else None
                        if match:
                            title_id = match.group(1)
                            title_block = []
                            block_depth = depth
                            depth += delta
                            if depth == block_depth:  # `951={}` в одну строку
                                title_block = None
                            continue
                        depth += delta
                        continue
                    title_block.append(line)
                    depth += delta
                    if depth == block_depth:
                        rows = parse_history(title_block)
                        key_match = KEY_RE.search("\n".join(title_block))
                        if key_match:
                            key = key_match.group(1)
                            title_keys[title_id] = key
                            if rows:
                                titles[key] = rows
                            name = title_name(title_block)
                            if name:
                                title_names[key] = name
                        title_block = None
                    continue

                depth += delta

    wars = []
    parsed = parse_wars(wars_block) if wars_block else {}
    active = parsed.get("active_wars") or {}
    for war_id, war in active.items():
        if not isinstance(war, dict):
            continue
        cb = war.get("casus_belli") if isinstance(war.get("casus_belli"), dict) else {}
        start = ""
        raw_start = war.get("start_date")
        if isinstance(raw_start, str):
            parts = raw_start.split(".")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                start = iso(*parts)
        targets = []
        for value in as_list(cb.get("targeted_titles")):
            key = title_keys.get(str(value))
            if key:
                targets.append(key)
        claimant = cb.get("claimant")
        claimant_id = int(claimant) if str(claimant or "").isdigit() else None
        if claimant_id == 4294967295:  # "нет претендента" в сейве
            claimant_id = None
        wars.append(
            {
                "id": str(war_id),
                "start": start,
                "cb": str(cb.get("type") or ""),
                "attacker": int(cb["attacker"]) if str(cb.get("attacker", "")).isdigit() else None,
                "defender": int(cb["defender"]) if str(cb.get("defender", "")).isdigit() else None,
                "claimant": claimant_id,
                "targets": targets,
                "attackers": participants(war.get("attacker")),
                "defenders": participants(war.get("defender")),
                "name": str(war.get("name") or "")[:400],
            }
        )

    faith = read_faith(path)
    return {
        "source": str(path),
        "date": save_date or meta_date,
        "title_keys": title_keys,
        "titles": titles,
        "names": title_names,
        "wars": wars,
        "rites": faith["rites"],
        "char_rites": faith["char_rites"],
        "county_rites": faith["county_rites"],
    }


FIXTURE = """meta_data={
\tmeta_date=900.1.1
}
date=900.1.1
landed_titles={
\tlanded_titles={
\t\t951={
\t\t\tkey=c_test
\t\t\ttitle_name_data={
\t\t\t\tname="Тест"
\t\t\t}
\t\t\thistory={ 500.1.1=11 899.5.4={
\t\t\t\t\ttype=usurped
\t\t\t\t\tholder=22
\t\t\t\t} }
\t\t}
\t}
}
wars={
\tactive_wars={
\t\t7={
\t\t\tattacker={
\t\t\t\tparticipants={ {
\t\t\t\t\t\tcharacter=11
\t\t\t\t\t} }
\t\t\t}
\t\t\tdefender={
\t\t\t\tparticipants={ {
\t\t\t\t\t\tcharacter=22
\t\t\t\t\t} }
\t\t\t}
\t\t\tstart_date=898.2.2
\t\t\tcasus_belli={
\t\t\t\ttype=county_conquest_cb
\t\t\t\ttargeted_titles={ 951 }
\t\t\t\tattacker=11
\t\t\t\tdefender=22
\t\t\t\tclaimant=4294967295
\t\t\t}
\t\t\tname="Война"
\t\t}
\t}
}
"""


def selftest() -> None:
    """Проверка разбора на синтетическом gamestate: обе формы истории, война, повод, цель."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "selftest.ck3"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("gamestate", FIXTURE)
        data = read_save(path)

    assert data["date"] == "0900-01-01", f"дата сейва: {data['date']}"
    rows = data["titles"].get("c_test")
    assert rows, "история титула не разобрана"
    assert [row[0] for row in rows] == ["0500-01-01", "0899-05-04"], rows
    assert rows[1][1] == 22 and rows[1][2] == "usurped", rows
    assert data["names"].get("c_test") == "Тест", data["names"]
    assert len(data["wars"]) == 1, data["wars"]
    war = data["wars"][0]
    assert war["cb"] == "county_conquest_cb", war
    assert war["targets"] == ["c_test"], war
    assert war["attacker"] == 11 and war["defender"] == 22, war
    assert war["claimant"] is None, war
    assert war["start"] == "0898-02-02", war
    print("самопроверка: ок — история в двух формах, повод, цель, претендент, даты")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--save", type=Path, default=None, help="файл .ck3")
    parser.add_argument("--out", type=Path, default=None, help="куда положить save-extra.json")
    parser.add_argument("--check", action="store_true", help="только показать, что нашлось")
    parser.add_argument("--min-wars", type=int, default=0, help="упасть, если войн меньше")
    parser.add_argument("--min-history-after", default=None, help="упасть, если история не доходит до этой даты (YYYY-MM-DD)")
    parser.add_argument("--selftest", action="store_true", help="проверить разбор на синтетическом сейве и выйти")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    if not args.save:
        raise SystemExit("Нужен --save (или --selftest)")
    if not args.save.exists():
        raise SystemExit(f"Нет файла: {args.save}")

    data = read_save(args.save)

    entries = sum(len(rows) for rows in data["titles"].values())
    last = max((rows[-1][0] for rows in data["titles"].values() if rows), default="")
    in_game = sum(1 for rows in data["titles"].values() for row in rows if row[0] > data["date"][:0] + "0867-01-01")
    cb_types = sorted({war["cb"] for war in data["wars"] if war["cb"]})

    print(f"сейв: {data['source']}")
    print(f"дата: {data['date'] or '—'}")
    print(f"титулов: {len(data['title_keys'])}, из них с историей {len(data['titles'])}, записей {entries}, последняя {last or '—'}")
    print(f"записей после 0867-01-01: {in_game}")
    print(f"войн: {len(data['wars'])}, поводов: {len(cb_types)}")
    if cb_types:
        print("поводы:", ", ".join(cb_types[:20]))
    if data["wars"]:
        print("пример:", json.dumps(data["wars"][0], ensure_ascii=False)[:400])

    failures = []
    if len(data["wars"]) < args.min_wars:
        failures.append(f"войн {len(data['wars'])}, ожидалось не меньше {args.min_wars}")
    if args.min_history_after and last < args.min_history_after:
        failures.append(f"история кончается на {last}, ожидалась не раньше {args.min_history_after}")

    if args.out and not args.check:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"\nзаписано: {args.out} ({args.out.stat().st_size / 1024:.0f} КБ)")

    if failures:
        print("\nПРОВАЛ:", file=sys.stderr)
        for line in failures:
            print("  -", line, file=sys.stderr)
        raise SystemExit(1)
    print("\nИТОГ: ок")


if __name__ == "__main__":
    main()
