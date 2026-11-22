# Сборщик справки из wiki.qsp.org

Проект собран в Python-пакет `qsp_help_builder` с единой точкой входа. Рабочие пути берутся из `qsp_help.toml`, а не из текущей директории, — запуск из любого CWD даёт одинаковый результат (конфиг ищется в корне проекта, рядом с пакетом; для необычного расположения — `--config <путь>`):

```
python -m qsp_help_builder download     # этап 1: выгрузка страниц и картинок с wiki (нужна сеть)
python -m qsp_help_builder prepare      # этап 2a: подготовка .build/wiki -> .build/chm (+ qsp.hhc/qsp.hhk)
python -m qsp_help_builder anchors      # этап 2b: извлечение якорей из собранного .build/chm в anchors.json
python -m qsp_help_builder all          # download -> prepare -> anchors одной командой
python -m qsp_help_builder spa          # сценарий 2: одностраничник .build/wiki -> .build/spa/index.html (+ images/)
python -m qsp_help_builder pwa          # сценарий 3: PWA для хостинга .build/wiki -> docs/ (индекс + манифест + sw + поиск)
python -m qsp_help_builder docusaurus   # сценарий 4: дерево .md-документов .build/wiki -> .build/docusaurus_docs/
python -m qsp_help_builder markdown-sync # получить и проверить Markdown-источники Docusaurus
python -m qsp_help_builder markdown-validate
python -m qsp_help_builder markdown-build --target all
```

`qsp_help_builder/` — код инструмента, `assets/` — поддерживаемые статические ресурсы,
`.build/` — локальные входы/выходы сборки (игнорируется Git). Скачанные файлы и обычные
результаты можно восстановить повторным запуском; удаление
`.build/docusaurus_docs/.docusaurus_build/` сбросит сохранённый порядок Docusaurus.
Исключение — `docs/`: это публикуемый каталог GitHub Pages, его нужно коммитить после сборки PWA.

## Четыре ключевых сценария сборки

Проект поддерживает **четыре независимых сценария** выхода, использующих один и тот же скачанный корпус `.build/wiki`:

1. **[CHM]** Подготовка файлов для HTML Help Workshop: `download` → `prepare` → `anchors` (или `all` одной командой); `prepare` строит `.build/chm` + `qsp.hhc`/`qsp.hhk`, компиляция `.chm` — внешний инструмент (не автоматизирован).
2. **[SPA]** Автономный одностраничник: `spa` из тех же `.build/wiki` строит офлайн `.build/spa/index.html` с hash-навигацией и локальной папкой `images/`. Каталог вывода задаётся в `[spa].out`, а первая страница — в `[spa].start_page` файла `qsp_help.toml`.
3. **[PWA]** Одностраничник для хостинга: `pwa` — надстройка над `spa` (тоже полностью офлайн), добавляющая `manifest.webmanifest` (устанавливаемость), `sw.js` (precache всего состава сборки, офлайн-режим после первого визита) и `search.json` с клиентским полнотекстовым поиском (свой индекс из Python, без внешних библиотек). Каталог вывода — `[pwa].out` (по умолчанию `docs` — авто-источник GitHub Pages), параметры манифеста — в `[pwa]`.
4. **[Docusaurus]** Древо .md-документов для Docusaurus: `docusaurus` извлекает из `.build/wiki` структуру содержания (sidebar) и раскладывает страницы по вложенным папкам `.md`-файлов (вне содержания → `help_add/`). Порядок задают `_category_.json` (папки) и `sidebar_position` (файлы), а числа и цели ссылок переживают пересборку через JSON-базы `[docusaurus].bases` (`numbering.json`/`links.json`). Каталог корня дерева — `[docusaurus].out` (для Docusaurus — это `docs.path`), slug корневой страницы — `[docusaurus].start_page`.

Все четыре сценария собираются поверх **одной нейтральной модели сайта** (`model.build_site_model`),
а различаются только целевым профилем (`render/profile.py`: `ChmProfile`/`SpaProfile`/`DocusaurusProfile`)
и способом сериализации — контент и структура согласованы во всех выходных форматах.

