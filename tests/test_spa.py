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
from qsp_help_builder.model import build_site_model
from qsp_help_builder.prepare.page_clean import wrap_into_template
from qsp_help_builder.render.profile import SpaProfile
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
        res_chm=tmp_path / "_res_src" / "chm",
        res_spa=tmp_path / "_res_src" / "spa",
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
    (settings.paths.out).mkdir(parents=True, exist_ok=True)
    (settings.paths.out / "help_wiki_logo.png").write_bytes(b"\x89PNG\r\n\x1a\nlogo")
    # css SPA теперь из своего дерева ресурсов (_res_src/spa), НЕ из html_out
    write_text(settings.paths.res_spa / "default.css", ".spa-marker{}", "utf-8")
    write_text(settings.paths.res_spa / "spa.css", ".spa-layout-marker{}", "utf-8")
    # html_out-css с другим содержимым: SPA не должен его подхватить
    write_text(settings.paths.out / "default.css", ".chm-marker{}", "utf-8")


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


def test_render_spa_css_comes_from_res_spa(tmp_path: Path):
    # spa-ресурсы копируются из _res_src/spa, а не из html_out (css теперь разные)
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_spa(settings)

    assert (settings.paths.spa / "default.css").read_text(encoding="utf-8") == ".spa-marker{}"


def test_render_spa_two_panel_layout(tmp_path: Path):
    # двухпанельный каркас: dokuwiki-обёртка контента, вкладки, отдельный spa.css
    settings = make_settings(tmp_path)
    seed(tmp_path, settings)
    render_spa(settings)

    index = (settings.paths.spa / "index.html").read_text(encoding="utf-8")
    # контент оформляется стилями DokuWiki -> body размечен классом dokuwiki
    assert 'class="dokuwiki"' in index
    # layout-стили подключены вторым файлом и скопированы в выход
    assert 'href="spa.css"' in index
    assert (settings.paths.spa / "spa.css").read_text(encoding="utf-8") == ".spa-layout-marker{}"
    # две вкладки левой панели + мобильный бар (data-tab на кнопках)
    assert 'data-tab="toc"' in index and 'data-tab="index"' in index
    # сворачивание/закрытие панели и оверлея
    assert 'id="toggleBtn"' in index and 'id="closeBtn"' in index


def _wrapped_line_of(settings: Settings, slug: str, marker: str) -> int:
    """0-based номер строки маркера в обёрнутой странице — тот же отсчёт, что у CHM.

    anchors.json хранит строки, измеренные на тексте ``wrap_into_template``; чтобы
    фикстура была точной, вычисляем индекс тем же способом, а не гадаем.
    """
    model = build_site_model(settings, SpaProfile())
    page = model.by_slug[slug]
    text = wrap_into_template(page.source_soup, page.fragment)
    for idx, line in enumerate(text.split("\n")):
        if marker in line:
            return idx
    raise AssertionError(f"маркер {marker!r} не найден в обёрнутой {slug}")


def test_render_spa_injects_anchors_and_builds_index(tmp_path: Path):
    # указатель: порядок/состав из таблицы help_keywords, цели — из anchors.json;
    # сам якорь вставляется в контент по номеру строки (как в CHM) и namespace'ится.
    settings = make_settings(tmp_path)
    src = settings.paths.src
    write_text(
        src / "start.html",
        '<html><head><title>Старт</title></head><body><div class="page group">'
        '<h1>Дом</h1></div></body></html>',
        "utf-8",
    )
    write_text(
        src / "help_acts.html",
        '<html><head><title>Действия</title></head><body><div class="page group">\n'
        '<h1>Действия</h1>\n'
        '<p>ACT - создать действие</p>\n'
        '</div></body></html>',
        "utf-8",
    )
    write_text(
        src / "help_keywords.html",
        f'<html><head><title>Ключи</title></head><body><div class="page group">'
        f'<table class="inline">'
        f'<tr class="row0"><td class="col0"><strong>ключевое слово</strong></td>'
        f'<td class="col1"><strong>назначение</strong></td></tr>'
        f'<tr class="row1"><td class="col0"><a href="{BASE_URL}/help:acts">ACT</a></td>'
        f'<td class="col1">Создать действие</td></tr>'
        f'<tr class="row2"><td class="col0">x ADDLIB</td>'
        f'<td class="col1">не поддерживается</td></tr>'
        f'</table></div></body></html>',
        "utf-8",
    )
    write_text(
        src / "sidebar.html",
        f'<html><head><title>Нав</title></head><body><div class="page group">'
        f'<ul><li><a href="{BASE_URL}/help:acts">Действия</a></li></ul></div></body></html>',
        "utf-8",
    )
    save_json(
        {
            "pages": {
                f"{BASE_URL}/help:acts": r"html_src\help_acts.html",
                f"{BASE_URL}/help:keywords": r"html_src\help_keywords.html",
            },
            "images": {},
        },
        settings.paths.scheme,
    )
    save_json({}, settings.paths.anchors)  # временный — нужен для build_site_model ниже

    line = _wrapped_line_of(settings, "help_acts", "<p>")
    save_json({"help_acts": {"statement_ACT": [line, "ACT"]}}, settings.paths.anchors)

    render_spa(settings)
    index = (settings.paths.spa / "index.html").read_text(encoding="utf-8")

    # блок указателя стоит между навигацией и контентом
    assert 'id="index"' in index
    assert index.index('id="toc"') < index.index('id="index"') < index.index('id="content"')
    # ссылка указателя: текст из help_keywords, цель (slug~anchor) из anchors.json
    assert '<a href="#help_acts~statement_ACT">ACT</a>' in index
    # ключ без якоря в anchors.json (ADDLIB) в указатель не попадает
    assert "ADDLIB" not in index[index.index('id="index"'):index.index('id="content"')]
    # сам якорь вставлен в контент по номеру строки и отnamespace'ен -> ссылка резолвится
    assert 'id="help_acts~statement_ACT"' in index
