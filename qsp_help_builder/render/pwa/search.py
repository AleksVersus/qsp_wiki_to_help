# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportIndexIssue=false
"""Client-side индекс полнотекстового поиска (Фаза 8, PWA).

Строится на этапе сборки из уже готовой модели сайта (:mod:`model`) и сериализуется
в ``pwa_out/search.json``. В рантайме его читает крошечный JS (:data:`shell.SEARCH_JS`)
без внешних библиотек — поэтому здесь только данные, никакой JS-логике не подражаем.

Формат (компактный инвертированный индекс постраничной гранулярности):

    {
      "version": 1,
      "docs":     [{"slug": "...", "title": "..."}, ...],
      "postings": {"<терм>": {"<индекс_документа>": частота, ...}, ...}
    }

Гранулярность — страница (не заголовок): ссылка результата ведёт на ``#slug`` того же
hash-роутера, что и весь одностраничник. Токенизация юникодная (``\\w`` в Python 3
захватывает кириллицу), стоп-слова не вырезаем — корпус мал (~80 страниц), а
короткие токены (<3 символов) отбрасываем, чтобы индекс не раздувался на предлоги.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...model import SiteModel

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
MIN_TOKEN_LEN = 3  # короче — предлоги/союзы, шум в индексе

# Юникодные «слова»: буквы/цифры/подчёркивание (кириллица входит в \w по умолчанию).
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Нормализует текст в список поисковых токенов (нижний регистр, длина >= 3)."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= MIN_TOKEN_LEN]


def build_search_index(model: SiteModel, exclude_slugs: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Собирает инвертированный индекс по контент-страницам модели (полностью офлайн).

    ``exclude_slugs`` — служебные страницы, не подлежащие поиску (навигация ``sidebar``).
    Текст документа = видимый текст фрагмента + заголовок страницы (он взвешен
    повторением токенов title, чтобы совпадение с названием ранжировалось выше).
    """
    docs: list[dict[str, str]] = []
    postings: dict[str, dict[str, int]] = {}

    for page in model.pages:
        if page.slug in exclude_slugs:
            continue
        idx = len(docs)
        docs.append({"slug": page.slug, "title": page.title})

        words = tokenize(page.fragment.get_text(" ", strip=True))
        # title weight=3: совпадение с названием страницы важнее совпадения в тексте
        words += tokenize(page.title) * 3
        for token in words:
            bucket = postings.setdefault(token, {})
            bucket[str(idx)] = bucket.get(str(idx), 0) + 1

    index = {"version": INDEX_VERSION, "docs": docs, "postings": postings}
    logger.info("PWA: поисковый индекс собран (документов %d, терминов %d)", len(docs), len(postings))
    return index
