"""Строгая проверка ручной карты выбранных Markdown-страниц."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import DocusaurusMarkdownError


class ManifestError(DocusaurusMarkdownError):
    """Манифест или выбранное им дерево исходников некорректны."""


@dataclass(frozen=True)
class SelectedPage:
    source: PurePosixPath
    slug: str


@dataclass(frozen=True)
class PageSelection:
    pages: tuple[SelectedPage, ...]
    excluded: frozenset[PurePosixPath]
    unlinked_excluded: frozenset[PurePosixPath]


_SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"В JSON-манифесте повторяется ключ {key!r}")
        result[key] = value
    return result


def _relative_posix_path(value: str, *, where: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ManifestError(f"{where}: ожидается непустой относительный POSIX-путь")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ManifestError(f"{where}: путь должен оставаться внутри docs/: {value!r}")
    return path


def _expand_selector(root: Path, selector: str, *, where: str) -> set[PurePosixPath]:
    relative = _relative_posix_path(selector, where=where)
    has_glob = any(char in selector for char in "*?[")
    target = root.joinpath(*relative.parts)
    if has_glob:
        matches = list(root.glob(selector))
        if not matches:
            raise ManifestError(f"{where}: шаблон ничего не нашёл: {selector!r}")
    elif target.is_dir():
        matches = [target]
    elif target.is_file():
        matches = [target]
    else:
        raise ManifestError(f"{where}: путь не найден: {selector!r}")

    files: list[Path] = []
    for match in matches:
        if match.is_dir():
            files.extend(path for path in match.rglob("*") if path.is_file())
        else:
            files.append(match)

    selected: set[PurePosixPath] = set()
    for path in files:
        if path.is_symlink():
            raise ManifestError(f"{where}: symbolic link не поддерживается: {path}")
        if path.suffix.lower() == ".mdx":
            raise ManifestError(f"{where}: MDX пока не поддерживается: {path}")
        if path.suffix.lower() != ".md":
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ManifestError(f"{where}: путь выходит за docs/: {path}")
        selected.add(PurePosixPath(path.relative_to(root).as_posix()))

    if not selected:
        raise ManifestError(f"{where}: путь не содержит Markdown-файлов: {selector!r}")
    return selected


def _string_list(value: Any, *, where: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ManifestError(f"{where}: ожидается список строк")
    if not allow_empty and not value:
        raise ManifestError(f"{where}: список не должен быть пустым")
    return value


def load_page_selection(manifest_path: Path, docs_root: Path) -> PageSelection:
    """Раскрывает выбор страниц, исключения и явные plain-text link targets."""
    try:
        with manifest_path.open("r", encoding="utf-8") as file:
            raw: Any = json.load(file, object_pairs_hook=_unique_json_object)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{manifest_path}: некорректный JSON: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError(f"Не удалось прочитать page manifest {manifest_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError(f"{manifest_path}: корнем должен быть JSON-объект")
    unknown = set(raw) - {"include", "exclude", "unlinked_excluded", "pages"}
    if unknown:
        raise ManifestError(f"{manifest_path}: неизвестные поля: {', '.join(sorted(unknown))}")

    includes = _string_list(raw.get("include"), where="include", allow_empty=False)
    excludes = _string_list(raw.get("exclude", []), where="exclude", allow_empty=True)
    unlinked_values = _string_list(
        raw.get("unlinked_excluded", []),
        where="unlinked_excluded",
        allow_empty=True,
    )
    page_map = raw.get("pages")
    if not isinstance(page_map, dict) or not page_map:
        raise ManifestError("pages: ожидается непустой объект source path → {slug}")

    root = docs_root.resolve()
    if not root.is_dir():
        raise ManifestError(f"Каталог Docusaurus docs не найден: {root}")

    included: set[PurePosixPath] = set()
    for selector in includes:
        expanded = _expand_selector(root, selector, where="include")
        overlap = included & expanded
        if overlap:
            names = ", ".join(sorted(path.as_posix() for path in overlap))
            raise ManifestError(f"include повторно выбирает страницы: {names}")
        included.update(expanded)

    excluded: set[PurePosixPath] = set()
    for selector in excludes:
        expanded = _expand_selector(root, selector, where="exclude")
        overlap = excluded & expanded
        if overlap:
            names = ", ".join(sorted(path.as_posix() for path in overlap))
            raise ManifestError(f"exclude повторно перечисляет страницы: {names}")
        excluded.update(expanded)

    outside_include = excluded - included
    if outside_include:
        names = ", ".join(sorted(path.as_posix() for path in outside_include))
        raise ManifestError(f"exclude не входит в include: {names}")
    unlinked_excluded: set[PurePosixPath] = set()
    for source_value in unlinked_values:
        source = _relative_posix_path(source_value, where="unlinked_excluded")
        if source in unlinked_excluded:
            raise ManifestError(f"unlinked_excluded повторно перечисляет страницу: {source}")
        if source not in excluded:
            raise ManifestError(
                f"unlinked_excluded должен ссылаться на страницу из exclude: {source}"
            )
        source_file = root.joinpath(*source.parts)
        if not source_file.is_file() or source_file.is_symlink():
            raise ManifestError(f"unlinked_excluded: файл не найден или небезопасен: {source}")
        if not source_file.resolve().is_relative_to(root):
            raise ManifestError(f"unlinked_excluded выходит за docs/: {source}")
        unlinked_excluded.add(source)
    selected = included - excluded
    if not selected:
        raise ManifestError("После применения exclude не осталось страниц")

    mapped: dict[PurePosixPath, str] = {}
    used_slugs: dict[str, PurePosixPath] = {}
    for source_value, page_data in page_map.items():
        if not isinstance(source_value, str):
            raise ManifestError("pages: ключи должны быть POSIX-путями")
        source = _relative_posix_path(source_value, where="pages")
        if source.suffix.lower() != ".md":
            raise ManifestError(f"pages: поддерживаются только .md: {source_value!r}")
        if not isinstance(page_data, dict) or set(page_data) != {"slug"}:
            raise ManifestError(f"pages[{source_value!r}]: ожидается объект только с полем slug")
        slug = page_data["slug"]
        if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
            raise ManifestError(
                f"pages[{source_value!r}].slug должен содержать только буквы, цифры, '_' или '-'"
            )
        if source in mapped:
            raise ManifestError(f"pages: повторный source path {source_value!r}")
        slug_key = slug.casefold()
        if slug_key in used_slugs:
            raise ManifestError(
                f"Коллизия slug {slug!r}: {source_value!r} и {used_slugs[slug_key]}"
            )
        mapped[source] = slug
        used_slugs[slug_key] = source

    missing_mappings = selected - mapped.keys()
    unused_mappings = mapped.keys() - selected
    if missing_mappings or unused_mappings:
        details: list[str] = []
        if missing_mappings:
            names = ", ".join(sorted(path.as_posix() for path in missing_mappings))
            details.append(f"не заданы slug: {names}")
        if unused_mappings:
            names = ", ".join(sorted(path.as_posix() for path in unused_mappings))
            details.append(f"не выбраны include: {names}")
        raise ManifestError("Страницы не совпадают с картой: " + "; ".join(details))

    for source in mapped:
        source_file = root.joinpath(*source.parts)
        if not source_file.is_file():
            raise ManifestError(f"Страница из pages не найдена: {source}")
        if not source_file.resolve().is_relative_to(root):
            raise ManifestError(f"Страница выходит за docs/: {source}")

    return PageSelection(
        pages=tuple(
            SelectedPage(source=source, slug=mapped[source])
            for source in sorted(mapped, key=lambda item: item.as_posix())
        ),
        excluded=frozenset(excluded),
        unlinked_excluded=frozenset(unlinked_excluded),
    )


def load_selected_pages(
    manifest_path: Path, docs_root: Path
) -> tuple[SelectedPage, ...]:
    """Backward-compatible helper for callers that only need active pages."""
    return load_page_selection(manifest_path, docs_root).pages
