"""Хеши, пропуск неизменённых сборок и атомарная замена выходов."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..fs_utils import ensure_dir


ADAPTER_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


def fingerprint(settings: Settings, target: str) -> str:
    markdown = settings.docusaurus_markdown
    if markdown is None:
        return ""
    docs = markdown.source_dir.joinpath(*markdown.docs_path.parts)
    digest = hashlib.sha256()
    digest.update(f"adapter:{ADAPTER_VERSION}".encode("utf-8"))
    digest.update(f"target:{target}".encode("utf-8"))
    digest.update(f"repository:{markdown.repository}".encode("utf-8"))
    digest.update(f"ref:{markdown.ref}".encode("utf-8"))
    digest.update(f"docs:{markdown.docs_path.as_posix()}".encode("utf-8"))
    for manifest in (markdown.pages_manifest, markdown.toc_manifest):
        digest.update(manifest.as_posix().encode("utf-8"))
        if manifest.is_file():
            digest.update(sha256_file(manifest).encode("ascii"))
    for rel, file_hash in _hash_tree(docs).items():
        digest.update(rel.encode("utf-8"))
        digest.update(file_hash.encode("ascii"))
    return digest.hexdigest()


def _files_hashes(root: Path) -> dict[str, str]:
    return _hash_tree(root)


def _load_manifest(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_manifest(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=4)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _replace_directory(output: Path, staging: Path) -> None:
    backup: Path | None = None
    if output.exists():
        backup = output.with_name(f"{output.name}.backup-{uuid.uuid4().hex}")
        os.replace(output, backup)
    try:
        os.replace(staging, output)
    except OSError:
        if backup is not None and backup.exists():
            os.replace(backup, output)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def build_incremental(
    settings: Settings,
    target: str,
    renderer: Callable[[Settings, Path], Path],
) -> tuple[Path, bool]:
    """Build target in staging, preserve unchanged files, atomically replace output.

    Returns (output, skipped). skipped=True means fingerprint and output were unchanged.
    """
    markdown = settings.docusaurus_markdown
    if markdown is None:
        raise RuntimeError("docusaurus_markdown settings are required")

    configured = {
        "chm": markdown.chm_out,
        "spa": markdown.spa_out,
        "pwa": markdown.pwa_out,
    }[target]
    output = configured or settings.paths.root / ".build" / "docusaurus_markdown" / target
    state = markdown.state_dir or settings.paths.root / ".build" / "docusaurus_markdown" / "state"
    manifest_path = state / f"{target}.manifest.json"
    input_hash = fingerprint(settings, target)
    prior = _load_manifest(manifest_path)

    if (
        prior.get("version") == ADAPTER_VERSION
        and prior.get("fingerprint") == input_hash
        and output.is_dir()
    ):
        return output, True

    ensure_dir(output.parent)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    staging.rmdir()
    try:
        renderer(settings, staging)
        staged_hashes = _files_hashes(staging)
        prior_files = prior.get("files")
        if isinstance(prior_files, dict) and output.is_dir():
            for rel, old_hash in prior_files.items():
                old_file = output / rel
                if (
                    isinstance(old_hash, str)
                    and old_file.is_file()
                    and sha256_file(old_file) == old_hash
                    and staged_hashes.get(rel) == old_hash
                ):
                    staged_file = staging / rel
                    if staged_file.is_file():
                        staged_file.unlink()
                        staged_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(old_file, staged_file)

        final_hashes = _files_hashes(staging)
        _replace_directory(output, staging)
        _write_manifest(
            manifest_path,
            {
                "version": ADAPTER_VERSION,
                "fingerprint": input_hash,
                "files": final_hashes,
            },
        )
        return output, False
    finally:
        if staging.exists():
            shutil.rmtree(staging)
