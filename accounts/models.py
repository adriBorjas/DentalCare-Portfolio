from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        PACIENTE = 'PACIENTE', 'Paciente'
        DENTISTA = 'DENTISTA', 'Dentista'
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'

    role = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.PACIENTE,
        verbose_name='Rol en el Sistema'
    )
    telefono = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Teléfono de contacto'
    )
    must_change_password = models.BooleanField(
        default=False,
        verbose_name='Debe cambiar contraseña',
        help_text='Indica si el usuario debe cambiar su contraseña temporal en su próximo inicio de sesión.'
    )

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    @property
    def es_dentista(self):
        # El administrador es exclusivamente de gestión y no es profesional clínico
        return self.role == self.Rol.DENTISTA and not self.is_superuser

    @property
    def es_paciente(self):
        return self.role == self.Rol.PACIENTE

    @property
    def es_administrador(self):
        return self.is_superuser or self.role == self.Rol.ADMINISTRADOR or self.is_staff

    def __str__(self):
        nombre_completo = self.get_full_name().strip()
        identificador = nombre_completo if nombre_completo else self.username
        return f"{identificador} ({self.get_role_display()})"


class Paciente(models.Model):
    user = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name='perfil_paciente',
        null=True,
        blank=True,
        verbose_name='Usuario asociado'
    )
    nombre = models.CharField(max_length=100, verbose_name='Nombre')
    apellidos = models.CharField(max_length=150, verbose_name='Apellidos')
    telefono = models.CharField(max_length=20, verbose_name='Teléfono')
    email = models.EmailField(blank=True, verbose_name='Correo electrónico')
    dni = models.CharField(max_length=20, blank=True, verbose_name='DNI/NIE')
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name='Fecha de nacimiento')
    direccion = models.CharField(max_length=255, blank=True, verbose_name='Dirección')
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de alta')

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'
        ordering = ['apellidos', 'nombre']

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellidos}".strip()

    def __str__(self):
        if self.dni:
            return f"{self.apellidos}, {self.nombre} (DNI: {self.dni})"
        return f"{self.apellidos}, {self.nombre}"


class Dentista(models.Model):
    user = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name='perfil_dentista',
        verbose_name='Usuario asociado'
    )
    numero_colegiado = models.CharField(max_length=50, blank=True, verbose_name='Nº Colegiado')
    especialidad = models.CharField(max_length=100, default='Odontología General', verbose_name='Especialidad')
    telefono = models.CharField(max_length=20, blank=True, verbose_name='Teléfono profesional')
    activo = models.BooleanField(default=True, verbose_name='En activo')

    class Meta:
        verbose_name = 'Dentista'
        verbose_name_plural = 'Dentistas'
        ordering = ['user__last_name', 'user__first_name']

    @property
    def nombre_completo(self):
        nombre = self.user.get_full_name().strip()
        return f"Dr/a. {nombre}" if nombre else f"Dr/a. {self.user.username}"

    def __str__(self):
        return f"{self.nombre_completo} - {self.especialidad}"


@receiver(post_save, sender=Usuario)
def crear_o_actualizar_perfil_usuario(sender, instance, created, **kwargs):
    """Garantiza la existencia del perfil adecuado al crear el usuario."""
    if created:
        if instance.is_superuser or instance.role == Usuario.Rol.ADMINISTRADOR:
            # Los administradores son exclusivamente para tareas de gestión y no tienen perfil clínico
            return
        elif instance.role == Usuario.Rol.PACIENTE:
            Paciente.objects.get_or_create(
                user=instance,
                defaults={
                    'nombre': instance.first_name or instance.username,
                    'apellidos': instance.last_name or '',
                    'email': instance.email or '',
                    'telefono': instance.telefono or '',
                }
            )
        elif instance.role == Usuario.Rol.DENTISTA:
            Dentista.objects.get_or_create(
                user=instance,
                defaults={
                    'telefono': instance.telefono or '',
                    'especialidad': 'Odontología General'
                }
            )
