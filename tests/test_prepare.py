# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownVariableType=false, reportArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportIndexIssue=false, reportOptionalSubscript=false
"""Тесты модулей prepare-этапа (Фаза 3).

Покрывают поведение, перенесённое 1:1 из ChmPrepare, особенно то, что легко
«случайно починить» и тем самым сдвинуть бейзлайн:
- футеры docInfo удаляются селектором 'div.docInfo' (§4.3 исправлено);
- нечёткое сопоставление src в replace_src без break — побеждает ПОСЛЕДНЕЕ
  совпадение;
- href ссылки, ушедшей на чужой домен, присваивается даже без замены;
- порядок атрибутов name/value в <param> hhc и hhk.
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from qsp_help_builder.anchors import AnchorEntry, Anchors
from qsp_help_builder.prepare import prepare_file
from qsp_help_builder.prepare.hhc import build_hhc, rebuild_hhc_ul
from qsp_help_builder.prepare.hhk import build_hhk, extract_hhk_data, href_compare
from qsp_help_builder.prepare.images import match_wiki_media_name, process_images, replace_src
from qsp_help_builder.prepare.links import replace_links
from qsp_help_builder.prepare.page_clean import apply_start_fixes, extract_page

BASE_URL = "https://wiki.qsp.org"


def make_scheme():
    """Мини-UrlScheme по контракту urls_links_to_files.json."""
    from qsp_help_builder.schema import UrlScheme
    return UrlScheme(
        pages={
            f"{BASE_URL}/help:coding": r"html_src\help_coding.html",
            f"{BASE_URL}/help:glossary": r"html_src\help_glossary.html",
        },
        images={
            f"{BASE_URL}/_media/help:msgbox.png": r"html_src\images\help_msgbox.png",
            f"{BASE_URL}/_media/other.png": r"html_src\images\other.png",
        },
    )


# ---------------------------------------------------------------- page_clean

DOKU_PAGE = """<html><head><title>Заголовок страницы</title></head><body>
<div class="page group">
  <h1>Текст</h1>
  <div class="toc" id="dw__toc"><a>содержание</a></div>
  <div class="docInfo"><span>последнее изменение</span></div>
  <script>var x = 1;</script>
  <p>полезный <a href="/help:coding">код</a></p>
</div></body></html>"""


def test_extract_page_removes_toc_scripts_and_docinfo():
    soup = BeautifulSoup(DOKU_PAGE, "lxml")
    page = extract_page(soup)
    text = str(page)
    assert "dw__toc" not in text
    assert "var x" not in text
    # §4.3: селектор 'div.docInfo' теперь корректно вырезает футер
    assert "последнее изменение" not in text
    assert "полезный" in text


def test_extract_page_missing_group_raises():
    soup = BeautifulSoup("<html><body><p>empty</p></body></html>", "lxml")
    with pytest.raises(ValueError, match="div.page.group"):
        extract_page(soup)


START_PAGE = """<html><head><title>s</title></head><body>
<div class="page group">
  <h1>QSP</h1>
  <a href="/help:keywords">ключевые слова</a>
  <h2 id="offlajn-versija">Онлайн-Версия</h2>
  <div><p>старое содержимое</p></div>
