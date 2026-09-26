from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import UsuarioEdificio
from accounts.services import (
    apartamentos_con_estado_cuenta,
    obtener_membresia,
    puede_registrar_finanzas,
)
from buildings.models import Apartamento, Edificio
from core.audit import auditar_con_usuario

from .models import AplicacionPago, Cargo, Gasto, Pago, PeriodoCuota, SaldoInicial


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Conciliacion:
    saldo_inicial: Decimal
    ingresos: Decimal
    gastos: Decimal
    saldo_final: Decimal
    fecha_corte: date | None
    fecha_hasta: date


def _sum(queryset, field):
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def _require_financial_permission(usuario, edificio):
    if not puede_registrar_finanzas(usuario, edificio):
        raise PermissionDenied(
            "El usuario no tiene permisos financieros para este edificio."
        )


@transaction.atomic
@auditar_con_usuario
def generar_cuotas_mensuales(
    *,
    edificio: Edificio,
    anio: int,
    mes: int,
    fecha_vencimiento: date,
    usuario,
):
    _require_financial_permission(usuario, edificio)
    edificio = Edificio.objects.select_for_update().get(pk=edificio.pk)
    periodo, periodo_creado = PeriodoCuota.objects.get_or_create(
        edificio=edificio,
        anio=anio,
        mes=mes,
        defaults={
            "fecha_vencimiento": fecha_vencimiento,
            "creado_por": usuario,
        },
    )
    if not periodo_creado and periodo.fecha_vencimiento != fecha_vencimiento:
        raise ValidationError(
            "El período ya existe con una fecha de vencimiento diferente."
        )
    if periodo.estado != PeriodoCuota.Estado.ABIERTO:
        return periodo, 0

    creados = 0
    apartamentos = edificio.apartamentos.filter(activo=True).order_by("pk")
    for apartamento in apartamentos:
        if apartamento.cuota_mensual <= ZERO:
            continue
        existe = Cargo.objects.filter(
            apartamento=apartamento,
            periodo=periodo,
            tipo=Cargo.Tipo.CUOTA_MENSUAL,
        ).exists()
        if existe:
            continue
        cargo = Cargo(
            apartamento=apartamento,
            periodo=periodo,
            tipo=Cargo.Tipo.CUOTA_MENSUAL,
            concepto=f"Cuota mensual {mes:02d}/{anio}",
            importe=apartamento.cuota_mensual,
            fecha_vencimiento=fecha_vencimiento,
            creado_por=usuario,
        )
        cargo.full_clean()
        cargo.save()
        creados += 1
    return periodo, creados


@transaction.atomic
@auditar_con_usuario
def registrar_pago(
    *,
    apartamento: Apartamento,
    importe_total: Decimal,
    fecha: date,
    metodo: str,
    usuario,
    referencia: str = "",
    comprobante=None,
):
    _require_financial_permission(usuario, apartamento.edificio)
    pago = Pago(
        apartamento=apartamento,
        importe_total=importe_total,
        fecha=fecha,
        metodo=metodo,
        referencia=referencia,
        comprobante=comprobante,
        registrado_por=usuario,
    )
    pago.full_clean()
    pago.save()
    return pago


@transaction.atomic
@auditar_con_usuario
def registrar_pago_residente(
    *,
    apartamento: Apartamento,
    importe_total: Decimal,
    fecha: date,
    metodo: str,
    usuario,
    referencia: str = "",
    comprobante=None,
):
    membresia = obtener_membresia(usuario, apartamento.edificio)
    if membresia is None or membresia.rol != UsuarioEdificio.Rol.RESIDENTE:
        raise PermissionDenied(
            "Solo un residente puede reportar pagos por este formulario."
        )
    permitido = apartamentos_con_estado_cuenta(
        usuario, apartamento.edificio
    ).filter(pk=apartamento.pk).exists()
    if not permitido:
        raise PermissionDenied(
            "El usuario no puede registrar pagos para este apartamento."
        )
    if not comprobante:
        raise ValidationError("Debe cargar un comprobante del pago.")
    pago = Pago(
        apartamento=apartamento,
        importe_total=importe_total,
        fecha=fecha,
        metodo=metodo,
        referencia=referencia,
        comprobante=comprobante,
        registrado_por=usuario,
    )
    pago.full_clean()
    pago.save()
    return pago