## Получение исходников Docusaurus Markdown

`markdown-sync` и последующие Markdown-команды образуют отдельный конвейер из
`Docusaurus Markdown`. Он не заменяет и не пишет в `.build/wiki`, `.build/chm`,
`.build/spa` и опубликованный `docs/` существующего wiki-конвейера:

```
python -m qsp_help_builder markdown-sync
python -m qsp_help_builder markdown-validate
python -m qsp_help_builder markdown-build --target chm
python -m qsp_help_builder markdown-build --target spa
python -m qsp_help_builder markdown-build --target pwa
python -m qsp_help_builder markdown-build --target all
```

Команда использует Git sparse checkout по `[docusaurus_markdown]` из `qsp_help.toml`,
синхронизирует `docs/` в игнорируемый `.build/docusaurus_source/`, проверяет выбранные
страницы по `docusaurus_markdown/pages.json` и сообщает commit SHA источника. В page manifest
вручную задаются выбранные файлы/папки, исключения, уникальный slug каждой страницы и
исключённые заглушки, ссылки на которые следует оставить обычным текстом.
Если загрузка или проверка завершилась ошибкой, прежний source-каталог остаётся нетронутым.
Для команды требуется установленный Git.

`markdown-validate` проверяет уже синхронизированный локальный source без сети и не пишет
в выходные каталоги: front matter, поддерживаемую Markdown-разметку, явные anchors,
относительные ссылки и fragments, локальные изображения и полное покрытие страниц
в `docusaurus_markdown/toc.json`. Raw HTML, MDX, admonitions и неизвестные языки code fence
отклоняются с указанием файла и строки. Для начала включены 62 `.md`-страницы из `qsp_wiki/`
и `help_add/`; MDX пока не поддерживается.

После проверки `markdown-build --target <цель>` строит изолированный результат:

- `chm` → `.build/docusaurus_markdown/chm/` (`.htm`, `qsp.hhc`, `qsp.hhk`, CSS и картинки);
- `spa` → `.build/docusaurus_markdown/spa/` (`index.html`, CSS и `images/`);
- `pwa` → `.build/docusaurus_markdown/pwa/` (SPA-shell, `manifest.webmanifest`,
  `sw.js`, `search.json` и картинки).

Пути выходов и каталог state-манифестов задаются в `[docusaurus_markdown]` ключами
`chm_out`, `spa_out`, `pwa_out` и `state`. Повторный запуск пропускает неизменённую цель;
изменения собираются в staging-каталог и заменяют рабочий выход только после успешной
сборки. Ошибка рендеринга оставляет предыдущий рабочий каталог и его манифест.

Две исключённые заглушки из исходника — `help_qspider_standalone.md` и
`glossary_snippet.md` — явно перечислены в `unlinked_excluded`: ссылки на них преобразуются
в обычный текст, а сами страницы не попадают в справку и TOC.

### Ручные схемы Markdown-входа

`docusaurus_markdown/pages.json` задаёт точный набор исходников и сопоставление
`source → slug`; selector может включать директорию или glob, но карта должна покрывать
только итоговый набор выбранных `.md`-файлов. Исключённые страницы не могут иметь slug,
а исключённые заглушки перечисляются отдельно в `unlinked_excluded`.

`docusaurus_markdown/toc.json` задаёт явное дерево навигации с `label`, `slug` и
`children`. Все выбранные slug должны встречаться ровно один раз; неизвестные,
повторные и отсутствующие страницы отклоняются валидацией.

Локальные картинки определяются ссылками из Markdown и остаются внутри staging/source;
публикация выполняется копированием в целевой CHM/SPA/PWA-каталог с сохранением имени.
Внешние HTTP(S)-ссылки сохраняются, а ссылки на `.md`-страницы и `{#anchor}` должны
разрешаться строго. Raw HTML, MDX JSX/import/export, admonitions, setext/H5/H6 и
неизвестные fenced-code languages не поддерживаются и не молча теряются.

### Цепочки преобразования

