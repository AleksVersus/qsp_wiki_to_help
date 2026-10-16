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

# Команда -> имя функции pipeline. Порядок буквальный, «all» собран отдельно.
COMMANDS = {
    "download": pipeline.run_download,
    "prepare": pipeline.run_prepare,
    "anchors": pipeline.run_anchors,
    "all": pipeline.run_all,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m qsp_help_builder",
        description="Сборка офлайн-справки QSP из wiki.qsp.org (этапы конвейера).",
    )
    parser.add_argument(
        "command",
        choices=sorted(COMMANDS),
        help="download — выгрузка с wiki (нужна сеть); prepare — html_src->html_out; "
        "anchors — извлечение якорей из собранного html_out; all — download->prepare->anchors.",
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
    COMMANDS[args.command](settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
