from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, date, time
from accounts.models import Dentista, Paciente
from treatments.models import Tratamiento


class HorarioDentista(models.Model):
    DIAS_SEMANA = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    dentista = models.ForeignKey(
        Dentista,
        on_delete=models.CASCADE,
        related_name='horarios',
        verbose_name='Dentista'
    )
    dia_semana = models.IntegerField(
        choices=DIAS_SEMANA,
        verbose_name='Día de la semana'
    )
    hora_apertura = models.TimeField(verbose_name='Hora de apertura')
    hora_cierre = models.TimeField(verbose_name='Hora de cierre')
    activo = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        verbose_name = 'Horario de Dentista'
        verbose_name_plural = 'Horarios de Dentistas'
        ordering = ['dentista', 'dia_semana', 'hora_apertura']

    def clean(self):
        if self.hora_apertura and self.hora_cierre and self.hora_apertura >= self.hora_cierre:
            raise ValidationError({
                'hora_cierre': 'La hora de cierre debe ser posterior a la hora de apertura.'
            })

    def __str__(self):
        return f"{self.dentista.nombre_completo} - {self.get_dia_semana_display()}: {self.hora_apertura.strftime('%H:%M')} a {self.hora_cierre.strftime('%H:%M')}"


class BloqueoDisponibilidad(models.Model):
    dentista = models.ForeignKey(
        Dentista,
        on_delete=models.CASCADE,
        related_name='bloqueos',
        verbose_name='Dentista'
    )
    fecha = models.DateField(verbose_name='Fecha del bloqueo')
    hora_inicio = models.TimeField(verbose_name='Hora de inicio')
    hora_fin = models.TimeField(verbose_name='Hora de fin')
    motivo = models.CharField(max_length=200, verbose_name='Motivo del bloqueo (vacaciones, descanso, etc.)')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Bloqueo de Disponibilidad'
        verbose_name_plural = 'Bloqueos de Disponibilidad'
        ordering = ['fecha', 'hora_inicio']

    def clean(self):
        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            raise ValidationError({
                'hora_fin': 'La hora de fin debe ser posterior a la hora de inicio.'
            })

    def __str__(self):
        return f"Bloqueo {self.dentista.nombre_completo}: {self.fecha} ({self.hora_inicio.strftime('%H:%M')} - {self.hora_fin.strftime('%H:%M')}) - {self.motivo}"


class CitaManager(models.Manager):
    def activas(self):
        """Retorna solo las citas no eliminadas y no canceladas."""
        return self.get_queryset().filter(is_deleted=False).exclude(estado=Cita.Estado.ELIMINADA)

    def no_eliminadas(self):
        """Retorna todas las citas excepto las eliminadas lógicamente."""
        return self.get_queryset().filter(is_deleted=False).exclude(estado=Cita.Estado.ELIMINADA)


