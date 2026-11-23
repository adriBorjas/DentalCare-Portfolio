from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    # Agenda pública de disponibilidad (accesible para cualquier visitante)
    path('calendario/', views.agenda_publica, name='agenda_publica'),
    path('solicitar/', views.solicitar_cita_publica, name='solicitar_cita_publica'),
    path('solicitar/acceso/', views.pre_reserva_acceso, name='pre_reserva_acceso'),
    path('confirmar-reserva/', views.confirmar_cita_pendiente, name='confirmar_cita_pendiente'),

    # Rutas para el paciente autenticado
    path('mis-citas/', views.mis_citas, name='mis_citas'),
    path('reservar/', views.reservar_cita, name='reservar_cita'),
    path('cancelar/<int:pk>/', views.cancelar_cita_paciente, name='cancelar_cita_paciente'),

    # Rutas para el dentista / administración clínica
    path('agenda/', views.dentista_agenda, name='dentista_agenda'),
    path('agenda/nueva/', views.dentista_crear_cita, name='dentista_crear_cita'),
    path('agenda/<int:pk>/editar/', views.dentista_editar_cita, name='dentista_editar_cita'),
    path('agenda/<int:pk>/eliminar/', views.dentista_eliminar_cita, name='dentista_eliminar_cita'),
    path('agenda/<int:pk>/estado/<str:nuevo_estado>/', views.dentista_cambiar_estado_rapido, name='cambiar_estado_rapido'),

    # API de búsqueda y detalle de citas
    path('api/buscar/', views.buscar_citas_api, name='buscar_citas_api'),
    path('api/detalle/<int:pk>/', views.detalle_cita_api, name='detalle_cita_api'),

    # Rutas para horarios y bloqueos de disponibilidad
    path('disponibilidad/', views.gestion_disponibilidad, name='gestion_disponibilidad'),
    path('horario/nuevo/', views.crear_horario, name='crear_horario'),
    path('horario/<int:pk>/eliminar/', views.eliminar_horario, name='eliminar_horario'),
    path('bloqueo/nuevo/', views.crear_bloqueo, name='crear_bloqueo'),
    path('bloqueo/<int:pk>/eliminar/', views.eliminar_bloqueo, name='eliminar_bloqueo'),
]
