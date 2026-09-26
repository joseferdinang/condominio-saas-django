from django.urls import path

from . import views

app_name = "buildings"

urlpatterns = [
    path("edificios/<int:edificio_id>/reservaciones/", views.reservaciones_lista, name="reservaciones_lista"),
    path("edificios/<int:edificio_id>/reservaciones/nueva/", views.reservacion_crear, name="reservacion_crear"),
    path("edificios/<int:edificio_id>/reservaciones/horarios/", views.reservacion_horarios, name="reservacion_horarios"),
    path("edificios/<int:edificio_id>/reservaciones/<int:reserva_id>/cancelar/", views.reservacion_cancelar, name="reservacion_cancelar"),
    path("edificios/<int:edificio_id>/zonas/nueva/", views.zona_crear, name="zona_crear"),
    path("edificios/<int:edificio_id>/zonas/<int:zona_id>/editar/", views.zona_editar, name="zona_editar"),
    path(
        "edificios/<int:edificio_id>/avisos/",
        views.avisos_lista,
        name="avisos_lista",
    ),
    path(
        "edificios/<int:edificio_id>/avisos/nuevo/",
        views.aviso_crear,
        name="aviso_crear",
    ),
    path(
        "edificios/<int:edificio_id>/avisos/<int:aviso_id>/publicar/",
        views.aviso_publicar,
        name="aviso_publicar",
    ),
    path(
        "edificios/<int:edificio_id>/avisos/<int:aviso_id>/enviar/",
        views.aviso_enviar,
        name="aviso_enviar",
    ),
]
