"""Единая модель контракта anchors.json (Фаза 2 рефакторинга).

До рефакторинга формат жил в двух местах независимо:
- извлечение: быв. _auxtools/extract_keywords.py (qsp.hhk + htm -> anchors.json);
- потребление: ChmPrepare (вставка <a id> в prepare_htm + карта keywords_anchors).
Здесь — единственное представление; при расхождении со старым кодом приоритет
за поведением бейзлайна (_baseline/2026-10-16), см. комментарии «ИСТОРИК».

Исторический формат файла (менять нельзя без миграции, handoff §5):
    { "<file_name_без_.htm>": { "<anchor>": [line_number, "title"] } }

§4.4 (исправлено): раньше line_number записывался как 1-based (extract), но
при вставке использовался как индекс списка, т.е. 0-based — якорь вставал на
строку НИЖЕ фактического id (backlog handoff §4.4). Теперь extract пишет
0-based индекс вставки, и inject применяет его согласованно (lines[entry.line]).
Критерий корректности — идемпотентность: повторный extract после prepare даёт
тот же anchors.json.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from bs4 import BeautifulSoup

from .fs_utils import file_name, load_json, read_text, save_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnchorEntry:
    """Один якорь: привязка к строке файла + заголовок из указателя."""

    line: int      # 0-based индекс строки, перед которой вставляется <a id> (§4.4 исправлено)
    title: str


def _entry_to_json(entry: AnchorEntry) -> list[object]:
    """Сериализация одной записи — дословно старый формат [line, title]."""
    return [entry.line, entry.title]


class Anchors:
    """Набор якорей по файлам. Ключ внешнего словаря — имя файла без расширения."""

    def __init__(self, by_file: dict[str, dict[str, AnchorEntry]] | None = None) -> None:
        self._by_file = by_file or {}

    # ---------- загрузка/сохранение исторического формата ----------

    @classmethod
    def load(cls, path: Path) -> "Anchors":
        """Читает anchors.json в историческом формате; битую структуру — явной ошибкой."""
        raw: dict[str, dict[str, Any]] = load_json(path)
        by_file: dict[str, dict[str, AnchorEntry]] = {}
        for file_key, anchors in raw.items():
            entries: dict[str, AnchorEntry] = {}
            for anchor, payload in anchors.items():
                pair = cast("list[Any]", payload) if isinstance(payload, list) else []
                if len(pair) != 2:
                    raise ValueError(
                        f"anchors.json: запись '{file_key}'/{anchor} != [line, title] — контракт нарушен"
                    )
                entries[anchor] = AnchorEntry(line=int(pair[0]), title=str(pair[1]))
            by_file[file_key] = entries
        return cls(by_file)

    def to_json_dict(self) -> dict[str, dict[str, list[object]]]:
        """Обратное преобразование в исторический JSON (порядок ключей — как добавляли)."""
        return {
            file_key: {anchor: _entry_to_json(e) for anchor, e in anchors.items()}
            for file_key, anchors in self._by_file.items()
        }

    def save(self, path: Path) -> None:
        """Пишет в формате старого ExtractKeyword.save_json (indent=4, ensure_ascii=False)."""
        save_json(self.to_json_dict(), path)

    # ---------- вопросы для потребителей ----------

    @property
    def files(self) -> list[str]:
        return list(self._by_file)

    def anchors_for(self, file_key: str) -> dict[str, AnchorEntry]:
        return self._by_file.get(file_key, {})

    def keywords_map(self) -> dict[str, str]:
        """Карта title -> 'file.htm#anchor' (быв. self.keywords_anchors из ChmPrepare).

        ИСТОРИК: при одинаковых заголовках побеждает последняя встреченная запись —
        ровно как в старом цикле `self.keywords_anchors[title] = ...`.
        """
        result: dict[str, str] = {}
        for file_key, anchors in self._by_file.items():
            for anchor, entry in anchors.items():
                result[entry.title] = f"{file_key}.htm#{anchor}"
        return result

    # ---------- вставка в собранную страницу (быв. кусок prepare_htm) ----------

    def inject_into_text(self, text: str, file_key: str) -> str:
        """Вставляет <a id=...></a> перед записанными строками готового текста страницы.

        Вызов всегда: после str(new_soup) и ДО записи файла (как в старом коде).
        ИСТОРИК сохранён: строки вне диапазона пропускаются (старый голый except),
        но с записью в лог. Теперь entry.line — согласованный 0-based индекс
        вставки (§4.4 исправлено): extract и inject трактуют число одинаково.

        Старый код глушил промах по индексу голым except + print; здесь тот же
        эффект (пропуск с записью в лог), но различимый: IndexError — единственный
        реальный способ промаха, остальные ошибки — баги, их ловить нечего.
        """
        anchors = self.anchors_for(file_key)
        if not anchors:
            return text
        lines = text.split("\n")
        for anchor, entry in anchors.items():
            try:
                lines[entry.line] = f'<a id="{anchor}"></a>{lines[entry.line]}'
            except IndexError:
                logger.warning(
                    "Якорь '%s' пропущен: строка %d вне файла '%s' (всего %d)",
                    anchor, entry.line, file_key, len(lines),
                )
        return "\n".join(lines)

    # ---------- извлечение из собранной сборки (быв. ExtractKeyword) ----------

    @staticmethod
    def extract_from_build(
        out_dir: Path,
        hhk_file: str,
        *,
        hhk_encoding: str,
        page_encoding: str,
    ) -> "Anchors":
        """Собирает anchors из готового html_out: qsp.hhk + htm-файлы с id=...

        Полный порт old ExtractKeyword: берёт OBJECT из hhk, для ссылок с якорем
        ищет первое вхождение id="<anchor>" в соответствующем htm и запоминает
        номер строки. Заодно кэширует тексты файлов (старый self.files).
        """
        hhk_path = out_dir / hhk_file
        soup = BeautifulSoup(read_text(hhk_path, hhk_encoding), "lxml")
        by_file: dict[str, dict[str, AnchorEntry]] = {}
        text_cache: dict[Path, str] = {}

        for obj in soup.select("OBJECT"):
            param_name = obj.select_one('param[name="Name"]')
            if param_name is None:
                continue
            param_local = obj.select_one('param[name="Local"]')
            if param_local is None:
                continue
            title = str(param_name["value"])
            href = str(param_local["value"])

            parts = href.split("#")
            if len(parts) < 2:
                continue  # ссылка без якоря — не указатель, старый код её пропускал
            file_part, anchor = parts[0], parts[1]
            if not anchor:
                continue

            htm_path = out_dir / file_name(file_part)
            if htm_path not in text_cache:
                # старый код падал с FileNotFoundError без объяснений; мы — с внятным сообщением
                if not htm_path.is_file():
                    raise FileNotFoundError(f"Файл страницы из hhk не найден: {htm_path}")
                text_cache[htm_path] = read_text(htm_path, page_encoding)
            text = text_cache[htm_path]

            # re.escape добавлен против старых голых regex: якоря — простые id,
            # поведение на валидных данных идентично, но битый якорь не уронит regex
            match = re.search(rf'id="{re.escape(anchor)}"', text)
            if match is None:
                continue  # ИСТОРИК: заголовок без id в файле — молча пропускаем
            # §4.4 (исправлено): 0-based индекс строки, куда вставляется <a id>
            line_number = len(text[0 : match.end()].split("\n")) - 1

            file_key = Path(file_part).stem  # старый os.path.splitext(file)[0]
            by_file.setdefault(file_key, {})[anchor] = AnchorEntry(line_number, title)

        return Anchors(by_file)
