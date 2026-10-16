"""Точка входа ``python -m qsp_help_builder`` (Фаза 5).

Позволяет запускать конвейер единой командой из любого CWD; вся логика — в cli.
Примеры:
    python -m qsp_help_builder prepare
    python -m qsp_help_builder anchors --log-level INFO
    python -m qsp_help_builder all --config /путь/qsp_help.toml
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
