from datetime import date

from django import forms

from django.utils import timezone

from .models import Apartamento, Aviso, ZonaComun
from .reservations import horarios_disponibles


class ApartamentoForm(forms.ModelForm):
    def __init__(self, *args, edificio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.edificio = edificio or getattr(self.instance, "edificio", None)

    class Meta:
        model = Apartamento
        fields = (
            "numero",
            "cuota_mensual",
            "porcentaje_contribucion",
            "peso_voto",
            "activo",
        )
        labels = {
            "numero": "Número o código",
            "cuota_mensual": "Cuota mensual",
            "porcentaje_contribucion": "Contribución a gastos (%)",
            "peso_voto": "Peso de voto",
            "activo": "Apartamento activo",
        }
        help_texts = {
            "numero": "Debe ser único dentro de este edificio.",
            "cuota_mensual": "Importe en pesos dominicanos.",
            "porcentaje_contribucion": "Se usa para distribuir gastos comunes.",
            "peso_voto": "Se mantiene separado de la contribución a gastos.",
            "activo": "Desactívalo para retirarlo del portal sin borrar su historial.",
        }
        widgets = {
            "numero": forms.TextInput(
                attrs={
                    "placeholder": "Ej. A-101",
                    "autocomplete": "off",
                }
            ),
            "cuota_mensual": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}
            ),
            "porcentaje_contribucion": forms.NumberInput(
                attrs={"step": "0.0001", "min": "0", "max": "100", "inputmode": "decimal"}
            ),
            "peso_voto": forms.NumberInput(
                attrs={"step": "0.0001", "min": "0", "inputmode": "decimal"}
            ),
            "activo": forms.CheckboxInput(),
        }

    def clean_numero(self):
        numero = self.cleaned_data["numero"].strip().upper()
        if self.edificio and Apartamento.objects.filter(
            edificio=self.edificio,
            numero__iexact=numero,
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                "Ya existe un apartamento con ese número en este edificio."
            )
        return numero


class AvisoForm(forms.ModelForm):
    class Meta:
        model = Aviso
        fields = ("titulo", "contenido", "fecha", "fijado", "estado")
        widgets = {
            "contenido": forms.Textarea(attrs={"rows": 6}),
            "fecha": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class ZonaComunForm(forms.ModelForm):
    class Meta:
        model = ZonaComun
        fields = (
            "nombre",
            "ubicacion",
            "descripcion",
            "hora_apertura",
            "hora_cierre",
            "duracion_bloque_minutos",
            "activo",
        )
        labels = {
            "nombre": "Nombre de la zona",
            "ubicacion": "Ubicación",
            "descripcion": "Descripción",
            "hora_apertura": "Hora de apertura",
            "hora_cierre": "Hora de cierre",
            "duracion_bloque_minutos": "Duración de cada reserva",
            "activo": "Disponible para reservaciones",
        }
        help_texts = {
            "duracion_bloque_minutos": "Entre 30 minutos y 4 horas.",
            "activo": "Desactívala para impedir nuevas reservas sin borrar el historial.",
        }
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "hora_apertura": forms.TimeInput(attrs={"type": "time"}),
            "hora_cierre": forms.TimeInput(attrs={"type": "time"}),
            "duracion_bloque_minutos": forms.NumberInput(
                attrs={"min": 30, "max": 240, "step": 30}
            ),
            "activo": forms.CheckboxInput(),
        }

    def __init__(self, *args, edificio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.edificio = edificio or getattr(self.instance, "edificio", None)

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if self.edificio and ZonaComun.objects.filter(
            edificio=self.edificio,
            nombre__iexact=nombre,
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                "Ya existe una zona con este nombre en el edificio."
            )
        return nombre


class ReservaZonaForm(forms.Form):
    zona = forms.ModelChoiceField(
        queryset=ZonaComun.objects.none(),
        label="Zona o salón",
        empty_label=None,
    )
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    hora_inicio = forms.ChoiceField(label="Horario disponible")
    detalle_privado = forms.CharField(
        label="Detalle del evento",
        required=False,
        max_length=240,
        help_text="Opcional. Solo tú y la administración podrán verlo.",
        widget=forms.TextInput(
            attrs={"placeholder": "Ej. cumpleaños familiar", "autocomplete": "off"}
        ),
    )

    def __init__(self, *args, edificio, horarios_url="", **kwargs):
        super().__init__(*args, **kwargs)
        zonas = ZonaComun.objects.filter(edificio=edificio, activo=True)
        self.fields["zona"].queryset = zonas

        self.fields["zona"].widget.attrs.update(
            {
                "hx-get": horarios_url,
                "hx-target": "#id_hora_inicio",
                "hx-include": "#id_fecha",
            }
        )
        self.fields["fecha"].widget.attrs.update(
            {
                "min": timezone.localdate().isoformat(),
                "hx-get": horarios_url,
                "hx-target": "#id_hora_inicio",
                "hx-include": "#id_zona",
            }
        )

        zona_id = self.data.get("zona") if self.is_bound else self.initial.get("zona")
        fecha_value = self.data.get("fecha") if self.is_bound else self.initial.get("fecha")
        zona = zonas.filter(pk=zona_id).first() if zona_id else zonas.first()
        if zona and not zona_id:
            self.initial["zona"] = zona.pk

        if not fecha_value:
            fecha_value = timezone.localdate()
            self.initial["fecha"] = fecha_value
        elif isinstance(fecha_value, str):
            try:
                fecha_value = date.fromisoformat(fecha_value)
            except ValueError:
                fecha_value = None

        opciones = []
        if zona and fecha_value:
            opciones = [
                (inicio.strftime("%H:%M"), f"{inicio:%H:%M} – {fin:%H:%M}")
                for inicio, fin in horarios_disponibles(zona, fecha_value)
            ]
        self.fields["hora_inicio"].choices = opciones or [
            ("", "No hay horarios disponibles")
        ]

    def clean_fecha(self):
        fecha = self.cleaned_data["fecha"]
        if fecha < timezone.localdate():
            raise forms.ValidationError("Selecciona una fecha de hoy en adelante.")
        return fecha

    def clean_detalle_privado(self):
        return self.cleaned_data["detalle_privado"].strip()
