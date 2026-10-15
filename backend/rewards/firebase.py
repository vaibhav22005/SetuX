from pathlib import Path

import firebase_admin
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from firebase_admin import credentials, messaging


def get_firebase_app():
    if not settings.FIREBASE_ENABLED:
        raise ImproperlyConfigured("Firebase push is disabled; set FIREBASE_ENABLED=1 to enable it.")
    if not settings.FIREBASE_CREDENTIALS_PATH:
        raise ImproperlyConfigured("FIREBASE_CREDENTIALS_PATH is required when Firebase push is enabled.")
    credentials_path = Path(settings.FIREBASE_CREDENTIALS_PATH)
    if not credentials_path.is_file():
        raise ImproperlyConfigured(
            f"Firebase service-account file was not found: {credentials_path}"
        )

    try:
        return firebase_admin.get_app("setux")
    except ValueError:
        return firebase_admin.initialize_app(
            credentials.Certificate(str(credentials_path)),
            name="setux",
        )


def send_push_message(*, token, title, body, url="/dashboard/"):
    message = messaging.Message(
        data={"title": title[:200], "body": body[:1000], "url": url},
        token=token,
    )
    return messaging.send(message, app=get_firebase_app())
