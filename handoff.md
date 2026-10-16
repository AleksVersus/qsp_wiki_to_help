# Handoff: контекст проекта и предыдущих действий

> Документ для восстановления контекста в новой сессии. Читается вместе с `plan.md`.
> Актуально на: сессия «анализ + план + направление SPA/PWA + закрытие открытых вопросов».

## 1. Что это за проект

Конвейер сборки офлайн-справки (CHM) по QSP из wiki.qsp.org (DokuWiki).
С Фазы 5 — единый Python-пакет `qsp_help_builder` с точкой входа (запуск из корня
проекта; рабочие пути резолвятся от `qsp_help.toml`, а не от CWD — фик backlog §4.1):

1. `python -m qsp_help_builder download` — краулит wiki → `html_src/` (быв. qsp_wiki_downloader);
2. `python -m qsp_help_builder prepare` — готовит файлы → `html_out/` (+ `qsp.hhc`, `qsp.hhk`) (быв. chm_prepare);
3. `python -m qsp_help_builder anchors` — извлекает якоря из собранного `html_out` в `html_src/anchors.json`
   (быв. `_auxtools/extract_keywords.py`); `all` = download→prepare→anchors;
4. Компиляция внешним **HTML Help Workshop** (`help_workshop/htmlhelp.exe`) — не автоматизирована.

Старые папки `qsp_wiki_downloader/` и `chm_prepare/` **удалены** в Фазе 5 (решение п.6);
их функциональность полностью переехала в пакет. `_auxtools/extract_keywords.py`
**удалён** в Фазе 6 (дублировался `anchors.extract_from_build` + `pipeline.run_anchors`).

Репозиторий также является Obsidian-vault (`.obsidian/`) и Sublime-проектом; артефакты
готовых справок (`qsp_5.9.2.chm`, `qsp_5.9.4.chm`) лежат в `html_out/`.

## 2. Смысл и контракт каждого модуля

### 2.1 `WikiDownloader` (qsp_wiki_downloader.py)

BFS-обход по `https://wiki.qsp.org`, сессионные GET с UA-браузера, задержка 0.5 c,
таймаут 30 c. Страницы сохраняет плоско в `html_src/` (имя = части URL path,
соединённые `_`, недопустимые символы → `_`, суффикс `.html`).

**Выходные контракты:**
- `html_src/*.html` — полные страницы DokuWiki (не только контент);
- `html_src/images/*` — картинки; имя = last-path-part без расширения + расширение
  из content-type (fallback jpg). **§4.2 исправлено (Фаза 6):** для DokuWiki
  `lib/exe/fetch.php?media=<id>` base-имя берётся из значения `media`
  (namespace:id → namespace_id), поэтому картинки больше не схлопываются в один
  `fetch.png`; `is_image_url` детектит картинки и по расширению пути, и по `media`.
- `html_src/urls_links_to_files.json`:
  `{"images": {url: rel_path}, "pages": {url: rel_path}}`,
  пути **относительные Windows** (`"..\\html_src\\..."`) — артефакт запуска из подпапки;
  потребитель (`ChmPrepare`) использует только `os.path.split(...)[1]`, т.е. только имя файла,
  поэтому кривизна пути не всплывает. **При рефакторинге формат менять нельзя** —
  существующий файл в репозитории должен читаться.

Извлечение картинок происходит как **побочный эффект** внутри `extract_links`
(по ссылкам на png/jpg/… и по `<img src>` в `extract_images`). Пропускаются: `.php`,
якоря, mailto, внешние домены, `lib/exe/indexer.php`.

### 2.2 `ChmPrepare` (to_chm_prepare.py)

Настройки by-default — dict в `__init__` (папки src/out, base_url, имена hhc/hhk-источников,
пути к scheme/anchors). Ключевые факты:

