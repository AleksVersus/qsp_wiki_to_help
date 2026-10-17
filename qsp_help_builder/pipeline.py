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
from .render.chm import render_chm
from .render.docusaurus import render_docusaurus
from .render.pwa import render_pwa
from .render.spa import render_spa

logger = logging.getLogger(__name__)


def run_download(settings: Settings) -> download_stage.DownloadStats:
    """Этап выгрузки с wiki. Требует сеть; перезаписывает html_src.

    Лог настраивает вызывающий (cli) — здесь configure_log=False, иначе два
    прохода настройки на один запуск.
    """
    return download_stage.run_download(settings, configure_log=False)


def run_prepare(settings: Settings) -> None:
    """Этап подготовки html_src -> html_out (htm + qsp.hhc/qsp.hhk). Полностью офлайн.

    С Фазы 7 — это CHM-рендерер поверх нейтральной модели.
    """
    logger.info("Этап prepare (chm): %s -> %s", settings.paths.src, settings.paths.out)
    render_chm(settings)


def run_spa(settings: Settings) -> None:
    """Этап одностраничника html_src -> spa_out (index.html + images/). Полностью офлайн.

    Переиспользует те же примитивы подготовки, что и CHM, только с SpaProfile
    (ссылки/картинки в формате хеш-навигации).
    """
    logger.info("Этап spa: %s -> %s", settings.paths.src, settings.paths.spa)
    render_spa(settings)


def run_pwa(settings: Settings) -> None:
    """Этап PWA html_src -> [pwa].out (папка docs: индекс + манифест + service worker + поиск). Офлайн.

    Надстройка над одностраничником: тот же контент-документ (SpaProfile) плюс
    устанавливаемость и клиентский поиск — то, что нужно для хостинга (GitHub Pages).
    """
    logger.info("Этап pwa: %s -> %s", settings.paths.src, settings.paths.pwa)
    render_pwa(settings)


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


def run_docusaurus(settings: Settings) -> None:
    """Этап Docusaurus html_src -> [docusaurus].out (дерево .mdx по уровням содержания).

    Переиспользует ту же модель и примитивы подготовки, что CHM/SPA, только с
    ``DocusaurusProfile`` (ссылки/картинки — токены, разворачиваемые в относительные
    пути при записи каждого файла). Порядок — атрибуты Docusaurus + JSON-базы.
    """
    logger.info("Этап docusaurus: %s -> %s", settings.paths.src, settings.paths.docusaurus)
    render_docusaurus(settings)


def run_all(settings: Settings) -> None:
    """Полный конвейер: download -> prepare -> anchors. Первый этап требует сеть."""
    run_download(settings)
    run_prepare(settings)
    run_anchors(settings)
