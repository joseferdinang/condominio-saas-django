# Vista previa en Vercel

Vercel detecta Django por `manage.py`, usa la aplicación WSGI configurada y publica los estáticos recopilados por `collectstatic`. La raíz del proyecto debe conservar `manage.py`, `requirements.txt` y `.python-version`.

El `requirements.txt` de la raíz declara las dependencias explícitamente porque el parser de Vercel no resolvió las referencias anidadas. Mantén sus versiones alineadas con `requirements/base.txt` y `requirements/production.txt`.

## Despliegue verificado

- Portal: https://condominio-saas-django.vercel.app/
- Proyecto Vercel: `condominio-saas-django`, equipo `projects-bc21`.
- Rama de producción: `codex/rediseno-ui`; `main` no se modificó.
- Neon: proyecto `Condominios`, rama `production`, base `CondominioDB`.
- Rol exclusivo de la aplicación: `condominio_app`; sin privilegios de administración de roles.
- Variables sensibles limitadas a Production, sin credenciales de producción en Preview.
- Migraciones aplicadas; `/health/` devuelve `200` y `database: ok`.
- Carga y lectura reales verificadas en el bucket privado. Archivo técnico: `media/verification/deployment-check.txt`.
- Login público responde `200`; HSTS y `X-Frame-Options: DENY` verificados.

La base está preparada sin edificios ni usuarios ficticios. Estas verificaciones no sustituyen una aceptación completa con usuarios y operaciones del edificio piloto.

## Crear el administrador inicial

En PowerShell, dentro de la carpeta del proyecto, copia desde Neon la URL PostgreSQL de `CondominioDB`. No la publiques ni la guardes en Git. Este comando usa las credenciales solo en el proceso local; no cambia el modo de producción del sitio.

```powershell
$neonConnection = Read-Host 'URL PostgreSQL de CondominioDB' -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new('', $neonConnection).Password
$env:DJANGO_SETTINGS_MODULE = 'config.settings.development'
.venv\Scripts\python.exe manage.py createsuperuser --username admin
Remove-Item Env:DATABASE_URL
Remove-Item Env:DJANGO_SETTINGS_MODULE
```

El comando solicita correo y contraseña de manera interactiva. Después entra en `/admin/`, crea el edificio real y asigna los roles del portal. No reutilices las contraseñas de demostración.

## Rotar la clave Django

La clave del despliegue es nueva y aleatoria; no es necesario cambiarla inmediatamente por completar la instalación. Rótala si se expone o como parte de tu política de seguridad.

1. Genera una clave nueva localmente: `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"`.
2. En Vercel, abre el proyecto → Environment Variables → `DJANGO_SECRET_KEY` → Edit.
3. Sustituye el valor para Production y guarda. No lo pegues en chats ni Git.
4. En Deployments, vuelve a desplegar la última versión de `codex/rediseno-ui` a Production.
5. Comprueba `/health/` y el inicio de sesión. La rotación invalida las sesiones y firmas anteriores; los usuarios deben iniciar sesión nuevamente.

## Pendientes antes del piloto

- Crear el administrador y los datos reales del edificio.
- Configurar y verificar entrega real de correo en Production; el backend local de consola no entrega invitaciones.
- Verificar PDF en el runtime Vercel: WeasyPrint necesita bibliotecas nativas. La suite local tuvo 7 errores de PDF por faltar `libgobject-2.0-0` en Windows; las otras 130 pruebas pasaron.
- Ejecutar aceptación autenticada de permisos, recibos, reportes y comprobantes desde el sitio desplegado.
- Adaptar y probar los respaldos/restauración de PostgreSQL y Object Storage, y la ejecución mensual de cuotas, para este alojamiento.
- Revisar los límites de cargas de Vercel y la política del plan antes de recibir archivos y operar comercialmente.

## Variables por entorno

Para cada entorno de Vercel, configura los valores en Project Settings → Environment Variables. No los guardes en Git ni los pegues en chats.

- `DJANGO_SETTINGS_MODULE=config.settings.production`
- `DJANGO_SECRET_KEY`: una clave aleatoria exclusiva de este despliegue, de al menos 50 caracteres.
- `DJANGO_ALLOWED_HOSTS`: el hostname exacto `*.vercel.app` no pasa la validación estricta actual; configura el hostname exacto asignado al proyecto.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origen HTTPS exacto del hostname.
- `DATABASE_URL`: URL PostgreSQL de la rama Neon prevista para este entorno, con `sslmode=require`. Usa el hostname pooled para el tráfico de la aplicación.
- `OBJECT_STORAGE_BACKEND=s3`
- `AWS_STORAGE_BUCKET_NAME=condominio-comprobantes`
- `AWS_ACCESS_KEY_ID`: ID completo de una credencial Neon de Object Storage limitada a `storage:read` y `storage:write` para `production`.
- `AWS_SECRET_ACCESS_KEY`: secreto S3 asociado a esa credencial.
- `AWS_ENDPOINT_URL_S3`: endpoint S3 de la rama `production` en Neon.
- `AWS_REGION=us-east-2`

No apuntes un despliegue de prueba a datos reales del condominio. Usa una rama de prueba de Neon y aplica sus migraciones de forma controlada.

## Requisitos antes de una vista previa funcional

En Docker, los comprobantes se guardan localmente. En Vercel, establece `OBJECT_STORAGE_BACKEND=s3` para usar el bucket privado `condominio-comprobantes` de Neon Object Storage. La aplicación entrega los archivos por vistas autenticadas, así que conserva `querystring_auth` y no hagas el bucket público. La credencial debe estar limitada a `storage:read` y `storage:write` en la rama `production`; introdúcela en las variables cifradas de Vercel y nunca en Git. El bucket ya está creado en Condominios/production. Vigila el límite de almacenamiento del plan.

Los reportes PDF usan WeasyPrint, que requiere bibliotecas nativas incluidas en el Dockerfile pero no garantizadas en el runtime Python administrado de Vercel. Verifica la generación real de PDF en Vercel antes de habilitar esa función para el piloto; si no funciona, el despliegue apto para producción debe permanecer en el VPS con Docker/Caddy o se debe separar la generación PDF en otro servicio.

No ejecutes `migrate` desde el build de Vercel. Después de configurar la base de prueba, ejecuta las migraciones desde un proceso controlado y valida `/health/`, inicio de sesión, aislamiento entre edificios, comprobantes y Excel/PDF.
