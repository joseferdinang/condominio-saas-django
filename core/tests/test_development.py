"""Configuration needed for a temporary HTTPS preview."""

import os
import subprocess
import sys

from django.test import SimpleTestCase


class DevelopmentSettingsTests(SimpleTestCase):
    def test_explicit_preview_host_and_csrf_origin(self):
        environment = os.environ.copy()
        environment.update({
            "DJANGO_DEBUG": "false",
            "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "DJANGO_ALLOWED_HOSTS": "localhost,preview.trycloudflare.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://preview.trycloudflare.com",
        })
        result = subprocess.run(
            [sys.executable, "-c", (
                "from config.settings import development as s; "
                "assert not s.DEBUG; "
                "assert s.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'; "
                "assert 'preview.trycloudflare.com' in s.ALLOWED_HOSTS; "
                "assert s.CSRF_TRUSTED_ORIGINS == ['https://preview.trycloudflare.com']"
            )],
            env=environment,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
