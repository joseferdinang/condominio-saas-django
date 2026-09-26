# Prueba de aceptación del edificio piloto

Fecha de ejecución: 18 de septiembre de 2026, zona `America/Santo_Domingo`.

Entorno: Docker Compose de producción, Django con `DEBUG=False`, PostgreSQL 17.11 y dos proyectos aislados:

- Origen: `condominio-uat-source`, base `condominio_uat`.
- Restauración: `condominio-uat-restore`, base `condominio_uat_restore`.

La prueba no utilizó ni modificó los datos del entorno de desarrollo visible en `localhost:8000`.

## Datos del escenario

- 1 edificio: Residencial Piloto UAT.
- 12 apartamentos con cuota mensual de RD$2,500.00.
- 12 propietarios y 12 relaciones activas con sus apartamentos.
- Roles: 1 administrador, 1 tesorero, 1 miembro de junta y 12 residentes.
- Las cuentas UAT se crearon con contraseña inutilizable; no se guardaron credenciales.
- Saldo inicial de caja/banco: RD$50,000.00.
- Saldo inicial por cobrar del apartamento A-12: RD$1,000.00.
- 12 cuotas del período por RD$30,000.00.
- Apartamentos al día: A-01, A-02, A-03, A-04 y A-06.
- Pago parcial: A-05 pagó RD$1,000.00 y conserva RD$1,500.00 pendiente.
- A-06 quedó al día mediante dos abonos de RD$1,500.00 y RD$1,000.00.
- Pagos confirmados: 7 movimientos por RD$13,500.00.
- Pagos pendientes de revisión: 2 movimientos por RD$3,500.00.
- Apartamentos con cuota pendiente: A-05 y A-07 a A-12; A-12 también conserva el saldo inicial de RD$1,000.00.
- Gastos confirmados con comprobantes: RD$4,000.00 de mantenimiento y RD$2,500.00 de servicios.
- 1 aviso fijado y publicado.

## Resultado de los flujos solicitados

| Paso | Prueba | Resultado | Evidencia |
|---:|---|---|---|
| 1 | Crear edificio | APROBADO | Edificio creado en PostgreSQL con ID 1. |
| 2 | Crear apartamentos y personas | APROBADO | 12 apartamentos y 12 propietarios relacionados. |
| 3 | Crear usuarios y asignar roles | APROBADO | 15 membresías: administrador, tesorero, junta y residentes. |
| 4 | Cargar saldos iniciales | APROBADO | RD$50,000.00 de caja y RD$1,000.00 por cobrar a A-12. |
| 5 | Generar cuotas | APROBADO | 12 cargos; la segunda ejecución generó 0 cargos duplicados. |
| 6 | Registrar pagos | APROBADO | 9 pagos con comprobante: 7 confirmados y 2 pendientes. |
| 7 | Aplicar abonos | APROBADO | A-05 quedó parcial y A-06 fue saldado con dos abonos. |
| 8 | Confirmar comprobantes | APROBADO | 7 confirmaciones con usuario y fecha; 2 pagos quedaron para revisión. |
| 9 | Registrar gastos | APROBADO | 2 gastos confirmados con comprobante por RD$6,500.00. |
| 10 | Generar reportes | APROBADO | 7 Excel y 7 PDF generados; todos abrieron correctamente. |
| 11 | Verificar totales | APROBADO | Conciliación y cuentas por cobrar coincidieron con la matriz esperada. |
| 12 | Crear respaldo | APROBADO | Dump PostgreSQL, medios, verificación y manifiesto con SHA-256. |
| 13 | Restaurar en base de prueba | APROBADO | Filas y huellas coinciden; se verificaron otra vez los totales y archivos. |

## Totales conciliados

| Concepto | Importe |
|---|---:|
| Saldo inicial de caja | RD$50,000.00 |
| Ingresos confirmados | RD$13,500.00 |
| Gastos confirmados | RD$6,500.00 |
| Saldo final | RD$57,000.00 |
| Cuotas emitidas | RD$30,000.00 |
| Cuotas cobradas | RD$13,500.00 |
| Cuotas pendientes del período | RD$16,500.00 |
| Saldo inicial por cobrar de A-12 | RD$1,000.00 |
| Cuentas por cobrar totales | RD$17,500.00 |
| Pagos pendientes de aprobación | RD$3,500.00 |

La conciliación de caja validada fue:

`RD$50,000.00 + RD$13,500.00 - RD$6,500.00 = RD$57,000.00`

## Reportes verificados