- Обрабатываются все `.html` из `html_src/`; выход — `.htm` в `html_out/`;
- Из каждой страницы извлекается **только `div.page.group`** (контент DokuWiki),
  вырезаются TOC (`div#dw__toc`), скрипты и футеры `div.docInfo`.
  **§4.3 исправлено (Фаза 6):** был опечатка `dic.docInfo` (тега `dic` нет) → футеры
  «Последние изменения» сохранялись в выводе; теперь селектор `div.docInfo`, футеры
  вырезаются (задокументированный сдвиг бейзлайна).
- `sidebar.html` (страница `help:sidebar`) — источник оглавления → `qsp.hhc`;
  `help_keywords.html` (`help:keywords`) — источник указателя → `qsp.hhk`;
  после генерации исходные `.htm`-версии **удаляются** из `html_out`;
- `files_to_del` — жёстко зашитый список разделов к исключению (навигатор, aqsp,
  playground, discussions, index). Он же используется для фильтра в hhc
  (`help_keywords` докидывается локально);
- Кодировки: html — utf-8; **hhc/hhk пишутся в windows-1251** (требование HH Workshop);
- Шаблон CHM_PAGE подставляется как обёртка, title переносится из исходной страницы;
  ссылка на `default.css` (файл кладётся в `html_out` вручную).

**Замена ссылок** (`replace_links`/`replace_href`): target=_blank и fn_bot/fn_top не трогаются;
относительные ссылки join-ятся с base_url; wiki-ссылки маппятся через scheme['pages']
(сначала обрезать `#`/`?`-хвосты), `.html`→`.htm`; всё остальное получает `target="_blank"`.

**Замена картинок** (`extract_images`/`replace_src`): src из `https://wiki.qsp.org` или `/_media/`
маппится через scheme['images']; если URL там нет — **эвристика**: из скачанного имени
`help_msgbox.png` восстанавливается wiki-идентификатор `help:msgbox` (`':'.join(name.split('_',1))`)
и ищется подстрока в src. Работает ровно потому, что DokuWiki кодирует media как
`namespace:file` и скачанные имена — `namespace_file`. Ломается на именах с `_` внутри.
Дальше: у картинок снимается «кликабельность» (unwrap родительского `<a>`), width форсируется
в 450, `img.icon` заменяется на alt-текст или удаляется.

**Спец-правки страницы `start`**: логотип в `<h1>`, разворачивание ссылок `/help:keywords`,
перезапись блока «Онлайн-Версия» на ссылку на живую wiki.

**Якоря**: `anchors.json` — `{file_name: {anchor: [line_number, title]}}`.
В `prepare_htm` перед строкой `file_lines[line]` вставляется `<a id="{anchor}"></a>`.
**§4.4 исправлено (Фаза 6):** `line_number` — согласованный **0-based** индекс и на
extract, и на inject (раньше 1-based↔0-based давал сдвиг на строку вниз). Сбои
вне диапазона логируются. При вставке якорей ids DokuWiki (у заголовков `<hN id=...>`)
сохранены — extract ищет именно их. Для hhk строится карта `title -> file.htm#anchor`
(`keywords_map`), `_href_compare` подставляет якорь к ссылке из таблицы; точечные
поправки §4.11 задаются в `[chm.keyword_overrides]` (побеждают карту и href_compare).

### 2.3 `ExtractKeyword` (быв. _auxtools/extract_keywords.py, удалён в Фазе 6)

Портирован в `anchors.Anchors.extract_from_build` + `pipeline.run_anchors`. Читает **готовый** `html_out/qsp.hhk` (cp1251) + `html_out/*.htm`, находит `id="{anchor}"`
в файлах, вычисляет номер строки, пишет `html_src/anchors.json`. По смыслу — это инструмент
переноса вручную размеченных якорей между пересборками — после перегенерации html_out
линии могут съехать, формат намеренно «сырые номера строк».

### 2.4 Тесты (`qsp_wiki_downloader/test_*.py`)

