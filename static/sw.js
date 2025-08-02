// Service Worker for Mavi Petshop PWA
const CACHE_NAME = 'mavipetshop-v1.2.0';
const urlsToCache = [
  '/',
  '/static/modern.css',
  '/static/app.js',
  '/contact',
  '/order-track',
  '/cart',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'
];

// Install Service Worker
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Caching app shell');
        return cache.addAll(urlsToCache);
      })
      .then(() => {
        console.log('[SW] Skip waiting');
        return self.skipWaiting();
      })
  );
});

// Activate Service Worker
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('[SW] Claiming clients');
      return self.clients.claim();
    })
  );
});

// Fetch Strategy - Network First with Cache Fallback
self.addEventListener('fetch', (event) => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  // Skip external requests
  if (!event.request.url.startsWith(self.location.origin)) {
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then((cache) => {
      return fetch(event.request)
        .then((response) => {
          // If successful, clone and cache the response
          if (response.status === 200) {
            cache.put(event.request, response.clone());
          }
          return response;
        })
        .catch(() => {
          // If network fails, try to get from cache
          return cache.match(event.request).then((cached) => {
            if (cached) {
              return cached;
            }
            
            // If not in cache, return offline page for navigation requests
            if (event.request.mode === 'navigate') {
              return cache.match('/offline') || new Response(
                `<!DOCTYPE html>
                <html>
                <head><title>Çevrimdışı - Mavi Petshop</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                  <h1>🐾 Bağlantı Yok</h1>
                  <p>İnternet bağlantınızı kontrol edin ve tekrar deneyin.</p>
                  <button onclick="window.location.reload()">Tekrar Dene</button>
                </body>
                </html>`,
                { headers: { 'Content-Type': 'text/html' } }
              );
            }
            
            // For other requests, return a generic offline response
            return new Response('Çevrimdışı', { status: 503 });
          });
        });
    })
  );
});

// Background Sync for offline actions
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);
  
  if (event.tag === 'cart-sync') {
    event.waitUntil(syncCart());
  }
  
  if (event.tag === 'contact-sync') {
    event.waitUntil(syncContactForm());
  }
});

// Push Notifications
self.addEventListener('push', (event) => {
  console.log('[SW] Push received:', event);
  
  const options = {
    body: event.data ? event.data.text() : 'Yeni bir bildiriminiz var!',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: 'İncele',
        icon: '/static/icons/checkmark.png'
      },
      {
        action: 'close',
        title: 'Kapat',
        icon: '/static/icons/xmark.png'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('🐾 Mavi Petshop', options)
  );
});

// Notification Click
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification click received.');

  event.notification.close();

  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/')
    );
  } else if (event.action === 'close') {
    // Just close the notification
    return;
  } else {
    // Default action
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// Helper functions for background sync
async function syncCart() {
  try {
    const cache = await caches.open('cart-sync');
    const cachedRequests = await cache.keys();
    
    for (const request of cachedRequests) {
      try {
        await fetch(request);
        await cache.delete(request);
        console.log('[SW] Cart sync successful');
      } catch (error) {
        console.log('[SW] Cart sync failed, will retry later');
      }
    }
  } catch (error) {
    console.log('[SW] Cart sync error:', error);
  }
}

async function syncContactForm() {
  try {
    const cache = await caches.open('contact-sync');
    const cachedRequests = await cache.keys();
    
    for (const request of cachedRequests) {
      try {
        await fetch(request);
        await cache.delete(request);
        console.log('[SW] Contact form sync successful');
      } catch (error) {
        console.log('[SW] Contact form sync failed, will retry later');
      }
    }
  } catch (error) {
    console.log('[SW] Contact form sync error:', error);
  }
}

// Share Target API
self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/share-target') && event.request.method === 'POST') {
    event.respondWith(Response.redirect('/'));
  }
});

console.log('[SW] Service Worker loaded successfully');