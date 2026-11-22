import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from qsp_help_builder.docusaurus_markdown.errors import DocusaurusMarkdownError
from qsp_help_builder.docusaurus_markdown import source as source_module
from qsp_help_builder.docusaurus_markdown.manifest import (
    ManifestError,
    load_selected_pages,
)
from qsp_help_builder.docusaurus_markdown.source import sync_source
from qsp_help_builder.config import (
    ConfigError,
    DocusaurusMarkdownSettings,
    load_settings,
)
from qsp_help_builder.pipeline import run_markdown_sync


def _write_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _manifest(
    *,
    include: list[str],
    pages: dict[str, dict[str, str]],
    exclude: list[str] | None = None,
    unlinked_excluded: list[str] | None = None,
) -> dict:
    return {
        "include": include,
        "exclude": exclude or [],
        "unlinked_excluded": unlinked_excluded or [],
        "pages": pages,
    }


def test_checked_in_page_map_matches_phase_zero_scope():
    path = Path(__file__).parents[1] / "docusaurus_markdown" / "pages.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    pages = raw["pages"]

    assert len(pages) == 62
    assert sum(source.startswith("qsp_wiki/") for source in pages) == 47
    assert sum(source.startswith("help_add/") for source in pages) == 15
    assert len({page["slug"].casefold() for page in pages.values()}) == 62
    assert len(raw["exclude"]) == 2
    assert set(raw["unlinked_excluded"]) == set(raw["exclude"])


def test_legacy_config_without_markdown_section_still_loads(tmp_path: Path):
    project_root = Path(__file__).parents[1]
    original = (project_root / "qsp_help.toml").read_text(encoding="utf-8")
    legacy = original.split("\n[docusaurus_markdown]\n", 1)[0] + "\n"
    config = tmp_path / "qsp_help.toml"
    config.write_text(legacy, encoding="utf-8")

    settings = load_settings(config)

    assert settings.docusaurus_markdown is None
    with pytest.raises(ConfigError, match="нужна секция"):
        run_markdown_sync(settings)


def test_manifest_expands_directories_and_globs_with_explicit_exclusions(tmp_path: Path):
    docs = tmp_path / "docs"
    files = [
        "qsp_wiki/start.md",
        "qsp_wiki/nested/keep.md",
        "qsp_wiki/nested/drop.md",
        "help_add/extra.md",
    ]
    for relative in files:
        target = docs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# page", encoding="utf-8")
    (docs / "qsp_wiki" / "picture.png").write_bytes(b"image")

    manifest = tmp_path / "pages.json"
    _write_manifest(
        manifest,
        _manifest(
            include=["qsp_wiki", "help_add/**/*.md"],
            exclude=["qsp_wiki/nested/drop.md"],
            pages={
                "qsp_wiki/start.md": {"slug": "start"},
                "qsp_wiki/nested/keep.md": {"slug": "keep"},
                "help_add/extra.md": {"slug": "extra"},
            },
        ),
    )

    pages = load_selected_pages(manifest, docs)

    assert [(page.source.as_posix(), page.slug) for page in pages] == [
        ("help_add/extra.md", "extra"),
        ("qsp_wiki/nested/keep.md", "keep"),
        ("qsp_wiki/start.md", "start"),
    ]


def test_manifest_rejects_new_unmapped_page(tmp_path: Path):
    docs = tmp_path / "docs"
    selected_dir = docs / "qsp_wiki"
    selected_dir.mkdir(parents=True)
    (selected_dir / "start.md").write_text("# Start", encoding="utf-8")
    (selected_dir / "new.md").write_text("# New", encoding="utf-8")
    manifest = tmp_path / "pages.json"
    _write_manifest(
        manifest,
        _manifest(
            include=["qsp_wiki"],
            pages={"qsp_wiki/start.md": {"slug": "start"}},
        ),
    )

    with pytest.raises(ManifestError, match="new.md"):
        load_selected_pages(manifest, docs)


