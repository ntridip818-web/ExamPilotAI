const CACHE_NAME = "exampilotai-v1";
const ASSETS = ["./", "./index.html", "./css/style.css", "./js/app.js", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.url.includes("/exams") || event.request.url.includes("/users")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
