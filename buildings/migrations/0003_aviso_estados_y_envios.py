import django.db.models.deletion
from django.db import migrations, models


def migrar_estado_publicado(apps, schema_editor):
    Aviso = apps.get_model("buildings", "Aviso")
    Aviso.objects.filter(publicado=True).update(estado="PUBLICADO")


class Migration(migrations.Migration):
    dependencies = [
        ("buildings", "0002_aviso"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="aviso",
            name="bld_aviso_pub_fecha_idx",
        ),
        migrations.RenameField(
            model_name="aviso",
            old_name="fecha_publicacion",
            new_name="fecha",
        ),
        migrations.AddField(
            model_name="aviso",
            name="estado",
            field=models.CharField(
                choices=[("BORRADOR", "Borrador"), ("PUBLICADO", "Publicado")],
                default="BORRADOR",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="aviso",
            name="fijado",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            migrar_estado_publicado,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="aviso",
            name="publicado",
        ),
        migrations.AlterModelOptions(
            name="aviso",
            options={"ordering": ["-fijado", "-fecha", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="aviso",
            constraint=models.CheckConstraint(
                condition=models.Q(("estado__in", ["BORRADOR", "PUBLICADO"])),
                name="ck_aviso_estado_valido",
            ),
        ),
        migrations.AddIndex(
            model_name="aviso",
            index=models.Index(
                fields=["edificio", "estado", "fijado", "fecha"],
                name="bld_aviso_est_fij_idx",
            ),
        ),
        migrations.CreateModel(
            name="EnvioAviso",
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
                ("destinatario", models.EmailField(max_length=254)),
                ("fecha_envio", models.DateTimeField(blank=True, null=True)),
                (
                    "fecha_ultimo_intento",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("ENVIADO", "Enviado"),
                            ("FALLIDO", "Fallido"),
                        ],
                        default="PENDIENTE",
                        max_length=9,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                ("numero_intentos", models.PositiveIntegerField(default=0)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "aviso",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="envios",
                        to="buildings.aviso",
                    ),
                ),
            ],
            options={
                "verbose_name": "envío de aviso",
                "verbose_name_plural": "envíos de avisos",
                "ordering": ["-fecha_ultimo_intento", "destinatario"],
                "indexes": [
                    models.Index(
                        fields=["aviso", "estado"],
                        name="bld_env_aviso_est_idx",
                    ),
                    models.Index(
                        fields=["destinatario", "estado"],
                        name="bld_env_dest_est_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("aviso", "destinatario"),
                        name="uq_envio_aviso_destinatario",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("estado__in", ["PENDIENTE", "ENVIADO", "FALLIDO"])
                        ),
                        name="ck_envio_aviso_estado",
                    ),
                    models.CheckConstraint(
                        condition=(
                            ~models.Q(("estado", "ENVIADO"))
                            | models.Q(("error", ""), ("fecha_envio__isnull", False))
                        ),
                        name="ck_envio_aviso_exito",
                    ),
                    models.CheckConstraint(
                        condition=(
                            ~models.Q(("estado", "FALLIDO"))
                            | ~models.Q(("error", ""))
                        ),
                        name="ck_envio_aviso_error",
                    ),
                ],
            },
        ),
    ]
