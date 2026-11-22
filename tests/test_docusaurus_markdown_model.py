import json
from pathlib import Path, PurePosixPath

import pytest

from qsp_help_builder.config import DocusaurusMarkdownSettings
from qsp_help_builder.docusaurus_markdown.analyzer import (
    MarkdownValidationError,
    validate_source,
)
from qsp_help_builder.docusaurus_markdown.model import build_markdown_site_model


def _settings(tmp_path: Path, *, invalid: bool = False) -> DocusaurusMarkdownSettings:
    source = tmp_path / "source"
    docs = source / "docs"
    (docs / "qsp_wiki" / "assets").mkdir(parents=True)
    (docs / "qsp_wiki" / "assets" / "picture.png").write_bytes(b"png")

    start = """---
title: Start
sidebar_position: 1
---
# Start {#start}

[Target](target.md#section)

![picture](assets/picture.png)

[DOCLINK](DOCLINK::index::start)

[External](https://example.com/page)
"""
    if invalid:
        start = start.replace("[Target](target.md#section)", "[Broken](missing.md)")
    (docs / "qsp_wiki" / "start.md").write_text(start, encoding="utf-8")
    (docs / "qsp_wiki" / "target.md").write_text(
        """---
title: Target
sidebar_position: 2
---
## Section {#section}
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
                {
                    "label": "Documentation",
                    "children": [
                        {"label": "Start", "slug": "start"},
                        {"label": "Target", "slug": "target"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return DocusaurusMarkdownSettings(
        repository="https://example.invalid/docs.git",
        ref="main",
        docs_path=PurePosixPath("docs"),
        source_dir=source,
        pages_manifest=pages,
        toc_manifest=toc,
    )


def test_build_markdown_site_model_resolves_pages_links_assets_and_search(tmp_path: Path):
    settings = _settings(tmp_path)
    model = build_markdown_site_model(settings)

    assert [page.slug for page in model.pages] == ["start", "target"]
    start = model.by_slug["start"]
    assert start.title == "Start"
    assert start.anchors == {"start"}
    assert model.assets == {PurePosixPath("qsp_wiki/assets/picture.png")}
    assert model.toc[0].label == "Documentation"
    assert [node.slug for node in model.toc[0].children] == ["start", "target"]

    target_link = next(link for link in start.links if "target.md" in link.destination)
    assert target_link.target_slug == "target"
    assert target_link.anchor == "section"
    assert target_link.external is False

    doclink = next(link for link in start.links if link.destination.startswith("DOCLINK"))
    assert doclink.target_slug == "start"
    assert doclink.anchor == "start"

    external = next(link for link in start.links if link.external)
    assert external.destination == "https://example.com/page"

    assert start.images[0].asset == PurePosixPath("qsp_wiki/assets/picture.png")
    assert model.search_entries[0].slug == "start"
    assert "Start" in model.search_entries[0].text


def test_build_markdown_site_model_rejects_diagnostics(tmp_path: Path):
    settings = _settings(tmp_path, invalid=True)
    with pytest.raises(MarkdownValidationError):
        build_markdown_site_model(settings)
