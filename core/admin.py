from accounts.models import UsuarioEdificio
from django.contrib import admin

from .models import Cambio


class BuildingScopedAdminMixin:
    """Scope Django Admin rows to buildings assigned to the staff user."""

    building_lookup = None
    tenant_view_roles = (
        UsuarioEdificio.Rol.ADMINISTRADOR,
        UsuarioEdificio.Rol.TESORERO,
        UsuarioEdificio.Rol.JUNTA,
    )
    tenant_add_roles = (UsuarioEdificio.Rol.ADMINISTRADOR,)
    tenant_change_roles = (UsuarioEdificio.Rol.ADMINISTRADOR,)
    allow_tenant_add = False
    allow_tenant_change = False

    @staticmethod
    def _is_technical_admin(request):
        return request.user.is_active and request.user.is_superuser

    def _building_ids(self, request, roles):
        if not request.user.is_active or not request.user.is_staff:
            return UsuarioEdificio.objects.none().values_list(
                "edificio_id", flat=True
            )
        return UsuarioEdificio.objects.filter(
            usuario=request.user,
            edificio__activo=True,
            activo=True,
            rol__in=roles,
        ).values_list("edificio_id", flat=True)

    def _scope_queryset(self, queryset, building_ids):
        if not self.building_lookup:
            return queryset.none()
        return queryset.filter(
            **{f"{self.building_lookup}__in": building_ids}
        ).distinct()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self._is_technical_admin(request):
            return queryset
        return self._scope_queryset(
            queryset,
            self._building_ids(request, self.tenant_view_roles),
        )

    def _has_object_access(self, request, obj, roles):
        if obj is None:
            return self._building_ids(request, roles).exists()
        queryset = super().get_queryset(request)
        return self._scope_queryset(
            queryset,
            self._building_ids(request, roles),
        ).filter(pk=obj.pk).exists()

    def has_module_permission(self, request):
        if self._is_technical_admin(request):
            return True
        return self._building_ids(request, self.tenant_view_roles).exists()

    def has_view_permission(self, request, obj=None):
        if self._is_technical_admin(request):
            return True
        return self._has_object_access(request, obj, self.tenant_view_roles)

    def has_add_permission(self, request):
        if self._is_technical_admin(request):
            return True
        return self.allow_tenant_add and self._building_ids(
            request, self.tenant_add_roles
        ).exists()

    def has_change_permission(self, request, obj=None):
        if self._is_technical_admin(request):
            return True
        return self.allow_tenant_change and self._has_object_access(
            request, obj, self.tenant_change_roles
        )

    def has_delete_permission(self, request, obj=None):
        return self._is_technical_admin(request)


class SuperuserOnlyAdminMixin(BuildingScopedAdminMixin):
    """Keep a model exclusively available to technical superusers."""

    tenant_view_roles = ()


@admin.register(Cambio)
class CambioAdmin(BuildingScopedAdminMixin, admin.ModelAdmin):
    building_lookup = "edificio_id"
    tenant_view_roles = (UsuarioEdificio.Rol.ADMINISTRADOR,)
    list_display = ("fecha", "edificio", "usuario_nombre", "accion", "modelo", "descripcion")
    list_filter = ("accion", "modelo", ("edificio", admin.RelatedOnlyFieldListFilter))
    search_fields = ("usuario_nombre", "modelo", "objeto_id", "descripcion")
    readonly_fields = ("fecha", "edificio", "usuario", "usuario_nombre", "accion", "modelo", "objeto_id", "descripcion")
    date_hierarchy = "fecha"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
