from django.urls import path

from . import views
from . import report_views

app_name = "finance"

urlpatterns = [
    path(
        "edificios/<int:edificio_id>/reportes/",
        report_views.reportes_index,
        name="reportes_index",
    ),
    path(
        "edificios/<int:edificio_id>/reportes/exportar/",
        report_views.reporte_exportar,
        name="reporte_exportar",
    ),
    path(
        "edificios/<int:edificio_id>/apartamentos/",
        views.apartamentos_lista,
        name="apartamentos_lista",
    ),
    path(
        "edificios/<int:edificio_id>/apartamentos/nuevo/",
        views.apartamento_crear,
        name="apartamento_crear",
    ),
    path(
        "edificios/<int:edificio_id>/apartamentos/<int:apartamento_id>/editar/",
        views.apartamento_editar,
        name="apartamento_editar",
    ),
    path(
        "edificios/<int:edificio_id>/apartamentos/<int:apartamento_id>/estado/",
        views.apartamento_cambiar_estado,
        name="apartamento_cambiar_estado",
    ),
    path(
        "edificios/<int:edificio_id>/apartamentos/<int:apartamento_id>/pagos/nuevo/",
        views.pago_registrar,
        name="pago_registrar",
    ),
    path(
        "edificios/<int:edificio_id>/pagos/<int:pago_id>/revisar/",
        views.pago_revisar,
        name="pago_revisar",
    ),
    path(
        "edificios/<int:edificio_id>/pagos/<int:pago_id>/recibo/",
        views.recibo_descargar,
        name="recibo_descargar",
    ),
    path(
        "edificios/<int:edificio_id>/pagos/<int:pago_id>/comprobante/",
        views.pago_comprobante,
        name="pago_comprobante",
    ),
    path(
        "edificios/<int:edificio_id>/gastos/",
        views.gastos_lista,
        name="gastos_lista",
    ),
    path(
        "edificios/<int:edificio_id>/gastos/nuevo/",
        views.gasto_registrar,
        name="gasto_registrar",
    ),
    path(
        "edificios/<int:edificio_id>/gastos/<int:gasto_id>/confirmar/",
        views.gasto_confirmar,
        name="gasto_confirmar",
    ),
    path(
        "edificios/<int:edificio_id>/gastos/<int:gasto_id>/comprobante/",
        views.gasto_comprobante,
        name="gasto_comprobante",
    ),
]
