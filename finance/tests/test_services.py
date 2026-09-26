from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio
from finance.models import AplicacionPago, Cargo, Gasto, Pago, PeriodoCuota
from finance.services import (
    anular_cargo,
    anular_pago,
    calcular_conciliacion,
    calcular_saldo_apartamento,
    confirmar_gasto,
    confirmar_pago,
    generar_cuotas_mensuales,
    registrar_gasto,
    registrar_pago,
    registrar_saldo_inicial,
)


class FinancialServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.edificio = Edificio.objects.create(
            nombre="Residencial Financiero",
            direccion="Santiago",
        )
        self.apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="1-A",
            cuota_mensual=Decimal("1000.00"),
        )
        self.otro_apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="2-A",
            cuota_mensual=Decimal("1500.00"),
        )
        self.administrador = user_model.objects.create_user(
            username="admin-finanzas"
        )
        self.tesorero = user_model.objects.create_user(
            username="tesorero-finanzas"
        )
        self.residente = user_model.objects.create_user(
            username="residente-finanzas"
        )
        UsuarioEdificio.objects.bulk_create(
            [
                UsuarioEdificio(
                    usuario=self.administrador,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
                UsuarioEdificio(
                    usuario=self.tesorero,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.TESORERO,
                ),
                UsuarioEdificio(
                    usuario=self.residente,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.RESIDENTE,
                ),
            ]
        )

    def generar_periodo(self, mes=1):
        periodo, _ = generar_cuotas_mensuales(
            edificio=self.edificio,
            anio=2026,
            mes=mes,
            fecha_vencimiento=date(2026, mes, 10),
            usuario=self.administrador,
        )
        return periodo

    def test_generar_el_mismo_periodo_dos_veces_no_duplica_cargos(self):
        periodo_1, creados_1 = generar_cuotas_mensuales(
            edificio=self.edificio,
            anio=2026,
            mes=1,
            fecha_vencimiento=date(2026, 1, 10),
            usuario=self.administrador,
        )
        periodo_2, creados_2 = generar_cuotas_mensuales(
            edificio=self.edificio,
            anio=2026,
            mes=1,
            fecha_vencimiento=date(2026, 1, 10),
            usuario=self.administrador,
        )

        self.assertEqual(periodo_1, periodo_2)
        self.assertEqual((creados_1, creados_2), (2, 0))
        self.assertEqual(PeriodoCuota.objects.count(), 1)
        self.assertEqual(Cargo.objects.count(), 2)

    def test_abono_parcial_actualiza_saldo_y_estado(self):
        periodo = self.generar_periodo()
        cargo = Cargo.objects.get(
            periodo=periodo,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("400.00"),
            fecha=date(2026, 1, 5),
            metodo=Pago.Metodo.TRANSFERENCIA,
            usuario=self.tesorero,
        )

        confirmar_pago(
            pago=pago,
            usuario=self.tesorero,
            aplicaciones=[(cargo, Decimal("400.00"))],
        )

        cargo.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.CONFIRMADO)
        self.assertEqual(cargo.estado, Cargo.Estado.PARCIAL)
        self.assertEqual(cargo.saldo_pendiente, Decimal("600.00"))

    def test_un_pago_se_aplica_a_dos_cargos(self):
        periodo_1 = self.generar_periodo(mes=1)
        periodo_2 = self.generar_periodo(mes=2)
        cargo_1 = Cargo.objects.get(
            periodo=periodo_1,
            apartamento=self.apartamento,
        )
        cargo_2 = Cargo.objects.get(
            periodo=periodo_2,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("1500.00"),
            fecha=date(2026, 2, 8),
            metodo=Pago.Metodo.EFECTIVO,
            usuario=self.tesorero,
        )

        confirmar_pago(
            pago=pago,
            usuario=self.administrador,
            aplicaciones=[
                (cargo_1, Decimal("1000.00")),
                (cargo_2, Decimal("500.00")),
            ],
        )

        cargo_1.refresh_from_db()
        cargo_2.refresh_from_db()
        self.assertEqual(pago.aplicaciones.count(), 2)
        self.assertEqual(cargo_1.estado, Cargo.Estado.PAGADO)
        self.assertEqual(cargo_2.estado, Cargo.Estado.PARCIAL)
        self.assertEqual(cargo_2.saldo_pendiente, Decimal("500.00"))

    def test_intento_de_sobrepago_es_rechazado_atomicamente(self):
        periodo = self.generar_periodo()
        cargo = Cargo.objects.get(
            periodo=periodo,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("1100.00"),
            fecha=date(2026, 1, 5),
            metodo=Pago.Metodo.DEPOSITO,
            usuario=self.tesorero,
        )

        with self.assertRaises(ValidationError):
            confirmar_pago(
                pago=pago,
                usuario=self.tesorero,
                aplicaciones=[(cargo, Decimal("1100.00"))],
            )

        pago.refresh_from_db()
        cargo.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertEqual(cargo.estado, Cargo.Estado.PENDIENTE)
        self.assertFalse(AplicacionPago.objects.filter(pago=pago).exists())

    def test_gasto_confirmado(self):
        gasto = registrar_gasto(
            edificio=self.edificio,
            categoria=Gasto.Categoria.MANTENIMIENTO,
            concepto="Reparación de bomba",
            importe=Decimal("750.00"),
            fecha=date(2026, 1, 12),
            usuario=self.tesorero,
            proveedor="Servicios del Cibao",
        )

        confirmar_gasto(gasto=gasto, usuario=self.administrador)

        gasto.refresh_from_db()
        self.assertEqual(gasto.estado, Gasto.Estado.CONFIRMADO)
        self.assertEqual(gasto.confirmado_por, self.administrador)
        self.assertIsNotNone(gasto.fecha_confirmacion)

    def test_anulacion_conserva_aplicaciones_y_reabre_el_cargo(self):
        periodo = self.generar_periodo()
        cargo = Cargo.objects.get(
            periodo=periodo,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("1000.00"),
            fecha=date(2026, 1, 5),
            metodo=Pago.Metodo.TRANSFERENCIA,
            usuario=self.tesorero,
        )
        confirmar_pago(
            pago=pago,
            usuario=self.administrador,
            aplicaciones=[(cargo, Decimal("1000.00"))],
        )

        anular_pago(
            pago=pago,
            usuario=self.administrador,
            motivo="Transferencia devuelta",
        )

        pago.refresh_from_db()
        cargo.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.ANULADO)
        self.assertEqual(pago.anulado_por, self.administrador)
        self.assertEqual(pago.motivo_anulacion, "Transferencia devuelta")
        self.assertEqual(pago.aplicaciones.count(), 1)
        self.assertEqual(cargo.estado, Cargo.Estado.PENDIENTE)
        self.assertEqual(cargo.saldo_pendiente, Decimal("1000.00"))

    def test_conciliacion_saldo_inicial_mas_ingresos_menos_gastos(self):
        registrar_saldo_inicial(
            edificio=self.edificio,
            importe=Decimal("10000.00"),
            fecha_corte=date(2026, 1, 31),
            concepto="Saldo de banco al cierre",
            usuario=self.administrador,
        )
        periodo = self.generar_periodo(mes=2)
        cargo = Cargo.objects.get(
            periodo=periodo,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("1000.00"),
            fecha=date(2026, 2, 5),
            metodo=Pago.Metodo.TRANSFERENCIA,
            usuario=self.tesorero,
        )
        confirmar_pago(
            pago=pago,
            usuario=self.administrador,
            aplicaciones=[(cargo, Decimal("1000.00"))],
        )
        gasto = registrar_gasto(
            edificio=self.edificio,
            categoria=Gasto.Categoria.SERVICIOS,
            concepto="Energía áreas comunes",
            importe=Decimal("300.00"),
            fecha=date(2026, 2, 7),
            usuario=self.tesorero,
        )
        confirmar_gasto(gasto=gasto, usuario=self.administrador)

        conciliacion = calcular_conciliacion(
            edificio=self.edificio,
            fecha_hasta=date(2026, 2, 28),
        )

        self.assertEqual(conciliacion.saldo_inicial, Decimal("10000.00"))
        self.assertEqual(conciliacion.ingresos, Decimal("1000.00"))
        self.assertEqual(conciliacion.gastos, Decimal("300.00"))
        self.assertEqual(conciliacion.saldo_final, Decimal("10700.00"))

    def test_saldo_de_apartamento_incluye_apertura_cargos_y_pagos(self):
        registrar_saldo_inicial(
            edificio=self.edificio,
            apartamento=self.apartamento,
            importe=Decimal("250.00"),
            fecha_corte=date(2025, 12, 31),
            concepto="Balance anterior",
            usuario=self.administrador,
        )
        periodo = self.generar_periodo()
        cargo = Cargo.objects.get(
            periodo=periodo,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("400.00"),
            fecha=date(2026, 1, 5),
            metodo=Pago.Metodo.EFECTIVO,
            usuario=self.tesorero,
        )
        confirmar_pago(
            pago=pago,
            usuario=self.tesorero,
            aplicaciones=[(cargo, Decimal("400.00"))],
        )

        self.assertEqual(
            calcular_saldo_apartamento(self.apartamento),
            Decimal("850.00"),
        )

    def test_permisos_financieros(self):
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("100.00"),
            fecha=date(2026, 1, 5),
            metodo=Pago.Metodo.EFECTIVO,
            usuario=self.tesorero,
        )
        self.assertIsNotNone(pago.pk)

        with self.assertRaises(PermissionDenied):
            registrar_pago(
                apartamento=self.apartamento,
                importe_total=Decimal("100.00"),
                fecha=date(2026, 1, 5),
                metodo=Pago.Metodo.EFECTIVO,
                usuario=self.residente,
            )
        with self.assertRaises(PermissionDenied):
            registrar_gasto(
                edificio=self.edificio,
                categoria=Gasto.Categoria.OTRO,
                concepto="No autorizado",
                importe=Decimal("100.00"),
                fecha=date(2026, 1, 5),
                usuario=self.residente,
            )

    def test_movimientos_financieros_no_se_eliminan(self):
        gasto = registrar_gasto(
            edificio=self.edificio,
            categoria=Gasto.Categoria.OTRO,
            concepto="Movimiento protegido",
            importe=Decimal("100.00"),
            fecha=date(2026, 1, 5),
            usuario=self.tesorero,
        )

        with self.assertRaises(ValidationError):
            gasto.delete()
        with self.assertRaises(ValidationError):
            Gasto.objects.filter(pk=gasto.pk).delete()

    def test_cargo_con_aplicacion_pendiente_no_puede_anularse(self):
        periodo = self.generar_periodo()
        cargo = Cargo.objects.get(
            periodo=periodo,
            apartamento=self.apartamento,
        )
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("100.00"),
            fecha=date(2026, 1, 5),
            metodo=Pago.Metodo.EFECTIVO,
            usuario=self.tesorero,
        )
        AplicacionPago.objects.create(
            pago=pago,
            cargo=cargo,
            importe_aplicado=Decimal("100.00"),
        )

        with self.assertRaises(ValidationError):
            anular_cargo(
                cargo=cargo,
                usuario=self.administrador,
                motivo="Corrección",
            )
