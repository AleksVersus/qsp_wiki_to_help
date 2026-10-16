# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownVariableType=false, reportArgumentType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Указатель CHM: help_keywords.htm + Anchors -> qsp.hhk.

Порт ChmPrepare.prepare_hhk/extract_hhk_data/_href_compare + карты
keywords_anchors (теперь живёт в Anchors.keywords_map, Фаза 2).

Порядок заголовков в указаторе = порядок строк таблицы help_keywords (как
раньше); к каждой ссылке подставляется якорь из anchors.json, если заголовок
там найден (логика _href_compare сохранена 1:1, включая «ветку расхождения»,
когда страница ссылки и страница якоря различаются).
"""

from __future__ import annotations

import logging
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from ..anchors import Anchors
from ..fs_utils import read_text, write_text
from ..templates import HHK_PAGE

logger = logging.getLogger(__name__)


def build_hhk(
    out_dir: Path,
    *,
    hhk_source: str,
    hhk_output: str,
    page_encoding: str,
    index_encoding: str,
    anchors: Anchors,
) -> None:
    """Читает подготовленный help_keywords.htm, пишет qsp.hhk, удаляет исходник.

    Локальные адреса берутся из anchors.json (keywords_map) с согласованием
    страницы из таблицы через href_compare.
    """
    src = out_dir / hhk_source
    soup = BeautifulSoup(read_text(src, page_encoding), "lxml")
    page = soup.select_one("div.page.group")

    params = extract_hhk_data(page.table)
    keywords_anchors = anchors.keywords_map()

    new_soup = BeautifulSoup(HHK_PAGE, "lxml")
    ul = new_soup.new_tag("ul")
    for title, new_href in params.items():
        li = new_soup.new_tag("li")
        obj = new_soup.new_tag("OBJECT")
        obj["type"] = "text/sitemap"
        # порядок установки атрибутов (name, value) как в старом коде — от него
        # зависит байтовый порядок атрибутов в <param>
        param_title = new_soup.new_tag("param")
        param_title["name"] = "Name"
        param_title["value"] = title
        if title in keywords_anchors:
            old_href = keywords_anchors[title]
            new_href = href_compare(old_href, new_href)
        param_href = new_soup.new_tag("param")
        param_href["name"] = "Local"
        param_href["value"] = new_href
        obj.append(param_title)
        obj.append(param_href)
        li.append(obj)
        ul.append(li)

    new_soup.body.append(ul)

    file_text = str(new_soup)
    # старый косметический перенос строк между li — CHM-красота, влияет на байты
    file_text = file_text.replace("</li><li>", "</li>\n<li>")

    write_text(out_dir / hhk_output, file_text, index_encoding)
    src.unlink()
    logger.info("Указатель собран: %s (записей %d, источник %s удалён)",
                hhk_output, len(params), hhk_source)


def extract_hhk_data(table: Tag) -> dict[str, str]:
    """Порт extract_hhk_data: заголовок -> href из первой колонки таблицы.

    Строки без ссылки в td.col0 пропускаются; отсутствующий td.col0 — падение
    (как старый код: AttributeError на None, вход сломан явно).
    """
    params: dict[str, str] = {}
    for tr in table.select("tr"):
        td = tr.select_one("td.col0")
        link = td.a
        if not link:
            continue
        params[link.text] = link["href"]
    return params


def href_compare(old_href: str, new_href: str) -> str:
    """Порт _href_compare: согласование ссылки из таблицы со ссылкой из якорей.

    Если записанный якорь указывает на ту же страницу (old начинается с new) —
    берём old целиком (он с якорем). Иначе — берём страницу из таблицы (new) и
    только якорь из записи — страница-источник уехала, а якорь оставили.
    """
    if old_href.startswith(new_href):
        return old_href
    anchor = old_href.split("#")[1]
    return f"{new_href}#{anchor}"
