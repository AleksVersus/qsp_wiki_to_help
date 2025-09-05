# CHM Prepare - Подготовка файлов для сборки CHM

Этот скрипт предназначен для подготовки HTML-файлов перед компиляцией в формат CHM (Compiled HTML Help).

## Описание

Скрипт `to_chm_prepare.py` выполняет следующие функции:

- **Подготовка HTML-файлов**: Очищает HTML от ненужных элементов (скрипты, навигация, TOC)
- **Обработка ссылок**: Заменяет внешние ссылки на внутренние согласно схеме
- **Извлечение изображений**: Обрабатывает ссылки на изображения
- **Создание HHC файла**: Генерирует файл навигации для CHM

## Структура проекта

```none
chm_prepare/
├── to_chm_prepare.py    # Основной скрипт
├── README.md            # Этот файл
└── requirements.txt     # Зависимости Python
```

## Требования

- Python 3.6+
- Зависимости из `requirements.txt`

## Установка

1. Убедитесь, что у вас установлен Python 3.6 или выше
2. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

## Использование

### Базовое использование

```python
from to_chm_prepare import ChmPrepare

# Создание экземпляра с настройками по умолчанию
preparat = ChmPrepare()

# Подготовка HTML файлов
preparat.prepare_html_files()

# Подготовка HHC файла
preparat.prepare_hhc()
```

### Настройка параметров

```python
settings = {
    'src_html_folder': '/path/to/source/html',
    'out_html_folder': '/path/to/output/html',
    'start_file': '/path/to/start.html',
    'scheme': '/path/to/urls_links_to_files.json',
    'base_url': 'https://your-wiki.org',
    'hhc': 'sidebar.htm'
}

preparat = ChmPrepare(settings)
```

## Структура настроек

- `src_html_folder`: Папка с исходными HTML файлами
- `out_html_folder`: Папка для подготовленных файлов
- `start_file`: Путь к стартовому HTML файлу
- `scheme`: JSON файл со схемой ссылок
- `base_url`: Базовый URL для обработки ссылок
- `hhc`: Имя файла боковой панели

## Формат схемы

Схема должна содержать два раздела:

- `pages`: Сопоставление URL страниц с локальными файлами
- `images`: Сопоставление URL изображений с локальными файлами

```json
{
    "pages": {
        "https://wiki.qsp.org/page1": "local_file1.htm",
        "https://wiki.qsp.org/page2": "local_file2.htm"
    },
    "images": {
        "https://wiki.qsp.org/image1.png": "local_image1.png",
        "https://wiki.qsp.org/image2.jpg": "local_image2.jpg"
    }
}
```

## Выходные файлы

После выполнения скрипта в папке `out_html_folder` будут созданы:

- Подготовленные HTML файлы (с расширением .htm)
- Файл навигации `qsp.hhc`

## Запуск

```bash
python to_chm_prepare.py
```

## Примечания

- Скрипт автоматически создает выходную папку, если она не существует
- Исходные HTML файлы должны содержать элемент `div.page.group`
- Для корректной работы требуется файл схемы с правильной структурой
- В конечную папку так же желательно поместить файл с описанием стилей `default.css`
