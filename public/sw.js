/* Hustlempires service worker: keeps the game's screens on the phone so the app opens instantly
   and shows a friendly message when offline. Game data (/api/) always goes to the server. */
const CACHE = 'hustle-v6';
const SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png', '/icons/favicon-48.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin') || url.pathname.endsWith('.json')) return;
  if (req.mode === 'navigate') {
    // always try the network first, so players get new versions straight away
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put('/', copy)); }
      return res;
    }).catch(() => caches.match('/')));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
    return res;
  })));
});

/* Notifications: show the nudge, and open the game when it is tapped. */
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Hustlempires', {
    body: d.body || 'Your empire is waiting.',
    icon: '/icons/icon-192.png',
    badge: '/icons/favicon-48.png',
    tag: d.tag || 'hustle',
    data: { url: d.url || '/', id: d.id || null }
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const d = e.notification.data || {};
  const opened = d.id ? fetch('/api/push/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: d.id }) }).catch(() => {}) : Promise.resolve();
  e.waitUntil(Promise.all([opened, self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    const w = list.find(c => new URL(c.url).origin === location.origin);
    if (w) return w.focus();
    return self.clients.openWindow('/');
  })]));
});
