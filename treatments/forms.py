from django import forms
from .models import Tratamiento


class TratamientoForm(forms.ModelForm):
    class Meta:
        model = Tratamiento
        fields = ['nombre', 'descripcion', 'precio', 'duracion_estimada', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Limpieza Dental con Ultrasonidos'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción del procedimiento...'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50', 'placeholder': '0.00'}),
            'duracion_estimada': forms.NumberInput(attrs={'class': 'form-control', 'step': '5', 'placeholder': '30'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nombre': 'Nombre del tratamiento',
            'descripcion': 'Descripción detallada',
            'precio': 'Precio (€)',
            'duracion_estimada': 'Duración orientativa (minutos)',
            'activo': 'Tratamiento disponible para reservas',
        }
