#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки работы с дублированием изображений
"""

from qsp_wiki_downloader import WikiDownloader

def test_duplicate_check():
    """Тестирует проверку дублирования изображений"""
    downloader = WikiDownloader()
    
    # Тестовые изображения
    test_images = [
        "https://wiki.qsp.org/images/logo.png",
        "https://wiki.qsp.org/images/logo.png",  # Дубликат
        "https://wiki.qsp.org/images/logo.png",  # Еще один дубликат
        "https://wiki.qsp.org/images/test.jpg",
        "https://wiki.qsp.org/images/test.jpg"   # Дубликат
    ]
    
    print("Тестирую проверку дублирования изображений...")
    
    for i, image_url in enumerate(test_images, 1):
        print(f"\n{i}. Обрабатываю: {image_url}")
        
        # Проверяем, есть ли уже в множестве скачанных
        if image_url in downloader.downloaded_images:
            print(f"   ✅ Изображение уже в списке скачанных")
        else:
            print(f"   🔍 Изображение новое, скачиваю...")
            success = downloader.download_image(image_url)
            if success:
                print(f"   ✅ Успешно скачано")
            else:
                print(f"   ❌ Ошибка при скачивании")
    
    print(f"\nРезультат:")
    print(f"  - Всего изображений в множестве: {len(downloader.downloaded_images)}")
    print(f"  - Список скачанных:")
    for url in downloader.downloaded_images:
        print(f"    * {url}")

if __name__ == "__main__":
    test_duplicate_check()
