import os, json
from bs4 import BeautifulSoup, Tag

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
            'hhk': 'help_keywords.htm'
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

    def prepare_html_files(self):
        """ Подготовка html-файлов к компиляции """
        for f in self.files_pathes:
            self.prepare_htm(f)

    def prepare_htm(self, file_path:str):
        """ Подготовка отдельного htm файла к публикации """

        # извлекаем имена
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(self.out_html_folder, f'{file_name}.htm')

        soup = BeautifulSoup(read_file(file_path), 'lxml')
        # извлекаем страницу
        page = soup.select('div.page.group')[0]
        # удаляем ненужные элементы
        for el in page.select('div#dw__toc'): el.decompose()
        for el in page.select('dic.docInfo'): el.decompose()
        for el in page.select('script'): el.decompose()
        # заменяем ссылки на внутренние
        self.replace_links(page)

        # извлекаем изображения
        self.extract_images(page)

        new_soup = BeautifulSoup(CHM_PAGE, 'lxml')
        new_soup.body.append(page)
        new_soup.title.replace_with(soup.title)

        write_file(output_path, str(new_soup))

    def extract_images(self, el:Tag):
        """ Извлечение изображений """
        for img in el.find_all('img', src=True):
            src = img['src']
            if src.startswith('https://wiki.qsp.org'):
                img['src'] = self.replace_href(src, scheme_type='images')

    def replace_links(self, el):
        """ Замена ссылок на внутренние, используя схему """
        for link in el.find_all('a', href=True):
            href = link['href']

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

        with open(self.hhc_dst_path, 'w', encoding='windows-1251') as fp:
            fp.write(str(new_soup))
        os.remove(self.hhc_src_path)

    def hhc_ul_rebuild_li(self, ul:Tag, soup:BeautifulSoup):
        """ Перестройка ul """
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
                param_name = soup.new_tag('param',  attrs={'name':'Name', 'value':name})
                param_local = soup.new_tag('param', attrs={'name':'Local', 'value':href})
                div.clear()
                div.extend([param_name, param_local])
            else:
                name = str(div.text).strip()
                param_name = soup.new_tag('param',  attrs={'name':'Name', 'value':name})
                div.clear()
                div.append(param_name)

    def prepare_hhk(self):
        """ Подготавливает файл указателя. """
        soup = BeautifulSoup(read_file(self.hhk_src_path), 'lxml')
        ul = soup.select('div.page.group')[0].ul

        self.hhc_ul_rebuild_li(ul, soup)
        
        new_soup = BeautifulSoup(HHK_PAGE, 'lxml')
        new_soup.body.append(ul)

        with open(self.hhk_dst_path, 'w', encoding='windows-1251') as fp:
            fp.write(str(new_soup))
        os.remove(self.hhk_src_path)


def main():
    preparat = ChmPrepare()
    preparat.prepare_html_files()
    preparat.prepare_hhc()
    preparat.prepare_hhk()

if __name__=="__main__":
    main()