# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownVariableType=false, reportArgumentType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Содержание CHM: sidebar.htm -> qsp.hhc (порт ChmPrepare.prepare_hhc/hhc_ul_rebuild_li).

ИСТОРИК, сохранён 1:1:
- `del li['class']` без guards — на элементе без class старый код падал
  KeyError; в реальных данных sidebar всегда размечен, так и оставим;
- фильтр исключения режет у href последние 4 символа (href[:-4] — '.htm'),
  сравнение со списком files_to_del + 'help_keywords' (ссылка на указатель
  вырезается из содержания — закрывает ручной шаг 4 старого README).
"""

from __future__ import annotations

import logging
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from ..fs_utils import read_text, write_text
from ..templates import HHC_PAGE

logger = logging.getLogger(__name__)


def build_hhc(
    out_dir: Path,
    *,
    hhc_source: str,
    hhc_output: str,
    page_encoding: str,
    index_encoding: str,
    exclude: frozenset[str],
) -> None:
    """Читает подготовленный sidebar.htm, строит qsp.hhc, удаляет исходник.

    Удаление источника — контракт: повторный прогон prepare без перескачивания
    sidebar не будет find_div (старый код вёл себя так же: sidebar.htm живёт
    ровно один цикл prepare).
    """
    src = out_dir / hhc_source
    soup = BeautifulSoup(read_text(src, page_encoding), "lxml")
    ul = soup.select("div.page.group")[0].ul

    rebuild_hhc_ul(ul, soup, exclude)

    new_soup = BeautifulSoup(HHC_PAGE, "lxml")
    new_soup.body.append(ul)

    write_text(out_dir / hhc_output, str(new_soup), index_encoding)
    src.unlink()
    logger.info("Содержание собрано: %s (источник %s удалён)", hhc_output, hhc_source)


def rebuild_hhc_ul(ul: Tag, soup: BeautifulSoup, exclude: frozenset[str]) -> None:
    """Перестройка li-ul в OBJECT/param структуру hhc — порт hhc_ul_rebuild_li."""
    exclude_links = list(exclude) + ["help_keywords"]  # старый exclude_links

    for li in ul.select("li"):
        del li["class"]
        div = li.div
        del div["class"]
        div.name = "OBJECT"
        div["type"] = "text/sitemap"

        for el in div.select("strong"):
            el.unwrap()

        anchors = div.select("a")
        if anchors:
            a = anchors[0]
            name = a.string
            href = a["href"]
            if href[:-4] in exclude_links:
                li.decompose()
                continue
            # attrs dict создаём в старом порядке ключей (name, value) — от него
            # зависит порядок атрибутов в сериализованном <param>
            param_name = soup.new_tag("param", attrs={"name": "Name", "value": name})
            param_local = soup.new_tag("param", attrs={"name": "Local", "value": href})
            div.clear()
            div.extend([param_name, param_local])
        else:
            name = str(div.text).strip()
            param_name = soup.new_tag("param", attrs={"name": "Name", "value": name})
            div.clear()
            div.append(param_name)
