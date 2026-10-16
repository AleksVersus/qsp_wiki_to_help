"""Этап подготовки: html_src -> html_out (htm + hhc/hhk).

Порт класса ChmPrepare из chm_prepare/to_chm_prepare.py, разобранный на
переиспользуемые модули (Фаза 3 рефакторинга):

- page_clean — вычистка страницы из DokuWiki-обёртки + спец-правки start;
- links      — замена ссылок по UrlScheme (профиль-параметризовано, Фаза 7);
- images     — обработка картинок (замена src, снятие «кликабельности»);
- hhc        — содержание из sidebar.htm -> qsp.hhc;
- hhk        — указатель из help_keywords.htm + Anchors -> qsp.hhk.

С Фазы 7 вся сборка CHM оркестрируется рендерером :mod:`render.chm` поверх
нейтральной модели (:mod:`model`). Здесь остаётся :func:`prepare_file` — подготовка
одной страницы (переиспользуется тестами и мелкими прогонами) и :func:`prepare_all`
как обратный вызов к рендереру (совместимость старых импортов).
"""

from __future__ import annotations

import logging
from pathlib import Path

from bs4 import BeautifulSoup

from ..anchors import Anchors
from ..config import Settings
from ..fs_utils import read_text, write_text
from ..schema import UrlScheme
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
    """Подготовка одной страницы — порт ChmPrepare.prepare_htm (по умолчанию CHM).

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
    """Полный CHM-выход. Делегирует рендереру модели (Фаза 7) — без дублей.

    Лёгкий импорт разрывает потенциальный цикл ``prepare`` <-> ``render.chm``.
    """
    from ..render.chm import render_chm

    render_chm(settings)
