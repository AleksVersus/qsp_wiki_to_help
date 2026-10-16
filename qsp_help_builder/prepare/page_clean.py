# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnknownVariableType=false, reportArgumentType=false
# Ограничения stub'ов bs4, не трогая семантику порта 1:1 (см. решение Фазы 3).
"""Вычистка страницы DokuWiki и спец-правки стартовой страницы.

Порт кусков ChmPrepare.prepare_htm (select div.page.group, decompose-циклы)
и блока «if file_name == 'start'».
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from ..templates import CHM_PAGE


def extract_page(soup: BeautifulSoup) -> Tag:
    """Извлекает контент страницы и удаляет служебные элементы DokuWiki.

    ИСТОРИК: селектор 'dic.docInfo' — опечатка старого кода (тега dic не
    существует; блоки class="docInfo" в html_src есть, но матчатся 'div.docInfo').
    Проверено в Фазе 3: элементы docInfo присутствуют в исходниках и СОХРАНЯЮТСЯ
    в выводе именно из-за опечатки. «Исправление» сдвинуло бы бейзлайн — правим
    только как задокументированное изменение поведения (Фаза 6, backlog §4.3).
    """
    page = soup.select_one("div.page.group")
    if page is None:
        # старый код падал TypeError на None; здесь — явная ошибка с адресом
        raise ValueError("В странице нет div.page.group — не-контентный html?")

    for el in page.select("div#dw__toc"):
        el.decompose()
    for el in page.select("dic.docInfo"):
        el.decompose()
    for el in page.select("script"):
        el.decompose()
    return page


def apply_start_fixes(soup: BeautifulSoup, page: Tag) -> None:
    """Спец-правки главной страницы справки (порт блока file_name == 'start').

    Вызывать ДО replace_links: вставляемая ссылка wiki.qsp.org содержит
    target='_blank' и должна пережить последующую замену ссылок.
    """
    # логотип в h1
    el = page.select_one("h1")
    if el:
        new_tag = soup.new_tag("img")
        new_tag["src"] = "help_wiki_logo.png"
        new_tag["alt"] = "QSP Logo"
        el.insert(0, new_tag)

    # разворачиваем ссылки на список ключевых слов (указатель делает hhc/hhk)
    for el in page.find_all("a", {"href": "/help:keywords"}):
        el.unwrap()

    # блок «Онлайн-Версия»: заголовок — текстом, содержимое — ссылкой на вики
    el = page.select_one("h2#offlajn-versija")
    if el:
        div = None
        for d in el.next_siblings:
            if d.name == "div":
                div = d
                break
        if div is None:
            # старый код падал NameError; понятное исключение вместо
            raise RuntimeError("start: у h2#offlajn-versija нет следующего div")
        el.clear()
        el.append("Онлайн-Версия")
        div.clear()
        p = soup.new_tag("p")
        a = soup.new_tag("a", href="https://wiki.qsp.org", target="_blank")
        a.append("онлайн")
        p.append("Свежая версия справки доступна ")
        p.append(a)
        p.append(".")
        div.append(p)


def wrap_into_template(source_soup: BeautifulSoup, page: Tag) -> str:
    """Порт обёртки: CHM_PAGE + append(page) + перенос title -> финальный текст.

    title.replace_with(source_soup.title) берёт тег из ИСХОДНОГО soup — как в
    старом коде; порядок операций в точности старый (append до replace_with).
    """
    new_soup = BeautifulSoup(CHM_PAGE, "lxml")
    new_soup.body.append(page)
    new_soup.title.replace_with(source_soup.title)
    return str(new_soup)
