from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio
from finance.models import Cargo, PeriodoCuota


class MonthlyCronTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cron-test")
        self.building = Edificio.objects.create(nombre="Cron", direccion="Santiago")
        UsuarioEdificio.objects.create(usuario=self.user, edificio=self.building, rol=UsuarioEdificio.Rol.TESORERO)
        Apartamento.objects.create(edificio=self.building, numero="1", cuota_mensual=Decimal("2500.00"))

    @patch("finance.management.commands.generar_cuotas.timezone.localdate", return_value=date(2028, 2, 1))
    def test_current_month_is_idempotent_and_clamps_due_date(self, localdate):
        for _ in range(2):
            call_command("generar_cuotas", actual=True, edificio=self.building.pk, usuario=self.user.username, dia_vencimiento=31)
        self.assertEqual(Cargo.objects.count(), 1)
        self.assertEqual(PeriodoCuota.objects.get().fecha_vencimiento, date(2028, 2, 29))

    def test_cron_does_not_bypass_financial_permissions(self):
        UsuarioEdificio.objects.update(rol=UsuarioEdificio.Rol.RESIDENTE)
        with self.assertRaises(CommandError):
            call_command("generar_cuotas", actual=True, edificio=self.building.pk, usuario=self.user.username)
        self.assertEqual(Cargo.objects.count(), 0)

    def test_rejects_ambiguous_dates(self):
        with self.assertRaises(CommandError):
            call_command("generar_cuotas", actual=True, anio=2026, edificio=self.building.pk, usuario=self.user.username)
