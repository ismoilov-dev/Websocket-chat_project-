"""
config/settings.py

Loyiha sozlamalari. Barcha maxfiy qiymatlar (SECRET_KEY, DB paroli, Redis manzili)
kod ichida emas, `.env` faylida saqlanadi va `django-environ` orqali o'qiladi.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# .env faylini o'qish
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------------------
# Ilovalar
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # `daphne` eng birinchi turishi shart: u `runserver` buyrug'ini
    # ASGI serverga almashtiradi (WSGI emas), shunda WebSocket ishlaydi.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "channels",
    # Loyiha ilovalari
    "accounts",
    "chat",
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

# WSGI - oddiy HTTP uchun (gunicorn va h.k.).
WSGI_APPLICATION = "config.wsgi.application"
# ASGI - HTTP + WebSocket uchun. Channels aynan shu nuqtadan ishga tushadi.
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database: DATABASE_URL orqali SQLite yoki PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# ---------------------------------------------------------------------------
# Custom User model (loyiha boshida belgilash shart!)
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "chat:index"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Til va vaqt
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True  # DB'da vaqt UTC'da saqlanadi, brauzer esa mahalliy vaqtga o'giradi

# ---------------------------------------------------------------------------
# Static fayllar
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
# Frontend shu domenning o'zida turgani uchun SessionAuthentication yetarli:
# brauzer session cookie'ni avtomatik yuboradi, POST so'rovlar esa CSRF token talab qiladi.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# ---------------------------------------------------------------------------
# Channels + Redis Channel Layer
# ---------------------------------------------------------------------------
# Channel Layer - turli WebSocket connectionlar (hatto turli server
# processlardagi) bir-biriga xabar yuborishi uchun "pochta xizmati".
# Redis shu pochta xizmatining ombori vazifasini bajaradi.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("REDIS_URL", default="redis://127.0.0.1:6379/0")],
            "capacity": 1500,  # har bir kanal navbatidagi maksimal xabarlar soni
            "expiry": 10,      # yetkazilmagan xabar necha soniyada o'chadi
        },
    },
}

# ---------------------------------------------------------------------------
# Xavfsizlik (production uchun)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True  # JS session cookie'ni o'qiy olmaydi
CSRF_COOKIE_HTTPONLY = False    # JS CSRF tokenni fetch() uchun o'qishi kerak

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# Logging: consumer'dagi xatolarni terminalda ko'rish uchun
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "chat": {"handlers": ["console"], "level": "INFO"},
    },
}
