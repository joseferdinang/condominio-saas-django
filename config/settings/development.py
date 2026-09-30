"""Local and Docker Compose development settings."""

import os

from .base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", False)  # noqa: F405
ALLOWED_HOSTS = env_list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,web"
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
