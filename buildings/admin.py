from django.contrib import admin

from django.core.exceptions import PermissionDenied, ValidationError

from accounts.models import UsuarioEdificio
from core.admin import BuildingScopedAdminMixin

from .models import (
    Apartamento,
    Aviso,
    Edificio,
    EnvioAviso,
    ReservaZona,
    ZonaComun,
)
from .services import enviar_aviso_por_correo, publicar_aviso


@admin.register(Edificio)
class EdificioAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "id"
    allow_tenant_change = True
    list_display = (
        "nombre",
        "telefono_administrativo",
        "correo_administrativo",
        "activo",
        "fecha_creacion",
    )
    list_filter = ("activo",)
    search_fields = ("nombre", "direccion", "correo_administrativo")
    readonly_fields = ("fecha_creacion",)
    ordering = ("nombre",)


@admin.register(Apartamento)
class ApartamentoAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    allow_tenant_add = True
    allow_tenant_change = True
    list_display = (
        "numero",
        "edificio",
        "cuota_mensual",
        "porcentaje_contribucion",
        "peso_voto",
        "activo",
    )
    list_filter = (
        "activo",
        ("edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("numero", "edificio__nombre")
    autocomplete_fields = ("edificio",)
    ordering = ("edificio__nombre", "numero")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "edificio" and not request.user.is_superuser:
            kwargs["queryset"] = Edificio.objects.filter(
                usuarios_autorizados__usuario=request.user,
                usuarios_autorizados__rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                usuarios_autorizados__activo=True,
                activo=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            allowed = self._building_ids(
                request, self.tenant_change_roles
            ).filter(edificio_id=obj.edificio_id).exists()
            if not allowed:
                raise PermissionDenied
        super().save_model(request, obj, form, change)


@admin.register(Aviso)
class AvisoAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    allow_tenant_add = True
    allow_tenant_change = True
    list_display = (
        "titulo",
        "edificio",
        "estado",
        "fijado",
        "fecha",
    )
    list_filter = (
        "estado",
        "fijado",
        ("edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("titulo", "contenido", "edificio__nombre")
    readonly_fields = ("creado_por", "fecha_creacion")
    actions = ("publicar_seleccionados", "enviar_seleccionados")

    @admin.action(description="Publicar avisos seleccionados")
    def publicar_seleccionados(self, request, queryset):
        publicados = 0
        for aviso in queryset:
            publicar_aviso(aviso=aviso, usuario=request.user)
            publicados += 1
        self.message_user(request, f"Avisos publicados: {publicados}.")

    @admin.action(description="Enviar avisos publicados por correo")
    def enviar_seleccionados(self, request, queryset):
        enviados = fallidos = omitidos = 0
        for aviso in queryset:
            try:
                resultado = enviar_aviso_por_correo(
                    aviso=aviso,
                    usuario=request.user,
                )
            except ValidationError as exc:
                self.message_user(request, f"{aviso}: {exc}", level="warning")
                continue
            enviados += resultado.enviados
            fallidos += resultado.fallidos
            omitidos += resultado.omitidos
        self.message_user(
            request,
            f"Enviados: {enviados}; fallidos: {fallidos}; omitidos: {omitidos}.",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "edificio" and not request.user.is_superuser:
            kwargs["queryset"] = Edificio.objects.filter(
                usuarios_autorizados__usuario=request.user,
                usuarios_autorizados__rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                usuarios_autorizados__activo=True,
                activo=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            allowed = self._building_ids(
                request, self.tenant_change_roles
            ).filter(edificio_id=obj.edificio_id).exists()
            if not allowed:
                raise PermissionDenied
        if not change:
            obj.creado_por = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(EnvioAviso)
class EnvioAvisoAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "aviso__edificio_id"
    list_display = (
        "aviso",
        "destinatario",
        "estado",
        "numero_intentos",
        "fecha_envio",
        "fecha_ultimo_intento",
    )
    list_filter = (
        "estado",
        ("aviso__edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("destinatario", "aviso__titulo", "error")
    readonly_fields = (
        "aviso",
        "destinatario",
        "fecha_envio",
        "fecha_ultimo_intento",
        "estado",
        "error",
        "numero_intentos",
        "fecha_creacion",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ZonaComun)
class ZonaComunAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    allow_tenant_add = True
    allow_tenant_change = True
    list_display = (
        "nombre",
        "edificio",
        "hora_apertura",
        "hora_cierre",
        "duracion_bloque_minutos",
        "activo",
    )
    list_filter = ("activo", ("edificio", admin.RelatedOnlyFieldListFilter))
    search_fields = ("nombre", "ubicacion", "edificio__nombre")
    autocomplete_fields = ("edificio",)
    readonly_fields = ("fecha_creacion", "fecha_actualizacion")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "edificio" and not request.user.is_superuser:
            kwargs["queryset"] = Edificio.objects.filter(
                usuarios_autorizados__usuario=request.user,
                usuarios_autorizados__rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                usuarios_autorizados__activo=True,
                activo=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ReservaZona)
class ReservaZonaAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "zona__edificio_id"
    tenant_view_roles = (UsuarioEdificio.Rol.ADMINISTRADOR,)
    list_display = (
        "zona",
        "fecha",
        "hora_inicio",
        "hora_fin",
        "estado",
        "usuario",
    )
    list_filter = ("estado", "fecha", ("zona__edificio", admin.RelatedOnlyFieldListFilter))
    search_fields = ("zona__nombre", "usuario__username", "detalle_privado")
    readonly_fields = (
        "zona",
        "usuario",
        "fecha",
        "hora_inicio",
        "hora_fin",
        "detalle_privado",
        "estado",
        "creada_en",
        "cancelada_en",
        "cancelada_por",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
