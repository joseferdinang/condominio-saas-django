from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.utils import timezone

from accounts.services import (
    apartamentos_con_estado_cuenta,
    puede_ver_reportes_financieros,
)
from buildings.models import Apartamento, Edificio

from .models import AplicacionPago, Cargo, Gasto, Pago, PeriodoCuota, SaldoInicial
from .services import calcular_conciliacion


ZERO = Decimal("0.00")

TIPOS_REPORTE = (
    ("estado_cuenta", "Estado de cuenta por apartamento"),
    ("cuentas_cobrar", "Cuentas por cobrar"),
    ("cuotas_periodo", "Cuotas cobradas y pendientes por período"),
    ("gastos_categoria", "Gastos por categoría"),
    ("resumen_mensual", "Resumen financiero mensual"),
    ("movimientos_caja", "Movimientos de caja"),
    ("pagos_pendientes", "Pagos pendientes de revisión"),
)
TITULOS_REPORTE = dict(TIPOS_REPORTE)


@dataclass(frozen=True)
class ColumnaReporte:
    titulo: str
    tipo: str = "texto"
    ancho: int = 18


@dataclass(frozen=True)
class SeccionReporte:
    titulo: str
    columnas: tuple[ColumnaReporte, ...]
    filas: tuple[tuple, ...]


@dataclass(frozen=True)
class TotalReporte:
    etiqueta: str
    valor: object
    tipo: str = "moneda"


@dataclass(frozen=True)
class ReporteFinanciero:
    codigo: str
    titulo: str
    edificio: Edificio
    periodo_consultado: str
    generado_en: datetime
    secciones: tuple[SeccionReporte, ...]
    totales: tuple[TotalReporte, ...]


def _sumar(queryset, campo):
    return queryset.aggregate(total=Sum(campo))["total"] or ZERO


def _etiqueta_periodo(periodo=None, fecha_desde=None, fecha_hasta=None):
    if periodo:
        return f"{periodo.mes:02d}/{periodo.anio}"
    if fecha_desde and fecha_hasta:
        if fecha_desde.year == fecha_hasta.year and fecha_desde.month == fecha_hasta.month:
            return f"{fecha_desde.month:02d}/{fecha_desde.year}"
        return f"{fecha_desde:%d/%m/%Y} al {fecha_hasta:%d/%m/%Y}"
    return "Todos los períodos"


def limites_mes(valor: date):
    inicio = valor.replace(day=1)
    siguiente = (
        inicio.replace(year=inicio.year + 1, month=1)
        if inicio.month == 12
        else inicio.replace(month=inicio.month + 1)
    )
    return inicio, siguiente - timedelta(days=1)


def _validar_acceso_general(usuario, edificio, tipo):
    if tipo == "estado_cuenta":
        return
    if not puede_ver_reportes_financieros(usuario, edificio):
        raise PermissionDenied


