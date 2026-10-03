# Mi Condominio — Minimal

## Overview
Dirección aprobada: Minimal, de la comparación `portal-apariencias-web.html`.
Administradores necesitan comparar saldos, revisar comprobantes y encontrar acciones;
residentes necesitan entender su deuda, reportar pagos y leer avisos.
Priorizar estos datos sobre decoración. Aplicar `programar-con-criterio` y su
referencia de diseño sin cambiar contratos, rutas ni permisos.

## Colors
Tokens en `static/css/minimal.css`, después de `app.css`: fondo blanco, texto
`#24272b`, texto secundario `#62666d`, divisores `#e5e6e8`, menú `#f7f7f8`.
Modo oscuro: fondo `#18191b`, superficies `#1d1f22`, texto `#ededee`.
Las cuatro paletas existentes conservan sus claves y preferencias por usuario.
Usar el acento para acciones y selección; estados financieros conservan texto y color.

## Typography
Fuente del sistema para títulos y cuerpo; títulos de peso 600, sin serif decorativa.
Cifras tabulares para importes. Conservar RD$, fechas y contenido reales.

## Layout
Menú lateral neutro de 244 px, contenido con espacio de lectura y cabecera discreta.
Métricas en una franja con divisores; actividad en secciones planas. En móvil,
métricas en dos columnas y navegación existente. No ocultar acciones por estética.

## Elevation & Depth
Sin sombras en tarjetas, métricas y navegación. Sombra reservada para elementos
superpuestos como selector de edificios y panel de preferencias.

## Shapes
Radios de 6 a 10 px. Evitar grandes bloques decorativos y curvas innecesarias.

## Components
Mantener formularios, filtros HTMX, tablas, mensajes y estados vacíos existentes.
Conservar foco visible, enlaces reales, permisos y etiquetas accesibles.
`minimal.css` es una capa de presentación compartida, exclusiva de pantalla;
los recibos y exportaciones imprimibles conservan sus estilos.

## Do's and Don'ts
Usar separación y jerarquía para comparar; respetar preferencias de movimiento
reducido y de tema. No inventar métricas, datos, rutas ni acciones. Validar móvil,
escritorio, modo oscuro y teclado antes de publicar.

## Acceso al portal
El login usa la dirección aprobada de arquitectura ilustrada, aislada en
`login.css`: blanco y azul petróleo, formulario a la izquierda e ilustración
SVG original a la derecha, sin datos ficticios. No representa un edificio real.
La ilustración vive en `registration/partials/login_architecture.html`, con
tejado separado, ventanas y trazos de plano. No necesita imágenes externas.
A 700 px o menos, el formulario aparece primero y la ilustración después.
Entrada breve de contenido y tejado, dibujo de cotas y luz de ventana; las
animaciones terminan y `prefers-reduced-motion` las elimina. El hover del tejado
solo aplica a dispositivos con ratón. Se conservan foco, errores y carga.
Mostrar/ocultar contraseña es una mejora progresiva: el formulario funciona sin
JavaScript. Se conserva el login, CSRF, recuperación y redirección de Django.
La recuperación de contraseña comparte esta identidad mediante `auth_base.html`:
formulario de correo, confirmación genérica de envío, nueva contraseña y enlace
inválido conservan la misma composición. Las validaciones y tokens siguen siendo
los de Django, con errores visibles y ayuda de contraseña asociada a los campos.
