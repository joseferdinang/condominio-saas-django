from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "cuentas/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("cuentas/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "cuentas/apariencia/",
        views.guardar_preferencia_visual,
        name="guardar_preferencia_visual",
    ),
    path(
        "cuentas/contrasena/cambiar/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url=reverse_lazy("accounts:password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "cuentas/contrasena/cambiada/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path(
        "cuentas/contrasena/recuperar/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "cuentas/contrasena/recuperar/enviada/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "cuentas/contrasena/restablecer/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "cuentas/contrasena/restablecida/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path(
        "edificios/<int:edificio_id>/",
        views.edificio_detalle,
        name="edificio_detalle",
    ),
    path(
        "edificios/<int:edificio_id>/apartamentos/<int:apartamento_id>/",
        views.apartamento_detalle,
        name="apartamento_detalle",
    ),
    path(
        "edificios/<int:edificio_id>/usuarios/invitar/",
        views.invitar_usuario,
        name="invitar_usuario",
    ),
]
