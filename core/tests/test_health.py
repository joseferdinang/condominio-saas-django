from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class HealthCheckIntegrationTests(TestCase):
    def test_health_check_confirms_postgresql_connection(self):
        response = self.client.get(reverse("core:health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})


class HealthCheckFailureTests(SimpleTestCase):
    @patch("core.views.connection")
    def test_health_check_returns_503_when_database_is_unavailable(
        self, mocked_connection
    ):
        mocked_connection.cursor.side_effect = OperationalError("unavailable")

        response = self.client.get(reverse("core:health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(), {"status": "error", "database": "unavailable"}
        )

    def test_health_check_only_accepts_get(self):
        response = self.client.post(reverse("core:health"))

        self.assertEqual(response.status_code, 405)
