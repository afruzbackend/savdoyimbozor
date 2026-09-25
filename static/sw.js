/* Service worker — ILDIZDAN (/sw.js) beriladi, shuning uchun butun ilovani boshqaradi.
   (Ilgari /static/sw.js edi — doirasi faqat /static/ bo'lib, hech bir sahifani
   boshqarmasdi: internet yo'q paytda sotuv sahifasi umuman ochilmasdi.)

   - Statik fayllar: avval tarmoq, bo'lmasa kesh.
   - Sotuv / skaner sahifalari: avval tarmoq; internet yo'q bo'lsa — oxirgi ochilgan nusxa.
     Sotuvlar localStorage navbatiga tushadi va tarmoq qaytganda yuboriladi (components.js).
   - Chiqish (logout/login): sahifa keshi o'chiriladi (umumiy qurilmada boshqasi ko'rmasin). */
const STATIC = "bn-static-v3";
const PAGES = "bn-pages-v1";
const OFFLINE_PAGES = ["/sotuv/", "/skaner/"];
const ASSETS = [
  "/static/css/tokens.css",
  "/static/css/components.css",
  "/static/js/alpine.min.js",
  "/static/js/htmx.min.js",
  "/static/js/components.js",
  "/static/js/ru.js",
  "/static/js/i18n.js",
  "/static/icons/sprite.svg",
  "/static/manifest.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(STATIC).then((c) => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== STATIC && k !== PAGES).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

function networkFirst(req, cacheName, key) {
  return fetch(req)
    .then((res) => {
      if (res.ok && !res.redirected) {
        const copy = res.clone();
        caches.open(cacheName).then((c) => c.put(key || req, copy));
      }
      return res;
    })
    .catch(() => caches.match(key || req));
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return; // POST/API — to'g'ridan-to'g'ri tarmoqqa
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === "navigate") {
    if (url.pathname === "/logout/" || url.pathname === "/login/") {
      e.waitUntil(caches.delete(PAGES));
      return;
    }
    if (OFFLINE_PAGES.includes(url.pathname)) {
      e.respondWith(networkFirst(req, PAGES, url.pathname));
    }
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(networkFirst(req, STATIC));
  }
});
