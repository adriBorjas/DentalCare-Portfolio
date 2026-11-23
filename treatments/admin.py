from django.contrib import admin
from .models import Tratamiento


@admin.register(Tratamiento)
class TratamientoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'duracion_estimada', 'activo', 'creado_en')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)
