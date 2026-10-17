# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportArgumentType=false, reportIndexIssue=false
"""Мутируемые JSON-базы Docusaurus: нумерация файлов и карта ссылок.

Оба файла лежат в ``[docusaurus].bases`` и переживают пересборку (read-modify-
write). Это «память» порядка: число, вручную заданное документу/папке, сохраняется
на пересборке; отсутствующий ключ получает вычисленный из TOC порядок внутри своей
папки (:meth:`Numbering.assign`). Поэтому перестановка в contents не трогает
уже проставленные номера, а новые узлы встают по содержанию.

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
    """Документ для нумерации: ключ, папка-родитель, имя файла, метка, порядок.

    ``position`` — вычисленный из TOC порядок внутри родительской папки;
    используется, если для ключа нет сохранённого значения (стабильность).
    """

    key: str
    folder: str
    filename: str
    label: str
    position: int


@dataclass
class FolderRecord:
    """Папка категории для нумерации: ключ, путь, метка, вычисленный порядок."""

    key: str
    path: str
    label: str
    position: int


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
    ) -> dict[str, dict[str, int]]:
        """Проставляет порядки; возвращает карты doc_keys и folder_keys -> position.

        Порядок вычисляется из TOC внутри каждой папки (см. ``toc._walk``), но
        приоритет имеет сохранённое значение: если для ключа в базе уже есть
        ``position`` — оно переиспользуется (ручная перестановка переживает
        пересборку); если ключа нет — берётся вычисленный TOC-порядок.
        """
        doc_pos: dict[str, int] = {}
        folder_pos: dict[str, int] = {}
        entries: dict[str, object] = {}

        for d in docs:
            pos = self._existing_position(d.key)
            if pos is None:
                pos = d.position
            doc_pos[d.key] = pos
            entries[d.key] = {"position": pos, "folder": d.folder, "label": d.label}

        for f in folders:
            pos = self._existing_position(f.key)
            if pos is None:
                pos = f.position
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