def test_manifest_rejects_missing_page_slug_and_slug_collisions(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("one.md", "two.md"):
        (docs / name).write_text("# Page", encoding="utf-8")
    manifest = tmp_path / "pages.json"
    _write_manifest(
        manifest,
        _manifest(
            include=["*.md"],
            pages={
                "one.md": {"slug": "same"},
                "two.md": {"slug": "SAME"},
            },
        ),
    )

    with pytest.raises(ManifestError, match="Коллизия slug"):
        load_selected_pages(manifest, docs)


def test_manifest_rejects_mdx_in_selected_directory(tmp_path: Path):
    docs = tmp_path / "docs"
    selected_dir = docs / "qsp_wiki"
    selected_dir.mkdir(parents=True)
    (selected_dir / "page.mdx").write_text("# Not supported", encoding="utf-8")
    manifest = tmp_path / "pages.json"
    _write_manifest(
        manifest,
        _manifest(
            include=["qsp_wiki"],
            pages={"qsp_wiki/page.mdx": {"slug": "page"}},
        ),
    )

    with pytest.raises(ManifestError, match="MDX пока не поддерживается"):
        load_selected_pages(manifest, docs)


def test_manifest_reports_missing_file(tmp_path: Path):
    with pytest.raises(ManifestError, match="Не удалось прочитать page manifest"):
        load_selected_pages(tmp_path / "missing.json", tmp_path / "docs")


def test_manifest_requires_plain_text_targets_to_be_explicitly_excluded(tmp_path: Path):
    docs = tmp_path / "docs"
    page = docs / "qsp_wiki" / "start.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Start", encoding="utf-8")
    manifest = tmp_path / "pages.json"
    _write_manifest(
        manifest,
        _manifest(
            include=["qsp_wiki"],
            pages={"qsp_wiki/start.md": {"slug": "start"}},
            unlinked_excluded=["qsp_wiki/start.md"],
        ),
    )

    with pytest.raises(ManifestError, match="должен ссылаться на страницу из exclude"):
        load_selected_pages(manifest, docs)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _local_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("outside docs", encoding="utf-8")
    docs = repo / "docs" / "qsp_wiki"
    docs.mkdir(parents=True)
    (docs / "start.md").write_text("# Start", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    _git(repo, "branch", "-M", "main")
    return repo, _git(repo, "rev-parse", "HEAD")


def _sync_settings(tmp_path: Path, repo: Path, ref: str = "main") -> DocusaurusMarkdownSettings:
    manifest = tmp_path / "pages.json"
    _write_manifest(
        manifest,
        _manifest(
            include=["qsp_wiki/**/*.md"],
            pages={"qsp_wiki/start.md": {"slug": "start"}},
        ),
    )
    return DocusaurusMarkdownSettings(
        repository=repo.as_uri(),
        ref=ref,
        docs_path=PurePosixPath("docs"),
        source_dir=tmp_path / ".build" / "docusaurus_source",
        pages_manifest=manifest,
        toc_manifest=tmp_path / "toc.json",
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is required for sparse checkout tests")
def test_sync_sparse_checks_out_selected_tree_and_skips_same_commit_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, expected_commit = _local_repo(tmp_path)
    settings = _sync_settings(tmp_path, repo)

    result = sync_source(settings)
    monkeypatch.setattr(
        source_module,
        "_install_staging",
        lambda *_args: pytest.fail("same-commit sync should not replace the source directory"),
    )
    repeated = sync_source(settings)

    assert result.commit == expected_commit
    assert repeated.commit == expected_commit
    assert result.docs_dir == settings.source_dir / "docs"
    assert [page.slug for page in result.pages] == ["start"]
    assert (result.docs_dir / "qsp_wiki" / "start.md").is_file()
    assert not (settings.source_dir / "README.md").exists()
    assert not list(settings.source_dir.parent.glob("docusaurus_source.backup-*"))


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is required for sparse checkout tests")
def test_sync_replaces_clean_checkout_when_remote_commit_changes(tmp_path: Path):
    repo, first_commit = _local_repo(tmp_path)
    settings = _sync_settings(tmp_path, repo)
    initial = sync_source(settings)
    source_page = repo / "docs" / "qsp_wiki" / "start.md"
    source_page.write_text("# Updated", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "update")
    expected_commit = _git(repo, "rev-parse", "HEAD")

    refreshed = sync_source(settings)

    assert initial.commit == first_commit
    assert refreshed.commit == expected_commit
    assert (refreshed.docs_dir / "qsp_wiki" / "start.md").read_text(encoding="utf-8") == "# Updated"
    assert not list(settings.source_dir.parent.glob("docusaurus_source.backup-*"))


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is required for sparse checkout tests")
def test_sync_accepts_absolute_local_repository_path(tmp_path: Path):
    repo, expected_commit = _local_repo(tmp_path)
    settings = replace(
        _sync_settings(tmp_path, repo),
        repository=str(repo.resolve()),
    )

    result = sync_source(settings)

    assert result.commit == expected_commit


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is required for sparse checkout tests")
def test_failed_fetch_preserves_previous_source(tmp_path: Path):
    repo, _ = _local_repo(tmp_path)
    settings = _sync_settings(tmp_path, repo)
    first = sync_source(settings)
    original = (first.docs_dir / "qsp_wiki" / "start.md").read_text(encoding="utf-8")

    with pytest.raises(DocusaurusMarkdownError):
        sync_source(_sync_settings(tmp_path, repo, ref="ref-that-does-not-exist"))

    assert (settings.source_dir / "docs" / "qsp_wiki" / "start.md").read_text(encoding="utf-8") == original


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is required for sparse checkout tests")
def test_sync_refuses_to_replace_locally_modified_source(tmp_path: Path):
    repo, _ = _local_repo(tmp_path)
    settings = _sync_settings(tmp_path, repo)
    result = sync_source(settings)
    source_page = result.docs_dir / "qsp_wiki" / "start.md"
    source_page.write_text("# Local edit", encoding="utf-8")

    with pytest.raises(DocusaurusMarkdownError, match="локальные изменения"):
        sync_source(settings)

    assert source_page.read_text(encoding="utf-8") == "# Local edit"
