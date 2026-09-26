from datetime import date, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.services import obtener_edificio_visible, puede_gestionar_usuarios

from .forms import AvisoForm, ReservaZonaForm, ZonaComunForm
from .models import Aviso, ReservaZona, ZonaComun
from .reservations import cancelar_reservacion, crear_reservacion, horarios_disponibles
from .services import enviar_aviso_por_correo, publicar_aviso


@login_required
def avisos_lista(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    puede_gestionar = puede_gestionar_usuarios(request.user, edificio)
    avisos = Aviso.objects.filter(edificio=edificio)
    if not puede_gestionar:
        avisos = avisos.filter(
            estado=Aviso.Estado.PUBLICADO,
            fecha__lte=timezone.now(),
        )
    return render(
        request,
        "buildings/avisos_lista.html",
        {
            "edificio": edificio,
            "avisos": avisos,
            "puede_gestionar": puede_gestionar,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def aviso_crear(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_usuarios(request.user, edificio):
        raise PermissionDenied
    form = AvisoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        aviso = form.save(commit=False)
        aviso.edificio = edificio
        aviso.creado_por = request.user
        aviso.full_clean()
        aviso.save()
        messages.success(request, "El aviso fue guardado correctamente.")
        return redirect("buildings:avisos_lista", edificio_id=edificio.pk)
    return render(
        request,
        "buildings/aviso_form.html",
        {"edificio": edificio, "form": form},
    )


@login_required
@require_POST
def aviso_publicar(request, edificio_id, aviso_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    aviso = get_object_or_404(Aviso, pk=aviso_id, edificio=edificio)
    publicar_aviso(aviso=aviso, usuario=request.user)
    messages.success(request, "El aviso fue publicado.")
    return redirect("buildings:avisos_lista", edificio_id=edificio.pk)


@login_required
@require_POST
def aviso_enviar(request, edificio_id, aviso_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    aviso = get_object_or_404(Aviso, pk=aviso_id, edificio=edificio)
    try:
        resultado = enviar_aviso_por_correo(aviso=aviso, usuario=request.user)
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Enviados: {resultado.enviados}; fallidos: {resultado.fallidos}; "
            f"omitidos por envío previo: {resultado.omitidos}.",
        )
    return redirect("buildings:avisos_lista", edificio_id=edificio.pk)


@login_required
def reservaciones_lista(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    puede_gestionar = puede_gestionar_usuarios(request.user, edificio)
    zonas = ZonaComun.objects.filter(edificio=edificio)
    if not puede_gestionar:
        zonas = zonas.filter(activo=True)

    reservas = ReservaZona.objects.filter(
        zona__edificio=edificio,
        fecha__gte=timezone.localdate(),
        fecha__lte=timezone.localdate() + timedelta(days=30),
        estado=ReservaZona.Estado.CONFIRMADA,
    ).select_related("zona", "usuario")
    fecha_filtro = request.GET.get("fecha", "").strip()
    zona_filtro = request.GET.get("zona", "").strip()
    if fecha_filtro:
        try:
            reservas = reservas.filter(fecha=date.fromisoformat(fecha_filtro))
        except ValueError:
            fecha_filtro = ""
    if zona_filtro.isdigit():
        reservas = reservas.filter(zona_id=zona_filtro, zona__edificio=edificio)
    else:
        zona_filtro = ""

    return render(
        request,
        "buildings/reservaciones_lista.html",
        {
            "edificio": edificio,
            "zonas": zonas,
            "reservaciones": reservas,
            "puede_gestionar": puede_gestionar,
            "fecha_filtro": fecha_filtro,
            "zona_filtro": zona_filtro,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def reservacion_crear(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    form = ReservaZonaForm(
        request.POST or None,
        edificio=edificio,
        horarios_url=reverse("buildings:reservacion_horarios", args=[edificio.pk]),
        initial={
            "zona": request.GET.get("zona", ""),
            "fecha": request.GET.get("fecha", timezone.localdate().isoformat()),
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            hora_inicio = time.fromisoformat(form.cleaned_data["hora_inicio"])
            crear_reservacion(
                zona=form.cleaned_data["zona"],
                usuario=request.user,
                fecha=form.cleaned_data["fecha"],
                hora_inicio=hora_inicio,
                detalle_privado=form.cleaned_data["detalle_privado"],
            )
        except (ValueError, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "La zona quedó reservada correctamente.")
            return redirect("buildings:reservaciones_lista", edificio_id=edificio.pk)
    return render(
        request,
        "buildings/reservacion_form.html",
        {"edificio": edificio, "form": form},
    )


@login_required
def reservacion_horarios(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    zona_id = request.GET.get("zona", "")
    zona = ZonaComun.objects.filter(
        pk=zona_id if zona_id.isdigit() else None,
        edificio=edificio,
        activo=True,
    ).first()
    try:
        fecha = date.fromisoformat(request.GET.get("fecha", ""))
    except ValueError:
        fecha = None
    horarios = horarios_disponibles(zona, fecha) if zona and fecha else []
    return render(
        request,
        "buildings/partials/horarios_options.html",
        {"horarios": horarios},
    )


@login_required
@require_POST
def reservacion_cancelar(request, edificio_id, reserva_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    reserva = get_object_or_404(
        ReservaZona.objects.select_related("zona__edificio"),
        pk=reserva_id,
        zona__edificio=edificio,
    )
    cancelar_reservacion(reserva=reserva, usuario=request.user)
    messages.success(request, "La reservación fue cancelada y el horario quedó libre.")
    return redirect("buildings:reservaciones_lista", edificio_id=edificio.pk)


@login_required
@require_http_methods(["GET", "POST"])
def zona_crear(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_usuarios(request.user, edificio):
        raise PermissionDenied
    form = ZonaComunForm(request.POST or None, edificio=edificio)
    if request.method == "POST" and form.is_valid():
        zona = form.save(commit=False)
        zona.edificio = edificio
        zona.full_clean()
        zona.save()
        messages.success(request, "La zona fue creada correctamente.")
        return redirect("buildings:reservaciones_lista", edificio_id=edificio.pk)
    return render(
        request,
        "buildings/zona_form.html",
        {"edificio": edificio, "form": form, "modo": "crear"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def zona_editar(request, edificio_id, zona_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_usuarios(request.user, edificio):
        raise PermissionDenied
    zona = get_object_or_404(ZonaComun, pk=zona_id, edificio=edificio)
    form = ZonaComunForm(request.POST or None, instance=zona, edificio=edificio)
    if request.method == "POST" and form.is_valid():
        zona = form.save(commit=False)
        zona.full_clean()
        zona.save()
        messages.success(request, "La zona fue actualizada.")
        return redirect("buildings:reservaciones_lista", edificio_id=edificio.pk)
    return render(
        request,
        "buildings/zona_form.html",
        {"edificio": edificio, "zona": zona, "form": form, "modo": "editar"},
    )
