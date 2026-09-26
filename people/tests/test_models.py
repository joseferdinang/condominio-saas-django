from datetime import date

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from buildings.models import Apartamento, Edificio
from people.models import Persona, RelacionApartamento


class RelacionApartamentoIntegrityTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(
            nombre="Residencial Prueba",
            direccion="Santiago de los Caballeros",
        )
        self.apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="1-A",
        )
        self.persona = Persona.objects.create(
            nombre_completo="Ana Pérez",
            telefono="809-555-0101",
            correo="ana@example.test",
        )

    def test_apartamento_admite_varias_personas(self):
        segunda_persona = Persona.objects.create(
            nombre_completo="Luis Pérez",
            telefono="809-555-0102",
            correo="luis@example.test",
        )
        RelacionApartamento.objects.create(
            persona=self.persona,
            apartamento=self.apartamento,
            tipo=RelacionApartamento.Tipo.PROPIETARIO,
            fecha_inicio=date(2026, 1, 1),
        )
        RelacionApartamento.objects.create(
            persona=segunda_persona,
            apartamento=self.apartamento,
            tipo=RelacionApartamento.Tipo.OCUPANTE,
            fecha_inicio=date(2026, 1, 1),
        )

        self.assertEqual(self.apartamento.relaciones_personas.count(), 2)

    def test_fecha_final_no_puede_ser_anterior_al_inicio_en_base_de_datos(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RelacionApartamento.objects.create(
                persona=self.persona,
                apartamento=self.apartamento,
                tipo=RelacionApartamento.Tipo.INQUILINO,
                fecha_inicio=date(2026, 2, 1),
                fecha_finalizacion=date(2026, 1, 31),
            )

    def test_tipo_de_relacion_invalido_es_rechazado_por_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RelacionApartamento.objects.create(
                persona=self.persona,
                apartamento=self.apartamento,
                tipo="OTRO",
                fecha_inicio=date(2026, 1, 1),
            )

    def test_ver_estado_de_cuenta_requiere_acceso_al_portal(self):
        relacion = RelacionApartamento(
            persona=self.persona,
            apartamento=self.apartamento,
            tipo=RelacionApartamento.Tipo.PROPIETARIO,
            fecha_inicio=date(2026, 1, 1),
            puede_acceder_portal=False,
            puede_ver_estado_cuenta=True,
        )

        with self.assertRaises(ValidationError):
            relacion.full_clean()

    def test_modelos_estan_registrados_en_admin(self):
        self.assertTrue(admin.site.is_registered(Persona))
        self.assertTrue(admin.site.is_registered(RelacionApartamento))


class PersonaValidationTests(TestCase):
    def test_telefono_y_correo_se_validan(self):
        persona = Persona(
            nombre_completo="Persona Inválida",
            telefono="abc",
            correo="correo-invalido",
        )

        with self.assertRaises(ValidationError) as context:
            persona.full_clean()

        self.assertIn("telefono", context.exception.message_dict)
        self.assertIn("correo", context.exception.message_dict)

    def test_identificacion_opcional_es_unica_cuando_existe(self):
        Persona.objects.create(
            nombre_completo="Ana Pérez",
            telefono="809-555-0101",
            correo="ana@example.test",
            identificacion="001-0000001-1",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Persona.objects.create(
                nombre_completo="Otra persona",
                telefono="809-555-0102",
                correo="otra@example.test",
                identificacion="001-0000001-1",
            )

    def test_un_usuario_solo_puede_vincularse_con_una_persona(self):
        usuario = get_user_model().objects.create_user(username="residente")
        Persona.objects.create(
            usuario=usuario,
            nombre_completo="Primera persona",
            telefono="809-555-0101",
            correo="primera@example.test",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Persona.objects.create(
                usuario=usuario,
                nombre_completo="Segunda persona",
                telefono="809-555-0102",
                correo="segunda@example.test",
            )
