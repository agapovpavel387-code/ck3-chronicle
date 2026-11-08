"""Чтение мира из `_data/world.js` (или `.json`, если он есть).

Мир хранится одним файлом: `window.__WORLD__={…};` — он работает и через
`file://`, и через сервер. Второй копии в JSON больше нет: десять мегабайт
дубля никому не нужны. Инструменты читают тот же файл, что и страница.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_world(path: str | Path) -> dict:
    """Читает мир: понимает и `world.js`, и `world.json`."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".js":
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"в {p} нет данных мира")
        text = text[start:end + 1]
    return json.loads(text)


def world_path(data_dir: str | Path) -> Path:
    """Путь к миру в папке данных: сначала `.js`, потом `.json`."""
    d = Path(data_dir)
    js = d / "world.js"
    if js.exists():
        return js
    return d / "world.json"
