"""Guardrails for an explicitly configured temporary HTTPS preview."""

import os
import subprocess
import sys

from django.test import SimpleTestCase


class PreviewSettingsTests(SimpleTestCase):
    def test_preview_requires_explicit_hosts_and_strong_secret(self):
        base = {key: value for key, value in os.environ.items() if not key.endswith("_FILE")}
        safe = {
            "DJANGO_SECRET_KEY": "aB9cD8eF7gH6" * 6,
            "DJANGO_ALLOWED_HOSTS": "preview.trycloudflare.com,localhost",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://preview.trycloudflare.com",
            "DJANGO_DEBUG": "true",
        }
        assertion = (
            "from config.settings import preview as s; "
            "assert not s.DEBUG; assert s.SESSION_COOKIE_SECURE; "
            "assert s.CSRF_COOKIE_SECURE; assert s.SECURE_SSL_REDIRECT"
        )
        result = subprocess.run(
            [sys.executable, "-c", assertion], env=base | safe, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for invalid in (
            {"DJANGO_SECRET_KEY": "change-me-development-only"},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://preview.trycloudflare.com"},
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "https://another.trycloudflare.com"},
        ):
            with self.subTest(invalid=list(invalid)):
                result = subprocess.run(
                    [sys.executable, "-c", "import config.settings.preview"],
                    env=base | safe | invalid,
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
