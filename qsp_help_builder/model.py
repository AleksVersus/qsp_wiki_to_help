# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportIndexIssue=false, reportArgumentType=false
"""Нейтральная модель сайта (Фаза 7) — единый источник для всех рендереров.

``build_site_model`` один раз готовит контент страниц поверх примитивов ``prepare``
(``page_clean`` + профиль-параметризованные ``links``/``images``) и отдаёт
структуру данных. Модель НИЧЕГО не пишет на диск — это делают рендереры
(:mod:`render.chm`, :mod:`render.spa`), выбирая способ сериализации.

Различие CHM/SPA целиком в ``profile``: одна и та же страница получает ссылки
``help_coding.htm#anchor`` (CHM) или ``#help_coding~anchor`` (SPA) и картинки
``pic.png`` / ``images/pic.png``. Поэтому «модуль подготовки ссылок для CHM»
буквально параллельно готовит ссылки и для одностраничника (решение пользователя).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from .anchors import Anchors
from .config import Settings
from .fs_utils import file_name, read_text
from .prepare.links import replace_links
from .prepare.page_clean import apply_start_fixes, extract_page
from .prepare.images import process_images
from .render.profile import OutputProfile
from .schema import UrlScheme

# Парсер тот же, что у этапа prepare: разбор влияет на дерево и на байты вывода.
HTML_PARSER = "lxml"


@dataclass
class Page:
    """Одна подготовленная страница: нейтральный фрагмент + служебные данные."""

    slug: str                    # имя файла без расширения (help_coding) — id в SPA и ключ CHM
    title: str                   # текст <title> исходной страницы
    source_soup: BeautifulSoup   # исходный soup (нужен CHM-обёртке для переноса <title>)
    fragment: Tag                # вычищенный контент со ссылками/картинками по профилю


@dataclass
class SiteModel:
    pages: list[Page]
    anchors: Anchors
    profile: OutputProfile
    scheme: UrlScheme
    by_slug: dict[str, Page] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_slug = {page.slug: page for page in self.pages}

    def referenced_images(self) -> set[str]:
        """Имена локальных файлов картинок, на которые ссылается контент.

        Профиль уже оформил ``src`` (CHM — голое имя, SPA — ``images/имя``);
        берём базовое имя и отбрасываем внешние/абсолютные ссылки.
        """
        names: set[str] = set()
        for page in self.pages:
            for img in page.fragment.find_all("img", src=True):
                src = str(img["src"])
                if "://" in src or src.startswith("/"):
                    continue
                names.add(file_name(src))
        return names


def build_site_model(settings: Settings, profile: OutputProfile) -> SiteModel:
    """Готовит модель из ``html_src`` для целевого профиля (полностью офлайн)."""
    scheme = UrlScheme.load(settings.paths.scheme)
    anchors = Anchors.load(settings.paths.anchors)
    base_url = settings.wiki.base_url
    page_encoding = settings.chm.page_encoding

    pages: list[Page] = []
    for src_file in _html_sources(settings.paths.src, settings.exclude_files):
        slug = src_file.stem
        soup = BeautifulSoup(read_text(src_file, page_encoding), HTML_PARSER)
        fragment = extract_page(soup)
        if slug == "start":
            apply_start_fixes(soup, fragment)
        replace_links(fragment, scheme, base_url, profile)
        process_images(fragment, scheme, base_url=base_url, profile=profile)
        title = (soup.title.string.strip() if soup.title and soup.title.string else "")
        pages.append(Page(slug=slug, title=title, source_soup=soup, fragment=fragment))

    return SiteModel(pages=pages, anchors=anchors, profile=profile, scheme=scheme)


def _html_sources(src_dir: Path, exclude: frozenset[str]) -> list[Path]:
    """Отсортированные .html из html_src без исключаемых разделов (стабильный порядок)."""
    files = [p for p in sorted(src_dir.iterdir()) if p.is_file() and p.suffix == ".html"]
    return [p for p in files if p.stem not in exclude]
