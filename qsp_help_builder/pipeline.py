"""Оркестрация этапов сборки (Фаза 5): композиция download/prepare/anchors.

Каждый этап живёт в своём подпакете и самодостаточен; pipeline лишь задаёт
порядок и связывает их общими ``Settings``. Порядок в ``run_all`` повторяет
реальный цикл конвейера (handoff §1): download -> prepare -> anchors.

Слоение сознательное:
- здесь НЕТ разбора аргументов и настройки логов — это responsibility ``cli``;
- здесь НЕТ сетевых/файловых деталей — они в download/ и prepare/.
Функции возвращают результаты (статистику/Anchors), чтобы их можно было вызывать
и как библиотеку, не только из CLI.
"""

from __future__ import annotations

import logging

from . import download as download_stage
from .anchors import Anchors
from .config import Settings
from .prepare import prepare_all

logger = logging.getLogger(__name__)


def run_download(settings: Settings) -> download_stage.DownloadStats:
    """Этап выгрузки с wiki. Требует сеть; перезаписывает html_src.

    Лог настраивает вызывающий (cli) — здесь configure_log=False, иначе два
    прохода настройки на один запуск.
    """
    return download_stage.run_download(settings, configure_log=False)


def run_prepare(settings: Settings) -> None:
    """Этап подготовки html_src -> html_out (htm + qsp.hhc/qsp.hhk). Полностью офлайн."""
    logger.info("Этап prepare: %s -> %s", settings.paths.src, settings.paths.out)
    prepare_all(settings)


def run_anchors(settings: Settings) -> Anchors:
    """Этап извлечения якорей из СОБРАННОГО html_out обратно в anchors.json.

    Порт быв. _auxtools/extract_keywords.py: читает qsp.hhk + htm-страницы из out и
    пишет anchors.json. Это замыкает цикл handoff §1 (якоря переживают пересборку);
    имеет смысл ТОЛЬКО после run_prepare (нужен свежий html_out).
    """
    logger.info("Этап anchors: из %s в %s", settings.paths.out, settings.paths.anchors)
    anchors = Anchors.extract_from_build(
        settings.paths.out,
        settings.chm.hhk_output,
        hhk_encoding=settings.chm.index_encoding,
        page_encoding=settings.chm.page_encoding,
    )
    anchors.save(settings.paths.anchors)
    return anchors


def run_all(settings: Settings) -> None:
    """Полный конвейер: download -> prepare -> anchors. Первый этап требует сеть."""
    run_download(settings)
    run_prepare(settings)
    run_anchors(settings)
