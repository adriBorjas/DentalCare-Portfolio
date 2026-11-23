from django.contrib import admin
from .models import HorarioDentista, BloqueoDisponibilidad, Cita


@admin.register(HorarioDentista)
class HorarioDentistaAdmin(admin.ModelAdmin):
    list_display = ('dentista', 'dia_semana', 'hora_apertura', 'hora_cierre', 'activo')
    list_filter = ('dentista', 'dia_semana', 'activo')
    ordering = ('dentista', 'dia_semana', 'hora_apertura')


@admin.register(BloqueoDisponibilidad)
class BloqueoDisponibilidadAdmin(admin.ModelAdmin):
    list_display = ('dentista', 'fecha', 'hora_inicio', 'hora_fin', 'motivo')
    list_filter = ('dentista', 'fecha')
    search_fields = ('dentista__user__first_name', 'dentista__user__last_name', 'motivo')
    ordering = ('-fecha', 'hora_inicio')


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'fecha', 'hora_inicio', 'hora_fin', 'dentista',
        'nombre_paciente_display', 'telefono_paciente_display',
        'tratamiento', 'estado', 'is_deleted'
    )
    list_filter = ('estado', 'is_deleted', 'fecha', 'dentista', 'tratamiento')
    search_fields = (
        'paciente__nombre', 'paciente__apellidos', 'paciente_nombre',
        'paciente_telefono', 'dentista__user__first_name', 'dentista__user__last_name'
    )
    date_hierarchy = 'fecha'
    ordering = ('-fecha', '-hora_inicio')
    actions = ['marcar_como_confirmada', 'marcar_como_completada', 'soft_delete_citas', 'restaurar_citas']

    @admin.action(description='Marcar seleccionadas como Confirmadas')
    def marcar_como_confirmada(self, request, queryset):
        queryset.update(estado=Cita.Estado.CONFIRMADA)

    @admin.action(description='Marcar seleccionadas como Completadas')
    def marcar_como_completada(self, request, queryset):
        queryset.update(estado=Cita.Estado.COMPLETADA)

    @admin.action(description='Borrado lógico de citas seleccionadas')
    def soft_delete_citas(self, request, queryset):
        queryset.update(is_deleted=True, estado=Cita.Estado.ELIMINADA)

    @admin.action(description='Restaurar citas eliminadas lógicamente')
    def restaurar_citas(self, request, queryset):
        queryset.update(is_deleted=False, estado=Cita.Estado.PENDIENTE)
