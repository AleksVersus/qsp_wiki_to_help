"""PWA-рендерер (Фаза 8): надстройка над одностраничником для хостинга.

Тот же контент-документ, что у :mod:`render.spa`, плюс манифест, service worker и
клиентский полнотекстовый поиск. Разложено по ответственности:

- :mod:`pwa.build`   — оркестратор ``render_pwa`` (shell-правки, запись артефактов);
- :mod:`pwa.search`  — сборка инвертированного индекса ``search.json`` (чистая функция);
- :mod:`pwa.assets`  — переписывание ``url()`` в CSS на origin вики (§4.13);
- :mod:`pwa.shell`   — текстовые заготовки (head, вкладка поиска, рантайм-JS, sw.js).
"""

from __future__ import annotations

from .build import render_pwa

__all__ = ["render_pwa"]
