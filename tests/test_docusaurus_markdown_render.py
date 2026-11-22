import json
from pathlib import Path, PurePosixPath

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
from qsp_help_builder.render.docusaurus_markdown import (
    render_markdown_chm,
    render_markdown_pwa,
    render_markdown_spa,
)


def _settings(tmp_path: Path) -> Settings:
    source = tmp_path / "source"
    docs = source / "docs"
    (docs / "qsp_wiki" / "assets").mkdir(parents=True)
    (docs / "qsp_wiki" / "assets" / "pic.png").write_bytes(b"png")
    (docs / "qsp_wiki" / "start.md").write_text(
        """---
title: Start
sidebar_position: 1
---
# Start {#start}

[Target](target.md#section)

![Picture](assets/pic.png)
""",
        encoding="utf-8",
    )
    (docs / "qsp_wiki" / "target.md").write_text(
        """---
title: Target
sidebar_position: 2
---
## Section {#section}

Target text.
""",
        encoding="utf-8",
    )
    pages = tmp_path / "pages.json"
    pages.write_text(
        json.dumps(
            {
                "include": ["qsp_wiki/**/*.md"],
                "exclude": [],
                "pages": {
                    "qsp_wiki/start.md": {"slug": "start"},
                    "qsp_wiki/target.md": {"slug": "target"},
                },
            }
        ),
        encoding="utf-8",
    )
    toc = tmp_path / "toc.json"
    toc.write_text(
        json.dumps(
            [
                {"label": "Start", "slug": "start"},
                {"label": "Target", "slug": "target"},
            ]
        ),
        encoding="utf-8",
    )
    markdown = DocusaurusMarkdownSettings(
        repository="https://example.invalid/docs.git",
        ref="main",
        docs_path=PurePosixPath("docs"),
        source_dir=source,
        pages_manifest=pages,
        toc_manifest=toc,
    )
    res_chm = tmp_path / "res_chm"
    res_spa = tmp_path / "res_spa"
    res_chm.mkdir()
    res_spa.mkdir()
    (res_chm / "default.css").write_text("body{}", encoding="utf-8")
    (res_spa / "default.css").write_text("body{}", encoding="utf-8")
    (res_spa / "spa.css").write_text("body{}", encoding="utf-8")
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
        res_chm=res_chm,
        res_spa=res_spa,
    )
    return Settings(
        config_path=tmp_path / "qsp_help.toml",
        wiki=WikiSettings("https://wiki.qsp.org", 30.0, 0.0, "test"),
        paths=paths,
        spa=SpaSettings("start"),
        pwa=PwaSettings("start", "QSP", "QSP", "#000", "#fff", "standalone", ""),
        docusaurus=DocusaurusSettings("start"),
        chm=ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251"),
        exclude_files=frozenset(),
        logging=LoggingSettings("INFO", tmp_path / "download.log"),
        docusaurus_markdown=markdown,
    )


def test_markdown_renderers_write_separate_targets(tmp_path: Path):
    settings = _settings(tmp_path)

    chm = render_markdown_chm(settings)
    spa = render_markdown_spa(settings)
    pwa = render_markdown_pwa(settings)

    assert (chm / "start.htm").is_file()
    assert not (chm / "start.md").exists()
    assert (chm / "qsp.hhc").is_file()
    assert (chm / "qsp.hhk").is_file()
    assert (chm / "pic.png").is_file()

    spa_html = (spa / "index.html").read_text(encoding="utf-8")
    assert 'data-slug="start"' in spa_html
    assert 'href="#target~section"' in spa_html
    assert 'src="images/pic.png"' in spa_html

    pwa_html = (pwa / "index.html").read_text(encoding="utf-8")
    assert 'manifest.webmanifest' in pwa_html
    assert 'id="search"' in pwa_html
    assert (pwa / "search.json").is_file()
    assert (pwa / "sw.js").is_file()
    assert (pwa / "manifest.webmanifest").is_file()
