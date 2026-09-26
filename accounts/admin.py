from django.contrib import admin

from core.admin import BuildingScopedAdminMixin

from .models import PreferenciaVisual, UsuarioEdificio


@admin.register(UsuarioEdificio)
class UsuarioEdificioAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    tenant_view_roles = (UsuarioEdificio.Rol.ADMINISTRADOR,)
    list_display = (
        "usuario",
        "edificio",
        "rol",
        "activo",
        "fecha_creacion",
    )
    list_filter = (
        "rol",
        "activo",
        ("edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
        "edificio__nombre",
    )
    autocomplete_fields = ("usuario", "edificio")
    readonly_fields = ("fecha_creacion",)


@admin.register(PreferenciaVisual)
class PreferenciaVisualAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tema", "paleta", "actualizado_en")
    list_filter = ("tema", "paleta")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name")
    autocomplete_fields = ("usuario",)
    readonly_fields = ("actualizado_en",)
