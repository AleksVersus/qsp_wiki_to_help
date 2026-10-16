"""Заготовки страниц для выходов CHM-конвейера.

Перенесены БЕЗ ИЗМЕНЕНИЙ из to_chm_prepare.py (строки 19–45): они подаются
BeautifulSoup как каркас нового документа, и любой их сдвиг (атрибуты, пробелы,
порядок тегов) сдвинет байты итогового html_out и упрётся в правило приёмки
бейзлайна (_baseline/2026-10-16/BASELINE.md). Правки здесь допустимы только
вместе с заранее задокументированным изменением поведения.
"""

# Обёртка каждой отдельной htm-страницы справки.
# Примечание: ссылка на default.css предполагает файл, который кладут в html_out
# вручную (README, этап 2, шаг 5) — в Фазе 6 решим, забирать ли его из конфига.
CHM_PAGE = '''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title></title>
    <link type="text/css" href="default.css" rel="stylesheet" />
</head>
<body>
</body>
</html>'''

# Каркас файла содержания qsp.hhc (блок <OBJECT> site properties обязателен для HH Workshop).
HHC_PAGE = '''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">
<HTML>
<BODY>
<OBJECT type="text/site properties">
    <param name="Window Styles" value="0x800025">
</OBJECT>
</BODY></HTML>'''

# Каркас файла указателя qsp.hhk.
HHK_PAGE = '''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">
<HTML>
<HEAD>
</HEAD><BODY>
<OBJECT type="text/site properties">
	<param name="FrameName" value="">
</OBJECT></BODY></HTML>'''
