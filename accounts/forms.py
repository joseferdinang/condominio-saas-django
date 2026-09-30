import secrets

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction

from .models import UsuarioEdificio


class InvitacionUsuarioForm(forms.Form):
    username = forms.CharField(
        label="Nombre de usuario",
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    first_name = forms.CharField(
        label="Nombre",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        label="Apellido",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )
    rol = forms.ChoiceField(label="Rol")

    def __init__(
        self,
        *args,
        edificio,
        permitir_administrador=False,
        permitir_usuarios_criticos=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        roles = [
            (UsuarioEdificio.Rol.TESORERO, "Tesorero"),
            (UsuarioEdificio.Rol.JUNTA, "Miembro de junta"),
            (UsuarioEdificio.Rol.RESIDENTE, "Residente"),
        ]
        if permitir_administrador:
            roles.insert(
                0,
                (UsuarioEdificio.Rol.ADMINISTRADOR, "Administrador"),
            )
        self.fields["rol"].choices = roles
        self.edificio = edificio
        self.permitir_usuarios_criticos = permitir_usuarios_criticos
        self.usuario_existente = None
        self.reenviar_existente = False

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        self.usuario_existente = (
            get_user_model().objects.filter(username__iexact=username).first()
        )
        return username

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        email = cleaned_data.get("email")
        if not username or not email:
            return cleaned_data

        user_model = get_user_model()
        usuario = self.usuario_existente
        email_owner = user_model.objects.filter(email__iexact=email).first()
        if email_owner and email_owner != usuario:
            raise forms.ValidationError(
                "Ya existe una cuenta con ese correo electrónico."
            )
        if usuario and usuario.email.strip().lower() != email:
            raise forms.ValidationError(
                "El usuario existente no coincide con el correo indicado."
            )
        if usuario and not usuario.is_active:
            raise forms.ValidationError(
                "La cuenta existente está inactiva y debe ser revisada."
            )
        if (
            usuario
            and (usuario.is_staff or usuario.is_superuser)
            and not self.permitir_usuarios_criticos
        ):
            raise forms.ValidationError(
                "Las cuentas técnicas solo pueden ser gestionadas por un superusuario."
            )
        if usuario:
            membresia = UsuarioEdificio.objects.filter(
                usuario=usuario,
                edificio=self.edificio,
            ).first()
            if membresia:
                if (
                    membresia.activo
                    and membresia.rol == cleaned_data.get("rol")
                    and usuario.last_login is None
                ):
                    self.reenviar_existente = True
                else:
                    raise forms.ValidationError(
                        "Ese usuario ya pertenece a este edificio."
                    )
        return cleaned_data

    @transaction.atomic
    def save(self):
        user_model = get_user_model()
        usuario = self.usuario_existente
        creado = usuario is None
        if creado:
            usuario = user_model.objects.create_user(
                username=self.cleaned_data["username"],
                email=self.cleaned_data["email"],
                first_name=self.cleaned_data["first_name"].strip(),
                last_name=self.cleaned_data["last_name"].strip(),
                password=secrets.token_urlsafe(32),
            )
        if not self.reenviar_existente:
            UsuarioEdificio.objects.create(
                usuario=usuario,
                edificio=self.edificio,
                rol=self.cleaned_data["rol"],
            )
        if self.cleaned_data["rol"] in {
            UsuarioEdificio.Rol.ADMINISTRADOR,
            UsuarioEdificio.Rol.TESORERO,
        } and not usuario.is_staff:
            usuario.is_staff = True
            usuario.save(update_fields=["is_staff"])
        return usuario, creado or self.reenviar_existente


class EditarUsuarioEdificioForm(forms.Form):
    first_name = forms.CharField(label="Nombre", max_length=150, required=False)
    last_name = forms.CharField(label="Apellido", max_length=150, required=False)
    email = forms.EmailField(label="Correo electrónico", required=False)
    rol = forms.ChoiceField(label="Rol")
    activo = forms.BooleanField(label="Acceso activo", required=False)

    def __init__(self, *args, membresia, editor, **kwargs):
        self.membresia = membresia
        self.editar_datos = not UsuarioEdificio.objects.filter(
            usuario=membresia.usuario
        ).exclude(edificio=membresia.edificio).exists()
        kwargs.setdefault(
            "initial",
            {
                "first_name": membresia.usuario.first_name,
                "last_name": membresia.usuario.last_name,
                "email": membresia.usuario.email,
                "rol": membresia.rol,
                "activo": membresia.activo,
            },
        )
        super().__init__(*args, **kwargs)
        self.fields["rol"].choices = [
            choice for choice in UsuarioEdificio.Rol.choices
            if editor.is_superuser or choice[0] != UsuarioEdificio.Rol.ADMINISTRADOR
        ]
        if not self.editar_datos:
            for nombre in ("first_name", "last_name", "email"):
                self.fields[nombre].disabled = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exclude(
            pk=self.membresia.usuario_id
        ).exists():
            raise forms.ValidationError("Ese correo ya pertenece a otra cuenta.")
        return email