Не pytest, а ручные скрипты, трогающие живую сеть. При рефакторинге заменяются
на офлайн-тесты чистых функций (см. план, Фаза 5).

### 2.5 Модель сайта и рендереры (Фаза 7)

- **`render/profile.py`** — `OutputProfile` (протокол) + `ChmProfile`/`SpaProfile`
  (одитональные чистые функции форматирования целей вывода, без сети/IO).
  `ChmProfile`: page → `{file}.htm`, anchor → `{file}.htm#{anchor}`, картинка → голое
  имя (побайтово == легаси `prepare`, CHM не сдвигается). `SpaProfile`: page →
  `#{slug}`, anchor → `#{slug}~{anchor}`, картинка → `images/{имя}`; нераспознанная
  вики-ссылка уходит наружу с `target=_blank`. `slug` = stem файла `html_src`.
- **`prepare/links.py` / `prepare/images.py`** — примитивы получили обязательный
  параметр `profile`; финальная цель строится через `profile.internal_target` /
  `profile.image_href`. Логика urljoin/scheme/среза хвостов и ИСТОРИКи (last-match-wins,
  сноски/`_blank`) сохранены. По умолчанию `CHM_PROFILE` — существующие вызовы не ломаются.
- **`model.py`** — `build_site_model(settings, profile) -> SiteModel`. Нейтральная сборка
  поверх `prepare`-примитивов (`extract_page` + `apply_start_fixes` для `start` +
  `replace_links(profile)` + `process_images(profile)`); `Page{slug,title,source_soup,fragment}`,
  `SiteModel{pages,anchors,scheme,profile,by_slug,referenced_images()}`. Ничего не пишет на диск.
- **`render/chm.py`** — `render_chm(settings)`: перенос тела `prepare_all` на модель
  (`ChmProfile`); обёртка CHM-шаблона + построчная инъекция якорей (CHM-специфика) +
  `qsp.hhc`/`qsp.hhk`. `prepare/__init__.prepare_all` оставлен ре-экспортом (ленивый импорт).
- **`render/spa.py`** — `render_spa(settings)`: `SpaProfile` → один `spa_out/index.html`
  (hash-router JS, `<section data-slug>`, namespace id `{slug}~X`, навигация из `sidebar`,
  `_normalize_local_images` + `_copy_assets` → `spa_out/images/`).

## 3. Что сделано в последней сессии

- Проект полностью прочитан и проанализирован (оба основных скрипта, aux-инструмент,
  тесты, README-и, форматы `urls_links_to_files.json` / `anchors.json`);
- Составлен черновой план рефакторинга → **`plan.md`** (целевая структура пакета
  `qsp_help_builder/`, фазы 0–8, принципы, открытые вопросы);
- Написан этот handoff;
- Пользователь заявил после рефакторинга цель: сборка в **автономный одностраничник
  или PWA**. Проработано направление в `plan.md` (раздел «Направление», Фазы 7–8):
  решение — не бинарный выбор, а общая **модель сайта** (`model.py`) с рендерерами
  chm/spa/pwa; первым — одностраничник, затем PWA. Отмечены предварительные условия:
  фикс ассет-пайплайна загрузчика (§4.2) и якоря как стабильные id (§4.4);
- **Код не изменялся** (по требованию пользователя). Ошибки линтера игнорировались
  по явному указанию — это осознанно, а не забыто.
- Все открытые вопросы plan.md закрыты пользователем (см. §5 «Принятые решения»,
  п.п. 4–7); в плане осталось одно направление — хостинг PWA (молча считаем GitHub Pages).
- **Фаза 0 выполнена**: бейзлайн зафиксирован в `_baseline/2026-10-16/` на commit
  `914e503`; helper `_baseline/make_manifest.py` (SHA256-манифесты для приёмки фаз).
  Ключевая находка: закоммиченный html_out — это **золото с ручными правками**, код
  воспроизводит 71/73 файла; расходятся только `help_qgen.htm` (url картинки qgen не
  чинится автоматикой) и `qsp.hhk` (4 якоря вручную переведены на другие страницы).
  Детерминированность кода доказана двойным прогоном; входы `html_src` тоже захэшированы.
