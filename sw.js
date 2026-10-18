// Boletus: funciona sense cobertura al bosc.
// L'app i les dades: primer la xarxa (per tenir sempre l'última versió), si no, la còpia guardada.
// Mapes i fonts: la còpia guardada, i s'actualitza de fons.
const APP = 'cb-app-v9', MAPS = 'cb-maps-v1';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'vendor/leaflet.js', 'vendor/leaflet.css',
  'icons/logo.svg', 'icons/icon-192.png', 'icons/apple-touch-icon.png',
  'data/meta.json', 'data/grid.bin', 'data/hist.json', 'data/now.json', 'data/llocs.json', 'data/obsol.png', 'data/region.json', 'data/reg_cares.png', 'data/reg_acid.png', 'data/reg_info.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(APP).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== APP && k !== MAPS).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.hostname.endsWith('open-meteo.com')) return; // la pluja la gestiona l'app
  if (url.origin === location.origin) {
    // 'no-cache': sempre pregunta al servidor si hi ha versió nova (així els canvis arriben de seguida)
    e.respondWith(fetch(e.request, { cache: 'no-cache' }).then(r => {
      if (r.ok) { const cp = r.clone(); caches.open(APP).then(c => c.put(e.request, cp)); }
      return r;
    }).catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || caches.match('index.html'))));
    return;
  }
  if (url.hostname === 'geoserveis.icgc.cat' || url.hostname === 'server.arcgisonline.com' || url.hostname.endsWith('gstatic.com') || url.hostname.endsWith('googleapis.com')) {
    e.respondWith(caches.open(MAPS).then(async c => {
      const hit = await c.match(e.request);
      const net = fetch(e.request).then(r => { if (r.ok || r.type === 'opaque') c.put(e.request, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
  }
});
