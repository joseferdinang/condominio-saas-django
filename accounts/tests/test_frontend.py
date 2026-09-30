from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio
from finance.models import Cargo, Pago, PeriodoCuota
from finance.services import confirmar_pago, registrar_pago
from people.models import Persona, RelacionApartamento


class FrontendPorRolTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.edificio = Edificio.objects.create(
            nombre="Residencial Los Jardines",
            direccion="Santiago de los Caballeros",
        )
        self.otro_edificio = Edificio.objects.create(
            nombre="Residencial Las Palmas",
            direccion="Santiago de los Caballeros",
        )
        self.apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="101",
            cuota_mensual=Decimal("4000.00"),
        )
        self.admin = user_model.objects.create_user(
            username="admin-frontend",
            password="Clave-segura-2026",
        )
        self.residente = user_model.objects.create_user(
            username="maria",
            first_name="María",
            password="Clave-segura-2026",
        )
        UsuarioEdificio.objects.create(
            usuario=self.admin,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )
        UsuarioEdificio.objects.create(
            usuario=self.admin,
            edificio=self.otro_edificio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )
        UsuarioEdificio.objects.create(
            usuario=self.residente,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.RESIDENTE,
        )
        persona = Persona.objects.create(
            usuario=self.residente,
            nombre_completo="María Pérez",
            telefono="809-555-0101",
            correo="maria@example.test",
        )
        RelacionApartamento.objects.create(
            persona=persona,
            apartamento=self.apartamento,
            tipo=RelacionApartamento.Tipo.PROPIETARIO,
            fecha_inicio=timezone.localdate() - timedelta(days=30),
            puede_acceder_portal=True,
            puede_ver_estado_cuenta=True,
        )
        periodo = PeriodoCuota.objects.create(
            edificio=self.edificio,
            anio=timezone.localdate().year,
            mes=timezone.localdate().month,
            fecha_vencimiento=date(
                timezone.localdate().year,
                timezone.localdate().month,
                10,
            ),
            creado_por=self.admin,
        )
        self.cargo = Cargo.objects.create(
            apartamento=self.apartamento,
            periodo=periodo,
            tipo=Cargo.Tipo.CUOTA_MENSUAL,
            concepto="Cuota mensual",
            importe=Decimal("4000.00"),
            fecha_vencimiento=periodo.fecha_vencimiento,
            creado_por=self.admin,
        )

    def test_inicio_residente_prioriza_saldo_pago_y_avisos(self):
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hola, María")
        self.assertContains(response, "RD$ 4,000.00")
        self.assertContains(response, "Reportar pago")
        self.assertContains(response, "Cargos pendientes")
        self.assertContains(response, "Cuota mensual")
        self.assertContains(response, "Pagos registrados")
        self.assertContains(response, "Aún no hay pagos registrados")
        self.assertContains(response, "Navegación móvil")

    def test_residente_ve_sus_pagos_y_recibo_confirmado(self):
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("500.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.TRANSFERENCIA,
            usuario=self.admin,
            referencia="TRX-RESIDENTE",
        )
        confirmar_pago(
            pago=pago,
            usuario=self.admin,
            aplicaciones=[(self.cargo, Decimal("500.00"))],
        )
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TRX-RESIDENTE")
        self.assertContains(response, "RD$ 500.00")
        self.assertContains(response, "Descargar recibo")
        recibo_url = reverse(
            "finance:recibo_descargar", args=[self.edificio.pk, pago.pk]
        )
        self.assertContains(response, recibo_url)

    def test_residente_no_ve_cargos_ni_pagos_de_otro_edificio(self):
        apartamento_ajeno = Apartamento.objects.create(
            edificio=self.otro_edificio,
            numero="999",
            cuota_mensual=Decimal("8000.00"),
        )
        periodo_ajeno = PeriodoCuota.objects.create(
            edificio=self.otro_edificio,
            anio=timezone.localdate().year,
            mes=timezone.localdate().month,
            fecha_vencimiento=timezone.localdate(),
            creado_por=self.admin,
        )
        Cargo.objects.create(
            apartamento=apartamento_ajeno,
            periodo=periodo_ajeno,
            tipo=Cargo.Tipo.CUOTA_MENSUAL,
            concepto="CARGO CONFIDENCIAL AJENO",
            importe=Decimal("8000.00"),
            fecha_vencimiento=timezone.localdate(),
            creado_por=self.admin,
        )
        pago_ajeno = registrar_pago(
            apartamento=apartamento_ajeno,
            importe_total=Decimal("8000.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.EFECTIVO,
            usuario=self.admin,
            referencia="PAGO CONFIDENCIAL AJENO",
        )
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "CARGO CONFIDENCIAL AJENO")
        self.assertNotContains(response, "PAGO CONFIDENCIAL AJENO")
        self.assertNotContains(response, str(pago_ajeno.importe_total))

    def test_navegacion_residente_oculta_finanzas_administrativas(self):
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertNotContains(
            response,
            reverse("finance:gastos_lista", args=[self.edificio.pk]),
        )
        self.assertNotContains(
            response,
            reverse("finance:reportes_index", args=[self.edificio.pk]),
        )
        self.assertContains(
            response,
            reverse(
                "finance:pago_registrar",
                args=[self.edificio.pk, self.apartamento.pk],
            ),
        )

    def test_administrador_ve_acciones_y_selector_multi_edificio(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertContains(response, "Registrar gasto")
        self.assertContains(response, "Generar reporte")
        self.assertContains(response, "Usuarios")
        self.assertContains(response, self.otro_edificio.nombre)
        self.assertContains(response, 'role="progressbar"')
        self.assertContains(response, "metric-cleared")


class FormatoMonedaTests(TestCase):
    def test_filtro_dop_usa_simbolo_miles_y_decimales(self):
        rendered = Template(
            "{% load formatting %}{{ value|dop }}"
        ).render(Context({"value": Decimal("12345.60")}))

        self.assertEqual(rendered, "RD$ 12,345.60")
