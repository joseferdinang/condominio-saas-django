# Portal de administración de condominios

Portal SaaS para condominios pequeños de Santiago de los Caballeros construido
con Django, PostgreSQL, templates y HTMX. Incluye aislamiento por edificio,
personas y apartamentos, operaciones financieras y las pantallas web del MVP.

## Requisitos

- Docker con el complemento Compose.
- Puertos 8000 y 5432 disponibles, o valores alternativos en `.env`.

## Inicio rápido

En PowerShell:

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up --detach
docker compose ps
Invoke-RestMethod http://localhost:8000/health/
```

El contenedor `web` aplica las migraciones antes de iniciar el servidor de
desarrollo. El endpoint responde con `status=ok` y `database=ok` solo cuando
Django puede ejecutar una consulta real en PostgreSQL.

## Comandos de desarrollo

```powershell
# Aplicar migraciones
docker compose exec web python manage.py migrate

# Crear migraciones futuras
docker compose exec web python manage.py makemigrations

# Verificar la configuración
docker compose exec web python manage.py check

# Ejecutar las pruebas en PostgreSQL
docker compose exec web python manage.py test --settings=config.settings.test

# Confirmar directamente la conexión y versión de PostgreSQL
docker compose exec db psql --username=condominio --dbname=condominio --command="SELECT current_database(), current_user, version();"

# Ver logs
docker compose logs --follow web

# Detener los servicios sin borrar los datos
docker compose down
```

## Datos ficticios y Django Admin

El comando de demostración es idempotente: crea un edificio de Santiago con 12
apartamentos, 12 propietarios, 3 inquilinos y un usuario vinculado al edificio.
El usuario `admin_demo` se crea con una contraseña inutilizable y no concede
acceso técnico a Django Admin.

```powershell
docker compose exec web python manage.py seed_demo
```

Para acceder a Django Admin, crea un superusuario técnico separado y visita
`http://localhost:8000/admin/`:

```powershell
docker compose exec web python manage.py createsuperuser
```

## Acceso al portal

El portal está disponible en `http://localhost:8000/`. Incluye inicio y cierre
de sesión, cambio y recuperación de contraseña, selección de edificios y acceso
a apartamentos según el rol. Un administrador de edificio puede invitar
usuarios desde la página de su edificio; las cuentas nuevas reciben un enlace
para establecer su contraseña. En desarrollo, el correo se imprime en los logs:

```powershell
docker compose logs --follow web
```

Los administradores y tesoreros tienen permisos financieros; los residentes
solo consultan los apartamentos vinculados a su persona y con acceso al estado
de cuenta habilitado.

## Pantallas del MVP

Desde la página de cada edificio:

- El administrador y el tesorero consultan cuotas, apartamentos al día o
  pendientes, pagos por revisar, gastos del mes, saldo disponible y movimientos
  recientes.
- El listado de apartamentos admite búsqueda y filtros por período y estado.
- Los pagos pendientes se distribuyen entre cargos y se confirman o rechazan
  con trazabilidad.
- Los gastos se registran, filtran y confirman desde el portal.
- El residente consulta su saldo, cargos, pagos y avisos; puede cargar un
  comprobante y descargar el recibo de un pago confirmado.

Los filtros y formularios usan HTMX, pero también funcionan como formularios
HTTP tradicionales. Los comprobantes se validan como PDF, PNG o JPG, con un
límite de 5 MB, y se descargan mediante vistas autenticadas con aislamiento por
edificio.

## Reportes y avisos

La página **Reportes** exporta a Excel y PDF el estado de cuenta, cuentas por
cobrar, cuotas del período, gastos por categoría, resumen mensual, movimientos
de caja y pagos pendientes. Cada archivo muestra edificio, período, fecha de
generación y totales conciliados. Los residentes solo pueden generar el estado
de cuenta de sus apartamentos autorizados.

Los administradores publican avisos desde la página **Avisos** y luego ejecutan
el envío por correo de forma explícita. Cada destinatario conserva estado,
fecha, número de intentos y el error del último fallo; un envío exitoso no se
repite. En desarrollo, los mensajes aparecen en los logs. Para producción,
configura `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, las credenciales SMTP y uno
de `DJANGO_EMAIL_USE_TLS` o `DJANGO_EMAIL_USE_SSL` en el archivo `.env`.

## Bitácora de cambios

En Django Admin, **Auditoría → Cambios** muestra fecha, usuario, edificio, acción
y objeto de los cambios realizados desde el portal, el Admin y los servicios
financieros. Un administrador ve únicamente los registros de su edificio; el
superusuario técnico puede verlos todos. La bitácora no se puede editar ni
eliminar desde Admin. Empieza a registrar cambios después de aplicar la
migración `core.0001_initial`; no reconstruye operaciones anteriores. Los
procesos sin un usuario identificado quedan registrados como «Sistema».

## Módulo financiero

La generación mensual de cuotas es idempotente y se ejecuta con un usuario que
sea administrador o tesorero del edificio:

```powershell
docker compose exec web python manage.py generar_cuotas --edificio 1 --anio 2026 --mes 9 --fecha-vencimiento 2026-09-10 --usuario admin
```

Pagos, aplicaciones, gastos, saldos iniciales y períodos quedan disponibles en
Django Admin. Los pagos pendientes pueden distribuirse entre varios cargos y se
confirman mediante la acción «Confirmar pagos seleccionados». Los movimientos
confirmados no se eliminan; se anulan mediante los servicios financieros para
conservar usuario, fecha y motivo.

En Linux o macOS, el `Makefile` ofrece los atajos `make build`, `make up`,
`make migrate`, `make check`, `make test`, `make logs` y `make down`.

## Entornos

- `config.settings.development`: servidor local, depuración configurable y
  correo en consola.
- `config.settings.test`: pruebas contra PostgreSQL con un hasher rápido.
- `config.settings.production`: depuración desactivada, cookies seguras,
  redirección HTTPS, HSTS configurable y archivos estáticos versionados.

Producción exige `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` y
`POSTGRES_PASSWORD`. Debe ejecutarse detrás de Caddy o de otro proxy HTTPS que
envíe `X-Forwarded-Proto`. Los valores de `.env.example` son exclusivamente de
desarrollo y no deben reutilizarse en el VPS.

## Piloto controlado en producción

El despliegue manual en un VPS Ubuntu con 2 GB está documentado en
[docs/PILOTO_PRODUCCION.md](docs/PILOTO_PRODUCCION.md). Usa el compose independiente
`compose.production.yaml`, Gunicorn, Caddy y secretos montados desde archivos.
`ops/production.py` incluye respaldo coherente de PostgreSQL/documentos y
restauración verificada exclusivamente sobre destinos vacíos. No se aprovisiona
infraestructura ni se incorporan credenciales de producción.
