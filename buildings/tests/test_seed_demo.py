from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio
from people.models import Persona, RelacionApartamento


class SeedDemoCommandTests(TestCase):
    def test_comando_es_idempotente_y_crea_doce_apartamentos(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)

        edificio = Edificio.objects.get(nombre="Residencial Demo Santiago")
        self.assertEqual(Apartamento.objects.filter(edificio=edificio).count(), 12)
        self.assertEqual(Persona.objects.count(), 15)
        self.assertEqual(
            RelacionApartamento.objects.filter(apartamento__edificio=edificio).count(),
            15,
        )
        self.assertEqual(
            UsuarioEdificio.objects.filter(edificio=edificio).count(),
            1,
        )
        self.assertFalse(
            get_user_model().objects.get(username="admin_demo").has_usable_password()
        )
