"""Общая нейтральная модель валидированного Docusaurus Markdown-входа."""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from ..config import DocusaurusMarkdownSettings
from .analyzer import (
    Heading,
    ImageReference,
    LinkReference,
    MarkdownValidationError,
    ParsedPage,
    ValidationReport,
    validate_source,
)
from .errors import DocusaurusMarkdownError


@dataclass(frozen=True)
class TocNode:
    """Узел явного оглавления Markdown-входа."""

    label: str
    slug: str | None = None
    children: tuple["TocNode", ...] = ()


MarkdownTocNode = TocNode


@dataclass(frozen=True)
class ResolvedLink:
    """Разрешённая ссылка с явной целевой страницей и якорем."""

    destination: str
    line: int
    target_slug: str | None
    anchor: str | None
    external: bool
    as_text: bool = False


@dataclass(frozen=True)
class ResolvedImage:
    """Локальный ассет с нормализованным POSIX-путём внутри docs."""

    destination: str
    line: int
    asset: PurePosixPath


@dataclass(frozen=True)
class SearchEntry:
    """Минимальная поисковая запись для последующих PWA/SPA-индексов."""

    slug: str
    title: str
    text: str
    anchors: tuple[str, ...]


@dataclass(frozen=True)
class MarkdownPage:
    """Одна выбранная Markdown-страница в нейтральной модели сайта."""

    source: PurePosixPath
    slug: str
    title: str
    sidebar_position: int
    headings: tuple[Heading, ...]
    links: tuple[ResolvedLink, ...]
    images: tuple[ResolvedImage, ...]
    parsed: ParsedPage

    @property
    def anchors(self) -> frozenset[str]:
        return frozenset(heading.anchor for heading in self.headings if heading.anchor)


DocusaurusMarkdownPage = MarkdownPage


@dataclass(frozen=True)
class MarkdownSiteModel:
    """Нейтральная модель страниц и оглавления без записи файлов."""

    pages: tuple[MarkdownPage, ...]
    toc: tuple[TocNode, ...]
    assets: frozenset[PurePosixPath]
    search_entries: tuple[SearchEntry, ...]
    by_slug: dict[str, MarkdownPage]

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_slug", {page.slug: page for page in self.pages})


DocusaurusMarkdownModel = MarkdownSiteModel
MarkdownModel = MarkdownSiteModel
MarkdownSearchEntry = SearchEntry
MarkdownResolvedLink = ResolvedLink
MarkdownResolvedImage = ResolvedImage

_DOCLINK_RE = re.compile(r"DOCLINK::index::([A-Za-z0-9][A-Za-z0-9_-]*)\Z")


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DocusaurusMarkdownError(f"Повторный ключ TOC в JSON: {key!r}")
        result[key] = value
    return result


