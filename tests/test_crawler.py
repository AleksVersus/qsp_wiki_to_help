"""Юнит-тесты download-краулера (Фаза 4).

Офлайн: сеть подменяется фиктивной сессией, time.sleep отключается обнулённой
задержкой. Проверяются чистые функции извлечения и полный BFS-прогон с отдельным
проходом картинок (без реального wiki).
    python -m pytest tests/test_crawler.py -v
"""

from pathlib import Path

import pytest
import requests
from bs4 import BeautifulSoup

from qsp_help_builder.config import (
    ChmSettings,
    LoggingSettings,
    PathSettings,
    Settings,
    WikiSettings,
)
from qsp_help_builder.download.crawler import (
    Crawler,
    collect_image_urls,
    extract_page_links,
)

BASE = "https://wiki.qsp.org"


# ------------------------------------------------------------------ fake session

class FakeResponse:
    def __init__(self, *, text="", content=b"", headers=None, status=200):
        self.text = text
        self.content = content
        self.headers = headers or {}
        self.status = status
        self.encoding = None

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}", response=self)


class FakeSession:
    """Маршрутизирует url -> заготовленный ответ; считает обращения к url."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url not in self.routes:
            return FakeResponse(status=404)
        return self.routes[url]


# ---------------------------------------------------------- extract_page_links

def _soup(html):
    return BeautifulSoup(html, "html.parser")


def test_extract_page_links_keeps_internal_relative_links():
    soup = _soup('<a href="/help:coding">код</a><a href="start">старт</a>')
    links = extract_page_links(soup, BASE, BASE, visited=set())
    assert f"{BASE}/help:coding" in links
    assert f"{BASE}/start" in links


def test_extract_page_links_skips_external_anchor_mailto_php_image_visited():
    soup = _soup(
        '<a href="http://other.example/x">внеш</a>'
        '<a href="#top">якорь</a>'
        '<a href="mailto:a@b.c">почта</a>'
        '<a href="/lib/exe/indexer.php">php</a>'
        '<a href="/_media/pic.png">картинка</a>'
        '<a href="/start">уже посещено</a>'
    )
    links = extract_page_links(soup, BASE, BASE, visited={f"{BASE}/start"})
    assert links == set()


def test_extract_page_links_strips_query_and_fragment():
    soup = _soup('<a href="/help:arrays?rev=2#sec">массивы</a>')
    links = extract_page_links(soup, BASE, BASE, visited=set())
    assert links == {f"{BASE}/help:arrays"}


# ---------------------------------------------------------- collect_image_urls

def test_collect_image_urls_from_img_src_keeps_query():
    soup = _soup('<img src="/_media/help:msgbox.png?w=200&tok=ab">')
    urls = collect_image_urls(soup, BASE, BASE)
    assert urls == {f"{BASE}/_media/help:msgbox.png?w=200&tok=ab"}


def test_collect_image_urls_skips_indexer_and_external():
    soup = _soup(
        '<img src="/lib/exe/indexer.php?x=1">'
        '<img src="https://cdn.other.example/pic.png">'
    )
    assert collect_image_urls(soup, BASE, BASE) == set()


def test_collect_image_urls_from_anchor_image():
    soup = _soup('<a href="/_media/logo.gif">логотип</a>')
    assert collect_image_urls(soup, BASE, BASE) == {f"{BASE}/_media/logo.gif"}


# ------------------------------------------------------------------ full run

@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    wiki = WikiSettings(base_url=BASE, timeout_sec=5.0, delay_sec=0.0, user_agent="test-ua")
    paths = PathSettings(
        root=tmp_path,
        src=tmp_path / "html_src",
        out=tmp_path / "html_out",
        images=tmp_path / "html_src" / "images",
        scheme=tmp_path / "html_src" / "urls_links_to_files.json",
        anchors=tmp_path / "html_src" / "anchors.json",
    )
    chm = ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251")
    log = LoggingSettings(level="DEBUG", download_log=tmp_path / "dl.log")
    return Settings(tmp_path / "qsp_help.toml", wiki, paths, chm, frozenset(), log)


def test_crawler_run_traverses_pages_and_downloads_images_separately(settings):
    # Ссылки — с ведущим слэшем (как в реальном DokuWiki); без него urljoin принял
    # бы 'help:coding' за схему URL.
    root_html = '<a href="/start">start</a><a href="/help:coding">код</a><img src="/_media/help:msgbox.png?w=200">'
    routes = {
        BASE: FakeResponse(text=root_html),
        f"{BASE}/start": FakeResponse(text="<p>привет</p>"),
        f"{BASE}/help:coding": FakeResponse(text='<img src="/lib/exe/indexer.php?i=1">'),
        f"{BASE}/_media/help:msgbox.png?w=200": FakeResponse(
            content=b"\x89PNG-bytes", headers={"content-type": "image/png"}
        ),
    }
    session = FakeSession(routes)

    crawler = Crawler(settings, session=session)
    stats = crawler.run()

    # Страницы сохранены под историческими именами.
    src = settings.paths.src
    assert (src / "index.html").is_file()
    assert (src / "start.html").is_file()
    assert (src / "help_coding.html").is_file()

    # Картинка скачана в отдельном проходе: ':' в media-имени -> '_' (help_msgbox.png).
    assert (src / "images" / "help_msgbox.png").is_file()

    # Статистика: 3 страницы ок, 1 картинка ок; indexer не скачан.
    assert stats.pages_ok == 3
    assert stats.images_ok == 1
    assert f"{BASE}/lib/exe/indexer.php?i=1" not in crawler.scheme.images

    # Scheme записан и читается обратно контрактом UrlScheme.
    from qsp_help_builder.schema import UrlScheme

    loaded = UrlScheme.load(settings.paths.scheme)
    assert BASE in loaded.pages
    assert f"{BASE}/_media/help:msgbox.png?w=200" in loaded.images


def test_crawler_records_failed_pages(settings):
    routes = {
        BASE: FakeResponse(text='<a href="/missing">нет</a>'),
        # /missing возвращает 404 (FakeSession отдаёт статус 404 для неизвестного url)
    }
    crawler = Crawler(settings, session=FakeSession(routes))
    stats = crawler.run()
    assert stats.pages_ok == 1
    assert stats.pages_failed == 1
    assert f"{BASE}/missing" in stats.failed_page_urls