@transaction.atomic
@auditar_con_usuario
def preparar_aplicacion(*, pago: Pago, cargo: Cargo, importe: Decimal, usuario):
    pago = Pago.objects.select_for_update().select_related(
        "apartamento__edificio"
    ).get(pk=pago.pk)
    _require_financial_permission(usuario, pago.apartamento.edificio)
    if pago.estado != Pago.Estado.PENDIENTE:
        raise ValidationError("Solo se pueden aplicar pagos pendientes.")
    return AplicacionPago.objects.create(
        pago=pago,
        cargo=cargo,
        importe_aplicado=importe,
    )


def _actualizar_estado_cargo(cargo):
    if cargo.estado == Cargo.Estado.ANULADO:
        return
    saldo = cargo.saldo_pendiente
    if saldo == ZERO:
        nuevo_estado = Cargo.Estado.PAGADO
    elif saldo < cargo.importe:
        nuevo_estado = Cargo.Estado.PARCIAL
    else:
        nuevo_estado = Cargo.Estado.PENDIENTE
    if cargo.estado != nuevo_estado:
        cargo.estado = nuevo_estado
        cargo.save(update_fields=["estado"])


@transaction.atomic
@auditar_con_usuario
def confirmar_pago(*, pago: Pago, usuario, aplicaciones=None):
    pago = Pago.objects.select_for_update().select_related(
        "apartamento__edificio"
    ).get(pk=pago.pk)
    _require_financial_permission(usuario, pago.apartamento.edificio)
    if pago.estado != Pago.Estado.PENDIENTE:
        raise ValidationError("El pago ya fue procesado.")

    if aplicaciones:
        cargo_ids = sorted({cargo.pk for cargo, _importe in aplicaciones})
        list(
            Cargo.objects.select_for_update()
            .filter(pk__in=cargo_ids)
            .order_by("pk")
        )
        for cargo, importe in aplicaciones:
            AplicacionPago.objects.create(
                pago=pago,
                cargo=cargo,
                importe_aplicado=importe,
            )

    aplicaciones_pago = list(pago.aplicaciones.select_related("cargo"))
    if not aplicaciones_pago:
        raise ValidationError("El pago debe aplicarse al menos a un cargo.")
    total_aplicado = sum(
        (aplicacion.importe_aplicado for aplicacion in aplicaciones_pago),
        ZERO,
    )
    if total_aplicado != pago.importe_total:
        raise ValidationError(
            "La suma de las aplicaciones debe ser igual al importe total del pago."
        )

    cargos_bloqueados = {
        cargo.pk: cargo
        for cargo in Cargo.objects.select_for_update()
        .filter(pk__in=[item.cargo_id for item in aplicaciones_pago])
        .order_by("pk")
    }
    for aplicacion in aplicaciones_pago:
        cargo = cargos_bloqueados[aplicacion.cargo_id]
        if cargo.estado == Cargo.Estado.ANULADO:
            raise ValidationError("No se puede confirmar un pago sobre un cargo anulado.")
        if cargo.apartamento_id != pago.apartamento_id:
            raise ValidationError(
                "Todas las aplicaciones deben pertenecer al apartamento del pago."
            )
        confirmado_previamente = cargo.aplicaciones.filter(
            pago__estado=Pago.Estado.CONFIRMADO
        ).exclude(pago=pago).aggregate(total=Sum("importe_aplicado"))[
            "total"
        ] or ZERO
        if confirmado_previamente + aplicacion.importe_aplicado > cargo.importe:
            raise ValidationError(
                "El importe aplicado supera el saldo pendiente del cargo."
            )

    pago.estado = Pago.Estado.CONFIRMADO
    pago.confirmado_por = usuario
    pago.fecha_confirmacion = timezone.now()
    pago.save(
        update_fields=["estado", "confirmado_por", "fecha_confirmacion"]
    )
    for cargo in cargos_bloqueados.values():
        _actualizar_estado_cargo(cargo)
    return pago


