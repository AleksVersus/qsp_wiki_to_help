# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportIndexIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOperatorIssue=false
# Ограничения stub'ов bs4 (как в links.py): find_all/select типизированы как union
# PageElement/NavigableString, но для <img> это всегда Tag; runtime-проверки не
# добавляем — порт 1:1 (параметры el/img аннотированы Tag явно).
"""Обработка изображений (порт ChmPrepare.extract_images + replace_src).

Печальную эвристику нечёткого сопоставления имён решено сохранить
(handoff §5): лучшего источника соответствий для уже скачанных файлов нет.
Она вынесена в явную функцию match_wiki_media_name с docstring — чтобы её
можно было тестировать и в Фазе 6 заменить осознанно, а не по случайности.

print-отладка старого кода (['previmg', src]) заменена на logger.debug —
на байты вывода это не влияет (правило приёмки не задевается).
"""

from __future__ import annotations

import logging

from bs4 import Tag

from ..schema import UrlScheme

logger = logging.getLogger(__name__)

# классы-маркеры не видны здесь, но набор фиксирован старым кодом
_ICON_SELECTOR = "img.icon"


def process_images(el: Tag, scheme: UrlScheme, *, base_url: str) -> None:
    """Порт extract_images: поправка src, снятие «кликабельности», иконки.

    base_url параметризует зашитый в старом коде 'https://wiki.qsp.org' —
    на текущем конфиге значения совпадают, вывод побайтовый.
    """
    for img in el.find_all("img", src=True):
        src = str(img["src"])
        logger.debug("img src до обработки: %s", src)

        if src.startswith((base_url, "/_media/")):
            replace_src(img, scheme)
        elif src.startswith("/lib/") and "http" in src:
            # ИСТОРИК: проксированный DokuWiki URL вида
            # /lib/exe/fetch.php?...media=https%3A%2F%2Fwiki...%2F_media%2Fqgen.png
            # — вырезаем http-часть, раскодируем percent-encoding и переводим
            # _media/... в wiki-идентификатор help:...
            src = src[src.index("http") :]
            src = src.replace(r"_media%2F", "/help:")
            src = src.replace(r"%3A", ":").replace(r"%2F", "/")
            img["src"] = src
            logger.debug("img src после lib-раскодирования: %s", src)
            replace_src(img, scheme)

        # «кликабельность» снимается у ВСЕХ картинок, даже не тронутых заменой —
        # как в старом коде (условие стояло вне веток)
        parent = img.parent
        if parent.name == "a":
            parent.unwrap()
        if img.has_attr("width"):  # форс только для уже размеченных — старый код
            img["width"] = "450"

    # ИСТОРИК старого шага: иконки emoticon в текст/удаляются
    for img in el.select(_ICON_SELECTOR):
        if img.has_attr("alt"):
            img.replace_with(str(img["alt"]))
        else:
            img.decompose()


def replace_src(img: Tag, scheme: UrlScheme) -> None:
    """Порт replace_src: точное совпадение url -> эвристика имён (без break!)."""
    src = img["src"]
    name = scheme.image_name(src)
    if name is not None:
        img["src"] = name
        return
    # ИСТОРИК: цикл без break — при нескольких совпадениях побеждает ПОСЛЕДНЕЕ,
    # ровно как в старом коде; порядок обхода = порядок keys в json-манифесте.
    for file_path in scheme.image_names:
        if match_wiki_media_name(file_path) in src:
            img["src"] = file_path


def match_wiki_media_name(file_path: str) -> str:
    """Из скачанного имени файла восстанавливает wiki-идентификатор media.

    DokuWiki хранит media как 'namespace:file', а загрузчик сохраняет их как
    'namespace_file.ext' — поэтому 'help_msgbox.png' -> 'help:msgbox.png'.
    Ломается на именах с '_' внутри файла (известная слабость, backlog §4.2),
    сохраняем как есть до Фазы 6.
    """
    return ":".join(file_path.split("_", 1))
