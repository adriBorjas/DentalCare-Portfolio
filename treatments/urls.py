from django.urls import path
from . import views

app_name = 'treatments'

urlpatterns = [
    path('', views.lista_tratamientos, name='lista'),
    path('nuevo/', views.crear_tratamiento, name='crear'),
    path('<int:pk>/editar/', views.editar_tratamiento, name='editar'),
    path('<int:pk>/toggle/', views.toggle_activo_tratamiento, name='toggle_activo'),
]
