# Умершие предки в CK3 1.20: секция `dead_unprunable`

Дополнение к `extractor-1.20.patch`. Патч описывает правки разбора под 1.20, но не включает это исправление — оно сделано позже, уже после сборки первого рабочего бинаря.

## Что было

В 1.19 и раньше игра хранила умерших предков картой «номер → персонаж»:

```
dead_unprunable={
    12345={
        ...
    }
}
```

Разбор ждал именно карту:

```rust
"dead_unprunable" => {
    for (key, d) in self.parse()?.as_map()? {
        if let SaveFileValue::Object(o) = d {
            game_state.add_character(&key.parse::<GameId>()?, o.as_map()?)?;
        }
    }
}
```

В 1.20 секция стала массивом объектов, а номер лежит внутри объекта полем `id`. `as_map()` на массиве возвращает ошибку, и вся секция отбрасывалась целиком — с предупреждением в лог, которое легко не заметить:

```
Warning: section dead_unprunable skipped: StructureError(ConversionError(InvalidType(...)))
```

Последствие: в дампе не было предков. Дерево обрывалось на первом живом поколении, хроника начиналась с первого сохранённого воспоминания, а не с начала рода.

## Что стало

`lib/src/save_file/process_section.rs`, ветка `dead_unprunable` читает оба вида и разбирает персонажей по одному:

```rust
"dead_unprunable" => {
    let parsed = self.parse()?;
    let mut skipped = 0usize;
    // 1.19 и раньше: карта id -> персонаж
    if let Ok(map) = parsed.as_map() {
        for (key, d) in map {
            if let SaveFileValue::Object(o) = d {
                let id = key.parse::<GameId>()?;
                if let Ok(character_map) = o.as_map() {
                    if game_state.add_character(&id, character_map).is_err() {
                        skipped += 1;
                    }
                }
            }
        }
    } else {
        // 1.20: массив персонажей, id лежит внутри объекта
        for d in parsed.as_array()? {
            if let SaveFileValue::Object(o) = d {
                let Ok(character_map) = o.as_map() else {
                    skipped += 1;
                    continue;
                };
                let Ok(id) = character_map.get_game_id("id") else {
                    skipped += 1;
                    continue;
                };
                if game_state.add_character(&id, character_map).is_err() {
                    skipped += 1;
                }
            }
        }
    }
    if skipped > 0 {
        eprintln!("Warning: dead_unprunable: {} персонажей не разобрано", skipped);
    }
}
```

Два уровня терпимости:

1. Если массив не читается как карта — пробуем как массив (совместимость 1.19 и 1.20).
2. Внутри секции каждый персонаж разбирается отдельно: один битый не уносит с собой остальных.

## Проверка

Сейв 995 года (Гондэрид, 1.20, русская локализация):

| | до правки | после |
|---|---|---|
| Размер дампа | 262 МБ | 410 МБ |
| Людей в дереве | 247 | 433 |
| В династии | 191 | 255 |
| Событий | 20 847 | 23 760 |
| Первый год событий | 935 | 845 |

## Оговорка

Даже с этой правкой в сейве нет того, кого игра успела вычистить полностью: у Рас Дэвыта (правил Дэмбией с 867) не сохранилось ни записи персонажа, ни держателя в истории титула — только пустые ссылки в списке лидеров дома. Начало рода до 867 берётся не из сейва, а из файлов игры `game/history/characters/` и `game/history/titles/`.
