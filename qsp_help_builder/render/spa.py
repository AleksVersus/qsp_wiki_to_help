# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownArgumentType=false, reportIndexIssue=false, reportArgumentType=false
"""Рендерер-одностраничник (SPA): модель -> ``spa_out/index.html`` + ``images/``.

Гибрид (решение п.4/7): один ``index.html`` и локальная папка картинок рядом —
без base64 и без zip. Открывается двойным кликом с ``file://`` (как CHM), но
навигация — hash-router поверх встроенного JS: ссылки ``#slug``, якоря
``#slug~anchor``.

Дизайн — двухпанельный (каркас в ``_res_src/spa/spa.css``, стили контента — из
DokuWiki ``default.css``; ``<body>`` размечен классом ``dokuwiki``, чтобы эти
стили применялись): слева узкая панель (~30%) с вкладками «Содержание»
(``#toc``) и «Указатель» (``#index``), справа — широкий контент (``#content``);
панели прокручиваются независимо, левую можно свернуть в полоску. На мобильном
(<768px) остаётся только контент и верхний бар из двух кнопок, открывающих
панель полноэкранным оверлеем; пункты содержания сворачиваемые (caret'ом).

Всё содержательное берётся из модели, собранной с ``SpaProfile`` (те же примитивы
``prepare``, что и для CHM). Специфика SPA здесь:
- namespace id внутри каждой страницы -> ``{slug}~{anchor}`` (иначе коллизии
  одинаковых id заголовков между страницами в одном документе);
- каждая страница — ``<section data-slug=... >``; показывается одна по хешу;
- содержание (``#toc``) строится из страницы ``sidebar`` (её ссылки уже ``#slug``);
- указатель (``#index``) — список ключевых слов из таблицы ``help_keywords`` со
  ссылками ``#slug~anchor`` по якорям из anchors.json (тот же контракт, что у
  CHM-указателя qsp.hhk); вкладки/сворачивание/оверлей/сворачиваемый TOC — JS из
  ``SPA_PAGE``;
- якоря из anchors.json вставляются в контент страниц по номерам строк — как в
  CHM (``wrap_into_template`` + ``Anchors.inject_into_text``), затем namespace'ятся
  до ``{slug}~{anchor}``, чтобы ссылки указателя резолвились в одном документе;
- картинки из манифеста модели копируются в ``images/`` (источник: html_src/images,
  с откатом на html_out для легаси-ассетов вроде логотипа).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup, Tag

from ..anchors import Anchors
from ..config import Settings
from ..fs_utils import copy_tree, ensure_dir, file_name, write_text
from ..model import Page, SiteModel, build_site_model
from ..prepare.hhk import extract_hhk_data
from ..prepare.page_clean import wrap_into_template
from .profile import SpaProfile

logger = logging.getLogger(__name__)

SPA_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QSP — справка</title>
<link type="text/css" href="default.css" rel="stylesheet" />
<link type="text/css" href="spa.css" rel="stylesheet" />
</head>
<body class="dokuwiki">
<div class="spa-layout">
<aside class="spa-sidebar" id="sidebar">
<div class="spa-sidebar-head">
<button type="button" class="spa-tab active" data-tab="toc">Содержание</button>
<button type="button" class="spa-tab" data-tab="index">Указатель</button>
<button type="button" class="spa-toggle" id="toggleBtn" title="Свернуть/развернуть панель">&#8249;</button>
<button type="button" class="spa-close" id="closeBtn" title="Закрыть">&#215;</button>
</div>
<div class="spa-sidebar-body">
<nav class="spa-panel active" id="toc"></nav>
<nav class="spa-panel" id="index"></nav>
</div>
</aside>
<main class="spa-content" id="content"></main>
</div>
<div class="spa-mobilebar">
<button type="button" data-tab="toc">Содержание</button>
<button type="button" data-tab="index">Указатель</button>
</div>
<script>
(function () {
  var QUERY = "(max-width: 768px)";
  var sidebar = document.getElementById("sidebar");

  function isMobile() {
    return !!(window.matchMedia && window.matchMedia(QUERY).matches);
  }

  // hash-роутер: показываем одну секцию-страницу, скроллим к якорю #slug~anchor
  function showSection() {
    var hash = location.hash.slice(1);
    var slug = hash.split("~")[0];
    var sections = document.getElementsByTagName("section");
    var shown = false;
    for (var i = 0; i < sections.length; i++) {
      var on = sections[i].getAttribute("data-slug") === slug;
      sections[i].hidden = !on;
      shown = shown || on;
    }
    if (!slug && sections.length) { sections[0].hidden = false; }
    if (hash) {
      var target = document.getElementById(hash);
      if (target) { target.scrollIntoView(); }
    }
  }

  function setTab(name) {
    var panels = document.querySelectorAll(".spa-panel");
    for (var i = 0; i < panels.length; i++) {
      panels[i].classList.toggle("active", panels[i].id === name);
    }
    var btns = document.querySelectorAll("[data-tab]");
    for (var j = 0; j < btns.length; j++) {
      btns[j].classList.toggle("active", btns[j].getAttribute("data-tab") === name);
    }
  }

  function openOverlay(on) {
    sidebar.classList.toggle("open", !!on);
  }

  // переключение вкладки; на мобильном вкладка ещё и открывает оверлей
  function clickTab(name) {
    setTab(name);
    if (isMobile()) { openOverlay(true); }
  }

  // пункты содержания со вложенным списком делаем сворачиваемыми (caret слева)
  function initCollapsible() {
    var items = sidebar.querySelectorAll("#toc li");
    for (var i = 0; i < items.length; i++) {
      var li = items[i], sub = null, kids = li.children;
      for (var k = 0; k < kids.length; k++) {
        if (kids[k].tagName === "UL") { sub = kids[k]; break; }
      }
      if (!sub) { continue; }
      li.className += " has-children";
      var label = li.querySelector(".li") || li;
      var caret = document.createElement("span");
      caret.className = "spa-caret";
      caret.setAttribute("aria-hidden", "true");
      label.insertBefore(caret, label.firstChild);
      (function (item) {
        caret.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          item.classList.toggle("collapsed");
        });
      })(li);
    }
  }

  // единый делегированный обработчик: вкладки / свернуть / закрыть / переход
  document.addEventListener("click", function (e) {
    if (!e.target || !e.target.closest) { return; }
    var btn = e.target.closest("[data-tab], #toggleBtn, #closeBtn");
    if (btn) {
      var tab = btn.getAttribute("data-tab");
      if (tab) { clickTab(tab); return; }
      if (btn.id === "toggleBtn") { sidebar.classList.toggle("collapsed"); return; }
      if (btn.id === "closeBtn") { openOverlay(false); return; }
    }
    // на мобильном клик по ссылке панели закрывает оверлей — виден контент
    var link = e.target.closest("a");
    if (link && isMobile() && sidebar.contains(link)) { openOverlay(false); }
  });

  window.addEventListener("hashchange", showSection);
  document.addEventListener("DOMContentLoaded", function () {
    showSection();
    setTab("toc");
    initCollapsible();
  });
})();
</script>
</body>
</html>"""

