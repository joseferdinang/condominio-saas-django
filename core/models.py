from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class CambioQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("La bitácora de cambios no se puede modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("La bitácora de cambios no se puede modificar.")

    def delete(self):
        raise ValidationError("La bitácora de cambios no se puede eliminar.")


class Cambio(models.Model):
    class Accion(models.TextChoices):
        CREAR = "CREAR", "Creación"
        MODIFICAR = "MODIFICAR", "Modificación"
        ELIMINAR = "ELIMINAR", "Eliminación"

    objects = CambioQuerySet.as_manager()
    edificio = models.ForeignKey(
        "buildings.Edificio", on_delete=models.PROTECT, related_name="cambios"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cambios_realizados",
    )
    usuario_nombre = models.CharField(max_length=150, default="Sistema")
    accion = models.CharField(max_length=10, choices=Accion.choices)
    modelo = models.CharField(max_length=100)
    objeto_id = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "cambio"
        verbose_name_plural = "cambios"
        ordering = ["-fecha", "-pk"]
        indexes = [
            models.Index(fields=["edificio", "-fecha"], name="core_cambio_edif_fecha_idx"),
            models.Index(fields=["usuario", "-fecha"], name="core_cambio_usr_fecha_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(accion__in=["CREAR", "MODIFICAR", "ELIMINAR"]),
                name="ck_cambio_accion_valida",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("La bitácora de cambios no se puede modificar.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La bitácora de cambios no se puede eliminar.")

    def __str__(self):
        return f"{self.get_accion_display()}: {self.descripcion}"
