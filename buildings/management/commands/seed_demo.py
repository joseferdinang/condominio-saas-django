from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Edificio
from people.models import Persona, RelacionApartamento


class Command(BaseCommand):
    help = "Carga datos ficticios idempotentes de un edificio con 12 apartamentos."

    @transaction.atomic
    def handle(self, *args, **options):
        edificio, _ = Edificio.objects.update_or_create(
            nombre="Residencial Demo Santiago",
            direccion="Avenida Demo 100, Santiago de los Caballeros",
            defaults={
                "telefono_administrativo": "809-555-0100",
                "correo_administrativo": "administracion@example.test",
                "activo": True,
            },
        )

        usuario, creado = get_user_model().objects.get_or_create(
            username="admin_demo",
            defaults={
                "email": "admin@example.test",
                "first_name": "Administración",
                "last_name": "Demo",
                "is_staff": False,
                "is_active": True,
            },
        )
        if creado:
            usuario.set_unusable_password()
            usuario.save(update_fields=["password"])

        UsuarioEdificio.objects.update_or_create(
            usuario=usuario,
            edificio=edificio,
            defaults={
                "rol": UsuarioEdificio.Rol.ADMINISTRADOR,
                "activo": True,
            },
        )

        fecha_inicio = date(2026, 1, 1)
        for numero in range(1, 13):
            porcentaje = Decimal("8.3334") if numero <= 4 else Decimal("8.3333")
            apartamento, _ = Apartamento.objects.update_or_create(
                edificio=edificio,
                numero=f"{numero:02d}",
                defaults={
                    "cuota_mensual": Decimal("3500.00"),
                    "porcentaje_contribucion": porcentaje,
                    "peso_voto": Decimal("1.0000"),
                    "activo": True,
                },
            )

            propietario, _ = Persona.objects.update_or_create(
                identificacion=f"DEMO-P-{numero:04d}",
                defaults={
                    "nombre_completo": f"Propietario Demo {numero:02d}",
                    "telefono": f"809-555-{1000 + numero:04d}",
                    "correo": f"propietario{numero:02d}@example.test",
                    "activo": True,
                },
            )
            RelacionApartamento.objects.update_or_create(
                persona=propietario,
                apartamento=apartamento,
                tipo=RelacionApartamento.Tipo.PROPIETARIO,
                fecha_inicio=fecha_inicio,
                defaults={
                    "fecha_finalizacion": None,
                    "puede_acceder_portal": True,
                    "puede_ver_estado_cuenta": True,
                    "puede_recibir_comunicaciones": True,
                },
            )

            if numero % 4 == 0:
                inquilino, _ = Persona.objects.update_or_create(
                    identificacion=f"DEMO-I-{numero:04d}",
                    defaults={
                        "nombre_completo": f"Inquilino Demo {numero:02d}",
                        "telefono": f"829-555-{1000 + numero:04d}",
                        "correo": f"inquilino{numero:02d}@example.test",
                        "activo": True,
                    },
                )
                RelacionApartamento.objects.update_or_create(
                    persona=inquilino,
                    apartamento=apartamento,
                    tipo=RelacionApartamento.Tipo.INQUILINO,
                    fecha_inicio=fecha_inicio,
                    defaults={
                        "fecha_finalizacion": None,
                        "puede_acceder_portal": True,
                        "puede_ver_estado_cuenta": False,
                        "puede_recibir_comunicaciones": True,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Datos demo listos: 1 edificio, 12 apartamentos, "
                "12 propietarios, 3 inquilinos y 1 usuario de edificio sin contraseña."
            )
        )
