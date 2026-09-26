from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.text import slugify

from accounts.services import obtener_edificio_visible

from .exports import exportar_excel, exportar_pdf
from .report_forms import ReporteFiltroForm
from .reporting import generar_reporte


@login_required
def reportes_index(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    form = ReporteFiltroForm(usuario=request.user, edificio=edificio)
    return render(
        request,
        "reports/index.html",
        {"edificio": edificio, "form": form},
    )


@login_required
def reporte_exportar(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    form = ReporteFiltroForm(
        request.GET,
        usuario=request.user,
        edificio=edificio,
    )
    if not form.is_valid():
        return render(
            request,
            "reports/index.html",
            {"edificio": edificio, "form": form},
            status=400,
        )
    try:
        reporte = generar_reporte(
            tipo=form.cleaned_data["tipo"],
            edificio=edificio,
            usuario=request.user,
            apartamento=form.cleaned_data.get("apartamento"),
            periodo=form.cleaned_data.get("periodo"),
            fecha_desde=form.cleaned_data.get("fecha_desde"),
            fecha_hasta=form.cleaned_data.get("fecha_hasta"),
        )
    except PermissionDenied:
        raise
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(
            request,
            "reports/index.html",
            {"edificio": edificio, "form": form},
            status=400,
        )

    base = slugify(
        f"{reporte.codigo}-{edificio.nombre}-{reporte.periodo_consultado}"
    )
    if form.cleaned_data["formato"] == "xlsx":
        contenido = exportar_excel(reporte)
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        extension = "xlsx"
    else:
        contenido = exportar_pdf(reporte)
        content_type = "application/pdf"
        extension = "pdf"
    response = HttpResponse(contenido, content_type=content_type)
    response["Content-Disposition"] = (
        f'attachment; filename="{base or reporte.codigo}.{extension}"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
