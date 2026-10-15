import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {
    getMessaging,
    getToken,
    isSupported,
    onMessage,
    deleteToken,
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging.js";

const button = document.querySelector("#enable-push-notifications");
const disableButton = document.querySelector("#disable-push-notifications");
const status = document.querySelector("#push-notification-status");
const configElement = document.querySelector("#firebase-push-config");

if (button && disableButton && status && configElement) {
    const config = JSON.parse(configElement.textContent);
    const tokenStorageKey = "setux-fcm-token";
    let messaging;
    let unsubscribeForegroundMessage;

    async function getCsrfToken() {
        const cookie = document.cookie
            .split("; ")
            .find((item) => item.startsWith("csrftoken="))
            ?.split("=")
            .slice(1)
            .join("=");
        if (!cookie) {
            throw new Error("The security token is missing. Reload the page and try again.");
        }
        return decodeURIComponent(cookie);
    }

    async function postToken(url, token) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-CSRFToken": await getCsrfToken(),
            },
            body: new URLSearchParams({ token }),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Could not update push notification settings.");
        }
        return result;
    }

    async function getMessagingClient() {
        if (!(await isSupported())) {
            throw new Error("This browser does not support Firebase web notifications.");
        }
        if (!messaging) {
            const app = initializeApp(config.webConfig);
            messaging = getMessaging(app);
        }
        return messaging;
    }

    async function enableForegroundNotifications(messagingClient) {
        if (unsubscribeForegroundMessage) {
            return;
        }
        unsubscribeForegroundMessage = onMessage(messagingClient, (payload) => {
            const data = payload.data || {};
            status.textContent = data.body || "You have a new SetuX alert.";
            if (Notification.permission === "granted") {
                new Notification(payload.notification?.title || "SetuX donor alert", {
                    body: data.body || payload.notification?.body || "You have a new SetuX alert.",
                });
            }
        });
    }

    if (
        "Notification" in window
        && localStorage.getItem(tokenStorageKey)
        && Notification.permission === "granted"
    ) {
        getMessagingClient()
            .then(enableForegroundNotifications)
            .catch((error) => {
                status.textContent = error instanceof Error
                    ? error.message
                    : "Could not initialize push notifications.";
            });
    }

    button.addEventListener("click", async () => {
        button.disabled = true;
        status.textContent = "Requesting browser notification permission…";

        try {
            if (!("Notification" in window)) {
                throw new Error("This browser does not support notifications.");
            }
            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
                throw new Error("Notification permission was not granted.");
            }

            const registration = await navigator.serviceWorker.register(
                "/firebase-messaging-sw.js",
            );
            const messagingClient = await getMessagingClient();
            const token = await getToken(messagingClient, {
                vapidKey: config.vapidKey,
                serviceWorkerRegistration: registration,
            });
            if (!token) {
                throw new Error("Firebase did not return a browser registration token.");
            }

            localStorage.setItem(tokenStorageKey, token);
            try {
                await postToken(config.registerUrl, token);
            } catch (error) {
                localStorage.removeItem(tokenStorageKey);
                throw error;
            }
            await enableForegroundNotifications(messagingClient);
            status.textContent = "Push alerts are enabled for this browser.";
            button.textContent = "Push alerts enabled";
        } catch (error) {
            status.textContent = error instanceof Error
                ? error.message
                : "Could not enable push alerts.";
            button.disabled = false;
        }
    });

    disableButton.addEventListener("click", async () => {
        disableButton.disabled = true;
        status.textContent = "Disabling push alerts on this browser…";

        try {
            const token = localStorage.getItem(tokenStorageKey);
            if (token) {
                const messagingClient = await getMessagingClient();
                await deleteToken(messagingClient);
                await postToken(config.unregisterUrl, token);
                localStorage.removeItem(tokenStorageKey);
                if (unsubscribeForegroundMessage) {
                    unsubscribeForegroundMessage();
                    unsubscribeForegroundMessage = null;
                }
            }
            status.textContent = "Push alerts are disabled on this browser.";
        } catch (error) {
            status.textContent = error instanceof Error
                ? error.message
                : "Could not disable push alerts.";
        } finally {
            disableButton.disabled = false;
        }
    });
}
