const CACHE = "qsp-pwa-ca86158bc3a9";
const PRECACHE = ["./", "default.css", "images/help_ballad.jpg", "images/help_input_window.png", "images/help_level13.jpg", "images/help_msgbox.png", "images/help_qspblank2.jpg", "images/help_wiki_logo.png", "images/help_window_msg.png", "images/image.png", "images/qgen.png", "index.html", "manifest.webmanifest", "search.json", "spa.css"];

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
});