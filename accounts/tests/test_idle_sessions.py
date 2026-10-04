from unittest.mock import patch

from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.idle import ACTIVITY_KEY
from accounts.models import UsuarioEdificio
from buildings.models import Edificio


class IdleSessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="session-admin", password="local-test-only"
        )
        self.building = Edificio.objects.create(nombre="Prueba de sesiones", direccion="Santiago")
        UsuarioEdificio.objects.create(
            usuario=self.user, edificio=self.building, rol=UsuarioEdificio.Rol.ADMINISTRADOR
        )
        self.client.force_login(self.user)
        with patch("accounts.idle.time.time", return_value=1000):
            self.client.get(reverse("accounts:dashboard"))

    def test_active_request_extends_session_and_cookie_for_five_minutes(self):
        with patch("accounts.idle.time.time", return_value=1299):
            response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(self.client.session[ACTIVITY_KEY], 1299)
        self.assertEqual(int(response.cookies["sessionid"]["max-age"]), 300)
        with patch("accounts.idle.time.time", return_value=1598):
            self.assertEqual(self.client.get(reverse("accounts:dashboard")).status_code, 200)

    def test_expired_post_cannot_modify_data(self):
        with patch("accounts.idle.time.time", return_value=1300):
            response = self.client.post(reverse("accounts:mi_cuenta"), {
                "username": "changed-after-expiry", "first_name": "Alterado",
            })
        self.assertRedirects(response, reverse("accounts:login") + "?inactivo=1")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "session-admin")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_htmx_expiration_redirects_the_entire_page(self):
        with patch("accounts.idle.time.time", return_value=1301):
            response = self.client.get(reverse("accounts:dashboard"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.headers["HX-Redirect"], reverse("accounts:login") + "?inactivo=1")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_activity_refreshes_an_active_session_but_cannot_revive_expired_one(self):
        url = reverse("accounts:session_activity")
        with patch("accounts.idle.time.time", return_value=1200):
            self.assertEqual(self.client.post(url).json(), {"timeout": 300})
        with patch("accounts.idle.time.time", return_value=1500):
            self.assertEqual(self.client.post(url).status_code, 401)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_activity_requires_post_and_csrf(self):
        with patch("accounts.idle.time.time", return_value=1001):
            self.assertEqual(self.client.get(reverse("accounts:session_activity")).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("accounts:session_activity")).status_code, 403)
        response = client.get(reverse("accounts:dashboard"))
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.get(reverse("accounts:session_activity")).status_code, 405)
        self.assertEqual(client.post(reverse("accounts:session_activity"), HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_health_checks_do_not_extend_inactivity(self):
        with patch("accounts.idle.time.time", return_value=1250):
            self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.session[ACTIVITY_KEY], 1000)
        with patch("accounts.idle.time.time", return_value=1300):
            self.assertEqual(self.client.get(reverse("accounts:dashboard")).status_code, 302)

    def test_expired_session_cannot_access_django_admin(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        with patch("accounts.idle.time.time", return_value=1300):
            response = self.client.get("/admin/")
        self.assertRedirects(response, reverse("accounts:login") + "?inactivo=1")

    def test_django_admin_includes_automatic_logout(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        with patch("accounts.idle.time.time", return_value=1001):
            self.assertContains(self.client.get("/admin/"), "js/session-idle.js")

    def test_anonymous_activity_does_not_create_a_session(self):
        client = Client()
        self.assertEqual(client.post(reverse("accounts:session_activity")).status_code, 401)
        self.assertNotIn("sessionid", client.cookies)

    def test_existing_session_without_activity_stamp_is_initialized(self):
        session = self.client.session
        del session[ACTIVITY_KEY]
        session.save()
        with patch("accounts.idle.time.time", return_value=1400):
            self.assertEqual(self.client.get(reverse("accounts:dashboard")).status_code, 200)
        self.assertEqual(self.client.session[ACTIVITY_KEY], 1400)

    def test_login_initializes_timeout_and_explains_expiration(self):
        self.client.logout()
        with patch("accounts.idle.time.time", return_value=1700):
            response = self.client.post(reverse("accounts:login"), {
                "username": self.user.username, "password": "local-test-only",
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session[ACTIVITY_KEY], 1700)
        self.assertContains(Client().get(reverse("accounts:login") + "?inactivo=1"), "sin actividad")


class BuildingAdministrationAccessTests(TestCase):
    def test_home_shows_user_management_only_for_buildings_the_user_administers(self):
        user = get_user_model().objects.create_user(username="multi-building")
        administered = Edificio.objects.create(nombre="Administrado", direccion="Santiago")
        resident = Edificio.objects.create(nombre="Residente", direccion="Santiago")
        other = Edificio.objects.create(nombre="Sin acceso", direccion="Santiago")
        for building, role in (
            (administered, UsuarioEdificio.Rol.ADMINISTRADOR),
            (resident, UsuarioEdificio.Rol.RESIDENTE),
        ):
            UsuarioEdificio.objects.create(usuario=user, edificio=building, rol=role)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, reverse("accounts:usuarios_lista", args=[administered.pk]))
        self.assertNotContains(response, reverse("accounts:usuarios_lista", args=[resident.pk]))
        self.assertNotContains(response, other.nombre)
        self.assertEqual(self.client.get(reverse("accounts:usuarios_lista", args=[resident.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:usuarios_lista", args=[other.pk])).status_code, 404)

    def test_superuser_has_a_management_link_for_every_active_building(self):
        user = get_user_model().objects.create_superuser(username="owner", password="local-test-only")
        building = Edificio.objects.create(nombre="Piloto", direccion="Santiago")
        self.client.force_login(user)
        self.assertContains(
            self.client.get(reverse("accounts:dashboard")),
            reverse("accounts:usuarios_lista", args=[building.pk]),
        )
