from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounts.models import UsuarioEdificio
from buildings.models import Edificio
from core.models import Cambio


class MyAccountTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('vecino', password='Cuenta-segura-2026')
        self.other = get_user_model().objects.create_user('otra-cuenta')
        self.building = Edificio.objects.create(nombre='Edificio', direccion='Santiago')
        UsuarioEdificio.objects.create(usuario=self.user, edificio=self.building, rol=UsuarioEdificio.Rol.RESIDENTE)
        self.url = reverse('accounts:mi_cuenta')

    def submit(self, **values):
        self.client.force_login(self.user)
        return self.client.post(self.url, {
            'username': 'nuevo-usuario', 'first_name': 'Ana', 'last_name': 'Pérez',
            'password_actual': 'Cuenta-segura-2026', **values,
        })

    def test_anonymous_requires_login(self):
        self.assertRedirects(self.client.get(self.url), reverse('accounts:login') + '?next=' + self.url)

    def test_updates_only_own_account_keeps_session_and_role_and_audits(self):
        self.assertRedirects(self.submit(user_id=self.other.pk, is_superuser='1'), self.url)
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.username, 'nuevo-usuario')
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.other.username, 'otra-cuenta')
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertTrue(Cambio.objects.filter(usuario=self.user, modelo='auth.User', descripcion__contains='vecino → nuevo-usuario').exists())
        self.client.logout()
        self.assertTrue(self.client.login(username='nuevo-usuario', password='Cuenta-segura-2026'))

    def test_wrong_password_does_not_change_account(self):
        response = self.submit(password_actual='incorrecta')
        self.assertContains(response, 'La contraseña actual no es correcta.')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'vecino')

    def test_duplicate_username_case_insensitive(self):
        self.assertContains(self.submit(username='OTRA-CUENTA'), 'Ese nombre de usuario ya está en uso.')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'vecino')

    def test_username_validation(self):
        self.assertEqual(self.submit(username='invalido con espacio').status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'vecino')
