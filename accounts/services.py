from django.db.models import Q, QuerySet
from django.http import Http404
from django.utils import timezone

from buildings.models import Apartamento, Edificio

from .models import UsuarioEdificio


ROLES_QUE_VEN_TODOS_LOS_APARTAMENTOS = {
    UsuarioEdificio.Rol.ADMINISTRADOR,
    UsuarioEdificio.Rol.TESORERO,
    UsuarioEdificio.Rol.JUNTA,
}
ROLES_QUE_REGISTRAN_FINANZAS = {
    UsuarioEdificio.Rol.ADMINISTRADOR,
    UsuarioEdificio.Rol.TESORERO,
}


def membresias_activas(usuario) -> QuerySet[UsuarioEdificio]:
    if not usuario.is_authenticated or not usuario.is_active:
        return UsuarioEdificio.objects.none()
    return UsuarioEdificio.objects.filter(
        usuario=usuario,
        activo=True,
        edificio__activo=True,
    ).select_related("edificio")


def edificios_visibles(usuario) -> QuerySet[Edificio]:
    if not usuario.is_authenticated or not usuario.is_active:
        return Edificio.objects.none()
    if usuario.is_superuser:
        return Edificio.objects.filter(activo=True)
    return Edificio.objects.filter(
        usuarios_autorizados__in=membresias_activas(usuario)
    ).distinct()


def obtener_edificio_visible(usuario, edificio_id: int) -> Edificio:
    try:
        return edificios_visibles(usuario).get(pk=edificio_id)
    except Edificio.DoesNotExist as exc:
        raise Http404("Edificio no encontrado.") from exc


def obtener_membresia(usuario, edificio) -> UsuarioEdificio | None:
    if usuario.is_superuser:
        return None
    try:
        return membresias_activas(usuario).get(edificio=edificio)
    except UsuarioEdificio.DoesNotExist as exc:
        raise Http404("Edificio no encontrado.") from exc


def _filtro_relacion_vigente(usuario, *, requiere_estado_cuenta=False):
    hoy = timezone.localdate()
    filtro = (
        Q(relaciones_personas__persona__usuario=usuario)
        & Q(relaciones_personas__persona__activo=True)
        & Q(relaciones_personas__puede_acceder_portal=True)
        & Q(relaciones_personas__fecha_inicio__lte=hoy)
        & (
            Q(relaciones_personas__fecha_finalizacion__isnull=True)
            | Q(relaciones_personas__fecha_finalizacion__gte=hoy)
        )
    )
    if requiere_estado_cuenta:
        filtro &= Q(relaciones_personas__puede_ver_estado_cuenta=True)
    return filtro


def apartamentos_visibles(usuario, edificio) -> QuerySet[Apartamento]:
    apartamentos = Apartamento.objects.filter(
        edificio=edificio,
        activo=True,
    )
    if usuario.is_superuser:
        return apartamentos

    membresia = obtener_membresia(usuario, edificio)
    if membresia.rol in ROLES_QUE_VEN_TODOS_LOS_APARTAMENTOS:
        return apartamentos

    return apartamentos.filter(_filtro_relacion_vigente(usuario)).distinct()


def apartamentos_con_estado_cuenta(usuario, edificio) -> QuerySet[Apartamento]:
    apartamentos = apartamentos_visibles(usuario, edificio)
    if usuario.is_superuser:
        return apartamentos

    membresia = obtener_membresia(usuario, edificio)
    if membresia.rol in ROLES_QUE_VEN_TODOS_LOS_APARTAMENTOS:
        return apartamentos
    return Apartamento.objects.filter(
        edificio=edificio,
        activo=True,
    ).filter(
        _filtro_relacion_vigente(
            usuario,
            requiere_estado_cuenta=True,
        )
    ).distinct()


def obtener_apartamento_visible(usuario, edificio, apartamento_id: int):
    try:
        return apartamentos_visibles(usuario, edificio).get(pk=apartamento_id)
    except Apartamento.DoesNotExist as exc:
        raise Http404("Apartamento no encontrado.") from exc


def obtener_apartamento_estado_cuenta(usuario, edificio, apartamento_id: int):
    try:
        return apartamentos_con_estado_cuenta(usuario, edificio).get(
            pk=apartamento_id
        )
    except Apartamento.DoesNotExist as exc:
        raise Http404("Apartamento no encontrado.") from exc


def _tiene_rol(usuario, edificio, roles) -> bool:
    if usuario.is_superuser:
        return True
    return membresias_activas(usuario).filter(
        edificio=edificio,
        rol__in=roles,
    ).exists()


def puede_gestionar_usuarios(usuario, edificio) -> bool:
    return _tiene_rol(
        usuario,
        edificio,
        {UsuarioEdificio.Rol.ADMINISTRADOR},
    )


def puede_gestionar_apartamentos(usuario, edificio) -> bool:
    """Solo la administración del edificio puede cambiar sus unidades."""
    return puede_gestionar_usuarios(usuario, edificio)


def puede_registrar_finanzas(usuario, edificio) -> bool:
    return _tiene_rol(usuario, edificio, ROLES_QUE_REGISTRAN_FINANZAS)


def puede_ver_reportes_financieros(usuario, edificio) -> bool:
    return _tiene_rol(
        usuario,
        edificio,
        ROLES_QUE_VEN_TODOS_LOS_APARTAMENTOS,
    )
