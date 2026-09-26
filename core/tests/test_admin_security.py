from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio
from finance.models import AplicacionPago, Cargo, Gasto, Pago, PeriodoCuota, SaldoInicial
from people.models import Persona, RelacionApartamento


class DomainAdminSecurityTests(TestCase):
    domain_models = (
        Edificio,
        Apartamento,
        Persona,
        RelacionApartamento,
        UsuarioEdificio,
        PeriodoCuota,
        Cargo,
        Pago,
        AplicacionPago,
        Gasto,
        SaldoInicial,
    )

    def setUp(self):
        self.factory = RequestFactory()
        self.staff_user = get_user_model().objects.create_user(
            username="staff",
            is_staff=True,
        )
        self.superuser = get_user_model().objects.create_superuser(
            username="technical-admin",
            email="technical-admin@example.test",
            password="test-password-only",
        )

    def test_staff_comun_no_puede_ver_modelos_del_dominio(self):
        request = self.factory.get("/admin/")
        request.user = self.staff_user

        for model in self.domain_models:
            with self.subTest(model=model):
                model_admin = admin.site._registry[model]
                self.assertFalse(model_admin.has_module_permission(request))
                self.assertFalse(model_admin.has_view_permission(request))

    def test_superusuario_tecnico_puede_ver_modelos_del_dominio(self):
        request = self.factory.get("/admin/")
        request.user = self.superuser

        for model in self.domain_models:
            with self.subTest(model=model):
                model_admin = admin.site._registry[model]
                self.assertTrue(model_admin.has_module_permission(request))
                self.assertTrue(model_admin.has_view_permission(request))

    def test_admin_de_edificio_solo_ve_registros_de_su_edificio(self):
        edificio_propio = Edificio.objects.create(
            nombre="Edificio propio",
            direccion="Santiago",
        )
        edificio_ajeno = Edificio.objects.create(
            nombre="Edificio ajeno",
            direccion="Santiago",
        )
        usuario = get_user_model().objects.create_user(
            username="admin-edificio",
            is_staff=True,
        )
        UsuarioEdificio.objects.create(
            usuario=usuario,
            edificio=edificio_propio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )
        request = self.factory.get("/admin/buildings/edificio/")
        request.user = usuario
        model_admin = admin.site._registry[Edificio]

        self.assertQuerySetEqual(
            model_admin.get_queryset(request),
            [edificio_propio],
        )
        self.assertTrue(model_admin.has_change_permission(request, edificio_propio))
        self.assertFalse(model_admin.has_view_permission(request, edificio_ajeno))

    def test_tesorero_no_puede_modificar_usuarios_ni_modelos_base(self):
        edificio = Edificio.objects.create(
            nombre="Edificio tesorería",
            direccion="Santiago",
        )
        tesorero = get_user_model().objects.create_user(
            username="tesorero-staff",
            is_staff=True,
        )
        UsuarioEdificio.objects.create(
            usuario=tesorero,
            edificio=edificio,
            rol=UsuarioEdificio.Rol.TESORERO,
        )
        request = self.factory.get("/admin/")
        request.user = tesorero

        edificio_admin = admin.site._registry[Edificio]
        usuarios_admin = admin.site._registry[UsuarioEdificio]
        self.assertTrue(edificio_admin.has_view_permission(request, edificio))
        self.assertFalse(edificio_admin.has_change_permission(request, edificio))
        self.assertFalse(usuarios_admin.has_module_permission(request))
