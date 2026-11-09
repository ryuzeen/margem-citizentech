// Service worker do Margem: guarda o app (casca) e o último estado da API para uso sem internet.
const VERSAO = "margem-v4";
const CASCA = [
  "./", "index.html", "app.html", "console.html", "manifest.webmanifest",
  "css/tokens.css", "css/base.css", "css/componentes.css", "css/app.css", "css/console.css", "css/landing.css",
  "js/app.js", "js/console.js", "js/landing.js", "js/api.js", "js/niveis.js", "js/pref.js",
  "js/ui/util.js", "js/ui/regua.js", "js/ui/mapa.js", "js/ui/graficos.js",
  "js/demo/motor.js", "js/demo/triagem.js", "js/demo/territorio.js",
  "vendor/lucide/sprite.js", "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css",
  "vendor/fonts/atkinson-next-var.woff2", "vendor/fonts/archivo-var.woff2",
  "vendor/fonts/plex-mono-400.woff2", "vendor/fonts/plex-mono-500.woff2", "vendor/fonts/plex-mono-600.woff2",
  "img/curvas.svg", "img/curvas-escuro.svg", "img/icone.svg", "img/icone-192.png",
];
// Rotas da API cujo último resultado fica guardado (rede primeiro, cache se cair)
const API_CACHE = /\/api\/v1\/(territorio|risco\/atual|alertas|iot\/estacoes|ocorrencias)/;

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSAO).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.endsWith("/api/v1/stream")) return; // SSE nunca passa pelo cache
  if (API_CACHE.test(url.pathname)) {
    ev.respondWith(fetch(req).then((r) => { if (r.ok) { const cp = r.clone(); caches.open(VERSAO).then((c) => c.put(req, cp)); } return r; })
      .catch(() => caches.match(req).then((r) => r ?? new Response(JSON.stringify({ erro: { codigo: "sem_conexao", mensagem: "Sem internet." } }), { status: 503, headers: { "Content-Type": "application/json" } }))));
    return;
  }
  if (url.origin !== location.origin) return; // tiles do OpenStreetMap: só rede
  // Casca: rede primeiro (sempre a versão nova quando há internet); sem rede, usa o cache
  ev.respondWith(fetch(req).then((r) => { if (r.ok) { const cp = r.clone(); caches.open(VERSAO).then((c) => c.put(req, cp)); } return r; })
    .catch(() => caches.match(req, { ignoreSearch: true }).then((r) => r ?? caches.match("app.html"))));
});
