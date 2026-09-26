from .models import PreferenciaVisual, UsuarioEdificio
from .services import (
    apartamentos_con_estado_cuenta,
    edificios_visibles,
    membresias_activas,
)


def navegacion_portal(request):
    """Datos mínimos para una navegación coherente con el rol y el edificio."""
    if not request.user.is_authenticated:
        return {}

    preferencia = (
        PreferenciaVisual.objects.filter(usuario=request.user)
        .only("tema", "paleta")
        .first()
    )

    edificios = edificios_visibles(request.user).only("id", "nombre").order_by(
        "nombre", "id"
    )
    context = {
        "nav_edificios": edificios,
        "nav_edificio": None,
        "nav_membresia": None,
        "nav_apartamento": None,
        "nav_es_residente": False,
        "nav_puede_finanzas": request.user.is_superuser,
        "nav_puede_reportes": request.user.is_superuser,
        "nav_puede_usuarios": request.user.is_superuser,
        "tema_visual": preferencia.tema if preferencia else PreferenciaVisual.Tema.CLARO,
        "paleta_visual": (
            preferencia.paleta if preferencia else PreferenciaVisual.Paleta.OCEANO
        ),
    }

    match = getattr(request, "resolver_match", None)
    edificio_id = match.kwargs.get("edificio_id") if match else None
    if not edificio_id:
        return context

    edificio = edificios.filter(pk=edificio_id).first()
    if edificio is None:
        return context
    context["nav_edificio"] = edificio

    if request.user.is_superuser:
        return context

    membresia = membresias_activas(request.user).filter(edificio=edificio).first()
    if membresia is None:
        return context

    es_residente = membresia.rol == UsuarioEdificio.Rol.RESIDENTE
    context.update(
        {
            "nav_membresia": membresia,
            "nav_es_residente": es_residente,
            "nav_puede_finanzas": membresia.rol
            in {
                UsuarioEdificio.Rol.ADMINISTRADOR,
                UsuarioEdificio.Rol.TESORERO,
            },
            "nav_puede_reportes": membresia.rol
            in {
                UsuarioEdificio.Rol.ADMINISTRADOR,
                UsuarioEdificio.Rol.TESORERO,
                UsuarioEdificio.Rol.JUNTA,
            },
            "nav_puede_usuarios": membresia.rol
            == UsuarioEdificio.Rol.ADMINISTRADOR,
        }
    )
    if es_residente:
        context["nav_apartamento"] = (
            apartamentos_con_estado_cuenta(request.user, edificio)
            .only("id", "numero", "edificio_id")
            .order_by("numero", "id")
            .first()
        )
    return context
