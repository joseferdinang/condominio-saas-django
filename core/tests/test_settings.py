from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


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
