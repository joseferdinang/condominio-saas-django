# Piloto controlado: despliegue manual

Destino previsto: DigitalOcean Basic, 2 GB RAM, NYC3, Ubuntu 24.04 LTS x86_64.
La creación del VPS, dominio, DNS, firewall, SMTP y almacenamiento externo se
hace manualmente. Este proyecto no contrata ni aprovisiona servicios.

## 1. Arquitectura y condiciones del piloto

- Caddy es el único servicio publicado: TCP 80 y 443. PostgreSQL y Gunicorn no
  publican puertos al host. Los documentos nunca se sirven desde `/media/`.
- Gunicorn: dos procesos, límite de 768 MB. PostgreSQL: 512 MB, 40 conexiones,
  `shared_buffers=128MB`. Caddy: 128 MB. Estos límites son un punto de partida,
  no una prueba de capacidad de un VPS real. Los PDF simultáneos requieren
  seguimiento de memoria. El contenedor de mantenimiento usa hasta 512 MB.
- Django corre como UID 10001, con raíz de solo lectura, sin capacidades Linux,
  y solo puede escribir documentos, estáticos y temporales.
- Python, PostgreSQL y Caddy tienen imágenes fijadas por digest. Para actualizar
  esas bases hay que cambiar el digest y repetir las pruebas. Conservar también
  la imagen final de cada versión: los paquetes Debian/transitivos pueden cambiar
  al reconstruir en otra fecha.
- El compose de producción es independiente de `compose.yaml`. Nunca mezclar
  ambos. Todas las operaciones siguientes usan `ops/production.py`.
- La creación inicial no carga datos ficticios, usuarios ni contraseñas.

## 2. Crear y preparar el VPS manualmente

En el panel de DigitalOcean elegir Ubuntu 24.04 LTS, NYC3, Basic de 2 GB y clave
SSH. Confirmar disponibilidad y precio en el panel antes de contratar. Configurar
un Cloud Firewall: SSH 22 solo desde tu IP; TCP 80 y 443 para el portal y ACME.
No abrir 5432 ni 8000. Si limitas 443 a las IP del piloto, mantener el desafío
HTTP de ACME accesible en 80. No depender solo de UFW para puertos de Docker.

Crear un registro DNS A del dominio hacia el VPS. Crear AAAA únicamente si IPv6
está configurado y accesible. Los certificados públicos requieren DNS correcto
y conectividad entrante/saliente. No hay certificados públicos preinstalados.

Conectarse por SSH y verificar la huella del servidor:

```bash
ssh root@IP_DEL_VPS
timedatectl set-timezone America/Santo_Domingo
apt-get update
apt-get install -y ca-certificates curl python3 cron logrotate
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.sources
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker cron
docker version
docker compose version
install -d -m 0755 /opt/condominio
```

Esta receta supone un VPS nuevo sin una instalación Docker anterior. Aplicar
actualizaciones del sistema en una ventana de mantenimiento y verificar si se
requiere reinicio; no hay actualizaciones destructivas automáticas.

## 3. Transferir el código sin datos ni secretos

Desde PowerShell en la carpeta del proyecto, preparar un archivo de código:

```powershell
tar -czf "$env:TEMP/condominio-piloto.tar.gz" --exclude=.venv --exclude=.git --exclude=.env --exclude=.env.production --exclude=.secrets --exclude=.pilot-local --exclude=.ops-locks --exclude=backups --exclude=media --exclude=staticfiles --exclude=__pycache__ --exclude=outputs --exclude=work .
scp "$env:TEMP/condominio-piloto.tar.gz" root@IP_DEL_VPS:/opt/condominio-piloto.tar.gz
```

Revisar antes `tar -tzf "$env:TEMP/condominio-piloto.tar.gz"`: no debe contener
credenciales, volcados, documentos ni otros `.env` privados que hayas creado.
En el primer despliegue, con `/opt/condominio` vacío:

