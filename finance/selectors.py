from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from accounts.models import UsuarioEdificio
from accounts.services import (
    apartamentos_visibles,
    obtener_membresia,
    puede_gestionar_apartamentos,
    puede_registrar_finanzas,
)
from buildings.models import Apartamento, Aviso, Edificio

from .models import Cargo, Gasto, Pago, PeriodoCuota
from .services import calcular_conciliacion, calcular_saldo_apartamento


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ApartamentoResumen:
    apartamento: object
    saldo: Decimal
    estado: str


def avisos_publicados(edificio):
    return Aviso.objects.filter(
        edificio=edificio,
        estado=Aviso.Estado.PUBLICADO,
        fecha__lte=timezone.now(),
    )


def apartamentos_resumen(
    *,
    usuario,
    edificio,
    periodo=None,
    busqueda="",
    estado="",
    incluir_inactivos=False,
):
    apartamentos = apartamentos_visibles(usuario, edificio)
    if incluir_inactivos and puede_gestionar_apartamentos(usuario, edificio):
        apartamentos = Apartamento.objects.filter(edificio=edificio)
    if busqueda:
        apartamentos = apartamentos.filter(numero__icontains=busqueda.strip())

    filas = []
    for apartamento in apartamentos.order_by("numero"):
        if periodo:
            cargos = Cargo.objects.filter(
                apartamento=apartamento,
                periodo=periodo,
            ).exclude(estado=Cargo.Estado.ANULADO)
            saldo = sum((cargo.saldo_pendiente for cargo in cargos), ZERO)
        else:
            saldo = calcular_saldo_apartamento(apartamento)
        estado_actual = "AL_DIA" if saldo <= ZERO else "PENDIENTE"
        if estado and estado != estado_actual:
            continue
        filas.append(
            ApartamentoResumen(
                apartamento=apartamento,
                saldo=saldo,
                estado=estado_actual,
            )
        )
    return filas


def contexto_resumen_edificio(*, usuario, edificio: Edificio):
    puede_gestionar = puede_registrar_finanzas(usuario, edificio)
    membresia = None if usuario.is_superuser else obtener_membresia(usuario, edificio)
    es_residente = bool(
        membresia and membresia.rol == UsuarioEdificio.Rol.RESIDENTE
    )
    periodos = PeriodoCuota.objects.filter(edificio=edificio)
    periodo_actual = periodos.first()
    apartamentos = apartamentos_resumen(usuario=usuario, edificio=edificio)
    al_dia = sum(1 for fila in apartamentos if fila.estado == "AL_DIA")
    pendientes = len(apartamentos) - al_dia

    contexto = {
        "periodos": periodos,
        "periodo_actual": periodo_actual,
        "apartamentos_resumen": apartamentos,
        "apartamentos_al_dia": al_dia,
        "apartamentos_pendientes": pendientes,
        "porcentaje_al_dia": round((al_dia / len(apartamentos)) * 100)
        if apartamentos
        else 0,
        "avisos": avisos_publicados(edificio)[:5],
        "puede_gestionar_finanzas": puede_gestionar,
        "es_residente": es_residente,
        "rol_actual": membresia.get_rol_display() if membresia else "Superusuario",
        "conciliacion": None,
    }
    if not puede_gestionar and not usuario.is_superuser:
        if es_residente and apartamentos:
            apartamento = apartamentos[0].apartamento
            contexto.update(
                {
                    "residente_apartamento": apartamento,
                    "residente_saldo": apartamentos[0].saldo,
                    "residente_proximo_cargo": (
                        Cargo.objects.filter(
                            apartamento=apartamento,
                            estado__in=[
                                Cargo.Estado.PENDIENTE,
                                Cargo.Estado.PARCIAL,
                            ],
                        )
                        .select_related("periodo")
                        .order_by("fecha_vencimiento", "pk")
                        .first()
                    ),
                    "residente_ultimo_pago": Pago.objects.filter(
                        apartamento=apartamento
                    ).order_by("-fecha", "-pk").first(),
                }
            )
        return contexto

    hoy = timezone.localdate()
    cargos_periodo = (
        Cargo.objects.filter(periodo=periodo_actual)
        if periodo_actual
        else Cargo.objects.none()
    )
    pagos_pendientes = Pago.objects.filter(
        apartamento__edificio=edificio,
        estado=Pago.Estado.PENDIENTE,
    ).select_related("apartamento")
    gastos_mes = Gasto.objects.filter(
        edificio=edificio,
        fecha__year=hoy.year,
        fecha__month=hoy.month,
    )
    gastos_confirmados = gastos_mes.filter(estado=Gasto.Estado.CONFIRMADO)
    pagos_recientes = list(
        Pago.objects.filter(apartamento__edificio=edificio)
        .select_related("apartamento")
        .order_by("-fecha_creacion")[:6]
    )
    gastos_recientes = list(gastos_mes.order_by("-fecha_creacion")[:6])
    movimientos = sorted(
        [
            {
                "tipo": "Pago",
                "concepto": f"Apartamento {pago.apartamento.numero}",
                "importe": pago.importe_total,
                "estado": pago.get_estado_display(),
                "fecha": pago.fecha_creacion,
            }
            for pago in pagos_recientes
        ]
        + [
            {
                "tipo": "Gasto",
                "concepto": gasto.concepto,
                "importe": -gasto.importe,
                "estado": gasto.get_estado_display(),
                "fecha": gasto.fecha_creacion,
            }
            for gasto in gastos_recientes
        ],
        key=lambda item: item["fecha"],
        reverse=True,
    )[:8]
    contexto.update(
        {
            "cuotas_periodo_total": cargos_periodo.aggregate(
                total=Sum("importe")
            )["total"]
            or ZERO,
            "cuotas_periodo_cantidad": cargos_periodo.count(),
            "pagos_pendientes": pagos_pendientes[:6],
            "pagos_pendientes_cantidad": pagos_pendientes.count(),
            "gastos_mes": gastos_mes[:6],
            "gastos_mes_total": gastos_confirmados.aggregate(
                total=Sum("importe")
            )["total"]
            or ZERO,
            "conciliacion": calcular_conciliacion(edificio=edificio),
            "movimientos_recientes": movimientos,
        }
    )
    return contexto
