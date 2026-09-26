from django.core.validators import RegexValidator


telefono_validator = RegexValidator(
    regex=r"^\+?[0-9][0-9\s().-]{6,24}$",
    message=(
        "Introduce un teléfono válido de 7 a 25 caracteres; puede incluir "
        "espacios, guiones y paréntesis."
    ),
)