```bash
tar -xzf /opt/condominio-piloto.tar.gz -C /opt/condominio
cd /opt/condominio
umask 077
cp --no-clobber .env.production.example .env.production
chmod 600 .env.production
nano .env.production
python3 ops/production.py init-secrets
```

Editar dominio, correo ACME, hosts Django, origen HTTPS exacto y SMTP. Usar
`https://tu-dominio` en CSRF, sin rutas ni barra final. No usar `*` en hosts.
En producción `DEBUG=False`, HTTPS y cookies seguras son obligatorios aunque
alguien establezca `DJANGO_DEBUG=true`. Una SECRET_KEY corta, un comodín de host
o un origen CSRF HTTP impiden el arranque.

`init-secrets` genera valores aleatorios y no los imprime. Se guardan en
`.secrets/` (directorio 0700; archivos 0444, inaccesibles a otros usuarios a través
del directorio). Docker los monta de solo lectura para UID 10001. No se incluyen
en el contexto de construcción ni en Git. En Windows se usa el ACL del usuario
y no el atributo de solo lectura para compatibilidad con Docker Desktop.
El comando se niega a reemplazar secretos existentes.

Guardar una copia cifrada de `.env.production` y `.secrets` fuera del VPS.
El respaldo normal no los incluye. Cambiar el archivo de contraseña PostgreSQL
no cambia la contraseña de un clúster ya inicializado: una rotación exige un
procedimiento explícito. Conservar la SECRET_KEY al recuperar para mantener
firmas y sesiones; la nueva clave invalida las firmas anteriores.

## 4. Primera puesta en marcha y migraciones

Desde `/opt/condominio`:

```bash
python3 ops/production.py dc config --quiet
python3 ops/production.py dc build web
python3 ops/production.py dc up --detach --wait db
python3 ops/production.py dc run --rm --no-deps -T maintenance python manage.py migrate --plan
python3 ops/production.py dc run --rm --no-deps -T maintenance python manage.py migrate --noinput
python3 ops/production.py dc run --rm --no-deps -T maintenance python manage.py collectstatic --noinput
python3 ops/production.py dc run --rm --no-deps -T maintenance python manage.py check --deploy --fail-level ERROR
python3 ops/production.py dc run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
python3 ops/production.py dc run --rm --no-deps maintenance python manage.py createsuperuser
python3 ops/production.py dc up --detach --wait web caddy
python3 ops/production.py dc ps
python3 ops/smoke_https.py https://TU_DOMINIO
```

`createsuperuser` pide usuario, correo y contraseña por terminal. No usar
`admin/admin`, parámetros con la contraseña, ni reutilizar usuarios de desarrollo.
El superusuario es una cuenta técnica: crear membresías de edificio y cuentas
de uso diario con los roles existentes desde Admin. No ejecutar `seed_demo`.

`check --deploy` conserva dos avisos deliberados: W005 y W021. HSTS se limita a
3600 segundos y al host actual; no se incluyen subdominios ni preload sin revisar
primero todos los dominios. No se silencian esas advertencias.

El smoke test verifica TLS, PostgreSQL, cabeceras, cookie CSRF Secure, estáticos
solicitados realmente por el HTML, denegación de `/media/`, CSRF y límite de carga.
No deshabilitar la verificación TLS en el VPS. Revisar también login/logout,
permisos de dos edificios, un PDF y un Excel con tus usuarios piloto.

## 5. Archivos y correo

Los formularios de comprobantes aceptan PDF/PNG/JPG hasta 5 MB con comprobación
de firma. Caddy y Django limitan el cuerpo completo a 6 MB; Django limita un
archivo por solicitud y pasa a disco temporal a partir de 1 MB. El rechazo HTTP
es 413 para un cuerpo declarado mayor de 6 MB. Los documentos viven en el volumen
`media`, con permisos privados, y solo se descargan tras autorización Django.

