from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_http_methods, require_POST

from .forms import InvitacionUsuarioForm
from .models import PreferenciaVisual
from .services import (
    apartamentos_visibles,
    edificios_visibles,
    obtener_apartamento_estado_cuenta,
    obtener_edificio_visible,
    puede_gestionar_usuarios,
    puede_gestionar_apartamentos,
)


@login_required
def dashboard(request):
    return render(
        request,
        "accounts/dashboard.html",
        {"edificios": edificios_visibles(request.user)},
    )


@login_required
@require_POST
def guardar_preferencia_visual(request):
    tema = request.POST.get("tema", "").strip()
    paleta = request.POST.get("paleta", "").strip()
    if tema not in PreferenciaVisual.Tema.values:
        return JsonResponse({"error": "Tema no válido."}, status=400)
    if paleta not in PreferenciaVisual.Paleta.values:
        return JsonResponse({"error": "Paleta no válida."}, status=400)

    preferencia, _ = PreferenciaVisual.objects.update_or_create(
        usuario=request.user,
        defaults={"tema": tema, "paleta": paleta},
    )
    return JsonResponse(
        {
            "tema": preferencia.tema,
            "paleta": preferencia.paleta,
            "mensaje": "Preferencia visual guardada.",
        }
    )


@login_required
def edificio_detalle(request, edificio_id):
    from finance.selectors import contexto_resumen_edificio

    edificio = obtener_edificio_visible(request.user, edificio_id)
    context = contexto_resumen_edificio(usuario=request.user, edificio=edificio)
    context.update(
        {
            "edificio": edificio,
            "apartamentos": apartamentos_visibles(request.user, edificio),
            "puede_gestionar_usuarios": puede_gestionar_usuarios(
                request.user, edificio
            ),
        }
    )
    return render(
        request,
        "finance/resumen_edificio.html",
        context,
    )


@login_required
def apartamento_detalle(request, edificio_id, apartamento_id):
    from buildings.models import Aviso
    from finance.models import Cargo, Pago, PeriodoCuota
    from finance.services import calcular_saldo_apartamento

    edificio = obtener_edificio_visible(request.user, edificio_id)
    apartamento = obtener_apartamento_estado_cuenta(
        request.user,
        edificio,
        apartamento_id,
    )
    cargos = apartamento.cargos.exclude(estado=Cargo.Estado.ANULADO)
    periodo_id = request.GET.get("periodo", "").strip()
    if periodo_id.isdigit():
        cargos = cargos.filter(periodo_id=periodo_id, periodo__edificio=edificio)
    estado = request.GET.get("estado", "").strip()
    if estado in Cargo.Estado.values:
        cargos = cargos.filter(estado=estado)
    else:
        estado = ""
    context = {
        "edificio": edificio,
        "apartamento": apartamento,
        "cargos": cargos.select_related("periodo"),
        "saldo_pendiente": calcular_saldo_apartamento(apartamento),
        "pagos": Pago.objects.filter(apartamento=apartamento).order_by(
            "-fecha", "-pk"
        ),
        "periodos": PeriodoCuota.objects.filter(edificio=edificio),
        "periodo_seleccionado": periodo_id,
        "estado_seleccionado": estado,
        "estados_cargo": Cargo.Estado.choices,
        "avisos": Aviso.objects.filter(
            edificio=edificio,
            estado=Aviso.Estado.PUBLICADO,
            fecha__lte=timezone.now(),
        )[:5],
        "puede_gestionar_apartamentos": puede_gestionar_apartamentos(
            request.user, edificio
        ),
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "finance/partials/cargos_table.html", context)
    return render(
        request,
        "accounts/apartamento_detalle.html",
        context,
    )


def _enviar_invitacion(request, usuario, edificio, creado):
    if creado:
        uid = urlsafe_base64_encode(force_bytes(usuario.pk))
        token = default_token_generator.make_token(usuario)
        url = request.build_absolute_uri(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
        )
    else:
        url = request.build_absolute_uri(reverse("accounts:login"))

    body = render_to_string(
        "accounts/emails/invitacion.txt",
        {
            "usuario": usuario,
            "edificio": edificio,
            "url": url,
            "cuenta_nueva": creado,
        },
    )
    send_mail(
        f"Invitación a {edificio.nombre}",
        body,
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
    )


@login_required
@require_http_methods(["GET", "POST"])
def invitar_usuario(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_usuarios(request.user, edificio):
        raise PermissionDenied

    form = InvitacionUsuarioForm(
        request.POST or None,
        edificio=edificio,
        permitir_administrador=request.user.is_superuser,
        permitir_usuarios_criticos=request.user.is_superuser,
    )
    if request.method == "POST" and form.is_valid():
        usuario, creado = form.save()
        _enviar_invitacion(request, usuario, edificio, creado)
        messages.success(request, "La invitación fue enviada correctamente.")
        return redirect("accounts:edificio_detalle", edificio_id=edificio.pk)

    return render(
        request,
        "accounts/invitar_usuario.html",
        {"edificio": edificio, "form": form},
    )
