"""BFS-краулер wiki.qsp.org: обход по ссылкам, сохранение страниц и картинок.

Порт сетевого ядра из qsp_wiki_downloader.WikiDownloader, но с разбиением,
предписанным планом (Фаза 4):
- чистое извлечение ссылок/картинок вынесено в функции, принимающие soup + данные
  (без self и без сети) — их можно тестировать офлайн;
- скачивание картинок БОЛЬШЕ не побочный эффект extract_links: за обход собираем
  множество URL картинок, а качаем их отдельным проходом после обхода страниц;
- сессия/таймаут/задержка/user-agent берутся из Settings (не захардкожены);
- логгер — logging.getLogger(__name__), НЕ настраивается при импорте (см. config).

Выходные контракты сохранены: html_src/*.html, html_src/images/*,
urls_links_to_files.json (UrlScheme: url -> путь; consumer берёт только имя файла).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..config import Settings
from ..fs_utils import ensure_dir, write_text
from ..schema import UrlScheme
from .naming import IMAGE_EXTENSIONS, image_filename, page_filename

logger = logging.getLogger(__name__)

# Парсер совпадает со старым загрузчиком ('html.parser'): разбор влияет на то,
# какие <a>/<img> будут найдены, поэтому меняем только осознанно.
HTML_PARSER = "html.parser"


def same_domain(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def is_image_url(url: str) -> bool:
    """URL оканчивается на известное расширение картинки (после среза query/frag)."""
    return url.split(".")[-1].lower() in IMAGE_EXTENSIONS


def extract_page_links(soup: BeautifulSoup, page_url: str, base_url: str, visited: set[str]) -> set[str]:
    """Внутренние ссылки на страницы для постановки в очередь обхода.

    Как старый extract_links, но БЕЗ скачивания картинок (это делает
    collect_image_urls). Пропускаем: внешние (href с http), якоря (#...), mailto,
    .php, ссылки на картинки, уже посещённые. Относительные href резолвятся от page_url.
    """
    links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("http") or href.startswith("#") or href.startswith("mailto:"):
            continue
        full_url = urljoin(page_url, href).split("?")[0].split("#")[0]
        if full_url in visited:
            continue
        if full_url.endswith(".php") or is_image_url(full_url):
            continue
        if same_domain(full_url, base_url):
            links.add(full_url)
    return links


def collect_image_urls(soup: BeautifulSoup, page_url: str, base_url: str) -> set[str]:
    """URL картинок со страницы — из <a href> и из <img src> (объединяем).

    Соответствует двум местам старого кода:
    - extract_links ловил картинки по <a href> (url ПОСЛЕ среза query/frag);
    - extract_images ловил картинки по <img src> (url С query, как в wiki).
    Пропускаем счётчик-пиксель indexer.php и чужие домены.
    """
    images: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("http") or href.startswith("#") or href.startswith("mailto:"):
            continue
        full_url = urljoin(page_url, href).split("?")[0].split("#")[0]
        if is_image_url(full_url) and same_domain(full_url, base_url):
            images.add(full_url)

    indexer_prefix = base_url + "/lib/exe/indexer.php"
    for img in soup.find_all("img", src=True):
        src = img["src"]
        image_url = src if src.startswith("http") else str(urljoin(page_url, src))
        if image_url.startswith(indexer_prefix):
            continue
        if same_domain(image_url, base_url):
            images.add(image_url)
    return images


@dataclass
class DownloadStats:
    pages_ok: int = 0
    pages_failed: int = 0
    images_ok: int = 0
    images_failed: int = 0
    failed_page_urls: set[str] = field(default_factory=set)
    failed_image_urls: set[str] = field(default_factory=set)

    @property
    def images_found(self) -> int:
        return self.images_ok + self.images_failed


class Crawler:
    """Сетевой обходчик. Отделяет «что скачать» (pure-функции выше) от «как скачать»."""

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.base_url = settings.wiki.base_url
        self.timeout = settings.wiki.timeout_sec
        self.delay = settings.wiki.delay_sec
        self.session = session or self._make_session()
        self.scheme = UrlScheme()
        self.stats = DownloadStats()

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": self.settings.wiki.user_agent})
        return session

    def _rel(self, path: Path) -> str:
        """Путь относительно корня проекта — значение в scheme (потребитель берёт имя файла)."""
        try:
            return str(path.relative_to(self.settings.paths.root))
        except ValueError:
            return str(path)

    def fetch(self, url: str) -> str | None:
        """GET страницы с таймаутом из настроек; кодировка фиксирована utf-8 (как в оригинале)."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as exc:
            logger.error("Ошибка при загрузке %s: %s", url, exc)
            return None

    def save_page(self, url: str, html_content: str) -> bool:
        filename = page_filename(url)
        filepath = self.settings.paths.src / filename
        try:
            ensure_dir(filepath.parent)
            write_text(filepath, html_content, "utf-8")
            self.scheme.pages[url] = self._rel(filepath)
            logger.info("Сохранена страница: %s", filename)
            return True
        except OSError as exc:
            logger.error("Ошибка при сохранении %s: %s", url, exc)
            return False

    def download_image(self, image_url: str) -> bool:
        """Качает одну картинку и кладёт в images_dir под именем из naming.image_filename."""
        try:
            response = self.session.get(image_url, timeout=self.timeout)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            filename = image_filename(image_url, content_type)
            filepath = self.settings.paths.images / filename
            ensure_dir(filepath.parent)
            filepath.write_bytes(response.content)
            self.scheme.images[image_url] = self._rel(filepath)
            logger.info("Скачано изображение: %s", filename)
            return True
        except (requests.RequestException, OSError) as exc:
            logger.error("Ошибка при скачивании изображения %s: %s", image_url, exc)
            return False

    def crawl_pages(self) -> set[str]:
        """BFS от base_url: сохраняет страницы, возвращает собранные URL картинок.

        Скачивание картинок намеренно НЕ здесь (фикс Фаза 4): здесь только собираем
        их URL в множество, отдаём вызывающему на отдельный проход download_images.
        """
        image_urls: set[str] = set()
        visited: set[str] = set()
        queue = [self.base_url]
        ensure_dir(self.settings.paths.src)
        ensure_dir(self.settings.paths.images)

        while queue:
            current_url = queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)
            logger.info("Обрабатываю: %s", current_url)

            html_content = self.fetch(current_url)
            if html_content is None:
                self.stats.pages_failed += 1
                self.stats.failed_page_urls.add(current_url)
                continue
            if self.save_page(current_url, html_content):
                self.stats.pages_ok += 1

            soup = BeautifulSoup(html_content, HTML_PARSER)
            for link in extract_page_links(soup, current_url, self.base_url, visited):
                queue.append(link)
            image_urls |= collect_image_urls(soup, current_url, self.base_url)

            time.sleep(self.delay)

        return image_urls

    def download_images(self, image_urls: set[str]) -> None:
        """Отдельный проход по собранным URL картинок (урендеренный download_image)."""
        for image_url in sorted(image_urls):
            if self.download_image(image_url):
                self.stats.images_ok += 1
            else:
                self.stats.images_failed += 1
                self.stats.failed_image_urls.add(image_url)

    def run(self) -> DownloadStats:
        """Полный этап выгрузки: обход страниц → прогон картинок → запись scheme."""
        logger.info("Начинаю скачивание с %s", self.base_url)
        image_urls = self.crawl_pages()
        self.download_images(image_urls)
        self.scheme.save(self.settings.paths.scheme)
        logger.info(
            "Скачивание завершено: страниц %d (ошибок %d), картинок %d (ошибок %d)",
            self.stats.pages_ok, self.stats.pages_failed,
            self.stats.images_ok, self.stats.images_failed,
        )
        return self.stats
