"""Целевые профили форматирования ссылок и картинок (Фаза 7).

Один и тот же подготовленный контент отдаётся в разных форматах «адреса»:
- CHM — отдельные ``.htm``-файлы, ссылки вида ``help_coding.htm#anchor``, картинки
  рядом по имени файла;
- SPA (одностраничник) — всё в одном документе, ссылки вида ``#slug~anchor``,
  картинки в подпапке ``images/``.

Классы несут только чистые функции форматирования — никакой сети/IO. Выбор
профиля делает вызывающий (``model.build_site_model`` / рендереры).
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol


class OutputProfile(Protocol):
    """Способ превратить разрешённую внутреннюю ссылку/картинку в целевой адрес."""

    def internal_target(self, resolved: str, base_url: str) -> tuple[str, bool]:
        """Финальный ``href`` для внутренней ссылки и флаг «открыть в новой вкладке».

        ``resolved`` — строка после разрешения по scheme (для CHM это может быть
        локальный ``help_coding.html#anchor`` либо нераспознанная вики-ссылка,
        оставшаяся абсолютной). Возвращает ``(итоговый_href, force_blank)``.
        """
        ...

    def image_href(self, name: str) -> str:
        """Финальный ``src`` картинки по её локальному имени файла."""
        ...


def _is_absolute(href: str, base_url: str) -> bool:
    return href.startswith(base_url) or href.startswith("http://") or href.startswith("https://")


class ChmProfile:
    """Формат CHM: побайтово повторяет старый ``replace_links``/``replace_src``."""

    def internal_target(self, resolved: str, base_url: str) -> tuple[str, bool]:
        # ИСТОРИК: '.html' -> '.htm' во всей строке (как старый href.replace),
        # нераспознанные вики-ссылки остаются абсолютными без target=_blank.
        return resolved.replace(".html", ".htm"), False

    def image_href(self, name: str) -> str:
        return name


class SpaProfile:
    """Формат одностраничника: слаги и якоря в hash-навигации, картинки в images/."""

    def internal_target(self, resolved: str, base_url: str) -> tuple[str, bool]:
        if _is_absolute(resolved, base_url):
            # Нераспознанная scheme вики-ссылка или внешний домен: живая вики —
            # наружная ссылка (новая вкладка), а не битый якорь одностраничника.
            return resolved, True
        head, _, rest = resolved.partition("#")
        anchor = rest.split("?", 1)[0] if rest else ""
        slug = PurePosixPath(head).stem
        return (f"#{slug}~{anchor}" if anchor else f"#{slug}"), False

    def image_href(self, name: str) -> str:
        return f"images/{name}"


CHM_PROFILE: OutputProfile = ChmProfile()
SPA_PROFILE: OutputProfile = SpaProfile()
