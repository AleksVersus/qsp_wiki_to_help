#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Фазa 0 (бейзлайн): генератор SHA256-манифестов для каталога.

Зачем: после каждого прогона рефакторинга мы пересобираем html_out и сверяем
манифест с эталонным — так обнаруживается ЛЮБОЕ расхождение выходных файлов,
включая те, что легко проглядеть (порядок строк, кодировки, невидимые символы).

Использование:
    python make_manifest.py <папка> [-o out.json] [--skip .chm]

Формат манифеста:
    {"root": "<абсолютный путь>", "algorithm": "sha256",
     "skip_ext": [...], "files": {"<относительный/path>": "<sha256>"}}
Относительные пути нормализуются к прямому слэшу — манифест сравнивается
на разных машинах и не зависит от разделителей Windows.
"""

import argparse
import hashlib
import json
from pathlib import Path


def sha256_of(path: Path) -> str:
    """Считает SHA256 файла по частям (файлы могут быть крупным памяти)."""
    h = hashlib.sha256()
    with open(path, "rb") as fp:  # 'rb' — хэшируем байты, кодировка не важна
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: Path, skip_ext: tuple[str, ...]) -> dict:
    files = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() in skip_ext:  # исключаем артефакты вроде .chm
            continue
        # POSIX-относительный путь — стабильный ключ для diff-сравнений
        key = p.relative_to(root).as_posix()
        files[key] = sha256_of(p)
    return {
        "root": str(root.resolve()),
        "algorithm": "sha256",
        "skip_ext": list(skip_ext),
        "files": files,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path, help="папка для охэширования")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="куда сохранить манифест (по умолчанию <folder>.manifest.json)")
    ap.add_argument("--skip", nargs="*", default=[".chm"],
                    help="расширения-исключения (по умолчанию: .chm)")
    args = ap.parse_args()

    root = args.folder
    if not root.is_dir():
        raise SystemExit(f"Не найдена папка: {root}")

    manifest = build_manifest(root, tuple(e.lower() for e in args.skip))

    out = args.out or Path(str(root).rstrip("/\\") + ".manifest.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2, sort_keys=True)

    # Сводка прямо в консоль: сколько файлов и нет ли дубликатов-коллизий
    hashes: dict[str, list[str]] = {}
    for name, digest in manifest["files"].items():
        hashes.setdefault(digest, []).append(name)
    dups = [v for v in hashes.values() if len(v) > 1]
    print(f"Захэшировано файлов: {len(manifest['files'])} -> {out}")
    if dups:
        print("Идентичные по содержимому группы (в пределах нормы для копий):")
        for group in dups:
            print("  *", ", ".join(group))


if __name__ == "__main__":
    main()
