from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.validators import telefono_validator


class Persona(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="persona",
        blank=True,
        null=True,
        help_text="Cuenta opcional utilizada para resolver acceso al portal.",
    )
    nombre_completo = models.CharField(max_length=180)
    telefono = models.CharField(max_length=25, validators=[telefono_validator])
    correo = models.EmailField()
    identificacion = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        unique=True,
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre_completo", "id"]
        verbose_name = "persona"
        verbose_name_plural = "personas"
        indexes = [
            models.Index(
                fields=["activo", "nombre_completo"],
                name="ppl_pers_act_nom_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.nombre_completo = self.nombre_completo.strip()
        self.telefono = self.telefono.strip()
        self.correo = self.correo.strip().lower()
        self.identificacion = (
            self.identificacion.strip() if self.identificacion else None
        )

    def __str__(self):
        return self.nombre_completo


class RelacionApartamento(models.Model):
    class Tipo(models.TextChoices):
        PROPIETARIO = "PROPIETARIO", "Propietario"
        INQUILINO = "INQUILINO", "Inquilino"
        OCUPANTE = "OCUPANTE", "Ocupante"

    persona = models.ForeignKey(
        Persona,
        on_delete=models.PROTECT,
        related_name="relaciones_apartamento",
    )
    apartamento = models.ForeignKey(
        "buildings.Apartamento",
        on_delete=models.PROTECT,
        related_name="relaciones_personas",
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    fecha_inicio = models.DateField()
    fecha_finalizacion = models.DateField(blank=True, null=True)
    puede_acceder_portal = models.BooleanField(default=False)
    puede_ver_estado_cuenta = models.BooleanField(default=False)
    puede_recibir_comunicaciones = models.BooleanField(default=True)

    class Meta:
        ordering = ["apartamento", "-fecha_inicio", "persona"]
        verbose_name = "relación con apartamento"
        verbose_name_plural = "relaciones con apartamentos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    tipo__in=["PROPIETARIO", "INQUILINO", "OCUPANTE"]
                ),
                name="ck_rel_tipo_valido",
            ),
            models.UniqueConstraint(
                fields=["persona", "apartamento", "tipo", "fecha_inicio"],
                name="uq_rel_persona_apto_tipo_inicio",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(fecha_finalizacion__isnull=True)
                    | models.Q(fecha_finalizacion__gte=models.F("fecha_inicio"))
                ),
                name="ck_rel_fechas_validas",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(puede_ver_estado_cuenta=False)
                    | models.Q(puede_acceder_portal=True)
                ),
                name="ck_rel_estado_requiere_portal",
            ),
        ]
        indexes = [
            models.Index(
                fields=["apartamento", "tipo", "fecha_finalizacion"],
                name="ppl_rel_apto_tipo_fin_idx",
            ),
            models.Index(
                fields=["persona", "fecha_finalizacion"],
                name="ppl_rel_pers_fin_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.fecha_finalizacion
            and self.fecha_finalizacion < self.fecha_inicio
        ):
            raise ValidationError(
                {
                    "fecha_finalizacion": (
                        "La fecha de finalización no puede ser anterior al inicio."
                    )
                }
            )
        if self.puede_ver_estado_cuenta and not self.puede_acceder_portal:
            raise ValidationError(
                {
                    "puede_ver_estado_cuenta": (
                        "Para ver el estado de cuenta debe tener acceso al portal."
                    )
                }
            )

    def __str__(self):
        return f"{self.persona} · {self.apartamento} · {self.get_tipo_display()}"
