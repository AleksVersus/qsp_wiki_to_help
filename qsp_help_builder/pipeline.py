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
from .config import ConfigError, Settings
from .docusaurus_markdown import MarkdownValidationError, sync_source, validate_source
from .render.chm import render_chm
from .render.docusaurus import render_docusaurus
from .render.pwa import render_pwa
from .render.docusaurus_markdown import (
    render_markdown_chm,
    render_markdown_pwa,
    render_markdown_spa,
)
from .docusaurus_markdown.incremental import build_incremental
from .render.spa import render_spa

logger = logging.getLogger(__name__)


def run_download(settings: Settings) -> download_stage.DownloadStats:
    """Этап выгрузки с wiki. Требует сеть; перезаписывает .build/wiki.

    Лог настраивает вызывающий (cli) — здесь configure_log=False, иначе два
    прохода настройки на один запуск.
    """
    return download_stage.run_download(settings, configure_log=False)


def run_prepare(settings: Settings) -> None:
    """Этап подготовки .build/wiki -> .build/chm (htm + qsp.hhc/qsp.hhk). Полностью офлайн.

    С Фазы 7 — это CHM-рендерер поверх нейтральной модели.
    """
    logger.info("Этап prepare (chm): %s -> %s", settings.paths.src, settings.paths.out)
    render_chm(settings)


def run_spa(settings: Settings) -> None:
    """Этап одностраничника .build/wiki -> .build/spa (index.html + images/). Полностью офлайн.

    Переиспользует те же примитивы подготовки, что и CHM, только с SpaProfile
    (ссылки/картинки в формате хеш-навигации).
    """
    logger.info("Этап spa: %s -> %s", settings.paths.src, settings.paths.spa)
    render_spa(settings)


def run_pwa(settings: Settings) -> None:
    """Этап PWA .build/wiki -> [pwa].out (папка docs: индекс + манифест + service worker + поиск). Офлайн.

    Надстройка над одностраничником: тот же контент-документ (SpaProfile) плюс
    устанавливаемость и клиентский поиск — то, что нужно для хостинга (GitHub Pages).
    """
    logger.info("Этап pwa: %s -> %s", settings.paths.src, settings.paths.pwa)
    render_pwa(settings)


def run_anchors(settings: Settings) -> Anchors:
    """Этап извлечения якорей из СОБРАННОГО .build/chm обратно в anchors.json.

    Порт быв. _auxtools/extract_keywords.py: читает qsp.hhk + htm-страницы из out и
    пишет anchors.json. Это замыкает цикл handoff §1 (якоря переживают пересборку);
    имеет смысл ТОЛЬКО после run_prepare (нужен свежий .build/chm).
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
    """Этап Docusaurus .build/wiki -> [docusaurus].out (дерево .md по уровням содержания).

    Переиспользует ту же модель и примитивы подготовки, что CHM/SPA, только с
    ``DocusaurusProfile`` (ссылки/картинки — токены, разворачиваемые в относительные
    пути при записи каждого файла). Порядок — атрибуты Docusaurus + JSON-базы.
    """
    logger.info("Этап docusaurus: %s -> %s", settings.paths.src, settings.paths.docusaurus)
    render_docusaurus(settings)


def run_markdown_sync(settings: Settings) -> None:
    """Получает и проверяет выбранные Docusaurus Markdown-исходники."""
    markdown_settings = settings.docusaurus_markdown
    if markdown_settings is None:
        raise ConfigError(
            "Команде markdown-sync нужна секция [docusaurus_markdown] в qsp_help.toml"
        )
    result = sync_source(markdown_settings)
    logger.info(
        "Markdown source синхронизирован: %s (%d страниц, commit %s)",
        result.source_dir,
        len(result.pages),
        result.commit,
    )


def run_markdown_validate(settings: Settings) -> None:
    """Validates the local Markdown corpus without writing build outputs."""
    markdown_settings = settings.docusaurus_markdown
    if markdown_settings is None:
        raise ConfigError(
            "Команде markdown-validate нужна секция [docusaurus_markdown] в qsp_help.toml"
        )
    report = validate_source(markdown_settings)
    if report.diagnostics:
        raise MarkdownValidationError(report.diagnostics)
    logger.info(
        "Markdown validation прошла: %d страниц, %d ссылок (%d без перехода на исключённые заглушки), "
        "%d локальных ассетов",
        len(report.pages),
        report.link_count,
        report.unlinked_link_count,
        len(report.assets),
    )


def run_markdown_build(settings: Settings, target: str) -> None:
    """Собирает один или все отдельные выходы Markdown-входа."""
    if target not in {"chm", "spa", "pwa", "all"}:
        raise ConfigError("markdown-build target должен быть chm|spa|pwa|all")
    if settings.docusaurus_markdown is None:
        raise ConfigError(
            "Команде markdown-build нужна секция [docusaurus_markdown] в qsp_help.toml"
        )
    targets = ("chm", "spa", "pwa") if target == "all" else (target,)
    renderers = {
        "chm": render_markdown_chm,
        "spa": render_markdown_spa,
        "pwa": render_markdown_pwa,
    }
    for name in targets:
        output, skipped = build_incremental(settings, name, renderers[name])
        if skipped:
            logger.info("Markdown %s пропущен без изменений: %s", name, output)


def run_all(settings: Settings) -> None:
    """Полный конвейер: download -> prepare -> anchors. Первый этап требует сеть."""
    run_download(settings)
    run_prepare(settings)
    run_anchors(settings)
