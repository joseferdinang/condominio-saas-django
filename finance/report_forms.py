from django import forms
from django.utils import timezone

from accounts.services import apartamentos_con_estado_cuenta, puede_ver_reportes_financieros
from buildings.models import Apartamento
from core.templatetags.formatting import MESES

from .models import PeriodoCuota
from .reporting import TIPOS_REPORTE, limites_mes


class ReporteFiltroForm(forms.Form):
    tipo = forms.ChoiceField(label="Reporte", choices=TIPOS_REPORTE)
    formato = forms.ChoiceField(
        label="Formato",
        choices=(("xlsx", "Excel"), ("pdf", "PDF")),
    )
    apartamento = forms.ModelChoiceField(
        label="Apartamento",
        queryset=Apartamento.objects.none(),
        required=False,
        empty_label="Selecciona un apartamento",
    )
    periodo = forms.ModelChoiceField(
        label="Período de cuota",
        queryset=PeriodoCuota.objects.none(),
        required=False,
        empty_label="Todos los períodos",
    )
    fecha_desde = forms.DateField(
        label="Desde",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fecha_hasta = forms.DateField(
        label="Hasta",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, usuario, edificio, **kwargs):
        super().__init__(*args, **kwargs)
        apartamentos = apartamentos_con_estado_cuenta(usuario, edificio).order_by("numero")
        self.fields["apartamento"].queryset = apartamentos
        self.fields["periodo"].queryset = PeriodoCuota.objects.filter(edificio=edificio)
        self.fields["periodo"].label_from_instance = lambda periodo: (
            f"{MESES[periodo.mes]} {periodo.anio}"
        )
        self.fields["apartamento"].widget.attrs.update({"class": "report-select"})
        self.fields["periodo"].widget.attrs.update({"class": "report-select"})
        self.fields["fecha_desde"].widget.attrs.update({"class": "report-date"})
        self.fields["fecha_hasta"].widget.attrs.update({"class": "report-date"})
        if not puede_ver_reportes_financieros(usuario, edificio):
            self.fields["tipo"].choices = (TIPOS_REPORTE[0],)
        hoy = timezone.localdate()
        inicio, fin = limites_mes(hoy)
        self.fields["fecha_desde"].initial = inicio
        self.fields["fecha_hasta"].initial = fin

    def clean(self):
        datos = super().clean()
        tipo = datos.get("tipo")
        if tipo == "estado_cuenta" and not datos.get("apartamento"):
            self.add_error("apartamento", "Selecciona un apartamento.")
        if tipo == "cuotas_periodo" and not datos.get("periodo"):
            self.add_error("periodo", "Selecciona el período de cuotas.")
        desde = datos.get("fecha_desde")
        hasta = datos.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            self.add_error("fecha_hasta", "Debe ser igual o posterior a la fecha inicial.")
        return datos
