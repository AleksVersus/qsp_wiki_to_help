"""Именование локальных файлов из URL вики (чистые функции, без сети).

Порт логики сохранения из qsp_wiki_downloader.WikiDownloader (save_page /
download_image), где она была перемешана с сетевым кодом. Формат имён — часть
выходного контракта html_src (handoff §2.1): его менять нельзя, иначе рассогласуется
urls_links_to_files.json и Prepare-этап перестанет находить файлы.

Правила перенесены 1:1 (включая известный баг среза query-строки — см. image_filename):
- страница: части URL-path через '_' + '.html', root -> 'index.html';
- картинка: последняя часть пути без расширения + расширение из content-type.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

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


def image_extension(content_type: str, url: str) -> str:
    """Расширение файла картинки: сначала из content-type, иначе из URL, иначе jpg.

    'image/jpeg' нормализуется в 'jpg' (как в старом download_image). Если
    content-type не содержит 'image/', пробуем разрешение из пути URL; если и
    его нет в известном списке — DEFAULT_IMAGE_EXT.
    """
    if "image/" in (content_type or ""):
        ext = content_type.split("/")[-1].split(";")[0].strip().lower()
        return "jpg" if ext == "jpeg" else ext
    path = urlparse(url).path.lower()
    for candidate in IMAGE_EXTENSIONS:
        if path.endswith("." + candidate):
            return "jpg" if candidate == "jpeg" else candidate
    return DEFAULT_IMAGE_EXT


def image_filename(url: str, content_type: str) -> str:
    """Имя файла картинки: base последней части пути + расширение.

    ИСТОРИЧЕСКИЙ БАГ (backlog handoff §4.2, осознано сохранён): DokuWiki отдаёт
    media через '/lib/exe/fetch.php?media=...', где путь — всегда 'fetch.php'.
    Поэтому base-имя получается 'fetch' и разные картинки сходятся в один файл
    ('качаются неверными именами'). Починка сдвинула бы выход относительно
    бейзлайна — чинится отдельным решением, не здесь.
    """
    ext = image_extension(content_type, url)
    path_parts = urlparse(url).path.strip("/").split("/")
    if not path_parts or path_parts[0] == "":
        base = PurePosixPath(url).name or "image"
    else:
        base = path_parts[-1]
    base = _safe(PurePosixPath(base).stem)
    return f"{base}.{ext}"
