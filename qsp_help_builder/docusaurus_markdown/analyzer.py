"""Strict parsing and validation of the selected Docusaurus Markdown corpus."""

from __future__ import annotations

import json
import logging
import posixpath
import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin

from ..config import DocusaurusMarkdownSettings
from .errors import DocusaurusMarkdownError
from .manifest import SelectedPage, load_page_selection

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_HEADING_ANCHOR_RE = re.compile(r"\s+\{#([^{}\s]+)\}\s*\Z")
_VALID_ANCHOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_ALLOWED_CODE_LANGUAGES = frozenset({"qsp", "text", "html", "js"})
_DOCLINK_RE = re.compile(r"DOCLINK::index::([A-Za-z0-9][A-Za-z0-9_-]*)\Z")
_MDX_IMPORT_RE = re.compile(r"(?m)^\s*(?:import|export)\s+(?:[\w*{]|[\"'])")
_STRIKETHROUGH_RE = re.compile(r"(?<!\\)~~(?=\S).*?\S~~")


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            is_duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "mapping key is not hashable",
                key_node.start_mark,
            ) from exc
        if is_duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int | None
    message: str

    def __str__(self) -> str:
        location = f"{self.file}:{self.line}" if self.line is not None else self.file
        return f"{location}: {self.message}"


@dataclass(frozen=True)
class Heading:
    anchor: str
    text: str
    level: int
    line: int


@dataclass(frozen=True)
class LinkReference:
    destination: str
    line: int
    as_text: bool = False


@dataclass(frozen=True)
class ImageReference:
    destination: str
    line: int


@dataclass(frozen=True)
class ParsedPage:
    selected: SelectedPage
    title: str
    sidebar_position: int
    headings: tuple[Heading, ...]
    links: tuple[LinkReference, ...]
    images: tuple[ImageReference, ...]
    tokens: tuple[Token, ...]

    @property
    def anchors(self) -> frozenset[str]:
        return frozenset(heading.anchor for heading in self.headings if heading.anchor)


@dataclass(frozen=True)
class ValidationReport:
    pages: tuple[ParsedPage, ...]
    diagnostics: tuple[Diagnostic, ...]
    assets: frozenset[PurePosixPath]
    link_count: int
    unlinked_link_count: int


def _markdown_parser() -> MarkdownIt:
    logging.getLogger("markdown_it").setLevel(logging.WARNING)
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    parser.use(footnote_plugin)
    return parser


def _token_line(token: Token, line_offset: int) -> int:
    return (token.map[0] + 1 + line_offset) if token.map else (1 + line_offset)


def _plain_inline_text(children: list[Token] | None) -> str:
    if not children:
        return ""
    text: list[str] = []
    for token in children:
        if token.type in {"text", "code_inline"}:
            text.append(token.content)
        elif token.type == "image":
            text.append(token.attrGet("alt") or "")
        elif token.type in {"softbreak", "hardbreak"}:
            text.append(" ")
    return "".join(text).strip()


