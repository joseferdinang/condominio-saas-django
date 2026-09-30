import os
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

from config.settings.base import postgres_database_config


class BaseSettingsTests(SimpleTestCase):
    def test_locale_and_database_backend(self):
        self.assertEqual(settings.LANGUAGE_CODE, "es")
        self.assertEqual(settings.TIME_ZONE, "America/Santo_Domingo")
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"],
            "django.db.backends.postgresql",
        )

    def test_portal_stylesheet_is_discoverable(self):
        self.assertIsNotNone(finders.find("css/app.css"))
        self.assertIsNotNone(finders.find("js/htmx.min.js"))

    def test_database_url_neon_decodifica_credenciales_y_exige_tls(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://app%40tenant:secret%2Fpart@ep-example-pooler.us-east-2.aws.neon.tech/condominio?sslmode=require&channel_binding=require"
            },
            clear=True,
        ):
            database = postgres_database_config()

        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["NAME"], "condominio")
        self.assertEqual(database["USER"], "app@tenant")
        self.assertEqual(database["PASSWORD"], "secret/part")
        self.assertEqual(database["HOST"], "ep-example-pooler.us-east-2.aws.neon.tech")
        self.assertEqual(database["CONN_MAX_AGE"], 0)
        self.assertEqual(database["OPTIONS"]["sslmode"], "require")
        self.assertEqual(database["OPTIONS"]["channel_binding"], "require")

    def test_database_url_rechaza_tls_desactivado(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://app:password@db.example/condominio?sslmode=disable"},
            clear=True,
        ):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "DATABASE_URL debe exigir una conexión PostgreSQL cifrada.",
            ):
                postgres_database_config()

    def test_database_url_rechaza_puerto_malformado(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://app:password@db.example:puerto/condominio"},
            clear=True,
        ):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "DATABASE_URL no tiene un formato PostgreSQL válido.",
            ):
                postgres_database_config()

    def test_database_url_conserva_la_configuracion_postgres_de_compose(self):
        with patch.dict(
            os.environ,
            {
                "POSTGRES_DB": "portal",
                "POSTGRES_USER": "portal_user",
                "POSTGRES_PASSWORD": "local-only",
                "POSTGRES_HOST": "db",
                "POSTGRES_PORT": "5433",
            },
            clear=True,
        ):
            database = postgres_database_config()

        self.assertEqual(database["NAME"], "portal")
        self.assertEqual(database["USER"], "portal_user")
        self.assertEqual(database["PASSWORD"], "local-only")
        self.assertEqual(database["HOST"], "db")
        self.assertEqual(database["PORT"], "5433")
