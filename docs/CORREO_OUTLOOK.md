# Correo saliente con Outlook.com

El archivo local `.env` configura Outlook.com como remitente y servidor SMTP (`smtp-mail.outlook.com`, puerto `587`, STARTTLS). No contiene la contraseña de la cuenta. `.env` está excluido de Git.

Según la [configuración oficial de Outlook.com](https://support.microsoft.com/es-es/outlook/pop-imap-and-smtp-settings-for-outlook-com), el envío SMTP requiere autenticación moderna OAuth2. El backend SMTP integrado de Django en este proyecto usa autenticación por contraseña, por lo que cambiar solo `DJANGO_EMAIL_HOST_PASSWORD` no completa la integración. No pegues la contraseña normal de Microsoft en `.env` ni en este chat.

Para habilitar Outlook.com como remitente se necesita registrar una aplicación Microsoft, conceder permisos de envío y añadir un backend OAuth2 con gestión segura de tokens. Como alternativa para el piloto, puede usarse un proveedor SMTP que admita el backend actual de Django, configurando sus credenciales solo en `.env`.

Las invitaciones fallidas no se marcan como enviadas. Cuando el correo funcione, un administrador puede reenviar una invitación pendiente desde **Usuarios → Invitar usuario** con el mismo nombre de usuario, dirección y rol.
