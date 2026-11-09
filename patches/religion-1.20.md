# Религия в CK3 1.20: что разбирается и что нет

Дополнение к `extractor-1.20.patch`. Описывает разбор веры: что уже работает после правки, а что сейв не отдаёт.

## Как было

Разбор ждал карту вер прямо в разделе `religion`:

```rust
"religion" => {
    let map = self.parse()?.as_map()?;
    for (key, f) in map.get_object("faiths")?.as_map()? {
        game_state.add_faith(&key.parse::<GameId>()?, f.as_object()?.as_map()?)?;
    }
}
```

В 1.20 такой карты нет — секция отбрасывалась целиком:

```
Warning: section religion skipped: MissingKey("faiths", {"great_holy_wars": …})
Warning: section county_manager skipped: MissingKey("faith", {"county_control": …})
```

Последствие: у держав пропадала не только вера, но и **культура** — обе брались из `county_manager`.

## Что в сейве на самом деле

Проверено отладочным разбором живой секции:

```
religion keys: ["great_holy_wars", "holy_sites", "religions"]
religion[42] keys: ["doctrine_background_icon", "faiths", "family", "graphical_faith",
                    "jacopo_39", "piety_icon_group", "religion_type", "tag"]
faiths value = Object(Array([Integer(88), Integer(89)]))
county_manager[county] keys: ["county_control", "culture", "development",
                              "development_progress", "timed_modifier"]
```

То есть:

- `religion.religions[]` — это религии, а `faiths` внутри — **список номеров вер**, не определения;
- сами определения лежат **отдельной секцией `faiths`** (`108` записей в сейве 995 года);
- у графства в `county_manager` есть `culture`, но **нет** `faith`.

## Что сделано

1. **Раздел `faiths`** читается как карта «номер → вера»; 108 вер разобрано.
2. **Раздел `religion`** больше не отбрасывается: религии и списки вер пропускаются через `get_faith`, чтобы вера не считалась чужой.
3. **`county_manager`** терпимее: культура берётся всегда, вера — если есть.

Итог по миру 995:

| | до | после |
|---|---|---|
| культура держав | 0/131 | **134/134** |
| определения вер | 0 | **108** |
| вера держав | 0 | 0 (в дампе — так и осталось) |
| вера людей | 0/433 | 0/433 (в дампе — так и осталось) |

Вера в дампе так и осталась пустой — её берут из сейва, минуя экстрактор.

## Почему вера была пуста и где она нашлась

Вера действительно не лежит там, где её искали: у персонажа в `living`/`characters`
нет поля `faith`, у графства в `county_manager` только `culture`. Но у них есть
другое поле — `rite`:

```
99758={  first_name="Parvin"  culture=110  rite=13  … }
c_middlesex={  development=11  county_control=71.08  culture=231  rite=0  }
```

Обряд — это и есть ключ к вере. Реестр `rites` в сейве связывает номер обряда с
ключом и номером веры, а ключ обряда есть в файлах игры и в локализации:

```
rites[13] → rite_type=roman_rite, faith=12
common\religion\rite_types\00_rite_types.txt: roman_rite = { … faith = christian_faith … }
localization\russian\rites_l_russian.yml: roman_rite_adj: "Римское христианство"
```

Замеры на сейве 957 года: обряды есть у **всех** 125 848 персонажей и у 3 476
графств; реестр содержит 159 обрядов и 107 вер. Читает это
`tools/save_reader.py`, названия собирает `tools/faith_names.py`; как всё
устроено — в [../docs/religion.md](../docs/religion.md).

Экстрактор при этом не меняется: он по-прежнему отдаёт `faith: null`, и это его
дело. Вера приходит из сейва.

## Проверка

Дамп 410,4 МБ, мир собирается: 134 державы, 429→433 человека, 23 829 событий (было 23 760), смертей 4050 (было 4043) — регрессии нет.
