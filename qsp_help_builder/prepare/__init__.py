"""Этап подготовки: html_src -> html_out (htm + hhc/hhk).

Порт класса ChmPrepare из chm_prepare/to_chm_prepare.py, разобранный на
переиспользуемые модули (Фаза 3 рефакторинга):

- page_clean — вычистка страницы из DokuWiki-обёртки + спец-правки start;
- links      — замена ссылок по UrlScheme;
- images     — обработка картинок (замена src, снятие «кликабельности»);
- hhc        — содержание из sidebar.htm -> qsp.hhc;
- hhk        — указатель из help_keywords.htm + Anchors -> qsp.hhk.

Порядок вызова в prepare_all повторяет старый main(): сначала все страницы,
потом hhc, потом hhk — он важен: hhc/hhk читают .htm УЖЕ подготовленных
sidebar/help_keywords (их ссылки заменены) и удаляют эти исходники.
"""

from __future__ import annotations

import logging
from pathlib import Path

from bs4 import BeautifulSoup

from ..anchors import Anchors
from ..config import Settings
from ..fs_utils import ensure_dir, read_text, write_text
from ..schema import UrlScheme
from .hhc import build_hhc
from .hhk import build_hhk
from .images import process_images
from .links import replace_links
from .page_clean import apply_start_fixes, extract_page, wrap_into_template

logger = logging.getLogger(__name__)


def prepare_file(
    src_file: Path,
    out_dir: Path,
    *,
    scheme: UrlScheme,
    anchors: Anchors,
    base_url: str,
    page_encoding: str,
    exclude: frozenset[str],
) -> None:
    """Подготовка одной страницы — полный порт ChmPrepare.prepare_htm.

    Последовательность шагов сохранена дословно: start-правки идут ДО
    replace_links (их target='_blank' должен сохраниться заменой), картинки —
    после ссылок, обёртка шаблоном — после всего, якоря — по финальному тексту.
    """
    file_name = src_file.stem
    if file_name in exclude:  # старый early-return для files_to_del
        return

    soup = BeautifulSoup(read_text(src_file, page_encoding), "lxml")
    page = extract_page(soup)

    if file_name == "start":
        apply_start_fixes(soup, page)

    replace_links(page, scheme, base_url)
    process_images(page, scheme, base_url=base_url)

    text = wrap_into_template(soup, page)
    text = anchors.inject_into_text(text, file_name)

    write_text(out_dir / f"{file_name}.htm", text, page_encoding)


def prepare_all(settings: Settings) -> None:
    """Весь этап подготовки по настройкам из qsp_help.toml.

    Композиция равна старому main(): prepare_html_files -> prepare_hhc -> prepare_hhk.
    В Фазе 5 это станет одним из шагов pipeline/cli, но модуль самодостаточен
    уже сейчас — его можно вызывать и как библиотеку.
    """
    out_dir = ensure_dir(settings.paths.out)
    scheme = UrlScheme.load(settings.paths.scheme)
    anchors = Anchors.load(settings.paths.anchors)

    src_files = [
        p for p in settings.paths.src.iterdir()
        if p.is_file() and p.suffix == ".html"
    ]
    logger.info("Подготовка %d html-файлов -> %s", len(src_files), out_dir)

    for src in src_files:
        prepare_file(
            src, out_dir,
            scheme=scheme,
            anchors=anchors,
            base_url=settings.wiki.base_url,
            page_encoding=settings.chm.page_encoding,
            exclude=settings.exclude_files,
        )

    # старый хвост prepare_html_files: чистим в out то, что не было создано
    for name in settings.exclude_files:
        stale = out_dir / f"{name}.htm"
        if stale.is_file():
            stale.unlink()

    build_hhc(
        out_dir,
        hhc_source=settings.chm.hhc_source,
        hhc_output=settings.chm.hhc_output,
        page_encoding=settings.chm.page_encoding,
        index_encoding=settings.chm.index_encoding,
        exclude=settings.exclude_files,
    )
    build_hhk(
        out_dir,
        hhk_source=settings.chm.hhk_source,
        hhk_output=settings.chm.hhk_output,
        page_encoding=settings.chm.page_encoding,
        index_encoding=settings.chm.index_encoding,
        anchors=anchors,
        keyword_overrides=settings.chm.keyword_overrides,
    )
