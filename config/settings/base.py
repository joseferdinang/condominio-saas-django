"""Settings shared by every environment."""

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_secret(name: str, default: str = "") -> str:
    """Read a secret from either the environment or a mounted secret file."""
    filename = os.getenv(f"{name}_FILE")
    if filename:
        if os.getenv(name):
            raise ImproperlyConfigured(f"Define solo {name} o {name}_FILE.")
        try:
            return Path(filename).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"No se pudo leer {name}_FILE.") from exc
    return os.getenv(name, default)


def postgres_database_config() -> dict[str, object]:
    """Read Neon-style PostgreSQL URLs or the existing Compose variables."""
    database_url = os.getenv("DATABASE_URL")
    connection_options: dict[str, object] = {
        "connect_timeout": env_int("POSTGRES_CONNECT_TIMEOUT", 5),
    }

    if database_url:
        try:
            parsed = urlsplit(database_url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ImproperlyConfigured("DATABASE_URL no tiene un formato PostgreSQL válido.") from exc
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise ImproperlyConfigured("DATABASE_URL debe usar el esquema PostgreSQL.")
        if not host or not parsed.path.strip("/") or not parsed.username:
            raise ImproperlyConfigured(
                "DATABASE_URL debe incluir usuario, host y nombre de base de datos."
            )

        query = parse_qs(parsed.query)
        sslmode = query.get("sslmode", ["require"])[-1]
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ImproperlyConfigured("DATABASE_URL debe exigir una conexión PostgreSQL cifrada.")
        connection_options["sslmode"] = sslmode
        if "channel_binding" in query:
            connection_options["channel_binding"] = query["channel_binding"][-1]

        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": host,
            "PORT": str(port or 5432),
            "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 0),
            "OPTIONS": connection_options,
        }

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "condominio"),
        "USER": os.getenv("POSTGRES_USER", "condominio"),
        "PASSWORD": env_secret("POSTGRES_PASSWORD", "condominio_dev"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 0),
        "OPTIONS": connection_options,
    }


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY", "development-only-secret-key-change-before-production"
)
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "buildings.apps.BuildingsConfig",
    "people.apps.PeopleConfig",
    "finance.apps.FinanceConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.idle.IdleSessionMiddleware",
    "core.audit_middleware.AuditActorMiddleware",
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
                "accounts.context_processors.navegacion_portal",
                "accounts.idle.idle_session_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Enforced on the server, independently of browser JavaScript.
SESSION_IDLE_TIMEOUT = 300
SESSION_COOKIE_AGE = SESSION_IDLE_TIMEOUT

DATABASES = {"default": postgres_database_config()}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Santo_Domingo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"
DEFAULT_FROM_EMAIL = os.getenv(
    "DJANGO_DEFAULT_FROM_EMAIL", "Portal de condominios <no-reply@localhost>"
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("DJANGO_EMAIL_PORT", 25)
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("DJANGO_EMAIL_TIMEOUT", 10)
