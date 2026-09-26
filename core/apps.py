from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Auditoría"

    def ready(self):
        from .audit import conectar_auditoria

        conectar_auditoria()
