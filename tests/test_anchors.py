"""Юнит-тесты anchors-модуля (Фаза 2).

Офлайн-проверки на маленьких фикстурах: формат anchors.json, извлечение из
«сборки», вставка якорей, карта ключевых слов. Запуск:
    python -m pytest tests/test_anchors.py -v
"""

from pathlib import Path

import pytest

from qsp_help_builder.anchors import AnchorEntry, Anchors

# ------------------------------ фикстуры ------------------------------

# Мини-страница: id заголовка DokuWiki на 1-based строке 2 (0-based индекс 1).
HTM_PAGE = """<html><body>
<h2 id="sec_one">Первый</h2>
<p>текст</p>
<h3 id="a.b">Точка в id</h3>
</body></html>"""

# Мини-qsp.hhk:OBJECT-ы покрывают все ветки extract_from_build:
# валидная ссылка, ссылка без якоря, пустой якорь, отсутствующий id, нет param.
HHK_BODY = """<!DOCTYPE HTML><HTML><BODY>
<OBJECT type="text/sitemap"><param name="Name" value="Первый"/><param name="Local" value="help_test.htm#sec_one"/></OBJECT>
<OBJECT type="text/sitemap"><param name="Name" value="Доточка"/><param name="Local" value="help_test.htm#a.b"/></OBJECT>
<OBJECT type="text/sitemap"><param name="Name" value="БезЯкоря"/><param name="Local" value="help_test.htm"/></OBJECT>
<OBJECT type="text/sitemap"><param name="Name" value="Пустой"/><param name="Local" value="help_test.htm#"/></OBJECT>
<OBJECT type="text/sitemap"><param name="Name" value="НетТакого"/><param name="Local" value="help_test.htm#ghost"/></OBJECT>
<OBJECT type="text/sitemap"><param name="Name" value="БезLocal"/></OBJECT>
</BODY></HTML>"""


@pytest.fixture()
def built_dir(tmp_path: Path) -> Path:
    """Папка, имитирующая html_out: htm (utf-8) + hhk (windows-1251)."""
    (tmp_path / "help_test.htm").write_text(HTM_PAGE, encoding="utf-8")
    (tmp_path / "qsp.hhk").write_text(HHK_BODY, encoding="cp1251")
    return tmp_path


def extract(built_dir: Path) -> Anchors:
    return Anchors.extract_from_build(
        built_dir, "qsp.hhk", hhk_encoding="windows-1251", page_encoding="utf-8"
    )


# ------------------------------ извлечение ------------------------------

def test_extract_only_anchor_links(built_dir: Path):
    a = extract(built_dir)
    got = a.to_json_dict()
    # ссылки без якоря / с пустым якорем / с отсутствующим id / без param — пропущены
    assert set(got) == {"help_test"}
    assert set(got["help_test"]) == {"sec_one", "a.b"}


def test_extract_line_is_1based(built_dir: Path):
    """ИСТОРИК закрепляем тестом: строка считается 1-based (как в старом инструменте)."""
    a = extract(built_dir)
    entry = a.anchors_for("help_test")["sec_one"]
    assert HTM_PAGE.split("\n")[entry.line - 1].startswith('<h2 id="sec_one"')
    assert entry.title == "Первый"


def test_extract_escapes_regex_in_anchor(built_dir: Path):
    """Якорь 'a.b' не должен сработать как regex «a, любой символ, b»."""
    a = extract(built_dir)
    entry = a.anchors_for("help_test")["a.b"]
    assert HTM_PAGE.split("\n")[entry.line - 1].startswith('<h3 id="a.b"')


def test_extract_missing_page_raises(built_dir: Path):
    (built_dir / "help_test.htm").unlink()
    with pytest.raises(FileNotFoundError):
        extract(built_dir)


# ------------------------------ round-trip ------------------------------

def test_save_load_roundtrip(built_dir: Path, tmp_path: Path):
    a = extract(built_dir)
    out = tmp_path / "sub" / "anchors.json"  # ensure_dir в save_json проверяем заодно
    a.save(out)
    b = Anchors.load(out)
    assert a.to_json_dict() == b.to_json_dict()


def test_load_rejects_broken_format(tmp_path: Path):
    bad = tmp_path / "anchors.json"
    bad.write_text('{"f": {"a": [1]}}', encoding="utf-8")  # не [line, title]
    with pytest.raises(ValueError, match="контракт нарушен"):
        Anchors.load(bad)


# ------------------------------ вставка якорей ------------------------------

def test_inject_uses_stored_number_as_index():
    """ИСТОРИК (backlog §4.4): записанное 1-based число применяется как 0-based
    индекс — якорь встаёт на строку НИЖЕ заголовка. Закрепляем фактическое
    поведение бейзлайна; починка будет задокументированной правкой в Фазе 6."""
    text = "\n".join(["<h2 id=\"sec_one\">Т</h2>", "<p>ниже</p>", "<p>низ</p>"])
    a = Anchors({"f": {"sec_one": AnchorEntry(line=1, title="Т")}})
    out = a.inject_into_text(text, "f").split("\n")
    assert out[0] == '<h2 id="sec_one">Т</h2>'          # заголовок не тронут
    assert out[1].startswith('<a id="sec_one"></a>')    # вставка по индексу 1
    assert out[2] == "<p>низ</p>"


def test_inject_out_of_range_skips_with_warning(caplog: pytest.LogCaptureFixture):
    text = "одна строка"
    a = Anchors({"f": {"ghost": AnchorEntry(line=99, title="Призрак")}})
    out = a.inject_into_text(text, "f")
    assert out == text  # старый голый except тоже просто пропускал
    assert "Призрак" not in out
    assert "ghost" in caplog.text  # но теперь это видно в логе


def test_inject_unknown_file_passthrough():
    a = Anchors({"f": {"x": AnchorEntry(line=1, title="Т")}})
    assert a.inject_into_text("text", "other") == "text"


# ------------------------------ карта указателя ------------------------------

def test_keywords_map_shape_and_last_wins():
    a = Anchors({
        "f1": {"x": AnchorEntry(line=1, title="Одинаковый")},
        "f2": {"y": AnchorEntry(line=2, title="Одинаковый")},
    })
    # старый ChmPrepare: self.keywords_anchors[title] = ... — побеждает последний
    assert a.keywords_map()["Одинаковый"] == "f2.htm#y"
