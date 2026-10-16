# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportIndexIssue=false, reportOperatorIssue=false, reportUnknownArgumentType=false, reportArgumentType=false, reportUnknownVariableType=false
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

from ..render.profile import CHM_PROFILE, OutputProfile
from ..schema import UrlScheme


def replace_links(
    el: Tag, scheme: UrlScheme, base_url: str, profile: OutputProfile | None = None
) -> None:
    """Заменяет href у всех ссылок внутри узла el (мутация на месте).

    Разрешение wiki-ссылки в локальный файл одно для всех целей; различие CHM/SPA
    только в форматировании итога (``profile.internal_target``) — по умолчанию CHM,
    поэтому вывод побайтово совпадает со старым.
    """
    profile = profile or CHM_PROFILE
    for link in el.find_all("a", href=True):
        href = str(link["href"])

        if link.get("target") == "_blank":
            continue  # внешние/намеренно-новые-окна — как в старом коде
        if set(link.get("class") or []) & {"fn_bot", "fn_top"}:
            continue  # сноски DokuWiki остаются якорями внутри страницы

        joined = str(urljoin(base_url, href))
        if joined.startswith(base_url):
            # порядок важен: сначала отщипываем хвост '#', потом '?'
            resolved = _swap_by_scheme(joined, "#", scheme)
            resolved = _swap_by_scheme(resolved, "?", scheme)
            final, force_blank = profile.internal_target(resolved, base_url)
            link["href"] = final
            if force_blank:
                link["target"] = "_blank"
        else:
            link["href"] = joined
            link["target"] = "_blank"  # ушедшее на чужой домен — новой вкладкой


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
