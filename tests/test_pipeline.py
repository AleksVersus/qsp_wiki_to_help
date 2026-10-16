# pyright: reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportIndexIssue=false, reportOptionalMemberAccess=false, reportUnknownLambdaType=false
"""Тесты pipeline-оркестрации (Фаза 5).

Проверяют порядок этапов в run_all (суб-функции подменены) и сквозной run_anchors
на маленькой «сборке» в tmp (htm + hhk windows-1251 -> anchors.json), без сети.
    python -m pytest tests/test_pipeline.py -v
"""

from pathlib import Path

from qsp_help_builder import pipeline
from qsp_help_builder.config import (
    ChmSettings,
    LoggingSettings,
    PathSettings,
    Settings,
    SpaSettings,
    PwaSettings,
    WikiSettings,
)


def make_settings(tmp_path: Path) -> Settings:
    wiki = WikiSettings("https://wiki.qsp.org", 5.0, 0.0, "ua")
    paths = PathSettings(
        root=tmp_path,
        src=tmp_path / "html_src",
        out=tmp_path / "html_out",
        images=tmp_path / "html_src" / "images",
        scheme=tmp_path / "html_src" / "urls_links_to_files.json",
        anchors=tmp_path / "html_src" / "anchors.json",
        spa=tmp_path / "spa_out",
        pwa=tmp_path / "pwa_out",
        res_chm=tmp_path / "_res_src" / "chm",
        res_spa=tmp_path / "_res_src" / "spa",
    )
    chm = ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251")
    log = LoggingSettings("DEBUG", tmp_path / "dl.log")
    pwa = PwaSettings("start", "QSP", "QSP", "#2f6db0", "#f4f5f7", "standalone",
                      "images/help_wiki_logo.png")
    return Settings(tmp_path / "qsp_help.toml", wiki, paths, SpaSettings("start"), pwa, chm, frozenset(), log)


def test_run_all_invokes_stages_in_order(monkeypatch):
    order = []
    monkeypatch.setattr(pipeline, "run_download", lambda s: order.append("download"))
    monkeypatch.setattr(pipeline, "run_prepare", lambda s: order.append("prepare"))
    monkeypatch.setattr(pipeline, "run_anchors", lambda s: order.append("anchors"))
    pipeline.run_all(make_settings(Path(".")))
    assert order == ["download", "prepare", "anchors"]


def test_run_anchors_extracts_and_saves(tmp_path: Path):
    """Сквозной прогон: из собранного html_out (hhk+htm) делается anchors.json."""
    settings = make_settings(tmp_path)
    out = settings.paths.out
    out.mkdir(parents=True)
    # id заголовка на 1-based строке 2; hhk ссылается на этот якорь (cp1251).
    (out / "help_test.htm").write_text(
        '<html><body>\n<h2 id="sec_one">Первый</h2>\n</body></html>', encoding="utf-8"
    )
    (out / "qsp.hhk").write_text(
        '<HTML><BODY><OBJECT type="text/sitemap">'
        '<param name="Name" value="Первый"/>'
        '<param name="Local" value="help_test.htm#sec_one"/>'
        "</OBJECT></BODY></HTML>",
        encoding="cp1251",
    )

    anchors = pipeline.run_anchors(settings)

    assert "sec_one" in anchors.anchors_for("help_test")
    assert settings.paths.anchors.is_file()
    # Файл перечитывается контрактом и даёт ту же карту ключевых слов.
    from qsp_help_builder.anchors import Anchors

    reloaded = Anchors.load(settings.paths.anchors)
    assert reloaded.keywords_map() == {"Первый": "help_test.htm#sec_one"}