@transaction.atomic
@auditar_con_usuario
def rechazar_pago(*, pago: Pago, usuario, motivo: str):
    pago = Pago.objects.select_for_update().select_related(
        "apartamento__edificio"
    ).get(pk=pago.pk)
    _require_financial_permission(usuario, pago.apartamento.edificio)
    if pago.estado != Pago.Estado.PENDIENTE:
        raise ValidationError("Solo se puede rechazar un pago pendiente.")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debe indicar el motivo del rechazo.")
    pago.estado = Pago.Estado.RECHAZADO
    pago.rechazado_por = usuario
    pago.fecha_rechazo = timezone.now()
    pago.motivo_rechazo = motivo
    pago.save(
        update_fields=[
            "estado",
            "rechazado_por",
            "fecha_rechazo",
            "motivo_rechazo",
        ]
    )
    return pago


@transaction.atomic
@auditar_con_usuario
def anular_pago(*, pago: Pago, usuario, motivo: str):
    pago = Pago.objects.select_for_update().select_related(
        "apartamento__edificio"
    ).get(pk=pago.pk)
    _require_financial_permission(usuario, pago.apartamento.edificio)
    if pago.estado == Pago.Estado.ANULADO:
        raise ValidationError("El pago ya está anulado.")
    if pago.estado == Pago.Estado.RECHAZADO:
        raise ValidationError("Un pago rechazado no puede anularse.")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debe indicar el motivo de anulación.")

    cargo_ids = list(pago.aplicaciones.values_list("cargo_id", flat=True))
    pago.estado = Pago.Estado.ANULADO
    pago.anulado_por = usuario
    pago.fecha_anulacion = timezone.now()
    pago.motivo_anulacion = motivo
    pago.save(
        update_fields=[
            "estado",
            "anulado_por",
            "fecha_anulacion",
            "motivo_anulacion",
        ]
    )
    for cargo in Cargo.objects.select_for_update().filter(pk__in=cargo_ids):
        _actualizar_estado_cargo(cargo)
    return pago


@transaction.atomic
@auditar_con_usuario
def registrar_gasto(
    *,
    edificio: Edificio,
    categoria: str,
    concepto: str,
    importe: Decimal,
    fecha: date,
    usuario,
    proveedor: str = "",
    comprobante=None,
):
    _require_financial_permission(usuario, edificio)
    gasto = Gasto(
        edificio=edificio,
        categoria=categoria,
        concepto=concepto,
        importe=importe,
        fecha=fecha,
        proveedor=proveedor,
        comprobante=comprobante,
        creado_por=usuario,
    )
    gasto.full_clean()
    gasto.save()
    return gasto


@transaction.atomic
@auditar_con_usuario
def confirmar_gasto(*, gasto: Gasto, usuario):
    gasto = Gasto.objects.select_for_update().select_related("edificio").get(
        pk=gasto.pk
    )
    _require_financial_permission(usuario, gasto.edificio)
    if gasto.estado != Gasto.Estado.PENDIENTE:
        raise ValidationError("El gasto ya fue procesado.")
    gasto.estado = Gasto.Estado.CONFIRMADO
    gasto.confirmado_por = usuario
    gasto.fecha_confirmacion = timezone.now()
    gasto.save(
        update_fields=["estado", "confirmado_por", "fecha_confirmacion"]
    )
    return gasto


