# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false
"""Рендерер CHM: модель -> html_out (.htm + qsp.hhc + qsp.hhk).

Это прежний этап ``prepare`` (порт ``ChmPrepare.main``), переписанный на нейтральную
модель (:func:`model.build_site_model`) с ``ChmProfile``. Порядок и способ сериализации
сохранены побайтово:

- каждая страница -> ``{slug}.htm`` через обёртку ``CHM_PAGE`` + перенос ``<title>``
  + построчная инъекция якорей (CHM-специфика, живёт здесь, а не в модели);
- ``qsp.hhc``/``qsp.hhk`` читают уже записанные ``sidebar.htm``/``help_keywords.htm``
  и удаляют их — как в исходном конвейере;
- чистка ``.htm`` исключённых разделов от прошлых прогонов.
"""

from __future__ import annotations

import logging

from ..config import Settings
from ..fs_utils import copy_tree, ensure_dir, write_text
from ..model import build_site_model
from ..prepare.hhc import build_hhc
from ..prepare.hhk import build_hhk
from ..prepare.page_clean import wrap_into_template
from .profile import ChmProfile

logger = logging.getLogger(__name__)


def render_chm(settings: Settings) -> None:
    """Весь CHM-выход по настройкам из ``qsp_help.toml`` (полностью офлайн)."""
    out_dir = ensure_dir(settings.paths.out)
    model = build_site_model(settings, ChmProfile())
    anchors = model.anchors
    page_encoding = settings.chm.page_encoding

    logger.info("CHM: %d страниц -> %s", len(model.pages), out_dir)
    for page in model.pages:
        text = wrap_into_template(page.source_soup, page.fragment)
        text = anchors.inject_into_text(text, page.slug)
        write_text(out_dir / f"{page.slug}.htm", text, page_encoding)

    # старый хвост prepare_html_files: чистим в out то, что не было создано
    for name in settings.exclude_files:
        stale = out_dir / f"{name}.htm"
        if stale.is_file():
            stale.unlink()

    build_hhc(
        out_dir,
        hhc_source=settings.chm.hhc_source,
        hhc_output=settings.chm.hhc_output,
        page_encoding=page_encoding,
        index_encoding=settings.chm.index_encoding,
        exclude=settings.exclude_files,
    )
    build_hhk(
        out_dir,
        hhk_source=settings.chm.hhk_source,
        hhk_output=settings.chm.hhk_output,
        page_encoding=page_encoding,
        index_encoding=settings.chm.index_encoding,
        anchors=anchors,
        keyword_overrides=settings.chm.keyword_overrides,
    )

    # статичные ресурсы (default.css и пр.) — из _res_src/chm в html_out
    res = copy_tree(settings.paths.res_chm, out_dir)
    if res:
        logger.info("CHM: ресурсы скопированы из %s: %s", settings.paths.res_chm, ", ".join(res))
    else:
        logger.warning("CHM: папка ресурсов %s пуста или отсутствует — default.css может отсутствовать",
                       settings.paths.res_chm)
