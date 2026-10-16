# pyright: reportUnknownMemberType=false
"""Статические заготовки PWA-оболочки (Фаза 8): head-добавки, вкладка поиска, рантайм-JS.

PWA — это тот же документ-одностраничник (:data:`render.spa.SPA_PAGE`), дополненный
тремя вещами: подключение манифеста +service worker, отдельная вкладка «Поиск» в левой
панели и рантайм, читающий собранный ``search.json``. Всё здесь — текст, который
вставляется в уже собранный ``index.html``; никакой сетевой/файловой логики (она в
``build.py``).

Рантайм намеренно крошечный и без внешних библиотек (решение по поиску — «свой индекс
из Python»): JS только токенизирует запрос так же, как ``search.tokenize`` (юникодный
диапазон кириллицы прописан явно, т.к. в JS ``\\w`` не включает ``а-я``), ищет
по готовым postings и отдаёт ссылки ``#slug`` уже живущему hash-роутеру.
"""

from __future__ import annotations

# Что добавляется в <head> поверх SPA-шаблона. Пути относительные — работают и в
# корне домена, и в под-пути GitHub Pages (/<repo>/), где index.html лежит в корне.
HEAD_LINKS_HTML = """<link rel="manifest" href="manifest.webmanifest" />
<meta name="theme-color" content="{theme_color}" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<link rel="apple-touch-icon" href="{icon}" />"""

# Третья вкладка левой панели (кнопка + панель). Кнопка помечена data-tab="search",
# поэтому штатный SPA-хэндлер setTab/clickTab подхватывает её без правки роутера.
SEARCH_TAB_HTML = """<button type="button" class="spa-tab" data-tab="search">Поиск</button>
"""
SEARCH_PANEL_HTML = """<nav class="spa-panel" id="search">
<input type="search" id="searchInput" placeholder="Поиск по справке…" autocomplete="off" />
<div id="searchResults" class="spa-search-results"></div>
</nav>
"""

# Рантайм поиска + регистрация service worker. Вставляется перед </body>.
RUNTIME_JS = """<script>
(function () {
  var INDEX_URL = "search.json";
  var input = document.getElementById("searchInput");
  var box = document.getElementById("searchResults");
  if (!input || !box) { return; }
  var index = null, loading = false;

  function load() {
    if (index || loading) { return; }
    loading = true;
    fetch(INDEX_URL)
      .then(function (r) { return r.json(); })
      .then(function (data) { index = data; loading = false; run(); })
      .catch(function () { loading = false; box.textContent = "Поиск недоступен."; });
  }

  // как search.tokenize: нижний регистр, токены >= 3; \\w в JS не знает кириллицу —
  // диапазон \\u0400-\\u04FF добавлен явно, иначе русские запросы не распались бы
  function tokenize(t) {
    var m = t.toLowerCase().match(/[\\w\\u0400-\\u04FF]+/g);
    return m ? m.filter(function (x) { return x.length >= 3; }) : [];
  }

  function run() {
    if (!index) { return; }
    var terms = tokenize(input.value);
    box.innerHTML = "";
    if (!terms.length) { return; }
    var scores = {}, missing = false;
    for (var i = 0; i < terms.length && !missing; i++) {
      var post = index.postings[terms[i]];
      if (!post) { missing = true; break; }
      for (var k in post) {
        if (Object.prototype.hasOwnProperty.call(post, k)) { scores[k] = (scores[k] || 0) + post[k]; }
      }
    }
    if (missing) { return; }  // AND-семантика: все термины должны встречаться
    var hits = Object.keys(scores).map(function (k) { return { i: +k, s: scores[k] }; });
    hits.sort(function (a, b) { return b.s - a.s; });
    hits = hits.slice(0, 30);
    if (!hits.length) { box.textContent = "Ничего не найдено."; return; }
    var ul = document.createElement("ul");
    for (var j = 0; j < hits.length; j++) {
      var d = index.docs[hits[j].i];
      var a = document.createElement("a");
      a.href = "#" + d.slug;
      a.textContent = d.title || d.slug;
      var li = document.createElement("li");
      li.appendChild(a);
      ul.appendChild(li);
    }
    box.appendChild(ul);
  }

  input.addEventListener("input", function () { load(); run(); });
  // предзагрузим индекс при первом открытии вкладки «Поиск»
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.getAttribute && t.getAttribute("data-tab") === "search") { load(); }
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("sw.js").catch(function () {});
    });
  }
})();
</script>"""

# Каркас service worker. Подстановки __CACHE_NAME__ и __PRECACHE__ заполняет build.py
# (детерминированный кэш-бастинг по содержимому сборки). Замены — маркерами, а не str.format,
# чтобы фигурные скобки JS-кода не воспринимались как поля шаблонизатора. Стратегия:
# precache на install + cache-first для same-origin GET; наружные запросы (живая вики,
# target=_blank) не перехватываем.
SW_JS = """const CACHE = "qsp-pwa-__CACHE_NAME__";
const PRECACHE = __PRECACHE__;

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") { return; }
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) { return; }
  e.respondWith(
    caches.match(req).then((hit) =>
      hit ||
      fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return resp;
      }).catch(() => hit)
    )
  );
});"""
