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
from qsp_help_builder.render.docusaurus.toc import HELP_ADD_DIR, slugify_cyr

BASE_URL = "https://wiki.qsp.org"
PROGRAMMING = slugify_cyr("Программирование")  # имя папки категории (транслит)


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
        "В начало",
        f'<h1 id="gl">Дом</h1><p>a {{b}} c</p>'
        f'<p><img src="{BASE_URL}/_media/help:msgbox.png"></p>',
    ), "utf-8")
    write_text(src / "help_coding.html", _page(
        "Код",
        f'<h2 id="aa">Структура</h2>'
        f'<p><a href="{BASE_URL}/help:regexp">Регэкспы</a> и '
        f'<a href="{BASE_URL}/help:coding#aa">на себя</a> и '
        f'<a href="https://example.com">внешняя</a></p>',
    ), "utf-8")
    write_text(src / "help_strings.html", _page("Строки", "<p>строки</p>"), "utf-8")
    write_text(src / "help_regexp.html", _page("Регэкспы", "<p>regex</p>"), "utf-8")
    write_text(src / "help_extra.html", _page("Лишнее", "<p>нет ссылки из TOC</p>"), "utf-8")

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

    # категория -> папка; ссылка без детей -> .mdx внутри неё
    assert (out / PROGRAMMING / "help_coding.mdx").is_file()
    # родитель-с-детьми -> папка по slug, индекс-док внутри + ребёнок рядом
    assert (out / PROGRAMMING / "help_strings" / "help_strings.mdx").is_file()
    assert (out / PROGRAMMING / "help_strings" / "help_regexp.mdx").is_file()
    # корневая ссылка -> файл в корне
    assert (out / "start.mdx").is_file()
    # sidebar как контент не пишется
    assert not (out / "sidebar.mdx").exists()


def test_off_toc_pages_go_to_help_add(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    assert (settings.paths.docusaurus / HELP_ADD_DIR / "help_extra.mdx").is_file()


def test_category_json_with_doc_index(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    cat = json.loads(_read(settings, f"{PROGRAMMING}/help_strings/_category_.json"))
    assert cat["label"] == "Строки"
    assert isinstance(cat["position"], int)
    assert cat["link"]["type"] == "doc"
    # id — относительная ссылка на файл индекс-дока от папки категории
    assert cat["link"]["id"] == "help_strings.mdx"
    # чистая категория (без индекс-дока) не имеет link.type==doc
    top = json.loads(_read(settings, f"{PROGRAMMING}/_category_.json"))
    assert "link" not in top


def test_relative_links_and_images(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)

    coding = _read(settings, f"{PROGRAMMING}/help_coding.mdx")
    # rel от папки help_coding к ребёнку help_strings
    assert "help_strings/help_regexp.mdx" in coding
    # якорь на себя: тот же файл + #aa
    assert "help_coding.mdx#aa" in coding
    # внешняя — абсолют
    assert "[внешняя](https://example.com)" in coding
    # картинка (start в корне) -> img/... и файл скопирован
    start = _read(settings, "start.mdx")
    assert "](img/help_msgbox.png)" in start
    assert (settings.paths.docusaurus / "img" / "help_msgbox.png").is_file()


def test_mdx_braces_escaped_and_frontmatter(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_docusaurus(settings)
    start = _read(settings, "start.mdx")
    assert start.startswith("---")
    assert 'title: "В начало"' in start
    assert "sidebar_position: 1" in start  # старт — первым в корне
    assert "a &#123;b&#125; c" in start  # литеральные фигурные скобки экранированы


def test_bases_persist_and_reuse_positions(tmp_path: Path):
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

    # новый узел в TOC (перенос help_extra из help_add в корень) -> позиция > прежнего максимума
    prev_max = max(int(e["position"]) for e in numbering_first.values())
    seed(tmp_path, settings, extra_toc=_li(1, f'<a href="{BASE_URL}/help:extra">Лишнее</a>'))
    render_docusaurus(settings)
    numbering2 = json.loads((bases / "numbering.json").read_text(encoding="utf-8"))
    new_pos = int(numbering2["./help_extra.mdx"]["position"])
    assert new_pos > prev_max


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
