"""Юнит-тесты naming-модуля (Фаза 4).

Офлайн-проверка чистого именования URL -> локальный файл. Отдельно закрепляет
ИСТОРИЧЕСКИЙ БАГ среза query-строки (разные fetch.php -> один fetch.png), чтобы
починка не «просочилась» молча (backlog handoff §4.2).
    python -m pytest tests/test_naming.py -v
"""

from qsp_help_builder.download.naming import (
    image_extension,
    image_filename,
    page_filename,
)

BASE = "https://wiki.qsp.org"


# ------------------------------------------------------------------ page_filename

def test_root_url_becomes_index():
    assert page_filename(BASE) == "index.html"


def test_single_path_part():
    assert page_filename(f"{BASE}/start") == "start.html"


def test_colon_sanitized_to_underscore():
    assert page_filename(f"{BASE}/help:qspider_spectags") == "help_qspider_spectags.html"


def test_nested_parts_joined_with_underscore():
    assert page_filename(f"{BASE}/a/b/c") == "a_b_c.html"


def test_query_and_fragment_ignored_in_page_name():
    # urlparse берёт только path: query/fragment не попадают в имя файла.
    assert page_filename(f"{BASE}/help:coding?rev=1#sec") == "help_coding.html"


# ------------------------------------------------------------------ image_extension

def test_ext_from_content_type_png():
    assert image_extension("image/png", f"{BASE}/whatever") == "png"


def test_jpeg_normalized_to_jpg():
    assert image_extension("image/jpeg", f"{BASE}/whatever") == "jpg"


def test_content_type_with_charset_param():
    assert image_extension("image/gif; charset=binary", f"{BASE}/x") == "gif"


def test_fallback_to_url_extension_when_not_image():
    assert image_extension("text/html", f"{BASE}/a/pic.webp") == "webp"


def test_default_jpg_when_nothing_matches():
    assert image_extension("application/octet-stream", f"{BASE}/lib/exe/fetch.php") == "jpg"


# ------------------------------------------------------------------ image_filename

def test_fetch_php_query_string_bug_preserved():
    """Разные media через fetch.php дают ОДНО имя fetch.png — известный баг сохраняется."""
    url_a = f"{BASE}/lib/exe/fetch.php?media=one.png&w=1"
    url_b = f"{BASE}/lib/exe/fetch.php?media=two.png&w=2"
    assert image_filename(url_a, "image/png") == "fetch.png"
    assert image_filename(url_b, "image/png") == "fetch.png"


def test_media_url_with_colon_namespace():
    url = f"{BASE}/_media/help:msgbox.png?w=200&tok=3424fe"
    assert image_filename(url, "image/png") == "help_msgbox.png"


def test_direct_gif_extension_from_url():
    url = f"{BASE}/lib/images/smileys/icon_smile.gif"
    assert image_filename(url, "") == "icon_smile.gif"
