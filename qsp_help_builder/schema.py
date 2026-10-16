"""Модель контракта ``urls_links_to_files.json`` — связка url -> локальный файл.

Формат зафиксирован решением о совместимости (handoff §5): старые файлы должны
читаться как есть, расширять можно, ломать нельзя. Значения исторически —
относительные Windows-пути; потребители всегда использовали только ИМЯ файла
(старый os.path.split(...)[1]), поэтому методы ниже возвращают именно имена.

Кто создаёт: этап download (Фаза 4). Кто потребляет: этап prepare
(links.py по 'pages', images.py по 'images') и последующие рендереры.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .fs_utils import file_name, load_json, save_json


def _empty_str_map() -> dict[str, str]:
    """Типизированный factory для mutable-default полей (pyright strict против голого dict)."""
    return {}


@dataclass
class UrlScheme:
    pages: dict[str, str] = field(default_factory=_empty_str_map)   # url страницы -> путь к .html
    images: dict[str, str] = field(default_factory=_empty_str_map)  # url картинки -> путь к файлу

    @classmethod
    def load(cls, path: Path) -> "UrlScheme":
        """Читает существующий манифест. Секции отсутствовать НЕ должны —
        это сломанный вход, молча чинить его не будем (принцип явных ошибок)."""
        raw = load_json(path)
        for section in ("pages", "images"):
            if section not in raw:
                raise ValueError(f"В {path.name} отсутствует секция '{section}' — контракт нарушен")
        return cls(pages=dict(raw["pages"]), images=dict(raw["images"]))

    def save(self, path: Path) -> None:
        """Пишет в формате старого save_urls_link_files (indent=4, ensure_ascii=False)."""
        save_json({"images": self.images, "pages": self.pages}, path)

    # --- доступ по именам файлов (так делал старый ChmPrepare) ---

    def page_name(self, url: str) -> str | None:
        """Имя html-файла страницы по её url, если страница скачана."""
        value = self.pages.get(url)
        return file_name(value) if value else None

    def image_name(self, url: str) -> str | None:
        """Имя файла картинки по её url (точное совпадение url, как в scheme['images'])."""
        value = self.images.get(url)
        return file_name(value) if value else None

    @property
    def image_names(self) -> list[str]:
        """Все имена скачанных картинок — вход для нечёткого сопоставления
        (эвристика replace_src, сохраняется по решению handoff §5)."""
        return [file_name(v) for v in self.images.values()]
