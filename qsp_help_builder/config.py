"""Настройки сборки — единственный источник: внешний ``qsp_help.toml``.

Решение пользователя от 2026-10-16 (plan.md § «Принятые решения», п.2):
значений by-default в коде НЕТ. Отсутствие файла, секции или ключа — ошибка
загрузки, а не повод что-то подставлять молча.

Что это чинит по сравнению со старыми скриптами:
- ``ChmPrepare.__init__`` держил dict настроек с путями через
  ``os.getcwd() + '..'`` (backlog handoff §4.1) — теперь все пути резолвятся
  от папки с конфигом (корень проекта) и не зависят от CWD;
- константы загрузчика (base_url, timeout, delay, user-agent, логгер) были
  зашиты в модуле — теперь они в ``[wiki]``/``[logging]``.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Ошибка конфигурации: нет файла/секции/ключа или значение непригодно."""


@dataclass(frozen=True)
class WikiSettings:
    """Этап выгрузки с wiki (быв. константы qsp_wiki_downloader.py)."""

    base_url: str
    timeout_sec: float
    delay_sec: float
    user_agent: str


@dataclass(frozen=True)
class PathSettings:
    """Рабочие пути. После загрузки все — абсолютные."""

    root: Path     # корень проекта = папка файла qsp_help.toml
    src: Path      # html_src: скачанные страницы wiki (вход этапа 2)
    out: Path      # html_out: подготовленные файлы (выход этапа 2)
    images: Path   # html_src/images: скачанные картинки (выход этапа download)
    scheme: Path   # urls_links_to_files.json: контракт url -> файл
    anchors: Path  # anchors.json: контракт якорь -> строка/заголовок


@dataclass(frozen=True)
class ChmSettings:
    """Этап подготовки (быв. dict настроек ChmPrepare + хардкод имён qsp.*)."""

    hhc_source: str    # файл в html_out — основа содержания (был ключ 'hhc')
    hhk_source: str    # файл в html_out — основа указателя (был ключ 'hhk')
    hhc_output: str    # имя итогового файла содержания (был хардкод 'qsp.hhc')
    hhk_output: str    # имя итогового файла указателя (был хардкод 'qsp.hhk')
    page_encoding: str       # кодировка htm-страниц (исторически utf-8)
    index_encoding: str      # кодировка hhc/hhk (HTML Help Workshop требует windows-1251)


@dataclass(frozen=True)
class LoggingSettings:
    level: str
    download_log: Path  # файл лога выгрузки (абсолютный путь)


@dataclass(frozen=True)
class Settings:
    config_path: Path
    wiki: WikiSettings
    paths: PathSettings
    chm: ChmSettings
    exclude_files: frozenset[str]  # wiki-разделы, исключаемые из справки (files_to_del)
    logging: LoggingSettings


def default_config_path() -> Path:
    """Проектный корень — папка на уровень выше пакета."""
    return Path(__file__).resolve().parent.parent / "qsp_help.toml"


def _require(section: dict, key: str, where: str):
    """Достаёт обязательный ключ; отсутствие — явная ошибка с адресом."""
    if key not in section:
        raise ConfigError(f"В qsp_help.toml отсутствует ключ '{key}' в секции [{where}]")
    return section[key]


def _require_section(raw: dict, name: str, config_path: Path) -> dict:
    if name not in raw:
        raise ConfigError(f"В {config_path.name} отсутствует обязательная секция [{name}]")
    return raw[name]


def _resolve(root: Path, value: str) -> Path:
    """Относительный путь конфига -> абсолютный от корня проекта (CWD не участвует)."""
    p = Path(value)
    return p if p.is_absolute() else (root / p).resolve()


def load_settings(config_path: Path | None = None) -> Settings:
    """Читает и валидирует qsp_help.toml. Без конфига запуск невозможен (решение п.2)."""
    path = Path(config_path) if config_path else default_config_path()
    if not path.is_file():
        raise ConfigError(
            f"Файл конфигурации не найден: {path}\n"
            "Значений by-default в коде нет — создайте qsp_help.toml в корне проекта."
        )

    with open(path, "rb") as fp:  # tomllib требует именно binary-режим
        raw = tomllib.load(fp)

    wiki_raw = _require_section(raw, "wiki", path)
    paths_raw = _require_section(raw, "paths", path)
    chm_raw = _require_section(raw, "chm", path)
    exclude_raw = _require_section(raw, "exclude", path)
    log_raw = _require_section(raw, "logging", path)

    root = path.resolve().parent

    wiki = WikiSettings(
        base_url=str(_require(wiki_raw, "base_url", "wiki")).rstrip("/"),
        # rstrip: старый код join-ил ссылки через urljoin от base_url без слэша;
        # приводим к тому же виду, чтобы поведение краулера не изменилось.
        timeout_sec=float(_require(wiki_raw, "timeout_sec", "wiki")),
        delay_sec=float(_require(wiki_raw, "delay_sec", "wiki")),
        user_agent=str(_require(wiki_raw, "user_agent", "wiki")),
    )
    if not wiki.base_url.startswith(("http://", "https://")):
        raise ConfigError(f"[wiki].base_url выглядит не как URL: {wiki.base_url!r}")

    paths = PathSettings(
        root=root,
        src=_resolve(root, _require(paths_raw, "src", "paths")),
        out=_resolve(root, _require(paths_raw, "out", "paths")),
        images=_resolve(root, _require(paths_raw, "images", "paths")),
        scheme=_resolve(root, _require(paths_raw, "scheme", "paths")),
        anchors=_resolve(root, _require(paths_raw, "anchors", "paths")),
    )

    chm = ChmSettings(
        hhc_source=str(_require(chm_raw, "hhc_source", "chm")),
        hhk_source=str(_require(chm_raw, "hhk_source", "chm")),
        hhc_output=str(_require(chm_raw, "hhc_output", "chm")),
        hhk_output=str(_require(chm_raw, "hhk_output", "chm")),
        page_encoding=str(_require(chm_raw, "page_encoding", "chm")),
        index_encoding=str(_require(chm_raw, "index_encoding", "chm")),
    )

    exclude_files = frozenset(_require(exclude_raw, "files", "exclude"))

    logging_s = LoggingSettings(
        level=str(_require(log_raw, "level", "logging")).upper(),
        download_log=_resolve(root, _require(log_raw, "download_log", "logging")),
    )

    return Settings(
        config_path=path.resolve(),
        wiki=wiki,
        paths=paths,
        chm=chm,
        exclude_files=exclude_files,
        logging=logging_s,
    )


def configure_logging(settings: Settings) -> None:
    """Настраивает логгеры ПО ЯВНОМУ вызову, а не на уровне импорта модуля.

    Старый qsp_wiki_downloader.py вызывал logging.basicConfig в шапке модуля —
    настройка срабатывала ещё до main и влияла на всё приложение при любом
    import (backlog handoff §4.6). Здесь логи подключаются только когда этап
    реально запускается (pipeline/cli). Файл лога — исторический download_log.
    """
    level = getattr(logging, settings.logging.level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):  # идемпотентность при повторных вызовах
        root.removeHandler(handler)
    log_path = settings.logging.download_log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
