# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Единый ассет-пайплайн CSS для PWA (Фаза 8; закрывает handoff §4.13).

Скачанный DokuWiki ``default.css`` наводнён декоративными ``url()``-ссылками вида
``/lib/images/…``, ``/lib/tpl/…``, ``/lib/plugins/…`` — это иконки interwiki,
файловые значки, jquery-ui-тема, фоны шаблона. Ни один из этих ассетов НЕ входит в
офлайн-корпус (краулер качает только картинки из контента), поэтому на размещённом
PWA абсолютный ``/lib/…`` резолвится в корень домена и даёт ``ERR_FILE_NOT_FOUND``
(в §4.13 это названо «не функциональный контент», кандидатам на закрытие Фазой 8).

Разрешение здесь простое и предсказуемое: переписать wiki-root-absolute ``url()``
на живой origin вики (``https://wiki.qsp.org/lib/…``). Тогда онлайн декорации
дотягиваются с оригинала, а офлайн graceful деградируют (исчезают иконки, контент
остаётся). Функциональные картинки контента уже лежат в ``images/`` (их оформил
``SpaProfile``) и тут не участвуют.

Не трогаем: ``data:``-URI (инлайн base64/SVG), уже абсолютные ``http(s)://``,
протокольно-относительные ``//`` и относительные пути без ведущего слэша.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# url( target ) с необязательными кавычками; \1 — тип кавычки (или пусто).
_URL_RE = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<target>[^'")]+)(?P=q)\s*\)""")


def _is_wiki_root_absolute(target: str) -> bool:
    """Только пути, начинающиеся с одного «/» (не «//» и не схема «http:»)."""
    return target.startswith("/") and not target.startswith("//")


def resolve_css_urls(css_text: str, origin: str) -> tuple[str, int]:
    """Переписывает wiki-root-absolute ``url()`` на ``origin``. Возвращает (текст, число правок).

    ``origin`` — базовый URL вики без завершающего слэша (``settings.wiki.base_url``).
    Идемпотентен: уже переписанные (абсолютные) цели больше не попадают под фильтр.
    """
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        target = m.group("target")
        if not _is_wiki_root_absolute(target):
            return m.group(0)
        count += 1
        quote = m.group("q")
        return f"url({quote}{origin}{target}{quote})"

    result = _URL_RE.sub(repl, css_text)
    if count:
        logger.debug("PWA: переписано url()-ссылок на %s: %d", origin, count)
    return result, count
