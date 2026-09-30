"""Production settings for a future HTTPS deployment behind Caddy."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
MIDDLEWARE = [MIDDLEWARE[0], "core.middleware.RequestSizeLimitMiddleware", *MIDDLEWARE[1:]]  # noqa: F405
SECRET_KEY = env_secret("DJANGO_SECRET_KEY")  # noqa: F405
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405

if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Producción exige una SECRET_KEY aleatoria de al menos 50 caracteres.")
if not ALLOWED_HOSTS or any("*" in host or host.startswith(".") for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS debe contener hosts explícitos.")
if not CSRF_TRUSTED_ORIGINS or any(
    not origin.startswith("https://") or "*" in origin for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured("Configura orígenes CSRF HTTPS explícitos.")
if len(DATABASES["default"].get("PASSWORD", "")) < 24:  # noqa: F405
    raise ImproperlyConfigured("Producción exige una contraseña PostgreSQL de al menos 24 caracteres.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 3600)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(  # noqa: F405
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)  # noqa: F405
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700
EMAIL_HOST_PASSWORD = env_secret("DJANGO_EMAIL_HOST_PASSWORD")  # noqa: F405
if EMAIL_USE_TLS and EMAIL_USE_SSL:  # noqa: F405
    raise ImproperlyConfigured("SMTP debe usar TLS o SSL, no ambos.")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        name: {"handlers": ["console"], "level": "WARNING", "propagate": False}
        for name in ("django", "weasyprint", "fontTools")
    },
}

OBJECT_STORAGE_BACKEND = os.getenv("OBJECT_STORAGE_BACKEND", "filesystem").strip().lower()
if OBJECT_STORAGE_BACKEND == "s3":
    object_storage_required = (
        "AWS_STORAGE_BUCKET_NAME",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ENDPOINT_URL_S3",
        "AWS_REGION",
    )
    missing_object_storage = [name for name in object_storage_required if not os.getenv(name)]
    if missing_object_storage:
        raise ImproperlyConfigured(
            "Object Storage S3 requiere estas variables: " + ", ".join(missing_object_storage)
        )
    default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.environ["AWS_STORAGE_BUCKET_NAME"],
            "access_key": os.environ["AWS_ACCESS_KEY_ID"],
            "secret_key": os.environ["AWS_SECRET_ACCESS_KEY"],
            "endpoint_url": os.environ["AWS_ENDPOINT_URL_S3"],
            "region_name": os.environ["AWS_REGION"],
            "addressing_style": "path",
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
            "location": "media",
        },
    }
elif OBJECT_STORAGE_BACKEND == "filesystem":
    default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
else:
    raise ImproperlyConfigured("OBJECT_STORAGE_BACKEND debe ser 'filesystem' o 's3'.")

STORAGES = {
    "default": default_storage,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        "OPTIONS": {
            "file_permissions_mode": 0o644,
            "directory_permissions_mode": 0o755,
        },
    },
}
