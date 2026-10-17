# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownArgumentType=false, reportIndexIssue=false, reportArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""Конвертер HTML-фрагмента страницы в MDX-тело документа (Docusaurus).

Написан вручную (решение пользователя — без новой зависимости): обходит дерево
``fragment`` модели и печатает Markdown, понятный Docusaurus (`.mdx`). Отличие от
CHM/SPA — цели ссылок/картинок приходят от ``DocusaurusProfile`` токенами
(``DOCLINK::<slug>::<anchor>`` / ``IMGLINK::<имя>``); здесь они разворачиваются в
относительные пути ОТ КОНКРЕТНОГО файла (``ConvertContext.src_dir``), т.к. только
рендерер знает, в какую папку лёг документ.

Экранирование под MDX: в текстовых узлах ``{ } <`` уходят в сущности (``&#123;``,
``&#125;``, ``&lt;``), иначе MDX-парсер примет их за JSX. Содержимое ``<pre>``/
``<code>`` (в fenced-блоке) — литеральное, не экранируется.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from bs4 import Tag
from bs4.element import Comment, NavigableString

from ...fs_utils import file_name
from ...render.profile import DOC_LINK_PREFIX, IMG_LINK_PREFIX

# теги-содержимое, которые div/section трактует как блочных детей
_BLOCKISH = {
    "p", "ul", "ol", "pre", "div", "table", "blockquote", "dl",
    "section", "article", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
}
_LANG_RE = re.compile(r"brush:\s*([A-Za-z0-9+#]+)")
_MULTI_BLANK = re.compile(r"\n{3,}")


@dataclass
class ConvertContext:
    """Данные для разворота токенов в относительные пути конкретного файла."""

    src_dir: PurePosixPath          # папка файла относительно корня docs ('.' = корень)
    links: dict[str, str]           # slug -> путь rel docs root без расширения
    img_dir: PurePosixPath          # центральная папка картинок ('img')
    missing: set[str] = field(default_factory=set)  # сюда пишем неразрешённые слаги


# ------------------------------------------------------------------ текст/экран


def _esc_text(text: str) -> str:
    return text.replace("{", "&#123;").replace("}", "&#125;").replace("<", "&lt;")


def _esc_link_text(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


def _class_str(tag: Tag) -> str:
    cls = tag.get("class")
    if isinstance(cls, list):
        return " ".join(cls)
    return str(cls or "")


def _relhref(src_dir: PurePosixPath, target: PurePosixPath) -> str:
    """Относительный posix-путь от папки файла к цели (обе — rel docs root)."""
    sp: list[str] = [] if str(src_dir) in (".", "") else list(src_dir.parts)
    tp = list(target.parts)
    i = 0
    while i < len(sp) and i < len(tp) and sp[i] == tp[i]:
        i += 1
    parts = [".."] * (len(sp) - i) + tp[i:]
    return "/".join(parts) if parts else "."


# ------------------------------------------------------------------ публичный API


def render_body(fragment: Tag, ctx: ConvertContext) -> str:
    """Возвращает MDX-тело страницы (без front-matter) с одной завершающей \\n."""
    blocks: list[str] = []
    for child in fragment.children:
        rendered = render_block(child, ctx)
        if rendered.strip():
            blocks.append(rendered)
    body = _MULTI_BLANK.sub("\n\n", "\n\n".join(blocks)).strip()
    return f"{body}\n" if body else ""


def render_block(node: object, ctx: ConvertContext) -> str:
    """Блочный рендер одного узла (текст/заголовок/список/контейнер/…)."""
    if isinstance(node, NavigableString):
        if isinstance(node, Comment):
            return ""
        text = str(node).strip()
        return _esc_text(text) if text else ""
    if not isinstance(node, Tag):
        return ""

    name = node.name
    if name in ("script", "style"):
        return ""
    if re.fullmatch(r"h[1-6]", name or ""):
        level = int(name[1])
        anchor = node.get("id")
        text = render_inline(node, ctx).strip()
        suffix = f" {{#{anchor}}}" if anchor else ""
        return f'{"#" * level} {text}{suffix}'
    if name == "p":
        return render_inline(node, ctx).strip()
    if name == "hr":
        return "---"
    if name == "br":
        return ""
    if name in ("ul", "ol"):
        return _render_list(node, 0, name == "ol", ctx)
    if name == "pre":
        return _render_pre(node)
    if name == "blockquote":
        inner = _render_container(node, ctx)
        return _prefix_lines(inner, "> ")
    if name == "dl":
        parts = [render_inline(c, ctx).strip() for c in node.find_all(["dt", "dd"], recursive=False)]
        return "\n\n".join(p for p in parts if p)
    if name in ("div", "section", "article"):
        return _render_container(node, ctx)
    if name == "table":
        return _render_table(node, ctx)
    return render_inline(node, ctx).strip()


def render_inline(node: object, ctx: ConvertContext) -> str:
    """Инлайн-рендер: текст, форматирование, ссылки, картинки; блоки — сквозь."""
    if isinstance(node, NavigableString):
        if isinstance(node, Comment):
            return ""
        return _esc_text(str(node))
    if not isinstance(node, Tag):
        return ""

    name = node.name
    if name in ("script", "style"):
        return ""
    if name == "br":
        return "\\\n"
    if name == "hr":
        return "\n\n---\n\n"
    if name == "img":
        return _render_img(node, ctx)
    if name == "a":
        return _render_a(node, ctx)
    if name == "code":
        text = node.get_text().strip().replace("\n", " ")
        return text if "`" in text else f"`{text}`"
    if name in ("strong", "b"):
        inner = _render_children(node, ctx).strip()
        return f"**{inner}**" if inner else ""
    if name in ("em", "i"):
        inner = _render_children(node, ctx).strip()
        return f"*{inner}*" if inner else ""
    if name in ("del", "s", "strike"):
        inner = _render_children(node, ctx).strip()
        return f"~~{inner}~~" if inner else ""
    if name in ("ul", "ol"):
        return _render_list(node, 0, name == "ol", ctx)
    if name == "table":
        return _render_table(node, ctx)
    if name == "pre":
        return _render_pre(node)
    # span/font/u/sup/sub/nobr/div/p… — прозрачно
    return _render_children(node, ctx)


def _render_children(node: Tag, ctx: ConvertContext) -> str:
    return "".join(render_inline(child, ctx) for child in node.children)


# ------------------------------------------------------------------ ссылки/картинки


def _render_a(tag: Tag, ctx: ConvertContext) -> str:
    href = str(tag.get("href", ""))
    text = _render_children(tag, ctx).strip() or href
    label = _esc_link_text(text)
    return f"[{label}]({_resolve_href(href, ctx)})"


def _resolve_href(href: str, ctx: ConvertContext) -> str:
    if href.startswith(DOC_LINK_PREFIX):
        resolved = _resolve_doc_link(href, ctx)
        return resolved if resolved is not None else href
    return href  # #якорь, http(s), абсолютный — как есть


def _resolve_doc_link(href: str, ctx: ConvertContext) -> str | None:
    rest = href[len(DOC_LINK_PREFIX):]
    slug, _, anchor = rest.partition("::")
    path = ctx.links.get(slug)
    if path is None:
        ctx.missing.add(slug)
        return None
    target = PurePosixPath(f"{path}.mdx")
    rel = _relhref(ctx.src_dir, target)
    return f"{rel}#{anchor}" if anchor else rel


def _render_img(tag: Tag, ctx: ConvertContext) -> str:
    src = str(tag.get("src", ""))
    alt = (tag.get("alt") or "").strip()
    if src.startswith(IMG_LINK_PREFIX):
        href = _relhref(ctx.src_dir, ctx.img_dir / src[len(IMG_LINK_PREFIX):])
    elif "://" in src or src.startswith("/"):
        return f"![{alt}]({src})"
    elif src.startswith("images/"):
        href = _relhref(ctx.src_dir, ctx.img_dir / file_name(src))
    elif src:
        href = _relhref(ctx.src_dir, ctx.img_dir / file_name(src))
    else:
        return ""
    return f"![{alt}]({href})"


# ------------------------------------------------------------------ pre/код


def _render_pre(tag: Tag) -> str:
    text = tag.get_text().strip("\n")
    m = _LANG_RE.search(_class_str(tag))
    lang = m.group(1) if m else ""
    return f"```{lang}\n{text}\n```"


# ------------------------------------------------------------------ списки


def _render_list(tag: Tag, depth: int, ordered: bool, ctx: ConvertContext) -> str:
    out: list[str] = []
    index = 1
    indent = "  " * depth
    for li in tag.find_all("li", recursive=False):
        content_div = next(
            (c for c in li.find_all("div", recursive=False) if "li" in (c.get("class") or [])),
            None,
        )
        src = content_div if content_div is not None else li
        inline = _render_li_content(src, ctx)
        marker = f"{index}. " if ordered else "- "
        out.append(f"{indent}{marker}{inline}")
        index += 1
        for sub in li.find_all(["ul", "ol"], recursive=False):
            out.append(_render_list(sub, depth + 1, sub.name == "ol", ctx))
    return "\n".join(out)


def _render_li_content(src: Tag, ctx: ConvertContext) -> str:
    """Инлайн содержимого li (из div.li в DokuWiki), без вложенных списков."""
    parts: list[str] = []
    for child in src.children:
        if isinstance(child, Tag) and child.name in ("ul", "ol"):
            continue  # вложенные списки рендерит _render_list отдельно
        parts.append(render_inline(child, ctx))
    return "".join(parts).strip()


# ------------------------------------------------------------------ таблицы


def _render_table(table: Tag, ctx: ConvertContext) -> str:
    rows = table.find_all("tr")
    if not rows:
        return ""
    parsed: list[list[str]] = []
    for tr in rows:
        cells = tr.find_all(["th", "td"])
        parsed.append([_cell_text(c, ctx) for c in cells])
    width = max(len(r) for r in parsed)
    for r in parsed:
        r.extend([""] * (width - len(r)))

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    body_rows = parsed[1:] if len(parsed) > 1 else []
    out = [line(parsed[0]), line(["---"] * width)]
    out.extend(line(r) for r in body_rows)
    return "\n".join(out)


def _cell_text(cell: Tag, ctx: ConvertContext) -> str:
    text = render_inline(cell, ctx).strip()
    return text.replace("\n", "<br>").replace("|", "\\|")


# ------------------------------------------------------------------ контейнеры


def _render_container(node: Tag, ctx: ConvertContext) -> str:
    tag_children = [
        c for c in node.children
        if isinstance(c, Tag) and c.name not in ("script", "style")
    ]
    has_block = any(c.name in _BLOCKISH for c in tag_children)
    if not has_block:
        return render_inline(node, ctx).strip()
    out = [r for r in (render_block(c, ctx) for c in node.children) if r.strip()]
    return "\n\n".join(out)


def _prefix_lines(text: str, prefix: str) -> str:
    if not text:
        return prefix.strip()
    return "\n".join(prefix + ln for ln in text.split("\n"))
