# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownArgumentType=false, reportIndexIssue=false, reportArgumentType=false, reportUnknownVariableType=false
"""Рендерер Docusaurus: модель -> ``docusaurus_docs/`` (дерево .mdx-документов).

Четвёртый выход поверх той же нейтральной модели (:func:`model.build_site_model`),
но с ``DocusaurusProfile`` (ссылки/картинки — токены, а не готовые адреса). Отличие
от CHM/SPA/PWA — способ сериализации и раскладки:

- содержание (sidebar) задаёт вложенность папок: каждый уровень TOC — свой каталог;
- страницы вне содержания уходят в ``help_add/``;
- HTML каждой страницы вручную конвертируется в MDX (:mod:`.convert`);
- порядок задают атрибуты Docusaurus: ``_category_.json`` (папки) и
  ``sidebar_position`` (файлы), а числа и цели ссылок переживают пересборку в
  мутируемых JSON-базах (:mod:`.bases`);
- ссылки в .mdx — относительные от самого файла; картинки — в центральный ``img/``.

Содержимое модели (тексты/ссылки/картинки)Prepare не трогает: CHM-вывод побайтово
не меняется (правило приёмки бейзлайна).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path, PurePosixPath

from ...config import Settings
from ...fs_utils import ensure_dir, file_name, save_json, write_text
from ...model import SiteModel, build_site_model
from ..profile import DocusaurusProfile, IMG_LINK_PREFIX
from ..spa import NAV_SOURCE_SLUG
from .bases import DocRecord, FolderRecord, LinksBase, Numbering
from .convert import ConvertContext, relhref, render_body
from .toc import HELP_ADD_DIR, Layout, build_layout, parse_toc

logger = logging.getLogger(__name__)

IMG_DIR = PurePosixPath("img")
DOC_EXT = ".mdx"


def render_docusaurus(settings: Settings) -> None:
    """Полная сборка дерева Docusaurus по настройкам (полностью офлайн)."""
    model = build_site_model(settings, DocusaurusProfile())
    out = ensure_dir(settings.paths.docusaurus)
    bases = ensure_dir(settings.paths.docusaurus_bases)

    layout = _build_layout(model, settings)
    # слаги дополнительных страниц тоже должны резолвиться ссылками -> обновляем links
    links_map = dict(layout.links)  # slug -> путь rel docs root без расширения
    LinksBase(links_map).save(bases / "links.json")

    doc_recs, folder_recs, placements = _records(model, layout)
    numbering = Numbering.load(bases / "numbering.json")
    positions = numbering.assign(
        doc_recs, folder_recs, start_slug_key=_start_key(layout, settings.docusaurus.start_page)
    )
    numbering.save(bases / "numbering.json")

    _write_folders(out, layout, folder_recs, positions["folder"])
    missing: set[str] = set()
    count = _write_docs(out, model, placements, positions["doc"], links_map, missing)
    if missing:
        logger.warning(
            "Docusaurus: ссылки на отсутствующие страницы (%d): %s",
            len(missing), ", ".join(sorted(missing)),
        )
    _copy_images(model, settings, out / "img")

    logger.info(
        "Docusaurus собран: %s (документов %d, папок %d)",
        out, count, len(layout.folders),
    )


# ------------------------------------------------------------------ раскладка


def _build_layout(model: SiteModel, settings: Settings) -> Layout:
    """TOC-дерево + layout; страницы вне содержания добавляет в help_add/."""
    sidebar = model.by_slug.get(NAV_SOURCE_SLUG)
    nodes = parse_toc(sidebar.fragment) if sidebar is not None else []
    available = set(model.by_slug) - {NAV_SOURCE_SLUG}
    layout = build_layout(nodes, available, settings.docusaurus.start_page)

    extra_slugs = [
        p.slug for p in model.pages
        if p.slug != NAV_SOURCE_SLUG and p.slug not in layout.links
    ]
    for slug in extra_slugs:
        layout.links[slug] = f"{HELP_ADD_DIR}/{slug}"
    layout.extra_slugs = extra_slugs
    return layout


def _records(model: SiteModel, layout: Layout) -> tuple[list[DocRecord], list[FolderRecord], list[tuple[str, PurePosixPath]]]:
    """Готовит записи нумерации (docs+folders) и порядок записи файлов (slug, путь)."""
    doc_recs: list[DocRecord] = []
    placements: list[tuple[str, PurePosixPath]] = []

    for doc in layout.docs:
        page = model.by_slug.get(doc.slug)
        label = (page.title if page and page.title else doc.slug)
        folder = doc.file_path.parent.as_posix()
        key = f"{folder}/{doc.file_path.name}"
        doc_recs.append(DocRecord(key=key, folder=folder, filename=doc.file_path.name, label=label))
        placements.append((doc.slug, doc.file_path))

    for slug in layout.extra_slugs:
        page = model.by_slug.get(slug)
        label = (page.title if page and page.title else slug)
        file_path = PurePosixPath(f"{HELP_ADD_DIR}/{slug}{DOC_EXT}")
        key = f"{HELP_ADD_DIR}/{file_path.name}"
        doc_recs.append(DocRecord(key=key, folder=HELP_ADD_DIR, filename=file_path.name, label=label))
        placements.append((slug, file_path))

    folder_recs = [
        FolderRecord(key=f.rel.as_posix(), path=f.rel.as_posix(), label=f.label)
        for f in layout.folders
    ]
    return doc_recs, folder_recs, placements


def _start_key(layout: Layout, start_slug: str) -> str:
    """Ключ нумерации стартового документа, если он лежит в корне (для позиции 1)."""
    for doc in layout.docs:
        if doc.slug == start_slug and doc.file_path.parent == PurePosixPath("."):
            return f"./{doc.file_path.name}"
    return ""


# ------------------------------------------------------------------ запись


def _write_folders(
    out: Path, layout: Layout, folder_recs: list[FolderRecord], positions: dict[str, int]
) -> None:
    for spec, rec in zip(layout.folders, folder_recs):
        folder_dir = ensure_dir(out / spec.rel.as_posix())
        category: dict[str, object] = {
            "label": spec.label,
            "position": positions.get(rec.key, 1),
        }
        if spec.index_slug:
            # id — относительная ссылка на файл индекс-дока от папки категории
            # (как и все ссылки в .mdx), а не docs-root идентификатор.
            doc_rel = PurePosixPath(f"{layout.links[spec.index_slug]}{DOC_EXT}")
            category["link"] = {
                "type": "doc",
                "id": relhref(spec.rel, doc_rel),
            }
        save_json(category, folder_dir / "_category_.json")


def _write_docs(
    out: Path,
    model: SiteModel,
    placements: list[tuple[str, PurePosixPath]],
    positions: dict[str, int],
    links_map: dict[str, str],
    missing: set[str],
) -> int:
    count = 0
    for slug, file_path in placements:
        page = model.by_slug.get(slug)
        if page is None:
            continue
        ctx = ConvertContext(
            src_dir=file_path.parent, links=links_map, img_dir=IMG_DIR, missing=missing
        )
        body = render_body(page.fragment, ctx)
        key = f"{file_path.parent.as_posix()}/{file_path.name}"
        position = positions.get(key, count + 1)
        label = page.title or slug
        text = _frontmatter(page.title or slug, position, label) + "\n\n" + body
        write_text(out / file_path.as_posix(), text, "utf-8")
        count += 1
    return count


def _frontmatter(title: str, position: int, label: str) -> str:
    lines = ["---", f'title: "{_yaml(title)}"', f"sidebar_position: {position}"]
    if label and label != title:
        lines.append(f'sidebar_label: "{_yaml(label)}"')
    lines.append("---")
    return "\n".join(lines)


def _yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ------------------------------------------------------------------ картинки


def _copy_images(model: SiteModel, settings: Settings, images_dir: Path) -> None:
    """Копирует используемые картинки в центральный ``<out>/img`` (два источника-каталога).

    Профиль оформил ``src`` токеном ``IMGLINK::<имя>`` (а не готовым путём, как
    CHM/SPA), поэтому :meth:`SiteModel.referenced_images` тут не подходит — он
    вернул бы токен целиком. Собираем имена сами: снимаем префикс токена,
    отсекаем внешние/абсолютные адреса.
    """
    ensure_dir(images_dir)
    sources = (settings.paths.images, settings.paths.out)
    names: set[str] = set()
    for page in model.pages:
        for img in page.fragment.find_all("img", src=True):
            src = str(img["src"])
            if src.startswith(IMG_LINK_PREFIX):
                names.add(file_name(src[len(IMG_LINK_PREFIX):]))
            elif "://" in src or src.startswith("/"):
                continue
            elif src:
                names.add(file_name(src))
    for name in sorted(names):
        src = next((d / name for d in sources if (d / name).is_file()), None)
        if src is None:
            logger.warning("картинка не найдена ни в html_src/images, ни в html_out: %s", name)
            continue
        shutil.copy2(src, images_dir / file_name(name))
