import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UsuarioEdificio
from buildings.models import Apartamento, Aviso, Edificio
from finance.models import Cargo, Gasto, Pago
from finance.services import generar_cuotas_mensuales, registrar_pago
from people.models import Persona, RelacionApartamento


class PortalFinancieroViewTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        user_model = get_user_model()
        self.edificio = Edificio.objects.create(
            nombre="Residencial Portal",
            direccion="Santiago de los Caballeros",
        )
        self.otro_edificio = Edificio.objects.create(
            nombre="Residencial Ajeno",
            direccion="Santiago de los Caballeros",
        )
        self.apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="A-1",
            cuota_mensual=Decimal("1000.00"),
        )
        self.otro_apartamento = Apartamento.objects.create(
            edificio=self.edificio,
            numero="A-2",
            cuota_mensual=Decimal("1500.00"),
        )
        self.apartamento_ajeno = Apartamento.objects.create(
            edificio=self.otro_edificio,
            numero="B-1",
            cuota_mensual=Decimal("2000.00"),
        )
        self.administrador = user_model.objects.create_user(
            username="admin-web",
            password="Clave-segura-2026",
        )
        self.tesorero = user_model.objects.create_user(
            username="tesorero-web",
            password="Clave-segura-2026",
        )
        self.residente = user_model.objects.create_user(
            username="residente-web",
            password="Clave-segura-2026",
        )
        self.admin_ajeno = user_model.objects.create_user(
            username="admin-ajeno-web",
            password="Clave-segura-2026",
        )
        UsuarioEdificio.objects.bulk_create(
            [
                UsuarioEdificio(
                    usuario=self.administrador,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
                UsuarioEdificio(
                    usuario=self.tesorero,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.TESORERO,
                ),
                UsuarioEdificio(
                    usuario=self.residente,
                    edificio=self.edificio,
                    rol=UsuarioEdificio.Rol.RESIDENTE,
                ),
                UsuarioEdificio(
                    usuario=self.admin_ajeno,
                    edificio=self.otro_edificio,
                    rol=UsuarioEdificio.Rol.ADMINISTRADOR,
                ),
            ]
        )
        persona = Persona.objects.create(
            usuario=self.residente,
            nombre_completo="Residente Portal",
            telefono="809-555-0101",
            correo="residente@example.test",
        )
        RelacionApartamento.objects.create(
            persona=persona,
            apartamento=self.apartamento,
            tipo=RelacionApartamento.Tipo.PROPIETARIO,
            fecha_inicio=timezone.localdate() - timedelta(days=90),
            puede_acceder_portal=True,
            puede_ver_estado_cuenta=True,
        )
        self.periodo, _ = generar_cuotas_mensuales(
            edificio=self.edificio,
            anio=2026,
            mes=9,
            fecha_vencimiento=timezone.localdate(),
            usuario=self.administrador,
        )
        self.cargo = Cargo.objects.get(
            periodo=self.periodo,
            apartamento=self.apartamento,
        )
        Aviso.objects.create(
            edificio=self.edificio,
            titulo="Mantenimiento de cisterna",
            contenido="El servicio será el sábado.",
            estado=Aviso.Estado.PUBLICADO,
            creado_por=self.administrador,
        )
        Aviso.objects.create(
            edificio=self.edificio,
            titulo="Borrador interno",
            contenido="Este aviso no está publicado.",
            estado=Aviso.Estado.BORRADOR,
            creado_por=self.administrador,
        )

    def comprobante(self, nombre="comprobante.pdf"):
        return SimpleUploadedFile(
            nombre,
            b"%PDF-1.4 comprobante de prueba",
            content_type="application/pdf",
        )

    def test_administrador_ve_resumen_financiero_del_edificio(self):
        self.client.force_login(self.administrador)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saldo disponible")
        self.assertContains(response, "Cuotas del período")
        self.assertContains(response, "Pagos por revisar")
        self.assertContains(response, "Movimientos recientes")
        self.assertContains(response, "Mantenimiento de cisterna")
        self.assertNotContains(response, "Borrador interno")

    def test_residente_ve_solo_su_estado_de_cuenta_y_avisos_publicados(self):
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("accounts:edificio_detalle", args=[self.edificio.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apartamento A-1")
        self.assertContains(response, "Mantenimiento de cisterna")
        self.assertNotContains(response, "Apartamento A-2")
        self.assertNotContains(response, "Saldo disponible")
        self.assertNotContains(response, "Borrador interno")

    def test_busqueda_htmx_respeta_apartamentos_visibles(self):
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse("finance:apartamentos_lista", args=[self.edificio.pk]),
            {"q": "A-1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/partials/apartamentos_table.html")
        self.assertContains(response, "A-1")
        self.assertNotContains(response, "A-2")

    def test_filtros_de_apartamentos_funcionan_sin_htmx_y_muestran_chips(self):
        self.client.force_login(self.administrador)

        response = self.client.get(
            reverse("finance:apartamentos_lista", args=[self.edificio.pk]),
            {"q": "A-1", "periodo": self.periodo.pk, "estado": "PENDIENTE"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtros activos")
        self.assertContains(response, "Unidad: A-1")
        self.assertContains(response, "Septiembre 2026")
        self.assertContains(response, "Pendiente")
        self.assertContains(response, "Quitar filtros")
        self.assertContains(response, "<html", html=False)

    def test_residente_no_puede_abrir_otro_apartamento(self):
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio.pk, self.otro_apartamento.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_residente_carga_comprobante_y_pago_queda_pendiente(self):
        self.client.force_login(self.residente)

        response = self.client.post(
            reverse(
                "finance:pago_registrar",
                args=[self.edificio.pk, self.apartamento.pk],
            ),
            {
                "importe_total": "400.00",
                "fecha": "2026-09-15",
                "metodo": Pago.Metodo.TRANSFERENCIA,
                "referencia": "TRX-001",
                "comprobante": self.comprobante(),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "accounts:apartamento_detalle",
                args=[self.edificio.pk, self.apartamento.pk],
            ),
        )
        pago = Pago.objects.get(referencia="TRX-001")
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertEqual(pago.registrado_por, self.residente)
        self.assertTrue(pago.comprobante.name.endswith("comprobante.pdf"))

    def test_residente_debe_adjuntar_comprobante(self):
        self.client.force_login(self.residente)

        response = self.client.post(
            reverse(
                "finance:pago_registrar",
                args=[self.edificio.pk, self.apartamento.pk],
            ),
            {
                "importe_total": "400.00",
                "fecha": "2026-09-15",
                "metodo": Pago.Metodo.EFECTIVO,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "comprobante", "Este campo es obligatorio.")
        self.assertFalse(Pago.objects.exists())

    def test_formulario_htmx_conserva_errores_de_validacion(self):
        self.client.force_login(self.residente)

        response = self.client.post(
            reverse(
                "finance:pago_registrar",
                args=[self.edificio.pk, self.apartamento.pk],
            ),
            {
                "importe_total": "400.00",
                "fecha": "2026-09-15",
                "metodo": Pago.Metodo.TRANSFERENCIA,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/partials/pago_form.html")
        self.assertContains(response, "Este campo es obligatorio.")
        self.assertNotContains(response, "<html", html=False)

    def test_comprobante_con_contenido_invalido_es_rechazado(self):
        self.client.force_login(self.residente)

        response = self.client.post(
            reverse(
                "finance:pago_registrar",
                args=[self.edificio.pk, self.apartamento.pk],
            ),
            {
                "importe_total": "400.00",
                "fecha": "2026-09-15",
                "metodo": Pago.Metodo.TRANSFERENCIA,
                "comprobante": SimpleUploadedFile(
                    "comprobante.pdf",
                    b"esto no es un PDF",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "comprobante",
            "El contenido del archivo no coincide con su extensión.",
        )
        self.assertFalse(Pago.objects.exists())

    def test_administrador_confirma_pago_y_residente_descarga_recibo(self):
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("400.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.TRANSFERENCIA,
            referencia="TRX-CONFIRMAR",
            comprobante=self.comprobante("confirmar.pdf"),
            usuario=self.administrador,
        )
        self.client.force_login(self.administrador)

        response = self.client.post(
            reverse(
                "finance:pago_revisar",
                args=[self.edificio.pk, pago.pk],
            ),
            {
                "accion": "confirmar",
                f"revision-cargo_{self.cargo.pk}": "400.00",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:edificio_detalle", args=[self.edificio.pk]),
        )
        pago.refresh_from_db()
        self.cargo.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.CONFIRMADO)
        self.assertEqual(self.cargo.estado, Cargo.Estado.PARCIAL)

        self.client.force_login(self.residente)
        recibo = self.client.get(
            reverse(
                "finance:recibo_descargar",
                args=[self.edificio.pk, pago.pk],
            )
        )
        self.assertEqual(recibo.status_code, 200)
        self.assertEqual(recibo["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("attachment;", recibo["Content-Disposition"])
        self.assertContains(recibo, "REC-")

    def test_administrador_rechaza_pago_con_trazabilidad(self):
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("300.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.DEPOSITO,
            usuario=self.tesorero,
        )
        self.client.force_login(self.administrador)

        response = self.client.post(
            reverse(
                "finance:pago_revisar",
                args=[self.edificio.pk, pago.pk],
            ),
            {
                "accion": "rechazar",
                "rechazo-motivo": "El comprobante no es legible.",
            },
        )

        self.assertEqual(response.status_code, 302)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.RECHAZADO)
        self.assertEqual(pago.rechazado_por, self.administrador)
        self.assertIsNotNone(pago.fecha_rechazo)
        self.assertEqual(pago.motivo_rechazo, "El comprobante no es legible.")

    def test_cambiar_edificio_en_url_no_expone_pago(self):
        pago_ajeno = Pago.objects.create(
            apartamento=self.apartamento_ajeno,
            importe_total=Decimal("500.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.EFECTIVO,
            registrado_por=self.admin_ajeno,
        )
        self.client.force_login(self.administrador)

        response = self.client.get(
            reverse(
                "finance:pago_revisar",
                args=[self.edificio.pk, pago_ajeno.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_comprobante_requiere_permiso_y_edificio_correcto(self):
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("250.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.TRANSFERENCIA,
            comprobante=self.comprobante("protegido.pdf"),
            usuario=self.administrador,
        )

        self.client.force_login(self.administrador)
        permitido = self.client.get(
            reverse(
                "finance:pago_comprobante",
                args=[self.edificio.pk, pago.pk],
            )
        )
        self.assertEqual(permitido.status_code, 200)
        self.assertEqual(permitido["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(permitido.streaming_content).startswith(b"%PDF-"))

        self.client.force_login(self.residente)
        denegado = self.client.get(
            reverse(
                "finance:pago_comprobante",
                args=[self.edificio.pk, pago.pk],
            )
        )
        self.assertEqual(denegado.status_code, 403)

        self.client.force_login(self.admin_ajeno)
        edificio_ajeno = self.client.get(
            reverse(
                "finance:pago_comprobante",
                args=[self.edificio.pk, pago.pk],
            )
        )
        self.assertEqual(edificio_ajeno.status_code, 404)

    def test_residente_no_puede_revisar_pagos_ni_ver_gastos(self):
        pago = registrar_pago(
            apartamento=self.apartamento,
            importe_total=Decimal("100.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.EFECTIVO,
            usuario=self.tesorero,
        )
        self.client.force_login(self.residente)

        revisar = self.client.get(
            reverse(
                "finance:pago_revisar",
                args=[self.edificio.pk, pago.pk],
            )
        )
        gastos = self.client.get(
            reverse("finance:gastos_lista", args=[self.edificio.pk])
        )

        self.assertEqual(revisar.status_code, 403)
        self.assertEqual(gastos.status_code, 403)

    def test_tesorero_registra_y_confirma_gasto(self):
        self.client.force_login(self.tesorero)

        crear = self.client.post(
            reverse("finance:gasto_registrar", args=[self.edificio.pk]),
            {
                "categoria": Gasto.Categoria.MANTENIMIENTO,
                "concepto": "Reparación de bomba",
                "importe": "750.00",
                "fecha": "2026-09-15",
                "proveedor": "Servicios del Cibao",
            },
        )

        self.assertEqual(crear.status_code, 302)
        gasto = Gasto.objects.get(concepto="Reparación de bomba")
        self.assertEqual(gasto.estado, Gasto.Estado.PENDIENTE)

        confirmar = self.client.post(
            reverse(
                "finance:gasto_confirmar",
                args=[self.edificio.pk, gasto.pk],
            )
        )
        self.assertEqual(confirmar.status_code, 302)
        gasto.refresh_from_db()
        self.assertEqual(gasto.estado, Gasto.Estado.CONFIRMADO)
        self.assertEqual(gasto.confirmado_por, self.tesorero)

    def test_filtro_htmx_de_gastos_devuelve_solo_el_parcial(self):
        Gasto.objects.create(
            edificio=self.edificio,
            categoria=Gasto.Categoria.OTRO,
            concepto="Gasto pendiente visible",
            importe=Decimal("100.00"),
            fecha=timezone.localdate(),
            creado_por=self.tesorero,
        )
        self.client.force_login(self.tesorero)

        response = self.client.get(
            reverse("finance:gastos_lista", args=[self.edificio.pk]),
            {"estado": Gasto.Estado.PENDIENTE},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/partials/gastos_table.html")
        self.assertContains(response, "Gasto pendiente visible")
        self.assertContains(response, "Filtros activos")
        self.assertContains(response, "Pendiente")
        self.assertNotContains(response, "<html", html=False)

    def test_recibo_de_otro_apartamento_no_es_visible_para_residente(self):
        pago = Pago.objects.create(
            apartamento=self.otro_apartamento,
            importe_total=Decimal("100.00"),
            fecha=timezone.localdate(),
            metodo=Pago.Metodo.EFECTIVO,
            estado=Pago.Estado.CONFIRMADO,
            registrado_por=self.administrador,
            confirmado_por=self.administrador,
            fecha_confirmacion=timezone.now(),
        )
        self.client.force_login(self.residente)

        response = self.client.get(
            reverse(
                "finance:recibo_descargar",
                args=[self.edificio.pk, pago.pk],
            )
        )

        self.assertEqual(response.status_code, 404)
