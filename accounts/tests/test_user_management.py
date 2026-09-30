from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UsuarioEdificio
from buildings.models import Edificio
from core.models import Cambio


class UserManagementTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Edificio Uno", direccion="Santiago")
        self.otro = Edificio.objects.create(nombre="Edificio Dos", direccion="Santiago")
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username="admin-uno", password="clave-pruebas")
        self.admin_otro = user_model.objects.create_user(username="admin-dos", password="clave-pruebas")
        self.tesorero = user_model.objects.create_user(username="tesorero", password="clave-pruebas")
        self.residente = user_model.objects.create_user(
            username="residente", email="residente@example.test", password="clave-pruebas"
        )
        self.compartido = user_model.objects.create_user(
            username="compartido", email="compartido@example.test", password="clave-pruebas"
        )
        self.admin_membresia = UsuarioEdificio.objects.create(
            usuario=self.admin, edificio=self.edificio, rol=UsuarioEdificio.Rol.ADMINISTRADOR
        )
        UsuarioEdificio.objects.create(
            usuario=self.admin_otro, edificio=self.otro, rol=UsuarioEdificio.Rol.ADMINISTRADOR
        )
        UsuarioEdificio.objects.create(
            usuario=self.tesorero, edificio=self.edificio, rol=UsuarioEdificio.Rol.TESORERO
        )
        self.residente_membresia = UsuarioEdificio.objects.create(
            usuario=self.residente, edificio=self.edificio, rol=UsuarioEdificio.Rol.RESIDENTE
        )
        self.compartido_membresia = UsuarioEdificio.objects.create(
            usuario=self.compartido, edificio=self.edificio, rol=UsuarioEdificio.Rol.RESIDENTE
        )
        UsuarioEdificio.objects.create(
            usuario=self.compartido, edificio=self.otro, rol=UsuarioEdificio.Rol.RESIDENTE
        )

    def test_solo_admin_ve_usuarios_y_cambios_en_menu(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:usuarios_lista", args=[self.edificio.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cambios")
        self.assertContains(response, "residente")
        self.assertNotContains(response, "admin-dos")

        self.client.force_login(self.tesorero)
        response = self.client.get(reverse("accounts:edificio_detalle", args=[self.edificio.pk]))
        self.assertNotContains(
            response, f'href="{reverse("accounts:cambios_lista", args=[self.edificio.pk])}"'
        )
        for nombre in ("usuarios_lista", "cambios_lista"):
            self.assertEqual(
                self.client.get(reverse(f"accounts:{nombre}", args=[self.edificio.pk])).status_code,
                403,
            )

    def test_cambiar_edificio_o_usuario_en_url_no_expone_datos(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("accounts:cambios_lista", args=[self.otro.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("accounts:usuario_editar", args=[self.otro.pk, self.compartido_membresia.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("accounts:usuario_retirar", args=[self.otro.pk, self.residente_membresia.pk])
            ).status_code,
            404,
        )

    def test_admin_edita_datos_y_rol_y_queda_auditoria(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:usuario_editar", args=[self.edificio.pk, self.residente_membresia.pk]),
            {
                "first_name": "María",
                "last_name": "Pérez",
                "email": "maria@example.test",
                "rol": UsuarioEdificio.Rol.TESORERO,
                "activo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.residente.refresh_from_db()
        self.residente_membresia.refresh_from_db()
        self.assertEqual(self.residente.email, "maria@example.test")
        self.assertEqual(self.residente_membresia.rol, UsuarioEdificio.Rol.TESORERO)
        self.assertTrue(self.residente.is_staff)
        self.assertTrue(Cambio.objects.filter(
            edificio=self.edificio, usuario=self.admin,
            modelo="accounts.UsuarioEdificio", objeto_id=str(self.residente_membresia.pk),
        ).exists())
        self.assertTrue(Cambio.objects.filter(
            edificio=self.edificio, usuario=self.admin,
            modelo=self.residente._meta.label, objeto_id=str(self.residente.pk),
        ).exists())

    def test_cuenta_de_varios_edificios_solo_permite_editar_su_membresia(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:usuario_editar", args=[self.edificio.pk, self.compartido_membresia.pk]),
            {
                "first_name": "Nombre alterado",
                "email": "alterado@example.test",
                "rol": UsuarioEdificio.Rol.JUNTA,
                "activo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.compartido.refresh_from_db()
        self.compartido_membresia.refresh_from_db()
        self.assertEqual(self.compartido.email, "compartido@example.test")
        self.assertEqual(self.compartido.first_name, "")
        self.assertEqual(self.compartido_membresia.rol, UsuarioEdificio.Rol.JUNTA)
        self.assertEqual(
            UsuarioEdificio.objects.get(usuario=self.compartido, edificio=self.otro).rol,
            UsuarioEdificio.Rol.RESIDENTE,
        )

    def test_retirar_acceso_conserva_cuenta_y_otros_edificios(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:usuario_retirar", args=[self.edificio.pk, self.compartido_membresia.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(self.compartido_membresia.activo)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.compartido_membresia.refresh_from_db()
        self.assertFalse(self.compartido_membresia.activo)
        self.assertTrue(get_user_model().objects.filter(pk=self.compartido.pk).exists())
        self.assertTrue(UsuarioEdificio.objects.get(usuario=self.compartido, edificio=self.otro).activo)
        self.assertTrue(Cambio.objects.filter(
            edificio=self.edificio, usuario=self.admin,
            modelo="accounts.UsuarioEdificio", objeto_id=str(self.compartido_membresia.pk),
            accion=Cambio.Accion.MODIFICAR,
        ).exists())

    def test_admin_no_puede_retirarse_a_si_mismo_ni_editar_otro_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse(
            "accounts:usuario_retirar", args=[self.edificio.pk, self.admin_membresia.pk]
        )).status_code, 403)
        self.assertEqual(self.client.get(reverse(
            "accounts:usuario_editar", args=[self.edificio.pk, self.admin_membresia.pk]
        )).status_code, 403)

    def test_cambios_filtrados_por_edificio_y_accion(self):
        self.client.force_login(self.admin)
        Cambio.objects.create(
            edificio=self.otro, usuario_nombre="Otro admin", accion=Cambio.Accion.CREAR,
            modelo="Prueba", objeto_id="99", descripcion="Secreto de otro edificio",
        )
        response = self.client.get(reverse("accounts:cambios_lista", args=[self.edificio.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secreto de otro edificio")
        self.assertContains(response, "admin-uno")
        response = self.client.get(
            reverse("accounts:cambios_lista", args=[self.edificio.pk]),
            {"accion": Cambio.Accion.CREAR},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secreto de otro edificio")
