"""Рендереры отдельного входа Docusaurus Markdown."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup

from ..config import Settings
from ..docusaurus_markdown.analyzer import render_page_html
from ..docusaurus_markdown.model import MarkdownPage, MarkdownSiteModel, build_markdown_site_model
from ..fs_utils import ensure_dir, save_json, write_text
from ..templates import CHM_PAGE, HHC_PAGE, HHK_PAGE
from .pwa.search import build_search_index
from .pwa.shell import HEAD_LINKS_HTML, RUNTIME_JS, SEARCH_PANEL_HTML, SEARCH_TAB_HTML, SW_JS
from .spa import SPA_PAGE

logger = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _fragment(page: MarkdownPage, target: str) -> BeautifulSoup:
    soup = BeautifulSoup(render_page_html(page.parsed), "lxml")
    body = soup.find("body")
    fragment = BeautifulSoup(str(body) if body is not None else str(soup), "lxml")

    link_by_destination = {link.destination: link for link in page.links}
    for a in fragment.find_all("a", href=True):
        href = str(a["href"])
        link = link_by_destination.get(href)
        if link is None:
            continue
        if link.external:
            a["target"] = "_blank"
        elif link.as_text:
            a.unwrap()
        elif link.target_slug:
            if target == "chm":
                a["href"] = f"{link.target_slug}.htm"
                if link.anchor:
                    a["href"] += f"#{link.anchor}"
            else:
                a["href"] = f"#{link.target_slug}"
                if link.anchor:
                    a["href"] += f"~{link.anchor}"

    image_by_destination = {image.destination: image for image in page.images}
    for image in fragment.find_all("img", src=True):
        src = str(image["src"])
        resolved = image_by_destination.get(src)
        if resolved is not None:
            image["src"] = resolved.asset.name if target == "chm" else f"images/{resolved.asset.name}"
    return fragment


def _namespace_ids(fragment: BeautifulSoup, slug: str) -> None:
    for element in fragment.find_all(id=True):
        element["id"] = f"{slug}~{element['id']}"


def _reset_output(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    return ensure_dir(path)


def render_markdown_chm(settings: Settings, out_dir: Path | None = None) -> Path:
    model = build_markdown_site_model(settings.docusaurus_markdown)
    configured = settings.docusaurus_markdown.chm_out
    out = _reset_output(out_dir or configured or settings.paths.root / ".build" / "docusaurus_markdown" / "chm")

    for page in model.pages:
        soup = BeautifulSoup(CHM_PAGE, "lxml")
        soup.title.string = page.title
        fragment = _fragment(page, "chm")
        body = soup.find("body")
        if body is not None:
            body.append(fragment)
        write_text(out / f"{page.slug}.htm", str(soup), settings.chm.page_encoding)

    _write_markdown_hhc(model, out)
    _write_markdown_hhk(model, out)
    _copy_markdown_assets(model, settings, out)
    _copy_chm_css(settings, out)
    logger.info("Docusaurus Markdown CHM собран: %s (%d страниц)", out, len(model.pages))
    return out


def _write_markdown_hhc(model: MarkdownSiteModel, out: Path) -> None:
    soup = BeautifulSoup(HHC_PAGE, "lxml")
    body = soup.find("body")
    if body is None:
        return
    ul = soup.new_tag("ul")

    def append_nodes(nodes: tuple, parent: object) -> None:
        for node in nodes:
            li = soup.new_tag("li")
            obj = soup.new_tag("object")
            obj["type"] = "text/sitemap"
            name = soup.new_tag("param")
            name["name"] = "Name"
            name["value"] = node.label
            obj.append(name)
            if node.slug:
                local = soup.new_tag("param")
                local["name"] = "Local"
                local["value"] = f"{node.slug}.htm"
                obj.append(local)
            li.append(obj)
            if node.children:
                child_ul = soup.new_tag("ul")
                append_nodes(node.children, child_ul)
                li.append(child_ul)
            parent.append(li)

    append_nodes(model.toc, ul)
    body.append(ul)
    write_text(out / "qsp.hhc", str(soup), "windows-1251")


def _write_markdown_hhk(model: MarkdownSiteModel, out: Path) -> None:
    soup = BeautifulSoup(HHK_PAGE, "lxml")
    body = soup.find("body")
    if body is None:
        return
    ul = soup.new_tag("ul")
    for page in model.pages:
        for heading in page.headings:
            if not heading.anchor:
                continue
            li = soup.new_tag("li")
            obj = soup.new_tag("object")
            obj["type"] = "text/sitemap"
            name = soup.new_tag("param")
            name["name"] = "Name"
            name["value"] = heading.text
            local = soup.new_tag("param")
            local["name"] = "Local"
            local["value"] = f"{page.slug}.htm#{heading.anchor}"
            obj.extend([name, local])
            li.append(obj)
            ul.append(li)
    body.append(ul)
    write_text(out / "qsp.hhk", str(soup), "windows-1251")


def _copy_markdown_assets(model: MarkdownSiteModel, settings: Settings, out: Path) -> None:
    docs = settings.docusaurus_markdown.source_dir.joinpath(
        *settings.docusaurus_markdown.docs_path.parts
    )
    images_dir = out if (out.name == "chm") else ensure_dir(out / "images")
    for asset in model.assets:
        source = docs.joinpath(*asset.parts)
        if source.is_file():
            shutil.copy2(source, images_dir / asset.name)


def _copy_chm_css(settings: Settings, out: Path) -> None:
    if settings.paths.res_chm.is_dir():
        for source in settings.paths.res_chm.iterdir():
            if source.is_file():
                shutil.copy2(source, out / source.name)


def render_markdown_spa(settings: Settings, out_dir: Path | None = None) -> Path:
    model = build_markdown_site_model(settings.docusaurus_markdown)
    configured = settings.docusaurus_markdown.spa_out
    out = _reset_output(out_dir or configured or settings.paths.root / ".build" / "docusaurus_markdown" / "spa")
    soup = BeautifulSoup(SPA_PAGE, "lxml")
    _assemble_markdown_body(soup, model)
    write_text(out / "index.html", str(soup), settings.chm.page_encoding)
    _copy_spa_resources(settings, out)
    _copy_markdown_assets(model, settings, out)
    logger.info("Docusaurus Markdown SPA собран: %s (%d страниц)", out, len(model.pages))
    return out


def _assemble_markdown_body(soup: BeautifulSoup, model: MarkdownSiteModel) -> None:
    toc = soup.find(id="toc")
    main = soup.find(id="content")
    if toc is not None:
        ul = soup.new_tag("ul")

        def append_nodes(nodes: tuple, parent: object) -> None:
            for node in nodes:
                li = soup.new_tag("li")
                label = soup.new_tag("span")
                label.string = node.label
                if node.slug:
                    a = soup.new_tag("a", href=f"#{node.slug}")
                    a.string = node.label
                    li.append(a)
                else:
                    li.append(label)
                if node.children:
                    child_ul = soup.new_tag("ul")
                    append_nodes(node.children, child_ul)
                    li.append(child_ul)
                parent.append(li)

        append_nodes(model.toc, ul)
        toc.append(ul)

    if main is not None:
        for page in model.pages:
            fragment = _fragment(page, "spa")
            _namespace_ids(fragment, page.slug)
            section = soup.new_tag("section")
            section["id"] = page.slug
            section["data-slug"] = page.slug
            section["hidden"] = ""
            section.append(fragment)
            main.append(section)


def _copy_spa_resources(settings: Settings, out: Path) -> None:
    if settings.paths.res_spa.is_dir():
        for source in settings.paths.res_spa.iterdir():
            if source.is_file():
                shutil.copy2(source, out / source.name)


def render_markdown_pwa(settings: Settings, out_dir: Path | None = None) -> Path:
    model = build_markdown_site_model(settings.docusaurus_markdown)
    configured = settings.docusaurus_markdown.pwa_out
    out = _reset_output(out_dir or configured or settings.paths.root / ".build" / "docusaurus_markdown" / "pwa")
    soup = BeautifulSoup(SPA_PAGE, "lxml")
    _assemble_markdown_body(soup, model)
    _add_markdown_pwa_shell(soup)
    write_text(out / "index.html", str(soup), settings.chm.page_encoding)
    _copy_spa_resources(settings, out)
    _copy_markdown_assets(model, settings, out)
    _write_markdown_search(model, out)
    _write_markdown_manifest(out)
    _write_markdown_sw(out)
    logger.info("Docusaurus Markdown PWA собран: %s (%d страниц)", out, len(model.pages))
    return out


def _add_markdown_pwa_shell(soup: BeautifulSoup) -> None:
    head = soup.find("head")
    if head is not None:
        head.append(BeautifulSoup(HEAD_LINKS_HTML.format(theme_color="#2f6db0", icon=""), "lxml"))
    sidebar_head = soup.find(class_="spa-sidebar-head")
    sidebar_body = soup.find(class_="spa-sidebar-body")
    if sidebar_head is not None:
        tab = BeautifulSoup(SEARCH_TAB_HTML, "lxml").find("button")
        if tab is not None:
            sidebar_head.insert(2, tab)
    if sidebar_body is not None:
        panel = BeautifulSoup(SEARCH_PANEL_HTML, "lxml").find("nav")
        if panel is not None:
            sidebar_body.append(panel)
    body = soup.find("body")
    if body is not None:
        body.append(BeautifulSoup(RUNTIME_JS, "lxml"))


def _write_markdown_search(model: MarkdownSiteModel, out: Path) -> None:
    docs: list[dict[str, str]] = []
    postings: dict[str, dict[str, int]] = {}
    for page in model.pages:
        index = len(docs)
        docs.append({"slug": page.slug, "title": page.title})
        words = [token for token in _TOKEN_RE.findall(page.title.lower()) if len(token) >= 3] * 4
        words += [token for token in _TOKEN_RE.findall(model.search_entries[index].text.lower()) if len(token) >= 3]
        for word in words:
            bucket = postings.setdefault(word, {})
            bucket[str(index)] = bucket.get(str(index), 0) + 1
    save_json({"version": 1, "docs": docs, "postings": postings}, out / "search.json")


def _write_markdown_manifest(out: Path) -> None:
    manifest = {
        "name": "QSP — справка",
        "short_name": "QSP",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "theme_color": "#2f6db0",
        "background_color": "#f4f5f7",
        "icons": [],
    }
    save_json(manifest, out / "manifest.webmanifest")


def _precache_paths(out: Path) -> list[str]:
    paths = ["./"]
    for file in sorted(out.rglob("*")):
        if file.is_file() and file.name != "sw.js":
            paths.append(PurePosixPath(file.relative_to(out)).as_posix())
    return paths


def _write_markdown_sw(out: Path) -> None:
    paths = _precache_paths(out)
    digest = hashlib.sha256()
    for rel in paths:
        if rel != "./":
            digest.update(rel.encode("utf-8"))
            digest.update((out / rel).read_bytes())
    text = SW_JS.replace("__CACHE_NAME__", digest.hexdigest()[:12])
    text = text.replace("__PRECACHE__", json.dumps(paths, ensure_ascii=False))
    write_text(out / "sw.js", text, "utf-8")