El correo de producción utiliza SMTP. Configurar remitente verificado,
`DJANGO_EMAIL_HOST`, puerto, usuario, contraseña y TLS o SSL, nunca ambos. No
activar un backend de consola en producción. Validar un envío con un destinatario
de prueba autorizado y la recuperación de contraseña antes de invitar residentes.
Este trabajo no envía correos reales ni comprueba entrega SMTP externa.

## 6. Cron y logs

El mes se calcula en `America/Santo_Domingo` dentro de Django, incluso si el host
tiene otra zona. Un vencimiento 31 se reduce al último día en meses más cortos.

```bash
python3 ops/production.py cuotas --edificio 1 --usuario USUARIO_FINANCIERO --dia-vencimiento 10
python3 ops/production.py cuotas --edificio 1 --usuario USUARIO_FINANCIERO --dia-vencimiento 10
```

La segunda ejecución debe crear cero cargos adicionales. El usuario debe tener
permisos financieros para ese edificio. Mantener el mismo día de vencimiento;
un cambio sobre un período existente falla explícitamente. Para recuperar un
mes anterior usar el comando original con año, mes y fecha explícitos.

Revisar `deploy/cron.example`, sustituir usuario/edificio, añadir una línea por
edificio autorizado y luego instalar manualmente:

```bash
install -m 0644 deploy/cron.example /etc/cron.d/condominio
install -m 0644 deploy/logrotate.example /etc/logrotate.d/condominio
systemctl is-active cron
```

El trabajo diario de cuotas actúa como reintento de la generación mensual
idempotente. El backup corre a las 03:10. Ambos comparten un bloqueo por proyecto:
si otra operación está activa, el segundo proceso falla y queda en el log. No
ejecutar escrituras manuales fuera de este flujo durante el respaldo.

```bash
python3 ops/production.py dc logs --tail 100 web caddy db
tail -n 50 /var/log/condominio-cuotas.log /var/log/condominio-backup.log
docker stats --no-stream
df -h
```

Docker rota logs a 3 archivos de 10 MB por contenedor. Gunicorn evita registrar
URLs/tokens/cookies; Caddy omite URI y cabeceras de los logs de acceso. Los logs
de errores pueden contener contexto operativo: tratarlos como privados. Los logs
de cron rotan semanalmente con ocho copias. Revisar cada mañana fallos de jobs,
disco, memoria y antigüedad del último respaldo; no hay alertas externas configuradas.

## 7. Respaldo coherente y copia fuera del VPS

```bash
python3 ops/production.py backup
```

El comando detiene brevemente Gunicorn, espera las solicitudes en curso, genera
un `pg_dump -Fc`, archiva todos los comprobantes/documentos y calcula huellas de
cada tabla y archivo. Luego reinicia Gunicorn aunque falle el respaldo. Caddy
puede responder 502 durante esa ventana; programarla fuera de uso del piloto.

Cada carpeta `backups/FECHA_UTC/` contiene `postgres.dump`, `media.tar.gz`,
`verification.json` y `manifest.json` con SHA-256. Solo se considera completo si
existe el manifest final. Las carpetas incompletas se conservan para investigar.
La verificación compara todos los datos, incluidas tablas intermedias, auditoría
y migraciones. El respaldo no borra archivos ni aplica retención automática.

Objetivo provisional con cron diario: RPO hasta 24 horas. El RTO se debe medir
con un respaldo del tamaño real del piloto. Mantener al menos 7 diarios y 4
semanales fuera del VPS; revisar espacio y archivar las copias antiguas de forma
manual, sin automatizar borrados en esta versión.

Un backup en el mismo VPS no cubre la pérdida del servidor. Transferirlo a un
equipo/almacenamiento bajo tu control; contiene información personal/financiera
y requiere almacenamiento cifrado. Ejemplo desde una máquina de confianza:

```bash
scp -r root@IP_DEL_VPS:/opt/condominio/backups/FECHA_UTC ./respaldo-condominio-FECHA_UTC
```

