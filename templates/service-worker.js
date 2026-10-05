{% load static %}/* ============================================================
   SignDocs Service Worker
   - Pre-caches the app shell so the UI loads instantly / offline
   - Stale-while-revalidate for static assets and CDN app-shell files
   - Network-first for navigations with an offline fallback page
   - NEVER caches authenticated pages, /media/, or /admin/
   Bump VERSION below whenever the caching strategy changes.
   ============================================================ */

var VERSION = 'v1.0.0';
var STATIC_CACHE = 'signdocs-static-' + VERSION;
var RUNTIME_CACHE = 'signdocs-runtime-' + VERSION;

var STATIC_BASE = new URL('{% get_static_prefix %}', self.location).pathname;
var OFFLINE_URL = new URL('{% static "offline.html" %}', self.location).href;

// Cross-origin app-shell hosts (CDN Bootstrap + Google Fonts) cached at runtime.
var CDN_HOSTS = ['cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];

// Assets pre-cached on install. Resolved to absolute URLs so matches always hit.
var PRECACHE_URLS = [
    '{% static "offline.html" %}',
    '{% static "css/style.css" %}',
    '{% static "js/main.js" %}',
    '{% static "icons/icon-192x192.png" %}',
    '{% static "icons/icon-512x512.png" %}',
    '{% static "icons/apple-touch-icon.png" %}',
    '/manifest.webmanifest'
].map(function (path) {
    return new URL(path, self.location).href;
});

// --- Install: pre-cache the app shell -------------------------------------
self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(STATIC_CACHE).then(function (cache) {
            return Promise.all(
                PRECACHE_URLS.map(function (url) {
                    return cache.add(new Request(url, { cache: 'reload' })).catch(function () {
                        // Ignore individual failures (e.g. an asset removed upstream).
                    });
                })
            );
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

// --- Activate: drop old caches and take control ---------------------------
self.addEventListener('activate', function (event) {
    var keep = [STATIC_CACHE, RUNTIME_CACHE];
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.map(function (key) {
                    if (keep.indexOf(key) === -1) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

// --- Fetch routing --------------------------------------------------------
self.addEventListener('fetch', function (event) {
    var request = event.request;

    // Only handle simple GET requests.
    if (request.method !== 'GET') {
        return;
    }

    var url = new URL(request.url);

    // Never touch sensitive or admin traffic.
    if (
        url.origin === self.location.origin &&
        (url.pathname.indexOf('/media/') === 0 || url.pathname.indexOf('/admin/') === 0)
    ) {
        return;
    }

    // Page navigations: always hit the network, fall back to the offline page.
    if (request.mode === 'navigate') {
        event.respondWith(networkFirst(request));
        return;
    }

    // Same-origin static assets: stale-while-revalidate.
    if (url.origin === self.location.origin && url.pathname.indexOf(STATIC_BASE) === 0) {
        event.respondWith(staleWhileRevalidate(request, STATIC_CACHE));
        return;
    }

    // CDN app-shell assets: stale-while-revalidate.
    if (CDN_HOSTS.indexOf(url.hostname) !== -1) {
        event.respondWith(staleWhileRevalidate(request, RUNTIME_CACHE));
        return;
    }

    // Everything else (media, API, docs): straight to the network.
});

// --- Strategies -----------------------------------------------------------
function networkFirst(request) {
    return fetch(request).catch(function () {
        return caches.match(OFFLINE_URL).then(function (cached) {
            if (cached) {
                return cached;
            }
            return new Response('You are offline.', {
                status: 503,
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
            });
        });
    });
}

function staleWhileRevalidate(request, cacheName) {
    return caches.open(cacheName).then(function (cache) {
        return cache.match(request).then(function (cached) {
            var network = fetch(request).then(function (response) {
                // Cache successful and opaque (no-cors CDN) responses.
                if (response && (response.ok || response.type === 'opaque')) {
                    cache.put(request, response.clone());
                }
                return response;
            }).catch(function () {
                return cached;
            });
            return cached || network;
        });
    });
}

// --- Allow the page to trigger an immediate update ------------------------
self.addEventListener('message', function (event) {
    if (event.data === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