- **Фаза 1 выполнена**: каркас пакета `qsp_help_builder/` (`config`, `fs_utils`,
  `schema`, `templates`) + рабочий `qsp_help.toml` (весь хардкод пересажен дословно,
  источники указаны в комментариях; CWD-независимость проверена). Мёртвый ключ
  `start_file` из старых настроек выброшен — код его не читал. В `.gitignore`
  добавлен `__pycache__/`. Старые скрипты и html_out не тронуты.
- **Фаза 2 выполнена**: `qsp_help_builder/anchors.py` + `tests/test_anchors.py`
  (10 pytest-тестов, все зелёные). Порт эквивалентен старому инструменту на
  реальных данных (сравнение ExtractKeyword↔Anchors на золотом html_out: True).
  Off-by-one (ИСТОРИК) сохранён намеренно и закреплён тестами — починка только
  как задокументированное изменение поведения (Фаза 6).
- **Фаза 3 выполнена**: `ChmPrepare` разобран на `qsp_help_builder/prepare/`
  (`__init__` c `prepare_file`/`prepare_all`, `page_clean`, `links`, `images`, `hhc`, `hhk`),
  питание через `Settings`/`UrlScheme`/`Anchors`. Порт 1:1: опечатка `dic.docInfo` проверена
  на реальных html_src (блоки docInfo есть, матчатся `div.docInfo`, но из-за опечатки
  СОХРАНЯЮТСЯ в выводе — не чиним, сдвинуло бы бейзлайн); нечёткое `replace_src` вынесено
  в `match_wiki_media_name`; сохранены присвоение href без замены, порядок атрибутов `<param>`,
  удаление sidebar.htm/help_keywords.htm. print→logger.debug. Приёмка: `prepare_all`
  пересобрал html_out побайтово == `m_regen1.json` (73 файла, 0 расхождений; манифест
  `_baseline/2026-10-16/m_phase3.json`, html_out откачен git restore). `tests/test_prepare.py`
  — 23 офлайн-теста; всего 33 зелёных. Старые `chm_prepare/` не тронуты.
- **Фаза 4 выполнена**: `WikiDownloader` разобран на `qsp_help_builder/download/`
  (`naming.py` — чистые page_filename/image_filename/image_extension; `crawler.py` —
  чистые `extract_page_links`/`collect_image_urls` + `Crawler`/`DownloadStats`). Ключевое
  изменение по плану: скачивание картинок больше НЕ побочный эффект обхода — за BFS
  собирается множество URL картинок, прогон отдельным `download_images`. Логгер: `logging.basicConfig`
  из шапки модуля заменён на явный `config.configure_logging(settings)` (вызывается в
  `run_download`). Настройки краулера из `Settings` (base_url/timeout/delay/UA), добавлен
  `[paths].images`. Контракты сохранены 1:1: имена файлов, ИСТОРИК-баг query-строки
  (`fetch.php?media=… → fetch.png`) закреплён тестом, scheme пишется в `urls_links_to_files.json`
  (значения — пути от корня проекта, потребителю нужно только имя). НЮАНС: относительные
  wiki-href `help:coding` без ведущего `/` urljoin принимает за схему URL и теряет их —
  реальные ссылки DokuWiki идут как `/help:coding` (проверено тестами). Офлайн-тесты:
  test_naming (13) + test_crawler (8, mock-сессия); всего 54 зелёных. Сеть не трогали,
  html_src не перезаписывали (реальный краул — ручной). Старый `qsp_wiki_downloader/` не тронут.
