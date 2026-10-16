# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportIndexIssue=false, reportOperatorIssue=false, reportUnknownArgumentType=false, reportArgumentType=false
# Ограничения stub'ов bs4: find_all('a') типизирован как union PageElement, но с
# href=True там всегда Tag; порт 1:1, runtime-проверки не добавляем (решение Фазы 3).
"""Замена ссылок на локальные файлы по UrlScheme (порт ChmPrepare.replace_links).

Портировано 1:1, включая тонкости, которые легко «случайно починить» и
сдвинуть бейзлайн:
- href присваивается даже когда замена не произошла (wiki-ссылка вне scheme
  становится абсолютной);
- .html -> .htm вырезается во всей строке, а не только в хвосте (по образцу
  старого href.replace('.html', '.htm'));
- ссылки сносок (fn_bot/fn_top) и target=_blank не трогаются.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import Tag

from ..schema import UrlScheme


def replace_links(el: Tag, scheme: UrlScheme, base_url: str) -> None:
    """Заменяет href у всех ссылок внутри узла el (мутация на месте)."""
    for link in el.find_all("a", href=True):
        href = link["href"]

        if link.has_attr("target") and link["target"] == "_blank":
            continue  # внешние/намеренно-новые-окна — как в старом коде
        if link.has_attr("class") and set(link["class"]) & {"fn_bot", "fn_top"}:
            continue  # сноски DokuWiki остаются якорями внутри страницы

        href = str(urljoin(base_url, href))
        if href.startswith(base_url):
            # порядок важен: сначала отщипываем хвост '#', потом '?'
            href = _swap_by_scheme(href, "#", scheme)
            href = _swap_by_scheme(href, "?", scheme)
            href = href.replace(".html", ".htm")
        else:
            link["target"] = "_blank"  # ушедшее на чужой домен — новой вкладкой

        link["href"] = href


def _swap_by_scheme(href: str, splitter: str, scheme: UrlScheme) -> str:
    """Порт ChmPrepare.replace_href(scheme_type='pages').

    Если до разделителя ссылка известна scheme — меняем head на имя локального
    файла, хвост сохраняем. Если head неизвестен — href остаётся КАК ЕСТЬ
    (со всей хвост-частью), ровно как в старом коде.
    """
    parts = href.split(splitter)
    if len(parts) > 1:
        name = scheme.page_name(parts[0])
        if name is not None:
            return f"{name}{splitter}{parts[1]}"
        return href
    name = scheme.page_name(href)
    return name if name is not None else href
