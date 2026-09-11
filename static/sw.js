/* Service worker — PWA o'rnatilishi va statik keshlash. Offline sotuv navbati
   sale.html/scan.html ichida localStorage bilan boshqariladi (bu SW faqat statik). */
const CACHE = "bozor-nazorat-v1";
const ASSETS = [
  "/static/css/tokens.css",
  "/static/css/components.css",
  "/static/js/alpine.min.js",
  "/static/js/htmx.min.js",
  "/static/js/components.js",
  "/static/js/i18n.js",
  "/static/icons/sprite.svg",
  "/static/manifest.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  // Faqat GET statik fayllar keshdan; POST/API to'g'ridan-to'g'ri tarmoqqa
  if (req.method !== "GET" || !req.url.includes("/static/")) return;
  e.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        }).catch(() => hit)
    )
  );
});
