from datetime import time, timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UsuarioEdificio
from buildings.models import Edificio, ReservaZona, ZonaComun
from buildings.reservations import crear_reservacion


class ReservacionesTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.edificio = Edificio.objects.create(
            nombre="Residencial Reservas",
            direccion="Santiago",
        )
        self.otro_edificio = Edificio.objects.create(
            nombre="Residencial Ajeno Reservas",
            direccion="Santiago",
        )
        self.admin = users.objects.create_user(username="admin-reservas")
        self.residente = users.objects.create_user(
            username="maria-reservas",
            first_name="María",
        )
        self.otro_residente = users.objects.create_user(username="pedro-reservas")
        self.admin_ajeno = users.objects.create_user(username="admin-ajeno-reservas")
        UsuarioEdificio.objects.bulk_create(
            [
                UsuarioEdificio(usuario=self.admin, edificio=self.edificio, rol=UsuarioEdificio.Rol.ADMINISTRADOR),
                UsuarioEdificio(usuario=self.residente, edificio=self.edificio, rol=UsuarioEdificio.Rol.RESIDENTE),
                UsuarioEdificio(usuario=self.otro_residente, edificio=self.edificio, rol=UsuarioEdificio.Rol.RESIDENTE),
                UsuarioEdificio(usuario=self.admin_ajeno, edificio=self.otro_edificio, rol=UsuarioEdificio.Rol.ADMINISTRADOR),
            ]
        )
        self.zona = ZonaComun.objects.create(
            edificio=self.edificio,
            nombre="Salón social",
            ubicacion="Primer nivel",
            hora_apertura=time(8, 0),
            hora_cierre=time(12, 0),
            duracion_bloque_minutos=60,
        )
        self.zona_ajena = ZonaComun.objects.create(
            edificio=self.otro_edificio,
            nombre="Terraza ajena",
            hora_apertura=time(8, 0),
            hora_cierre=time(12, 0),
            duracion_bloque_minutos=60,
        )
        self.fecha = timezone.localdate() + timedelta(days=2)

    def crear_reserva(self, usuario=None, detalle="Cumpleaños privado"):
        return crear_reservacion(
            zona=self.zona,
            usuario=usuario or self.residente,
            fecha=self.fecha,
            hora_inicio=time(9, 0),
            detalle_privado=detalle,
        )

    def test_administrador_crea_y_edita_zona_residente_no_puede(self):
        self.client.force_login(self.admin)
        crear = self.client.post(
            reverse("buildings:zona_crear", args=[self.edificio.pk]),
            {
                "nombre": "Gazebo",
                "ubicacion": "Patio",
                "descripcion": "Área techada",
                "hora_apertura": "10:00",
                "hora_cierre": "20:00",
                "duracion_bloque_minutos": "120",
                "activo": "on",
            },
        )
        self.assertEqual(crear.status_code, 302)
        gazebo = ZonaComun.objects.get(edificio=self.edificio, nombre="Gazebo")

        editar = self.client.post(
            reverse("buildings:zona_editar", args=[self.edificio.pk, gazebo.pk]),
            {
                "nombre": "Gazebo principal",
                "ubicacion": "Patio",
                "descripcion": "Área techada",
                "hora_apertura": "10:00",
                "hora_cierre": "20:00",
                "duracion_bloque_minutos": "60",
                "activo": "on",
            },
        )
        self.assertEqual(editar.status_code, 302)
        gazebo.refresh_from_db()
        self.assertEqual(gazebo.nombre, "Gazebo principal")

        self.client.force_login(self.residente)
        denegado = self.client.get(
            reverse("buildings:zona_editar", args=[self.edificio.pk, gazebo.pk])
        )
        self.assertEqual(denegado.status_code, 403)

    def test_impide_reservar_el_mismo_horario_dos_veces(self):
        self.crear_reserva()

        with self.assertRaisesMessage(ValidationError, "acaba de ser reservado"):
            self.crear_reserva(usuario=self.otro_residente)

        self.assertEqual(
            ReservaZona.objects.filter(estado=ReservaZona.Estado.CONFIRMADA).count(),
            1,
        )

    def test_residente_no_ve_identidad_ni_detalle_de_otra_reserva(self):
        self.crear_reserva()
        self.client.force_login(self.otro_residente)

        response = self.client.get(
            reverse("buildings:reservaciones_lista", args=[self.edificio.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salón social")
        self.assertContains(response, "09:00–10:00")
        self.assertContains(response, "Ocupado")
        self.assertNotContains(response, "maria-reservas")
        self.assertNotContains(response, "Cumpleaños privado")

    def test_tesoreria_y_junta_no_ven_detalle_privado_en_django_admin(self):
        reserva = self.crear_reserva()
        modelo_admin = admin.site._registry[ReservaZona]
        for rol in (UsuarioEdificio.Rol.TESORERO, UsuarioEdificio.Rol.JUNTA):
            with self.subTest(rol=rol):
                usuario = get_user_model().objects.create_user(
                    username=f"staff-{rol.lower()}", is_staff=True
                )
                UsuarioEdificio.objects.create(usuario=usuario, edificio=self.edificio, rol=rol)
                self.client.force_login(usuario)
                url = reverse("admin:buildings_reservazona_changelist")
                self.assertEqual(self.client.get(url).status_code, 403)
                url_detalle = reverse("admin:buildings_reservazona_change", args=[reserva.pk])
                self.assertEqual(self.client.get(url_detalle).status_code, 403)

        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("admin:buildings_reservazona_changelist")).status_code,
            200,
        )

    def test_propietario_y_administrador_si_ven_detalle_privado(self):
        self.crear_reserva()
        for usuario in (self.residente, self.admin):
            self.client.force_login(usuario)
            response = self.client.get(
                reverse("buildings:reservaciones_lista", args=[self.edificio.pk])
            )
            self.assertContains(response, "Cumpleaños privado")
        self.assertContains(response, "María")

    def test_cancelacion_es_trazable_y_solo_la_hace_dueno_o_admin(self):
        reserva = self.crear_reserva()
        url = reverse(
            "buildings:reservacion_cancelar",
            args=[self.edificio.pk, reserva.pk],
        )
        self.client.force_login(self.otro_residente)
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.residente)
        self.assertEqual(self.client.post(url).status_code, 302)
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, ReservaZona.Estado.CANCELADA)
        self.assertEqual(reserva.cancelada_por, self.residente)
        self.assertIsNotNone(reserva.cancelada_en)

        nueva = self.crear_reserva(usuario=self.otro_residente, detalle="")
        self.assertEqual(nueva.estado, ReservaZona.Estado.CONFIRMADA)

    def test_no_permite_consultar_zona_de_otro_edificio_cambiando_id(self):
        self.client.force_login(self.residente)
        crear_ajena = self.client.get(
            reverse("buildings:reservacion_crear", args=[self.otro_edificio.pk])
        )
        self.client.force_login(self.admin)
        editar_ajena = self.client.get(
            reverse(
                "buildings:zona_editar",
                args=[self.edificio.pk, self.zona_ajena.pk],
            )
        )
        horarios_ajenos = self.client.get(
            reverse("buildings:reservacion_horarios", args=[self.edificio.pk]),
            {"zona": self.zona_ajena.pk, "fecha": self.fecha.isoformat()},
        )

        self.assertEqual(crear_ajena.status_code, 404)
        self.assertEqual(editar_ajena.status_code, 404)
        self.assertNotContains(horarios_ajenos, "08:00")

    def test_residente_reserva_desde_la_vista(self):
        self.client.force_login(self.residente)
        response = self.client.post(
            reverse("buildings:reservacion_crear", args=[self.edificio.pk]),
            {
                "zona": self.zona.pk,
                "fecha": self.fecha.isoformat(),
                "hora_inicio": "10:00",
                "detalle_privado": "Reunión familiar",
            },
        )

        self.assertEqual(response.status_code, 302)
        reserva = ReservaZona.objects.get(usuario=self.residente)
        self.assertEqual(reserva.hora_inicio, time(10, 0))
        self.assertEqual(reserva.hora_fin, time(11, 0))
        self.assertEqual(reserva.detalle_privado, "Reunión familiar")
