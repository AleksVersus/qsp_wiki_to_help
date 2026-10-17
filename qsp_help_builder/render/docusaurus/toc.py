# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownArgumentType=false, reportIndexIssue=false, reportArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportOptionalSubscript=false
"""Разбор содержания (sidebar) в дерево и раскладка по папкам Docusaurus.

Содержание — тот же ``sidebar`` (help:sidebar), что питают CHM (``qsp.hhc``) и
SPA (``#toc``). Его ``<ul>/<li>``-вложенность задаёт уровни: дочерние ``li``
уходят в подпапки, поэтому итоговые ``.mdx`` раскладываются «по уровням
содержания». Ссылки внутри фрагмента уже оформлены ``DocusaurusProfile``
(токен ``DOCLINK::<slug>::<anchor>``), поэтому slug узла читается из href.

Правила раскладки (см. plan «Docusaurus render mode»):
- текстовый заголовок без ссылки c потомками -> папка (имя — транслит метки);
- ссылка без потомков -> ``<slug>.mdx`` в текущей папке;
- ссылка с потомками (напр. «Строки»/«qSpider») -> папка по имени slug, внутри
  неё кладётся и сам документ ``<slug>.mdx`` (он же — индекс категории);
- страницы, не попавшие в содержание -> ``help_add/`` (доопределяет вызывающий).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from bs4 import Tag

from ...render.profile import DOC_LINK_PREFIX

# Категория «вне содержания» — куда кладутся страницы, на которые нет ссылки из TOC.
# Остаётся в корне выхода (рядом с ``.docusaurus_build``), а не внутри
# ``WIKI_DIR`` — так на её документы можно сослаться из дерева и обратно.
HELP_ADD_DIR = "help_add"

# Корень дерева содержания: все TOC-документы и папки-категории собираются внутрь
# этой папки выхода (``<out>/qsp_wiki/...``), оставляя в корне лишь ``help_add``
# и ``.docusaurus_build``. Относительные ссылки между разделами считаются
# от общего корня docs, поэтому ``qsp_wiki`` <-> ``help_add`` резолвятся штатно.
WIKI_DIR = "qsp_wiki"

# кириллица -> латиница для имён папок (метки категорий — русские).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DUP_HYPHEN = re.compile(r"-+")


def slugify_cyr(label: str) -> str:
    """Транслитерирует метку категории в безопасное имя папки (латиница, строчные)."""
    out = []
    for ch in label.strip().lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isascii() and (ch.isalnum() or ch in " -_"):
            out.append(ch)
        else:
            out.append(" ")
    slug = _DUP_HYPHEN.sub("-", _NON_ALNUM.sub("-", "".join(out))).strip("-")
    return slug[:48] or "section"


@dataclass
class TocNode:
    """Узел содержания: label, опциональный slug (если это ссылка), дети."""

    label: str
    slug: str = ""
    children: list["TocNode"] = field(default_factory=list)


@dataclass
class DocSpec:
    """Один документ и его желаемый путь (папки + имя файла).

    ``position`` — вычисленный порядок внутри родительской папки (1-й по TOC,
    перемешиваясь с подпапками); для индекс-дока категории = 1 (саму категорию
    Docusaurus рендерит по ``_category_.json.link``, а не как соседа).
    """

    slug: str
    file_path: PurePosixPath  # rel docs root с расширением (.mdx)
    position: int = 0


@dataclass
class FolderSpec:
    """Папка категории: путь, метка, позиция в группе брата, слаг индекс-дока.

    ``position`` — порядок среди соседей родителя (доки и подпапки — одна
    нумерация, т.к. Docusaurus сравнивает ``_category_.json.position`` именно
    так).
    """

    rel: PurePosixPath
    label: str
    index_slug: str  # "" если индекс-дока нет (чистый заголовок)
    position: int = 0


@dataclass
class Layout:
    """Итоговая раскладка содержания: документы и папки + карта slug->путь."""

    docs: list[DocSpec]
    folders: list[FolderSpec]
    links: dict[str, str]  # slug -> путь rel docs root без расширения
    extra_slugs: list[str] = field(default_factory=list)  # страницы вне содержания (help_add)

    @property
    def covered_slugs(self) -> set[str]:
        return set(self.links)


# ------------------------------------------------------------------ разбор дерева


def parse_toc(fragment: Tag) -> list[TocNode]:
    """Разбирает корневой(евые) ``<ul>`` фрагмента sidebar в список узлов."""
    nodes: list[TocNode] = []
    for ul in fragment.find_all("ul", recursive=False):
        nodes.extend(_nodes_from_ul(ul))
    return nodes


def _nodes_from_ul(ul: Tag) -> list[TocNode]:
    nodes: list[TocNode] = []
    for li in ul.find_all("li", recursive=False):
        nodes.append(_node_from_li(li))
    return nodes


def _node_from_li(li: Tag) -> TocNode:
    div = next((c for c in li.find_all("div", recursive=False) if "li" in (c.get("class") or [])), li)
    a = div.find("a")
    sub = next((c for c in li.find_all("ul", recursive=False)), None)
    if a is not None:
        label = a.get_text(" ", strip=True) or div.get_text(" ", strip=True)
        slug = _slug_from_href(str(a.get("href", "")))
    else:
        label = div.get_text(" ", strip=True)
        slug = ""
    children = _nodes_from_ul(sub) if sub is not None else []
    return TocNode(label=label, slug=slug, children=children)


def _slug_from_href(href: str) -> str:
    if not href.startswith(DOC_LINK_PREFIX):
        return ""
    rest = href[len(DOC_LINK_PREFIX):]
    slug, _, _anchor = rest.partition("::")
    return slug


# ------------------------------------------------------------------ раскладка


def build_layout(
    nodes: list[TocNode], available: set[str], start_slug: str
) -> Layout:
    """Обходит дерево, раскладывая документы/папки; недоступные слаги вырезает."""
    docs: list[DocSpec] = []
    folders: list[FolderSpec] = []
    links: dict[str, str] = {}

    # старт — первым в разделе (position 1 в нумерации нижележащего прохода);
    # всё дерево содержания вкладывается в WIKI_DIR, оставляя help_add/img в корне.
    ordered = _promote_start(nodes, start_slug)
    _walk(ordered, PurePosixPath(WIKI_DIR), docs, folders, links, available)
    return Layout(docs=docs, folders=folders, links=links)


def _promote_start(nodes: list[TocNode], start_slug: str) -> list[TocNode]:
    start = next((n for n in nodes if n.slug == start_slug), None)
    if start is None:
        return nodes
    return [start, *(n for n in nodes if n is not start)]


def _walk(
    nodes: list[TocNode],
    folder: PurePosixPath,
    docs: list[DocSpec],
    folders: list[FolderSpec],
    links: dict[str, str],
    available: set[str],
) -> None:
    used_names: set[str] = set()
    # Единый счётчик соседей папки: документы и подпапки нумеруются вместе,
    # поэтому порядок в сайдбаре Docusaurus повторяет порядок TOC (позиция
    # сравнивается только внутри одной папки, не глобально).
    pos = 0
    for node in nodes:
        if node.slug and node.slug not in available:
            # страницы нет в модели (исключена/не скачана) — вырезаем ветку целиком
            continue
        has_children = bool(node.children)

        if not node.slug:
            # чистый текстовый заголовок -> папка
            if not has_children:
                continue
            pos += 1
            name = _unique(slugify_cyr(node.label), used_names)
            child_folder = folder / name
            folders.append(FolderSpec(rel=child_folder, label=node.label, index_slug="", position=pos))
            _walk(node.children, child_folder, docs, folders, links, available)
            continue

        # узел — документ
        doc_file = f"{node.slug}.mdx"
        if has_children:
            pos += 1
            name = _unique(node.slug, used_names)
            child_folder = folder / name
            folders.append(FolderSpec(rel=child_folder, label=node.label, index_slug=node.slug, position=pos))
            links[node.slug] = (child_folder / node.slug).as_posix()
            # индекс-док категории — её собственная страница, соседу не отдаёт
            # место: позиция 1 (Docusaurus уберёт его из списка по category.link).
            docs.append(DocSpec(slug=node.slug, file_path=child_folder / doc_file, position=1))
            _walk(node.children, child_folder, docs, folders, links, available)
        else:
            pos += 1
            links[node.slug] = (folder / node.slug).as_posix()
            docs.append(DocSpec(slug=node.slug, file_path=folder / doc_file, position=pos))


def _unique(name: str, used: set[str]) -> str:
    base = name
    i = 2
    while name in used:
        name = f"{base}-{i}"
        i += 1
    used.add(name)
    return name