class Cita(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        CONFIRMADA = 'CONFIRMADA', 'Confirmada'
        COMPLETADA = 'COMPLETADA', 'Completada'
        CANCELADA = 'CANCELADA', 'Cancelada'
        ELIMINADA = 'ELIMINADA', 'Eliminada'

    TRANSICIONES_ESTADO = {
        Estado.PENDIENTE: {Estado.CONFIRMADA, Estado.CANCELADA},
        Estado.CONFIRMADA: {Estado.COMPLETADA, Estado.CANCELADA},
        Estado.COMPLETADA: set(),
        Estado.CANCELADA: set(),
        Estado.ELIMINADA: set(),
    }

    dentista = models.ForeignKey(
        Dentista,
        on_delete=models.PROTECT,
        related_name='citas',
        verbose_name='Dentista asignado'
    )
    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='citas',
        verbose_name='Paciente con ficha'
    )
    # Campos para pacientes sin cuenta / invitados
    paciente_nombre = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Nombre del Paciente (sin cuenta)'
    )
    paciente_telefono = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='Teléfono del Paciente (sin cuenta)'
    )
    paciente_email = models.EmailField(
        blank=True,
        verbose_name='Email del Paciente (sin cuenta)'
    )

    tratamiento = models.ForeignKey(
        Tratamiento,
        on_delete=models.PROTECT,
        related_name='citas',
        verbose_name='Tratamiento'
    )
    fecha = models.DateField(verbose_name='Fecha de la cita')
    hora_inicio = models.TimeField(verbose_name='Hora de inicio')
    hora_fin = models.TimeField(verbose_name='Hora de fin')

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        verbose_name='Estado de la cita'
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Borrado lógico',
        help_text='Indica si la cita fue eliminada sin suprimir su registro físico.'
    )
    motivo_cancelacion = models.TextField(
        blank=True,
        verbose_name='Motivo de cancelación / notas de estado'
    )
    notas = models.TextField(
        blank=True,
        verbose_name='Observaciones o notas clínicas preliminares'
    )

    creado_en = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name='Última modificación')

    objects = CitaManager()

    class Meta:
        verbose_name = 'Cita'
        verbose_name_plural = 'Citas'
        ordering = ['fecha', 'hora_inicio']

    @property
    def nombre_paciente_display(self):
        if self.paciente:
            return self.paciente.nombre_completo
        return self.paciente_nombre or 'Paciente sin identificar'

    @property
    def telefono_paciente_display(self):
        if self.paciente:
            return self.paciente.telefono
        return self.paciente_telefono or '-'

    @property
    def email_paciente_display(self):
        if self.paciente:
            return self.paciente.email
        return self.paciente_email or '-'

    @property
    def duracion_minutos(self):
        if self.hora_inicio and self.hora_fin:
            inicio_dt = datetime.combine(date.today(), self.hora_inicio)
            fin_dt = datetime.combine(date.today(), self.hora_fin)
            diff = (fin_dt - inicio_dt).total_seconds() / 60
            return int(diff) if diff > 0 else 0
        return 0

    def clean(self):
        if self.pk:
            estado_anterior = Cita.objects.filter(pk=self.pk).values_list('estado', flat=True).first()
            if estado_anterior and self.estado != estado_anterior and self.estado not in self.TRANSICIONES_ESTADO.get(estado_anterior, set()):
                raise ValidationError({
                    'estado': (
                        f'No se permite cambiar una cita de "{self.get_estado_display()}" '
                        'desde su estado actual.'
                    )
                })

        # 1. Validación de paciente: debe tener paciente con ficha o datos mínimos si no tiene cuenta
        if not self.paciente:
            if not self.paciente_nombre or not self.paciente_telefono:
                raise ValidationError({
                    'paciente_nombre': 'Para pacientes sin cuenta es obligatorio registrar al menos nombre y teléfono.'
                })

        # 2. Validación de horas: hora_fin debe ser posterior a hora_inicio
        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            raise ValidationError({
                'hora_fin': 'La hora de fin debe ser posterior a la hora de inicio de la cita.'
            })

        # Si la cita está cancelada o eliminada, no validamos solapamientos
        if self.estado in [self.Estado.CANCELADA, self.Estado.ELIMINADA] or self.is_deleted:
            return

        if not (self.dentista_id and self.fecha and self.hora_inicio and self.hora_fin):
            return

        # 3. Validación de solapamiento con otras citas del mismo dentista
        solapadas = Cita.objects.filter(
            dentista=self.dentista,
            fecha=self.fecha,
            is_deleted=False
        ).exclude(
            estado__in=[self.Estado.CANCELADA, self.Estado.ELIMINADA]
        ).filter(
            hora_inicio__lt=self.hora_fin,
            hora_fin__gt=self.hora_inicio
        )

        if self.pk:
            solapadas = solapadas.exclude(pk=self.pk)

        if solapadas.exists():
            cita_choque = solapadas.first()
            raise ValidationError({
                'hora_inicio': (
                    f"El dentista ya tiene una cita asignada en ese intervalo horario: "
                    f"{cita_choque.hora_inicio.strftime('%H:%M')} a {cita_choque.hora_fin.strftime('%H:%M')} "
                    f"({cita_choque.nombre_paciente_display})."
                )
            })

        # 4. Validación de bloqueos de disponibilidad del dentista
        bloqueos = BloqueoDisponibilidad.objects.filter(
            dentista=self.dentista,
            fecha=self.fecha,
            hora_inicio__lt=self.hora_fin,
            hora_fin__gt=self.hora_inicio
        )
        if bloqueos.exists():
            bloqueo = bloqueos.first()
            raise ValidationError({
                'hora_inicio': (
                    f"El dentista tiene un bloqueo de disponibilidad programado: "
                    f"{bloqueo.motivo} ({bloqueo.hora_inicio.strftime('%H:%M')} - {bloqueo.hora_fin.strftime('%H:%M')})."
                )
            })

        # 5. Validación de horario laboral del dentista (si tiene horarios configurados)
        horarios_dentista = HorarioDentista.objects.filter(dentista=self.dentista, activo=True)
        if horarios_dentista.exists():
            dia_sem = self.fecha.weekday()
            horarios_dia = horarios_dentista.filter(dia_semana=dia_sem)
            if not horarios_dia.exists():
                dias_dict = dict(HorarioDentista.DIAS_SEMANA)
                nombre_dia = dias_dict.get(dia_sem, 'ese día')
                raise ValidationError({
                    'fecha': f"El {self.dentista.nombre_completo} no pasa consulta los {nombre_dia}."
                })

            en_horario = False
            for h in horarios_dia:
                if self.hora_inicio >= h.hora_apertura and self.hora_fin <= h.hora_cierre:
                    en_horario = True
                    break

            if not en_horario:
                franjas = ", ".join([f"{h.hora_apertura.strftime('%H:%M')} - {h.hora_cierre.strftime('%H:%M')}" for h in horarios_dia])
                raise ValidationError({
                    'hora_inicio': f"La cita no se encuentra dentro del horario de consulta del dentista para este día ({franjas})."
                })

    def delete(self, using=None, keep_parents=False):
        """Soft delete: marca la cita como eliminada sin borrar el registro de la base de datos."""
        self.is_deleted = True
        self.estado = self.Estado.ELIMINADA
        self.save(update_fields=['is_deleted', 'estado'])

    def hard_delete(self, using=None, keep_parents=False):
        """Eliminación física real si se requiere para mantenimiento."""
        super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return f"Cita #{self.id} - {self.fecha} {self.hora_inicio.strftime('%H:%M')} | {self.nombre_paciente_display} con {self.dentista.nombre_completo} [{self.get_estado_display()}]"
