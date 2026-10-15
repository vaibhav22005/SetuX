import os
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "donors",
    "inventory",
    "rewards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=600,
            conn_health_checks=True,
            engine=os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []
LOGIN_URL = "/login/"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
CELERY_TIMEZONE = TIME_ZONE
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_TRACK_STARTED = True
FIREBASE_ENABLED = os.environ.get("FIREBASE_ENABLED", "0") == "1"
FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")
FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
    "appId": os.environ.get("FIREBASE_APP_ID", ""),
}
FIREBASE_VAPID_KEY = os.environ.get("FIREBASE_VAPID_KEY", "")
FIREBASE_WEB_ENABLED = bool(
    FIREBASE_ENABLED
    and FIREBASE_CREDENTIALS_PATH
    and all(FIREBASE_WEB_CONFIG.values())
    and FIREBASE_VAPID_KEY
)
CELERY_BEAT_SCHEDULE = {
    "notify-open-shortages-every-five-minutes": {
        "task": "inventory.tasks.notify_open_shortages",
        "schedule": 300.0,
    },
    "dispatch-daily-inventory-risk-alerts": {
        "task": "inventory.tasks.dispatch_inventory_risk_alerts",
        "schedule": crontab(hour=8, minute=0),
    },
}
if FIREBASE_ENABLED:
    CELERY_BEAT_SCHEDULE["dispatch-pending-firebase-push-alerts"] = {
        "task": "rewards.tasks.dispatch_pending_firebase_alerts",
        "schedule": 60.0,
    }