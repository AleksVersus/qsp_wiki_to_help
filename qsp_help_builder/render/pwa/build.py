# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownArgumentType=false, reportIndexIssue=false
"""Сборщик PWA (Фаза 8): одностраничник + манифест + service worker + поиск.

PWA — надстройка над выводом :func:`render.spa.render_spa`, а не новый рендерер
контента: модель строится тем же ``SpaProfile``, тело документа собирает общий
:func:`render.spa.assemble_body`, ассеты кладёт общий :func:`render.spa.copy_assets`.
Здесь добавляется только то, чего нет у файлового одностраничника и что нужно для
хостинга (GitHub Pages):

1. ``<head>`` — ссылка на манифест, ``theme-color``, иконки;
2. третья вкладка «Поиск» + рантайм, читающий ``search.json`` (клиентский полнотекст);
3. ``search.json`` — инвертированный индекс (:mod:`pwa.search`);
4. ``manifest.webmanifest`` — устанавливаемость/иконки/имена из ``[pwa]``;
5. переписывание ``url()`` в CSS на живой origin вики (:mod:`pwa.assets`, §4.13);
6. ``sw.js`` — precache полного списка файлов сборки с детерминированным именем кэша.

Все пути в артефактах — относительные, поэтому сборка одинаково работает в корне
домена и в под-пути проекта (``https://<user>.github.io/<repo>/``).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup

from ...config import Settings
from ...fs_utils import ensure_dir, save_json, write_text
from ...model import SiteModel, build_site_model
from ..profile import SpaProfile
from ..spa import NAV_SOURCE_SLUG, SPA_PAGE, assemble_body, copy_assets, toc_excluded_slugs
from .assets import resolve_css_urls
from .search import build_search_index
from .shell import (
    HEAD_LINKS_HTML,
    RUNTIME_JS,
    SEARCH_PANEL_HTML,
    SEARCH_TAB_HTML,
    SW_JS,
)

logger = logging.getLogger(__name__)

# Минимальная оформление вкладки поиска (свой <style>, чтобы не трогать spa.css и SPA).
SEARCH_STYLE = """
.spa-sidebar-body #searchInput {
    width: 100%;
    box-sizing: border-box;
    padding: 6px 8px;
    margin: 4px 0 8px;
    font: inherit;
    border: 1px solid #c9ccd2;
    border-radius: 4px;
}
.spa-search-results ul { list-style: none; margin: 0; padding: 0; }
.spa-search-results li { margin: 2px 0; }
.spa-search-results a { display: block; padding: 3px 6px; border-radius: 3px; }
.spa-search-results a:hover { background: #f2f6fb; }
"""


def render_pwa(settings: Settings) -> None:
    """Полная сборка PWA в ``[pwa].out`` (полностью офлайн; сеть не трогается)."""
    model = build_site_model(settings, SpaProfile())
    out_dir = ensure_dir(settings.paths.pwa)

    soup = BeautifulSoup(SPA_PAGE, "lxml")
    assemble_body(soup, model, settings.pwa.start_page, toc_excluded_slugs(settings))
    _add_pwa_shell(soup, settings)
    write_text(out_dir / "index.html", str(soup), settings.chm.page_encoding)

    copy_assets(model, settings, out_dir)
    _resolve_css(settings, out_dir)
    _write_search(model, out_dir)
    _write_manifest(settings, out_dir)
    _write_sw(settings, out_dir)

    logger.info("PWA собран: %s (страниц %d)", out_dir, len(model.pages))


def _add_pwa_shell(soup: BeautifulSoup, settings: Settings) -> None:
    """Дополняет SPA-документ PWA-оболочкой: head-ссылки, вкладка поиска, рантайм."""
    head = soup.head
    assert head is not None
    head.append(BeautifulSoup(
        HEAD_LINKS_HTML.format(theme_color=settings.pwa.theme_color, icon=settings.pwa.icon),
        "lxml",
    ))
    head.append(BeautifulSoup(f"<style>{SEARCH_STYLE}</style>", "lxml"))

    body = soup.body
    assert body is not None

    # третья вкладка: кнопка в заголовок панели, панель — в тело левой панели
    tab_btn = BeautifulSoup(SEARCH_TAB_HTML, "lxml").find("button")
    panel = BeautifulSoup(SEARCH_PANEL_HTML, "lxml").find("nav")
    sidebar_body = soup.find(class_="spa-sidebar-body")
    sidebar_head = soup.find(class_="spa-sidebar-head")
    if tab_btn is not None and sidebar_head is not None:
        # перед кнопками сворачивания/закрытия, чтобы не ломать их раскладку
        sidebar_head.insert(2, tab_btn)
    if panel is not None and sidebar_body is not None:
        sidebar_body.append(panel)

    # рантайм поиска + регистрация SW — последним элементом body
    body.append(BeautifulSoup(RUNTIME_JS, "lxml"))


def _resolve_css(settings: Settings, out_dir: Path) -> None:
    """Переписывает wiki-root-absolute ``url()`` во всех CSS выхода на origin вики."""
    origin = settings.wiki.base_url
    total = 0
    for css in sorted(out_dir.rglob("*.css")):
        text = css.read_text(encoding="utf-8")
        rewritten, n = resolve_css_urls(text, origin)
        if n:
            css.write_text(rewritten, encoding="utf-8")
            total += n
    if total:
        logger.info("PWA: CSS url() переписано на %s (%d ссылок)", origin, total)


def _write_search(model: SiteModel, out_dir: Path) -> None:
    """Пишет ``search.json`` — индекс клиентского поиска (навигация не индексируется)."""
    index = build_search_index(model, exclude_slugs=frozenset({NAV_SOURCE_SLUG}))
    save_json(index, out_dir / "search.json")


def _write_manifest(settings: Settings, out_dir: Path) -> None:
    """Пишет ``manifest.webmanifest`` из ``[pwa]``. start_url/scope — относительные."""
    pwa = settings.pwa
    manifest = {
        "name": pwa.name,
        "short_name": pwa.short_name,
        "start_url": "./",
        "scope": "./",
        "display": pwa.display,
        "theme_color": pwa.theme_color,
        "background_color": pwa.background_color,
        "icons": [
            {"src": pwa.icon, "sizes": "any", "type": "image/png", "purpose": "any"},
            {"src": pwa.icon, "sizes": "any", "type": "image/png", "purpose": "maskable"},
        ],
    }
    save_json(manifest, out_dir / "manifest.webmanifest")


def _precache_paths(out_dir: Path) -> list[str]:
    """Относительные (posix) пути всех файлов сборки, кроме самого ``sw.js``.

    ``sw.js`` не включаем в precache: иначе addAll закеширует устаревшую версию воркера
    и помешает её обновлению. Добавляем ``./`` — корневую навигацию (GitHub Pages
    отдаёт по нему index.html), чтобы офлайн-открытие сайта тоже попадало в кэш.
    """
    paths: list[str] = ["./"]
    for f in sorted(out_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = PurePosixPath(f.relative_to(out_dir)).as_posix()
        if rel == "sw.js":
            continue
        paths.append(rel)
    return paths


def _build_version(paths: list[str], out_dir: Path) -> str:
    """Детерминированный кэш-бастинг: короткий хэш от имён и содержимого файлов.

    Любое изменение в сборке меняет имя кэша -> activate чистит старый и precache
    перелистывает заново; одинаковый вход даёт одинаковый номер (воспроизводимость).
    """
    digest = hashlib.sha256()
    for rel in paths:
        if rel == "./":
            continue
        digest.update(rel.encode("utf-8"))
        digest.update((out_dir / rel).read_bytes())
    return digest.hexdigest()[:12]


def _write_sw(settings: Settings, out_dir: Path) -> None:
    """Пишет ``sw.js``: precache полного состава сборки + cache-first для same-origin."""
    paths = _precache_paths(out_dir)
    version = _build_version(paths, out_dir)
    precache = ", ".join(f'"{p}"' for p in paths)
    sw = SW_JS.replace("__CACHE_NAME__", version).replace("__PRECACHE__", f"[{precache}]")
    write_text(out_dir / "sw.js", sw, settings.chm.page_encoding)
    logger.info("PWA: sw.js записан (кэш qsp-pwa-%s, файлов %d)", version, len(paths))
