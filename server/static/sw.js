// Minimal service worker — exists mainly so Chrome/Android treats Pulse as
// an installable app (its installability check requires a controlling SW
// with a fetch handler; iOS/Safari doesn't need this at all, but doesn't
// mind it either). Deliberately not a real offline cache: this dashboard
// is live monitoring data, so serving a stale cached response instead of
// the network would be actively misleading. Every request just passes
// straight through to the network, same as if there were no SW at all.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => { e.respondWith(fetch(e.request)); });
