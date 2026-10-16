"""qsp_help_builder — сборка офлайн-справки QSP из wiki.qsp.org.

Пакет построен по этапам (см. plan.md в корне проекта):

- ``config``   — загрузка настроек из единственного файла ``qsp_help.toml``;
- ``fs_utils`` — общие операции с файлами (read/write/json), дублировавшиеся
  в старых скриптах;
- ``schema``   — модель контракта ``urls_links_to_files.json`` (этап 1 -> этап 2);
- ``templates``— дословные заготовки страниц CHM/HHС/HHK из старого кода;
- ``anchors``  — единая модель anchors.json (Фаза 2);
- ``prepare``  — этап подготовки html_src→html_out, порт ChmPrepare (Фаза 3);
- ``download``/``pipeline`` — появляются в Фазах 4–5.

Правило приёмки каждого изменения: пересборка html_out обязана совпасть
с эталоном ``_baseline/2026-10-16`` (см. BASELINE.md там же).
"""
