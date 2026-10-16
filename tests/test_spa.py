# pyright: reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Тесты рендерера-одностраничника (Фаза 7).

Офлайн на маленькой фикстуре: проверка, что render_spa собирает единый
index.html с секциями по слагам, навигацией из sidebar, namespace-якорями
``id="{slug}~X"`` и копированием картинок в images/. Сеть не трогаем.
    python -m pytest tests/test_spa.py -v
"""

from pathlib import Path

from qsp_help_builder.config import (
    ChmSettings,
    LoggingSettings,
    PathSettings,
    Settings,
    SpaSettings,
    WikiSettings,
)
from qsp_help_builder.fs_utils import save_json, write_text
from qsp_help_builder.render.spa import render_spa

BASE_URL = "https://wiki.qsp.org"


def make_settings(tmp_path: Path, start_page: str = "start") -> Settings:
    wiki = WikiSettings(BASE_URL, 5.0, 0.0, "ua")
    paths = PathSettings(
        root=tmp_path,
        src=tmp_path / "html_src",
        out=tmp_path / "html_out",
        images=tmp_path / "html_src" / "images",
        scheme=tmp_path / "html_src" / "urls_links_to_files.json",
        anchors=tmp_path / "html_src" / "anchors.json",
        spa=tmp_path / "spa_out",
    )
    chm = ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251")
    log = LoggingSettings("DEBUG", tmp_path / "dl.log")
    return Settings(
        tmp_path / "qsp_help.toml", wiki, paths, SpaSettings(start_page), chm, frozenset(), log
    )


def seed(tmp_path: Path, settings: Settings) -> None:
    src = settings.paths.src
    write_text(
        src / "start.html",
        f'<html><head><title>Старт</title></head><body><div class="page group">'
        f'<h1>Добро пожаловать</h1>'
        f'</div></body></html>',
        "utf-8",
    )
    write_text(
        src / "help_coding.html",
        f'<html><head><title>Код</title></head><body><div class="page group">'
        f'<h2 id="funkcii">Функции</h2>'
        f'<p><a href="{BASE_URL}/help:coding#funkcii">на себя</a></p>'
        f'<p><img src="{BASE_URL}/_media/help:msgbox.png"></p>'
        f'<p><img src="help_wiki_logo.png"></p>'
        f'</div></body></html>',
        "utf-8",
    )
    write_text(
        src / "sidebar.html",
        f'<html><head><title>Нав</title></head><body><div class="page group">'
        f'<ul><li><a href="{BASE_URL}/help:coding">Код</a></li></ul>'
        f'</div></body></html>',
        "utf-8",
    )
    save_json(
        {
            "pages": {f"{BASE_URL}/help:coding": r"html_src\help_coding.html"},
            "images": {f"{BASE_URL}/_media/help:msgbox.png": r"html_src\images\help_msgbox.png"},
        },
        settings.paths.scheme,
    )
    save_json({}, settings.paths.anchors)
    # реальная картинка-источник и css для шага копирования ассетов
    (settings.paths.images).mkdir(parents=True, exist_ok=True)
    (settings.paths.images / "help_msgbox.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    # легаси-логотип: голым именем лежит в html_out (не в scheme), как в реальном CHM
    write_text(settings.paths.out / "default.css", "body{}", "utf-8")
    (settings.paths.out / "help_wiki_logo.png").write_bytes(b"\x89PNG\r\n\x1a\nlogo")


def test_render_spa_builds_index_with_sections_and_nav(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_spa(settings)

    index = (settings.paths.spa / "index.html").read_text(encoding="utf-8")
    # контент-страница — секция по слагу
    assert 'data-slug="help_coding"' in index
    # sidebar ушёл в навигацию, а не в контент-секции
    assert 'data-slug="sidebar"' not in index
    # hash-ссылка модели (#slug~anchor)
    assert 'href="#help_coding~funkcii"' in index
    # namespace id заголовка, чтобы #help_coding~funkcii резолвился
    assert 'id="help_coding~funkcii"' in index
    # картинки переведены в подпапку images/
    assert 'src="images/help_msgbox.png"' in index
    # легаси-логотип (голое имя мимо scheme) тоже уходит в images/
    assert 'src="images/help_wiki_logo.png"' in index


def test_render_spa_start_page_is_first_section(tmp_path: Path):
    # стартовая страница из конфига идёт первой секцией (её показывает router без хеша)
    settings = make_settings(tmp_path, start_page="start")
    seed(tmp_path, settings)
    render_spa(settings)

    index = (settings.paths.spa / "index.html").read_text(encoding="utf-8")
    assert index.index('data-slug="start"') < index.index('data-slug="help_coding"')


def test_render_spa_start_page_is_configurable(tmp_path: Path):
    # сменив start_page в конфиге, меняем первую секцию без правки кода
    settings = make_settings(tmp_path, start_page="help_coding")
    seed(tmp_path, settings)
    render_spa(settings)

    index = (settings.paths.spa / "index.html").read_text(encoding="utf-8")
    assert index.index('data-slug="help_coding"') < index.index('data-slug="start"')


def test_render_spa_copies_assets(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_spa(settings)

    assert (settings.paths.spa / "images" / "help_msgbox.png").is_file()
    assert (settings.paths.spa / "images" / "help_wiki_logo.png").is_file()
    assert (settings.paths.spa / "default.css").is_file()