def load_toc(path: Path, slugs: set[str]) -> tuple[TocNode, ...]:
    """Читает явное оглавление в типизированное дерево."""

    try:
        with path.open("r", encoding="utf-8") as stream:
            raw = json.load(stream, object_pairs_hook=_strict_json_object)
    except json.JSONDecodeError as exc:
        raise DocusaurusMarkdownError(
            f"{path}:{exc.lineno}: некорректный JSON TOC: {exc.msg}"
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise DocusaurusMarkdownError(f"Не удалось прочитать TOC {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise DocusaurusMarkdownError(f"{path}: корнем TOC должен быть массив")

    def visit(nodes: object) -> tuple[TocNode, ...]:
        if not isinstance(nodes, list):
            raise DocusaurusMarkdownError(f"{path}: children TOC должен быть массивом")
        result: list[TocNode] = []
        for node in nodes:
            if not isinstance(node, dict):
                raise DocusaurusMarkdownError(f"{path}: узел TOC должен быть объектом")
            label = node.get("label")
            slug = node.get("slug")
            if not isinstance(label, str):
                raise DocusaurusMarkdownError(f"{path}: label TOC должен быть строкой")
            if slug is not None:
                if not isinstance(slug, str) or slug not in slugs:
                    raise DocusaurusMarkdownError(f"{path}: неизвестный slug TOC {slug!r}")
            children = visit(node["children"]) if "children" in node else ()
            result.append(TocNode(label=label, slug=slug if isinstance(slug, str) else None, children=children))
        return tuple(result)

    return visit(raw)


def _source_target(
    page: ParsedPage,
    destination: str,
    docs_root: Path,
    by_source: dict[PurePosixPath, ParsedPage],
) -> tuple[PurePosixPath | None, str | None]:
    """Возвращает (source страницы, fragment) для локальной Markdown-ссылки."""

    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return None, None
    source = page.selected.source
    if parsed.path:
        normalized = posixpath.normpath(
            posixpath.join(source.parent.as_posix(), unquote(parsed.path))
        )
        target = PurePosixPath(normalized)
    else:
        target = source
    fragment = unquote(parsed.fragment) if parsed.fragment else None
    if target not in by_source:
        return None, fragment
    return target, fragment


def _text_for_search(page: ParsedPage) -> str:
    texts: list[str] = [page.title]
    for heading in page.headings:
        if heading.text:
            texts.append(heading.text)
    return " ".join(texts)


def build_markdown_site_model(
    settings: DocusaurusMarkdownSettings,
    report: ValidationReport | None = None,
) -> MarkdownSiteModel:
    """Строит общую модель только после успешной строгой валидации."""

    validation = report if report is not None else validate_source(settings)
    if validation.diagnostics:
        raise MarkdownValidationError(validation.diagnostics)

    by_source = {page.selected.source: page for page in validation.pages}
    docs_root = settings.source_dir.joinpath(*settings.docs_path.parts).resolve()
    pages: list[MarkdownPage] = []

    for parsed in validation.pages:
        links: list[ResolvedLink] = []
        for link in parsed.links:
            if link.as_text:
                links.append(
                    ResolvedLink(
                        destination=link.destination,
                        line=link.line,
                        target_slug=None,
                        anchor=None,
                        external=False,
                        as_text=True,
                    )
                )
                continue
            doclink_match = _DOCLINK_RE.fullmatch(link.destination)
            if doclink_match is not None:
                links.append(
                    ResolvedLink(
                        destination=link.destination,
                        line=link.line,
                        target_slug=parsed.selected.slug,
                        anchor=doclink_match.group(1),
                        external=False,
                    )
                )
                continue

            parsed_url = urlsplit(link.destination)
            if parsed_url.scheme.lower() in {"http", "https"}:
                links.append(
                    ResolvedLink(
                        destination=link.destination,
                        line=link.line,
                        target_slug=None,
                        anchor=None,
                        external=True,
                    )
                )
                continue

            target_source, fragment = _source_target(parsed, link.destination, docs_root, by_source)
            target = by_source[target_source] if target_source is not None else None
            links.append(
                ResolvedLink(
                    destination=link.destination,
                    line=link.line,
                    target_slug=target.selected.slug if target is not None else None,
                    anchor=fragment,
                    external=False,
                )
            )

        images: list[ResolvedImage] = []
        for image in parsed.images:
            parsed_url = urlsplit(image.destination)
            normalized = posixpath.normpath(
                posixpath.join(parsed.selected.source.parent.as_posix(), unquote(parsed_url.path))
            )
            asset = PurePosixPath(normalized)
            images.append(
                ResolvedImage(
                    destination=image.destination,
                    line=image.line,
                    asset=asset,
                )
            )

        pages.append(
            MarkdownPage(
                source=parsed.selected.source,
                slug=parsed.selected.slug,
                title=parsed.title,
                sidebar_position=parsed.sidebar_position,
                headings=parsed.headings,
                links=tuple(links),
                images=tuple(images),
                parsed=parsed,
            )
        )

    toc = load_toc(settings.toc_manifest, {page.slug for page in pages})
    search_entries = tuple(
        SearchEntry(
            slug=page.slug,
            title=page.title,
            text=_text_for_search(page.parsed),
            anchors=tuple(
                heading.anchor for heading in page.headings if heading.anchor
            ),
        )
        for page in pages
    )
    return MarkdownSiteModel(
        pages=tuple(pages),
        toc=toc,
        assets=validation.assets,
        search_entries=search_entries,
        by_slug={page.slug: page for page in pages},
    )


build_docusaurus_markdown_model = build_markdown_site_model
build_markdown_model = build_markdown_site_model
