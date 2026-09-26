from contextvars import ContextVar
from functools import wraps

from django.apps import apps
from django.db.models.signals import post_save, pre_delete

from .models import Cambio


_actor = ContextVar("audit_actor", default=None)


def set_actor(usuario):
    return _actor.set(usuario if getattr(usuario, "is_authenticated", False) else None)


def reset_actor(token):
    _actor.reset(token)


def auditar_con_usuario(funcion):
    """Atribuye cambios de servicios llamados fuera de una solicitud HTTP."""
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        token = set_actor(kwargs.get("usuario"))
        try:
            return funcion(*args, **kwargs)
        finally:
            reset_actor(token)

    return envoltura


def _edificios(instance):
    modelo = instance._meta.label_lower
    if modelo == "buildings.edificio":
        return [instance.pk] if instance.pk else []
    if modelo == "people.persona":
        return list(
            instance.relaciones_apartamento.values_list(
                "apartamento__edificio_id", flat=True
            ).distinct()
        ) if instance.pk else []
    if modelo in {"buildings.apartamento", "buildings.aviso", "buildings.zonacomun",
                  "accounts.usuarioedificio", "finance.periodocuota", "finance.gasto",
                  "finance.saldoinicial"}:
        return [instance.edificio_id]
    if modelo in {"people.relacionapartamento", "finance.cargo", "finance.pago"}:
        return [instance.apartamento.edificio_id]
    if modelo == "finance.aplicacionpago":
        return [instance.pago.apartamento.edificio_id]
    if modelo == "buildings.envioaviso":
        return [instance.aviso.edificio_id]
    if modelo == "buildings.reservazona":
        return [instance.zona.edificio_id]
    return []


def _registrar(instance, accion):
    usuario = _actor.get()
    if usuario is None and accion == Cambio.Accion.CREAR:
        for campo in ("creado_por", "registrado_por"):
            usuario = getattr(instance, campo, None)
            if usuario:
                break
    for edificio_id in set(_edificios(instance)):
        Cambio.objects.create(
            edificio_id=edificio_id,
            usuario=usuario if getattr(usuario, "pk", None) else None,
            usuario_nombre=usuario.get_username() if getattr(usuario, "pk", None) else "Sistema",
            accion=accion,
            modelo=instance._meta.label,
            objeto_id=str(instance.pk),
            descripcion=str(instance)[:255],
        )


def _guardado(sender, instance, created, **kwargs):
    _registrar(instance, Cambio.Accion.CREAR if created else Cambio.Accion.MODIFICAR)


def _eliminado(sender, instance, **kwargs):
    _registrar(instance, Cambio.Accion.ELIMINAR)


def conectar_auditoria():
    modelos = (
        "accounts.UsuarioEdificio", "buildings.Edificio", "buildings.Apartamento",
        "buildings.Aviso", "buildings.EnvioAviso", "buildings.ZonaComun",
        "buildings.ReservaZona", "people.Persona", "people.RelacionApartamento",
        "finance.PeriodoCuota", "finance.Cargo", "finance.Pago",
        "finance.AplicacionPago", "finance.Gasto", "finance.SaldoInicial",
    )
    for etiqueta in modelos:
        modelo = apps.get_model(etiqueta)
        post_save.connect(_guardado, sender=modelo, dispatch_uid=f"audit_save_{etiqueta}")
        pre_delete.connect(_eliminado, sender=modelo, dispatch_uid=f"audit_delete_{etiqueta}")
