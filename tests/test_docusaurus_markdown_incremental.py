from pathlib import Path, PurePosixPath

import pytest

from qsp_help_builder.config import (
    ChmSettings,
    DocusaurusMarkdownSettings,
    DocusaurusSettings,
    LoggingSettings,
    PathSettings,
    PwaSettings,
    Settings,
    SpaSettings,
    WikiSettings,
)
from qsp_help_builder.docusaurus_markdown.incremental import build_incremental
from qsp_help_builder.fs_utils import write_text


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    docs = source / "docs"
    docs.mkdir(parents=True)
    (docs / "start.md").write_text("# Start\n", encoding="utf-8")
    pages = tmp_path / "pages.json"
    toc = tmp_path / "toc.json"
    pages.write_text("{}", encoding="utf-8")
    toc.write_text("[]", encoding="utf-8")
    markdown = DocusaurusMarkdownSettings(
        repository="https://example.invalid/docs.git",
        ref="main",
        docs_path=PurePosixPath("docs"),
        source_dir=source,
        pages_manifest=pages,
        toc_manifest=toc,
        chm_out=tmp_path / "out",
        state_dir=tmp_path / "state",
    )
    paths = PathSettings(
        root=tmp_path,
        src=tmp_path / "wiki",
        out=tmp_path / "chm",
        images=tmp_path / "wiki" / "images",
        scheme=tmp_path / "scheme.json",
        anchors=tmp_path / "anchors.json",
        spa=tmp_path / "spa",
        pwa=tmp_path / "pwa",
        docusaurus=tmp_path / "docusaurus",
        docusaurus_bases=tmp_path / "docusaurus_bases",
        res_chm=tmp_path / "res_chm",
        res_spa=tmp_path / "res_spa",
    )
    return Settings(
        tmp_path / "qsp_help.toml",
        WikiSettings("https://wiki.qsp.org", 30.0, 0.0, "test"),
        paths,
        SpaSettings("start"),
        PwaSettings("start", "QSP", "QSP", "#000", "#fff", "standalone", ""),
        DocusaurusSettings("start"),
        ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251"),
        frozenset(),
        LoggingSettings("INFO", tmp_path / "download.log"),
        markdown,
    )


def test_incremental_skips_unchanged_and_rebuilds_changed(tmp_path: Path):
    settings = _settings(tmp_path)
    calls = 0

    def renderer(_settings: Settings, out: Path) -> Path:
        nonlocal calls
        calls += 1
        write_text(out / "page.htm", "same", "utf-8")
        return out

    output, skipped = build_incremental(settings, "chm", renderer)
    assert skipped is False
    assert calls == 1

    output, skipped = build_incremental(settings, "chm", renderer)
    assert skipped is True
    assert calls == 1
    assert (output / "page.htm").read_text(encoding="utf-8") == "same"

    (settings.docusaurus_markdown.source_dir / "docs" / "start.md").write_text(
        "# Changed\n", encoding="utf-8"
    )
    output, skipped = build_incremental(settings, "chm", renderer)
    assert skipped is False
    assert calls == 2


def test_incremental_renderer_failure_preserves_previous_output(tmp_path: Path):
    settings = _settings(tmp_path)

    def good(_settings: Settings, out: Path) -> Path:
        write_text(out / "page.htm", "working", "utf-8")
        return out

    output, _ = build_incremental(settings, "chm", good)
    assert (output / "page.htm").read_text(encoding="utf-8") == "working"

    (settings.docusaurus_markdown.source_dir / "docs" / "start.md").write_text(
        "# New\n", encoding="utf-8"
    )

    def bad(_settings: Settings, out: Path) -> Path:
        write_text(out / "page.htm", "broken", "utf-8")
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError, match="render failed"):
        build_incremental(settings, "chm", bad)

    assert (output / "page.htm").read_text(encoding="utf-8") == "working"
