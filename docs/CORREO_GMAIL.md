# Correo SMTP para la vista previa

Esta guía aplica si decides usar Gmail como proveedor SMTP. La configuración local actual puede usar otro proveedor; comprueba `.env` antes de seguirla. `.env` está excluido de Git. El entorno de desarrollo usa SMTP cuando `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`; sin esa variable sigue usando correo de consola. La vista previa y producción usan SMTP.

Para que Gmail permita el envío, activa la verificación en dos pasos y crea una [contraseña de aplicación](https://support.google.com/accounts/answer/185833?hl=es). Escríbela **solo** en `DJANGO_EMAIL_HOST_PASSWORD` dentro del archivo local `.env`; no uses la contraseña normal de Google ni publiques ese archivo. Si Google no ofrece contraseñas de aplicación para la cuenta, se necesita otro proveedor SMTP o una integración OAuth posterior.

Después de guardar `.env`, desde la carpeta del proyecto ejecuta:

```powershell
docker compose -f compose.yaml -f compose.preview.yaml up -d --no-deps --force-recreate web
docker compose -f compose.yaml -f compose.preview.yaml exec web python manage.py check
```

Para comprobar el correo con tu propia dirección, cuando la contraseña de aplicación ya esté configurada:

```powershell
docker compose -f compose.yaml -f compose.preview.yaml exec web python manage.py sendtestemail TU_CORREO@GMAIL.COM
```

Una invitación que falló antes de esta configuración puede reenviarse desde **Usuarios → Invitar usuario** con el mismo nombre de usuario, correo y rol, siempre que esa cuenta aún no haya iniciado sesión. El portal mostrará un error y no guardará cambios si el SMTP falla.