- `wiki.qsp.org → HTML`: существующий `download` сохраняет страницу/asset corpus в
  `.build/wiki`; `prepare` и `anchors` дают CHM; `spa` и `pwa` используют ту же модель;
  `docusaurus` генерирует отдельное `.md`-дерево из wiki HTML.
- `Docusaurus Markdown → CHM/SPA/PWA`: `markdown-sync` → `markdown-validate` →
  `markdown-build --target …` в отдельные `.build/docusaurus_markdown/*`.
- `Docusaurus Markdown → DokuWiki`: отдельного генератора DokuWiki в этом репозитории нет.
  Экспериментальный `docu_at_wiki/qspdocuwiki` использовался только как внешний образец;
  важные архитектурные решения и исторические caveats см. в [`hist/project-context.md`](hist/project-context.md).

Статические ресурсы (`default.css` и пр.) лежат в `assets/` и при сборке копируются
в выходные папки из разных источников: `assets/chm` → `.build/chm` (ключ `[chm].res`),
`assets/spa` → `.build/spa` и `docs` (ключ `[spa].res`). CSS одностраничника и CSS CHM — разные файлы.
Docusaurus-выход оформлением не управляет: стилизует дерево сам сайт на Docusaurus.
В PWA wiki-root-absolute `url()` из CSS (`/lib/…` — декоративные иконки DokuWiki, которых нет
в офлайн-корпусе) переписываются на живой `https://wiki.qsp.org/…` — онлайн декорации
дотягиваются с оригинала, офлайн graceful исчезают (контент остаётся).

Настройки (папки src/out/images/ресурсов, base_url, кодировки, исключаемые разделы, уровень
лога) — единственные и только в [`qsp_help.toml`](qsp_help.toml). Файл обязателен:
значений по умолчанию в коде нет.

Зависимости: `pip install -r requirements.txt` (включая requests, beautifulsoup4, lxml,
markdown-it-py, mdit-py-plugins и PyYAML).

## Этапы сборки

