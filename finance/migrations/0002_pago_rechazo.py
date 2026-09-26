import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pago",
            name="fecha_rechazo",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pago",
            name="motivo_rechazo",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="pago",
            name="rechazado_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pagos_rechazados", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name="pago",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("estado", "RECHAZADO"), _negated=True),
                    models.Q(
                        ("rechazado_por__isnull", False),
                        ("fecha_rechazo__isnull", False),
                        models.Q(("motivo_rechazo", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="ck_pago_rechazo_traza",
            ),
        ),
    ]