def _estado_cuenta(*, edificio, usuario, apartamento, periodo):
    if apartamento is None:
        raise ValidationError("Selecciona el apartamento del estado de cuenta.")
    try:
        apartamento = apartamentos_con_estado_cuenta(usuario, edificio).get(
            pk=apartamento.pk
        )
    except Apartamento.DoesNotExist as exc:
        raise PermissionDenied from exc
    cargos = Cargo.objects.filter(apartamento=apartamento).exclude(
        estado=Cargo.Estado.ANULADO
    )
    if periodo:
        cargos = cargos.filter(periodo=periodo)
        saldo_inicial = ZERO
    else:
        apertura = SaldoInicial.objects.filter(
            apartamento=apartamento,
            estado=SaldoInicial.Estado.CONFIRMADO,
        ).first()
        saldo_inicial = apertura.importe if apertura else ZERO

    cargos = cargos.select_related("periodo")
    total_cargos = _sumar(cargos, "importe")
    aplicaciones = AplicacionPago.objects.filter(
        cargo__in=cargos,
        pago__estado=Pago.Estado.CONFIRMADO,
    )
    total_pagos = _sumar(aplicaciones, "importe_aplicado")
    filas_cargos = tuple(
        (
            f"{cargo.periodo.mes:02d}/{cargo.periodo.anio}",
            cargo.fecha_vencimiento,
            cargo.concepto,
            cargo.importe,
            cargo.total_aplicado,
            cargo.saldo_pendiente,
            cargo.get_estado_display(),
        )
        for cargo in cargos
    )
    pagos = Pago.objects.filter(apartamento=apartamento).order_by("fecha", "pk")
    if periodo:
        pagos = pagos.filter(fecha__year=periodo.anio, fecha__month=periodo.mes)
    filas_pagos = tuple(
        (
            pago.fecha,
            pago.get_metodo_display(),
            pago.referencia or "-",
            pago.importe_total,
            pago.get_estado_display(),
        )
        for pago in pagos
    )
    saldo = saldo_inicial + total_cargos - total_pagos
    return (
        (
            SeccionReporte(
                titulo=f"Apartamento {apartamento.numero} - cargos",
                columnas=(
                    ColumnaReporte("Período", ancho=12),
                    ColumnaReporte("Vencimiento", "fecha", 15),
                    ColumnaReporte("Concepto", ancho=32),
                    ColumnaReporte("Cargo", "moneda", 16),
                    ColumnaReporte("Aplicado", "moneda", 16),
                    ColumnaReporte("Pendiente", "moneda", 16),
                    ColumnaReporte("Estado", ancho=14),
                ),
                filas=filas_cargos,
            ),
            SeccionReporte(
                titulo="Pagos registrados",
                columnas=(
                    ColumnaReporte("Fecha", "fecha", 15),
                    ColumnaReporte("Método", ancho=18),
                    ColumnaReporte("Referencia", ancho=24),
                    ColumnaReporte("Importe", "moneda", 16),
                    ColumnaReporte("Estado", ancho=14),
                ),
                filas=filas_pagos,
            ),
        ),
        (
            TotalReporte("Saldo inicial", saldo_inicial),
            TotalReporte("Cargos", total_cargos),
            TotalReporte("Pagos aplicados", total_pagos),
            TotalReporte("Saldo pendiente conciliado", saldo),
        ),
    )


def _cuentas_por_cobrar(*, edificio, usuario, periodo):
    filas = []
    total_inicial = total_cargos = total_pagos = total_pendiente = ZERO
    for apartamento in apartamentos_con_estado_cuenta(usuario, edificio).order_by("numero"):
        cargos = Cargo.objects.filter(apartamento=apartamento).exclude(
            estado=Cargo.Estado.ANULADO
        )
        if periodo:
            cargos = cargos.filter(periodo=periodo)
            inicial = ZERO
        else:
            apertura = SaldoInicial.objects.filter(
                apartamento=apartamento,
                estado=SaldoInicial.Estado.CONFIRMADO,
            ).first()
            inicial = apertura.importe if apertura else ZERO
        cargos_total = _sumar(cargos, "importe")
        pagos_total = _sumar(
            AplicacionPago.objects.filter(
                cargo__in=cargos,
                pago__estado=Pago.Estado.CONFIRMADO,
            ),
            "importe_aplicado",
        )
        pendiente = inicial + cargos_total - pagos_total
        if pendiente <= ZERO:
            continue
        filas.append((apartamento.numero, inicial, cargos_total, pagos_total, pendiente))
        total_inicial += inicial
        total_cargos += cargos_total
        total_pagos += pagos_total
        total_pendiente += pendiente
    return (
        (
            SeccionReporte(
                titulo="Apartamentos con saldo pendiente",
                columnas=(
                    ColumnaReporte("Apartamento", ancho=15),
                    ColumnaReporte("Saldo inicial", "moneda", 17),
                    ColumnaReporte("Cargos", "moneda", 17),
                    ColumnaReporte("Pagos", "moneda", 17),
                    ColumnaReporte("Pendiente", "moneda", 17),
                ),
                filas=tuple(filas),
            ),
        ),
        (
            TotalReporte("Saldo inicial", total_inicial),
            TotalReporte("Cargos", total_cargos),
            TotalReporte("Pagos aplicados", total_pagos),
            TotalReporte("Cuentas por cobrar conciliadas", total_pendiente),
        ),
    )


