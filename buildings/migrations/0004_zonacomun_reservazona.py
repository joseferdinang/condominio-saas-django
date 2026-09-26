from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.text


class Migration(migrations.Migration):
    dependencies = [
        ("buildings", "0003_aviso_estados_y_envios"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ZonaComun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("ubicacion", models.CharField(blank=True, max_length=160)),
                ("descripcion", models.TextField(blank=True)),
                ("hora_apertura", models.TimeField()),
                ("hora_cierre", models.TimeField()),
                ("duracion_bloque_minutos", models.PositiveSmallIntegerField(default=60, help_text="Duración permitida para cada reservación.", validators=[django.core.validators.MinValueValidator(30), django.core.validators.MaxValueValidator(240)])),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("edificio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="zonas_comunes", to="buildings.edificio")),
            ],
            options={"verbose_name": "zona reservable", "verbose_name_plural": "zonas reservables", "ordering": ["nombre", "id"]},
        ),
        migrations.CreateModel(
            name="ReservaZona",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField()),
                ("hora_inicio", models.TimeField()),
                ("hora_fin", models.TimeField()),
                ("detalle_privado", models.CharField(blank=True, help_text="Solo tú y la administración podrán verlo.", max_length=240)),
                ("estado", models.CharField(choices=[("CONFIRMADA", "Confirmada"), ("CANCELADA", "Cancelada")], default="CONFIRMADA", max_length=10)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("cancelada_en", models.DateTimeField(blank=True, null=True)),
                ("cancelada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reservaciones_canceladas", to=settings.AUTH_USER_MODEL)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservaciones_zonas", to=settings.AUTH_USER_MODEL)),
                ("zona", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservaciones", to="buildings.zonacomun")),
            ],
            options={"verbose_name": "reservación de zona", "verbose_name_plural": "reservaciones de zonas", "ordering": ["fecha", "hora_inicio", "zona__nombre", "id"]},
        ),
        migrations.AddConstraint(
            model_name="zonacomun",
            constraint=models.UniqueConstraint(models.F("edificio"), django.db.models.functions.text.Lower("nombre"), name="uq_zona_edif_nombre_ci"),
        ),
        migrations.AddConstraint(
            model_name="zonacomun",
            constraint=models.CheckConstraint(condition=models.Q(("hora_apertura__lt", models.F("hora_cierre"))), name="ck_zona_horario_valido"),
        ),
        migrations.AddConstraint(
            model_name="zonacomun",
            constraint=models.CheckConstraint(condition=models.Q(("duracion_bloque_minutos__gte", 30), ("duracion_bloque_minutos__lte", 240)), name="ck_zona_duracion_rango"),
        ),
        migrations.AddIndex(model_name="zonacomun", index=models.Index(fields=["edificio", "activo", "nombre"], name="bld_zona_edif_act_idx")),
        migrations.AddConstraint(
            model_name="reservazona",
            constraint=models.CheckConstraint(condition=models.Q(("estado__in", ["CONFIRMADA", "CANCELADA"])), name="ck_reserva_zona_estado"),
        ),
        migrations.AddConstraint(
            model_name="reservazona",
            constraint=models.CheckConstraint(condition=models.Q(("hora_inicio__lt", models.F("hora_fin"))), name="ck_reserva_zona_horas"),
        ),
        migrations.AddConstraint(
            model_name="reservazona",
            constraint=models.UniqueConstraint(condition=models.Q(("estado", "CONFIRMADA")), fields=("zona", "fecha", "hora_inicio"), name="uq_reserva_zona_inicio_activo"),
        ),
        migrations.AddIndex(model_name="reservazona", index=models.Index(fields=["zona", "fecha", "estado", "hora_inicio"], name="bld_res_zona_fecha_idx")),
        migrations.AddIndex(model_name="reservazona", index=models.Index(fields=["usuario", "fecha", "estado"], name="bld_res_usuario_idx")),
    ]
