"""Файловые утилиты, общие для всех этапов.

В старом коде эти операции дублировались в каждом скрипте
(read_file/json_load/write_file в to_chm_prepare.py; свои inline-открытия
в qsp_wiki_downloader.py и extract_keywords.py) — теперь это единственное
место. Поведение намеренно совпадает с оригиналами, чтобы не двигать
бейзлайн: JSON — тот же формат, что писал save_urls_link_files
(ensure_ascii=False, indent=4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    """Создаёт папку (и промежуточные), возвращает её — как старый makedirs,
    но без гонки: exist_ok=True."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path, encoding: str) -> str:
    """Читает текстовый файл. Кодировка обязательна явно: в проекте смешаны
    utf-8 (htm) и windows-1251 (hhc/hhk) — молча угадывать нельзя."""
    with open(path, "r", encoding=encoding) as fp:
        return fp.read()


def write_text(path: Path, text: str, encoding: str) -> None:
    """Пишет текстовый файл, создавая родительские папки.
    (Старый write_file возвращал число записанных символов — бесполезно, здесь None.)"""
    ensure_dir(path.parent)
    with open(path, "w", encoding=encoding) as fp:
        fp.write(text)


def load_json(path: Path, encoding: str = "utf-8") -> Any:
    """Читает JSON. encoding по умолчанию utf-8 — во всех JSON-контрактах проекта."""
    with open(path, "r", encoding=encoding) as fp:
        return json.load(fp)


def save_json(data: Any, path: Path) -> None:
    """Пишет JSON в историческом формате проекта: отступ 4, юникод как есть
    (ключи и значения содержат пути/заголовки на русском)."""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=4)


def file_name(path_value: str) -> str:
    """Имя файла из пути ЛЮБОЙ разделительной природы.

    Значения в urls_links_to_files.json исторически — относительные Windows-пути
    ('..\\html_src\\images\\fetch.png'), но манифест может содержать и прямые слэши.
    os.path.split завязан на платформу, поэтому режем оба разделителя вручную —
    так потребитель работает и на Linux (в старом коде это была скрытая зависимость).
    """
    return path_value.replace("\\", "/").split("/")[-1]
