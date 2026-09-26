from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_usuarioedificio_ck_usuario_edif_rol_valido"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PreferenciaVisual",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "tema",
                    models.CharField(
                        choices=[("claro", "Claro"), ("oscuro", "Oscuro")],
                        default="claro",
                        max_length=7,
                    ),
                ),
                (
                    "paleta",
                    models.CharField(
                        choices=[
                            ("oceano", "Océano"),
                            ("esmeralda", "Esmeralda"),
                            ("violeta", "Violeta"),
                            ("coral", "Coral"),
                        ],
                        default="oceano",
                        max_length=10,
                    ),
                ),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "usuario",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="preferencia_visual",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "preferencia visual",
                "verbose_name_plural": "preferencias visuales",
            },
        ),
        migrations.AddConstraint(
            model_name="preferenciavisual",
            constraint=models.CheckConstraint(
                condition=models.Q(("tema__in", ["claro", "oscuro"])),
                name="ck_preferencia_tema_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="preferenciavisual",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("paleta__in", ["oceano", "esmeralda", "violeta", "coral"])
                ),
                name="ck_preferencia_paleta_valida",
            ),
        ),
    ]
