"""Short-lived HTTPS preview through a Cloudflare Quick Tunnel."""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env_secret("DJANGO_SECRET_KEY")  # noqa: F405
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405

if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured("La vista previa exige una SECRET_KEY aleatoria.")
if not ALLOWED_HOSTS or any("*" in host or host.startswith(".") for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("La vista previa exige hosts explícitos.")
if not CSRF_TRUSTED_ORIGINS or any(
    urlsplit(origin).scheme != "https" or urlsplit(origin).hostname not in ALLOWED_HOSTS
    for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured("Configura orígenes CSRF HTTPS para los hosts permitidos.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
MIDDLEWARE = [MIDDLEWARE[0], "core.middleware.RequestSizeLimitMiddleware", *MIDDLEWARE[1:]]  # noqa: F405
