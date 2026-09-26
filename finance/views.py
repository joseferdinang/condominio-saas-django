import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST

from accounts.services import (
    obtener_apartamento_estado_cuenta,
    obtener_edificio_visible,
    obtener_membresia,
    puede_gestionar_apartamentos,
    puede_registrar_finanzas,
    puede_ver_reportes_financieros,
)
from accounts.models import UsuarioEdificio
from buildings.forms import ApartamentoForm
from buildings.models import Apartamento

from .forms import GastoForm, RechazoPagoForm, RegistroPagoForm, RevisionPagoForm
from .models import Gasto, Pago, PeriodoCuota
from .selectors import apartamentos_resumen
from .services import (
    confirmar_gasto,
    confirmar_pago,
    rechazar_pago,
    registrar_gasto,
    registrar_pago,
    registrar_pago_residente,
)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _success_redirect(request, url):
    if _is_htmx(request):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


def _pago_del_edificio(edificio, pago_id):
    return get_object_or_404(
        Pago.objects.select_related(
            "apartamento__edificio",
            "registrado_por",
            "confirmado_por",
        ),
        pk=pago_id,
        apartamento__edificio=edificio,
    )


@login_required
def apartamentos_lista(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    puede_gestionar = puede_gestionar_apartamentos(request.user, edificio)
    incluir_inactivos = (
        request.GET.get("inactivos") == "1" and puede_gestionar
    )
    periodo = None
    periodo_id = request.GET.get("periodo", "").strip()
    if periodo_id.isdigit():
        periodo = PeriodoCuota.objects.filter(
            pk=periodo_id,
            edificio=edificio,
        ).first()
    estado = request.GET.get("estado", "").strip()
    if estado not in {"", "AL_DIA", "PENDIENTE"}:
        estado = ""
    busqueda = request.GET.get("q", "")
    context = {
        "edificio": edificio,
        "filas": apartamentos_resumen(
            usuario=request.user,
            edificio=edificio,
            periodo=periodo,
            busqueda=busqueda,
            estado=estado,
            incluir_inactivos=incluir_inactivos,
        ),
        "periodos": PeriodoCuota.objects.filter(edificio=edificio),
        "periodo_seleccionado": periodo_id,
        "estado_seleccionado": estado,
        "busqueda": busqueda,
        "puede_gestionar": puede_gestionar,
        "incluir_inactivos": incluir_inactivos,
    }
    template = (
        "finance/partials/apartamentos_table.html"
        if _is_htmx(request)
        else "finance/apartamentos_lista.html"
    )
    return render(request, template, context)


@login_required
@require_http_methods(["GET", "POST"])
def apartamento_crear(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_apartamentos(request.user, edificio):
        raise PermissionDenied

    form = ApartamentoForm(request.POST or None, edificio=edificio)
    if request.method == "POST" and form.is_valid():
        apartamento = form.save(commit=False)
        apartamento.edificio = edificio
        try:
            apartamento.full_clean()
            apartamento.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f"El apartamento {apartamento.numero} fue agregado.",
            )
            return redirect(
                "finance:apartamentos_lista", edificio_id=edificio.pk
            )

    return render(
        request,
        "finance/apartamento_form_page.html",
        {
            "edificio": edificio,
            "form": form,
            "apartamento": None,
            "modo": "crear",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def apartamento_editar(request, edificio_id, apartamento_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_apartamentos(request.user, edificio):
        raise PermissionDenied
    apartamento = get_object_or_404(
        Apartamento,
        pk=apartamento_id,
        edificio=edificio,
    )
    form = ApartamentoForm(
        request.POST or None,
        instance=apartamento,
        edificio=edificio,
    )
    if request.method == "POST" and form.is_valid():
        try:
            apartamento = form.save(commit=False)
            apartamento.full_clean()
            apartamento.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f"El apartamento {apartamento.numero} fue actualizado.",
            )
            return redirect(
                "accounts:apartamento_detalle",
                edificio_id=edificio.pk,
                apartamento_id=apartamento.pk,
            )

    return render(
        request,
        "finance/apartamento_form_page.html",
        {
            "edificio": edificio,
            "form": form,
            "apartamento": apartamento,
            "modo": "editar",
        },
    )


@login_required
@require_POST
def apartamento_cambiar_estado(request, edificio_id, apartamento_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_apartamentos(request.user, edificio):
        raise PermissionDenied
    apartamento = get_object_or_404(
        Apartamento,
        pk=apartamento_id,
        edificio=edificio,
    )
    apartamento.activo = not apartamento.activo
    apartamento.save(update_fields=["activo"])
    estado = "activado" if apartamento.activo else "desactivado"
    messages.success(request, f"El apartamento {apartamento.numero} fue {estado}.")
    return redirect(
        "finance:apartamentos_lista",
        edificio_id=edificio.pk,
    )


@login_required
@require_http_methods(["GET", "POST"])
def pago_registrar(request, edificio_id, apartamento_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    apartamento = obtener_apartamento_estado_cuenta(
        request.user,
        edificio,
        apartamento_id,
    )
    es_gestor = puede_registrar_finanzas(request.user, edificio)
    if not es_gestor:
        membresia = obtener_membresia(request.user, edificio)
        if membresia is None or membresia.rol != UsuarioEdificio.Rol.RESIDENTE:
            raise PermissionDenied
    form = RegistroPagoForm(
        request.POST or None,
        request.FILES or None,
        comprobante_requerido=not es_gestor,
    )
    if request.method == "POST" and form.is_valid():
        datos = {
            "apartamento": apartamento,
            "importe_total": form.cleaned_data["importe_total"],
            "fecha": form.cleaned_data["fecha"],
            "metodo": form.cleaned_data["metodo"],
            "referencia": form.cleaned_data["referencia"],
            "comprobante": form.cleaned_data["comprobante"],
            "usuario": request.user,
        }
        try:
            if es_gestor:
                pago = registrar_pago(**datos)
            else:
                pago = registrar_pago_residente(**datos)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f"Pago #{pago.pk} registrado y pendiente de revisión.",
            )
            return _success_redirect(
                request,
                reverse(
                    "accounts:apartamento_detalle",
                    args=[edificio.pk, apartamento.pk],
                ),
            )

    template = (
        "finance/partials/pago_form.html"
        if _is_htmx(request)
        else "finance/pago_form_page.html"
    )
    return render(
        request,
        template,
        {"edificio": edificio, "apartamento": apartamento, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def pago_revisar(request, edificio_id, pago_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_registrar_finanzas(request.user, edificio):
        raise PermissionDenied
    pago = _pago_del_edificio(edificio, pago_id)
    if pago.estado != Pago.Estado.PENDIENTE:
        messages.info(request, "Este pago ya fue procesado.")
        return redirect("accounts:edificio_detalle", edificio_id=edificio.pk)

    revision_form = RevisionPagoForm(
        request.POST or None,
        pago=pago,
        prefix="revision",
    )
    rechazo_form = RechazoPagoForm(
        request.POST or None,
        prefix="rechazo",
    )
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "confirmar" and revision_form.is_valid():
            try:
                confirmar_pago(
                    pago=pago,
                    usuario=request.user,
                    aplicaciones=revision_form.aplicaciones(),
                )
            except ValidationError as exc:
                revision_form.add_error(None, exc)
            else:
                messages.success(request, f"Pago #{pago.pk} confirmado.")
                return _success_redirect(
                    request,
                    reverse("accounts:edificio_detalle", args=[edificio.pk]),
                )
        elif accion == "rechazar" and rechazo_form.is_valid():
            try:
                rechazar_pago(
                    pago=pago,
                    usuario=request.user,
                    motivo=rechazo_form.cleaned_data["motivo"],
                )
            except ValidationError as exc:
                rechazo_form.add_error(None, exc)
            else:
                messages.success(request, f"Pago #{pago.pk} rechazado.")
                return _success_redirect(
                    request,
                    reverse("accounts:edificio_detalle", args=[edificio.pk]),
                )

    context = {
        "edificio": edificio,
        "pago": pago,
        "revision_form": revision_form,
        "rechazo_form": rechazo_form,
    }
    template = (
        "finance/partials/revision_forms.html"
        if _is_htmx(request)
        else "finance/pago_revision.html"
    )
    return render(request, template, context)


@login_required
def recibo_descargar(request, edificio_id, pago_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    pago = _pago_del_edificio(edificio, pago_id)
    if not puede_registrar_finanzas(request.user, edificio):
        apartamento = obtener_apartamento_estado_cuenta(
            request.user,
            edificio,
            pago.apartamento_id,
        )
        if apartamento.pk != pago.apartamento_id:
            raise Http404
    if pago.estado not in {Pago.Estado.CONFIRMADO, Pago.Estado.ANULADO}:
        raise Http404("El pago todavía no tiene recibo.")

    numero = f"REC-{edificio.pk:04d}-{pago.pk:08d}"
    contenido = render_to_string(
        "finance/recibo.html",
        {
            "edificio": edificio,
            "pago": pago,
            "numero_recibo": numero,
            "aplicaciones": pago.aplicaciones.select_related("cargo"),
        },
        request=request,
    )
    response = HttpResponse(contenido, content_type="text/html; charset=utf-8")
    filename = slugify(f"recibo-{numero}-{pago.apartamento.numero}")
    response["Content-Disposition"] = f'attachment; filename="{filename}.html"'
    return response


@login_required
def pago_comprobante(request, edificio_id, pago_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_registrar_finanzas(request.user, edificio):
        raise PermissionDenied
    pago = _pago_del_edificio(edificio, pago_id)
    if not pago.comprobante:
        raise Http404("Este pago no tiene comprobante.")
    content_type = mimetypes.guess_type(pago.comprobante.name)[0]
    return FileResponse(
        pago.comprobante.open("rb"),
        content_type=content_type or "application/octet-stream",
        filename=Path(pago.comprobante.name).name,
    )


@login_required
def gastos_lista(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_ver_reportes_financieros(request.user, edificio):
        raise PermissionDenied
    gastos = Gasto.objects.filter(edificio=edificio).select_related("creado_por")
    estado = request.GET.get("estado", "").strip()
    if estado in Gasto.Estado.values:
        gastos = gastos.filter(estado=estado)
    else:
        estado = ""
    periodo = request.GET.get("periodo", "").strip()
    if len(periodo) == 7 and periodo[4] == "-":
        try:
            anio, mes = (int(valor) for valor in periodo.split("-"))
        except ValueError:
            periodo = ""
        else:
            if 1 <= mes <= 12:
                gastos = gastos.filter(fecha__year=anio, fecha__month=mes)
            else:
                periodo = ""
    context = {
        "edificio": edificio,
        "gastos": gastos,
        "estado_seleccionado": estado,
        "periodo_seleccionado": periodo,
        "periodos": PeriodoCuota.objects.filter(edificio=edificio),
        "puede_registrar": puede_registrar_finanzas(request.user, edificio),
        "estados": Gasto.Estado.choices,
    }
    template = (
        "finance/partials/gastos_table.html"
        if _is_htmx(request)
        else "finance/gastos_lista.html"
    )
    return render(request, template, context)


@login_required
@require_http_methods(["GET", "POST"])
def gasto_registrar(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_registrar_finanzas(request.user, edificio):
        raise PermissionDenied
    form = GastoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            gasto = registrar_gasto(
                edificio=edificio,
                categoria=form.cleaned_data["categoria"],
                concepto=form.cleaned_data["concepto"],
                importe=form.cleaned_data["importe"],
                fecha=form.cleaned_data["fecha"],
                proveedor=form.cleaned_data["proveedor"],
                comprobante=form.cleaned_data["comprobante"],
                usuario=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f"Gasto #{gasto.pk} registrado y pendiente de confirmación.",
            )
            return _success_redirect(
                request,
                reverse("finance:gastos_lista", args=[edificio.pk]),
            )
    template = (
        "finance/partials/gasto_form.html"
        if _is_htmx(request)
        else "finance/gasto_form_page.html"
    )
    return render(request, template, {"edificio": edificio, "form": form})


@login_required
@require_POST
def gasto_confirmar(request, edificio_id, gasto_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_registrar_finanzas(request.user, edificio):
        raise PermissionDenied
    gasto = get_object_or_404(Gasto, pk=gasto_id, edificio=edificio)
    try:
        confirmar_gasto(gasto=gasto, usuario=request.user)
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Gasto #{gasto.pk} confirmado.")
    return _success_redirect(
        request,
        reverse("finance:gastos_lista", args=[edificio.pk]),
    )


@login_required
def gasto_comprobante(request, edificio_id, gasto_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_ver_reportes_financieros(request.user, edificio):
        raise PermissionDenied
    gasto = get_object_or_404(Gasto, pk=gasto_id, edificio=edificio)
    if not gasto.comprobante:
        raise Http404("Este gasto no tiene comprobante.")
    content_type = mimetypes.guess_type(gasto.comprobante.name)[0]
    return FileResponse(
        gasto.comprobante.open("rb"),
        content_type=content_type or "application/octet-stream",
        filename=Path(gasto.comprobante.name).name,
    )
