from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('registro/', views.registro_paciente, name='registro'),
    path('cambiar-password-temporal/', views.cambiar_password_temporal, name='cambiar_password_temporal'),
    path('pacientes/', views.dentista_lista_pacientes, name='lista_pacientes'),
    path('pacientes/nuevo/', views.dentista_crear_paciente, name='crear_paciente'),
]