def _cuotas_periodo(*, edificio, periodo):
    if periodo is None:
        raise ValidationError("Selecciona el período de cuotas.")
    cargos = Cargo.objects.filter(
        periodo=periodo,
        apartamento__edificio=edificio,
        tipo=Cargo.Tipo.CUOTA_MENSUAL,
    ).exclude(estado=Cargo.Estado.ANULADO).select_related("apartamento")
    filas = tuple(
        (
            cargo.apartamento.numero,
            cargo.importe,
            cargo.total_aplicado,
            cargo.saldo_pendiente,
            cargo.get_estado_display(),
        )
        for cargo in cargos
    )
    cobrado = _sumar(
        AplicacionPago.objects.filter(
            cargo__in=cargos,
            pago__estado=Pago.Estado.CONFIRMADO,
        ),
        "importe_aplicado",
    )
    facturado = _sumar(cargos, "importe")
    return (
        (
            SeccionReporte(
                titulo="Cuotas del período",
                columnas=(
                    ColumnaReporte("Apartamento", ancho=15),
                    ColumnaReporte("Cuota", "moneda", 17),
                    ColumnaReporte("Cobrado", "moneda", 17),
                    ColumnaReporte("Pendiente", "moneda", 17),
                    ColumnaReporte("Estado", ancho=14),
                ),
                filas=filas,
            ),
        ),
        (
            TotalReporte("Cuotas facturadas", facturado),
            TotalReporte("Cuotas cobradas", cobrado),
            TotalReporte("Cuotas pendientes conciliadas", facturado - cobrado),
        ),
    )


def _gastos_categoria(*, edificio, fecha_desde, fecha_hasta):
    gastos = Gasto.objects.filter(
        edificio=edificio,
        estado=Gasto.Estado.CONFIRMADO,
        fecha__range=(fecha_desde, fecha_hasta),
    )
    agregados = gastos.values("categoria").annotate(
        cantidad=Count("id"), total=Sum("importe")
    ).order_by("categoria")
    etiquetas = dict(Gasto.Categoria.choices)
    filas = tuple(
        (etiquetas[item["categoria"]], item["cantidad"], item["total"] or ZERO)
        for item in agregados
    )
    total = _sumar(gastos, "importe")
    return (
        (
            SeccionReporte(
                titulo="Gastos confirmados por categoría",
                columnas=(
                    ColumnaReporte("Categoría", ancho=28),
                    ColumnaReporte("Cantidad", "entero", 12),
                    ColumnaReporte("Importe", "moneda", 18),
                ),
                filas=filas,
            ),
        ),
        (TotalReporte("Gastos confirmados conciliados", total),),
    )