Cada reporte se generó en Excel y PDF e incluye edificio, período y fecha de generación:

1. Estado de cuenta por apartamento.
2. Cuentas por cobrar.
3. Cuotas cobradas y pendientes por período.
4. Gastos por categoría.
5. Resumen financiero mensual.
6. Movimientos de caja.
7. Pagos pendientes de revisión.

Los 7 libros se abrieron con `openpyxl`. Los 7 PDF se abrieron con `pypdf`; todos tienen una página. El resumen mensual también se renderizó a PNG y se revisó visualmente sin cortes, solapamientos ni datos ausentes.

## Respaldo y restauración

Respaldo verificado:

`.pilot-local/uat-backups/20260919T003244915375Z`

Contenido:

- `postgres.dump`: 103,052 bytes.
- `media.tar.gz`: 156,746 bytes.
- `verification.json`: 5,532 bytes.
- `manifest.json`: hashes SHA-256 de los tres archivos anteriores.

Después de restaurar se comprobaron en `condominio_uat_restore`:

- 12 apartamentos, 12 personas y 12 cargos.
- 7 pagos confirmados y 2 pendientes.
- 2 gastos confirmados y 1 aviso publicado.
- Saldo final RD$57,000.00.
- 7 Excel, 7 PDF, 9 comprobantes de pago y 2 comprobantes de gasto.
- Coincidencia de filas y huellas de todas las tablas y documentos.

La aplicación web restaurada permaneció detenida, como establece el procedimiento de restauración.

## Validaciones adicionales

| Validación | Resultado |
|---|---|
| Health check de `web` | APROBADO; contenedor saludable. |
| Health check a través de Caddy/HTTPS | APROBADO; `{"status":"ok","database":"ok"}`. |
| Migraciones pendientes | APROBADO; `No changes detected`. |
| Suite en configuración de pruebas | APROBADO; 87 pruebas, 0 fallos. |
| `manage.py check --deploy` | APROBADO CON OBSERVACIONES; 2 advertencias HSTS. |
| Suite ejecutada dentro de la imagen de producción | FALLIDO COMO ENTORNO DE PRUEBAS; 33 respuestas 301 por `SECURE_SSL_REDIRECT` y 1 importación fallida porque `pypdf` solo está en dependencias de desarrollo. |

La última fila no representa un fallo funcional del piloto: la misma suite pasa completa en `config.settings.test`. Sí evidencia que la imagen de producción no debe usarse directamente como ejecutor de pruebas sin sobreponer la configuración y las dependencias de pruebas.

## Hallazgos y decisiones pendientes

1. `check --deploy` informa que `SECURE_HSTS_INCLUDE_SUBDOMAINS` y `SECURE_HSTS_PRELOAD` están desactivados. Antes de habilitarlos se debe confirmar que todos los subdominios del dominio definitivo usarán HTTPS y decidir si el dominio participará en la lista de precarga HSTS.
2. Conviene documentar en CI que la suite se ejecuta con el target `development` y `config.settings.test`; ejecutar pruebas de vistas con los settings de producción fuerza redirecciones HTTPS y produce falsos negativos.
3. Los datos, comprobantes y reportes de esta prueba son sintéticos y están en volúmenes aislados. No deben promoverse a la futura base del piloto real.
4. No se detectaron diferencias de datos, archivos ni totales después de restaurar el respaldo.

## Comandos para repetir la prueba manualmente

En PowerShell, desde la raíz del proyecto y con Docker Desktop activo:

```powershell
$dockerBin = 'C:\Program Files\Docker\Docker\resources\bin'
$env:Path = "$dockerBin;$env:Path"

.\.venv\Scripts\python.exe ops\production.py `
  --env-file .pilot-local\uat-source.env `
  --secrets-dir .pilot-local\secrets `
  --project condominio-uat-source dc up -d db web caddy

curl.exe --insecure https://localhost:28443/health/

docker compose run --rm `
  -e DJANGO_SETTINGS_MODULE=config.settings.test `
  web python manage.py test --noinput
```

El respaldo y la restauración se repiten con:

```powershell
.\.venv\Scripts\python.exe ops\production.py `
  --env-file .pilot-local\uat-source.env `
  --secrets-dir .pilot-local\secrets `
  --project condominio-uat-source backup `
  --output .pilot-local\uat-backups

.\.venv\Scripts\python.exe ops\production.py `
  --env-file .pilot-local\uat-restore.env `
  --secrets-dir .pilot-local\secrets `
  --project condominio-uat-restore restore `
  .pilot-local\uat-backups\20260919T003244915375Z
```