</div></body></html>"""


def test_apply_start_fixes_logo_keywords_and_online_block():
    soup = BeautifulSoup(START_PAGE, "lxml")
    page = extract_page(soup)
    apply_start_fixes(soup, page)
    out = str(page)
    assert 'src="help_wiki_logo.png"' in out
    # ссылка на keywords развёрнута в текст
    assert '/help:keywords' not in out
    assert "ключевые слова" in out
    # онлайн-блок переписан, target=_blank (его сохранит replace_links)
    assert 'href="https://wiki.qsp.org" target="_blank"' in out
    assert "старое содержимое" not in out


def test_wrap_into_template_moves_page_and_title():
    soup = BeautifulSoup(DOKU_PAGE, "lxml")
    page = extract_page(soup)
    from qsp_help_builder.prepare.page_clean import wrap_into_template
    out = wrap_into_template(soup, page)
    assert "<title>Заголовок страницы</title>" in out
    assert "полезный" in out
    assert 'href="default.css"' in out


# ---------------------------------------------------------------------- links

def test_replace_links_scheme_hit_with_anchor_tail():
    soup = BeautifulSoup(
        f'<div><a href="{BASE_URL}/help:coding#funkcii">ссылка</a></div>', "lxml")
    replace_links(soup.div, make_scheme(), BASE_URL)
    # '.html' -> '.htm' из имени scheme вырезается заменой ниже по коду
    assert soup.a["href"] == "help_coding.htm#funkcii"


def test_replace_links_unknown_wiki_url_becomes_absolute_unchanged():
    soup = BeautifulSoup(f'<div><a href="/help:nowhere">x</a></div>', "lxml")
    replace_links(soup.div, make_scheme(), BASE_URL)
    # ИСТОРИК: href присваивается даже без замены по scheme
    assert soup.a["href"] == f"{BASE_URL}/help:nowhere"
    assert "target" not in soup.a.attrs


def test_replace_links_foreign_domain_gets_new_tab():
    soup = BeautifulSoup('<div><a href="https://example.com/p">x</a></div>', "lxml")
    replace_links(soup.div, make_scheme(), BASE_URL)
    assert soup.a["href"] == "https://example.com/p"
    assert soup.a["target"] == "_blank"


def test_replace_links_skips_footnotes_and_blank_targets():
    soup = BeautifulSoup(
        '<div><a class="fn_bot" href="/a">1</a>'
        '<a href="/b" target="_blank">2</a></div>', "lxml")
    replace_links(soup.div, make_scheme(), BASE_URL)
    assert soup.find_all("a")[0]["href"] == "/a"
    assert soup.find_all("a")[1]["href"] == "/b"


def test_replace_links_html_to_htm_across_whole_string():
    # '.html' вырезается во всей строке, не только в хвосте — как старый replace
    soup = BeautifulSoup(
        f'<div><a href="{BASE_URL}/help:coding?do=export_html">x</a></div>', "lxml")
    replace_links(soup.div, make_scheme(), BASE_URL)
    assert ".html" not in soup.a["href"]


# ---------------------------------------------------------------------- images

def test_match_wiki_media_name():
    assert match_wiki_media_name("help_msgbox.png") == "help:msgbox.png"
    assert match_wiki_media_name("other.png") == "other.png"


def test_replace_src_exact_url_hit():
    soup = BeautifulSoup(
        f'<img src="{BASE_URL}/_media/help:msgbox.png">', "lxml")
    replace_src(soup.img, make_scheme())
    assert soup.img["src"] == "help_msgbox.png"


def test_replace_src_fuzzy_last_match_wins_no_break():
    # ИСТОРИК: цикл без break — при двух совпадениях побеждает ПОСЛЕДНЕЕ
    from qsp_help_builder.schema import UrlScheme
    scheme = UrlScheme(pages={}, images={
        "u1": r"dir\help_msgbox.png",   # 'help:msgbox.png'
        "u2": r"dir\help_x.png",        # 'help:x.png' — не матчится
    })
    soup = BeautifulSoup('<img src="/_media/help:msgbox.png">', "lxml")
    replace_src(soup.img, scheme)
    assert soup.img["src"] == "help_msgbox.png"


def test_process_images_unclickable_and_width():
    soup = BeautifulSoup(
        '<div><a href="#"><img src="pic.png" width="800"></a></div>', "lxml")
    process_images(soup.div, make_scheme(), base_url=BASE_URL)
    # обёртка-ссылка снята, width форсится только если уже был
    assert soup.a is None
    assert soup.img["width"] == "450"


def test_process_images_lib_proxy_decoding():
    src = ("/lib/exe/fetch.php?media="
           "https%3A%2F%2Fwiki.qsp.org%2F_media%2Fhelp%3Amsgbox.png")
    soup = BeautifulSoup(f'<div><img src="{src}"></div>', "lxml")
    process_images(soup.div, make_scheme(), base_url=BASE_URL)
    assert soup.img["src"] == "help_msgbox.png"


def test_process_images_icons_replaced_by_alt():
    soup = BeautifulSoup(
        '<div><img class="icon" src="i.png" alt="SMILE"><img class="icon" src="j.png"></div>',
        "lxml")
    process_images(soup.div, make_scheme(), base_url=BASE_URL)
    out = str(soup.div)
    assert "SMILE" in out and "i.png" not in out and "j.png" not in out


# ----------------------------------------------------------------------- hhc

SIDEBAR = """<html><body><div class="page group">
<ul>
  <li class="level1"><div class="li"><strong>Раздел</strong>
    <ul><li class="level2"><div class="li">
      <a href="help_coding.htm">Код</a></div></li>
      <li class="level2"><div class="li">
        <a href="index.htm">Индекс</a></div></li>
      <li class="level2"><div class="li">
        <a href="help_keywords.htm">Указатель</a></div></li>
    </ul></div></li>
</ul></div></body></html>"""


def test_rebuild_hhc_object_params_and_excludes():
    soup = BeautifulSoup(SIDEBAR, "lxml")
    ul = soup.select_one("div.page.group").ul
    rebuild_hhc_ul(ul, soup, frozenset({"index"}))
    out = str(ul)
    assert '<object type="text/sitemap">' in out.lower()
    # ИСТОРИК: порядок атрибутов name затем value (bs4 сериализует param как пустой элемент)
    assert '<param name="Name" value="Код"/>' in out
    assert '<param name="Local" value="help_coding.htm"/>' in out
    # исключённые (files_to_del и help_keywords) вырезаны вместе с li
    assert "Индекс" not in out
    assert "Указатель" not in out
    # div/li классы сняты
    assert 'class=' not in out


def test_build_hhc_end_to_end(tmp_path: Path):
    src = tmp_path / "sidebar.htm"
    src.write_text(SIDEBAR, encoding="utf-8")
    build_hhc(tmp_path, hhc_source="sidebar.htm", hhc_output="qsp.hhc",
              page_encoding="utf-8", index_encoding="windows-1251",
              exclude=frozenset())
    hhc = (tmp_path / "qsp.hhc").read_text(encoding="windows-1251")
    assert "<OBJECT" in hhc and "text/site properties" in hhc
    assert not src.exists()  # источник удаляется — контракт прогона


# ----------------------------------------------------------------------- hhk

KEYWORDS_TABLE = """<html><body><div class="page group">
<table><tr>
  <td class="col0"><a href="help_coding.htm#funkcii">Функции</a></td>
  <td class="col1">описание</td>