@transaction.atomic
@auditar_con_usuario
def anular_gasto(*, gasto: Gasto, usuario, motivo: str):
    gasto = Gasto.objects.select_for_update().select_related("edificio").get(
        pk=gasto.pk
    )
    _require_financial_permission(usuario, gasto.edificio)
    if gasto.estado == Gasto.Estado.ANULADO:
        raise ValidationError("El gasto ya está anulado.")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debe indicar el motivo de anulación.")
    gasto.estado = Gasto.Estado.ANULADO
    gasto.anulado_por = usuario
    gasto.fecha_anulacion = timezone.now()
    gasto.motivo_anulacion = motivo
    gasto.save(
        update_fields=[
            "estado",
            "anulado_por",
            "fecha_anulacion",
            "motivo_anulacion",
        ]
    )
    return gasto


@transaction.atomic
@auditar_con_usuario
def registrar_saldo_inicial(
    *,
    edificio: Edificio,
    importe: Decimal,
    fecha_corte: date,
    concepto: str,
    usuario,
    apartamento: Apartamento | None = None,
):
    _require_financial_permission(usuario, edificio)
    saldo = SaldoInicial(
        edificio=edificio,
        apartamento=apartamento,
        importe=importe,
        fecha_corte=fecha_corte,
        concepto=concepto,
        registrado_por=usuario,
    )
    saldo.full_clean()
    saldo.save()
    return saldo


@transaction.atomic
@auditar_con_usuario
def anular_saldo_inicial(*, saldo: SaldoInicial, usuario, motivo: str):
    saldo = SaldoInicial.objects.select_for_update().select_related(
        "edificio"
    ).get(pk=saldo.pk)
    _require_financial_permission(usuario, saldo.edificio)
    if saldo.estado == SaldoInicial.Estado.ANULADO:
        raise ValidationError("El saldo inicial ya está anulado.")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debe indicar el motivo de anulación.")
    saldo.estado = SaldoInicial.Estado.ANULADO
    saldo.anulado_por = usuario
    saldo.fecha_anulacion = timezone.now()
    saldo.motivo_anulacion = motivo
    saldo.save(
        update_fields=[
            "estado",
            "anulado_por",
            "fecha_anulacion",
            "motivo_anulacion",
        ]
    )
    return saldo


@transaction.atomic
@auditar_con_usuario
def anular_cargo(*, cargo: Cargo, usuario, motivo: str):
    cargo = Cargo.objects.select_for_update().select_related(
        "apartamento__edificio"
    ).get(pk=cargo.pk)
    _require_financial_permission(usuario, cargo.apartamento.edificio)
    if cargo.estado == Cargo.Estado.ANULADO:
        raise ValidationError("El cargo ya está anulado.")
    if cargo.aplicaciones.filter(
        pago__estado__in=[Pago.Estado.PENDIENTE, Pago.Estado.CONFIRMADO]
    ).exists():
        raise ValidationError(
            "Primero debe anular los pagos activos aplicados al cargo."
        )
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debe indicar el motivo de anulación.")
    cargo.estado = Cargo.Estado.ANULADO
    cargo.anulado_por = usuario
    cargo.fecha_anulacion = timezone.now()
    cargo.motivo_anulacion = motivo
    cargo.save(
        update_fields=[
            "estado",
            "anulado_por",
            "fecha_anulacion",
            "motivo_anulacion",
        ]
    )
    return cargo


@transaction.atomic
@auditar_con_usuario
def cerrar_periodo(*, periodo: PeriodoCuota, usuario):
    periodo = PeriodoCuota.objects.select_for_update().select_related(
        "edificio"
    ).get(pk=periodo.pk)
    _require_financial_permission(usuario, periodo.edificio)
    if periodo.estado != PeriodoCuota.Estado.ABIERTO:
        raise ValidationError("Solo se puede cerrar un período abierto.")
    periodo.estado = PeriodoCuota.Estado.CERRADO
    periodo.save(update_fields=["estado"])
    return periodo


