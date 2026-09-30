import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, RequestFactory
from django.http import HttpResponse

from config.settings.base import env_secret
from core.middleware import RequestSizeLimitMiddleware
from ops.production import init_secrets, validate_backup, validate_media_archive


class ProductionSafetyTests(SimpleTestCase):
    def test_oversized_upload_is_rejected_before_view(self):
        middleware = RequestSizeLimitMiddleware(lambda request: HttpResponse("accepted"))
        request = RequestFactory().post("/upload/", CONTENT_LENGTH=str(7 * 1024 * 1024))
        self.assertEqual(middleware(request).status_code, 413)

    def test_secret_file_and_environment_are_mutually_exclusive(self):
        with patch.dict(os.environ, {"TEST_SECRET": "value", "TEST_SECRET_FILE": "file"}):
            with self.assertRaises(ImproperlyConfigured):
                env_secret("TEST_SECRET")

    def test_secret_files_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            init_secrets(folder)
            original = (Path(folder) / "django_secret_key").read_text()
            self.assertGreaterEqual(len(original), 50)
            with self.assertRaises(ValueError):
                init_secrets(folder)
            self.assertEqual((Path(folder) / "django_secret_key").read_text(), original)
            for path in Path(folder).iterdir():
                path.chmod(0o600)  # Permit TemporaryDirectory cleanup on Windows.

    def test_restore_rejects_traversal_and_links(self):
        for name, kind in [("../outside", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "media.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    info = tarfile.TarInfo(name)
                    info.type = kind
                    archive.addfile(info, io.BytesIO(b""))
                with self.assertRaises(ValueError):
                    validate_media_archive(path)

    def test_incomplete_backup_cannot_be_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "manifest.json").write_text('{"format": 1, "sha256": {}}')
            with self.assertRaises(ValueError):
                validate_backup(Path(folder))

    def test_production_refuses_weak_secrets_wildcard_hosts_and_http_csrf(self):
        safe = {
            "DJANGO_SECRET_KEY": "aB9cD8eF7gH6" * 6,
            "POSTGRES_PASSWORD": "TestOnlyDatabaseValue" * 2,
            "DJANGO_ALLOWED_HOSTS": "pilot.example.test",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://pilot.example.test",
        }
        for invalid in [
            {"DJANGO_SECRET_KEY": "weak"},
            {"POSTGRES_PASSWORD": "condominio_dev"},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://pilot.example.test"},
        ]:
            with self.subTest(invalid=list(invalid)):
                environment = {key: value for key, value in os.environ.items() if not key.endswith("_FILE")}
                environment.update(safe | invalid)
                result = subprocess.run(
                    [sys.executable, "-c", "import config.settings.production"],
                    env=environment, capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)

    def test_production_forces_debug_off_and_secure_cookies(self):
        environment = {key: value for key, value in os.environ.items() if not key.endswith("_FILE")}
        environment.update({
            "DJANGO_SECRET_KEY": "aB9cD8eF7gH6" * 6,
            "POSTGRES_PASSWORD": "TestOnlyDatabaseValue" * 2,
            "DJANGO_ALLOWED_HOSTS": "pilot.example.test",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://pilot.example.test",
            "DJANGO_DEBUG": "true",
        })
        result = subprocess.run([sys.executable, "-c", (
            "from config.settings import production as p; "
            "assert not p.DEBUG; assert p.SESSION_COOKIE_SECURE; "
            "assert p.CSRF_COOKIE_SECURE; assert p.SECURE_SSL_REDIRECT; "
            "options=p.STORAGES['staticfiles']['OPTIONS']; "
            "assert options['file_permissions_mode'] == 0o644; "
            "assert options['directory_permissions_mode'] == 0o755"
        )], env=environment, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_production_configures_private_s3_storage_when_enabled(self):
        environment = {key: value for key, value in os.environ.items() if not key.endswith("_FILE")}
        environment.update({
            "DJANGO_SECRET_KEY": "aB9cD8eF7gH6" * 6,
            "POSTGRES_PASSWORD": "TestOnlyDatabaseValue" * 2,
            "DJANGO_ALLOWED_HOSTS": "pilot.example.test",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://pilot.example.test",
            "OBJECT_STORAGE_BACKEND": "s3",
            "AWS_STORAGE_BUCKET_NAME": "condominio-comprobantes",
            "AWS_ACCESS_KEY_ID": "nak_test_token_id",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
            "AWS_ENDPOINT_URL_S3": "https://branch.storage.example.test",
            "AWS_REGION": "us-east-2",
        })
        result = subprocess.run([sys.executable, "-c", (
            "from config.settings import production as p; "
            "s=p.STORAGES['default']; assert s['BACKEND']=='storages.backends.s3.S3Storage'; "
            "o=s['OPTIONS']; assert o['bucket_name']=='condominio-comprobantes'; "
            "assert o['addressing_style']=='path'; assert o['querystring_auth'] is True; "
            "assert o['default_acl'] is None"
        )], env=environment, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_production_rejects_incomplete_s3_storage_configuration(self):
        environment = {key: value for key, value in os.environ.items() if not key.endswith("_FILE")}
        environment.update({
            "DJANGO_SECRET_KEY": "aB9cD8eF7gH6" * 6,
            "POSTGRES_PASSWORD": "TestOnlyDatabaseValue" * 2,
            "DJANGO_ALLOWED_HOSTS": "pilot.example.test",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://pilot.example.test",
            "OBJECT_STORAGE_BACKEND": "s3",
        })
        result = subprocess.run([sys.executable, "-c", "import config.settings.production"],
                                env=environment, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Object Storage S3 requiere", result.stderr)
