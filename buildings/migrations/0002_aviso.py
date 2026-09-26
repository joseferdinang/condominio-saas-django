import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("buildings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Aviso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=180)),
                ("contenido", models.TextField()),
                ("publicado", models.BooleanField(default=False)),
                ("fecha_publicacion", models.DateTimeField(default=django.utils.timezone.now)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="avisos_creados", to=settings.AUTH_USER_MODEL)),
                ("edificio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="avisos", to="buildings.edificio")),
            ],
            options={
                "ordering": ["-fecha_publicacion", "-id"],
                "indexes": [models.Index(fields=["edificio", "publicado", "fecha_publicacion"], name="bld_aviso_pub_fecha_idx")],
            },
        )
    ]
