from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.services import puede_gestionar_usuarios
from core.audit import auditar_con_usuario
from people.models import Persona

from .models import Aviso, EnvioAviso


@dataclass(frozen=True)
class ResultadoEnvioAviso:
    enviados: int
    fallidos: int
    omitidos: int


def destinatarios_aviso(aviso: Aviso):
    hoy = timezone.localdate()
    return list(
        Persona.objects.filter(
            activo=True,
            relaciones_apartamento__apartamento__edificio=aviso.edificio,
            relaciones_apartamento__puede_recibir_comunicaciones=True,
            relaciones_apartamento__fecha_inicio__lte=hoy,
        )
        .filter(
            Q(relaciones_apartamento__fecha_finalizacion__isnull=True)
            | Q(relaciones_apartamento__fecha_finalizacion__gte=hoy)
        )
        .exclude(correo="")
        .values_list("correo", flat=True)
        .distinct()
    )


@transaction.atomic
@auditar_con_usuario
def publicar_aviso(*, aviso: Aviso, usuario):
    aviso = Aviso.objects.select_for_update().select_related("edificio").get(
        pk=aviso.pk
    )
    if not puede_gestionar_usuarios(usuario, aviso.edificio):
        raise PermissionDenied
    aviso.estado = Aviso.Estado.PUBLICADO
    aviso.save(update_fields=["estado"])
    return aviso


@auditar_con_usuario
def enviar_aviso_por_correo(*, aviso: Aviso, usuario, destinatarios=None):
    aviso = Aviso.objects.select_related("edificio").get(pk=aviso.pk)
    if not puede_gestionar_usuarios(usuario, aviso.edificio):
        raise PermissionDenied
    if aviso.estado != Aviso.Estado.PUBLICADO or aviso.fecha > timezone.now():
        raise ValidationError("Solo se pueden enviar avisos publicados y vigentes.")

    correos = destinatarios if destinatarios is not None else destinatarios_aviso(aviso)
    correos = sorted({correo.strip().lower() for correo in correos if correo.strip()})
    enviados = fallidos = omitidos = 0

    for correo in correos:
        with transaction.atomic():
            registro, _ = EnvioAviso.objects.get_or_create(
                aviso=aviso,
                destinatario=correo,
            )
            registro = EnvioAviso.objects.select_for_update().get(pk=registro.pk)
            if registro.estado == EnvioAviso.Estado.ENVIADO:
                omitidos += 1
                continue

            ahora = timezone.now()
            registro.estado = EnvioAviso.Estado.PENDIENTE
            registro.error = ""
            registro.fecha_ultimo_intento = ahora
            registro.numero_intentos += 1
            registro.save(
                update_fields=[
                    "estado",
                    "error",
                    "fecha_ultimo_intento",
                    "numero_intentos",
                ]
            )
            try:
                send_mail(
                    f"{aviso.edificio.nombre}: {aviso.titulo}",
                    aviso.contenido,
                    settings.DEFAULT_FROM_EMAIL,
                    [correo],
                    fail_silently=False,
                )
            except Exception as exc:  # El error se conserva para reintentos operativos.
                registro.estado = EnvioAviso.Estado.FALLIDO
                registro.error = str(exc)[:4000] or exc.__class__.__name__
                registro.fecha_envio = None
                registro.save(update_fields=["estado", "error", "fecha_envio"])
                fallidos += 1
            else:
                registro.estado = EnvioAviso.Estado.ENVIADO
                registro.error = ""
                registro.fecha_envio = ahora
                registro.save(update_fields=["estado", "error", "fecha_envio"])
                enviados += 1

    return ResultadoEnvioAviso(
        enviados=enviados,
        fallidos=fallidos,
        omitidos=omitidos,
    )
