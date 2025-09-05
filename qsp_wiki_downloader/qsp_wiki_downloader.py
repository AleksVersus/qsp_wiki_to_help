#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для скачивания всех страниц документации с wiki.qsp.org
и сохранения их в папку html_src
"""

import requests
import os, json
import time
import re
from urllib.parse import urljoin, urlparse, ParseResult
from bs4 import BeautifulSoup
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,  # Изменено на DEBUG для более детального логирования
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wiki_download.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class WikiDownloader:
    def __init__(self, base_url="https://wiki.qsp.org", output_dir="..\\html_src"):
        self.base_url = base_url
        self.output_dir = output_dir

        self.session = requests.Session()
        user_agent = ' '.join([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'AppleWebKit/537.36 (KHTML, like Gecko)',
            'Chrome/91.0.4472.124 Safari/537.36'
        ])
        self.session.headers.update({
            'User-Agent': user_agent
        })

        self.downloaded_urls = set()
        self.failed_urls = set()
        self.downloaded_images = set()
        self.failed_images = set()

        self.urls_link_file = {
            'images': {},
            'pages': {}
        }
        
        # Создаем папку для сохранения файлов
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"Создана папка: {output_dir}")
        
        # Создаем папку для изображений
        self.images_dir = os.path.join(output_dir, "images")
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)
            logging.info(f"Создана папка для изображений: {self.images_dir}")
    
    def get_page_content(self, url):
        """Получает содержимое страницы"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except requests.RequestException as e:
            logging.error(f"Ошибка при загрузке {url}: {e}")
            return None
    
    def extract_links(self, soup:BeautifulSoup, base_url):
        """Извлекает все ссылки со страницы"""
        links = set()

        # Ищем все ссылки
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Пропускаем внешние ссылки и якоря
            if href.startswith('http') or href.startswith('#') or href.startswith('mailto:'):
                continue
            
            # Получаем полный URL
            full_url = str(urljoin(base_url, href))
            full_url = full_url.split('?')[0]
            full_url = full_url.split('#')[0]

            # Пропускаем, если url уже загружен (такого не должно быть!)
            if full_url in self.downloaded_urls:
                continue

            if full_url.endswith('.php'):
                continue
            elif full_url.split('.')[-1] in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                # Скачиваем изображение если оно еще не скачано
                if full_url not in self.downloaded_images:
                    logging.debug(f"Найдена ссылка на новое изображение: {full_url}")
                    self.download_image(full_url)
                else:
                    logging.debug(f"Ссылка на уже найденное изображение: {full_url}")
                continue
            
            # Проверяем, что ссылка ведет на тот же домен
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                links.add(full_url)
        
        return links
    
    def extract_images(self, soup:BeautifulSoup, base_url):
        # Ищем изображения в тегах <img>

        for img in soup.find_all('img', src=True):
            src = img['src']
            if src.startswith('http'):
                image_url = src
            else:
                image_url = str(urljoin(base_url, src))

            if image_url.startswith('https://wiki.qsp.org/lib/exe/indexer.php'):
                continue
            
            # Скачиваем изображение если это локальный файл и оно еще не скачано
            if urlparse(image_url).netloc == urlparse(base_url).netloc:
                if image_url not in self.downloaded_images:
                    logging.debug(f"Найдено новое изображение в <img>: {image_url}")
                    self.download_image(image_url)
                else:
                    logging.debug(f"Изображение уже найдено ранее: {image_url}")
    
    def save_page(self, url, html_content):
        """Сохраняет страницу в файл"""
        try:
            # Создаем безопасное имя файла
            parsed_url:ParseResult = urlparse(url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            if not path_parts or path_parts[0] == '':
                filename = "index.html"
            else:
                # Заменяем недопустимые символы в имени файла
                safe_parts = []
                for part in path_parts:
                    safe_part = re.sub(r'[<>:"/\\|?*]', '_', part)
                    safe_parts.append(safe_part)
                
                filename = "_".join(safe_parts) + ".html"
            
            filepath = os.path.join(self.output_dir, filename)
            
            # # Если файл уже существует, добавляем номер
            # counter = 1
            # original_filepath = filepath
            # while os.path.exists(filepath):
            #     name, ext = os.path.splitext(original_filepath)
            #     filepath = f"{name}_{counter}{ext}"
            #     counter += 1
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.urls_link_file['pages'][url] = filepath
            
            logging.info(f"Сохранена страница: {filename}")
            return True
            
        except Exception as e:
            logging.error(f"Ошибка при сохранении {url}: {e}")
            return False
    
    def download_image(self, image_url):
        """Скачивает изображение по указанной ссылке"""
        # Проверяем, не скачано ли уже это изображение
        if image_url in self.downloaded_images:
            logging.debug(f"Изображение уже скачано, пропускаю: {image_url}")
            return
        try:
            # Получаем изображение
            response = self.session.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Определяем расширение файла
            content_type = response.headers.get('content-type', '')
            if 'image/' in content_type:
                ext = content_type.split('/')[-1]
                if ext == 'jpeg':
                    ext = 'jpg'
            else:
                # Пытаемся определить расширение по URL
                parsed_url = urlparse(image_url)
                path = parsed_url.path.lower()
                if path.endswith('.png'):
                    ext = 'png'
                elif path.endswith('.jpg') or path.endswith('.jpeg'):
                    ext = 'jpg'
                elif path.endswith('.gif'):
                    ext = 'gif'
                elif path.endswith('.webp'):
                    ext = 'webp'
                else:
                    ext = 'jpg'  # По умолчанию
            
            # Создаем безопасное имя файла
            parsed_url = urlparse(image_url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            if not path_parts or path_parts[0] == '':
                filename = f"image_{int(time.time())}.{ext}"
            else:
                # Берем последнюю часть пути как имя файла
                last_part = path_parts[-1]
                # Убираем расширение если есть
                name_without_ext = os.path.splitext(last_part)[0]
                # Очищаем имя файла от недопустимых символов
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', name_without_ext)
                filename = f"{safe_name}.{ext}"
            
            filepath = os.path.join(self.images_dir, filename)
            
            # Если файл уже существует, добавляем номер
            # counter = 1
            # original_filepath = filepath
            # while os.path.exists(filepath):
            #     name, ext = os.path.splitext(original_filepath)
            #     filepath = f"{name}_{counter}{ext}"
            #     counter += 1
            
            # Сохраняем изображение
            with open(filepath, 'wb') as f:
                f.write(response.content)

            self.urls_link_file['images'][image_url] = filepath
            
            logging.info(f"Скачано изображение: {filename}")
            self.downloaded_images.add(image_url)
            return True
            
        except Exception as e:
            logging.error(f"Ошибка при скачивании изображения {image_url}: {e}")
            self.failed_images.add(image_url)
            return False
    
    def get_download_stats(self):
        """Возвращает статистику скачивания"""
        return {
            'downloaded_urls': len(self.downloaded_urls),
            'failed_urls': len(self.failed_urls),
            'downloaded_images': len(self.downloaded_images),
            'failed_images': len(self.failed_images),
            'total_images_found': len(self.downloaded_images) + len(self.failed_images)
        }
    
    def save_urls_link_files(self) -> None:
        """ Сохраняет JSON-файл со списком итоговых файлов и гиперссылок. """
        json_path = os.path.join(self.output_dir, 'urls_links_to_files.json')
        with open(json_path, 'w', encoding='utf-8') as fp:
            json.dump(self.urls_link_file, fp, ensure_ascii=False, indent=4)
        logging.info('JSON структура со связкой url и путей к файлам сохраена.')
    
    def download_wiki(self):
        """Основная функция для скачивания всей вики"""
        logging.info(f"Начинаю скачивание с {self.base_url}")
        
        # Начинаем с главной страницы
        urls_to_process = [self.base_url]
        
        while urls_to_process:
            current_url = urls_to_process.pop(0)
            
            if current_url in self.downloaded_urls:
                continue
            
            logging.info(f"Обрабатываю: {current_url}")
            
            # Получаем содержимое страницы
            html_content = self.get_page_content(current_url)
            if not html_content:
                self.failed_urls.add(current_url)
                continue
            
            # Сохраняем страницу
            if self.save_page(current_url, html_content):
                self.downloaded_urls.add(current_url)
            
            # Извлекаем новые ссылки
            soup = BeautifulSoup(html_content, 'html.parser')
            new_links = self.extract_links(soup, current_url)
            for link in new_links:
                if link not in self.downloaded_urls:
                    urls_to_process.append(link)
            self.extract_images(soup, current_url)
            
            # Небольшая задержка между запросами
            time.sleep(0.5)
        
        logging.info(f"Скачивание завершено!")
        logging.info(f"Успешно скачано: {len(self.downloaded_urls)} страниц")
        logging.info(f"Ошибок: {len(self.failed_urls)} страниц")
        logging.info(f"Успешно скачано изображений: {len(self.downloaded_images)}")
        logging.info(f"Ошибок при скачивании изображений: {len(self.failed_images)}")
        
        if self.failed_urls:
            logging.warning("Список неудачных URL:")
            for url in self.failed_urls:
                logging.warning(f"  - {url}")
        
        if self.failed_images:
            logging.warning("Список неудачных изображений:")
            for url in self.failed_images:
                logging.warning(f"  - {url}")

def main():
    """Главная функция"""
    downloader = WikiDownloader()
    
    try:
        downloader.download_wiki()
        print(f"\nСкачивание завершено!")
        print(f"HTML файлы сохранены в папке: {downloader.output_dir}")
        print(f"Изображения сохранены в папке: {downloader.images_dir}")
        print(f"Лог сохранен в файле: wiki_download.log")
        
        # Выводим детальную статистику
        stats = downloader.get_download_stats()
        print(f"\nСтатистика скачивания:")
        print(f"  - Скачано страниц: {stats['downloaded_urls']}")
        print(f"  - Ошибок страниц: {stats['failed_urls']}")
        print(f"  - Скачано изображений: {stats['downloaded_images']}")
        print(f"  - Ошибок изображений: {stats['failed_images']}")
        print(f"  - Всего изображений найдено: {stats['total_images_found']}")

        downloader.save_urls_link_files()
        
    except KeyboardInterrupt:
        logging.info("Скачивание прервано пользователем")
        print("\nСкачивание прервано пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    main()
