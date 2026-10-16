"""Именование локальных файлов из URL вики (чистые функции, без сети).

Порт логики сохранения из qsp_wiki_downloader.WikiDownloader (save_page /
download_image), где она была перемешана с сетевым кодом. Формат имён — часть
выходного контракта html_src (handoff §2.1): его менять нельзя, иначе рассогласуется
urls_links_to_files.json и Prepare-этап перестанет находить файлы.

Правила перенесены и исправлены (см. handoff §4.2):
- страница: части URL-path через '_' + '.html', root -> 'index.html';
- картинка: base последней части пути (или значения media у fetch.php) +
  расширение из content-type / суффикса имени.

DokuWiki отдаёт медиа через '/lib/exe/fetch.php?media=<идентификатор>', где путь
всегда 'fetch.php' — старый код выводил все такие картинки в один 'fetch.png'.
Теперь base берётся из значения `media` (namespace:id -> namespace_id), поэтому
разные картинки больше не схлопываются (backlog §4.2 устранён).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import parse_qs, unquote, urlparse

# Недопустимые символы имени файла Windows -> '_': та же регулярка, что в старом коде
# для частей пути страницы и для base-имени картинки.
_UNSAFE = re.compile(r'[<>:"/\\|?*]')

# Расширения, которые краулер считает картинками (совпадает с проверкой в
# extract_links/extract_images старого загрузчика).
IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "webp")

# Fallback-расширение, когда content-type не'image/*' и URL не заканчивается
# на известное разрешение — как в старом download_image.
DEFAULT_IMAGE_EXT = "jpg"


def _safe(part: str) -> str:
    return _UNSAFE.sub("_", part)


def page_filename(url: str) -> str:
    """Имя html-файла страницы по URL.

    Корневой URL (пустой path) -> 'index.html'; иначе части пути, очищенные от
    недопустимых символов, соединяются через '_' и получают '.html'.
    (В старом save_page url сначала резался на path-части тем же способом.)
    """
    path_parts = urlparse(url).path.strip("/").split("/")
    if not path_parts or path_parts[0] == "":
        return "index.html"
    return "_".join(_safe(part) for part in path_parts) + ".html"


def media_value(url: str) -> str | None:
    """Значение query-параметра 'media' (already percent-decoded) или None.

    DokuWiki-медиа отдают через fetch.php?media=<wiki-id или url>.
    """
    values = parse_qs(urlparse(url).query).get("media")
    return values[0] if values else None


def image_ext_from_name(name: str) -> str:
    """Расширение картинки из имени ('help:qgen.png' -> 'png'); '' если неизвестно."""
    suffix = PurePosixPath(unquote(name)).suffix.lower().lstrip(".")
    if suffix == "jpeg":
        return "jpg"
    return suffix if suffix in IMAGE_EXTENSIONS else ""


def is_image_url(url: str) -> bool:
    """Картинка ли это: расширение в пути ИЛИ в значении media у fetch.php."""
    if any(urlparse(url).path.lower().endswith("." + e) for e in IMAGE_EXTENSIONS):
        return True
    media = media_value(url)
    return bool(media) and bool(image_ext_from_name(media))


def image_extension(content_type: str, url: str) -> str:
    """Расширение файла картинки: сначала из content-type, иначе из имени/media, иначе jpg.

    'image/jpeg' нормализуется в 'jpg' (как в старом download_image). Если
    content-type не 'image/', пробуем разрешение из значения media (для
    fetch.php) или из пути URL; если и его нет — DEFAULT_IMAGE_EXT.
    """
    if "image/" in (content_type or ""):
        ext = content_type.split("/")[-1].split(";")[0].strip().lower()
        return "jpg" if ext == "jpeg" else ext
    media = media_value(url)
    return image_ext_from_name(media) if media else image_ext_from_name(urlparse(url).path) or DEFAULT_IMAGE_EXT


def image_filename(url: str, content_type: str) -> str:
    """Имя файла картинки: base из media (для fetch.php) либо из пути + расширение.

    Для DokuWiki fetch.php?media=<...> base — последняя часть значения media с
    ':'->'_' (namespace:id -> namespace_id), поэтому картинки больше не сходятся
    в 'fetch.png' (устранено §4.2). Для обычных _media/_detail URL — прежнее
    поведение: base последней части пути.
    """
    ext = image_extension(content_type, url)
    media = media_value(url)
    if media:
        last = unquote(media).rstrip("/").split("/")[-1]
        base = _safe(PurePosixPath(last).stem)
        return f"{base or 'image'}.{ext}"
    path_parts = urlparse(url).path.strip("/").split("/")
    if not path_parts or path_parts[0] == "":
        base = PurePosixPath(url).name or "image"
    else:
        base = path_parts[-1]
    base = _safe(PurePosixPath(base).stem)
    return f"{base}.{ext}"
