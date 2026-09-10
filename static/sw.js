// Oddiy service worker — PWA o'rnatilishi va statik fayllar keshi uchun.
const CACHE = "savdo-nazorat-v1";
const ASSETS = ["/static/css/style.css", "/static/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  // Faqat GET statik fayllarni keshdan beramiz; POST/API to'g'ridan-to'g'ri tarmoqqa
  if (req.method !== "GET" || !req.url.includes("/static/")) return;
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }).catch(() => hit))
  );
});
