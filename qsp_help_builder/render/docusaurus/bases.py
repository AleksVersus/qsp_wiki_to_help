# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportArgumentType=false, reportIndexIssue=false
"""Мутируемые JSON-базы Docusaurus: нумерация файлов и карта ссылок.

Оба файла лежат в ``[docusaurus].bases`` и переживают пересборку (read-modify-
write). Это «память» порядка: число, выданное документу/папке однажды,
сохраняется, а новый узел получает ``max+1`` — поэтому перестановка в contents не
переизобретает номера с нуля и ссылки/позиции остаются стабильными.

Формат (indent=4, ensure_ascii=False — общий контракт JSON проекта, fs_utils):
- ``numbering.json``: ``{ "<key>": {"position": int, "folder": str, "label": str} }``
  где ``key`` = стабильная сигнатура узла (``folder/<имя файла>``);
- ``links.json``: ``{ "<slug>": "<путь rel docs root без расширения>" }`` — цель
  для разворота токенов ``DOCLINK::<slug>::<anchor>`` в относительные ссылки.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ...fs_utils import load_json, save_json


@dataclass
class DocRecord:
    """Документ для нумерации: ключ, папка-родитель, имя файла, метка."""

    key: str
    folder: str
    filename: str
    label: str


@dataclass
class FolderRecord:
    """Папка категории для нумерации: ключ, путь, метка."""

    key: str
    path: str
    label: str


class Numbering:
    """Позиции документов и папок. Существенна стабильность ключей между сборками."""

    def __init__(self, entries: dict[str, object]) -> None:
        # значения — object намеренно: их приносит load_json из внешнего файла,
        # поэтому перед употреблением проверяем isinstance(entry, dict).
        self._entries = entries

    @classmethod
    def load(cls, path: Path) -> "Numbering":
        if not path.is_file():
            return cls({})
        raw = load_json(path)
        return cls(dict(raw))

    def save(self, path: Path) -> None:
        # сортировка ключей — детерминированный вывод (сравним в diff-приёмке)
        save_json(
            {k: self._entries[k] for k in sorted(self._entries)},
            path,
        )

    def assign(
        self,
        docs: list[DocRecord],
        folders: list[FolderRecord],
        start_slug_key: str = "",
    ) -> dict[str, dict[str, int]]:
        """Проставляет порядки; возвращает карты doc_keys и folder_keys -> position.

        Единый глобальный монотонный счётчик: сохранённый ранее номер узла
        остаётся, а новый узел получает глобальный максимум+1. Стартовый документ
        обрабатывается первым, поэтому при первой сборке занимает позицию 1.
        Перестановка в содержании не переизобретает номера с нуля, а новый узел
        гарантированно встает после всех существующих (стабильность пересборок).
        """
        highest = 0
        for entry in self._entries.values():
            pos = entry.get("position") if isinstance(entry, dict) else None
            if isinstance(pos, int):
                highest = max(highest, pos)

        doc_pos: dict[str, int] = {}
        folder_pos: dict[str, int] = {}
        entries: dict[str, object] = {}

        # старт — первым, если он есть в документах (получает минимальный номер)
        ordered_docs = list(docs)
        if start_slug_key:
            start = next((d for d in ordered_docs if d.key == start_slug_key), None)
            if start is not None:
                ordered_docs.remove(start)
                ordered_docs.insert(0, start)

        for d in ordered_docs:
            pos = self._existing_position(d.key)
            if pos is None:
                highest += 1
                pos = highest
            doc_pos[d.key] = pos
            entries[d.key] = {"position": pos, "folder": d.folder, "label": d.label}

        for f in folders:
            pos = self._existing_position(f.key)
            if pos is None:
                highest += 1
                pos = highest
            folder_pos[f.key] = pos
            entries[f.key] = {"position": pos, "folder": str(PurePosixPath(f.path).parent.as_posix()), "label": f.label}

        self._entries = entries
        return {"doc": doc_pos, "folder": folder_pos}

    def _existing_position(self, key: str) -> int | None:
        entry = self._entries.get(key)
        if isinstance(entry, dict):
            pos = entry.get("position")
            if isinstance(pos, int):
                return pos
        return None


class LinksBase:
    """Карта slug -> путь rel docs root (без расширения). Отражает текущую сборку."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.map = mapping

    @classmethod
    def load(cls, path: Path) -> "LinksBase":
        if not path.is_file():
            return cls({})
        return cls(dict(load_json(path)))

    def save(self, path: Path) -> None:
        save_json({k: self.map[k] for k in sorted(self.map)}, path)
