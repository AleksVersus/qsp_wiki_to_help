import json
from pathlib import Path, PurePosixPath

from qsp_help_builder.config import DocusaurusMarkdownSettings
from qsp_help_builder.docusaurus_markdown.analyzer import validate_source


def _site(
    tmp_path: Path,
    pages: dict[str, str],
    toc: list[dict],
) -> DocusaurusMarkdownSettings:
    source_dir = tmp_path / "source"
    docs_root = source_dir / "docs"
    for relative, content in pages.items():
        target = docs_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    pages_manifest = tmp_path / "pages.json"
    pages_manifest.write_text(
        json.dumps(
            {
                "include": ["qsp_wiki/**/*.md"],
                "exclude": [],
                "pages": {
                    relative: {"slug": PurePosixPath(relative).stem}
                    for relative in pages
                },
            }
        ),
        encoding="utf-8",
    )
    toc_manifest = tmp_path / "toc.json"
    toc_manifest.write_text(json.dumps(toc), encoding="utf-8")
    return DocusaurusMarkdownSettings(
        repository="https://example.invalid/docs.git",
        ref="main",
        docs_path=PurePosixPath("docs"),
        source_dir=source_dir,
        pages_manifest=pages_manifest,
        toc_manifest=toc_manifest,
    )


def test_validate_supported_markdown_links_anchors_images_and_footnotes(tmp_path: Path):
    settings = _site(
        tmp_path,
        {
            "qsp_wiki/start.md": """---
title: Start
sidebar_position: 1
---
# Start {#start}

[Target](target.md#section), [same page](#start), and [DOCLINK](DOCLINK::index::start).

![local image](assets/picture.png)

> Quote

- outer
  - nested

| A | B |
|---|---|
| 1 | 2 |

```html
<div>example, intentionally code</div>
```

[^note]

[^note]: Footnote text.
""",
            "qsp_wiki/target.md": """---
title: Target
sidebar_position: 2
---
## Target section {#section}
""",
        },
        [
            {
                "label": "Docs",
                "children": [
                    {"label": "Start", "slug": "start"},
                    {"label": "Target", "slug": "target"},
                ],
            }
        ],
    )
    image = settings.source_dir / "docs" / "qsp_wiki" / "assets" / "picture.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    report = validate_source(settings)

    assert report.diagnostics == ()
    assert len(report.pages) == 2
    assert report.link_count == 3
    assert report.assets == {PurePosixPath("qsp_wiki/assets/picture.png")}
    assert report.pages[0].anchors == {"start"}


def test_validate_reports_broken_links_anchors_and_images_with_locations(tmp_path: Path):
    settings = _site(
        tmp_path,
        {
            "qsp_wiki/start.md": """---
title: Start
sidebar_position: 1
---
# Start {#start}

[Broken fragment](target.md#missing) and [missing file](missing.md).

![missing image](missing.png)

[Bad DOCLINK](DOCLINK::index::missing)
""",
            "qsp_wiki/target.md": """---
title: Target
sidebar_position: 2
---
# Target {#target}
""",
        },
        [
            {
                "label": "Docs",
                "children": [
                    {"label": "Start", "slug": "start"},
                    {"label": "Target", "slug": "target"},
                ],
            }
        ],
    )

    report = validate_source(settings)
    messages = [str(diagnostic) for diagnostic in report.diagnostics]

    assert any(
        "start.md:7:" in message and "anchor 'missing'" in message and "target.md" in message
        for message in messages
    )
    assert any("start.md:7:" in message and "missing.md" in message for message in messages)
    assert any("start.md:9:" in message and "missing.png" in message for message in messages)
    assert any("start.md:11:" in message and "DOCLINK anchor 'missing'" in message for message in messages)


def test_validate_rejects_unsupported_markdown_without_treating_fenced_html_as_html(
    tmp_path: Path,
):
    settings = _site(
        tmp_path,
        {
            "qsp_wiki/start.md": """---
title: Start
sidebar_position: 1
---
# Start {#start}

Setext heading {#setext}
-----------------------

~~strikethrough~~

<div>raw</div>

:::note
Not supported.
:::

```ruby
puts 'unsupported'
```

```html
<div>allowed as an example</div>
```
""",
        },
        [{"label": "Start", "slug": "start"}],
    )

    report = validate_source(settings)
    messages = [diagnostic.message for diagnostic in report.diagnostics]

    assert any("сырой HTML" in message for message in messages)
    assert any("admonitions" in message for message in messages)
    assert any("fenced code language" in message for message in messages)
    assert any("ATX-заголовки" in message for message in messages)
    assert any("strikethrough" in message for message in messages)


def test_validate_reports_links_to_excluded_pages_and_invalid_toc(tmp_path: Path):
    settings = _site(
        tmp_path,
        {
            "qsp_wiki/start.md": """---
title: Start
sidebar_position: 1
---
# Start {#start}

[Excluded](excluded.md)
""",
            "qsp_wiki/excluded.md": """---
title: Excluded
sidebar_position: 2
---
# Excluded {#excluded}
""",
            "qsp_wiki/target.md": """---
title: Target
sidebar_position: 3
---
# Target {#target}
""",
        },
        [
            {"label": "Start", "slug": "start"},
            {"label": "Repeated", "slug": "start"},
        ],
    )
    settings.pages_manifest.write_text(
        json.dumps(
            {
                "include": ["qsp_wiki/**/*.md"],
                "exclude": ["qsp_wiki/excluded.md"],
                "unlinked_excluded": ["qsp_wiki/excluded.md"],
                "pages": {
                    "qsp_wiki/start.md": {"slug": "start"},
                    "qsp_wiki/target.md": {"slug": "target"},
                },
            }
        ),
        encoding="utf-8",
    )

    report = validate_source(settings)
    messages = [str(diagnostic) for diagnostic in report.diagnostics]

    assert not any("не выбрана или исключена" in message for message in messages)
    assert report.pages[0].links[0].as_text
    inline = next(
        token
        for token in report.pages[0].tokens
        if token.type == "inline" and "Excluded" in token.content
    )
    assert all(child.type not in {"link_open", "link_close"} for child in inline.children or [])
    assert any(child.type == "text" and child.content == "Excluded" for child in inline.children or [])
    assert any("slug 'start' уже указан" in message for message in messages)
    assert any("страница 'target' отсутствует в TOC" in message for message in messages)

    manifest = json.loads(settings.pages_manifest.read_text(encoding="utf-8"))
    manifest.pop("unlinked_excluded")
    settings.pages_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    strict_report = validate_source(settings)
    assert any(
        "не выбрана или исключена" in diagnostic.message
        for diagnostic in strict_report.diagnostics
    )
