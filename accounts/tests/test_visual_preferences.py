from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import PreferenciaVisual


class PreferenciaVisualTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.usuario = user_model.objects.create_user(
            username="usuario-tema",
            password="Clave-segura-2026",
        )
        self.otro_usuario = user_model.objects.create_user(
            username="otro-tema",
            password="Clave-segura-2026",
        )
        self.url = reverse("accounts:guardar_preferencia_visual")

    def test_requiere_autenticacion(self):
        response = self.client.post(
            self.url,
            {"tema": "oscuro", "paleta": "violeta"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertFalse(PreferenciaVisual.objects.exists())

    def test_guarda_tema_y_paleta_para_el_usuario(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            self.url,
            {"tema": "oscuro", "paleta": "violeta"},
        )

        self.assertEqual(response.status_code, 200)
        preferencia = PreferenciaVisual.objects.get(usuario=self.usuario)
        self.assertEqual(preferencia.tema, PreferenciaVisual.Tema.OSCURO)
        self.assertEqual(preferencia.paleta, PreferenciaVisual.Paleta.VIOLETA)
        self.assertFalse(
            PreferenciaVisual.objects.filter(usuario=self.otro_usuario).exists()
        )

    def test_actualiza_la_preferencia_sin_duplicarla(self):
        PreferenciaVisual.objects.create(
            usuario=self.usuario,
            tema=PreferenciaVisual.Tema.CLARO,
            paleta=PreferenciaVisual.Paleta.OCEANO,
        )
        self.client.force_login(self.usuario)

        response = self.client.post(
            self.url,
            {"tema": "oscuro", "paleta": "coral"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PreferenciaVisual.objects.filter(usuario=self.usuario).count(),
            1,
        )
        preferencia = PreferenciaVisual.objects.get(usuario=self.usuario)
        self.assertEqual(preferencia.tema, PreferenciaVisual.Tema.OSCURO)
        self.assertEqual(preferencia.paleta, PreferenciaVisual.Paleta.CORAL)

    def test_paleta_almacenada_conserva_clave_y_nombre_visible_arena(self):
        PreferenciaVisual.objects.create(
            usuario=self.usuario,
            tema=PreferenciaVisual.Tema.OSCURO,
            paleta=PreferenciaVisual.Paleta.VIOLETA,
        )
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-palette="violeta"')
        self.assertContains(response, 'aria-label="Paleta Arena"')
        self.assertContains(response, 'data-theme="oscuro"')

    def test_rechaza_valores_no_permitidos(self):
        self.client.force_login(self.usuario)

        response = self.client.post(
            self.url,
            {"tema": "personalizado", "paleta": "javascript"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PreferenciaVisual.objects.exists())

    def test_renderiza_la_preferencia_guardada_en_el_documento(self):
        PreferenciaVisual.objects.create(
            usuario=self.usuario,
            tema=PreferenciaVisual.Tema.OSCURO,
            paleta=PreferenciaVisual.Paleta.ESMERALDA,
        )
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(response, 'data-theme="oscuro"')
        self.assertContains(response, 'data-palette="esmeralda"')
        self.assertContains(response, "Modo claro")
        self.assertContains(response, "Colores del portal")
        self.assertContains(response, "css/app.css?v=20260929.7")
        self.assertContains(response, "js/theme.js?v=20260920.2")
