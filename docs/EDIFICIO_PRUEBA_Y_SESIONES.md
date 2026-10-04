# Edificio de prueba, usuarios e inactividad

## Resultado

- Cuenta existente: `jose-ferdinand`.
- Edificio de prueba · José, ID 1, identificado como DEMO.
- 12 apartamentos: 101–104, 201–204 y 301–304.
- Cuota mensual de prueba: RD$ 3,500.00; porcentajes de contribución suman 100%.
- Membresía activa con rol administrador. Se registraron 14 cambios de auditoría.
- No se crearon cargos, pagos, gastos ni saldos ficticios.

La cuenta ya era superusuario. Su membresía nueva no limita ese acceso global.
Para probar aislamiento, usar una cuenta residente asignada al apartamento y edificio.

## Administración de usuarios

En **Inicio → Mis edificios**, los administradores ven **Administrar usuarios**.
Dentro del edificio, el menú **Usuarios** abre el mismo apartado existente:
listado, búsqueda, invitaciones, edición de roles y retiro de acceso.

Retirar acceso desactiva la membresía; conserva la cuenta y el historial.
Se mantienen las protecciones de cuentas críticas, del último administrador
y de datos personales de usuarios que pertenecen a varios edificios.
Tesoreros y residentes no pueden administrar usuarios. Cambiar IDs en las
URLs no concede acceso a otro edificio.

## Sesiones

El servidor y el navegador aplican un límite de 300 segundos de inactividad.
La actividad real del teclado, ratón y pantalla táctil renueva la sesión
mediante POST protegido por CSRF. No hay renovaciones periódicas sin interacción.
La actividad se comparte entre pestañas del mismo usuario.

Al vencer, se cierra la sesión y se muestra el motivo en el login. Una petición
vencida no ejecuta la operación solicitada. HTMX redirige la página completa.
El control también se incluye en Django Admin. Las respuestas autenticadas
llevan `Cache-Control: private, no-store`.

La protección del servidor sigue funcionando sin JavaScript. El cierre visible
automático requiere JavaScript; los navegadores pueden suspender temporizadores
en segundo plano, y se vuelve a comprobar el vencimiento al regresar a la pestaña.
Recargar las pestañas existentes después del despliegue para cargar el nuevo control.

## Archivos del cambio

- `accounts/idle.py`: middleware, renovación y contexto del tiempo restante.
- `accounts/urls.py`: endpoint de actividad.
- `accounts/views.py`: edificios administrables en el inicio.
- `accounts/tests/test_idle_sessions.py`: vencimiento, CSRF, HTMX, Admin y permisos.
- `config/settings/base.py`: límite y registro del middleware/contexto.
- `static/js/session-idle.js`: actividad, pestañas y cierre automático.
- `static/css/minimal.css`: acceso directo, aviso y lista móvil.
- `templates/base.html` y `templates/accounts/partials/session_script.html`.
- `templates/admin/base_site.html`: control compartido en Django Admin.
- `templates/accounts/dashboard.html`, `usuarios_lista.html`.
- `templates/registration/login.html`: explicación del cierre.
- `.gitignore`: excluir el archivo local de credenciales.

No hay migraciones nuevas ni cambios a contraseñas o secretos.

## Comprobación manual

1. Iniciar sesión con `jose-ferdinand` en el portal de producción.
2. Abrir `/edificios/1/` y comprobar los 12 apartamentos.
3. Abrir `/edificios/1/usuarios/` o **Administrar usuarios** desde Inicio.
4. Probar invitación, edición y retiro de acceso con una cuenta de prueba.
5. Con un residente, comprobar que no aparece Usuarios y su URL devuelve denegación.
6. Abrir dos pestañas; interactuar con una y comprobar que ambas conservan la sesión.
7. Dejarlas sin interacción durante cinco minutos: deben regresar al login.
8. Intentar guardar un formulario de una sesión vencida: debe pedir iniciar sesión.

Pruebas automatizadas, usando PostgreSQL local configurado:

```powershell
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python manage.py test accounts.tests --settings=config.settings.test --noinput
```

Se verificaron escritorio a 1280 px y móvil a 360 px con Playwright en un
servidor local aislado. El vencimiento del navegador se probó adelantando su
reloj, y el del servidor con tiempo controlado en las pruebas de integración.
La asignación en Neon se comprobó con consultas reales; la validación visual
autenticada no utiliza la contraseña de producción.