- **Фаза 5 выполнена**: `pipeline.py` (`run_download`/`run_prepare`/`run_anchors`/`run_all`) +
  `cli.py`/`__main__.py` — единая точка входа `python -m qsp_help_builder <download|prepare|anchors|all>`
  с `--config`/`--log-level`, CWD-независимая. README переписан под команды CLI. Единый
  `requirements.txt` в корне. `download_log` перенесён в корень (`wiki_download.log`) —
  логу больше не нужна удалённая папка; в .gitignore добавлен `/wiki_download.log`.
  **Удалены** `qsp_wiki_downloader/` и `chm_prepare/` (без shim, решение п.6). Приёмка:
  `python -m qsp_help_builder prepare` пересобрал html_out побайтово == `m_regen1.json`
  (73/73, 0 расхождений; html_out откачен git restore). Тесты: test_cli (6) + test_pipeline (2),
  всего 62 зелёных.
- **Фаза 6 (безопасная зачистка) выполнена**: удалён мёртвый дубль
  `_auxtools/extract_keywords.py` (всё равно не импортировался; функциональность — в
  `anchors.extract_from_build` + `pipeline.run_anchors`); поправлены устаревшие пометки и
  грамматика в комментариях (`anchors.py`, `pipeline.py`). Вывод НЕ менялся: prepare ==
  `m_regen1` (73/73), 62 теста зелёные. Остальное из §4 устранено портированием ранее
  (print/дубли/логгер/getcwd/counter/опечатки кода — Фазы 1–5; README — Фаза 5).
  **Отложены (сдвигают бейзлайн, пользователь выбрал только безопасную часть):**
  §4.2 fetch-имена (нужна сеть), §4.3 docInfo, §4.4/§4.12 якоря, §4.11 ручные правки —
  выполнять как ЗАДОКУМЕНТИРОВАННОЕ изменение поведения с переламыванием baseline,
  целесообразно в составе Фазы 7.
- **Фаза 6 (достройка) ВЫПОЛНЕНА 2026-10-17 — отложенные пункты доведены отдельными
  шагами + живой ре-краул, новый бейзлайн `_baseline/2026-10-17`:**
  §4.2 `naming.image_filename`/`is_image_url` — имя из `media=` (fetch.php больше не
  схлопывается в `fetch.png`), `crawler.download_image` одним источником зовёт naming;
  §4.3 `page_clean` — `dic.docInfo`→`div.docInfo` (футеры вырезаются);
  §4.4/§4.12 `anchors` — согласованный 0-based, `anchors.json` перегенерирован из свежей
  сборки до идемпотентной точки покоя (2 итерации prepare→anchors);
  §4.11 — ручные правки перенесены в код: `[chm.keyword_overrides]` (4 редиректа hhk) +
  штатное разрешение qgen через §4.2; ассеты в `html_out` синхронизированы (добавлены
  `qgen.png`/`image.png`, удалены устаревшие `help_qgen.png`/`help_qspider_error.png`,
  из `html_src` удалён `fetch.png`). Проведён `download` на живую вики (80 стр./17 картинок,
  0 ошибок; контент-дрейф + per-request tok — ожидаемы). Приёмка: `prepare` детерминирован
  (m_regen==m_regen2, 77 файлов), расхождение golden↔regen = 0; 69 тестов зелёные.
