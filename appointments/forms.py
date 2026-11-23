from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, date, time, timedelta
from .models import Cita, HorarioDentista, BloqueoDisponibilidad
from accounts.models import Dentista, Paciente
from treatments.models import Tratamiento


class ReservaCitaPacienteForm(forms.Form):
    dentista = forms.ModelChoiceField(
        queryset=Dentista.objects.filter(activo=True, user__is_superuser=False),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Dentista Especialista',
        empty_label='-- Seleccione un dentista --'
    )
    tratamiento = forms.ModelChoiceField(
        queryset=Tratamiento.objects.filter(activo=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tratamiento solicitado',
        empty_label='-- Seleccione el tratamiento --'
    )
    fecha = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha de la cita'
    )
    hora_inicio = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '900'}),
        label='Hora deseada de inicio'
    )
    notas = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Indique motivo o notas para el dentista (opcional)...'}),
        label='Observaciones o motivo de la consulta'
    )

    def __init__(self, paciente, *args, **kwargs):
        self.paciente = paciente
        super().__init__(*args, **kwargs)

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if fecha and fecha < timezone.localdate():
            raise ValidationError('No es posible reservar citas en fechas pasadas.')
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        dentista = cleaned_data.get('dentista')
        tratamiento = cleaned_data.get('tratamiento')
        fecha = cleaned_data.get('fecha')
        hora_inicio = cleaned_data.get('hora_inicio')

        if dentista and tratamiento and fecha and hora_inicio:
            # Calcular hora_fin orientativa a partir de la duración del tratamiento
            dt_inicio = datetime.combine(fecha, hora_inicio)
            duracion = tratamiento.duracion_estimada or 30
            dt_fin = dt_inicio + timedelta(minutes=duracion)
            hora_fin = dt_fin.time()
            cleaned_data['hora_fin'] = hora_fin

            # Instancia preliminar para aplicar validaciones del modelo (solapamientos, bloques, etc.)
            cita_temp = Cita(
                dentista=dentista,
                paciente=self.paciente,
                tratamiento=tratamiento,
                fecha=fecha,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
                estado=Cita.Estado.PENDIENTE
            )
            try:
                cita_temp.clean()
            except ValidationError as e:
                if hasattr(e, 'message_dict'):
                    for field, errors in e.message_dict.items():
                        for err in errors:
                            self.add_error(field if field in self.fields else None, err)
                else:
                    self.add_error(None, e.message)

        return cleaned_data

    def save(self):
        data = self.cleaned_data
        cita = Cita.objects.create(
            dentista=data['dentista'],
            paciente=self.paciente,
            tratamiento=data['tratamiento'],
            fecha=data['fecha'],
            hora_inicio=data['hora_inicio'],
            hora_fin=data['hora_fin'],
            estado=Cita.Estado.PENDIENTE,
            notas=data.get('notas', '')
        )
        return cita


class CitaDentistaForm(forms.ModelForm):
    # Permite asociar paciente registrado o registrar datos de paciente sin cuenta
    tipo_paciente = forms.ChoiceField(
        choices=[('REGISTRADO', 'Paciente Registrado'), ('INVITADO', 'Paciente Sin Cuenta')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='REGISTRADO',
        label='Tipo de Paciente'
    )

    class Meta:
        model = Cita
        fields = [
            'dentista', 'paciente', 'paciente_nombre', 'paciente_telefono',
            'paciente_email', 'tratamiento', 'fecha', 'hora_inicio', 'hora_fin',
            'estado', 'notas', 'motivo_cancelacion'
        ]
        widgets = {
            'dentista': forms.Select(attrs={'class': 'form-select'}),
            'paciente': forms.Select(attrs={'class': 'form-select'}),
            'paciente_nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre y apellidos'}),
            'paciente_telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono de contacto'}),
            'paciente_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'}),
            'tratamiento': forms.Select(attrs={'class': 'form-select'}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'hora_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '900'}),
            'hora_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '900'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Notas internas...'}),
            'motivo_cancelacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Motivo si se cancela'}),
        }
        labels = {
            'hora_fin': 'Hora de fin (El dentista puede ajustar la duración real)',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dentista'].queryset = Dentista.objects.filter(activo=True, user__is_superuser=False)
        if user and not (user.is_superuser or user.is_staff):
            dentista = getattr(user, 'perfil_dentista', None)
            self.fields['dentista'].queryset = self.fields['dentista'].queryset.filter(
                pk=getattr(dentista, 'pk', None)
            )
        if self.instance and self.instance.pk:
            if not self.instance.paciente:
                self.fields['tipo_paciente'].initial = 'INVITADO'
            self.fields['paciente'].required = False
        else:
            self.fields['paciente'].required = False

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_paciente')
        paciente = cleaned_data.get('paciente')
        p_nombre = cleaned_data.get('paciente_nombre')
        p_tel = cleaned_data.get('paciente_telefono')

        if tipo == 'REGISTRADO':
            if not paciente:
                self.add_error('paciente', 'Debe seleccionar un paciente registrado de la lista.')
        else:
            cleaned_data['paciente'] = None
            if not p_nombre:
                self.add_error('paciente_nombre', 'Indique el nombre del paciente sin cuenta.')
            if not p_tel:
                self.add_error('paciente_telefono', 'Indique el teléfono del paciente sin cuenta.')

        # Validación del modelo
        cita = self.instance
        for field, value in cleaned_data.items():
            if hasattr(cita, field):
                setattr(cita, field, value)

        try:
            cita.clean()
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                for field, errors in e.message_dict.items():
                    for err in errors:
                        self.add_error(field if field in self.fields else None, err)
            else:
                self.add_error(None, e.message)

        return cleaned_data


class HorarioDentistaForm(forms.ModelForm):
    class Meta:
        model = HorarioDentista
        fields = ['dia_semana', 'hora_apertura', 'hora_cierre', 'activo']
        widgets = {
            'dia_semana': forms.Select(attrs={'class': 'form-select'}),
            'hora_apertura': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '1800'}),
            'hora_cierre': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '1800'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BloqueoDisponibilidadForm(forms.ModelForm):
    class Meta:
        model = BloqueoDisponibilidad
        fields = ['fecha', 'hora_inicio', 'hora_fin', 'motivo']
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'hora_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '900'}),
            'hora_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'step': '900'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Vacaciones, Congreso, Guardia, Cirugía...'}),
        }