def _frontmatter(
    text: str, file: str
) -> tuple[dict[str, Any], str, int, list[Diagnostic]]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return (
            {},
            text,
            0,
            [Diagnostic(file, 1, "ожидается YAML front matter с title и sidebar_position")],
        )

    line_offset = text[: match.end()].count("\n")
    diagnostics: list[Diagnostic] = []
    try:
        metadata = yaml.load(match.group(1), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 2 if mark else 2
        diagnostics.append(Diagnostic(file, line, f"ошибка YAML front matter: {exc}"))
        metadata = {}

    if not isinstance(metadata, dict):
        diagnostics.append(Diagnostic(file, 2, "front matter должен быть YAML-объектом"))
        metadata = {}

    unknown = set(metadata) - {"title", "sidebar_position"}
    if unknown:
        diagnostics.append(
            Diagnostic(
                file,
                2,
                f"неподдерживаемые ключи front matter: {', '.join(sorted(map(str, unknown)))}",
            )
        )
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        diagnostics.append(Diagnostic(file, 2, "front matter должен содержать непустой title"))
        title = ""
    position = metadata.get("sidebar_position")
    if type(position) is not int:
        diagnostics.append(Diagnostic(file, 2, "sidebar_position должен быть целым числом"))
        position = 0

    return metadata, text[match.end() :], line_offset, diagnostics


def _remove_heading_suffix(inline: Token, anchor_match: re.Match[str]) -> None:
    inline.content = inline.content[: anchor_match.start()].rstrip()
    if inline.children:
        for token in reversed(inline.children):
            if token.type == "text":
                token.content = _HEADING_ANCHOR_RE.sub("", token.content).rstrip()
                break


def _parse_page(
    parser: MarkdownIt, selected: SelectedPage, source_file: Path
) -> tuple[ParsedPage, list[Diagnostic]]:
    file = selected.source.as_posix()
    diagnostics: list[Diagnostic] = []
    try:
        text = source_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return (
            ParsedPage(selected, "", 0, (), (), (), ()),
            [Diagnostic(file, None, f"не удалось прочитать Markdown: {exc}")],
        )

    metadata, body, line_offset, frontmatter_diagnostics = _frontmatter(text, file)
    diagnostics.extend(frontmatter_diagnostics)
    try:
        tokens = parser.parse(body)
    except ValueError as exc:
        return (
            ParsedPage(selected, str(metadata.get("title", "")), 0, (), (), (), ()),
            diagnostics + [Diagnostic(file, line_offset + 1, f"ошибка разбора Markdown: {exc}")],
        )

    headings: list[Heading] = []
    links: list[LinkReference] = []
    images: list[ImageReference] = []
    anchor_locations: dict[str, int] = {}

    for index, token in enumerate(tokens):
        line = _token_line(token, line_offset)
        if token.type in {"html_block", "html_inline"}:
            diagnostics.append(Diagnostic(file, line, "сырой HTML вне fenced code не поддерживается"))
        elif token.type == "code_block":
            diagnostics.append(
                Diagnostic(file, line, "используйте fenced code block с поддерживаемым языком")
            )
        elif token.type == "fence":
            info = token.info.strip().split()
            language = info[0].lower() if info else ""
            if len(info) != 1 or language not in _ALLOWED_CODE_LANGUAGES:
                supported = ", ".join(sorted(_ALLOWED_CODE_LANGUAGES))
                diagnostics.append(
                    Diagnostic(file, line, f"неподдерживаемый fenced code language; допустимы: {supported}")
                )
        elif token.type == "heading_open":
            level = int(token.tag[1:])
            if token.markup != "#" * level:
                diagnostics.append(
                    Diagnostic(file, line, "поддерживаются только ATX-заголовки с явным anchor")
                )
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            if inline is None or inline.type != "inline":
                diagnostics.append(Diagnostic(file, line, "не удалось разобрать содержимое заголовка"))
                continue
            anchor_match = _HEADING_ANCHOR_RE.search(inline.content)
            if anchor_match is None:
                diagnostics.append(Diagnostic(file, line, "заголовку требуется явный suffix {#anchor}"))
                anchor = ""
            else:
                anchor = anchor_match.group(1)
                _remove_heading_suffix(inline, anchor_match)
                if not _VALID_ANCHOR_RE.fullmatch(anchor):
                    diagnostics.append(Diagnostic(file, line, f"неподдерживаемый ID якоря: {anchor!r}"))
                if anchor in anchor_locations:
                    diagnostics.append(
                        Diagnostic(
                            file,
                            line,
                            f"повторный anchor {anchor!r}; впервые объявлен в строке {anchor_locations[anchor]}",
                        )
                    )
                else:
                    anchor_locations[anchor] = line
            if level > 4:
                diagnostics.append(Diagnostic(file, line, f"заголовок H{level} не входит в поддерживаемый поднабор"))
            headings.append(
                Heading(anchor, _plain_inline_text(inline.children), level, line)
            )

        if token.type != "inline":
            continue
        if re.search(r"(?m)^\s*:::", token.content):
            diagnostics.append(Diagnostic(file, line, "Docusaurus admonitions ::: не поддерживаются"))
        if _MDX_IMPORT_RE.search(token.content):
            diagnostics.append(Diagnostic(file, line, "MDX import/export не поддерживается"))
        if any(
            child.type == "text" and _STRIKETHROUGH_RE.search(child.content)
            for child in token.children or []
        ):
            diagnostics.append(Diagnostic(file, line, "Markdown strikethrough не поддерживается"))
        for child in token.children or []:
            if child.type == "html_inline":
                diagnostics.append(Diagnostic(file, line, "сырой HTML вне fenced code не поддерживается"))
            elif child.type == "link_open":
                destination = child.attrGet("href")
                if destination is None:
                    diagnostics.append(Diagnostic(file, line, "ссылка без href"))
                elif child.attrGet("class") != "footnote-backref":
                    links.append(LinkReference(destination, line))
            elif child.type == "image":
                destination = child.attrGet("src")
                if destination is None:
                    diagnostics.append(Diagnostic(file, line, "изображение без src"))
                else:
                    images.append(ImageReference(destination, line))

    parsed = ParsedPage(
        selected=selected,
        title=str(metadata.get("title", "")),
        sidebar_position=metadata.get("sidebar_position", 0)
        if type(metadata.get("sidebar_position", 0)) is int
        else 0,
        headings=tuple(headings),
        links=tuple(links),
        images=tuple(images),
        tokens=tuple(tokens),
    )
    return parsed, diagnostics


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _validate_toc(path: Path, slugs: set[str]) -> list[Diagnostic]:
    file = str(path)
    try:
        with path.open("r", encoding="utf-8") as stream:
            raw: Any = json.load(stream, object_pairs_hook=_strict_json_object)
    except json.JSONDecodeError as exc:
        return [Diagnostic(file, exc.lineno, f"некорректный JSON: {exc.msg}")]
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [Diagnostic(file, None, f"не удалось прочитать TOC: {exc}")]

    diagnostics: list[Diagnostic] = []
    if not isinstance(raw, list) or not raw:
        return [Diagnostic(file, None, "корнем TOC должен быть непустой массив узлов")]

    seen: dict[str, str] = {}

    def visit(nodes: Any, parent: str) -> None:
        if not isinstance(nodes, list):
            diagnostics.append(Diagnostic(file, None, f"{parent}: children должен быть массивом"))
            return
        for index, node in enumerate(nodes):
            location = f"{parent}[{index}]"
            if not isinstance(node, dict):
                diagnostics.append(Diagnostic(file, None, f"{location}: ожидается объект"))
                continue
            unknown = set(node) - {"label", "slug", "children"}
            if unknown:
                diagnostics.append(
                    Diagnostic(file, None, f"{location}: неизвестные поля {', '.join(sorted(unknown))}")
                )
            label = node.get("label")
            if not isinstance(label, str) or not label.strip():
                diagnostics.append(Diagnostic(file, None, f"{location}: требуется непустой label"))
            slug = node.get("slug")
            children = node.get("children")
            has_slug = "slug" in node
            has_children = "children" in node
            if not has_slug and not has_children:
                diagnostics.append(Diagnostic(file, None, f"{location}: требуется slug или children"))
            if has_slug:
                if not isinstance(slug, str) or not slug:
                    diagnostics.append(Diagnostic(file, None, f"{location}.slug должен быть строкой"))
                elif slug not in slugs:
                    diagnostics.append(Diagnostic(file, None, f"{location}: неизвестный slug {slug!r}"))
                elif slug in seen:
                    diagnostics.append(
                        Diagnostic(file, None, f"{location}: slug {slug!r} уже указан в {seen[slug]}")
                    )
                else:
                    seen[slug] = location
            if has_children:
                if not isinstance(children, list) or not children:
                    diagnostics.append(Diagnostic(file, None, f"{location}.children должен быть непустым массивом"))
                else:
                    visit(children, f"{location}.children")

    visit(raw, "toc")
    for slug in sorted(slugs - seen.keys()):
        diagnostics.append(Diagnostic(file, None, f"страница {slug!r} отсутствует в TOC"))
    return diagnostics


def _safe_doc_path(
    docs_root: Path,
    source: PurePosixPath,
    destination: str,
) -> PurePosixPath | None:
    if not destination or "\\" in destination or destination.startswith("/"):
        return None
    try:
        decoded = unquote(destination)
        normalized = posixpath.normpath(posixpath.join(source.parent.as_posix(), decoded))
    except (UnicodeDecodeError, ValueError):
        return None
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        return None
    relative = PurePosixPath(normalized)
    path = docs_root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(docs_root):
        return None
    path = docs_root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            return None
    return relative


def _validate_link(
    page: ParsedPage,
    link: LinkReference,
    docs_root: Path,
    pages_by_source: dict[PurePosixPath, ParsedPage],
    selected_sources: set[PurePosixPath],
    unlinked_excluded: frozenset[PurePosixPath],
) -> tuple[bool, list[Diagnostic]]:
    file = page.selected.source.as_posix()
    destination = link.destination
    diagnostics: list[Diagnostic] = []
    if not destination:
        return False, [Diagnostic(file, link.line, "ссылка не может быть пустой")]
    doclink_match = _DOCLINK_RE.fullmatch(destination)
    if destination.startswith("DOCLINK::"):
        if doclink_match is None:
            return False, [Diagnostic(file, link.line, f"неподдерживаемый DOCLINK: {destination!r}")]
        anchor = doclink_match.group(1)
        if anchor not in page.anchors:
            diagnostics.append(Diagnostic(file, link.line, f"DOCLINK anchor {anchor!r} не найден"))
        return False, diagnostics

    try:
        parsed_url = urlsplit(destination)
    except ValueError as exc:
        return False, [Diagnostic(file, link.line, f"некорректная ссылка {destination!r}: {exc}")]
    if parsed_url.scheme:
        if parsed_url.scheme.lower() in {"http", "https"} and parsed_url.netloc:
            return False, []
        return False, [Diagnostic(file, link.line, f"неподдерживаемая схема ссылки: {destination!r}")]
    if parsed_url.netloc or parsed_url.query:
        return False, [Diagnostic(file, link.line, f"неподдерживаемый URL: {destination!r}")]

    if parsed_url.path:
        target = _safe_doc_path(
            docs_root,
            page.selected.source,
            parsed_url.path,
        )
        if target is None:
            return False, [
                Diagnostic(file, link.line, f"некорректный или небезопасный путь ссылки: {destination!r}")
            ]
        if target.suffix.lower() != ".md":
            return False, [
                Diagnostic(file, link.line, f"ссылка должна указывать на .md-документ: {destination!r}")
            ]
        target_file = docs_root.joinpath(*target.parts)
        if not target_file.is_file():
            return False, [Diagnostic(file, link.line, f"целевая страница не найдена: {target}")]
        if target not in selected_sources:
            if target in unlinked_excluded:
                return True, []
            return False, [
                Diagnostic(file, link.line, f"целевая страница не выбрана или исключена: {target}")
            ]
    else:
        target = page.selected.source

    fragment = unquote(parsed_url.fragment)
    if fragment:
        target_page = pages_by_source.get(target)
        if target_page is not None and fragment not in target_page.anchors:
            diagnostics.append(
                Diagnostic(file, link.line, f"anchor {fragment!r} не найден в {target}")
            )
    return False, diagnostics


def _unwrap_link(tokens: tuple[Token, ...], destination: str) -> None:
    for inline in tokens:
        if inline.type != "inline" or not inline.children:
            continue
        children = inline.children
        for start, child in enumerate(children):
            if child.type != "link_open" or child.attrGet("href") != destination:
                continue
            end = next(
                (index for index in range(start + 1, len(children)) if children[index].type == "link_close"),
                None,
            )
            if end is None:
                raise DocusaurusMarkdownError(
                    f"Внутренняя ошибка Markdown AST: отсутствует link_close для {destination!r}"
                )
            inline.children = children[:start] + children[start + 1 : end] + children[end + 1 :]
            return
    raise DocusaurusMarkdownError(
        f"Внутренняя ошибка Markdown AST: не найдена ссылка {destination!r}"
    )


def _validate_image(
    page: ParsedPage, image: ImageReference, docs_root: Path
) -> tuple[PurePosixPath | None, Diagnostic | None]:
    file = page.selected.source.as_posix()
    destination = image.destination
    try:
        parsed_url = urlsplit(destination)
    except ValueError as exc:
        return None, Diagnostic(file, image.line, f"некорректный image URL {destination!r}: {exc}")
    if parsed_url.scheme or parsed_url.netloc or parsed_url.query or parsed_url.fragment:
        return None, Diagnostic(file, image.line, f"поддерживаются только локальные изображения: {destination!r}")
    target = _safe_doc_path(
        docs_root,
        page.selected.source,
        parsed_url.path,
    )
    if target is None:
        return None, Diagnostic(file, image.line, f"некорректный или небезопасный путь изображения: {destination!r}")
    path = docs_root.joinpath(*target.parts)
    if not path.is_file():
        return None, Diagnostic(file, image.line, f"файл изображения не найден: {target}")
    return target, None


def validate_source(settings: DocusaurusMarkdownSettings) -> ValidationReport:
    """Checks all selected Markdown pages, links, anchors, images, and the TOC."""
    docs_root = settings.source_dir.joinpath(*settings.docs_path.parts).resolve()
    selection = load_page_selection(settings.pages_manifest, docs_root)
    selected_pages = selection.pages
    selected_sources = {page.source for page in selected_pages}
    diagnostics = _validate_toc(settings.toc_manifest, {page.slug for page in selected_pages})
    parser = _markdown_parser()
    parsed_pages: list[ParsedPage] = []
    parsed_by_source: dict[PurePosixPath, ParsedPage] = {}
    for selected in selected_pages:
        parsed, page_diagnostics = _parse_page(
            parser,
            selected,
            docs_root.joinpath(*selected.source.parts),
        )
        parsed_pages.append(parsed)
        parsed_by_source[selected.source] = parsed
        diagnostics.extend(page_diagnostics)

    assets: set[PurePosixPath] = set()
    link_count = 0
    validated_pages: list[ParsedPage] = []
    for page in parsed_pages:
        validated_links: list[LinkReference] = []
        for link in page.links:
            link_count += 1
            as_text, link_diagnostics = _validate_link(
                page,
                link,
                docs_root,
                parsed_by_source,
                selected_sources,
                selection.unlinked_excluded,
            )
            diagnostics.extend(link_diagnostics)
            if as_text:
                _unwrap_link(page.tokens, link.destination)
            validated_links.append(replace(link, as_text=as_text))
        for image in page.images:
            asset, diagnostic = _validate_image(page, image, docs_root)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
            elif asset is not None:
                assets.add(asset)
        validated_pages.append(replace(page, links=tuple(validated_links)))

    diagnostics.sort(key=lambda item: (item.file, item.line or 0, item.message))
    return ValidationReport(
        pages=tuple(validated_pages),
        diagnostics=tuple(diagnostics),
        assets=frozenset(assets),
        link_count=link_count,
        unlinked_link_count=sum(
            link.as_text for page in validated_pages for link in page.links
        ),
    )


def format_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> str:
    return "\n".join(map(str, diagnostics))


def render_page_html(page: ParsedPage) -> str:
    """Сериализует валидированный ParsedPage в содержательный HTML-фрагмент."""
    parser = _markdown_parser()
    html = parser.renderer.render(list(page.tokens), parser.options, {})
    soup = BeautifulSoup(html, "lxml")
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4"])
    for heading_tag, parsed_heading in zip(heading_tags, page.headings):
        if parsed_heading.anchor:
            heading_tag["id"] = parsed_heading.anchor
    body = soup.find("body")
    return str(body) if body is not None else str(soup)


class MarkdownValidationError(DocusaurusMarkdownError):
    """Aggregated diagnostics from a Markdown validation run."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__(format_diagnostics(diagnostics))
