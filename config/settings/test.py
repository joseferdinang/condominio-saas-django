"""Test settings. Tests still use PostgreSQL."""

from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret-key"
DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
