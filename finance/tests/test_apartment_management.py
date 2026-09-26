from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio


class ApartmentManagementViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.edificio = Edificio.objects.create(
            nombre="Residencial Gestión",
            direccion="Santiago de los Caballeros",
        )
        self.otro_edificio = Edificio.objects.create(
            nombre="Residencial Ajeno",
            direccion="Santiago de los Caballeros",
        )
        self.admin = user_model.objects.create_user(
            username="admin-apartamentos",
            password="Clave-segura-2026",
        )
        self.tesorero = user_model.objects.create_user(
            username="tesorero-apartamentos",
            password="Clave-segura-2026",
        )
        UsuarioEdificio.objects.bulk_create(
            [
                UsuarioEdificio(
                    usuario=self.admin,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
                UsuarioEdificio(
                    usuario=self.tesorero,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.TESORERO,
                ),
            ]
        )
        self.apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="A-101",
            cuota_mensual=Decimal("4000.00"),
        )

    def datos(self, numero="A-102", **extra):
        return {
            "numero": numero,
            "cuota_mensual": "4500.00",
            "porcentaje_contribucion": "8.5000",
            "peso_voto": "1.0000",
            "activo": "on",
            **extra,
        }

    def test_administrador_puede_agregar_editar_y_desactivar(self):
        self.client.force_login(self.admin)
        crear = self.client.post(
            reverse("finance:apartamento_crear", args=[self.edificio.pk]),
            self.datos(),
        )
        self.assertRedirects(
            crear,
            reverse("finance:apartamentos_lista", args=[self.edificio.pk]),
        )
        nuevo = Apartamento.objects.get(numero="A-102")
        self.assertEqual(nuevo.cuota_mensual, Decimal("4500.00"))

        editar = self.client.post(
            reverse(
                "finance:apartamento_editar",
                args=[self.edificio.pk, nuevo.pk],
            ),
            self.datos(numero="A-102", cuota_mensual="4750.00"),
        )
        self.assertRedirects(
            editar,
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio.pk, nuevo.pk],
            ),
        )
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.cuota_mensual, Decimal("4750.00"))

        desactivar = self.client.post(
            reverse(
                "finance:apartamento_cambiar_estado",
                args=[self.edificio.pk, nuevo.pk],
            )
        )
        self.assertRedirects(
            desactivar,
            reverse("finance:apartamentos_lista", args=[self.edificio.pk]),
        )
        nuevo.refresh_from_db()
        self.assertFalse(nuevo.activo)

        activar = self.client.post(
            reverse(
                "finance:apartamento_cambiar_estado",
                args=[self.edificio.pk, nuevo.pk],
            )
        )
        self.assertRedirects(
            activar,
            reverse("finance:apartamentos_lista", args=[self.edificio.pk]),
        )
        nuevo.refresh_from_db()
        self.assertTrue(nuevo.activo)

    def test_tesorero_no_puede_administrar_apartamentos(self):
        self.client.force_login(self.tesorero)
        response = self.client.get(
            reverse("finance:apartamento_crear", args=[self.edificio.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_de_otro_edificio_no_puede_cambiar_el_id(self):
        otro_admin = get_user_model().objects.create_user(
            username="admin-otro-edificio",
            password="Clave-segura-2026",
        )
        UsuarioEdificio.objects.create(
            usuario=otro_admin,
            edificio=self.otro_edificio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )
        self.client.force_login(otro_admin)
        response = self.client.get(
            reverse(
                "finance:apartamento_editar",
                args=[self.edificio.pk, self.apartamento.pk],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_numero_duplicado_muestra_error_y_no_crea_unidad(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("finance:apartamento_crear", args=[self.edificio.pk]),
            self.datos(numero="a-101"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un apartamento")
        self.assertEqual(
            Apartamento.objects.filter(edificio=self.edificio).count(),
            1,
        )
