from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from core.validators import telefono_validator


class Edificio(models.Model):
    nombre = models.CharField(max_length=160)
    direccion = models.TextField()
    telefono_administrativo = models.CharField(
        max_length=25,
        blank=True,
        validators=[telefono_validator],
    )
    correo_administrativo = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre", "id"]
        verbose_name = "edificio"
        verbose_name_plural = "edificios"
        indexes = [
            models.Index(
                fields=["activo", "nombre"],
                name="bld_edif_act_nom_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.nombre = self.nombre.strip()
        self.direccion = self.direccion.strip()
        self.telefono_administrativo = self.telefono_administrativo.strip()
        self.correo_administrativo = self.correo_administrativo.strip().lower()

    def __str__(self):
        return self.nombre


class Apartamento(models.Model):
    edificio = models.ForeignKey(
        Edificio,
        on_delete=models.PROTECT,
        related_name="apartamentos",
    )
    numero = models.CharField(max_length=30)
    cuota_mensual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    porcentaje_contribucion = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[
            MinValueValidator(Decimal("0.0000")),
            MaxValueValidator(Decimal("100.0000")),
        ],
        help_text="Porcentaje entre 0 y 100 utilizado para distribuir gastos.",
    )
    peso_voto = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("1.0000"),
        validators=[MinValueValidator(Decimal("0.0000"))],
        help_text="Peso de voto independiente del porcentaje de gastos.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["edificio__nombre", "numero", "id"]
        verbose_name = "apartamento"
        verbose_name_plural = "apartamentos"
        constraints = [
            models.UniqueConstraint(
                models.F("edificio"),
                Lower("numero"),
                name="uq_apto_edif_numero_ci",
            ),
            models.CheckConstraint(
                condition=models.Q(cuota_mensual__gte=0),
                name="ck_apto_cuota_no_neg",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(porcentaje_contribucion__gte=0)
                    & models.Q(porcentaje_contribucion__lte=100)
                ),
                name="ck_apto_porcentaje_rango",
            ),
            models.CheckConstraint(
                condition=models.Q(peso_voto__gte=0),
                name="ck_apto_peso_voto_no_neg",
            ),
        ]
        indexes = [
            models.Index(
                fields=["edificio", "activo"],
                name="bld_apto_edif_act_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.numero = self.numero.strip().upper()

    def __str__(self):
        return f"{self.edificio} · Apto. {self.numero}"


class Aviso(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        PUBLICADO = "PUBLICADO", "Publicado"

    edificio = models.ForeignKey(
        Edificio,
        on_delete=models.PROTECT,
        related_name="avisos",
    )
    titulo = models.CharField(max_length=180)
    contenido = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)
    fijado = models.BooleanField(default=False)
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="avisos_creados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fijado", "-fecha", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado__in=["BORRADOR", "PUBLICADO"]),
                name="ck_aviso_estado_valido",
            )
        ]
        indexes = [
            models.Index(
                fields=["edificio", "estado", "fijado", "fecha"],
                name="bld_aviso_est_fij_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.titulo = self.titulo.strip()
        self.contenido = self.contenido.strip()

    def __str__(self):
        return f"{self.edificio} · {self.titulo}"


class EnvioAviso(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIADO = "ENVIADO", "Enviado"
        FALLIDO = "FALLIDO", "Fallido"

    aviso = models.ForeignKey(
        Aviso,
        on_delete=models.PROTECT,
        related_name="envios",
    )
    destinatario = models.EmailField()
    fecha_envio = models.DateTimeField(blank=True, null=True)
    fecha_ultimo_intento = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(
        max_length=9,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    error = models.TextField(blank=True)
    numero_intentos = models.PositiveIntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_ultimo_intento", "destinatario"]
        verbose_name = "envío de aviso"
        verbose_name_plural = "envíos de avisos"
        constraints = [
            models.UniqueConstraint(
                fields=["aviso", "destinatario"],
                name="uq_envio_aviso_destinatario",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    estado__in=["PENDIENTE", "ENVIADO", "FALLIDO"]
                ),
                name="ck_envio_aviso_estado",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado="ENVIADO")
                    | models.Q(fecha_envio__isnull=False, error="")
                ),
                name="ck_envio_aviso_exito",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado="FALLIDO") | ~models.Q(error="")
                ),
                name="ck_envio_aviso_error",
            ),
        ]
        indexes = [
            models.Index(
                fields=["aviso", "estado"],
                name="bld_env_aviso_est_idx",
            ),
            models.Index(
                fields=["destinatario", "estado"],
                name="bld_env_dest_est_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.destinatario = self.destinatario.strip().lower()
        self.error = self.error.strip()

    def __str__(self):
        return f"{self.aviso} · {self.destinatario} · {self.get_estado_display()}"


class ZonaComun(models.Model):
    edificio = models.ForeignKey(
        Edificio,
        on_delete=models.PROTECT,
        related_name="zonas_comunes",
    )
    nombre = models.CharField(max_length=120)
    ubicacion = models.CharField(max_length=160, blank=True)
    descripcion = models.TextField(blank=True)
    hora_apertura = models.TimeField()
    hora_cierre = models.TimeField()
    duracion_bloque_minutos = models.PositiveSmallIntegerField(
        default=60,
        validators=[MinValueValidator(30), MaxValueValidator(240)],
        help_text="Duración permitida para cada reservación.",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre", "id"]
        verbose_name = "zona reservable"
        verbose_name_plural = "zonas reservables"
        constraints = [
            models.UniqueConstraint(
                models.F("edificio"),
                Lower("nombre"),
                name="uq_zona_edif_nombre_ci",
            ),
            models.CheckConstraint(
                condition=models.Q(hora_apertura__lt=models.F("hora_cierre")),
                name="ck_zona_horario_valido",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(duracion_bloque_minutos__gte=30)
                    & models.Q(duracion_bloque_minutos__lte=240)
                ),
                name="ck_zona_duracion_rango",
            ),
        ]
        indexes = [
            models.Index(
                fields=["edificio", "activo", "nombre"],
                name="bld_zona_edif_act_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.nombre = self.nombre.strip()
        self.ubicacion = self.ubicacion.strip()
        self.descripcion = self.descripcion.strip()
        if self.hora_apertura and self.hora_cierre:
            if self.hora_apertura >= self.hora_cierre:
                raise ValidationError(
                    {"hora_cierre": "La hora de cierre debe ser posterior a la apertura."}
                )

    def __str__(self):
        return f"{self.edificio} · {self.nombre}"


class ReservaZona(models.Model):
    class Estado(models.TextChoices):
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CANCELADA = "CANCELADA", "Cancelada"

    zona = models.ForeignKey(
        ZonaComun,
        on_delete=models.PROTECT,
        related_name="reservaciones",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reservaciones_zonas",
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    detalle_privado = models.CharField(
        max_length=240,
        blank=True,
        help_text="Solo tú y la administración podrán verlo.",
    )
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.CONFIRMADA,
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    cancelada_en = models.DateTimeField(blank=True, null=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reservaciones_canceladas",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["fecha", "hora_inicio", "zona__nombre", "id"]
        verbose_name = "reservación de zona"
        verbose_name_plural = "reservaciones de zonas"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado__in=["CONFIRMADA", "CANCELADA"]),
                name="ck_reserva_zona_estado",
            ),
            models.CheckConstraint(
                condition=models.Q(hora_inicio__lt=models.F("hora_fin")),
                name="ck_reserva_zona_horas",
            ),
            models.UniqueConstraint(
                fields=["zona", "fecha", "hora_inicio"],
                condition=models.Q(estado="CONFIRMADA"),
                name="uq_reserva_zona_inicio_activo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["zona", "fecha", "estado", "hora_inicio"],
                name="bld_res_zona_fecha_idx",
            ),
            models.Index(
                fields=["usuario", "fecha", "estado"],
                name="bld_res_usuario_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.detalle_privado = self.detalle_privado.strip()
        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            raise ValidationError(
                {"hora_fin": "La hora final debe ser posterior a la inicial."}
            )
        if self.estado == self.Estado.CONFIRMADA:
            if self.cancelada_en or self.cancelada_por_id:
                raise ValidationError("Una reservación confirmada no puede estar cancelada.")
        elif not self.cancelada_en or not self.cancelada_por_id:
            raise ValidationError(
                "Una reservación cancelada debe registrar quién y cuándo la canceló."
            )

    def __str__(self):
        return (
            f"{self.zona} · {self.fecha:%d/%m/%Y} "
            f"{self.hora_inicio:%H:%M}–{self.hora_fin:%H:%M}"
        )
