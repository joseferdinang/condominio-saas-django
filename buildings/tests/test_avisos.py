from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Aviso, Edificio, EnvioAviso
from buildings.services import enviar_aviso_por_correo
from people.models import Persona, RelacionApartamento


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AvisoTests(TestCase):
    def setUp(self):
        usuarios = get_user_model()
        self.edificio = Edificio.objects.create(
            nombre="Residencial Avisos",
            direccion="Santiago",
        )
        self.otro_edificio = Edificio.objects.create(
            nombre="Residencial Ajeno",
            direccion="Santiago",
        )
        self.apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="A-1",
        )
        self.admin = usuarios.objects.create_user(username="admin-avisos")
        self.residente = usuarios.objects.create_user(username="residente-avisos")
        self.admin_ajeno = usuarios.objects.create_user(username="admin-avisos-ajeno")
        UsuarioEdificio.objects.bulk_create(
            [
                UsuarioEdificio(
                    usuario=self.admin,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
                UsuarioEdificio(
                    usuario=self.residente,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.RESIDENTE,
                ),
                UsuarioEdificio(
                    usuario=self.admin_ajeno,
                    edificio=self.otro_edificio,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
            ]
        )
        persona = Persona.objects.create(
            usuario=self.residente,
            nombre_completo="Residente Avisos",
            telefono="809-555-0101",
            correo="residente@example.test",
        )
        RelacionApartamento.objects.create(
            persona=persona,
            apartamento=self.apartamento,
            tipo=RelacionApartamento.Tipo.PROPIETARIO,
            fecha_inicio=timezone.localdate() - timedelta(days=30),
            puede_acceder_portal=True,
            puede_recibir_comunicaciones=True,
        )
        self.aviso = Aviso.objects.create(
            edificio=self.edificio,
            titulo="Mantenimiento programado",
            contenido="La cisterna estará en mantenimiento.",
            estado=Aviso.Estado.PUBLICADO,
            fijado=True,
            creado_por=self.admin,
        )

    def test_guardar_aviso_no_envia_correo_automaticamente(self):
        Aviso.objects.create(
            edificio=self.edificio,
            titulo="Solo borrador",
            contenido="Contenido interno",
            creado_por=self.admin,
        )

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EnvioAviso.objects.count(), 0)

    def test_servicio_explicito_envia_y_evitar_duplicados(self):
        primero = enviar_aviso_por_correo(aviso=self.aviso, usuario=self.admin)
        segundo = enviar_aviso_por_correo(aviso=self.aviso, usuario=self.admin)

        self.assertEqual((primero.enviados, primero.fallidos), (1, 0))
        self.assertEqual(segundo.omitidos, 1)
        self.assertEqual(len(mail.outbox), 1)
        envio = EnvioAviso.objects.get()
        self.assertEqual(envio.destinatario, "residente@example.test")
        self.assertEqual(envio.estado, EnvioAviso.Estado.ENVIADO)
        self.assertEqual(envio.numero_intentos, 1)
        self.assertIsNotNone(envio.fecha_envio)

    def test_envio_fallido_registra_error_y_puede_reintentarse(self):
        with patch("buildings.services.send_mail", side_effect=RuntimeError("SMTP caído")):
            fallido = enviar_aviso_por_correo(aviso=self.aviso, usuario=self.admin)

        envio = EnvioAviso.objects.get()
        self.assertEqual(fallido.fallidos, 1)
        self.assertEqual(envio.estado, EnvioAviso.Estado.FALLIDO)
        self.assertEqual(envio.error, "SMTP caído")
        self.assertEqual(envio.numero_intentos, 1)

        reintento = enviar_aviso_por_correo(aviso=self.aviso, usuario=self.admin)
        envio.refresh_from_db()
        self.assertEqual(reintento.enviados, 1)
        self.assertEqual(envio.estado, EnvioAviso.Estado.ENVIADO)
        self.assertEqual(envio.error, "")
        self.assertEqual(envio.numero_intentos, 2)

    def test_otro_edificio_no_puede_enviar_aviso(self):
        with self.assertRaises(PermissionDenied):
            enviar_aviso_por_correo(
                aviso=self.aviso,
                usuario=self.admin_ajeno,
            )

    def test_residente_ve_publicados_pero_no_puede_crear(self):
        Aviso.objects.create(
            edificio=self.edificio,
            titulo="Borrador privado",
            contenido="No visible",
            estado=Aviso.Estado.BORRADOR,
            creado_por=self.admin,
        )
        self.client.force_login(self.residente)

        listado = self.client.get(
            reverse("buildings:avisos_lista", args=[self.edificio.pk])
        )
        crear = self.client.get(
            reverse("buildings:aviso_crear", args=[self.edificio.pk])
        )

        self.assertEqual(listado.status_code, 200)
        self.assertContains(listado, "Mantenimiento programado")
        self.assertNotContains(listado, "Borrador privado")
        self.assertEqual(crear.status_code, 403)

    def test_administrador_crea_publica_y_envia_desde_vistas(self):
        self.client.force_login(self.admin)
        crear = self.client.post(
            reverse("buildings:aviso_crear", args=[self.edificio.pk]),
            {
                "titulo": "Reunión general",
                "contenido": "Reunión el viernes.",
                "fecha": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "fijado": "on",
                "estado": Aviso.Estado.BORRADOR,
            },
        )
        self.assertEqual(crear.status_code, 302)
        aviso = Aviso.objects.get(titulo="Reunión general")
        publicar = self.client.post(
            reverse(
                "buildings:aviso_publicar",
                args=[self.edificio.pk, aviso.pk],
            )
        )
        self.assertEqual(publicar.status_code, 302)
        aviso.refresh_from_db()
        self.assertEqual(aviso.estado, Aviso.Estado.PUBLICADO)

        enviar = self.client.post(
            reverse(
                "buildings:aviso_enviar",
                args=[self.edificio.pk, aviso.pk],
            )
        )
        self.assertEqual(enviar.status_code, 302)
        self.assertTrue(
            EnvioAviso.objects.filter(
                aviso=aviso,
                destinatario="residente@example.test",
                estado=EnvioAviso.Estado.ENVIADO,
            ).exists()
        )
