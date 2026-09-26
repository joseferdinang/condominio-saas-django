from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from datetime import date

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio, ZonaComun
from core.models import Cambio
from finance.models import Cargo
from finance.services import anular_periodo, generar_cuotas_mensuales


class CambiosAdminTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Residencial Uno", direccion="Santiago")
        self.ajeno = Edificio.objects.create(nombre="Residencial Dos", direccion="Santiago")
        self.admin_usuario = get_user_model().objects.create_user(
            username="admin-auditoria", is_staff=True
        )
        self.tesorero = get_user_model().objects.create_user(
            username="tesorero-auditoria", is_staff=True
        )
        UsuarioEdificio.objects.create(
            usuario=self.admin_usuario,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )
        UsuarioEdificio.objects.create(
            usuario=self.tesorero,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.TESORERO,
        )

    def test_el_portal_registra_actor_fecha_y_objeto(self):
        self.client.force_login(self.admin_usuario)
        response = self.client.post(
            reverse("buildings:zona_crear", args=[self.edificio.pk]),
            {
                "nombre": "Salón social", "ubicacion": "Primer nivel",
                "hora_apertura": "08:00", "hora_cierre": "20:00",
                "duracion_bloque_minutos": 60, "activo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        zona = ZonaComun.objects.get(edificio=self.edificio)
        cambio = Cambio.objects.get(modelo="buildings.ZonaComun", objeto_id=str(zona.pk))
        self.assertEqual(cambio.usuario, self.admin_usuario)
        self.assertEqual(cambio.edificio, self.edificio)
        self.assertEqual(cambio.accion, Cambio.Accion.CREAR)
        self.assertIsNotNone(cambio.fecha)

    def test_admin_ve_solo_cambios_de_su_edificio_y_tesorero_no_accede(self):
        modelo_admin = admin.site._registry[Cambio]
        factory = RequestFactory()
        request = factory.get("/admin/core/cambio/")
        request.user = self.admin_usuario
        self.assertTrue(modelo_admin.has_view_permission(request))
        self.assertTrue(modelo_admin.get_queryset(request).filter(edificio=self.edificio).exists())
        self.assertFalse(modelo_admin.get_queryset(request).filter(edificio=self.ajeno).exists())
        self.assertFalse(modelo_admin.has_add_permission(request))
        self.assertFalse(modelo_admin.has_change_permission(request))
        self.assertFalse(modelo_admin.has_delete_permission(request))

        request.user = self.tesorero
        self.assertFalse(modelo_admin.has_view_permission(request))
        self.assertFalse(modelo_admin.get_queryset(request).exists())

    def test_cambio_no_se_modifica_ni_elimina_por_orm(self):
        cambio = Cambio.objects.filter(edificio=self.edificio).first()
        cambio.descripcion = "alterado"
        with self.assertRaises(ValidationError):
            cambio.save()
        with self.assertRaises(ValidationError):
            cambio.delete()
        with self.assertRaises(ValidationError):
            Cambio.objects.filter(pk=cambio.pk).delete()
        with self.assertRaises(ValidationError):
            Cambio.objects.filter(pk=cambio.pk).update(descripcion="alterado")

    def test_comando_financiero_conserva_actor_al_crear_y_anular(self):
        Apartamento.objects.create(
            edificio=self.edificio, numero="101", cuota_mensual="2500.00"
        )
        periodo, creados = generar_cuotas_mensuales(
            edificio=self.edificio, anio=2026, mes=10,
            fecha_vencimiento=date(2026, 10, 10), usuario=self.admin_usuario,
        )
        self.assertEqual(creados, 1)
        cargo = Cargo.objects.get(periodo=periodo)
        anular_periodo(periodo=periodo, usuario=self.admin_usuario, motivo="Corrección")
        for modelo, objeto_id in (
            ("finance.PeriodoCuota", periodo.pk), ("finance.Cargo", cargo.pk)
        ):
            with self.subTest(modelo=modelo):
                cambios = Cambio.objects.filter(modelo=modelo, objeto_id=str(objeto_id))
                self.assertEqual(
                    list(cambios.values_list("accion", flat=True)),
                    [Cambio.Accion.MODIFICAR, Cambio.Accion.CREAR],
                )
                self.assertTrue(all(item.usuario == self.admin_usuario for item in cambios))