@transaction.atomic
@auditar_con_usuario
def anular_periodo(*, periodo: PeriodoCuota, usuario, motivo: str):
    periodo = PeriodoCuota.objects.select_for_update().select_related(
        "edificio"
    ).get(pk=periodo.pk)
    _require_financial_permission(usuario, periodo.edificio)
    if periodo.estado == PeriodoCuota.Estado.ANULADO:
        raise ValidationError("El período ya está anulado.")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debe indicar el motivo de anulación.")

    cargos = list(
        Cargo.objects.select_for_update().filter(periodo=periodo).order_by("pk")
    )
    if AplicacionPago.objects.filter(
        cargo__in=cargos,
        pago__estado__in=[Pago.Estado.PENDIENTE, Pago.Estado.CONFIRMADO],
    ).exists():
        raise ValidationError(
            "Primero debe anular los pagos activos aplicados al período."
        )

    ahora = timezone.now()
    for cargo in cargos:
        cargo.estado = Cargo.Estado.ANULADO
        cargo.anulado_por = usuario
        cargo.fecha_anulacion = ahora
        cargo.motivo_anulacion = motivo
        cargo.save(update_fields=["estado", "anulado_por", "fecha_anulacion", "motivo_anulacion"])
    periodo.estado = PeriodoCuota.Estado.ANULADO
    periodo.anulado_por = usuario
    periodo.fecha_anulacion = ahora
    periodo.motivo_anulacion = motivo
    periodo.save(
        update_fields=[
            "estado",
            "anulado_por",
            "fecha_anulacion",
            "motivo_anulacion",
        ]
    )
    return periodo


def calcular_conciliacion(*, edificio: Edificio, fecha_hasta: date | None = None):
    fecha_hasta = fecha_hasta or timezone.localdate()
    apertura = (
        SaldoInicial.objects.filter(
            edificio=edificio,
            apartamento__isnull=True,
            estado=SaldoInicial.Estado.CONFIRMADO,
            fecha_corte__lte=fecha_hasta,
        )
        .order_by("-fecha_corte", "-pk")
        .first()
    )
    saldo_inicial = apertura.importe if apertura else ZERO

    pagos = Pago.objects.filter(
        apartamento__edificio=edificio,
        estado=Pago.Estado.CONFIRMADO,
        fecha__lte=fecha_hasta,
    )
    gastos = Gasto.objects.filter(
        edificio=edificio,
        estado=Gasto.Estado.CONFIRMADO,
        fecha__lte=fecha_hasta,
    )
    if apertura:
        pagos = pagos.filter(fecha__gt=apertura.fecha_corte)
        gastos = gastos.filter(fecha__gt=apertura.fecha_corte)

    ingresos = _sum(pagos, "importe_total")
    total_gastos = _sum(gastos, "importe")
    return Conciliacion(
        saldo_inicial=saldo_inicial,
        ingresos=ingresos,
        gastos=total_gastos,
        saldo_final=saldo_inicial + ingresos - total_gastos,
        fecha_corte=apertura.fecha_corte if apertura else None,
        fecha_hasta=fecha_hasta,
    )


def calcular_saldo_apartamento(apartamento: Apartamento):
    apertura = SaldoInicial.objects.filter(
        apartamento=apartamento,
        estado=SaldoInicial.Estado.CONFIRMADO,
    ).first()
    saldo_inicial = apertura.importe if apertura else ZERO
    cargos = _sum(
        Cargo.objects.filter(apartamento=apartamento).exclude(
            estado=Cargo.Estado.ANULADO
        ),
        "importe",
    )
    pagos = _sum(
        AplicacionPago.objects.filter(
            cargo__apartamento=apartamento,
            pago__estado=Pago.Estado.CONFIRMADO,
        ),
        "importe_aplicado",
    )
    return saldo_inicial + cargos - pagos