Conservar por separado los secretos cifrados y el archivo de código de la versión.
Guardar la imagen probada para poder restaurar exactamente la misma versión:

```bash
docker image save condominio-pilot:local -o /opt/condominio-pilot-image.tar
```

No publicar esos respaldos ni incorporarlos al repositorio. No se ha contratado
almacenamiento externo ni configurado una transferencia automática.

## 8. Restauración sin sobrescribir el origen

Requiere el código/imagen de la misma versión del respaldo, PostgreSQL 17, el
respaldo completo y los secretos correspondientes. Se restaura en un **nombre de
proyecto nuevo**, que crea volúmenes independientes. No ejecutar migraciones
antes de restaurar: la base de destino debe estar vacía.

En el mismo VPS se puede verificar el destino sin abrir otro puerto:

```bash
cd /opt/condominio
python3 ops/production.py --project condominio-recuperado restore /opt/condominio/backups/FECHA_UTC
python3 ops/production.py --project condominio-recuperado dc run --rm --no-deps -T maintenance python manage.py check --deploy --fail-level ERROR
python3 ops/production.py --project condominio-recuperado dc run --rm --no-deps -T maintenance python manage.py migrate --plan
python3 ops/production.py --project condominio-recuperado dc run --rm --no-deps -T maintenance python manage.py migrate --noinput
python3 ops/production.py --project condominio-recuperado dc run --rm --no-deps -T maintenance python manage.py collectstatic --noinput
```

La restauración comprueba SHA-256, rechaza rutas peligrosas/enlaces, rechaza
destinos con tablas o archivos, usa una transacción PostgreSQL y compara todas
las huellas recuperadas. No usa `DROP`, `--clean` ni elimina volúmenes. Si falla,
web queda detenido; conservar ese destino para investigar y elegir otro nombre
vacío para reintentar. Si un volumen de PostgreSQL falla, no se modifica el original.

La salida de éxito es `Restauración verificada...`. Antes de recuperar el servicio,
revisar los datos y acordar la ventana de cambio. En el mismo VPS:

```bash
# Primero pausar manualmente las líneas de /etc/cron.d/condominio.
python3 ops/production.py dc stop web caddy
python3 ops/production.py --project condominio-recuperado dc up --detach --wait web caddy
python3 ops/smoke_https.py https://TU_DOMINIO
```

Actualizar cron para incluir `--project condominio-recuperado` en cuotas y backup
antes de reactivarlo. El origen permanece intacto. Si necesitas revertir el
cambio de servicio, detener web/caddy del recuperado y arrancar web/caddy del
origen. No permitir escrituras en ambos a la vez. Un Caddy nuevo puede emitir un
certificado nuevo; conservar sus volúmenes persistentes para evitar emisiones
repetidas. Sus certificados son renovables y no forman parte del backup de negocio.

## 9. Actualizaciones de la aplicación

1. Pausar cron en una ventana de mantenimiento; preparar el nuevo código y
   conservar la imagen anterior con otra etiqueta. Nunca sobrescribir secretos.
2. Ejecutar backup y verificar su manifest. Detener web; revisar `migrate --plan`.
3. Construir la nueva imagen. Ejecutar `migrate`, `collectstatic` y `check --deploy`
   mediante maintenance. Si hay error, mantener web detenido e investigar.
4. Ejecutar `dc up --detach --wait web caddy`, smoke test y reactivar cron.
5. No revertir migraciones automáticamente. Para una recuperación con datos,
   usar el respaldo en un proyecto nuevo con la imagen anterior.

## 10. Referencias verificadas

- [Instalación oficial de Docker en Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Checklist de despliegue Django 5.2](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
- [HTTPS automático de Caddy](https://caddyserver.com/docs/automatic-https).
- [pg_restore de PostgreSQL 17](https://www.postgresql.org/docs/17/app-pgrestore.html).
- [Disponibilidad de Droplets por región](https://docs.digitalocean.com/products/droplets/details/availability/).
