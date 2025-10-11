import os, json
from bs4 import BeautifulSoup, Tag
from typing import List, Dict, Union

from urllib.parse import urljoin, urlparse, ParseResult

def json_load(path:str):
    with open(path, 'r', encoding='utf-8') as fp:
        return json.load(fp)

def read_file(path:str):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()

def write_file(path:str, text:str):
    with open(path, 'w', encoding='utf-8') as fp:
        return fp.write(text)
    
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

HHC_PAGE = '''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">
<HTML>
<BODY>
<OBJECT type="text/site properties">
    <param name="Window Styles" value="0x800025">
</OBJECT>
</BODY></HTML>'''

HHK_PAGE = '''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">
<HTML>
<HEAD>
</HEAD><BODY>
<OBJECT type="text/site properties">
	<param name="FrameName" value="">
</OBJECT></BODY></HTML>'''

class ChmPrepare:
    """ Подготовка HTML-файлов к компиляции """

    def __init__(self, settings:dict = None) -> None:

        workdir = os.path.normpath(os.path.join(os.getcwd(), '..\\'))
        # подготавливаем настройки
        self.sets = {
            'src_html_folder': os.path.join(workdir, 'html_src'),
            'out_html_folder': os.path.join(workdir, 'html_out'),
            'start_file': os.path.join(workdir, 'html_src/start.html'),
            'scheme': os.path.join(workdir, 'html_src/urls_links_to_files.json'),
            'base_url': 'https://wiki.qsp.org',
            'hhc': 'sidebar.htm',
            'hhk': 'help_keywords.htm',
            'anchors': os.path.join(workdir, 'html_src/anchors.json')
        }
        if settings: self.sets.update(settings)

        # файлы папки
        self.src_html_folder = os.path.abspath(self.sets['src_html_folder'])
        self.out_html_folder = os.path.abspath(self.sets['out_html_folder'])

        if not os.path.exists(self.out_html_folder):
            os.makedirs(self.out_html_folder)

        self.files_pathes:list[str] = [] # Список файлов для преподготовки

        for f in os.listdir(self.src_html_folder):
            rf = os.path.join(self.src_html_folder, f)
            if os.path.isfile(rf) and os.path.splitext(rf)[1] == '.html':
                self.files_pathes.append(rf)

        self.hhc_src_path = os.path.join(self.out_html_folder, self.sets['hhc'])
        self.hhc_dst_path = os.path.join(self.out_html_folder, 'qsp.hhc')
        self.hhk_src_path = os.path.join(self.out_html_folder, self.sets['hhk'])
        self.hhk_dst_path = os.path.join(self.out_html_folder, 'qsp.hhk')

        self.base_url = self.sets['base_url']

        # схема сборки
        self.scheme = json_load(self.sets['scheme'])

        # якоря
        self.anchors_files:Dict[str, Dict[str, List[Union[int, str]]]]  = None
        with open(self.sets['anchors'], 'r', encoding='utf-8') as fp:
            self.anchors_files = json.load(fp)

        self.keywords_anchors:Dict[str, str] = {} # title: href

        for file_name, kwrds in self.anchors_files.items():
            for anchor, line_title in kwrds.items():
                _, title = line_title
                self.keywords_anchors[title] = f'{file_name}.htm#{anchor}'

        # имена файлов к удалению
        self.files_to_del = [
            'discussions',
            'help_aeroqsp',
            'help_fajl_css_igry_v_quest_navigator',
            'help_fajl_js_igry_v_quest_navigator',
            'help_fajl_nastroek_igry_v_quest_navigator',
            'help_ispolzovanie_shriftov_v_quest_navigator',
            'help_navigator_command_line',
            'help_navigator_game_files',
            'help_navigator_game_template',
            'help_navigator_standalone',
            'help_sozdanie_igr_na_quest_navigator',
            'playground_contents_what_dif_goto_gosub.md',
            'index',
            'playground_playground',
            'help_navigator'
        ]

    def prepare_html_files(self):
        """ Подготовка html-файлов к компиляции """
        for f in self.files_pathes:
            self.prepare_htm(f)

        for f in self.files_to_del:
            file_path = os.path.join(self.out_html_folder, f'{f}.htm')
            if os.path.isfile(file_path): os.remove(file_path)

    def prepare_htm(self, file_path:str):
        """ Подготовка отдельного htm файла к публикации """

        # извлекаем имена
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(self.out_html_folder, f'{file_name}.htm')
        if file_name in self.files_to_del: return

        soup = BeautifulSoup(read_file(file_path), 'lxml')
        # извлекаем страницу
        page = soup.select_one('div.page.group')
        # удаляем ненужные элементы
        for el in page.select('div#dw__toc'): el.decompose()
        for el in page.select('dic.docInfo'): el.decompose()
        for el in page.select('script'): el.decompose()

        # если страница start
        if file_name == 'start':
            # , добавляем лого в заголовок
            el = page.select_one('h1')
            if el:
                new_tag = soup.new_tag('img')
                new_tag['src'] = 'help_wiki_logo.png'
                new_tag['alt'] = 'QSP Logo'
                el.insert(0, new_tag)
            # избавляемся от несуществующих ссылок
            els = page.find_all('a', {'href': '/help:keywords'})
            for el in els:
                el.unwrap()
            # добавляем ссылку на онлайн
            el = page.select_one('h2#offlajn-versija')
            if el:
                for d in el.next_siblings:
                    if d.name == 'div':
                        div = d
                        break
                el.clear()
                el.append('Онлайн-Версия')
                div.clear()
                p = soup.new_tag('p')
                a = soup.new_tag('a', href="https://wiki.qsp.org", target="_blank")
                a.append('онлайн')
                p.append('Свежая версия справки доступна ')
                p.append(a)
                p.append('.')
                div.append(p)

        # заменяем ссылки на внутренние
        self.replace_links(page)

        # извлекаем изображения
        self.extract_images(page)

        new_soup = BeautifulSoup(CHM_PAGE, 'lxml')
        new_soup.body.append(page)
        new_soup.title.replace_with(soup.title)

        # добавляем якоря
        file_lines = str(new_soup).split('\n')
        anchors_files = self.anchors_files

        if file_name in anchors_files:
            anchors = anchors_files[file_name]
            for anchor, line_keyword in anchors.items():
                line, _ = line_keyword
                file_lines[line] = f'<a id="{anchor}"></a>{file_lines[line]}'

        write_file(output_path, '\n'.join(file_lines))

    def extract_images(self, el:Tag):
        """ Извлечение изображений """
        for img in el.find_all('img', src=True):
            src = img['src']
            if src.startswith('https://wiki.qsp.org'):
                img['src'] = self.replace_href(src, scheme_type='images')

        for img in el.select('img.icon'):
            if img.has_attr('alt'):
                alt = img['alt']
                img.replace_with(str(alt))
            else:
                img.decompose()

    def replace_links(self, el:Tag):
        """ Замена ссылок на внутренние, используя схему """
        for link in el.find_all('a', href=True):
            href = link['href']
            if link.has_attr('target') and link['target'] == '_blank':
                continue
            if link.has_attr('class') and set(link['class']) & {'fn_bot', 'fn_top'}:
                continue 

            href = str(urljoin(self.base_url, href))
            if href.startswith('https://wiki.qsp.org'):
                href = self.replace_href(href, '#')
                href = self.replace_href(href, '?')
                href = href.replace('.html', '.htm')
            else:
                link['target'] = '_blank'

            link['href'] = href

    def replace_href(self, href:str, splitter:str = '', scheme_type:str = 'pages') -> str:
        """ Замена ссылки на схематозную. """
        hash_taged = href.split(splitter)
        if len(hash_taged)>1:      
            if hash_taged[0] in self.scheme[scheme_type]:
                hash_taged[0] = os.path.split(self.scheme[scheme_type][hash_taged[0]])[-1]
                href = f'{hash_taged[0]}{splitter}{hash_taged[1]}'
        elif href in self.scheme[scheme_type]:
            href = os.path.split(self.scheme[scheme_type][href])[-1]

        return href

    def prepare_hhc(self) -> None:
        """ Подготовка hhc файла """

        soup = BeautifulSoup(read_file(self.hhc_src_path), 'lxml')
        ul = soup.select('div.page.group')[0].ul

        self.hhc_ul_rebuild_li(ul, soup)
        
        new_soup = BeautifulSoup(HHC_PAGE, 'lxml')
        new_soup.body.append(ul)

        # удаляем 

        with open(self.hhc_dst_path, 'w', encoding='windows-1251') as fp:
            fp.write(str(new_soup))
        os.remove(self.hhc_src_path)

    def hhc_ul_rebuild_li(self, ul:Tag, soup:BeautifulSoup):
        """ Перестройка ul """
        exclude_links = self.files_to_del[:]
        exclude_links.extend([
            'help_keywords'])
        for li in ul.select('li'):
            del li['class']
            div = li.div
            del div['class']
            div.name = 'OBJECT'
            div['type'] = 'text/sitemap'
            for el in div.select('strong'):
                el.unwrap()
            anchors = div.select('a')
            if anchors:
                a = anchors[0]
                name = a.string
                href = a['href']
                if href[:-4] in exclude_links:
                    li.decompose()
                    continue
                param_name = soup.new_tag('param',  attrs={'name':'Name', 'value':name})
                param_local = soup.new_tag('param', attrs={'name':'Local', 'value':href})
                div.clear()
                div.extend([param_name, param_local])
            else:
                name = str(div.text).strip()
                param_name = soup.new_tag('param',  attrs={'name':'Name', 'value':name})
                div.clear()
                div.append(param_name)

    def extract_hhk_data(self, table:Tag, soup:BeautifulSoup) -> Dict[str, str]:
        params = {
            # title: href
        }
        for tr in table.select('tr'):
            td = tr.select_one('td.col0')
            link = td.a
            if not link: continue
            params[link.text] = link['href']

        return params

    def prepare_hhk(self):
        """ Подготавливает файл указателя. """
        soup = BeautifulSoup(read_file(self.hhk_src_path), 'lxml')
        page = soup.select_one('div.page.group')

        params = self.extract_hhk_data(page.table, soup)
        
        new_soup = BeautifulSoup(HHK_PAGE, 'lxml')
        ul = new_soup.new_tag('ul')
        for title, new_href in params.items():
            li = new_soup.new_tag('li')
            obj = new_soup.new_tag('OBJECT')
            obj['type'] = 'text/sitemap'
            param_title = new_soup.new_tag('param')
            param_title['name'] = "Name"
            param_title['value'] = title
            if title in self.keywords_anchors:
                old_href = self.keywords_anchors[title]
                new_href = self._href_compare(old_href, new_href)
            param_href = new_soup.new_tag('param')
            param_href['name'] = "Local"
            param_href['value'] = new_href
            obj.append(param_title)
            obj.append(param_href)
            li.append(obj)
            ul.append(li)

        new_soup.body.append(ul)

        file_text = str(new_soup)
        file_text = file_text.replace('</li><li>', '</li>\n<li>')

        with open(self.hhk_dst_path, 'w', encoding='windows-1251') as fp:
            fp.write(file_text)
        os.remove(self.hhk_src_path)

    def _href_compare(self, old_href:str, new_href:str) -> str:
        if old_href.startswith(new_href):
            return old_href
        else:
            ancor = old_href.split('#')[1]
            return f"{new_href}#{ancor}"


def main():
    preparat = ChmPrepare()
    preparat.prepare_html_files()
    preparat.prepare_hhc()
    preparat.prepare_hhk()

if __name__=="__main__":
    main()