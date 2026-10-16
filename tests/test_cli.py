# pyright: reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false
"""Тесты CLI-точка входа (Фаза 5).

Проверяют разбор аргументов и диспетчеризацию, НЕ запуская реальные этапы
(pipeline-функции подменяются recorder-ами). Реальный qsp_help.toml проекта
используется как вход — заодно это офлайн-проверка, что конфиг грузится и
конвертируется в Settings.
    python -m pytest tests/test_cli.py -v
"""

import pytest

from qsp_help_builder import cli
from qsp_help_builder.config import ConfigError


# ------------------------------------------------------------------ разбор аргументов

def test_parser_accepts_all_commands():
    parser = cli.build_parser()
    for cmd in ("download", "prepare", "anchors", "spa", "pwa", "all"):
        assert parser.parse_args([cmd]).command == cmd


def test_parser_rejects_unknown_command():
    with pytest.raises(SystemExit):
        cli.main(["frobnicate"])


def test_parser_requires_command():
    with pytest.raises(SystemExit):
        cli.main([])


# ------------------------------------------------------------------ диспетчеризация

def test_main_dispatches_selected_command_and_returns_zero(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "configure_logging", lambda s: None)
    monkeypatch.setitem(cli.COMMANDS, "prepare", lambda s: calls.append("prepare"))
    assert cli.main(["prepare"]) == 0
    assert calls == ["prepare"]


def test_main_log_level_overrides_config(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "configure_logging", lambda s: seen.setdefault("settings", s))
    monkeypatch.setitem(cli.COMMANDS, "prepare", lambda s: None)
    cli.main(["prepare", "--log-level", "WARNING"])
    assert seen["settings"].logging.level == "WARNING"


def test_main_returns_2_on_config_error(monkeypatch):
    def boom(_path):
        raise ConfigError("нет файла")

    monkeypatch.setattr(cli, "load_settings", boom)
    assert cli.main(["prepare"]) == 2
