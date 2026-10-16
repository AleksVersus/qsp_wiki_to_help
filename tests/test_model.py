# pyright: reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportArgumentType=false
"""Тесты нейтральной модели сайта (Фаза 7).

Офлайн на маленькой фикстуре html_src: проверка, что один и тот же контент,
прогнанный через prepare-примитивы с разными профилями, даёт CHM-цели
(``file.htm#anchor`` / голое имя картинки) и SPA-цели (``#slug~anchor`` /
``images/имя``). Сеть не трогаем.
    python -m pytest tests/test_model.py -v
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
from qsp_help_builder.render.profile import ChmProfile, SpaProfile

BASE_URL = "https://wiki.qsp.org"


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
        res_chm=tmp_path / "_res_src" / "chm",
        res_spa=tmp_path / "_res_src" / "spa",
    )
    chm = ChmSettings("sidebar.htm", "help_keywords.htm", "qsp.hhc", "qsp.hhk", "utf-8", "windows-1251")
    log = LoggingSettings("DEBUG", tmp_path / "dl.log")
    return Settings(tmp_path / "qsp_help.toml", wiki, paths, SpaSettings("start"), chm, frozenset(), log)


def seed_inputs(settings: Settings, page_html: str) -> None:
    """Пишет страницу help_coding.html + scheme (страница и картинка) + пустой anchors."""
    src = settings.paths.src
    write_text(src / "help_coding.html", page_html, "utf-8")
    save_json(
        {
            "pages": {f"{BASE_URL}/help:coding": r"html_src\help_coding.html"},
            "images": {f"{BASE_URL}/_media/help:msgbox.png": r"html_src\images\help_msgbox.png"},
        },
        settings.paths.scheme,
    )
    save_json({}, settings.paths.anchors)


PAGE_HTML = f"""<html><head><title>Функции</title></head><body>
<div class="page group">
  <h2 id="funkcii">Функции</h2>
  <p><a href="{BASE_URL}/help:coding#funkcii">на якорь</a></p>
  <p><img src="{BASE_URL}/_media/help:msgbox.png"></p>
</div></body></html>"""


def test_build_site_model_slug_title_and_skip_excluded(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed_inputs(settings, PAGE_HTML)
    model = build_site_model(settings, ChmProfile())
    assert [p.slug for p in model.pages] == ["help_coding"]
    assert model.pages[0].title == "Функции"
    assert model.by_slug["help_coding"] is model.pages[0]


def test_chm_profile_resolves_to_htm_and_bare_image(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed_inputs(settings, PAGE_HTML)
    model = build_site_model(settings, ChmProfile())
    html = str(model.pages[0].fragment)
    assert 'href="help_coding.htm#funkcii"' in html
    assert 'src="help_msgbox.png"' in html
    assert model.referenced_images() == {"help_msgbox.png"}


def test_spa_profile_resolves_to_hash_and_images_dir(tmp_path: Path):
    settings = make_settings(tmp_path)
    seed_inputs(settings, PAGE_HTML)
    model = build_site_model(settings, SpaProfile())
    html = str(model.pages[0].fragment)
    assert 'href="#help_coding~funkcii"' in html
    assert 'src="images/help_msgbox.png"' in html
    # базовое имя картинки для манифеста совпадает с CHM
    assert model.referenced_images() == {"help_msgbox.png"}


# --------------------------------------------------------------- профили (чистые)

def test_chm_profile_internal_target_matches_legacy_replace():
    prof = ChmProfile()
    assert prof.internal_target("help_coding.html#x", BASE_URL) == ("help_coding.htm#x", False)
    # ИСТОРИК: '.html' вырезается во всей строке
    assert prof.internal_target("help_coding.html?do=export_html", BASE_URL) == (
        "help_coding.htm?do=export_html",
        False,
    )
    # нераспознанная вики-ссылка остаётся абсолютной без _blank
    assert prof.internal_target(f"{BASE_URL}/help:nowhere", BASE_URL) == (
        f"{BASE_URL}/help:nowhere",
        False,
    )


def test_spa_profile_internal_target_slug_and_external():
    prof = SpaProfile()
    assert prof.internal_target("help_coding.html#x", BASE_URL) == ("#help_coding~x", False)
    assert prof.internal_target("help_coding.html", BASE_URL) == ("#help_coding", False)
    assert prof.internal_target("help_coding.html?do=export_html", BASE_URL) == ("#help_coding", False)
    # нераспознанная вики-ссылка -> наружу (новая вкладка)
    assert prof.internal_target(f"{BASE_URL}/help:nowhere", BASE_URL) == (
        f"{BASE_URL}/help:nowhere",
        True,
    )


def test_spa_profile_image_href_prefix():
    assert SpaProfile().image_href("pic.png") == "images/pic.png"
    assert ChmProfile().image_href("pic.png") == "pic.png"
