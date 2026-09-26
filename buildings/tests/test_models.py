from decimal import Decimal

from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import TestCase

from buildings.models import Apartamento, Edificio


class ApartamentoIntegrityTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(
            nombre="Residencial Prueba",
            direccion="Santiago de los Caballeros",
        )

    def test_numero_es_unico_en_el_edificio_sin_importar_mayusculas(self):
        Apartamento.objects.create(edificio=self.edificio, numero="A-01")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(edificio=self.edificio, numero="a-01")

    def test_mismo_numero_se_permite_en_otro_edificio(self):
        otro_edificio = Edificio.objects.create(
            nombre="Residencial Alterno",
            direccion="Santiago de los Caballeros",
        )
        Apartamento.objects.create(edificio=self.edificio, numero="1")

        apartamento = Apartamento.objects.create(
            edificio=otro_edificio,
            numero="1",
        )

        self.assertIsNotNone(apartamento.pk)

    def test_restricciones_monetarias_y_porcentuales_viven_en_la_base(self):
        casos_invalidos = (
            {"numero": "1", "cuota_mensual": Decimal("-0.01")},
            {"numero": "2", "porcentaje_contribucion": Decimal("100.0001")},
            {"numero": "3", "peso_voto": Decimal("-0.0001")},
        )

        for datos in casos_invalidos:
            with self.subTest(datos=datos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Apartamento.objects.create(edificio=self.edificio, **datos)

    def test_modelos_estan_registrados_en_admin(self):
        self.assertTrue(admin.site.is_registered(Edificio))
        self.assertTrue(admin.site.is_registered(Apartamento))