def _resumen_mensual(*, edificio, fecha_desde, fecha_hasta):
    pagos = Pago.objects.filter(
        apartamento__edificio=edificio,
        estado=Pago.Estado.CONFIRMADO,
        fecha__range=(fecha_desde, fecha_hasta),
    )
    gastos = Gasto.objects.filter(
        edificio=edificio,
        estado=Gasto.Estado.CONFIRMADO,
        fecha__range=(fecha_desde, fecha_hasta),
    )
    cargos = Cargo.objects.filter(
        apartamento__edificio=edificio,
        periodo__anio=fecha_desde.year,
        periodo__mes=fecha_desde.month,
    ).exclude(estado=Cargo.Estado.ANULADO)
    ingresos = _sumar(pagos, "importe_total")
    egresos = _sumar(gastos, "importe")
    conciliacion_final = calcular_conciliacion(
        edificio=edificio,
        fecha_hasta=fecha_hasta,
    )
    saldo_apertura = conciliacion_final.saldo_final - ingresos + egresos
    cuotas = _sumar(cargos, "importe")
    cuotas_cobradas = _sumar(
        AplicacionPago.objects.filter(
            cargo__in=cargos,
            pago__estado=Pago.Estado.CONFIRMADO,
        ),
        "importe_aplicado",
    )
    filas = (
        ("Saldo antes de movimientos del mes", saldo_apertura),
        ("Ingresos confirmados", ingresos),
        ("Gastos confirmados", -egresos),
        ("Saldo disponible al cierre", conciliacion_final.saldo_final),
        ("Cuotas emitidas", cuotas),
        ("Cuotas cobradas", cuotas_cobradas),
        ("Cuotas pendientes", cuotas - cuotas_cobradas),
    )
    return (
        (
            SeccionReporte(
                titulo="Resumen conciliado",
                columnas=(
                    ColumnaReporte("Concepto", ancho=38),
                    ColumnaReporte("Importe", "moneda", 20),
                ),
                filas=filas,
            ),
        ),
        (
            TotalReporte("Saldo de apertura", saldo_apertura),
            TotalReporte("Ingresos", ingresos),
            TotalReporte("Gastos", egresos),
            TotalReporte("Saldo final conciliado", conciliacion_final.saldo_final),
        ),
    )


def _movimientos_caja(*, edificio, fecha_desde, fecha_hasta):
    apertura = SaldoInicial.objects.filter(
        edificio=edificio,
        apartamento__isnull=True,
        estado=SaldoInicial.Estado.CONFIRMADO,
        fecha_corte__lte=fecha_hasta,
    ).order_by("-fecha_corte", "-pk").first()
    filas_base = []
    if apertura and apertura.fecha_corte >= fecha_desde:
        saldo_apertura = ZERO
        filas_base.append(
            (apertura.fecha_corte, "Saldo inicial", apertura.concepto, apertura.importe)
        )
        inicio_movimientos = apertura.fecha_corte + timedelta(days=1)
    else:
        saldo_apertura = calcular_conciliacion(
            edificio=edificio,
            fecha_hasta=fecha_desde - timedelta(days=1),
        ).saldo_final
        inicio_movimientos = fecha_desde
        if apertura:
            inicio_movimientos = max(
                inicio_movimientos,
                apertura.fecha_corte + timedelta(days=1),
            )

    pagos = Pago.objects.filter(
        apartamento__edificio=edificio,
        estado=Pago.Estado.CONFIRMADO,
        fecha__range=(inicio_movimientos, fecha_hasta),
    ).select_related("apartamento")
    gastos = Gasto.objects.filter(
        edificio=edificio,
        estado=Gasto.Estado.CONFIRMADO,
        fecha__range=(inicio_movimientos, fecha_hasta),
    )
    movimientos = filas_base + [
        (pago.fecha, "Ingreso", f"Pago apartamento {pago.apartamento.numero}", pago.importe_total)
        for pago in pagos
    ] + [
        (gasto.fecha, "Gasto", gasto.concepto, -gasto.importe)
        for gasto in gastos
    ]
    movimientos.sort(key=lambda item: (item[0], item[1], item[2]))
    saldo = saldo_apertura
    filas = []
    for fecha, tipo, concepto, importe in movimientos:
        saldo += importe
        filas.append((fecha, tipo, concepto, importe, saldo))
    ingresos = _sumar(pagos, "importe_total")
    egresos = _sumar(gastos, "importe")
    return (
        (
            SeccionReporte(
                titulo="Libro de caja",
                columnas=(
                    ColumnaReporte("Fecha", "fecha", 15),
                    ColumnaReporte("Tipo", ancho=14),
                    ColumnaReporte("Concepto", ancho=38),
                    ColumnaReporte("Movimiento", "moneda", 18),
                    ColumnaReporte("Saldo", "moneda", 18),
                ),
                filas=tuple(filas),
            ),
        ),
        (
            TotalReporte("Saldo de apertura", saldo_apertura),
            TotalReporte("Ingresos", ingresos),
            TotalReporte("Gastos", egresos),
            TotalReporte("Saldo final conciliado", saldo),
        ),
    )