# Навигационная страница-источник (help:sidebar) не показывается как контент.
NAV_SOURCE_SLUG = "sidebar"
# Страница-источник указателя (help:keywords): её таблица задаёт порядок и
# состав ключевых слов — тот же контракт, что у CHM-указателя (qsp.hhk).
HHK_SOURCE_SLUG = "help_keywords"
# Парсер для повторного разбора собранной страницы (совпадает с model/prepare).
HTML_PARSER = "lxml"


def render_spa(settings: Settings) -> None:
    """Собирает одностраничник по настройкам (полностью офлайн)."""
    model = build_site_model(settings, SpaProfile())
    spa_dir = ensure_dir(settings.paths.spa)

    soup = BeautifulSoup(SPA_PAGE, "lxml")
    nav = soup.find(id="toc")
    index = soup.find(id="index")
    main = soup.find(id="content")

    sidebar = model.by_slug.get(NAV_SOURCE_SLUG)
    if sidebar is not None:
        _namespace_ids(sidebar.fragment, sidebar.slug)
        nav.append(sidebar.fragment)

    # Указатель строится ДО раскладки контента: он лишь читает таблицу
    # help_keywords (порядок/состав) и anchors.json (цели ссылок), а контент-цикл
    # ниже перемещает/пересобирает фрагменты страниц.
    _fill_index(model, soup, index)

    for page in _content_pages(model, settings.spa.start_page):
        fragment = _with_anchors(page, model.anchors)
        _namespace_ids(fragment, page.slug)
        section = soup.new_tag("section")
        section["id"] = page.slug
        section["data-slug"] = page.slug
        section["hidden"] = ""
        section.append(fragment)
        main.append(section)

    _normalize_local_images(soup)
    write_text(spa_dir / "index.html", str(soup), settings.chm.page_encoding)
    _copy_assets(model, settings, spa_dir)
    logger.info("Одностраничник собран: %s (страниц %d)", spa_dir / "index.html", len(model.pages))


def _content_pages(model: SiteModel, start_slug: str) -> list[Page]:
    """Порядок секций контента: ``start_slug`` первым, остальные — как в модели.

    Router без хеша показывает ``sections[0]``, поэтому стартовая страница из
    конфига должна идти в DOM первой (страница ``sidebar`` в контент не попадает —
    она ушла в навигацию). Если стартовый slug не найден среди контента, порядок
    остаётся модельным и пишется предупреждение.
    """
    pages = [p for p in model.pages if p.slug != NAV_SOURCE_SLUG]
    start = next((p for p in pages if p.slug == start_slug), None)
    if start is None:
        logger.warning("SPA: стартовая страница %r не найдена среди контента", start_slug)
        return pages
    return [start, *(p for p in pages if p is not start)]


