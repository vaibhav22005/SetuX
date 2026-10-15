importScripts("https://www.gstatic.com/firebasejs/11.10.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging-compat.js");

firebase.initializeApp({{ firebase_web_config_json|safe }});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
    const data = payload.data || {};
    self.registration.showNotification(data.title || "SetuX alert", {
        body: data.body || "There is a new update on your donor dashboard.",
        data: { url: data.url || "/dashboard/" },
    });
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    event.waitUntil(clients.openWindow(event.notification.data.url));
});
