# Vista previa en Vercel

Vercel detecta Django por `manage.py`, usa la aplicación WSGI configurada y publica los estáticos recopilados por `collectstatic`. La raíz del proyecto debe conservar `manage.py`, `requirements.txt` y `.python-version`.

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
