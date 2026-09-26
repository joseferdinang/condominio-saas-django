from django.contrib import admin

from core.admin import BuildingScopedAdminMixin

from .models import Persona, RelacionApartamento


@admin.register(Persona)
class PersonaAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "relaciones_apartamento__apartamento__edificio_id"
    list_display = (
        "nombre_completo",
        "usuario",
        "telefono",
        "correo",
        "identificacion",
        "activo",
    )
    list_filter = ("activo",)
    search_fields = (
        "nombre_completo",
        "telefono",
        "correo",
        "identificacion",
        "usuario__username",
        "usuario__email",
    )
    autocomplete_fields = ("usuario",)
    ordering = ("nombre_completo",)


@admin.register(RelacionApartamento)
class RelacionApartamentoAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "apartamento__edificio_id"
    list_display = (
        "persona",
        "apartamento",
        "tipo",
        "fecha_inicio",
        "fecha_finalizacion",
        "puede_acceder_portal",
    )
    list_filter = (
        "tipo",
        "puede_acceder_portal",
        "puede_ver_estado_cuenta",
        "puede_recibir_comunicaciones",
        "apartamento__edificio",
    )
    search_fields = (
        "persona__nombre_completo",
        "persona__identificacion",
        "apartamento__numero",
        "apartamento__edificio__nombre",
    )
    autocomplete_fields = ("persona", "apartamento")
    date_hierarchy = "fecha_inicio"
