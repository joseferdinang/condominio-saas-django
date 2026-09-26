from decimal import Decimal
from pathlib import Path

from django import forms
from django.utils import timezone

from .models import Cargo, Gasto, Pago


MAX_COMPROBANTE_BYTES = 5 * 1024 * 1024
FIRMAS_COMPROBANTE = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


def validar_comprobante(archivo):
    if not archivo:
        return archivo
    if archivo.size > MAX_COMPROBANTE_BYTES:
        raise forms.ValidationError("El comprobante no puede superar 5 MB.")
    extension = Path(archivo.name).suffix.lower()
    firmas = FIRMAS_COMPROBANTE.get(extension)
    if not firmas:
        raise forms.ValidationError("Adjunta un archivo PDF, PNG o JPG.")
    cabecera = archivo.read(8)
    archivo.seek(0)
    if not any(cabecera.startswith(firma) for firma in firmas):
        raise forms.ValidationError(
            "El contenido del archivo no coincide con su extensión."
        )
    return archivo


class RegistroPagoForm(forms.Form):
    importe_total = forms.DecimalField(
        label="Importe",
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    fecha = forms.DateField(
        label="Fecha del pago",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    metodo = forms.ChoiceField(label="Método", choices=Pago.Metodo.choices)
    referencia = forms.CharField(
        label="Referencia",
        max_length=160,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ej. TRANSF-48291"}),
    )
    comprobante = forms.FileField(
        label="Comprobante",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/png,image/jpeg,application/pdf"}
        ),
    )

    def __init__(self, *args, comprobante_requerido=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comprobante"].required = comprobante_requerido
        if comprobante_requerido:
            self.fields["comprobante"].help_text = (
                "Adjunta una imagen o PDF para que la administración lo revise."
            )

    def clean_comprobante(self):
        return validar_comprobante(self.cleaned_data.get("comprobante"))


class RevisionPagoForm(forms.Form):
    def __init__(self, *args, pago, **kwargs):
        super().__init__(*args, **kwargs)
        self.pago = pago
        self.usa_aplicaciones_existentes = pago.aplicaciones.exists()
        if self.usa_aplicaciones_existentes:
            return

        cargos = (
            Cargo.objects.filter(apartamento=pago.apartamento)
            .exclude(estado=Cargo.Estado.ANULADO)
            .select_related("periodo")
        )
        for cargo in cargos:
            saldo = cargo.saldo_pendiente
            if saldo <= 0:
                continue
            self.fields[f"cargo_{cargo.pk}"] = forms.DecimalField(
                label=f"{cargo.concepto} · saldo RD${saldo:,.2f}",
                required=False,
                min_value=Decimal("0.01"),
                max_value=saldo,
                max_digits=14,
                decimal_places=2,
                widget=forms.NumberInput(
                    attrs={"step": "0.01", "inputmode": "decimal"}
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        if self.usa_aplicaciones_existentes:
            return cleaned_data
        total = sum(
            (
                value
                for name, value in cleaned_data.items()
                if name.startswith("cargo_") and value
            ),
            Decimal("0.00"),
        )
        if total != self.pago.importe_total:
            raise forms.ValidationError(
                "La distribución debe sumar exactamente "
                f"RD${self.pago.importe_total:,.2f}."
            )
        return cleaned_data

    def aplicaciones(self):
        if self.usa_aplicaciones_existentes:
            return None
        resultado = []
        for name, importe in self.cleaned_data.items():
            if name.startswith("cargo_") and importe:
                cargo_id = int(name.removeprefix("cargo_"))
                resultado.append((Cargo.objects.get(pk=cargo_id), importe))
        return resultado


class RechazoPagoForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo del rechazo",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class GastoForm(forms.Form):
    categoria = forms.ChoiceField(label="Categoría", choices=Gasto.Categoria.choices)
    concepto = forms.CharField(
        label="Concepto",
        max_length=240,
        widget=forms.TextInput(
            attrs={"placeholder": "Ej. Mantenimiento de bomba de agua"}
        ),
    )
    importe = forms.DecimalField(
        label="Importe",
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    fecha = forms.DateField(
        label="Fecha",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    proveedor = forms.CharField(
        label="Proveedor",
        max_length=180,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Nombre o razón social"}),
    )
    comprobante = forms.FileField(
        label="Comprobante",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/png,image/jpeg,application/pdf"}
        ),
    )

    def clean_comprobante(self):
        return validar_comprobante(self.cleaned_data.get("comprobante"))
