# pyright: reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportIndexIssue=false
"""Тесты PWA-рендерера (Фаза 8).

Офлайн на маленькой фикстуре (тот же каркас, что test_spa): проверка, что
render_pwa собирает индекс одностраничника + манифест + sw.js + search.json,
добавляет вкладку поиска и регистрирует service worker, а CSS url() уходят на
живой origin вики (§4.13). Плюс юнит-проверки чистых функций search/assets.
    python -m pytest tests/test_pwa.py -v
"""

import json
from pathlib import Path

from qsp_help_builder.config import (
    ChmSettings,
    DocusaurusSettings,
    LoggingSettings,
    PathSettings,
    Settings,
    SpaSettings,
    PwaSettings,
    WikiSettings,
)
from qsp_help_builder.fs_utils import save_json, write_text
from qsp_help_builder.render.pwa.assets import resolve_css_urls
from qsp_help_builder.render.pwa.build import render_pwa
from qsp_help_builder.render.pwa.search import build_search_index, tokenize
from qsp_help_builder.model import Page, SiteModel
from qsp_help_builder.render.profile import SpaProfile
from bs4 import BeautifulSoup

BASE_URL = "https://wiki.qsp.org"


def make_settings(tmp_path: Path) -> Settings:
    wiki = WikiSettings(BASE_URL, 5.0, 0.0, "ua")
    paths = PathSettings(
        root=tmp_path,
        src=tmp_path / "html_src",
        out=tmp_path / "html_out",
        images=tmp_path / "html_src" / "images",
        scheme=tmp_path / "html_src" / "urls_links_to_files.json",
        anchors=tmp_path / "html_src" / "anchors.json",
        spa=tmp_path / "spa_out",
        pwa=tmp_path / "pwa_out",
        docusaurus=tmp_path / "docusaurus_docs",
        docusaurus_bases=tmp_path / "docusaurus_docs" / ".docusaurus_build",
        res_chm=tmp_path / "_res_src" / "chm",
        res_spa=tmp_path / "_res_src" / "spa",
    )
    chm = ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251")
    log = LoggingSettings("DEBUG", tmp_path / "dl.log")
    spa = SpaSettings("start")
    pwa = PwaSettings("start", "QSP — справка", "QSP", "#2f6db0", "#f4f5f7", "standalone",
                      "images/help_wiki_logo.png")
    return Settings(tmp_path / "qsp_help.toml", wiki, paths, spa, pwa, DocusaurusSettings("start"), chm, frozenset(), log)


def seed(tmp_path: Path, settings: Settings) -> None:
    src = settings.paths.src
    write_text(
        src / "start.html",
        '<html><head><title>Старт</title></head><body><div class="page group">'
        '<h1>Добро пожаловать в справку</h1><p>Квесты на квэст скрипт пейджер.</p>'
        '</div></body></html>',
        "utf-8",
    )
    write_text(
        src / "help_coding.html",
        f'<html><head><title>Код</title></head><body><div class="page group">'
        f'<h2 id="funkcii">Функции</h2>'
        f'<p><a href="{BASE_URL}/help:coding#funkcii">на себя</a></p>'
        f'<p><img src="{BASE_URL}/_media/help:msgbox.png"></p>'
        f'<p><img src="help_wiki_logo.png"></p>'
        f'</div></body></html>',
        "utf-8",
    )
    write_text(
        src / "sidebar.html",
        f'<html><head><title>Нав</title></head><body><div class="page group">'
        f'<ul><li><a href="{BASE_URL}/help:coding">Код</a></li></ul>'
        f'</div></body></html>',
        "utf-8",
    )
    save_json(
        {
            "pages": {f"{BASE_URL}/help:coding": r"html_src\help_coding.html"},
            "images": {f"{BASE_URL}/_media/help:msgbox.png": r"html_src\images\help_msgbox.png"},
        },
        settings.paths.scheme,
    )
    save_json({}, settings.paths.anchors)
    (settings.paths.images).mkdir(parents=True, exist_ok=True)
    (settings.paths.images / "help_msgbox.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (settings.paths.out).mkdir(parents=True, exist_ok=True)
    (settings.paths.out / "help_wiki_logo.png").write_bytes(b"\x89PNG\r\n\x1a\nlogo")
    # default.css со wiki-root-absolute url() — должен переписаться на origin
    write_text(
        settings.paths.res_spa / "default.css",
        '.a{background:url(/lib/images/interwiki.png)} .b{background:url("data:image/gif;base64,AAA")}',
        "utf-8",
    )
    write_text(settings.paths.res_spa / "spa.css", ".spa-layout{}", "utf-8")


# ------------------------------------------------------------------ интеграция render_pwa

def test_render_pwa_writes_all_artifacts(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)

    out = settings.paths.pwa
    assert (out / "index.html").is_file()
    assert (out / "manifest.webmanifest").is_file()
    assert (out / "sw.js").is_file()
    assert (out / "search.json").is_file()
    # картинки и css переехали (общий copy_assets с SPA)
    assert (out / "images" / "help_msgbox.png").is_file()
    assert (out / "images" / "help_wiki_logo.png").is_file()
    assert (out / "default.css").is_file()


def test_render_pwa_index_has_manifest_sw_and_search(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)

    index = (settings.paths.pwa / "index.html").read_text(encoding="utf-8")
    # shell-добавки поверх SPA-документа
    assert 'rel="manifest"' in index
    assert 'name="theme-color"' in index
    # контент-секции те же, что у одностраничника
    assert 'data-slug="help_coding"' in index
    assert 'href="#help_coding~funkcii"' in index
    # третья вкладка поиска + инпут
    assert 'data-tab="search"' in index
    assert 'id="searchInput"' in index
    # рантайм читает search.json и регистрирует sw.js
    assert "search.json" in index
    assert 'navigator.serviceWorker.register("sw.js")' in index


def test_render_pwa_css_urls_point_to_wiki_origin(tmp_path: Path):
    # §4.13: декоративные /lib/... в CSS резолвятся на живой origin, data: не трогаем
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)

    css = (settings.paths.pwa / "default.css").read_text(encoding="utf-8")
    assert f"url({BASE_URL}/lib/images/interwiki.png)" in css
    assert "url(/lib" not in css  # ни одного wiki-root-absolute не осталось
    assert "data:image/gif;base64,AAA" in css  # инлайн-ассет не тронут


