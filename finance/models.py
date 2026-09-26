from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Sum


ZERO = Decimal("0.00")


class FinancialQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError(
            "Los movimientos financieros no se eliminan; deben anularse."
        )


class FinancialRecord(models.Model):
    objects = FinancialQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        raise ValidationError(
            "Los movimientos financieros no se eliminan; deben anularse."
        )


class AnulableRecord(FinancialRecord):
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
    )
    fecha_anulacion = models.DateTimeField(blank=True, null=True)
    motivo_anulacion = models.TextField(blank=True)

    class Meta:
        abstract = True


class PeriodoCuota(AnulableRecord):
    class Estado(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        CERRADO = "CERRADO", "Cerrado"
        ANULADO = "ANULADO", "Anulado"

    edificio = models.ForeignKey(
        "buildings.Edificio",
        on_delete=models.PROTECT,
        related_name="periodos_cuota",
    )
    anio = models.PositiveSmallIntegerField("año")
    mes = models.PositiveSmallIntegerField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=8,
        choices=Estado.choices,
        default=Estado.ABIERTO,
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="periodos_cuota_creados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-anio", "-mes", "edificio"]
        verbose_name = "período de cuota"
        verbose_name_plural = "períodos de cuota"
        constraints = [
            models.UniqueConstraint(
                fields=["edificio", "anio", "mes"],
                name="uq_periodo_edif_anio_mes",
            ),
            models.CheckConstraint(
                condition=Q(mes__gte=1) & Q(mes__lte=12),
                name="ck_periodo_mes_valido",
            ),
            models.CheckConstraint(
                condition=Q(anio__gte=2000) & Q(anio__lte=2200),
                name="ck_periodo_anio_valido",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["ABIERTO", "CERRADO", "ANULADO"]),
                name="ck_periodo_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="ANULADO")
                    | (
                        Q(anulado_por__isnull=False)
                        & Q(fecha_anulacion__isnull=False)
                        & ~Q(motivo_anulacion="")
                    )
                ),
                name="ck_periodo_anulacion_traza",
            ),
        ]
        indexes = [
            models.Index(
                fields=["edificio", "estado", "anio", "mes"],
                name="fin_period_edif_est_idx",
            )
        ]

    def __str__(self):
        return f"{self.edificio} · {self.mes:02d}/{self.anio}"


