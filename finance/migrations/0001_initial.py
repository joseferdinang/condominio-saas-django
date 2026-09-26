import django.core.validators
import django.db.models.deletion
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("buildings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PeriodoCuota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_anulacion", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("anio", models.PositiveSmallIntegerField(verbose_name="año")),
                ("mes", models.PositiveSmallIntegerField()),
                ("fecha_vencimiento", models.DateField()),
                ("estado", models.CharField(choices=[("ABIERTO", "Abierto"), ("CERRADO", "Cerrado"), ("ANULADO", "Anulado")], default="ABIERTO", max_length=8)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("anulado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="periodos_cuota_creados", to=settings.AUTH_USER_MODEL)),
                ("edificio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="periodos_cuota", to="buildings.edificio")),
            ],
            options={
                "verbose_name": "período de cuota",
                "verbose_name_plural": "períodos de cuota",
                "ordering": ["-anio", "-mes", "edificio"],
                "indexes": [models.Index(fields=["edificio", "estado", "anio", "mes"], name="fin_period_edif_est_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("edificio", "anio", "mes"), name="uq_periodo_edif_anio_mes"),
                    models.CheckConstraint(condition=models.Q(("mes__gte", 1), ("mes__lte", 12)), name="ck_periodo_mes_valido"),
                    models.CheckConstraint(condition=models.Q(("anio__gte", 2000), ("anio__lte", 2200)), name="ck_periodo_anio_valido"),
                    models.CheckConstraint(condition=models.Q(("estado__in", ["ABIERTO", "CERRADO", "ANULADO"])), name="ck_periodo_estado_valido"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "ANULADO"), _negated=True), models.Q(("anulado_por__isnull", False), ("fecha_anulacion__isnull", False), models.Q(("motivo_anulacion", ""), _negated=True)), _connector="OR"), name="ck_periodo_anulacion_traza"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Cargo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_anulacion", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("tipo", models.CharField(choices=[("CUOTA_MENSUAL", "Cuota mensual"), ("EXTRAORDINARIO", "Cargo extraordinario"), ("AJUSTE", "Ajuste"), ("OTRO", "Otro")], max_length=18)),
                ("concepto", models.CharField(max_length=240)),
                ("importe", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("fecha_vencimiento", models.DateField()),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("PARCIAL", "Parcial"), ("PAGADO", "Pagado"), ("ANULADO", "Anulado")], default="PENDIENTE", max_length=9)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("anulado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("apartamento", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cargos", to="buildings.apartamento")),
                ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cargos_creados", to=settings.AUTH_USER_MODEL)),
                ("periodo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cargos", to="finance.periodocuota")),
            ],
            options={
                "ordering": ["fecha_vencimiento", "apartamento", "id"],
                "indexes": [
                    models.Index(fields=["apartamento", "estado", "fecha_vencimiento"], name="fin_cargo_apto_est_idx"),
                    models.Index(fields=["periodo", "tipo"], name="fin_cargo_period_tipo_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("tipo", "CUOTA_MENSUAL")), fields=("apartamento", "periodo", "tipo"), name="uq_cargo_cuota_apto_periodo"),
                    models.CheckConstraint(condition=models.Q(("importe__gt", 0)), name="ck_cargo_importe_positivo"),
                    models.CheckConstraint(condition=models.Q(("tipo__in", ["CUOTA_MENSUAL", "EXTRAORDINARIO", "AJUSTE", "OTRO"])), name="ck_cargo_tipo_valido"),
                    models.CheckConstraint(condition=models.Q(("estado__in", ["PENDIENTE", "PARCIAL", "PAGADO", "ANULADO"])), name="ck_cargo_estado_valido"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "ANULADO"), _negated=True), models.Q(("anulado_por__isnull", False), ("fecha_anulacion__isnull", False), models.Q(("motivo_anulacion", ""), _negated=True)), _connector="OR"), name="ck_cargo_anulacion_traza"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Pago",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_anulacion", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("importe_total", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("fecha", models.DateField()),
                ("metodo", models.CharField(choices=[("TRANSFERENCIA", "Transferencia"), ("EFECTIVO", "Efectivo"), ("DEPOSITO", "Depósito"), ("OTRO", "Otro")], max_length=13)),
                ("referencia", models.CharField(blank=True, max_length=160)),
                ("comprobante", models.FileField(blank=True, upload_to="finanzas/pagos/%Y/%m/")),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("CONFIRMADO", "Confirmado"), ("RECHAZADO", "Rechazado"), ("ANULADO", "Anulado")], default="PENDIENTE", max_length=10)),
                ("fecha_confirmacion", models.DateTimeField(blank=True, null=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("anulado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("apartamento", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pagos", to="buildings.apartamento")),
                ("confirmado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pagos_confirmados", to=settings.AUTH_USER_MODEL)),
                ("registrado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pagos_registrados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-fecha", "-id"],
                "indexes": [models.Index(fields=["apartamento", "estado", "fecha"], name="fin_pago_apto_est_idx")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("importe_total__gt", 0)), name="ck_pago_importe_positivo"),
                    models.CheckConstraint(condition=models.Q(("metodo__in", ["TRANSFERENCIA", "EFECTIVO", "DEPOSITO", "OTRO"])), name="ck_pago_metodo_valido"),
                    models.CheckConstraint(condition=models.Q(("estado__in", ["PENDIENTE", "CONFIRMADO", "RECHAZADO", "ANULADO"])), name="ck_pago_estado_valido"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "CONFIRMADO"), _negated=True), models.Q(("confirmado_por__isnull", False), ("fecha_confirmacion__isnull", False)), _connector="OR"), name="ck_pago_confirmacion_traza"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "ANULADO"), _negated=True), models.Q(("anulado_por__isnull", False), ("fecha_anulacion__isnull", False), models.Q(("motivo_anulacion", ""), _negated=True)), _connector="OR"), name="ck_pago_anulacion_traza"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AplicacionPago",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("importe_aplicado", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("cargo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aplicaciones", to="finance.cargo")),
                ("pago", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aplicaciones", to="finance.pago")),
            ],
            options={
                "verbose_name": "aplicación de pago",
                "verbose_name_plural": "aplicaciones de pagos",
                "ordering": ["pago", "cargo"],
                "indexes": [models.Index(fields=["cargo", "pago"], name="fin_aplic_cargo_pago_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("pago", "cargo"), name="uq_aplicacion_pago_cargo"),
                    models.CheckConstraint(condition=models.Q(("importe_aplicado__gt", 0)), name="ck_aplic_importe_positivo"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Gasto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_anulacion", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("categoria", models.CharField(choices=[("MANTENIMIENTO", "Mantenimiento"), ("SERVICIOS", "Servicios"), ("PERSONAL", "Personal"), ("SUMINISTROS", "Suministros"), ("OTRO", "Otro")], max_length=13)),
                ("concepto", models.CharField(max_length=240)),
                ("importe", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("fecha", models.DateField()),
                ("proveedor", models.CharField(blank=True, max_length=180)),
                ("comprobante", models.FileField(blank=True, upload_to="finanzas/gastos/%Y/%m/")),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("CONFIRMADO", "Confirmado"), ("ANULADO", "Anulado")], default="PENDIENTE", max_length=10)),
                ("fecha_confirmacion", models.DateTimeField(blank=True, null=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("anulado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("confirmado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="gastos_confirmados", to=settings.AUTH_USER_MODEL)),
                ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gastos_creados", to=settings.AUTH_USER_MODEL)),
                ("edificio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gastos", to="buildings.edificio")),
            ],
            options={
                "ordering": ["-fecha", "-id"],
                "indexes": [models.Index(fields=["edificio", "estado", "fecha"], name="fin_gasto_edif_est_idx")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("importe__gt", 0)), name="ck_gasto_importe_positivo"),
                    models.CheckConstraint(condition=models.Q(("categoria__in", ["MANTENIMIENTO", "SERVICIOS", "PERSONAL", "SUMINISTROS", "OTRO"])), name="ck_gasto_categoria_valida"),
                    models.CheckConstraint(condition=models.Q(("estado__in", ["PENDIENTE", "CONFIRMADO", "ANULADO"])), name="ck_gasto_estado_valido"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "CONFIRMADO"), _negated=True), models.Q(("confirmado_por__isnull", False), ("fecha_confirmacion__isnull", False)), _connector="OR"), name="ck_gasto_confirmacion_traza"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "ANULADO"), _negated=True), models.Q(("anulado_por__isnull", False), ("fecha_anulacion__isnull", False), models.Q(("motivo_anulacion", ""), _negated=True)), _connector="OR"), name="ck_gasto_anulacion_traza"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SaldoInicial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_anulacion", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("importe", models.DecimalField(decimal_places=2, max_digits=14)),
                ("fecha_corte", models.DateField()),
                ("concepto", models.CharField(max_length=240)),
                ("estado", models.CharField(choices=[("CONFIRMADO", "Confirmado"), ("ANULADO", "Anulado")], default="CONFIRMADO", max_length=10)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("anulado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("apartamento", models.ForeignKey(blank=True, help_text="Vacío para el saldo de caja/banco del edificio.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="saldos_iniciales", to="buildings.apartamento")),
                ("edificio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="saldos_iniciales", to="buildings.edificio")),
                ("registrado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="saldos_iniciales_registrados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "saldo inicial",
                "verbose_name_plural": "saldos iniciales",
                "ordering": ["-fecha_corte", "edificio", "apartamento"],
                "indexes": [models.Index(fields=["edificio", "fecha_corte", "estado"], name="fin_saldo_edif_fecha_idx")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("importe", 0), _negated=True), name="ck_saldo_importe_no_cero"),
                    models.CheckConstraint(condition=models.Q(("estado__in", ["CONFIRMADO", "ANULADO"])), name="ck_saldo_estado_valido"),
                    models.CheckConstraint(condition=models.Q(models.Q(("estado", "ANULADO"), _negated=True), models.Q(("anulado_por__isnull", False), ("fecha_anulacion__isnull", False), models.Q(("motivo_anulacion", ""), _negated=True)), _connector="OR"), name="ck_saldo_anulacion_traza"),
                    models.UniqueConstraint(condition=models.Q(("apartamento__isnull", True), ("estado", "CONFIRMADO")), fields=("edificio",), name="uq_saldo_edif_confirmado"),
                    models.UniqueConstraint(condition=models.Q(("apartamento__isnull", False), ("estado", "CONFIRMADO")), fields=("apartamento",), name="uq_saldo_apto_confirmado"),
                ],
            },
        ),
    ]
