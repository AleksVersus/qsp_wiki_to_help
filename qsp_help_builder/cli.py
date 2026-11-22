"""CLI-точка входа: ``python -m qsp_help_builder <этап>`` (Фаза 5).

Закрывает главную боль старых скриптов (handoff §4.1): вместо трёх запусков
«каждый из своей папки» — единая точка входа, работающая из ЛЮБОГО CWD (все
пути резолвятся от qsp_help.toml). Разбор аргументов и настройка логов живут
только здесь; реальную работу делает ``pipeline``.

Единственный обязательный аргумент — команда; ``--config`` нужен лишь когда
qsp_help.toml лежит нестандартно (по умолчанию ищется в корне проекта).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from . import pipeline
from .config import ConfigError, configure_logging, load_settings
from .docusaurus_markdown.errors import DocusaurusMarkdownError

# Команда -> имя функции pipeline. Порядок буквальный, «all» собран отдельно.
COMMANDS = {
    "download": pipeline.run_download,
    "prepare": pipeline.run_prepare,
    "anchors": pipeline.run_anchors,
    "spa": pipeline.run_spa,
    "pwa": pipeline.run_pwa,
    "docusaurus": pipeline.run_docusaurus,
    "markdown-sync": pipeline.run_markdown_sync,
    "markdown-validate": pipeline.run_markdown_validate,
    "markdown-build": pipeline.run_markdown_build,
    "all": pipeline.run_all,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m qsp_help_builder",
        description="Сборка офлайн-справки QSP из wiki.qsp.org и Markdown-источников Docusaurus.",
    )
    parser.add_argument(
        "command",
        choices=sorted(COMMANDS),
        help="download — выгрузка с wiki (нужна сеть); prepare — .build/wiki->.build/chm (CHM); "
        "anchors — извлечение якорей из .build/chm; spa — одностраничник "
        ".build/wiki->.build/spa; pwa — PWA для хостинга .build/wiki->docs; "
        "docusaurus — дерево .md-документов .build/wiki->[docusaurus].out; "
        "markdown-sync — sparse checkout и проверка выбранных исходников Docusaurus; "
        "markdown-validate — локальная проверка Markdown, ссылок, якорей, ассетов и TOC; "
        "markdown-build — CHM/SPA/PWA из локального Markdown-входа (отдельные выходы); "
        "all — download->prepare->anchors.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="путь к qsp_help.toml (по умолчанию — корень проекта рядом с пакетом).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="переопределить уровень логирования из конфига для этого запуска.",
    )
    parser.add_argument(
        "--target",
        choices=["chm", "spa", "pwa", "all"],
        default="all",
        help="цель для markdown-build (по умолчанию all).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.log_level:
        settings = replace(
            settings, logging=replace(settings.logging, level=args.log_level)
        )

    configure_logging(settings)
    try:
        if args.command == "markdown-build":
            pipeline.run_markdown_build(settings, args.target)
        else:
            COMMANDS[args.command](settings)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except DocusaurusMarkdownError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
