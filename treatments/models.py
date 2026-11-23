from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Tratamiento(models.Model):
    nombre = models.CharField(
        max_length=120,
        unique=True,
        verbose_name='Nombre del Tratamiento'
    )
    descripcion = models.TextField(
        blank=True,
        verbose_name='Descripción'
    )
    precio = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Precio (€)'
    )
    duracion_estimada = models.PositiveIntegerField(
        help_text='Duración orientativa en minutos. No impone la duración real de la cita.',
        verbose_name='Duración Orientativa (minutos)'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tratamiento'
        verbose_name_plural = 'Tratamientos'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.duracion_estimada} min - {self.precio} €)"