- **Фаза 7 (модель сайта + одностраничник) ВЫПОЛНЕНА 2026-10-16 — CHM сохранён:**
  `render/profile.py` (`ChmProfile`/`SpaProfile` + протокол `OutputProfile`) — единый источник
  форматирования целей; `prepare/links.py`/`images.py` получили обязательный `profile`
  (тот же модуль параллельно готовит ссылки/картинки и для CHM, и для SPA — решение
  пользователя); `model.py` (`build_site_model` → `SiteModel{pages,anchors,scheme,profile}`)
  — нейтральная сборка поверх примитивов `prepare`, ничего не пишет; `render/chm.py`
  (`render_chm` — перенос `prepare_all`, `prepare/__init__.prepare_all` теперь лениво
  делегирует ему) и `render/spa.py` (`render_spa` → `spa_out/index.html` + hash-router +
  `images/`, namespace id `{slug}~X`, навигация из `sidebar`, `_normalize_local_images`
  доводит легаси-голые src до `images/`). Конфиг: `[spa].out → paths.spa` (обязателен,
  без дефолтов); `[spa].start_page → spa.start_page` — slug первой контент-секции
  (её показывает router без хеша; правится в конфиге без правки кода). CLI/`pipeline`: команда `spa` (`run_spa`). Приёмка: `prepare` → `html_out`
  **побайтово == baseline `_baseline/2026-10-17/m_regen.json`** (77 файлов, 0 расхождений —
  CHM не сдвинут, пересъёмка не потребовалась); `spa` проверен с `file://` (#start логотип
  грузится, TOC/якоря/картинки работают); 0 ошибок pyright, 77 тестов зелёные
  (`test_model.py`, `test_spa.py` + обновлённые фикстуры под `profile`/`[spa]`).

## 4. Известные проблемы / подозрительные места (вести как backlog)

> Статусы после Фазы 6 (достройки, 2026-10-17): ✅ — устранено; ⏸ — отложено;
> ◻ — архитектурное, остаётся задокументированным.
> ✅ 1,2,3,4,5,6,7,8,9,11,12 (2,3,4,11,12 закрыты в достройке Фазы 6: ре-краул +
> naming/docInfo/anchors 0-based/keyword_overrides); ⏸ — нет; ◻ 10 (chicken-and-egg
> якорей — цикл prepare↔anchors; смягчён идемпотентной точкой покоя, но остаётся
> структурной особенностью).

1. Пути через `os.getcwd()` — скрипты работают только из своей папки;
2. Срез query-строки → картинки `fetch.php?media=...` качались одним `fetch.png` —
   **исправлено в Фазе 6 (ре-краул):** имя берётся из `media=`, `is_image_url` детектит
   по media; детали — `_baseline/2026-10-17/BASELINE.md`;
3. `dic.docInfo` — **исправлено в Фазе 6:** селектор `div.docInfo`, футеры вырезаются;
4. Голый `except` + off-by-one при вставке якорей — **исправлено в Фазе 6:**
   согласованный 0-based + логирование промахов (см. 2.2);
5. `print`-отладка в `extract_images`;
6. Дублирующие helpers (read/write/json) между скриптами; логгер настраивается на import;
7. `save_page` перезаписывает коллизирующиеся имена (блок counter закомментирован);
8. Опечатки в коде/доках: «files_pathes», «сохраена», «подготавливает» и т.п.;
9. README этапы 4–7 (ручная правка hhc/hhk/картинок) частично уже автоматизированы
   кодом — документация отстаёт, обновить по итогам рефакторинга;
10. Chicken-and-egg: `anchors.json` извлекается из выхода того же этапа 2, который его
    потребляет; первый прогон после changes вики требует аккуратности;
11. Ручные правки (qgen-картинка, 4 якоря hhk) — **исправлено в Фазе 6:** перенесены
    в код (`[chm.keyword_overrides]` + штатное разрешение qgen через §4.2); золото
    больше не расходится с кодом (0 файлов);
12. **anchors.json** — **исправлено в Фазе 6:** перегенерирован из свежей сборки
    (после ре-краула), дрейф «+1» и потерянный `kommentarii` устранены; якоря сходятся
    до идемпотентной точки покоя.
13. ⏸ **SPA: url() внутри `default.css` остаются wiki-root-absolute** (`/lib/tpl/…/
    page-gradient.png`, `/lib/images/interwiki/…`) — копируемый из `html_out` CSS ссылается
    на ресурсы, которых нет в `spa_out`; даёт 1 `ERR_FILE_NOT_FOUND` на декоративный фон
    (не функциональный контент). Разрешение css-url-ассетов (сканирование `url()` +
    бандлинг/переписывание) — вне объёма Фазы 7 (манифест собран только по `<img>`),
    кандидатами закрывает Фаза 8 (PWA/единый ассет-пайплайн). Легаси-логотип `start`
    (`help_wiki_logo.png`) в SPA уже резолвится через модель в `images/` (`_copy_assets`
    берёт его из `html_out`, т.к. в `html_src/images` он лежит как `wiki_logo.png`).