class Cargo(AnulableRecord):
    class Tipo(models.TextChoices):
        CUOTA_MENSUAL = "CUOTA_MENSUAL", "Cuota mensual"
        EXTRAORDINARIO = "EXTRAORDINARIO", "Cargo extraordinario"
        AJUSTE = "AJUSTE", "Ajuste"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PARCIAL = "PARCIAL", "Parcial"
        PAGADO = "PAGADO", "Pagado"
        ANULADO = "ANULADO", "Anulado"

    apartamento = models.ForeignKey(
        "buildings.Apartamento",
        on_delete=models.PROTECT,
        related_name="cargos",
    )
    periodo = models.ForeignKey(
        PeriodoCuota,
        on_delete=models.PROTECT,
        related_name="cargos",
    )
    tipo = models.CharField(max_length=18, choices=Tipo.choices)
    concepto = models.CharField(max_length=240)
    importe = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=9,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cargos_creados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_vencimiento", "apartamento", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["apartamento", "periodo", "tipo"],
                condition=Q(tipo="CUOTA_MENSUAL"),
                name="uq_cargo_cuota_apto_periodo",
            ),
            models.CheckConstraint(
                condition=Q(importe__gt=0),
                name="ck_cargo_importe_positivo",
            ),
            models.CheckConstraint(
                condition=Q(
                    tipo__in=[
                        "CUOTA_MENSUAL",
                        "EXTRAORDINARIO",
                        "AJUSTE",
                        "OTRO",
                    ]
                ),
                name="ck_cargo_tipo_valido",
            ),
            models.CheckConstraint(
                condition=Q(
                    estado__in=["PENDIENTE", "PARCIAL", "PAGADO", "ANULADO"]
                ),
                name="ck_cargo_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="ANULADO")
                    | (
                        Q(anulado_por__isnull=False)
                        & Q(fecha_anulacion__isnull=False)
                        & ~Q(motivo_anulacion="")
                    )
                ),
                name="ck_cargo_anulacion_traza",
            ),
        ]
        indexes = [
            models.Index(
                fields=["apartamento", "estado", "fecha_vencimiento"],
                name="fin_cargo_apto_est_idx",
            ),
            models.Index(
                fields=["periodo", "tipo"],
                name="fin_cargo_period_tipo_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.concepto = self.concepto.strip()
        if (
            self.apartamento_id
            and self.periodo_id
            and self.apartamento.edificio_id != self.periodo.edificio_id
        ):
            raise ValidationError(
                {"periodo": "El período y el apartamento deben pertenecer al mismo edificio."}
            )

    @property
    def total_aplicado(self):
        return self.aplicaciones.filter(
            pago__estado=Pago.Estado.CONFIRMADO
        ).aggregate(total=Sum("importe_aplicado"))["total"] or ZERO

    @property
    def saldo_pendiente(self):
        if self.estado == self.Estado.ANULADO:
            return ZERO
        return max(self.importe - self.total_aplicado, ZERO)

    def __str__(self):
        return f"{self.apartamento} · {self.concepto} · RD${self.importe}"


class Pago(AnulableRecord):
    class Metodo(models.TextChoices):
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"
        EFECTIVO = "EFECTIVO", "Efectivo"
        DEPOSITO = "DEPOSITO", "Depósito"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        ANULADO = "ANULADO", "Anulado"

    apartamento = models.ForeignKey(
        "buildings.Apartamento",
        on_delete=models.PROTECT,
        related_name="pagos",
    )
    importe_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fecha = models.DateField()
    metodo = models.CharField(max_length=13, choices=Metodo.choices)
    referencia = models.CharField(max_length=160, blank=True)
    comprobante = models.FileField(
        upload_to="finanzas/pagos/%Y/%m/",
        blank=True,
    )
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pagos_registrados",
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pagos_confirmados",
        blank=True,
        null=True,
    )
    fecha_confirmacion = models.DateTimeField(blank=True, null=True)
    rechazado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pagos_rechazados",
        blank=True,
        null=True,
    )
    fecha_rechazo = models.DateTimeField(blank=True, null=True)
    motivo_rechazo = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(importe_total__gt=0),
                name="ck_pago_importe_positivo",
            ),
            models.CheckConstraint(
                condition=Q(
                    metodo__in=["TRANSFERENCIA", "EFECTIVO", "DEPOSITO", "OTRO"]
                ),
                name="ck_pago_metodo_valido",
            ),
            models.CheckConstraint(
                condition=Q(
                    estado__in=["PENDIENTE", "CONFIRMADO", "RECHAZADO", "ANULADO"]
                ),
                name="ck_pago_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="CONFIRMADO")
                    | (
                        Q(confirmado_por__isnull=False)
                        & Q(fecha_confirmacion__isnull=False)
                    )
                ),
                name="ck_pago_confirmacion_traza",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="ANULADO")
                    | (
                        Q(anulado_por__isnull=False)
                        & Q(fecha_anulacion__isnull=False)
                        & ~Q(motivo_anulacion="")
                    )
                ),
                name="ck_pago_anulacion_traza",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="RECHAZADO")
                    | (
                        Q(rechazado_por__isnull=False)
                        & Q(fecha_rechazo__isnull=False)
                        & ~Q(motivo_rechazo="")
                    )
                ),
                name="ck_pago_rechazo_traza",
            ),
        ]
        indexes = [
            models.Index(
                fields=["apartamento", "estado", "fecha"],
                name="fin_pago_apto_est_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.referencia = self.referencia.strip()

    @property
    def importe_aplicado(self):
        return self.aplicaciones.aggregate(total=Sum("importe_aplicado"))[
            "total"
        ] or ZERO

    @property
    def importe_sin_aplicar(self):
        return max(self.importe_total - self.importe_aplicado, ZERO)

    def __str__(self):
        return f"Pago #{self.pk or 'nuevo'} · {self.apartamento} · RD${self.importe_total}"


class AplicacionPago(FinancialRecord):
    pago = models.ForeignKey(
        Pago,
        on_delete=models.PROTECT,
        related_name="aplicaciones",
    )
    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.PROTECT,
        related_name="aplicaciones",
    )
    importe_aplicado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pago", "cargo"]
        verbose_name = "aplicación de pago"
        verbose_name_plural = "aplicaciones de pagos"
        constraints = [
            models.UniqueConstraint(
                fields=["pago", "cargo"],
                name="uq_aplicacion_pago_cargo",
            ),
            models.CheckConstraint(
                condition=Q(importe_aplicado__gt=0),
                name="ck_aplic_importe_positivo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["cargo", "pago"],
                name="fin_aplic_cargo_pago_idx",
            )
        ]

    def clean(self):
        super().clean()
        if self.pago_id and self.cargo_id:
            if self.pago.apartamento_id != self.cargo.apartamento_id:
                raise ValidationError(
                    "El pago y el cargo deben pertenecer al mismo apartamento."
                )
            if self.pago.estado != Pago.Estado.PENDIENTE:
                raise ValidationError(
                    "Solo se pueden preparar aplicaciones para pagos pendientes."
                )
            if self.cargo.estado == Cargo.Estado.ANULADO:
                raise ValidationError("No se puede pagar un cargo anulado.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            pago = Pago.objects.select_for_update().get(pk=self.pago_id)
            cargo = Cargo.objects.select_for_update().get(pk=self.cargo_id)
            self.pago = pago
            self.cargo = cargo
            self.full_clean()

            otras_pago = pago.aplicaciones.exclude(pk=self.pk).aggregate(
                total=Sum("importe_aplicado")
            )["total"] or ZERO
            if otras_pago + self.importe_aplicado > pago.importe_total:
                raise ValidationError(
                    "El importe aplicado supera el importe total del pago."
                )

            otras_cargo = cargo.aplicaciones.exclude(pk=self.pk).filter(
                pago__estado__in=[
                    Pago.Estado.PENDIENTE,
                    Pago.Estado.CONFIRMADO,
                ]
            ).aggregate(total=Sum("importe_aplicado"))["total"] or ZERO
            if otras_cargo + self.importe_aplicado > cargo.importe:
                raise ValidationError(
                    "El importe aplicado supera el saldo pendiente del cargo."
                )
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pago} → {self.cargo} · RD${self.importe_aplicado}"


class Gasto(AnulableRecord):
    class Categoria(models.TextChoices):
        MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"
        SERVICIOS = "SERVICIOS", "Servicios"
        PERSONAL = "PERSONAL", "Personal"
        SUMINISTROS = "SUMINISTROS", "Suministros"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        ANULADO = "ANULADO", "Anulado"

    edificio = models.ForeignKey(
        "buildings.Edificio",
        on_delete=models.PROTECT,
        related_name="gastos",
    )
    categoria = models.CharField(max_length=13, choices=Categoria.choices)
    concepto = models.CharField(max_length=240)
    importe = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fecha = models.DateField()
    proveedor = models.CharField(max_length=180, blank=True)
    comprobante = models.FileField(
        upload_to="finanzas/gastos/%Y/%m/",
        blank=True,
    )
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="gastos_creados",
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="gastos_confirmados",
        blank=True,
        null=True,
    )
    fecha_confirmacion = models.DateTimeField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(importe__gt=0),
                name="ck_gasto_importe_positivo",
            ),
            models.CheckConstraint(
                condition=Q(
                    categoria__in=[
                        "MANTENIMIENTO",
                        "SERVICIOS",
                        "PERSONAL",
                        "SUMINISTROS",
                        "OTRO",
                    ]
                ),
                name="ck_gasto_categoria_valida",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["PENDIENTE", "CONFIRMADO", "ANULADO"]),
                name="ck_gasto_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="CONFIRMADO")
                    | (
                        Q(confirmado_por__isnull=False)
                        & Q(fecha_confirmacion__isnull=False)
                    )
                ),
                name="ck_gasto_confirmacion_traza",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="ANULADO")
                    | (
                        Q(anulado_por__isnull=False)
                        & Q(fecha_anulacion__isnull=False)
                        & ~Q(motivo_anulacion="")
                    )
                ),
                name="ck_gasto_anulacion_traza",
            ),
        ]
        indexes = [
            models.Index(
                fields=["edificio", "estado", "fecha"],
                name="fin_gasto_edif_est_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.concepto = self.concepto.strip()
        self.proveedor = self.proveedor.strip()

    def __str__(self):
        return f"{self.edificio} · {self.concepto} · RD${self.importe}"


class SaldoInicial(AnulableRecord):
    class Estado(models.TextChoices):
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        ANULADO = "ANULADO", "Anulado"

    edificio = models.ForeignKey(
        "buildings.Edificio",
        on_delete=models.PROTECT,
        related_name="saldos_iniciales",
    )
    apartamento = models.ForeignKey(
        "buildings.Apartamento",
        on_delete=models.PROTECT,
        related_name="saldos_iniciales",
        blank=True,
        null=True,
        help_text="Vacío para el saldo de caja/banco del edificio.",
    )
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    fecha_corte = models.DateField()
    concepto = models.CharField(max_length=240)
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.CONFIRMADO,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="saldos_iniciales_registrados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_corte", "edificio", "apartamento"]
        verbose_name = "saldo inicial"
        verbose_name_plural = "saldos iniciales"
        constraints = [
            models.CheckConstraint(
                condition=~Q(importe=0),
                name="ck_saldo_importe_no_cero",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["CONFIRMADO", "ANULADO"]),
                name="ck_saldo_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="ANULADO")
                    | (
                        Q(anulado_por__isnull=False)
                        & Q(fecha_anulacion__isnull=False)
                        & ~Q(motivo_anulacion="")
                    )
                ),
                name="ck_saldo_anulacion_traza",
            ),
            models.UniqueConstraint(
                fields=["edificio"],
                condition=Q(apartamento__isnull=True, estado="CONFIRMADO"),
                name="uq_saldo_edif_confirmado",
            ),
            models.UniqueConstraint(
                fields=["apartamento"],
                condition=Q(apartamento__isnull=False, estado="CONFIRMADO"),
                name="uq_saldo_apto_confirmado",
            ),
        ]
        indexes = [
            models.Index(
                fields=["edificio", "fecha_corte", "estado"],
                name="fin_saldo_edif_fecha_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.concepto = self.concepto.strip()
        if (
            self.apartamento_id
            and self.apartamento.edificio_id != self.edificio_id
        ):
            raise ValidationError(
                {"apartamento": "El apartamento debe pertenecer al edificio indicado."}
            )

    def __str__(self):
        destino = self.apartamento or self.edificio
        return f"{destino} · {self.concepto} · RD${self.importe}"
