from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Usuario, Paciente
import secrets
import string


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre de usuario',
            'autofocus': True
        }),
        label='Usuario'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña'
        }),
        label='Contraseña'
    )


class RegistroPacienteForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: carlosg'}),
        label='Nombre de usuario'
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Carlos'}),
        label='Nombre'
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Gómez Ruiz'}),
        label='Apellidos'
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'carlos@ejemplo.com'}),
        label='Correo electrónico'
    )
    telefono = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 600123456'}),
        label='Teléfono móvil'
    )
    dni = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678Z'}),
        label='DNI/NIE (Opcional)'
    )
    fecha_nacimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha de nacimiento (Opcional)'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Mínimo 6 caracteres'}),
        label='Contraseña'
    )
    password_confirmacion = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repita la contraseña'}),
        label='Confirmar Contraseña'
    )

    class Meta:
        model = Usuario
        fields = ['username', 'first_name', 'last_name', 'email', 'telefono']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if Usuario.objects.filter(username__iexact=username).exists():
            raise ValidationError('Este nombre de usuario ya está registrado.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirmacion')

        if p1 and p2 and p1 != p2:
            self.add_error('password_confirmacion', 'Las contraseñas no coinciden.')

        if p1:
            validate_password(p1)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        # El registro público SOLO permite crear cuentas de rol PACIENTE
        user.role = Usuario.Rol.PACIENTE
        user.is_staff = False
        user.is_superuser = False
        user.must_change_password = False
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            paciente, _ = Paciente.objects.get_or_create(user=user)
            paciente.nombre = user.first_name
            paciente.apellidos = user.last_name
            paciente.email = user.email
            paciente.telefono = user.telefono
            paciente.dni = self.cleaned_data.get('dni', '')
            paciente.fecha_nacimiento = self.cleaned_data.get('fecha_nacimiento')
            paciente.save()
        return user


class CrearPacientePorDentistaForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: pac_carlos'}),
        label='Nombre de usuario para el paciente'
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del paciente'}),
        label='Nombre'
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos del paciente'}),
        label='Apellidos'
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'}),
        label='Correo electrónico'
    )
    telefono = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '600123456'}),
        label='Teléfono de contacto'
    )
    dni = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678Z'}),
        label='DNI/NIE'
    )
    fecha_nacimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha de nacimiento'
    )
    direccion = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Calle, número, ciudad'}),
        label='Dirección'
    )
    password_temporal = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Dejar en blanco para autogenerar contraseña temporal'
        }),
        label='Contraseña temporal personalizada (opcional)',
        help_text='Si se deja en blanco, el sistema generará una clave aleatoria segura.'
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if Usuario.objects.filter(username__iexact=username).exists():
            raise ValidationError('Este nombre de usuario ya está registrado en la base de datos.')
        return username

    def save(self):
        data = self.cleaned_data
        pwd = data.get('password_temporal')
        if not pwd or len(pwd.strip()) < 6:
            # Generar contraseña temporal segura
            caracteres = string.ascii_letters + string.digits + '!@#$'
            pwd = ''.join(secrets.choice(caracteres) for _ in range(8))
        else:
            pwd = pwd.strip()

        user = Usuario.objects.create_user(
            username=data['username'],
            email=data.get('email', ''),
            first_name=data['first_name'],
            last_name=data['last_name'],
            telefono=data['telefono'],
            role=Usuario.Rol.PACIENTE,
            must_change_password=True,
            password=pwd
        )

        paciente, _ = Paciente.objects.get_or_create(user=user)
        paciente.nombre = user.first_name
        paciente.apellidos = user.last_name
        paciente.email = user.email
        paciente.telefono = user.telefono
        paciente.dni = data.get('dni', '')
        paciente.fecha_nacimiento = data.get('fecha_nacimiento')
        paciente.direccion = data.get('direccion', '')
        paciente.save()

        return user, paciente, pwd


class CambiarPasswordTemporalForm(forms.Form):
    password_nueva = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nueva contraseña segura'}),
        label='Nueva Contraseña'
    )
    password_confirmacion = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repita la nueva contraseña'}),
        label='Confirmar Nueva Contraseña'
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password_nueva')
        p2 = cleaned_data.get('password_confirmacion')

        if p1 and p2 and p1 != p2:
            self.add_error('password_confirmacion', 'Las contraseñas no coinciden.')

        if p1:
            validate_password(p1, user=self.user)

        return cleaned_data

    def save(self):
        pwd = self.cleaned_data['password_nueva']
        self.user.set_password(pwd)
        self.user.must_change_password = False
        self.user.save()
        return self.user
