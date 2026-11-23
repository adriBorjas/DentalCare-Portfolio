"""
URL configuration for dentalcare project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('tratamientos/', include('treatments.urls', namespace='treatments')),
    path('citas/', include('appointments.urls', namespace='appointments')),
    path('', include('core.urls', namespace='core')),
]

# Personalización del panel de administración
admin.site.site_header = 'DentalCare - Panel de Administración'
admin.site.site_title = 'DentalCare Admin'
admin.site.index_title = 'Gestión Clínica DentalCare'
