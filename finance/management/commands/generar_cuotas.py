import calendar
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from buildings.models import Edificio
from finance.services import generar_cuotas_mensuales


class Command(BaseCommand):
    help = "Genera de forma idempotente las cuotas mensuales de un edificio."

    def add_arguments(self, parser):
        parser.add_argument("--edificio", type=int, required=True)
        parser.add_argument("--anio", type=int)
        parser.add_argument("--mes", type=int)
        parser.add_argument("--fecha-vencimiento")
        parser.add_argument("--actual", action="store_true", help="Mes actual en America/Santo_Domingo.")
        parser.add_argument("--dia-vencimiento", type=int, default=10)
        parser.add_argument("--usuario", required=True)

    def handle(self, *args, **options):
        if options["actual"]:
            if any(options[key] is not None for key in ("anio", "mes", "fecha_vencimiento")):
                raise CommandError("--actual no se combina con año, mes o fecha explícitos.")
            if not 1 <= options["dia_vencimiento"] <= 31:
                raise CommandError("El día de vencimiento debe estar entre 1 y 31.")
            hoy = timezone.localdate()
            options["anio"], options["mes"] = hoy.year, hoy.month
            dia = min(options["dia_vencimiento"], calendar.monthrange(hoy.year, hoy.month)[1])
            options["fecha_vencimiento"] = date(hoy.year, hoy.month, dia).isoformat()
        elif any(options[key] is None for key in ("anio", "mes", "fecha_vencimiento")):
            raise CommandError("Indica --actual o --anio, --mes y --fecha-vencimiento.")
        try:
            edificio = Edificio.objects.get(pk=options["edificio"])
            usuario = get_user_model().objects.get(
                username=options["usuario"]
            )
            fecha_vencimiento = date.fromisoformat(
                options["fecha_vencimiento"]
            )
            periodo, creados = generar_cuotas_mensuales(
                edificio=edificio,
                anio=options["anio"],
                mes=options["mes"],
                fecha_vencimiento=fecha_vencimiento,
                usuario=usuario,
            )
        except (Edificio.DoesNotExist, get_user_model().DoesNotExist) as exc:
            raise CommandError("Edificio o usuario no encontrado.") from exc
        except ValueError as exc:
            raise CommandError(
                "La fecha debe usar el formato AAAA-MM-DD."
            ) from exc
        except (PermissionDenied, ValidationError) as exc:
            mensajes = getattr(exc, "messages", [str(exc)])
            raise CommandError("; ".join(mensajes)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Período {periodo.mes:02d}/{periodo.anio}: "
                f"{creados} cargo(s) creado(s)."
            )
        )
