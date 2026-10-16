"""Этап download: выгрузка страниц и картинок с wiki.qsp.org в html_src (Фаза 4).

Публичный интерфейс пакета download:
- ``run_download(settings)`` — композиция этапа (создаёт Crawler, настраивает лог,
  запускает обход + прогон картинок); вызывается из pipeline/cli (Фаза 5);
- ``Crawler`` — сетевой обходчик (можно использовать точечно);
- pure-функции ``extract_page_links`` / ``collect_image_urls`` и naming-функции —
  офлайн-тестируемое ядро без сети.

Сетевой код намеренно отделён от трансформаций (prepare/) — prepare полностью
офлайн-тестируется, а здесь офлайн-тестируются извлечение и именование (mock сессии).
"""

from __future__ import annotations

import logging

from ..config import Settings, configure_logging
from .crawler import (
    Crawler,
    DownloadStats,
    collect_image_urls,
    extract_page_links,
    is_image_url,
    same_domain,
)
from .naming import image_extension, image_filename, page_filename

__all__ = [
    "run_download",
    "Crawler",
    "DownloadStats",
    "extract_page_links",
    "collect_image_urls",
    "is_image_url",
    "same_domain",
    "page_filename",
    "image_filename",
    "image_extension",
]


def run_download(settings: Settings, configure_log: bool = True) -> DownloadStats:
    """Прогон этапа выгрузки по настройкам. Возвращает статистику скачивания."""
    if configure_log:
        configure_logging(settings)
    logging.getLogger(__name__).info(
        "Этап download: %s -> %s", settings.wiki.base_url, settings.paths.src
    )
    return Crawler(settings).run()
