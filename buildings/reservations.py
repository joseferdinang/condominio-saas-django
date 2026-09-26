from datetime import datetime, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from core.audit import auditar_con_usuario
from django.utils import timezone

from accounts.services import obtener_edificio_visible, puede_gestionar_usuarios

from .models import ReservaZona, ZonaComun


def _fin_del_bloque(zona, fecha, hora_inicio):
    inicio = datetime.combine(fecha, hora_inicio)
    return (inicio + timedelta(minutes=zona.duracion_bloque_minutos)).time()


def horarios_disponibles(zona, fecha):
    """Devuelve los bloques libres dentro del horario configurado para la zona."""
    inicio = datetime.combine(fecha, zona.hora_apertura)
    cierre = datetime.combine(fecha, zona.hora_cierre)
    duracion = timedelta(minutes=zona.duracion_bloque_minutos)
    ocupadas = list(
        ReservaZona.objects.filter(
            zona=zona,
            fecha=fecha,
            estado=ReservaZona.Estado.CONFIRMADA,
        ).values_list("hora_inicio", "hora_fin")
    )
    ahora = timezone.localtime()
    resultado = []
    actual = inicio
    while actual + duracion <= cierre:
        fin = actual + duracion
        es_pasado = fecha == ahora.date() and actual.time() <= ahora.time()
        se_solapa = any(
            actual.time() < hora_fin and fin.time() > hora_inicio
            for hora_inicio, hora_fin in ocupadas
        )
        if not es_pasado and not se_solapa:
            resultado.append((actual.time(), fin.time()))
        actual = fin
    return resultado


@auditar_con_usuario
def crear_reservacion(*, zona, usuario, fecha, hora_inicio, detalle_privado=""):
    obtener_edificio_visible(usuario, zona.edificio_id)
    with transaction.atomic():
        zona = ZonaComun.objects.select_for_update().get(pk=zona.pk)
        if not zona.activo:
            raise ValidationError("Esta zona no está disponible para reservaciones.")
        if fecha < timezone.localdate():
            raise ValidationError("No puedes reservar una fecha pasada.")

        apertura = datetime.combine(fecha, zona.hora_apertura)
        inicio = datetime.combine(fecha, hora_inicio)
        cierre = datetime.combine(fecha, zona.hora_cierre)
        duracion = timedelta(minutes=zona.duracion_bloque_minutos)
        fin = inicio + duracion
        if inicio < apertura or fin > cierre:
            raise ValidationError("El horario está fuera de la disponibilidad de la zona.")
        minutos_desde_apertura = int((inicio - apertura).total_seconds() // 60)
        if minutos_desde_apertura % zona.duracion_bloque_minutos:
            raise ValidationError("Selecciona uno de los bloques establecidos.")

        inicio_local = timezone.make_aware(inicio, timezone.get_current_timezone())
        if inicio_local <= timezone.now():
            raise ValidationError("La hora seleccionada ya pasó.")

        if ReservaZona.objects.filter(
            zona=zona,
            fecha=fecha,
            estado=ReservaZona.Estado.CONFIRMADA,
            hora_inicio__lt=fin.time(),
            hora_fin__gt=hora_inicio,
        ).exists():
            raise ValidationError("Ese horario acaba de ser reservado. Elige otro bloque.")

        reserva = ReservaZona(
            zona=zona,
            usuario=usuario,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=fin.time(),
            detalle_privado=detalle_privado,
        )
        reserva.full_clean()
        reserva.save()
        return reserva


@auditar_con_usuario
def cancelar_reservacion(*, reserva, usuario):
    obtener_edificio_visible(usuario, reserva.zona.edificio_id)
    if reserva.usuario_id != usuario.pk and not puede_gestionar_usuarios(
        usuario, reserva.zona.edificio
    ):
        raise PermissionDenied

    with transaction.atomic():
        reserva = ReservaZona.objects.select_for_update().select_related(
            "zona__edificio"
        ).get(pk=reserva.pk)
        if reserva.estado == ReservaZona.Estado.CANCELADA:
            return reserva
        reserva.estado = ReservaZona.Estado.CANCELADA
        reserva.cancelada_en = timezone.now()
        reserva.cancelada_por = usuario
        reserva.full_clean()
        reserva.save(
            update_fields=["estado", "cancelada_en", "cancelada_por"]
        )
        return reserva
