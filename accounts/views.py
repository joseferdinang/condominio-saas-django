import logging
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_http_methods, require_POST

from core.models import Cambio

from .forms import EditarUsuarioEdificioForm, InvitacionUsuarioForm, MiCuentaForm
from .models import PreferenciaVisual, UsuarioEdificio
from .services import (
    apartamentos_visibles,
    edificios_visibles,
    obtener_apartamento_estado_cuenta,
    obtener_edificio_visible,
    puede_gestionar_usuarios,
    puede_gestionar_apartamentos,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def mi_cuenta(request):
    anterior = request.user.get_username()
    form = MiCuentaForm(
        request.POST if request.method == "POST" else None, instance=request.user
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                usuario = form.save()
                edificios = (
                    UsuarioEdificio.objects.filter(usuario=usuario, activo=True)
                    .values_list("edificio_id", flat=True).distinct()
                )
                for edificio_id in edificios:
                    Cambio.objects.create(
                        edificio_id=edificio_id, usuario=usuario,
                        usuario_nombre=usuario.get_username(), accion=Cambio.Accion.MODIFICAR,
                        modelo=usuario._meta.label, objeto_id=str(usuario.pk),
                        descripcion=f"Actualización de cuenta propia: {anterior} → {usuario.get_username()}"[:255],
                    )
        except IntegrityError:
            form.add_error("username", "Ese nombre de usuario ya está en uso.")
        else:
            messages.success(request, "Tu cuenta se actualizó. Usa el nuevo nombre de usuario para iniciar sesión.")
            return redirect("accounts:mi_cuenta")
    return render(request, "accounts/mi_cuenta.html", {"form": form})


@login_required
def dashboard(request):
    edificios = edificios_visibles(request.user)
    administrables = (
        set(edificios.values_list("pk", flat=True))
        if request.user.is_superuser
        else set(UsuarioEdificio.objects.filter(
            usuario=request.user, activo=True, rol=UsuarioEdificio.Rol.ADMINISTRADOR,
            edificio__activo=True,
        ).values_list("edificio_id", flat=True))
    )
    return render(
        request,
        "accounts/dashboard.html",
        {"edificios": edificios, "edificios_administrables": administrables},
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
    enviados = send_mail(
        f"Invitación a {edificio.nombre}",
        body,
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
    )
    if enviados != 1:
        raise SMTPException("El servidor de correo no confirmó el envío.")


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
        try:
            with transaction.atomic():
                usuario, necesita_crear_clave = form.save()
                _enviar_invitacion(request, usuario, edificio, necesita_crear_clave)
        except (OSError, SMTPException) as exc:
            logger.warning("No se pudo enviar la invitación: %s", type(exc).__name__)
            form.add_error(
                None,
                "No se pudo enviar el correo. Revisa la configuración SMTP e inténtalo de nuevo; no se guardó ningún cambio.",
            )
        else:
            messages.success(request, "La invitación fue enviada correctamente.")
            return redirect("accounts:edificio_detalle", edificio_id=edificio.pk)

    return render(
        request,
        "accounts/invitar_usuario.html",
        {"edificio": edificio, "form": form},
    )


def _administracion_edificio(request, edificio_id):
    edificio = obtener_edificio_visible(request.user, edificio_id)
    if not puede_gestionar_usuarios(request.user, edificio):
        raise PermissionDenied
    return edificio


def _membresia_editable(request, edificio, membresia_id):
    membresia = get_object_or_404(
        UsuarioEdificio.objects.select_related("usuario"),
        pk=membresia_id,
        edificio=edificio,
    )
    if membresia.usuario.is_superuser or (
        membresia.rol == UsuarioEdificio.Rol.ADMINISTRADOR
        and not request.user.is_superuser
    ):
        raise PermissionDenied
    return membresia


def _puede_retirar_administrador(membresia):
    if membresia.rol != UsuarioEdificio.Rol.ADMINISTRADOR or not membresia.activo:
        return True
    return UsuarioEdificio.objects.filter(
        edificio=membresia.edificio,
        rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        activo=True,
    ).exclude(pk=membresia.pk).exists()


@login_required
def usuarios_lista(request, edificio_id):
    edificio = _administracion_edificio(request, edificio_id)
    busqueda = request.GET.get("q", "").strip()[:100]
    usuarios = UsuarioEdificio.objects.filter(edificio=edificio).select_related("usuario")
    if busqueda:
        usuarios = usuarios.filter(
            Q(usuario__username__icontains=busqueda)
            | Q(usuario__first_name__icontains=busqueda)
            | Q(usuario__last_name__icontains=busqueda)
            | Q(usuario__email__icontains=busqueda)
        )
    pagina = Paginator(usuarios.order_by("usuario__username", "pk"), 20).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "accounts/usuarios_lista.html",
        {"edificio": edificio, "pagina": pagina, "busqueda": busqueda},
    )


@login_required
@require_http_methods(["GET", "POST"])
def usuario_editar(request, edificio_id, membresia_id):
    edificio = _administracion_edificio(request, edificio_id)
    membresia = _membresia_editable(request, edificio, membresia_id)
    form = EditarUsuarioEdificioForm(
        request.POST or None, membresia=membresia, editor=request.user
    )
    if request.method == "POST" and form.is_valid():
        nuevo_rol = form.cleaned_data["rol"]
        nuevo_activo = form.cleaned_data["activo"]
        pierde_administracion = (
            membresia.rol == UsuarioEdificio.Rol.ADMINISTRADOR
            and (nuevo_rol != UsuarioEdificio.Rol.ADMINISTRADOR or not nuevo_activo)
        )
        if pierde_administracion and (
            membresia.usuario_id == request.user.pk
            or not _puede_retirar_administrador(membresia)
        ):
            form.add_error(None, "No puedes retirar al último administrador ni tu propio acceso administrativo.")
        else:
            with transaction.atomic():
                usuario = membresia.usuario
                if form.editar_datos:
                    campos = ("first_name", "last_name", "email")
                    modificados = []
                    for campo in campos:
                        valor = form.cleaned_data[campo].strip()
                        if getattr(usuario, campo) != valor:
                            setattr(usuario, campo, valor)
                            modificados.append(campo)
                    if modificados:
                        usuario.save(update_fields=modificados)
                        Cambio.objects.create(
                            edificio=edificio,
                            usuario=request.user,
                            usuario_nombre=request.user.get_username(),
                            accion=Cambio.Accion.MODIFICAR,
                            modelo=usuario._meta.label,
                            objeto_id=str(usuario.pk),
                            descripcion=f"Datos de cuenta actualizados: {usuario.get_username()}",
                        )
                if nuevo_rol != membresia.rol or nuevo_activo != membresia.activo:
                    membresia.rol = nuevo_rol
                    membresia.activo = nuevo_activo
                    membresia.save(update_fields=["rol", "activo"])
                requiere_staff = UsuarioEdificio.objects.filter(
                    usuario=usuario,
                    activo=True,
                    rol__in=[UsuarioEdificio.Rol.ADMINISTRADOR, UsuarioEdificio.Rol.TESORERO],
                ).exists()
                if usuario.is_staff != requiere_staff and not usuario.is_superuser:
                    usuario.is_staff = requiere_staff
                    usuario.save(update_fields=["is_staff"])
            messages.success(request, "Los cambios del usuario fueron guardados.")
            return redirect("accounts:usuarios_lista", edificio_id=edificio.pk)
    return render(
        request,
        "accounts/usuario_editar.html",
        {"edificio": edificio, "membresia": membresia, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def usuario_retirar(request, edificio_id, membresia_id):
    edificio = _administracion_edificio(request, edificio_id)
    membresia = _membresia_editable(request, edificio, membresia_id)
    if not membresia.activo:
        raise PermissionDenied
    if membresia.usuario_id == request.user.pk or not _puede_retirar_administrador(membresia):
        raise PermissionDenied
    if request.method == "POST":
        with transaction.atomic():
            membresia.activo = False
            membresia.save(update_fields=["activo"])
            usuario = membresia.usuario
            if usuario.is_staff and not usuario.is_superuser and not UsuarioEdificio.objects.filter(
                usuario=usuario,
                activo=True,
                rol__in=[UsuarioEdificio.Rol.ADMINISTRADOR, UsuarioEdificio.Rol.TESORERO],
            ).exists():
                usuario.is_staff = False
                usuario.save(update_fields=["is_staff"])
        messages.success(request, "El acceso al edificio fue retirado. La cuenta y el historial se conservaron.")
        return redirect("accounts:usuarios_lista", edificio_id=edificio.pk)
    return render(
        request,
        "accounts/usuario_retirar.html",
        {"edificio": edificio, "membresia": membresia},
    )


@login_required
def cambios_lista(request, edificio_id):
    edificio = _administracion_edificio(request, edificio_id)
    accion = request.GET.get("accion", "").strip()
    cambios = Cambio.objects.filter(edificio=edificio).select_related("usuario")
    if accion in Cambio.Accion.values:
        cambios = cambios.filter(accion=accion)
    else:
        accion = ""
    pagina = Paginator(cambios, 30).get_page(request.GET.get("page"))
    return render(
        request,
        "accounts/cambios_lista.html",
        {"edificio": edificio, "pagina": pagina, "accion": accion, "acciones": Cambio.Accion.choices},
    )