1. Выгрузка исходных html-файлов с [wiki.qsp.org](https://wiki.qsp.org) — `download`.
2. Подготовка файлов для CHM (htm-страницы + `qsp.hhc`/`qsp.hhk`) — `prepare`.
3. Извлечение актуальных якорей из собранного `.build/chm` — `anchors` (для повторных сборок).
4. Сборка одностраничника (`spa`), PWA (`pwa`) или Docusaurus-дерево (`docusaurus`) — независимые выходы, использующие тот же корпус `.build/wiki`.
5. Компиляция `.chm` программой **HTML Help Workshop** — внешний инструмент, не автоматизирован.

## Первый этап. Выгрузка страниц (`download`)

1. `python -m qsp_help_builder download` — выгрузит все страницы справки и изображения.
   Изображения DokuWiki (`lib/exe/fetch.php?media=…`) сохраняются под корректными
   именами: base-имя берётся из значения `media` (`namespace:file` → `namespace_file`),
   а не схлопывается в одно `fetch.png`.
2. Страницы и изображения сохранятся в `.build/wiki` (картинки — в `.build/wiki/images`).
3. Там же появится `urls_links_to_files.json` — связка прямых url ↔ файлов.
4. `.build/` — локальные рабочие данные, они не попадают в Git. После удаления
   скачанный корпус можно восстановить командой `download`, а последовательность
   `all` заново подготовит CHM-файлы и обновит `.build/wiki/anchors.json`.

> **Ре-краул и baseline.** `download` перезаписывает `.build/wiki` целиком: вики
> отдаёт per-request токены (`sec`/`tok`/`rev`), поэтому байты исходников меняются
> при каждом скачивании — это ожидаемо. Действующий зафиксированный снимок
> состояния — [`_baseline/2026-10-17/BASELINE.md`](_baseline/2026-10-17/BASELINE.md);
> проверки приёмки — через `python _baseline/make_manifest.py` (SHA256-манифесты
> `.build/wiki`/`.build/chm`). Старый `_baseline/2026-10-16/` оставлен как история.

## Второй этап. Подготовка CHM (`prepare`)

1. `python -m qsp_help_builder prepare` — возьмёт скачанные `.build/wiki` и подготовит к сборке CHM.
2. Подготовленные файлы пересохранятся в `.build/chm` (кодировка страниц utf-8,
   `qsp.hhc`/`qsp.hhk` — windows-1251 по требованию HTML Help Workshop).
3. В `.build/chm` появятся `qsp.hhc` (содержание) и `qsp.hhk` (указатель).
4. Автоматически выполняются: исключение разделов навигатора/aqsp из `files` в
   `qsp_help.toml`, чистка ссылок и картинок, снятие «кликабельности» с изображений,
   удаление изображений-иконок, правки стартовой страницы, лог и ссылка на живую вики.
5. Указатель (`qsp.hhk`) строится автоматически: список ключевых слов берётся из
   таблицы `help_keywords`, а локальные адреса якорей — из `.build/wiki/anchors.json`
   (ручных правок в конфиге больше нет). Статичные ресурсы (`default.css`) копируются
   из `assets/…` (см. выше); прочие ассеты картинок в `.build/chm` (`qgen.png` и др.)
   укладываются вручную — `prepare` их не копирует.
6. Якоря переживают пересборку через `anchors.json`: `prepare` вставляет их из
   `.build/wiki/anchors.json` (согласованный 0-based индекс строки), а `python -m qsp_help_builder
   anchors` извлекает актуальные якоря обратно из собранного `.build/chm` (цикл замкнут;
   после ре-краула сходится до идемпотентной точки покоя за 2–3 итерации).

## Третий этап. Сборка справки

1. Потребуется [HTML Help Workshop](https://www.helpandmanual.com/downloads_mscomp.html) —
   установщик в папке `tools/html_help_workshop`.
2. Инструкция по созданию проекта скопирована в `tools/html_help_workshop` (в виде md).
3. Создаёте новый проект, добавляете нужные файлы (не забудьте отметить `Default file`),
   запускаете компиляцию.
4. Внимательно читайте ошибки компиляции.

## Что дальше?

- Распространяете полученный `chm` среди жильцов вашего ЖэКа;
- **одностраничник доступен**: `python -m qsp_help_builder spa` → автономный
  `.build/spa/index.html` (открывается двойным кликом с `file://`, hash-навигация,
  картинки в `.build/spa/images/`). Модель сайта общая для CHM/SPA/PWA/Docusaurus — ссылки и
  картинки готовит один профиль-абстракция, просто под разные целевые форматы;
- **PWA готов**: `python -m qsp_help_builder pwa` → `docs/` (то же, что SPA, плюс
  устанавливаемость, офлайн-кэш и клиентский поиск). Размещение — см. ниже.
- **Docusaurus-дерево готово**: `python -m qsp_help_builder docusaurus` → `.build/docusaurus_docs/` (иерархия
  `.md` по содержанию + `help_add/` для вне-содержания, JSON-базы для сохранения порядка/ссылок).

## Деплой PWA на GitHub Pages

1. `python -m qsp_help_builder pwa` — соберётся `docs/` (`index.html`, `sw.js`,
   `manifest.webmanifest`, `search.json`, `default.css`, `spa.css`, `images/`).
2. Закоммитьте `docs/` в рабочую ветку. GitHub Pages берёт папку `docs/` как корень
   сайта автоматически: в настройках репозитория (Settings → Pages) достаточно выбрать
   `Deploy from a branch` → эту ветку → `docs` (папка `/` определяется сама).
   Сайт будет в под-пути `https://<user>.github.io/<repo>/` — относительные пути
   в сборке корректны.
3. Первый визит — по `https://` (service worker не работает с `file://` и требует
   HTTPS); после первого визита справка доступна офлайн и устанавливается как приложение.

> Для повторной публикации достаточно пересобрать `pwa` и закоммитить `docs/`:
> `sw.js` сам меняет имя кэша по содержимому сборки, поэтому браузеры пользователей
> подтянут обновление без ручной инвалидации.

## Сборка разделов для Docusaurus

1. `python -m qsp_help_builder docusaurus` — соберётся дерево `.md` в `[docusaurus].out`
   (по умолчанию `.build/docusaurus_docs`): содержание — в `qsp_wiki/` (вложенность папок =
   уровням TOC), страницы вне содержания и служебные (`help_keywords`) — в `help_add/`.
2. Эта папка — `docs.path` в `docusaurus.config.js`; сайдбар собирается самим Docusaurus
   из метаданных (`_category_.json` у папок, `sidebar_position`/`sidebar_label` в
   front matter файлов), отдельный `sidebars.js` не нужен.
3. Картинки коллоцируются рядом с документом, который их использует (отдельной папки
   картинок в `docs.path` нет — иначе Docusaurus превратил бы её в раздел); дубликаты
   одной картинки в разных папках допустимы и осознанны.
4. Порядок и цели ссылок переживают пересборку в мутируемых JSON-базах
   `[docusaurus].bases` (`numbering.json`/`links.json`, по умолчанию
   `.build/docusaurus_docs/.docusaurus_build`) — их **нельзя удалять и перемещать**: при переезде
   документа база помнит прежний адрес, а ручная правка чисел в `_category_.json` /
   `sidebar_position` следующая сборка перезапишет.
5. Пересборка пишет дерево заново (старые `.md`/`.mdx` и папки удаляются, базы остаются),
   поэтому переезд раздела не оставляет устаревших дублей.

## Тесты

`python -m pytest` — регрессионные тесты конвейера (`tests/`, 103 теста):
нейтральная модель сайта, профили целей, рендереры CHM/SPA/PWA/Docusaurus,
загрузчик (краулер), якоря, CLI и идемпотентность ссылок.

**TODO:**

- [x] автоматически удалять ненужные файлы
- [x] автоматически очищать изображения от "кликабельности"
- [x] автоматически исправлять кривые ссылки на изображения
   - [x] изображения скачиваются корректными именами (base из `media=`, Фаза 6);
   - [x] изображение интерфейса QGen разрешается штатно (`qgen.png`);
   - [x] устаревшие ручные редиректы указателя `qsp.hhk` убраны из конфига
     (`[chm.keyword_overrides]` удалён; адреса берутся из `anchors.json`).
- [x] автоматически добавлять на стартовую страницу лого
- [x] автоматически удалять ссылку на указатель в содержании
- [x] автоматически удалять изображения с классом icon
- [x] автоматически исправлять сноски
- [x] автоматически исключать разделы по навигатору и aqsp
- [x] удалить из вики блок про компилируемую версию справки, а в эту встраивать ссылку на вики
- [x] **Собрать все этапы в один скрипт. Почитсить от мусора.** (единая точка входа
      `python -m qsp_help_builder`, старые скрипты `qsp_wiki_downloader/` и `chm_prepare/` удалены)
- [x] **Автономный одностраничник** (`spa`): модель сайта + профили целей (CHM/SPA),
      `.build/spa/index.html` + `images/`, CHM-путь сохранён побайтово (Фаза 7)
- [x] **PWA** (`pwa`): `render/pwa` — манифест + service worker (precache) + клиентский
      поиск (свой индекс из Python); единый ассет-пайплайн `url()` в CSS переписывает
      декоративные `/lib/…` на живую вики (закрыт handoff §4.13). CHM-путь не сдвинут (Фаза 8)
- [x] **Docusaurus** (`docusaurus`): `render/docusaurus` — извлечение содержания из sidebar,
      раскладка по папкам `.md` (вне содержания → `help_add/`), `_category_.json`/`sidebar_position`
      + JSON-базы для переживания пересборки (`[docusaurus].bases`). CHM-путь не затронут (Фаза 9)

## P.S.!!!

> [!important] **Важно!!!**
> Здесь не описаны все ошибки, которые могут вылезти при работе скриптов и HTML Help
> Workshop. При возникновении проблем проверьте сообщения CLI, тесты и соответствующий
> код. Исторические архитектурные решения собраны в [`hist/project-context.md`](hist/project-context.md).
