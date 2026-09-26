from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.models import UsuarioEdificio
from accounts.services import puede_registrar_finanzas
from buildings.models import Apartamento, Edificio
from core.admin import BuildingScopedAdminMixin

from .models import AplicacionPago, Cargo, Gasto, Pago, PeriodoCuota, SaldoInicial
from .services import confirmar_gasto, confirmar_pago


FINANCIAL_ROLES = (
    UsuarioEdificio.Rol.ADMINISTRADOR,
    UsuarioEdificio.Rol.TESORERO,
)


class FinancialAdminMixin(BuildingScopedAdminMixin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PeriodoCuota)
class PeriodoCuotaAdmin(FinancialAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    list_display = (
        "edificio",
        "anio",
        "mes",
        "fecha_vencimiento",
        "estado",
        "fecha_creacion",
    )
    list_filter = (
        "estado",
        "anio",
        "mes",
        ("edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("edificio__nombre",)
    readonly_fields = (
        "edificio",
        "anio",
        "mes",
        "fecha_vencimiento",
        "estado",
        "creado_por",
        "fecha_creacion",
        "anulado_por",
        "fecha_anulacion",
        "motivo_anulacion",
    )


@admin.register(Cargo)
class CargoAdmin(FinancialAdminMixin, admin.ModelAdmin):
    building_lookup = "apartamento__edificio_id"
    list_display = (
        "apartamento",
        "periodo",
        "tipo",
        "importe",
        "saldo_pendiente",
        "fecha_vencimiento",
        "estado",
    )
    list_filter = (
        "estado",
        "tipo",
        ("apartamento__edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "apartamento__numero",
        "apartamento__edificio__nombre",
        "concepto",
    )
    readonly_fields = (
        "apartamento",
        "periodo",
        "tipo",
        "concepto",
        "importe",
        "fecha_vencimiento",
        "estado",
        "creado_por",
        "fecha_creacion",
        "anulado_por",
        "fecha_anulacion",
        "motivo_anulacion",
    )


class AplicacionPagoInline(admin.TabularInline):
    model = AplicacionPago
    extra = 1
    fields = ("cargo", "importe_aplicado", "fecha_creacion")
    readonly_fields = ("fecha_creacion",)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj):
        return bool(obj and obj.estado == Pago.Estado.PENDIENTE)

    def has_change_permission(self, request, obj=None):
        return bool(obj and obj.estado == Pago.Estado.PENDIENTE)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "cargo" and not request.user.is_superuser:
            kwargs["queryset"] = Cargo.objects.filter(
                apartamento__edificio__usuarios_autorizados__usuario=request.user,
                apartamento__edificio__usuarios_autorizados__activo=True,
                apartamento__edificio__usuarios_autorizados__rol__in=FINANCIAL_ROLES,
            ).exclude(estado=Cargo.Estado.ANULADO).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Pago)
class PagoAdmin(FinancialAdminMixin, admin.ModelAdmin):
    building_lookup = "apartamento__edificio_id"
    tenant_add_roles = FINANCIAL_ROLES
    tenant_change_roles = FINANCIAL_ROLES
    allow_tenant_add = True
    allow_tenant_change = True
    list_display = (
        "id",
        "apartamento",
        "importe_total",
        "importe_aplicado",
        "fecha",
        "metodo",
        "estado",
    )
    list_filter = (
        "estado",
        "metodo",
        ("apartamento__edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "referencia",
        "apartamento__numero",
        "apartamento__edificio__nombre",
    )
    readonly_fields = (
        "estado",
        "registrado_por",
        "confirmado_por",
        "fecha_confirmacion",
        "rechazado_por",
        "fecha_rechazo",
        "motivo_rechazo",
        "fecha_creacion",
        "anulado_por",
        "fecha_anulacion",
        "motivo_anulacion",
    )
    inlines = (AplicacionPagoInline,)
    actions = ("confirmar_pagos_seleccionados",)

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.estado != Pago.Estado.PENDIENTE:
            return False
        return super().has_change_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "apartamento" and not request.user.is_superuser:
            kwargs["queryset"] = Apartamento.objects.filter(
                edificio__usuarios_autorizados__usuario=request.user,
                edificio__usuarios_autorizados__activo=True,
                edificio__usuarios_autorizados__rol__in=FINANCIAL_ROLES,
                activo=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not puede_registrar_finanzas(
            request.user, obj.apartamento.edificio
        ):
            raise PermissionDenied
        if not change:
            obj.registrado_por = request.user
            obj.estado = Pago.Estado.PENDIENTE
        obj.full_clean()
        super().save_model(request, obj, form, change)

    @admin.action(description="Confirmar pagos seleccionados")
    def confirmar_pagos_seleccionados(self, request, queryset):
        confirmados = 0
        for pago in queryset:
            try:
                confirmar_pago(pago=pago, usuario=request.user)
            except (PermissionDenied, ValidationError) as exc:
                self.message_user(
                    request,
                    f"Pago #{pago.pk}: {str(exc)}",
                    level=messages.ERROR,
                )
            else:
                confirmados += 1
        if confirmados:
            self.message_user(
                request,
                f"{confirmados} pago(s) confirmado(s).",
                level=messages.SUCCESS,
            )


@admin.register(AplicacionPago)
class AplicacionPagoAdmin(FinancialAdminMixin, admin.ModelAdmin):
    building_lookup = "pago__apartamento__edificio_id"
    list_display = ("pago", "cargo", "importe_aplicado", "fecha_creacion")
    search_fields = (
        "pago__referencia",
        "cargo__concepto",
        "cargo__apartamento__numero",
    )
    readonly_fields = ("pago", "cargo", "importe_aplicado", "fecha_creacion")


@admin.register(Gasto)
class GastoAdmin(FinancialAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    tenant_add_roles = FINANCIAL_ROLES
    tenant_change_roles = FINANCIAL_ROLES
    allow_tenant_add = True
    allow_tenant_change = True
    list_display = (
        "fecha",
        "edificio",
        "categoria",
        "concepto",
        "importe",
        "estado",
    )
    list_filter = (
        "estado",
        "categoria",
        ("edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("concepto", "proveedor", "edificio__nombre")
    readonly_fields = (
        "estado",
        "creado_por",
        "confirmado_por",
        "fecha_confirmacion",
        "fecha_creacion",
        "anulado_por",
        "fecha_anulacion",
        "motivo_anulacion",
    )
    actions = ("confirmar_gastos_seleccionados",)

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.estado != Gasto.Estado.PENDIENTE:
            return False
        return super().has_change_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "edificio" and not request.user.is_superuser:
            kwargs["queryset"] = Edificio.objects.filter(
                usuarios_autorizados__usuario=request.user,
                usuarios_autorizados__activo=True,
                usuarios_autorizados__rol__in=FINANCIAL_ROLES,
                activo=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not puede_registrar_finanzas(request.user, obj.edificio):
            raise PermissionDenied
        if not change:
            obj.creado_por = request.user
            obj.estado = Gasto.Estado.PENDIENTE
        obj.full_clean()
        super().save_model(request, obj, form, change)

    @admin.action(description="Confirmar gastos seleccionados")
    def confirmar_gastos_seleccionados(self, request, queryset):
        confirmados = 0
        for gasto in queryset:
            try:
                confirmar_gasto(gasto=gasto, usuario=request.user)
            except (PermissionDenied, ValidationError) as exc:
                self.message_user(
                    request,
                    f"Gasto #{gasto.pk}: {str(exc)}",
                    level=messages.ERROR,
                )
            else:
                confirmados += 1
        if confirmados:
            self.message_user(
                request,
                f"{confirmados} gasto(s) confirmado(s).",
                level=messages.SUCCESS,
            )


@admin.register(SaldoInicial)
class SaldoInicialAdmin(FinancialAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    tenant_add_roles = FINANCIAL_ROLES
    allow_tenant_add = True
    list_display = (
        "edificio",
        "apartamento",
        "importe",
        "fecha_corte",
        "estado",
    )
    list_filter = (
        "estado",
        ("edificio", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("concepto", "apartamento__numero", "edificio__nombre")
    readonly_fields = (
        "estado",
        "registrado_por",
        "fecha_creacion",
        "anulado_por",
        "fecha_anulacion",
        "motivo_anulacion",
    )

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.name == "edificio":
            kwargs["queryset"] = Edificio.objects.filter(
                usuarios_autorizados__usuario=request.user,
                usuarios_autorizados__activo=True,
                usuarios_autorizados__rol__in=FINANCIAL_ROLES,
            ).distinct()
        if not request.user.is_superuser and db_field.name == "apartamento":
            kwargs["queryset"] = Apartamento.objects.filter(
                edificio__usuarios_autorizados__usuario=request.user,
                edificio__usuarios_autorizados__activo=True,
                edificio__usuarios_autorizados__rol__in=FINANCIAL_ROLES,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not puede_registrar_finanzas(request.user, obj.edificio):
            raise PermissionDenied
        if not change:
            obj.registrado_por = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)