def _with_anchors(page: Page, anchors: Anchors) -> Tag:
    """Возвращает фрагмент страницы с вставленными якорями из anchors.json.

    По аналогии с CHM (:func:`render.chm.render_chm`): якоря вставляются по
    0-based номерам строк, отсчитанным от обёрнутой страницы. Поэтому для
    страниц с якорями собираем тот же текст (``wrap_into_template`` +
    ``inject_into_text``) и разбираем его обратно, забирая ``div.page.group`` —
    так позиция вставки совпадает с CHM побайтово. Страницы без якорей
    возвращаются как есть (без лишнего переразбора).
    """
    if not anchors.anchors_for(page.slug):
        return page.fragment
    text = anchors.inject_into_text(wrap_into_template(page.source_soup, page.fragment), page.slug)
    inner = BeautifulSoup(text, HTML_PARSER).select_one("div.page.group")
    return inner if inner is not None else page.fragment


def _fill_index(model: SiteModel, soup: BeautifulSoup, index: Tag) -> None:
    """Строит блок указателя ``<nav id=index>`` из help_keywords + anchors.json.

    Порядок и состав ключевых слов берутся из таблицы help_keywords (тот же
    контракт, что у CHM: :func:`prepare.hhk.extract_hhk_data`), а идентификатор и
    страница ссылки — из anchors.json (:meth:`Anchors.keywords_map`). Ключ, для
    которого в anchors.json нет записи, в указатель не попадает (некуда вести
    ссылке). Итоговая ссылка ``#slug~anchor`` совпадает с namespace-якорями
    контента, которые ставит :func:`_namespace_ids`.
    """
    page = model.by_slug.get(HHK_SOURCE_SLUG)
    table = page.fragment.find("table") if page is not None else None
    if table is None:
        logger.warning("SPA: указатель не собран — нет таблицы ключевых слов (%s)", HHK_SOURCE_SLUG)
        return

    keywords_anchors = model.anchors.keywords_map()
    ul = soup.new_tag("ul")
    count = 0
    for title in extract_hhk_data(table):  # dict: порядок строк таблицы help_keywords
        target = keywords_anchors.get(title)
        if target is None:
            continue  # ключ без якоря в anchors.json — некуда вести ссылку
        link = soup.new_tag("a", href=_spa_anchor_href(target))
        link.string = title
        li = soup.new_tag("li")
        li.append(link)
        ul.append(li)
        count += 1
    index.append(ul)
    logger.info("SPA: указатель собран (записей %d)", count)


def _spa_anchor_href(target: str) -> str:
    """``file.htm#anchor`` (из anchors.json) -> ``#slug~anchor`` hash-навигации SPA."""
    file_part, _, anchor = target.partition("#")
    slug = PurePosixPath(file_part).stem
    return f"#{slug}~{anchor}" if anchor else f"#{slug}"


def _namespace_ids(fragment: Tag, slug: str) -> None:
    """Префиксирует все id внутри страницы, чтобы они были уникальны в одном документе."""
    for el in fragment.find_all(id=True):
        el["id"] = f"{slug}~{el['id']}"


def _normalize_local_images(soup: BeautifulSoup) -> None:
    """Доводит легаси-картинки до ``images/<имя>``.

    ``SpaProfile.image_href`` оформляет лишь те ``src``, что резолвятся через
    scheme. Ручные легаси-ассеты (``help_wiki_logo.png`` из ``apply_start_fixes``)
    проходят мимо профиля и остаются голым именем — здесь они так же уходят в
    ``images/``. Внешние (``://``) и абсолютные (``/``) ссылки не трогаем; то, что
    уже под ``images/``, оставляем как есть. Файлы в ``images/`` кладёт
    :func:`_copy_assets` (он берёт базовое имя из тех же ``src``).
    """
    for img in soup.find_all("img", src=True):
        src = str(img["src"])
        if "://" in src or src.startswith("/") or src.startswith("images/"):
            continue
        img["src"] = f"images/{file_name(src)}"


def _copy_assets(model: SiteModel, settings: Settings, spa_dir: Path) -> None:
    """Копирует используемые картинки в spa_out/images и статичные ресурсы рядом."""
    images_dir = ensure_dir(spa_dir / "images")
    sources = (settings.paths.images, settings.paths.out)
    for name in sorted(model.referenced_images()):
        src = next((d / name for d in sources if (d / name).is_file()), None)
        if src is None:
            logger.warning("SPA: картинка не найдена ни в html_src/images, ни в html_out: %s", name)
            continue
        shutil.copy2(src, images_dir / name)

    # default.css и прочие статичные ресурсы SPA — из _res_src/spa (свой, не из html_out)
    res = copy_tree(settings.paths.res_spa, spa_dir)
    if res:
        logger.info("SPA: ресурсы скопированы из %s: %s", settings.paths.res_spa, ", ".join(res))
    else:
        logger.warning("SPA: папка ресурсов %s пуста или отсутствует — стили не подключены",
                       settings.paths.res_spa)
