#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки скачивания изображений
"""

from qsp_wiki_downloader import WikiDownloader

def test_image_download():
    """Тестирует скачивание изображения"""
    downloader = WikiDownloader()
    
    # Тестовое изображение (замените на реальную ссылку)
    test_image_url = "https://wiki.qsp.org/images/logo.png"
    
    print(f"Тестирую скачивание изображения: {test_image_url}")
    
    try:
        success = downloader.download_image(test_image_url)
        if success:
            print("✅ Изображение успешно скачано!")
        else:
            print("❌ Ошибка при скачивании изображения")
    except Exception as e:
        print(f"❌ Исключение при скачивании: {e}")

if __name__ == "__main__":
    test_image_download()
