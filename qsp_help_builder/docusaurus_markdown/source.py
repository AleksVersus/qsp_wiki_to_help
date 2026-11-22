"""Получение изолированной sparse-копии Markdown-документации."""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..config import DocusaurusMarkdownSettings
from .errors import DocusaurusMarkdownError
from .manifest import SelectedPage, load_selected_pages

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    source_dir: Path
    docs_dir: Path
    commit: str
    pages: tuple[SelectedPage, ...]


def _git(cwd: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(cwd), *args],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
            stdin=subprocess.DEVNULL,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise DocusaurusMarkdownError("Для markdown-sync требуется установленный Git") from exc
    except subprocess.TimeoutExpired as exc:
        raise DocusaurusMarkdownError(f"Команда Git превысила таймаут: git {' '.join(args)}") from exc
    except OSError as exc:
        raise DocusaurusMarkdownError(f"Не удалось запустить Git: {exc}") from exc

    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        command = " ".join(args[:2])
        raise DocusaurusMarkdownError(f"git {command} завершился с ошибкой: {detail}")
    return result.stdout.strip()


def _validate_repository(repository: str, ref: str) -> None:
    if not Path(repository).is_absolute():
        try:
            parsed = urlsplit(repository)
        except ValueError as exc:
            raise DocusaurusMarkdownError(f"Некорректный repository URL: {exc}") from exc
        if parsed.scheme == "https":
            if not parsed.netloc or parsed.username or parsed.password:
                raise DocusaurusMarkdownError(
                    "repository должен быть HTTPS URL без встроенных credentials"
                )
        elif parsed.scheme == "file":
            if parsed.netloc not in {"", "localhost"}:
                raise DocusaurusMarkdownError("file repository должен быть локальным")
        elif parsed.scheme:
            raise DocusaurusMarkdownError(
                "Поддерживаются HTTPS URL, file:// URL или абсолютный локальный путь"
            )
        else:
            raise DocusaurusMarkdownError(
                "Локальный repository должен быть абсолютным путём"
            )

    if not ref or ref.startswith("-") or any(char in ref for char in "\r\n\x00"):
        raise DocusaurusMarkdownError("ref должен быть непустым Git ref или commit SHA")


def _assert_replaceable_target(source_dir: Path, repository: str) -> None:
    if not source_dir.exists():
        return
    if not source_dir.is_dir() or not (source_dir / ".git").exists():
        raise DocusaurusMarkdownError(
            f"Отказываюсь перезаписывать неуправляемый source-каталог: {source_dir}"
        )
    actual_repository = _git(source_dir, "config", "--get", "remote.origin.url")
    if actual_repository != repository:
        raise DocusaurusMarkdownError(
            f"Source-каталог {source_dir} принадлежит другому repository"
        )
    status = _git(source_dir, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise DocusaurusMarkdownError(
            f"Source-каталог содержит локальные изменения; сначала сохраните их: {source_dir}"
        )


def _stop_fsmonitor_daemon(source_dir: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_dir), "fsmonitor--daemon", "stop"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DocusaurusMarkdownError(
            f"Не удалось остановить Git fsmonitor для {source_dir}: {exc}"
        ) from exc

    if result.returncode:
        detail = result.stderr.strip().lower()
        if (
            "not running" in detail
            or "not supported" in detail
            or "not a git command" in detail
        ):
            return
        raise DocusaurusMarkdownError(
            f"Не удалось остановить Git fsmonitor для {source_dir}: {result.stderr.strip()}"
        )


def _remove_directory(path: Path) -> None:
    def make_writable_and_retry(function, target: str, _exc_info) -> None:
        target_path = Path(target)
        os.chmod(target_path, os.stat(target_path).st_mode | stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _install_staging(staging: Path, source_dir: Path) -> None:
    backup: Path | None = None
    if source_dir.exists():
        backup = source_dir.with_name(f"{source_dir.name}.backup-{uuid.uuid4().hex}")
        os.replace(source_dir, backup)
    try:
        os.replace(staging, source_dir)
    except OSError as exc:
        if backup is not None and backup.exists():
            try:
                os.replace(backup, source_dir)
            except OSError as restore_exc:
                raise DocusaurusMarkdownError(
                    f"Не удалось установить source и восстановить прежний каталог: "
                    f"{source_dir}; backup оставлен в {backup}"
                ) from restore_exc
        raise DocusaurusMarkdownError(
            f"Не удалось атомарно установить source-каталог: {source_dir}"
        ) from exc

    if backup is not None:
        try:
            _remove_directory(backup)
        except OSError as exc:
            logger.warning("Новый source установлен; не удалось удалить backup %s: %s", backup, exc)


def sync_source(settings: DocusaurusMarkdownSettings) -> SyncResult:
    """Скачивает ref во staging, проверяет карту и только затем меняет source-dir."""
    _validate_repository(settings.repository, settings.ref)
    source_dir = settings.source_dir
    _assert_replaceable_target(source_dir, settings.repository)

    try:
        source_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{source_dir.name}.staging-",
                dir=source_dir.parent,
            )
        )
    except OSError as exc:
        raise DocusaurusMarkdownError(
            f"Не удалось создать временную папку рядом с {source_dir}: {exc}"
        ) from exc
    try:
        _git(staging, "init", "--quiet")
        _git(staging, "remote", "add", "origin", settings.repository)
        _git(staging, "fetch", "--depth=1", "--filter=blob:none", "origin", settings.ref)
        _git(staging, "sparse-checkout", "init", "--no-cone")
        _git(
            staging,
            "sparse-checkout",
            "set",
            "--no-cone",
            f"/{settings.docs_path.as_posix()}/",
        )
        _git(staging, "checkout", "--quiet", "--detach", "FETCH_HEAD")
        commit = _git(staging, "rev-parse", "HEAD")

        docs_dir = staging.joinpath(*settings.docs_path.parts)
        pages = load_selected_pages(settings.pages_manifest, docs_dir)
        if source_dir.exists() and _git(source_dir, "rev-parse", "HEAD") == commit:
            existing_docs_dir = source_dir.joinpath(*settings.docs_path.parts)
            if all((existing_docs_dir / page.source).is_file() for page in pages):
                logger.info("Source уже синхронизирован с commit %s", commit)
                return SyncResult(
                    source_dir=source_dir,
                    docs_dir=existing_docs_dir,
                    commit=commit,
                    pages=pages,
                )
        if source_dir.exists():
            _stop_fsmonitor_daemon(source_dir)
        _install_staging(staging, source_dir)
        return SyncResult(
            source_dir=source_dir,
            docs_dir=source_dir.joinpath(*settings.docs_path.parts),
            commit=commit,
            pages=pages,
        )
    except OSError as exc:
        raise DocusaurusMarkdownError(f"Не удалось синхронизировать {source_dir}: {exc}") from exc
    finally:
        if staging.exists():
            try:
                _remove_directory(staging)
            except OSError as exc:
                logger.warning("Не удалось удалить staging-каталог %s: %s", staging, exc)
