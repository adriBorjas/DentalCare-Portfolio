from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Paciente, Dentista


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'telefono', 'must_change_password', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'must_change_password')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'telefono')
    ordering = ('username',)

    fieldsets = UserAdmin.fieldsets + (
        ('Información de Rol DentalCare', {
            'fields': ('role', 'telefono', 'must_change_password')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información de Rol DentalCare', {
            'fields': ('role', 'telefono', 'must_change_password')
        }),
    )


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('apellidos', 'nombre', 'telefono', 'email', 'dni', 'fecha_nacimiento', 'user')
    search_fields = ('nombre', 'apellidos', 'telefono', 'email', 'dni')
    list_filter = ('creado_en',)


@admin.register(Dentista)
class DentistaAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'especialidad', 'numero_colegiado', 'telefono', 'activo')
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'especialidad', 'numero_colegiado')
    list_filter = ('especialidad', 'activo')
