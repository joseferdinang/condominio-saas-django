from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()

MESES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


@register.filter
def dop(value):
    """Presenta importes dominicanos de forma consistente."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return "RD$ 0.00"
    return f"RD$ {amount:,.2f}"


@register.filter
def mes_nombre(value):
    """Devuelve el nombre del mes en español dominicano."""
    try:
        mes = int(value)
    except (TypeError, ValueError):
        return value
    return MESES[mes] if 1 <= mes <= 12 else value


@register.filter
def periodo_nombre(periodo):
    """Presenta un PeriodoCuota como 'Septiembre 2026'."""
    if not periodo:
        return "Todos los períodos"
    return f"{mes_nombre(periodo.mes)} {periodo.anio}"


@register.filter
def periodo_valor(periodo):
    """Devuelve el valor YYYY-MM para filtros de período."""
    if not periodo:
        return ""
    return f"{periodo.anio:04d}-{periodo.mes:02d}"
