# pyright: reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Тесты рендерера Docusaurus (режим docs).

Офлайн на маленькой фикстуре: проверяем, что render_docusaurus раскладывает
.mdx по папкам согласно уровням содержания, страницы вне содержания кладёт в
help_add/, ссылки/картинки делает относительными от файла, порядок пишет через
атрибуты Docusaurus, а JSON-базы (numbering/links) переживают пересборку.
    python -m pytest tests/test_docusaurus.py -v
"""

import json
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup, Tag

from qsp_help_builder.config import (
    ChmSettings,
    DocusaurusSettings,
    LoggingSettings,
    PathSettings,
    Settings,
    SpaSettings,
    PwaSettings,
    WikiSettings,
)
from qsp_help_builder.fs_utils import save_json, write_text
from qsp_help_builder.render.docusaurus import render_docusaurus
from qsp_help_builder.render.docusaurus.convert import ConvertContext, render_body
from qsp_help_builder.render.docusaurus.toc import HELP_ADD_DIR, WIKI_DIR, slugify_cyr

BASE_URL = "https://wiki.qsp.org"
PROGRAMMING = slugify_cyr("Программирование")  # имя папки категории (транслит)
WIKI = WIKI_DIR  # корень дерева содержания внутри выхода


def make_settings(tmp_path: Path) -> Settings:
    wiki = WikiSettings(BASE_URL, 5.0, 0.0, "ua")
    paths = PathSettings(
        root=tmp_path,
        src=tmp_path / "html_src",
        out=tmp_path / "html_out",
        images=tmp_path / "html_src" / "images",
        scheme=tmp_path / "html_src" / "urls_links_to_files.json",
        anchors=tmp_path / "html_src" / "anchors.json",
        spa=tmp_path / "spa_out",
        pwa=tmp_path / "pwa_out",
        docusaurus=tmp_path / "docusaurus_docs",
        docusaurus_bases=tmp_path / "docusaurus_docs" / ".docusaurus_build",
        res_chm=tmp_path / "_res_src" / "chm",
        res_spa=tmp_path / "_res_src" / "spa",
    )
    chm = ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251")
    log = LoggingSettings("DEBUG", tmp_path / "dl.log")
    pwa = PwaSettings("start", "QSP", "QSP", "#2f6db0", "#f4f5f7", "standalone", "images/logo.png")
    return Settings(
        tmp_path / "qsp_help.toml", wiki, paths, SpaSettings("start"), pwa,
        DocusaurusSettings("start"), chm, frozenset(), log
    )


def _page(title: str, body: str) -> str:
    return (
        f'<html><head><title>{title}</title></head><body><div class="page group">'
        f"{body}</div></body></html>"
    )


def _li(level: int, inner: str, sub: str = "") -> str:
    return f'<li class="level{level}"><div class="li">{inner}</div>{sub}</li>'


def seed(tmp_path: Path, settings: Settings, extra_toc: str = "") -> None:
    src = settings.paths.src
    # start — корневой док + картинка; help_coding — под категорией; help_strings —
    # родитель-с-детьми; help_regexp — его ребёнок; help_extra — вне содержания.
    write_text(src / "start.html", _page(
        "В начало [Документация QSP]",
        f'<h1 id="gl">Дом</h1><p>a {{b}} c</p>'
        f'<p><img src="{BASE_URL}/_media/help:msgbox.png"></p>'
        f'<p><a href="{BASE_URL}/help:keywords">Указатель</a></p>',
    ), "utf-8")
    write_text(src / "help_coding.html", _page(
        "Код [Документация QSP]",
        f'<h2 id="aa">Структура</h2>'
        f'<p><a href="{BASE_URL}/help:regexp">Регэкспы</a> и '
        f'<a href="{BASE_URL}/help:coding#aa">на себя</a> и '
        f'<a href="https://example.com">внешняя</a></p>',
    ), "utf-8")
    write_text(src / "help_strings.html", _page("Строки [Документация QSP]", "<p>строки</p>"), "utf-8")
    write_text(src / "help_regexp.html", _page("Регэкспы [Документация QSP]", "<p>regex</p>"), "utf-8")
    write_text(src / "help_extra.html", _page("Лишнее [Документация QSP]", "<p>нет ссылки из TOC</p>"), "utf-8")
    # help_keywords — есть в TOC, но принудительно уезжает в help_add (HELP_ADD_ONLY_SLUGS)
    write_text(src / "help_keywords.html", _page(
        "Ключевые слова. Указатель [Документация QSP]",
        f'<p>указатель: <a href="{BASE_URL}/help:coding">Код</a></p>',
    ), "utf-8")

    regexp_li = _li(3, f'<a href="{BASE_URL}/help:regexp">Регэкспы</a>')
    strings_sub = f'<ul>{regexp_li}</ul>'
    category_sub = (
        '<ul>'
        + _li(2, f'<a href="{BASE_URL}/help:coding">Код</a>')
        + _li(2, f'<a href="{BASE_URL}/help:strings">Строки</a>', strings_sub)
        + '</ul>'
    )
    write_text(src / "sidebar.html", _page(
        "Нав",
        '<ul>'
        + _li(1, "<strong>Программирование</strong>", category_sub)
        + _li(1, f'<a href="{BASE_URL}/start">В начало</a>')
        + _li(1, f'<a href="{BASE_URL}/help:keywords">Ключевые слова</a>')
        + extra_toc
        + '</ul>',
    ), "utf-8")

    save_json(
        {
            "pages": {
                f"{BASE_URL}/start": r"html_src\start.html",
                f"{BASE_URL}/help:coding": r"html_src\help_coding.html",
                f"{BASE_URL}/help:strings": r"html_src\help_strings.html",
                f"{BASE_URL}/help:regexp": r"html_src\help_regexp.html",
                f"{BASE_URL}/help:extra": r"html_src\help_extra.html",
                f"{BASE_URL}/help:keywords": r"html_src\help_keywords.html",
            },
            "images": {f"{BASE_URL}/_media/help:msgbox.png": r"html_src\images\help_msgbox.png"},
        },
        settings.paths.scheme,
    )
    save_json({}, settings.paths.anchors)
    (settings.paths.images).mkdir(parents=True, exist_ok=True)
    (settings.paths.images / "help_msgbox.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")


def _read(settings: Settings, rel: str) -> str:
    return (settings.paths.docusaurus / rel).read_text(encoding="utf-8")


def test_layout_by_toc_levels(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    out = settings.paths.docusaurus

    # категория -> папка; ссылка без детей -> .mdx внутри неё (всё — внутри qsp_wiki/)
    assert (out / WIKI / PROGRAMMING / "help_coding.mdx").is_file()
    # родитель-с-детьми -> папка по slug, индекс-док внутри + ребёнок рядом
    assert (out / WIKI / PROGRAMMING / "help_strings" / "help_strings.mdx").is_file()
    assert (out / WIKI / PROGRAMMING / "help_strings" / "help_regexp.mdx").is_file()
    # корневая ссылка -> файл в корне раздела содержания
    assert (out / WIKI / "start.mdx").is_file()
    # в корне выхода больше нет документов содержания (ушли в qsp_wiki/)
    assert not (out / "start.mdx").exists()
    assert not (out / PROGRAMMING).exists()
    # sidebar как контент не пишется
    assert not (out / "sidebar.mdx").exists()


def test_off_toc_pages_go_to_help_add(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    # help_add остаётся в корне выхода (не внутри qsp_wiki)
    assert (settings.paths.docusaurus / HELP_ADD_DIR / "help_extra.mdx").is_file()
    assert not (settings.paths.docusaurus / WIKI / HELP_ADD_DIR).exists()


def test_help_keywords_forced_to_help_add(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    out = settings.paths.docusaurus
    # help_keywords есть в TOC, но принудительно уезжает в help_add, а не в дерево
    assert (out / HELP_ADD_DIR / "help_keywords.mdx").is_file()
    assert not (out / WIKI / "help_keywords.mdx").exists()
    assert not (out / "help_keywords.mdx").exists()
    assert not (out / "help_keywords.mdx_").exists()  # не переименовывается
    # ссылка с help_keywords на документ дерева (help:coding) резолвится в qsp_wiki
    kw = _read(settings, f"{HELP_ADD_DIR}/help_keywords.mdx")
    assert "../qsp_wiki/programmirovanie/help_coding.mdx" in kw
    # ссылка из дерева (start) на help_keywords резолвится в help_add
    start = _read(settings, f"{WIKI}/start.mdx")
    assert "../help_add/help_keywords.mdx" in start


def test_wiki_root_category_json(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    # корневой раздел содержания получает метку и позицию (иначе — сырое имя qsp_wiki)
    cat = json.loads(_read(settings, f"{WIKI}/_category_.json"))
    assert cat["label"] == "QSP-Wiki"
    assert cat["position"] == 1


def test_category_json_with_doc_index(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    cat = json.loads(_read(settings, f"{WIKI}/{PROGRAMMING}/help_strings/_category_.json"))
    assert cat["label"] == "Строки"
    assert isinstance(cat["position"], int)
    assert cat["link"]["type"] == "doc"
    # id — относительная ссылка на индекс-док от папки категории, без расширения
    assert cat["link"]["id"] == "help_strings"
    # чистая категория (без индекс-дока) не имеет link.type==doc
    top = json.loads(_read(settings, f"{WIKI}/{PROGRAMMING}/_category_.json"))
    assert "link" not in top


def test_relative_links_and_images(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)

    coding = _read(settings, f"{WIKI}/{PROGRAMMING}/help_coding.mdx")
    # rel от папки help_coding к ребёнку help_strings
    assert "help_strings/help_regexp.mdx" in coding
    # якорь на себя: тот же файл + #aa
    assert "help_coding.mdx#aa" in coding
    # внешняя — абсолют
    assert "[внешняя](https://example.com)" in coding
    # картинка коллоцируется рядом с документом: start в qsp_wiki -> голое имя foo.png,
    # файл лежит в той же папке; центрального img/ на выходе больше нет
    start = _read(settings, f"{WIKI}/start.mdx")
    assert "](help_msgbox.png)" in start
    assert (settings.paths.docusaurus / WIKI / "help_msgbox.png").is_file()
    assert not (settings.paths.docusaurus / "img").exists()


def test_mdx_braces_escaped_and_frontmatter(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    start = _read(settings, f"{WIKI}/start.mdx")
    assert start.startswith("---")
    assert 'title: "В начало"' in start
    assert "sidebar_position: 1" in start  # старт — первым в корне
    assert "a &#123;b&#125; c" in start  # литеральные фигурные скобки экранированы


def test_title_marker_stripped(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    # метка «[Документация QSP]» убирается из title во front-matter
    coding = _read(settings, f"{WIKI}/{PROGRAMMING}/help_coding.mdx")
    assert 'title: "Код"' in coding
    assert "Документация QSP" not in coding.split("# ")[0]  # в front-matter метки нет


def test_positions_are_per_folder_and_interleaved(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    # корень: старт promoted вперёд -> 1, папка-категория -> 2 (доки и папки
    # нумеруются вместе, поэтому категория идёт сразу после старта, а не в хвосте)
    root_start_pos = _frontmatter_position(_read(settings, f"{WIKI}/start.mdx"))
    assert root_start_pos == 1
    prog_cat = json.loads(_read(settings, f"{WIKI}/{PROGRAMMING}/_category_.json"))
    assert prog_cat["position"] == 2
    # внутри категории доки/подпапки — своя нумерация с 1: help_coding=1, подпапка help_strings=2
    coding_pos = _frontmatter_position(_read(settings, f"{WIKI}/{PROGRAMMING}/help_coding.mdx"))
    assert coding_pos == 1
    strings_cat = json.loads(_read(settings, f"{WIKI}/{PROGRAMMING}/help_strings/_category_.json"))
    assert strings_cat["position"] == 2
    # индекс-док категории = 1, ребёнок help_regexp получает свой порядок внутри папки
    regexp_pos = _frontmatter_position(_read(settings, f"{WIKI}/{PROGRAMMING}/help_strings/help_regexp.mdx"))
    assert regexp_pos == 1


def test_bases_persist_stored_overrides_computed(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    bases = settings.paths.docusaurus_bases
    numbering_first = json.loads((bases / "numbering.json").read_text(encoding="utf-8"))
    links = json.loads((bases / "links.json").read_text(encoding="utf-8"))
    assert links["help_extra"] == f"{HELP_ADD_DIR}/help_extra"

    # пересборка без изменений -> позиции стабильны
    render_docusaurus(settings)
    numbering_same = json.loads((bases / "numbering.json").read_text(encoding="utf-8"))
    assert numbering_same == numbering_first

    # ручная правка позиции в numbering.json имеет приоритет над вычисленной
    numbering_first[f"{WIKI}/start.mdx"]["position"] = 99
    save_json(numbering_first, bases / "numbering.json")
    render_docusaurus(settings)
    after = json.loads((bases / "numbering.json").read_text(encoding="utf-8"))
    assert after[f"{WIKI}/start.mdx"]["position"] == 99
    assert _frontmatter_position(_read(settings, f"{WIKI}/start.mdx")) == 99

    # новый узел (перенос help_extra из help_add в корень TOC): ключ отсутствует в
    # базе -> получает вычисленный TOC-порядок внутри корня (после start=99-го и
    # категории=2-го), то есть следующий свободный слот корня = 3.
    seed(tmp_path, settings, extra_toc=_li(1, f'<a href="{BASE_URL}/help:extra">Лишнее</a>'))
    render_docusaurus(settings)
    numbering2 = json.loads((bases / "numbering.json").read_text(encoding="utf-8"))
    assert f"{WIKI}/help_extra.mdx" in numbering2  # ключ появился по новому пути
    new_pos = int(numbering2[f"{WIKI}/help_extra.mdx"]["position"])
    assert new_pos == 3


def _frontmatter_position(mdx: str) -> int:
    for line in mdx.split("---")[1].splitlines():
        if line.startswith("sidebar_position:"):
            return int(line.split(":", 1)[1].strip())
    raise AssertionError("sidebar_position не найден во front-matter")


def test_code_block_in_list_item_breaks_onto_own_lines():
    # <pre> внутри <li> (типично для DokuWiki): границы fenced-кода обязаны
    # вставать на отдельные строки с отступом-продолжением пункта, иначе
    # Docusaurus не распознает блок и роняет сборку.
    frag = BeautifulSoup(
        '<div class="page group"><ul>'
        '<li class="level1"><div class="li">Отступы кода: '
        '<pre class="brush: qsp">\n*p 1\n  *p 2\n</pre></div></li>'
        "</ul></div>",
        "html.parser",
    ).find("div")
    assert isinstance(frag, Tag)
    ctx = ConvertContext(src_dir=PurePosixPath("."), links={}, img_dir=PurePosixPath("img"))
    out = render_body(frag, ctx)
    assert "- Отступы кода:\n\n  ```qsp\n  *p 1\n    *p 2\n  ```" in out
