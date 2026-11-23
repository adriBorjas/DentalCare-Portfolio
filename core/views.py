from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from treatments.models import Tratamiento
from accounts.models import Dentista


def home(request):
    """Página de inicio pública de la clínica DentalCare."""
    tratamientos = Tratamiento.objects.filter(activo=True)[:6]
    dentistas = Dentista.objects.filter(activo=True, user__is_superuser=False)[:4]
    return render(request, 'core/home.html', {
        'tratamientos': tratamientos,
        'dentistas': dentistas,
    })


@login_required
def dashboard(request):
    """Redirige al panel adecuado según el rol del usuario autenticado."""
    if request.user.role == 'DENTISTA' or request.user.is_superuser or request.user.is_staff:
        return redirect('appointments:dentista_agenda')
    elif request.user.es_paciente:
        return redirect('appointments:mis_citas')
    return redirect('home')
