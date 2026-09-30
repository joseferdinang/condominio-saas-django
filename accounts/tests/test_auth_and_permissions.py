from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UsuarioEdificio
from accounts.services import (
    apartamentos_con_estado_cuenta,
    puede_gestionar_usuarios,
    puede_registrar_finanzas,
)
from buildings.models import Apartamento, Edificio
from people.models import Persona, RelacionApartamento


class PortalAuthorizationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.clave = "Clave-segura-pruebas-2026"
        self.edificio_a = Edificio.objects.create(
            nombre="Residencial A",
            direccion="Santiago",
        )
        self.edificio_b = Edificio.objects.create(
            nombre="Residencial B",
            direccion="Santiago",
        )
        self.apartamento_a1 = Apartamento.objects.create(
            edificio=self.edificio_a,
            numero="A-1",
        )
        self.apartamento_a2 = Apartamento.objects.create(
            edificio=self.edificio_a,
            numero="A-2",
        )
        self.apartamento_b1 = Apartamento.objects.create(
            edificio=self.edificio_b,
            numero="B-1",
        )
        self.administrador = user_model.objects.create_user(
            username="administrador",
            password=self.clave,
            email="administrador@example.test",
        )
        self.tesorero = user_model.objects.create_user(
            username="tesorero-portal",
            password=self.clave,
            email="tesorero@example.test",
        )
        self.residente = user_model.objects.create_user(
            username="residente-portal",
            password=self.clave,
            email="residente@example.test",
        )
        self.multi = user_model.objects.create_user(
            username="usuario-multi",
            password=self.clave,
            email="multi@example.test",
        )
        UsuarioEdificio.objects.bulk_create(
            [
                UsuarioEdificio(
                    usuario=self.administrador,
                    edificio=self.edificio_a,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
                UsuarioEdificio(
                    usuario=self.tesorero,
                    edificio=self.edificio_a,
                    rol=UsuarioEdificio.Rol.TESORERO,
                ),
                UsuarioEdificio(
                    usuario=self.residente,
                    edificio=self.edificio_a,
                    rol=UsuarioEdificio.Rol.RESIDENTE,
                ),
                UsuarioEdificio(
                    usuario=self.multi,
                    edificio=self.edificio_a,
                    rol=UsuarioEdificio.Rol.RESIDENTE,
                ),
                UsuarioEdificio(
                    usuario=self.multi,
                    edificio=self.edificio_b,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
            ]
        )
        hoy = timezone.localdate()
        residente_persona = Persona.objects.create(
            usuario=self.residente,
            nombre_completo="Residente Uno",
            telefono="809-555-0101",
            correo="residente@example.test",
        )
        multi_persona = Persona.objects.create(
            usuario=self.multi,
            nombre_completo="Usuario Multi",
            telefono="809-555-0102",
            correo="multi@example.test",
        )
        RelacionApartamento.objects.create(
            persona=residente_persona,
            apartamento=self.apartamento_a1,
            tipo=RelacionApartamento.Tipo.INQUILINO,
            fecha_inicio=hoy - timedelta(days=30),
            puede_acceder_portal=True,
            puede_ver_estado_cuenta=True,
        )
        RelacionApartamento.objects.create(
            persona=multi_persona,
            apartamento=self.apartamento_a1,
            tipo=RelacionApartamento.Tipo.PROPIETARIO,
            fecha_inicio=hoy - timedelta(days=30),
            puede_acceder_portal=True,
            puede_ver_estado_cuenta=True,
        )

    def test_usuario_no_autenticado_es_enviado_al_login(self):
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next=/",
        )

    def test_administrador_accede_solo_a_su_edificio(self):
        self.client.force_login(self.administrador)

        permitido = self.client.get(
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio_a.pk, self.apartamento_a2.pk],
            )
        )
        denegado = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio_b.pk])
        )

        self.assertEqual(permitido.status_code, 200)
        self.assertEqual(denegado.status_code, 404)

    def test_cambiar_edificio_en_url_no_expone_apartamento(self):
        self.client.force_login(self.multi)

        response = self.client.get(
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio_b.pk, self.apartamento_a1.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_residente_no_puede_consultar_otro_apartamento(self):
        self.client.force_login(self.residente)

        propio = self.client.get(
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio_a.pk, self.apartamento_a1.pk],
            )
        )
        ajeno = self.client.get(
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio_a.pk, self.apartamento_a2.pk],
            )
        )

        self.assertEqual(propio.status_code, 200)
        self.assertEqual(ajeno.status_code, 404)
        self.assertQuerySetEqual(
            apartamentos_con_estado_cuenta(self.residente, self.edificio_a),
            [self.apartamento_a1],
        )

    def test_relacion_vencida_no_concede_acceso_al_estado_de_cuenta(self):
        usuario = get_user_model().objects.create_user(
            username="residente-historico",
            password=self.clave,
        )
        UsuarioEdificio.objects.create(
            usuario=usuario,
            edificio=self.edificio_a,
            rol=UsuarioEdificio.Rol.RESIDENTE,
        )
        persona = Persona.objects.create(
            usuario=usuario,
            nombre_completo="Residente Histórico",
            telefono="809-555-0103",
            correo="historico@example.test",
        )
        hoy = timezone.localdate()
        RelacionApartamento.objects.create(
            persona=persona,
            apartamento=self.apartamento_a2,
            tipo=RelacionApartamento.Tipo.OCUPANTE,
            fecha_inicio=hoy - timedelta(days=10),
            puede_acceder_portal=True,
            puede_ver_estado_cuenta=False,
        )
        RelacionApartamento.objects.create(
            persona=persona,
            apartamento=self.apartamento_a2,
            tipo=RelacionApartamento.Tipo.INQUILINO,
            fecha_inicio=hoy - timedelta(days=60),
            fecha_finalizacion=hoy - timedelta(days=30),
            puede_acceder_portal=True,
            puede_ver_estado_cuenta=True,
        )

        self.assertQuerySetEqual(
            apartamentos_con_estado_cuenta(usuario, self.edificio_a),
            [],
        )

    def test_usuario_de_varios_edificios_accede_a_ambos(self):
        self.client.force_login(self.multi)

        responses = [
            self.client.get(
                reverse("accounts:edificio_detalle", args=[edificio.pk])
            )
            for edificio in (self.edificio_a, self.edificio_b)
        ]

        self.assertEqual([response.status_code for response in responses], [200, 200])

    def test_roles_separan_finanzas_y_gestion_de_usuarios(self):
        self.assertTrue(
            puede_registrar_finanzas(self.tesorero, self.edificio_a)
        )
        self.assertFalse(
            puede_gestionar_usuarios(self.tesorero, self.edificio_a)
        )
        self.assertTrue(
            puede_gestionar_usuarios(self.administrador, self.edificio_a)
        )

        self.client.force_login(self.tesorero)
        response = self.client.get(
            reverse("accounts:invitar_usuario", args=[self.edificio_a.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_residente_no_ve_conciliacion_del_edificio(self):
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio_a.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["conciliacion"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthenticationFlowTests(TestCase):
    def setUp(self):
        self.clave = "Clave-segura-pruebas-2026"
        self.usuario = get_user_model().objects.create_user(
            username="usuario-auth",
            password=self.clave,
            email="usuario-auth@example.test",
        )

    def test_login_y_logout(self):
        login_response = self.client.post(
            reverse("accounts:login"),
            {"username": self.usuario.username, "password": self.clave},
        )
        self.assertRedirects(login_response, reverse("accounts:dashboard"))

        logout_response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(logout_response, reverse("accounts:login"))

    def test_cambio_de_contrasena(self):
        self.client.force_login(self.usuario)
        nueva_clave = "Otra-clave-segura-2026"

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.clave,
                "new_password1": nueva_clave,
                "new_password2": nueva_clave,
            },
        )

        self.assertRedirects(response, reverse("accounts:password_change_done"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(nueva_clave))

    def test_recuperacion_de_contrasena_envia_enlace(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.usuario.email},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/cuentas/contrasena/restablecer/", mail.outbox[0].body)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ControlledInvitationTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(
            nombre="Residencial Invitaciones",
            direccion="Santiago",
        )
        self.administrador = get_user_model().objects.create_user(
            username="admin-invitaciones",
            password="Clave-segura-pruebas-2026",
            email="admin-invitaciones@example.test",
        )
        UsuarioEdificio.objects.create(
            usuario=self.administrador,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )
        self.client.force_login(self.administrador)

    def test_administrador_invita_usuario_con_enlace_para_crear_clave(self):
        response = self.client.post(
            reverse("accounts:invitar_usuario", args=[self.edificio.pk]),
            {
                "username": "nuevo-residente",
                "email": "nuevo@example.test",
                "first_name": "Nuevo",
                "last_name": "Residente",
                "rol": UsuarioEdificio.Rol.RESIDENTE,
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:edificio_detalle", args=[self.edificio.pk]),
        )
        nuevo = get_user_model().objects.get(username="nuevo-residente")
        self.assertTrue(nuevo.has_usable_password())
        self.assertTrue(
            UsuarioEdificio.objects.filter(
                usuario=nuevo,
                edificio=self.edificio,
                rol=UsuarioEdificio.Rol.RESIDENTE,
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/cuentas/contrasena/restablecer/", mail.outbox[0].body)

    def test_fallo_smtp_no_deja_usuario_ni_membresia_y_muestra_error(self):
        from unittest.mock import patch

        datos = {
            "username": "sin-correo",
            "email": "sin-correo@example.test",
            "rol": UsuarioEdificio.Rol.RESIDENTE,
        }
        with patch("accounts.views.send_mail", side_effect=OSError("SMTP no disponible")):
            response = self.client.post(
                reverse("accounts:invitar_usuario", args=[self.edificio.pk]), datos
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se pudo enviar el correo")
        self.assertFalse(get_user_model().objects.filter(username="sin-correo").exists())

    def test_puede_reenviar_invitacion_creada_antes_del_fallo_smtp(self):
        usuario = get_user_model().objects.create_user(
            username="invitado-previo", email="previo@example.test", password="clave-temporal"
        )
        UsuarioEdificio.objects.create(
            usuario=usuario, edificio=self.edificio, rol=UsuarioEdificio.Rol.RESIDENTE
        )
        response = self.client.post(
            reverse("accounts:invitar_usuario", args=[self.edificio.pk]),
            {
                "username": "invitado-previo",
                "email": "previo@example.test",
                "rol": UsuarioEdificio.Rol.RESIDENTE,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(UsuarioEdificio.objects.filter(usuario=usuario, edificio=self.edificio).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/cuentas/contrasena/restablecer/", mail.outbox[0].body)

    def test_no_reinvita_usuario_que_ya_entro_al_portal(self):
        usuario = get_user_model().objects.create_user(
            username="usuario-activo", email="activo@example.test", password="clave-temporal"
        )
        usuario.last_login = timezone.now()
        usuario.save(update_fields=["last_login"])
        UsuarioEdificio.objects.create(
            usuario=usuario, edificio=self.edificio, rol=UsuarioEdificio.Rol.RESIDENTE
        )
        response = self.client.post(
            reverse("accounts:invitar_usuario", args=[self.edificio.pk]),
            {
                "username": "usuario-activo",
                "email": "activo@example.test",
                "rol": UsuarioEdificio.Rol.RESIDENTE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ese usuario ya pertenece a este edificio")
        self.assertEqual(len(mail.outbox), 0)

    def test_administrador_de_edificio_no_puede_crear_otro_administrador(self):
        response = self.client.post(
            reverse("accounts:invitar_usuario", args=[self.edificio.pk]),
            {
                "username": "admin-no-autorizado",
                "email": "otro-admin@example.test",
                "rol": UsuarioEdificio.Rol.ADMINISTRADOR,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(
                username="admin-no-autorizado"
            ).exists()
        )

    def test_tesorero_invitado_recibe_acceso_limitado_a_django_admin(self):
        response = self.client.post(
            reverse("accounts:invitar_usuario", args=[self.edificio.pk]),
            {
                "username": "nuevo-tesorero",
                "email": "nuevo-tesorero@example.test",
                "rol": UsuarioEdificio.Rol.TESORERO,
            },
        )

        self.assertEqual(response.status_code, 302)
        tesorero = get_user_model().objects.get(username="nuevo-tesorero")
        self.assertTrue(tesorero.is_staff)
        self.assertFalse(tesorero.is_superuser)