def test_render_pwa_manifest_matches_config(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)

    manifest = json.loads((settings.paths.pwa / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "QSP — справка"
    assert manifest["short_name"] == "QSP"
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#2f6db0"
    assert manifest["start_url"] == "./" and manifest["scope"] == "./"
    assert manifest["icons"][0]["src"] == "images/help_wiki_logo.png"


def test_render_pwa_search_index_excludes_sidebar(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)

    index = json.loads((settings.paths.pwa / "search.json").read_text(encoding="utf-8"))
    slugs = {d["slug"] for d in index["docs"]}
    assert "help_coding" in slugs and "start" in slugs
    assert "sidebar" not in slugs  # навигация не индексируется
    # термин из контента help_coding обязан присутствовать в postings
    assert "funkcii" in index["postings"] or "функции" in index["postings"]


def test_render_pwa_sw_precache_lists_output_without_sw(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)

    sw = (settings.paths.pwa / "sw.js").read_text(encoding="utf-8")
    assert '"index.html"' in sw and '"search.json"' in sw and '"manifest.webmanifest"' in sw
    assert '"images/help_msgbox.png"' in sw
    assert '"sw.js"' not in sw  # сам воркер в precache не кладём
    # кэш-бастинг: PRECACHE разворачивается в заполненный массив (не токен)
    assert "__PRECACHE__" not in sw and "__CACHE_NAME__" not in sw


def test_render_pwa_is_deterministic(tmp_path: Path):
    # одинаковый вход -> одинаковые sw.js (кэш-имя по содержимому) и index.html
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_pwa(settings)
    first_sw = (settings.paths.pwa / "sw.js").read_text(encoding="utf-8")
    render_pwa(settings)
    assert (settings.paths.pwa / "sw.js").read_text(encoding="utf-8") == first_sw


# ------------------------------------------------------------------ юниты чистых функций

def test_tokenize_lowercases_and_drops_short():
    toks = tokenize("Код ACT a ab action")
    assert "код" in toks and "act" in toks and "action" in toks
    assert "a" not in toks and "ab" not in toks  # короче MIN_TOKEN_LEN отбрасывается


def test_build_search_index_weights_title_and_counts():
    frag = BeautifulSoup('<div class="page group">проверка текста текста</div>', "lxml").select_one("div.page.group")
    assert frag is not None
    page = Page(slug="p", title="Текст", source_soup=BeautifulSoup("<html></html>", "lxml"), fragment=frag)
    model = SiteModel(pages=[page], anchors=None, profile=SpaProfile(), scheme=None)  # type: ignore[arg-type]
    index = build_search_index(model, exclude_slugs=frozenset())
    assert index["docs"][0]["slug"] == "p"
    # стемминга нет: «текст» из title (вес 3) и «текста» из контента (2) — разные термины
    assert index["postings"]["текст"]["0"] == 3
    assert index["postings"]["текста"]["0"] == 2


def test_resolve_css_urls_only_wiki_root_absolute():
    css = (
        '.x{background:url(/lib/a.png)}'
        '.y{background:url("//cdn/b.png")}'
        '.z{background:url("http://h/c.png")}'
        '.w{background:url(/rel.png)}'
        '.d{background:url(data:image/png;base64,AAA)}'
        '.r{background:url(../local/e.png)}'
    )
    out, n = resolve_css_urls(css, "https://wiki.qsp.org")
    assert out.count("https://wiki.qsp.org/lib/a.png") == 1
    assert out.count("https://wiki.qsp.org/rel.png") == 1
    assert n == 2  # переписаны только два ведущих «/»
    assert '"//cdn/b.png"' in out  # протокольно-относительная не тронута
    assert "http://h/c.png" in out and "data:image/png" in out and "../local/e.png" in out


def test_resolve_css_urls_is_idempotent():
    css = ".x{background:url(/lib/a.png)}"
    once, n1 = resolve_css_urls(css, "https://wiki.qsp.org")
    twice, n2 = resolve_css_urls(once, "https://wiki.qsp.org")
    assert once == twice and n1 == 1 and n2 == 0