</tr><tr>
  <td class="col0">без ссылки</td>
</tr><tr>
  <td class="col0"><a href="help_glossary.htm">Глоссарий</a></td>
</tr></table></div></body></html>"""


def test_extract_hhk_data_skips_rows_without_link():
    soup = BeautifulSoup(KEYWORDS_TABLE, "lxml")
    data = extract_hhk_data(soup.select_one("div.page.group").table)
    assert data == {"Функции": "help_coding.htm#funkcii",
                    "Глоссарий": "help_glossary.htm"}


def test_href_compare_same_page_keeps_anchor_href():
    assert href_compare("a.htm#x", "a.htm") == "a.htm#x"


def test_href_compare_other_page_takes_table_page_with_anchor():
    # страница-источник уехала: берём страницу из таблицы + якорь из записи
    assert href_compare("old.htm#x", "new.htm") == "new.htm#x"


def test_build_hhk_end_to_end(tmp_path: Path):
    src = tmp_path / "help_keywords.htm"
    src.write_text(KEYWORDS_TABLE, encoding="utf-8")
    anchors = Anchors({
        "help_coding": {"funkcii": AnchorEntry(line=5, title="Функции")},
        "help_other": {"peremest": AnchorEntry(line=2, title="Глоссарий")},
    })
    build_hhk(tmp_path, hhk_source="help_keywords.htm", hhk_output="qsp.hhk",
              page_encoding="utf-8", index_encoding="windows-1251",
              anchors=anchors)
    hhk = (tmp_path / "qsp.hhk").read_text(encoding="windows-1251")
    # совпавшая страница -> якорное href из anchors
    assert '<param name="Local" value="help_coding.htm#funkcii"/>' in hhk
    # расхождение страниц -> страница из таблицы + якорь из anchors
    assert '<param name="Local" value="help_glossary.htm#peremest"/>' in hhk
    assert "</li>\n<li>" in hhk  # косметический перенос старого кода
    assert not src.exists()


def test_build_hhk_keyword_override_wins(tmp_path: Path):
    src = tmp_path / "help_keywords.htm"
    src.write_text(KEYWORDS_TABLE, encoding="utf-8")
    anchors = Anchors({
        # keywords_map даст «Функции» -> help_coding.htm#funkcii; override должен победить
        "help_coding": {"funkcii": AnchorEntry(line=5, title="Функции")},
    })
    build_hhk(tmp_path, hhk_source="help_keywords.htm", hhk_output="qsp.hhk",
              page_encoding="utf-8", index_encoding="windows-1251",
              anchors=anchors,
              keyword_overrides={"Функции": "help_regexp.htm#funkcii"})
    hhk = (tmp_path / "qsp.hhk").read_text(encoding="windows-1251")
    # §4.11: override перекрывает и keywords_map, и href_compare
    assert '<param name="Local" value="help_regexp.htm#funkcii"/>' in hhk
    assert 'help_coding.htm#funkcii' not in hhk


# ---------------------------------------------------------------- prepare_file

def test_prepare_file_excluded_returns_early(tmp_path: Path):
    (tmp_path / "index.html").write_text(DOKU_PAGE, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    prepare_file(tmp_path / "index.html", out, scheme=make_scheme(),
                 anchors=Anchors(), base_url=BASE_URL, page_encoding="utf-8",
                 exclude=frozenset({"index"}))
    assert not (out / "index.htm").exists()


def test_prepare_file_full_flow_with_anchor_injection(tmp_path: Path):
    page_src = """<html><head><title>T</title></head><body>
<div class="page group">
<p>абзац</p>
<h2 id="need_id">Раздел</h2>
<p>ещё</p>
</div></body></html>"""
    src = tmp_path / "help_coding.html"
    src.write_text(page_src, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    # line=2: инжект вставляет <a id> перед индексом 2 (0-based, §4.4 согласован)
    anchors = Anchors({"help_coding": {"need_id": AnchorEntry(line=2, title="Раздел")}})
    prepare_file(src, out, scheme=make_scheme(), anchors=anchors,
                 base_url=BASE_URL, page_encoding="utf-8", exclude=frozenset())
    text = (out / "help_coding.htm").read_text(encoding="utf-8")
    assert '<a id="need_id"></a>' in text
    assert "<title>T</title>" in text
