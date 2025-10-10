"""

    Извлекает из hhk ключевые слова и якоря, на которые эти ключевые слова ссылаются.
    Это вспомогательный инструмент. Якоря и место их размещения в файлах сериализуются
    в файле anchors.json, откуда их впоследствии можно извлекать и добавлять в файлы.

"""

import os, json, re
from bs4 import BeautifulSoup, Tag

class ExtractKeyword:

    def __init__(self, folder_out:str) -> None:
        self.folder_out = folder_out
        self.hhk = os.path.join(folder_out, 'qsp.hhk')
        with open(self.hhk, 'r', encoding='cp1251') as fp:
            file_text = fp.read()
        self.soup = BeautifulSoup(file_text, 'lxml')
        self.objects = self.soup.select('OBJECT')
        self.files = {}
        self.anchors_in_files = {}
        
    def get_kwrds_infile(self) -> None:
        lin = self.anchors_in_files
        for obj in self.objects:
            param = obj.select_one('param[name="Name"]')
            if param is None: continue
            point_name = str(param['value'])
            param = obj.select_one('param[name="Local"]')
            if param is None: continue
            point_href = str(param['value'])

            file_anchor = point_href.split('#')
            file, anchor = (tuple(file_anchor) if len(file_anchor)>1 else (file_anchor[0], ''))
            if not anchor: continue
            file_path = os.path.join(self.folder_out, str(file))
            if file_path in self.files:
                file_text = self.files[file_path]
            else:
                with open(file_path, 'r', encoding='utf-8') as fp:
                    file_text = fp.read()
                self.files[file_path] = file_text

            match = re.search(rf'id="{anchor}"', file_text)
            if match is None: continue
            string_number = len(file_text[0:match.end()].split('\n'))
            file_name = os.path.splitext(file)[0]
            if file_name in lin:
                lin[file_name][anchor] = [string_number, point_name]
            else:
                lin[file_name] = {anchor:[string_number, point_name]}

    def save_json(self, folder_src:str="..\\html_src") -> None:
        json_file = os.path.join(folder_src, 'anchors.json')
        with open(json_file, 'w', encoding='utf-8') as fp:
            json.dump(self.anchors_in_files, fp, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    folder_out = os.path.abspath("..\\html_out")
    e = ExtractKeyword(folder_out)
    e.get_kwrds_infile()
    e.save_json()