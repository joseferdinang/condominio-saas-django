from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import UsuarioEdificio
from buildings.models import Edificio


class UsuarioEdificioIntegrityTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="tesorero")
        self.edificio = Edificio.objects.create(
            nombre="Residencial Prueba",
            direccion="Santiago de los Caballeros",
        )

    def test_usuario_tiene_un_solo_rol_por_edificio(self):
        UsuarioEdificio.objects.create(
            usuario=self.usuario,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.TESORERO,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            UsuarioEdificio.objects.create(
                usuario=self.usuario,
                edificio=self.edificio,
                rol=UsuarioEdificio.Rol.RESIDENTE,
            )

    def test_usuario_puede_pertenecer_a_varios_edificios(self):
        segundo_edificio = Edificio.objects.create(
            nombre="Residencial Alterno",
            direccion="Santiago de los Caballeros",
        )
        UsuarioEdificio.objects.create(
            usuario=self.usuario,
            edificio=self.edificio,
            rol=UsuarioEdificio.Rol.TESORERO,
        )

        segunda_membresia = UsuarioEdificio.objects.create(
            usuario=self.usuario,
            edificio=segundo_edificio,
            rol=UsuarioEdificio.Rol.ADMINISTRADOR,
        )

        self.assertIsNotNone(segunda_membresia.pk)

    def test_rol_invalido_es_rechazado_por_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UsuarioEdificio.objects.create(
                usuario=self.usuario,
                edificio=self.edificio,
                rol="OTRO",
            )

    def test_modelo_esta_registrado_en_admin(self):
        self.assertTrue(admin.site.is_registered(UsuarioEdificio))