## 5. Решения, уже принятые (не переигрывать без причины)

- Объединять этап компиляции CHM с external exe не будем — остаётся ручной шаг;
- Форматы JSON-контрактов обратно совместимы (расширять можно, ломать нельзя);
- Эвристику `replace_src` сохраняем как явную именованную функцию с docstring
  (пока нет лучшего источника соответствий для уже скачанных файлов).

Приняты пользователем 2026-10-16 (детали — § «Принятые решения» в plan.md):

4. Пакет называется **`qsp_help_builder`**;
5. Настройки — **только внешний `qsp_help.toml`** в корне проекта; в `config.py`
   нет значений by-default, только dataclass + загрузчик/валидатор; конфиг-файл
   обязателен для запуска и хранится в репозитории;
6. Старые папки `qsp_wiki_downloader/` и `chm_prepare/` **удаляются сразу** после
   Фазы 5 и сверки бейзлайна; shim-обёрток и совместимости запуска «из своей
   папки» не делаем — единственный вход `python -m qsp_help_builder …`;
7. Одностраничник — **гибрид**: `index.html` + локальная папка `images/` рядом,
   без base64 и без zip.

## 6. С чего начать в новой сессии

1. Открытые вопросы закрыты (plan.md § «Принятые решения»); **Фазы 0–7 завершены**
   (включая достройку Фазы 6 и модель сайта + одностраничник Фазы 7); действующий бейзлайн и
   правило приёмки — `_baseline/2026-10-17/BASELINE.md` (старый 2026-10-16 — superseded).
   Выход `html_out` (CHM) побайтово совпадает с бейзлайном — Фаза 7 его не сдвинула;
2. Следующий шаг — **Фаза 8 (PWA)**: `render/pwa/` поверх уже готовой `model.build_site_model`
   и тех же целей ссылок (переиспользует `SpaProfile`-подобный профиль): статика из модели +
   `manifest.webmanifest` + service worker + client-side поиск; сюда же — единый ассет-пайплайн
   (закрыть §4.13: сканирование `url()` в CSS и бандлинг шрифтов/иконок, легаси-пути `res/…`,
   `images/pic_01.png`). Обсудить хостинг/деплой (plan.md «Направление»). Каждая правка
   поведения CHM — с пересъёмкой baseline-манифеста и фиксацией diff.
4. При проектировании Фаз 3–5 учитывать будущее направление: внутренним ссылкам
   разрешаться в слаги/модель, а не только в .htm-файлы (см. plan.md «Направление»,
   Фазы 7–8) — иначе модель сайта придётся выводить задним числом;
5. Дальше по фазам плана; перед изменением поведения якорей/схем — перечитать §2.2–2.3.

## 7. Технические детали среды

- Windows + PowerShell (`;` вместо `&&`); Python 3.13 (нужен 3.11+ из-за `tomllib`),
  зависимости: `requests`, `beautifulsoup4`, `lxml` — единый `requirements.txt` в корне;
- Запуск: `python -m qsp_help_builder <download|prepare|anchors|all>` из корня проекта
  (нужен корень в sys.path; внутренние пути не зависят от CWD — резолвятся от конфига).
  Тесты: `python -m pytest tests/ -q`;
- В `html_out` уже лежат собранные артефакты прошлых прогонов — использовать для сверки,
  но быть осторожным: prepare **удаляет** `sidebar.htm`/`help_keywords.htm` из `html_out`;
- Коммуникация с пользователем — по-русски (prefs в памяти).
