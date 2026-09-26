from django.conf import settings
from django.db import models


class UsuarioEdificio(models.Model):
    class Rol(models.TextChoices):
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
        TESORERO = "TESORERO", "Tesorero"
        JUNTA = "JUNTA", "Miembro de junta"
        RESIDENTE = "RESIDENTE", "Residente"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membresias_edificios",
    )
    edificio = models.ForeignKey(
        "buildings.Edificio",
        on_delete=models.PROTECT,
        related_name="usuarios_autorizados",
    )
    rol = models.CharField(max_length=13, choices=Rol.choices)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["edificio", "usuario"]
        verbose_name = "usuario de edificio"
        verbose_name_plural = "usuarios de edificios"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    rol__in=["ADMINISTRADOR", "TESORERO", "JUNTA", "RESIDENTE"]
                ),
                name="ck_usuario_edif_rol_valido",
            ),
            models.UniqueConstraint(
                fields=["usuario", "edificio"],
                name="uq_usuario_edificio",
            ),
        ]
        indexes = [
            models.Index(
                fields=["edificio", "rol", "activo"],
                name="acc_usr_edif_rol_act_idx",
            ),
            models.Index(
                fields=["usuario", "activo"],
                name="acc_usr_usuario_act_idx",
            ),
        ]

    def __str__(self):
        return f"{self.usuario} · {self.edificio} · {self.get_rol_display()}"


class PreferenciaVisual(models.Model):
    class Tema(models.TextChoices):
        CLARO = "claro", "Claro"
        OSCURO = "oscuro", "Oscuro"

    class Paleta(models.TextChoices):
        OCEANO = "oceano", "Océano"
        ESMERALDA = "esmeralda", "Esmeralda"
        VIOLETA = "violeta", "Violeta"
        CORAL = "coral", "Coral"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferencia_visual",
    )
    tema = models.CharField(
        max_length=7,
        choices=Tema.choices,
        default=Tema.CLARO,
    )
    paleta = models.CharField(
        max_length=10,
        choices=Paleta.choices,
        default=Paleta.OCEANO,
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "preferencia visual"
        verbose_name_plural = "preferencias visuales"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tema__in=["claro", "oscuro"]),
                name="ck_preferencia_tema_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    paleta__in=["oceano", "esmeralda", "violeta", "coral"]
                ),
                name="ck_preferencia_paleta_valida",
            ),
        ]

    def __str__(self):
        return f"{self.usuario} · {self.get_tema_display()} · {self.get_paleta_display()}"