def _pagos_pendientes(*, edificio, fecha_desde, fecha_hasta):
    pagos = Pago.objects.filter(
        apartamento__edificio=edificio,
        estado=Pago.Estado.PENDIENTE,
        fecha__range=(fecha_desde, fecha_hasta),
    ).select_related("apartamento", "registrado_por")
    filas = tuple(
        (
            pago.fecha,
            pago.apartamento.numero,
            pago.get_metodo_display(),
            pago.referencia or "-",
            pago.importe_total,
            pago.registrado_por.get_full_name() or pago.registrado_por.get_username(),
        )
        for pago in pagos
    )
    total = _sumar(pagos, "importe_total")
    return (
        (
            SeccionReporte(
                titulo="Comprobantes pendientes de revisión",
                columnas=(
                    ColumnaReporte("Fecha", "fecha", 15),
                    ColumnaReporte("Apartamento", ancho=15),
                    ColumnaReporte("Método", ancho=17),
                    ColumnaReporte("Referencia", ancho=22),
                    ColumnaReporte("Importe", "moneda", 18),
                    ColumnaReporte("Registrado por", ancho=24),
                ),
                filas=filas,
            ),
        ),
        (
            TotalReporte("Pagos pendientes", len(filas), "entero"),
            TotalReporte("Importe pendiente de revisión", total),
        ),
    )


def generar_reporte(
    *,
    tipo,
    edificio,
    usuario,
    apartamento=None,
    periodo=None,
    fecha_desde=None,
    fecha_hasta=None,
):
    if tipo not in TITULOS_REPORTE:
        raise ValidationError("Tipo de reporte no válido.")
    _validar_acceso_general(usuario, edificio, tipo)
    if periodo and periodo.edificio_id != edificio.pk:
        raise PermissionDenied
    if apartamento and apartamento.edificio_id != edificio.pk:
        raise PermissionDenied

    hoy = timezone.localdate()
    fecha_desde = fecha_desde or hoy.replace(day=1)
    fecha_hasta = fecha_hasta or limites_mes(fecha_desde)[1]
    if fecha_desde > fecha_hasta:
        raise ValidationError("La fecha inicial no puede superar la fecha final.")

    if tipo == "estado_cuenta":
        secciones, totales = _estado_cuenta(
            edificio=edificio,
            usuario=usuario,
            apartamento=apartamento,
            periodo=periodo,
        )
    elif tipo == "cuentas_cobrar":
        secciones, totales = _cuentas_por_cobrar(
            edificio=edificio,
            usuario=usuario,
            periodo=periodo,
        )
    elif tipo == "cuotas_periodo":
        secciones, totales = _cuotas_periodo(
            edificio=edificio,
            periodo=periodo,
        )
    elif tipo == "gastos_categoria":
        secciones, totales = _gastos_categoria(
            edificio=edificio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    elif tipo == "resumen_mensual":
        fecha_desde, fecha_hasta = limites_mes(fecha_desde)
        secciones, totales = _resumen_mensual(
            edificio=edificio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    elif tipo == "movimientos_caja":
        secciones, totales = _movimientos_caja(
            edificio=edificio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    else:
        secciones, totales = _pagos_pendientes(
            edificio=edificio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

    tipos_por_periodo = {"estado_cuenta", "cuentas_cobrar", "cuotas_periodo"}
    periodo_etiqueta = periodo if tipo in tipos_por_periodo else None
    etiqueta = _etiqueta_periodo(
        periodo=periodo_etiqueta,
        fecha_desde=None if periodo_etiqueta else fecha_desde,
        fecha_hasta=None if periodo_etiqueta else fecha_hasta,
    )
    return ReporteFinanciero(
        codigo=tipo,
        titulo=TITULOS_REPORTE[tipo],
        edificio=edificio,
        periodo_consultado=etiqueta,
        generado_en=timezone.localtime(),
        secciones=secciones,
        totales=totales,
    )
